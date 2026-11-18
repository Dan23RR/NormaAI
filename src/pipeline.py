"""
NormaAI Ingestion Pipeline - End-to-end: EUR-Lex → Parse → Chunk → Context → Index.

This is the main orchestration script that:
1. Crawls EUR-Lex for all core framework regulations
2. Downloads full text HTML for each regulation
3. Chunks HTML into semantically meaningful pieces
4. Enriches chunks with contextual prefixes (improves retrieval ~10-15%)
5. Indexes chunks into Qdrant with hybrid search (dense + sparse)

Usage:
    python -m src.pipeline --action seed     # Initial seed: crawl + index all tracked acts
    python -m src.pipeline --action seed --acts AI_ACT,32022L2464 --lang IT   # subset
    python -m src.pipeline --action seed --recreate   # drop + rebuild the collection
    python -m src.pipeline --action update   # Check for amendments and index new content
    python -m src.pipeline --action stats    # Show collection statistics

Scheduled jobs (cron on the server; they do not load the embedding model):
    python -m src.pipeline --action recheck-documents   # weekly: watched documents
    python -m src.pipeline --action check-freshness     # nightly: corpus vs CELLAR
"""

import argparse
import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from src.config import get_settings
from src.crawler.eurlex import celex as celex_utils
from src.crawler.eurlex.client import (
    CORE_FRAMEWORKS,
    TRACKED_ACTS,
    EurLexClient,
    get_tracked_act,
)
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import HybridIndexer, indexer_kwargs_from_settings
from src.nlp.processing.dots_ocr_processor import UnifiedDocumentProcessor

logger = logging.getLogger("normaai.pipeline")


class IngestionPipeline:
    """
    End-to-end pipeline: EUR-Lex SPARQL → HTML Download → Chunking → Context → Qdrant Indexing.
    """

    def __init__(self):
        settings = get_settings()
        self.eurlex = EurLexClient(
            endpoint=settings.eurlex_sparql_endpoint,
            request_delay=1.5,
        )
        self.indexer = HybridIndexer(**indexer_kwargs_from_settings(settings))
        self.contextual_chunker = ContextualChunker()
        self.doc_processor = UnifiedDocumentProcessor()

    def _enrich(self, chunks: list) -> list:
        """Add the contextual prefix to every chunk, keeping its metadata."""
        enriched = []
        for chunk in chunks:
            ctx = self.contextual_chunker.enrich_single(
                text=chunk.text,
                framework=chunk.metadata.get("framework", ""),
                article=chunk.metadata.get("article_number", ""),
                section=chunk.metadata.get("section_title", ""),
            )
            # Merge original metadata
            ctx.metadata.update(chunk.metadata)
            enriched.append(ctx)
        return enriched

    def _seed_eurlex_act(self, reg, download_celex: str, lang: str, batch_size: int) -> dict | None:
        """Download, chunk, enrich and (re)index one act in one language.

        Returns a summary dict, or None when no usable text was obtained.
        """
        act = get_tracked_act(reg.celex)
        html = self.eurlex.download_full_text_html(download_celex, lang=lang)
        if not html and download_celex != reg.celex:
            logger.warning(
                f"  {reg.celex} [{lang}]: consolidated text {download_celex} unavailable, "
                "falling back to the original act"
            )
            download_celex = reg.celex
            html = self.eurlex.download_full_text_html(download_celex, lang=lang)
        if not html:
            logger.warning(f"  FAILED to download {reg.celex} [{lang}]")
            return None
        if len(html.strip()) < 500:
            logger.warning(
                f"  SKIPPED {reg.celex} [{lang}]: HTML too short ({len(html)} chars), "
                "likely error page"
            )
            return None

        chunker = EURLexHTMLChunker(
            celex=reg.celex,
            framework=reg.framework,
            lang=lang,
            source_celex=download_celex,
            eli_type=act.eli_type if act else None,
            title=reg.title or None,
        )
        chunks = chunker.chunk_html(html)
        frameworks = list(act.all_frameworks) if act else [reg.framework]
        # Populate temporal metadata from the real EUR-Lex record so the
        # "exclude superseded" filter is actually effective. effective_date
        # enables date reasoning; a not-in-force regulation is marked superseded
        # so it is NOT served as current law.
        for c in chunks:
            c.metadata["frameworks"] = frameworks
            if getattr(reg, "date_document", None):
                c.metadata["effective_date"] = reg.date_document
            if getattr(reg, "is_in_force", None) is False:
                c.metadata["superseded_by"] = "not_in_force"

        enriched = self._enrich(chunks)
        # Idempotent per act + language: delete the previous points, upsert the new.
        count = (
            self.indexer.reindex_act(reg.celex, lang, enriched, batch_size=batch_size)
            if enriched
            else 0
        )
        consolidated_as_of = (
            celex_utils.consolidated_as_of(download_celex)
            if isinstance(download_celex, str)
            else None
        )
        version = f"consolidated {consolidated_as_of}" if consolidated_as_of else "original text"
        logger.info(
            f"  OK {reg.celex} [{lang}] {version}: {count} chunks ({len(html):,} chars HTML)"
        )
        return {
            "celex": reg.celex,
            "framework": reg.framework,
            "lang": lang,
            "source_celex": download_celex,
            "consolidated_as_of": consolidated_as_of,
            "chunks": count,
            "title": (reg.title or "")[:120],
        }

    def seed(
        self,
        recreate_collection: bool = False,
        acts: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict:
        """
        Initial seed: download and index the tracked EU acts.

        No Italian law: the old Normattiva client called endpoints that answer
        HTTP 409 and was removed. DATA_SOURCE=normattiva or both only logs that.

        Idempotent: every (act, language) pair is re-indexed in place (delete +
        upsert with deterministic point ids), so re-running the seed never
        duplicates chunks. Prefers the latest CELLAR consolidated text of each
        act when one exists (EURLEX_PREFER_CONSOLIDATED), downloads every
        language in CORPUS_LANGUAGES, and finally writes the corpus metadata
        point (``corpus_as_of``, acts, embedding model).

        Args:
            recreate_collection: drop and re-create the Qdrant collection first
                (needed when the sparse IDF modifier or the embedding model changed).
            acts: optional CELEX ids and/or framework names restricting the seed.
            languages: optional language codes (default: settings.corpus_languages).
        """
        logger.info("=" * 60)
        logger.info("NORMAAI SEED PIPELINE - Building regulatory knowledge base")
        logger.info("=" * 60)

        start_time = time.time()
        settings = get_settings()
        data_source = settings.data_source  # "eurlex"; "normattiva"/"both" index no Italian law
        raw_langs = languages or settings.corpus_language_list
        langs = list(dict.fromkeys(celex_utils.normalize_lang(code) for code in raw_langs))
        prefer_consolidated = bool(getattr(settings, "eurlex_prefer_consolidated", True))
        batch_size = settings.embedding_batch_size

        # Step 1: Setup Qdrant collection
        logger.info("[1/4] Setting up Qdrant collection...")
        self.indexer.setup_collection(recreate=recreate_collection)

        download_stats_eurlex = {"success": 0, "failed": 0, "total_chunks": 0}
        indexed_acts: list[dict] = []
        indexed = 0

        # Step 2-3: EUR-Lex acts, one (act, language) at a time
        if data_source in ("eurlex", "both"):
            logger.info(
                f"[2/4] Crawling EUR-Lex metadata for the tracked acts "
                f"(languages: {', '.join(langs)}, consolidated: {prefer_consolidated})..."
            )
            regulations = self.eurlex.crawl_all_core_frameworks(celex_filter=acts, unique=True)
            logger.info(
                f"  {len(regulations)} acts selected across {len(CORE_FRAMEWORKS)} frameworks"
            )

            logger.info("[3/4] Downloading, chunking and indexing EUR-Lex texts...")
            for reg in regulations:
                logger.info(f"  Processing {reg.celex} ({reg.framework}): {reg.title[:60]}...")
                download_celex = self.eurlex.resolve_download_celex(
                    reg.celex, prefer_consolidated=prefer_consolidated
                )
                if not isinstance(download_celex, str) or not download_celex:
                    download_celex = reg.celex
                for lang in langs:
                    result = self._seed_eurlex_act(reg, download_celex, lang, batch_size)
                    if result is None:
                        download_stats_eurlex["failed"] += 1
                        continue
                    download_stats_eurlex["success"] += 1
                    download_stats_eurlex["total_chunks"] += result["chunks"]
                    indexed += result["chunks"]
                    indexed_acts.append(result)

        # Italian law is not indexed: the document check reads it through the
        # newer open data API (src/document_check/normattiva.py) instead.
        if data_source in ("normattiva", "both"):
            logger.warning(
                f"  DATA_SOURCE={data_source}: no Italian law goes into the Q&A corpus, "
                "only EUR-Lex (set DATA_SOURCE=eurlex)"
            )

        # Step 4: corpus metadata - only when something was indexed, so an empty
        # seed never makes the corpus look ready.
        corpus_meta = None
        if indexed > 0:
            logger.info("[4/4] Writing corpus metadata point...")
            try:
                corpus_meta = self.indexer.write_corpus_meta(
                    acts=indexed_acts,
                    embedding_model=settings.embedding_model,
                    extra={
                        "languages": langs,
                        "data_source": data_source,
                        "prefer_consolidated": prefer_consolidated,
                    },
                )
            except Exception as e:
                logger.warning(f"  corpus metadata write failed: {e}")
        corpus_as_of = corpus_meta.get("corpus_as_of") if isinstance(corpus_meta, dict) else None

        elapsed = time.time() - start_time

        # Summary
        total_downloads = download_stats_eurlex["success"]
        total_failed = download_stats_eurlex["failed"]
        total_chunks_created = download_stats_eurlex["total_chunks"]

        stats = {
            "action": "seed",
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "data_source": data_source,
            "languages": langs,
            "prefer_consolidated": prefer_consolidated,
            "eurlex": download_stats_eurlex,
            "total_downloads_success": total_downloads,
            "total_downloads_failed": total_failed,
            "total_chunks": total_chunks_created,
            "chunks_indexed": indexed,
            "frameworks": list(CORE_FRAMEWORKS.keys()),
            "acts": indexed_acts,
            "corpus_as_of": corpus_as_of,
            "contextual_enrichment": True,
        }

        logger.info("=" * 60)
        logger.info("SEED COMPLETE")
        logger.info(f"  Data source: {data_source} | languages: {', '.join(langs)}")
        for entry in indexed_acts:
            version = entry["consolidated_as_of"] or "original"
            logger.info(
                f"  {entry['celex']:<12} {entry['lang']:<3} {entry['framework']:<9} "
                f"{version:<11} {entry['chunks']:>5} chunks"
            )
        logger.info(
            f"  EUR-Lex:    {download_stats_eurlex['success']} OK, {download_stats_eurlex['failed']} failed"
        )
        logger.info(f"  Chunks:     {stats['chunks_indexed']} indexed (with contextual enrichment)")
        logger.info(f"  Corpus as of: {corpus_as_of or 'n/a'}")
        logger.info(f"  Time:       {stats['elapsed_seconds']}s")
        logger.info("=" * 60)

        return stats

    def update(self, days_back: int = 7) -> dict:
        """
        Incremental update: refresh temporal status + index new publications.

        Run on demand (CLI ``--action update``) or by the AcquisitionScheduler
        when ACQUISITION_SCHEDULER_ENABLED=true. Re-checks the in-force status of
        tracked regulations and marks any no longer in force as superseded (so
        the corpus stops serving repealed law as current), then indexes recently
        published legislation.
        """
        logger.info(f"NORMAAI UPDATE - Checking for changes (last {days_back} days)")

        start_time = time.time()

        # Tracked CELEX numbers across all frameworks
        all_celex = []
        for celex_map in CORE_FRAMEWORKS.values():
            all_celex.extend(celex_map.keys())

        # Check amendments to tracked regulations
        amendments = self.eurlex.check_for_new_amendments(all_celex)

        # Temporal freshness: mark chunks of regulations no longer in force as
        # superseded (an amendment alone does NOT supersede a still-in-force act).
        freshness = refresh_in_force_status(
            self.eurlex, self.indexer, all_celex, amendments=amendments
        )

        # Check for new legislation
        new_legislation = self.eurlex.fetch_recent_legislation(days_back=days_back)

        # Download and index any new content
        new_chunks = []
        for reg in new_legislation:
            html = self.eurlex.download_full_text_html(reg.celex)
            if html and len(html.strip()) > 500:
                chunker = EURLexHTMLChunker(celex=reg.celex, framework=reg.framework or "UNKNOWN")
                chunks = chunker.chunk_html(html)
                new_chunks.extend(chunks)

        # Enrich and index
        indexed = 0
        if new_chunks:
            enriched = []
            for chunk in new_chunks:
                ctx = self.contextual_chunker.enrich_single(
                    text=chunk.text,
                    framework=chunk.metadata.get("framework", ""),
                    article=chunk.metadata.get("article_number", ""),
                    section=chunk.metadata.get("section_title", ""),
                )
                ctx.metadata.update(chunk.metadata)
                enriched.append(ctx)

            indexed = self.indexer.index_contextual_chunks(enriched)

        elapsed = time.time() - start_time

        stats = {
            "action": "update",
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "amendments_found": len(amendments),
            "regulations_superseded": freshness["superseded_regulations"],
            "chunks_superseded": freshness["superseded_chunks"],
            "new_legislation": len(new_legislation),
            "new_chunks_indexed": indexed,
        }

        logger.info(
            f"UPDATE COMPLETE: {len(amendments)} amendments, "
            f"{freshness['superseded_chunks']} chunks superseded, "
            f"{len(new_legislation)} new, {indexed} chunks indexed ({elapsed:.1f}s)"
        )
        return stats

    def process_document(
        self,
        file_path: str,
        framework: str = "UNKNOWN",
        force_engine: str = None,
        org_id: str | None = None,
    ) -> dict:
        """
        Process an uploaded document (PDF, image, HTML) through the dual OCR pipeline.

        Uses dots.ocr for scanned/complex documents and Docling for clean digital files.
        Automatically chunks and indexes the extracted text into Qdrant.

        Args:
            file_path: Path to the document file
            framework: EU framework code (e.g., "CSRD", "GDPR")
            force_engine: Override auto-routing ("dots_ocr", "docling")
            org_id: Owning tenant. MUST be set for tenant uploads - without it the
                chunks are indexed as shared (org_id null) and become visible to
                every tenant (cross-tenant leak/poisoning, SEC-01).

        Returns:
            Processing statistics dict
        """
        logger.info(f"Processing document: {file_path} (framework={framework})")

        # Step 1: Extract text using the best available engine
        result = self.doc_processor.process(file_path, force_engine=force_engine)

        if not result["markdown"]:
            return {
                "status": "error",
                "message": f"No text extracted from {file_path}",
                "engine": result["metadata"].get("processor", "none"),
                "error": result["metadata"].get("error", "Unknown"),
            }

        engine_used = result["metadata"].get("processor", "unknown")
        logger.info(f"  Extracted {len(result['markdown'])} chars using {engine_used}")

        # Step 2: Chunk the extracted text
        import hashlib

        from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

        celex = (
            f"DOC_{hashlib.md5(file_path.encode(), usedforsecurity=False).hexdigest()[:8].upper()}"
        )
        chunker = EURLexHTMLChunker(celex=celex, framework=framework)

        # Wrap markdown in minimal HTML for the chunker
        html_wrapped = f"<html><body><p>{result['markdown']}</p></body></html>"
        chunks = chunker.chunk_html(html_wrapped)

        if not chunks:
            return {
                "status": "warning",
                "message": "Text extracted but chunking produced no results",
                "engine": engine_used,
                "chars_extracted": len(result["markdown"]),
            }

        # Step 3: Contextual enrichment
        enriched = []
        for chunk in chunks:
            ctx = self.contextual_chunker.enrich_single(
                text=chunk.text,
                framework=framework,
                article=chunk.metadata.get("article_number", ""),
                section=chunk.metadata.get("section_title", ""),
            )
            ctx.metadata.update(chunk.metadata)
            enriched.append(ctx)

        # Step 4: Index into Qdrant - scoped to the owning tenant.
        settings = get_settings()
        indexed = self.indexer.index_contextual_chunks(
            enriched, batch_size=settings.embedding_batch_size, org_id=org_id
        )

        return {
            "status": "success",
            "engine": engine_used,
            "framework": framework,
            "chars_extracted": len(result["markdown"]),
            "tables_found": len(result.get("tables", [])),
            "chunks_created": len(chunks),
            "chunks_indexed": indexed,
        }

    def stats(self) -> dict:
        """Show collection statistics (+ the corpus metadata point when present)."""
        try:
            collection_stats = self.indexer.get_collection_stats()
        except Exception:
            collection_stats = {"status": "unavailable"}
        try:
            corpus = self.indexer.get_corpus_info()
        except Exception:
            corpus = None

        return {
            "qdrant": collection_stats,
            "corpus": corpus if isinstance(corpus, dict) else None,
            "tracked_frameworks": list(CORE_FRAMEWORKS.keys()),
            "tracked_regulations": sum(len(v) for v in CORE_FRAMEWORKS.values()),
            "tracked_acts": len(TRACKED_ACTS),
        }

    def close(self):
        self.eurlex.close()


def refresh_in_force_status(eurlex, indexer, tracked_celex: list[str], amendments=None) -> dict:
    """Re-check the in-force status of tracked regulations and mark the chunks of
    any that are NO LONGER in force as superseded.

    This is the write side of temporal freshness. The retrieval filter excludes
    chunks whose ``superseded_by`` is set, but at seed time that field is only
    written from the initial is_in_force flag and never refreshed - so a norm
    repealed AFTER the seed kept being served as current law. This closes that
    gap: it re-queries EUR-Lex for each tracked CELEX and, when a regulation is
    now ``is_in_force == False``, flips ``superseded_by`` on its chunks.

    Correctness guard: an amendment alone does NOT supersede a still-in-force
    regulation (e.g. CSRD amended by Omnibus is still the law) - only a False
    in-force flag triggers a mark. When EUR-Lex names a successor act, the most
    recent amending CELEX is used as the pointer; otherwise ``"not_in_force"``.
    A None in-force flag (unknown) is treated conservatively as "leave as-is".

    Returns ``{"checked", "superseded_regulations", "superseded_chunks"}``.
    """
    if amendments is None:
        try:
            amendments = eurlex.check_for_new_amendments(tracked_celex)
        except Exception as e:
            logger.warning(f"  amendment lookup failed: {e}")
            amendments = []

    # original CELEX -> most recent amending CELEX (amendments are DESC by date)
    latest_amender: dict[str, str] = {}
    for a in amendments:
        orig = getattr(a, "original_celex", None)
        amending = getattr(a, "amending_celex", None)
        if orig and amending:
            latest_amender.setdefault(orig, amending)

    checked = 0
    superseded_regulations = 0
    superseded_chunks = 0
    for celex in tracked_celex:
        try:
            meta = eurlex.fetch_regulation_metadata(celex)
        except Exception as e:
            logger.warning(f"  in-force re-check failed for {celex}: {e}")
            continue
        checked += 1
        # Only mark when EXPLICITLY no longer in force (None = unknown = leave it).
        if meta.is_in_force is False:
            marker = latest_amender.get(celex) or "not_in_force"
            marked = indexer.mark_superseded(celex, marker)
            if marked:
                superseded_regulations += 1
                superseded_chunks += marked
                logger.info(f"  Superseded {marked} chunks: {celex} -> {marker}")

    return {
        "checked": checked,
        "superseded_regulations": superseded_regulations,
        "superseded_chunks": superseded_chunks,
    }


# ─── Scheduled jobs ──────────────────────────────────────────────────
# Run by cron on the server (the in-process scheduler stays off). Neither
# builds an IngestionPipeline: no embedding model, no document processor.


def _iso_z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def corpus_freshness(
    corpus: dict | None,
    versions_of: Callable[[str], list[Any]],
    now: datetime | None = None,
) -> dict:
    """Compare the version of each tracked EU act in the corpus with CELLAR's latest.

    ``corpus`` is the corpus metadata point the seed writes
    (``HybridIndexer.get_corpus_info()``: its ``acts`` say which text of each act
    was indexed, per language). ``versions_of(celex)`` lists the versions of an
    act, oldest first, as the document check reads them
    (``default_source().versions``): objects with ``celex``, ``as_of`` and
    ``initial``.

    An act is outdated when CELLAR lists a consolidated text newer than the one
    indexed in some language. A corpus that holds the act as adopted is not
    behind a consolidated text that is only CELLAR's snapshot of the act as
    published (``initial``): the words are the same. Acts registered as
    amending are skipped, they have no consolidated text of their own.

    Returns ``{"status", "checked_at", "outdated", "missing", "unknown", ...}``:
    ``status`` is ``ok``, ``outdated`` or ``unknown`` (no corpus metadata, or no
    act could be compared); ``missing`` are tracked acts the corpus does not
    hold, ``unknown`` those CELLAR could not be asked about.
    """
    now = now or datetime.now(UTC)
    acts = corpus.get("acts") if isinstance(corpus, dict) else None
    if not isinstance(acts, list) or not acts:
        return {
            "status": "unknown",
            "checked_at": None,
            "outdated": [],
            "missing": [],
            "unknown": [],
            "reason": "corpus metadata not available",
            "attempted_at": _iso_z(now),
        }

    indexed: dict[str, dict[str, str]] = {}  # act -> {language: id of the text indexed}
    for entry in acts:
        if not isinstance(entry, dict):
            continue
        celex = celex_utils.base_celex(str(entry.get("celex") or ""))
        text_id = str(entry.get("source_celex") or entry.get("celex") or "")
        if celex and text_id:
            indexed.setdefault(celex, {})[str(entry.get("lang") or "")] = text_id

    def age(text_id: str) -> str:
        """Sorts the act as adopted before every consolidated text."""
        return celex_utils.consolidated_as_of(text_id) or ""

    outdated: list[dict] = []
    missing: list[str] = []
    unknown: list[str] = []
    compared = 0
    for act in TRACKED_ACTS:
        if not act.consolidated:
            continue
        in_corpus = indexed.get(act.celex)
        if not in_corpus:
            missing.append(act.celex)
            continue
        try:
            consolidated = [v for v in versions_of(act.celex) if getattr(v, "as_of", None)]
        except Exception as e:  # noqa: BLE001 - CELLAR not reachable for this act
            logger.warning(f"  freshness: versions of {act.celex} not available: {e}")
            unknown.append(act.celex)
            continue
        compared += 1
        if not consolidated:
            continue
        real = [v for v in consolidated if not getattr(v, "initial", False)]
        behind: dict[str, str] = {}
        for lang, text_id in in_corpus.items():
            if celex_utils.is_consolidated_celex(text_id):
                if age(text_id) < str(consolidated[-1].as_of):
                    behind[lang] = text_id
            elif real:
                behind[lang] = text_id
        if behind:
            outdated.append(
                {
                    "celex": act.celex,
                    "indexed": min(behind.values(), key=age),
                    "latest": consolidated[-1].celex,
                    "langs": sorted(lang for lang in behind if lang),
                }
            )

    if outdated:
        status = "outdated"
    elif compared and not unknown:
        status = "ok"
    else:
        status = "unknown"
    return {
        "status": status,
        "checked_at": _iso_z(now) if compared else None,
        "outdated": outdated,
        "missing": missing,
        "unknown": unknown,
        "acts": compared,
        "corpus_as_of": corpus.get("corpus_as_of") if isinstance(corpus, dict) else None,
        "attempted_at": _iso_z(now),
    }


async def store_freshness(sessions: Any, outcome: dict, now: datetime | None = None) -> None:
    """Keep the outcome in ``system_state``, where GET /api/v1/stats reads it."""
    from src.db.models import CORPUS_FRESHNESS_KEY, SystemState

    now = now or datetime.now(UTC)
    async with sessions() as session:
        row = await session.get(SystemState, CORPUS_FRESHNESS_KEY)
        if row is None:
            session.add(SystemState(key=CORPUS_FRESHNESS_KEY, value=outcome, updated_at=now))
        else:
            row.value = outcome
            row.updated_at = now
        await session.commit()


def run_check_freshness() -> dict:
    """``--action check-freshness``: compare, store, return the outcome.

    Without Qdrant (or on a corpus seeded before the metadata point existed)
    the outcome is ``unknown`` and is stored as such.
    """
    import asyncio

    from src.db.engine import db_manager
    from src.document_check.sources import default_source

    try:
        corpus = HybridIndexer(**indexer_kwargs_from_settings(get_settings())).get_corpus_info()
    except Exception as e:  # noqa: BLE001 - Qdrant not reachable
        logger.warning(f"freshness: corpus metadata not readable: {e}")
        corpus = None

    source: Any = None

    def versions_of(celex: str) -> list[Any]:
        # One source for the run: it keeps the lists on disk for a day, the
        # same lists the document checks read.
        nonlocal source
        if source is None:
            source = default_source()
        return list(source.versions(celex))

    outcome = corpus_freshness(corpus if isinstance(corpus, dict) else None, versions_of)

    async def _store() -> None:
        db_manager.init()
        try:
            await store_freshness(db_manager.session, outcome)
        finally:
            await db_manager.close()

    asyncio.run(_store())
    logger.info(
        f"FRESHNESS: {outcome['status']}, {len(outcome['outdated'])} outdated, "
        f"{len(outcome['missing'])} missing, {len(outcome['unknown'])} not checked"
    )
    return outcome


def run_recheck_documents() -> dict:
    """``--action recheck-documents``: the surveillance of the watched documents.

    Re-checks the provisions every watched document cites, writes the alerts
    and sends the digest emails (src/document_check/surveillance.py). Safe to
    run again: a change is announced once.
    """
    import asyncio

    from src.db.engine import db_manager
    from src.document_check import surveillance
    from src.document_check.sources import default_source

    async def _run() -> dict:
        db_manager.init()
        try:
            report = await surveillance.run(db_manager.session, default_source())
            return report.as_dict()
        finally:
            await db_manager.close()

    result = asyncio.run(_run())
    logger.info(
        f"RECHECK: {result['checks']} watched documents, {result['provisions']} provisions, "
        f"{result['checks_changed']} documents to review, {result['emails_sent']} emails"
    )
    return result


SCHEDULED_ACTIONS: dict[str, Callable[[], dict]] = {
    "recheck-documents": run_recheck_documents,
    "check-freshness": run_check_freshness,
}


def run_scheduled(action: str) -> dict:
    """Run a cron job; when it raises, tell the operator, then exit with 1.

    Cron only keeps the output in /var/log/normaai-jobs.log, which nobody reads
    unless something sends them there. With SENTRY_DSN set, every ERROR line of
    the job becomes a Sentry event, the traceback of a failure included; with
    OPS_ALERT_EMAIL (and RESEND_API_KEY) the failure is also emailed
    (src/ops_alerts.py).
    """
    from src.observability import setup_sentry
    from src.ops_alerts import failure_summary, notify_failure

    settings = get_settings()
    sentry_on = setup_sentry(settings)
    try:
        return SCHEDULED_ACTIONS[action]()
    except Exception as e:
        logger.exception(f"{action} failed")
        notify_failure(
            f"pipeline {action}",
            failure_summary(e),
            "See /var/log/normaai-jobs.log on the server for the traceback.",
            sentry=not sentry_on,
            settings=settings,
        )
        raise SystemExit(1) from e


def main():
    # CLI entry point only: when imported by the API (data router, scheduler)
    # the application's own logging setup applies - a module-level basicConfig
    # would install a second root handler and duplicate every line.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="NormaAI Ingestion Pipeline")
    parser.add_argument(
        "--action",
        choices=["seed", "update", "stats", *SCHEDULED_ACTIONS],
        required=True,
        help="Pipeline action to run",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate Qdrant collection (seed only)",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Days to look back for updates (update only)",
    )
    parser.add_argument(
        "--acts",
        action="append",
        default=[],
        metavar="CELEX_OR_FRAMEWORK",
        help=(
            "Restrict the seed to these acts: CELEX ids and/or framework names, "
            "comma-separated or repeated (e.g. --acts AI_ACT --acts 32022L2464). "
            "Default: every tracked act (seed only)"
        ),
    )
    parser.add_argument(
        "--lang",
        action="append",
        default=[],
        metavar="CODE",
        help=(
            "Language(s) to download, comma-separated or repeated (e.g. --lang EN --lang IT). "
            "Default: CORPUS_LANGUAGES (seed only)"
        ),
    )

    args = parser.parse_args()

    def _split(values: list[str]) -> list[str]:
        return [item.strip() for value in values for item in value.split(",") if item.strip()]

    if args.action in SCHEDULED_ACTIONS:
        # Before IngestionPipeline(): these jobs need no embedding model.
        result = run_scheduled(args.action)
        print("\n" + json.dumps(result, indent=2, ensure_ascii=False))
        return

    pipeline = IngestionPipeline()

    try:
        if args.action == "seed":
            result = pipeline.seed(
                recreate_collection=args.recreate,
                acts=_split(args.acts) or None,
                languages=_split(args.lang) or None,
            )
        elif args.action == "update":
            result = pipeline.update(days_back=args.days_back)
        elif args.action == "stats":
            result = pipeline.stats()

        print("\n" + json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
