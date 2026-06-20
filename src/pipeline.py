"""
NormaAI Ingestion Pipeline - End-to-end: EUR-Lex → Parse → Chunk → Context → Index.

This is the main orchestration script that:
1. Crawls EUR-Lex for all core framework regulations
2. Downloads full text HTML for each regulation
3. Chunks HTML into semantically meaningful pieces
4. Enriches chunks with contextual prefixes (improves retrieval ~10-15%)
5. Indexes chunks into Qdrant with hybrid search (dense + sparse)

Usage:
    python -m src.pipeline --action seed     # Initial seed: crawl + index all core frameworks
    python -m src.pipeline --action update   # Check for amendments and index new content
    python -m src.pipeline --action stats    # Show collection statistics
"""

import argparse
import json
import logging
import time
from datetime import datetime

from src.config import get_settings
from src.crawler.eurlex.client import CORE_FRAMEWORKS, EurLexClient
from src.nlp.chunking.contextual_chunker import ContextualChunker
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker
from src.nlp.embedding.indexer import HybridIndexer
from src.nlp.processing.dots_ocr_processor import UnifiedDocumentProcessor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
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
        self.indexer = HybridIndexer(
            qdrant_host=settings.qdrant_host,
            qdrant_port=settings.qdrant_port,
            embedding_model=settings.embedding_model,
            embedding_dim=settings.embedding_dimension,
        )
        self.contextual_chunker = ContextualChunker()
        self.doc_processor = UnifiedDocumentProcessor()

    def seed(self, recreate_collection: bool = False) -> dict:
        """
        Initial seed: download and index all core EU regulatory frameworks.
        This is the Day 1 operation that builds the foundational knowledge base.
        Supports both EUR-Lex (EU regulations) and Normattiva (Italian implementations).
        """
        logger.info("=" * 60)
        logger.info("NORMAAI SEED PIPELINE - Building regulatory knowledge base")
        logger.info("=" * 60)

        start_time = time.time()

        # Step 1: Setup Qdrant collection
        logger.info("[1/6] Setting up Qdrant collection...")
        self.indexer.setup_collection(recreate=recreate_collection)

        settings = get_settings()
        data_source = settings.data_source  # "eurlex", "normattiva", or "both"

        # Step 2a: Crawl EUR-Lex (if enabled)
        all_chunks = []
        download_stats_eurlex = {"success": 0, "failed": 0, "total_chunks": 0}
        download_stats_normattiva = {"success": 0, "failed": 0, "total_chunks": 0}

        if data_source in ("eurlex", "both"):
            logger.info("[2/6] Crawling EUR-Lex for core framework metadata...")
            regulations = self.eurlex.crawl_all_core_frameworks()
            logger.info(
                f"  Found {len(regulations)} regulations across {len(CORE_FRAMEWORKS)} frameworks"
            )

            # Step 3a: Download and chunk EUR-Lex content
            logger.info("[3/6] Downloading EUR-Lex full text and chunking...")

            for reg in regulations:
                logger.info(f"  Processing {reg.celex} ({reg.framework}): {reg.title[:60]}...")

                # Download HTML
                html = self.eurlex.download_full_text_html(reg.celex)
                if not html:
                    logger.warning(f"  FAILED to download {reg.celex}")
                    download_stats_eurlex["failed"] += 1
                    continue

                # Validate HTML has content
                if len(html.strip()) < 500:
                    logger.warning(
                        f"  SKIPPED {reg.celex}: HTML too short ({len(html)} chars), likely error page"
                    )
                    download_stats_eurlex["failed"] += 1
                    continue

                download_stats_eurlex["success"] += 1

                # Chunk
                chunker = EURLexHTMLChunker(celex=reg.celex, framework=reg.framework)
                chunks = chunker.chunk_html(html)
                # Populate temporal metadata from the real EUR-Lex record so the
                # "exclude superseded" filter is actually effective (it was inert
                # because nothing ever set these fields). effective_date enables
                # date reasoning; a not-in-force regulation is marked superseded
                # so it is NOT served as current law.
                for c in chunks:
                    if getattr(reg, "date_document", None):
                        c.metadata["effective_date"] = reg.date_document
                    if getattr(reg, "is_in_force", None) is False:
                        c.metadata["superseded_by"] = "not_in_force"
                all_chunks.extend(chunks)
                download_stats_eurlex["total_chunks"] += len(chunks)

                logger.info(f"  OK {reg.celex}: {len(chunks)} chunks ({len(html):,} chars HTML)")

        # Step 2b/3b: Seed Normattiva (if enabled)
        if data_source in ("normattiva", "both"):
            logger.info("[2/6] Initializing Normattiva Italian implementations...")
            normattiva_chunks = self.seed_normattiva(list(CORE_FRAMEWORKS.keys()))
            all_chunks.extend(normattiva_chunks)
            download_stats_normattiva["success"] = len(normattiva_chunks) // max(
                1, len(normattiva_chunks) // 5
            )
            download_stats_normattiva["total_chunks"] = len(normattiva_chunks)

        # Step 4: Enrich with contextual prefixes
        logger.info(f"[4/6] Enriching {len(all_chunks)} chunks with contextual prefixes...")
        enriched_chunks = []
        for chunk in all_chunks:
            framework = chunk.metadata.get("framework", "")
            ctx = self.contextual_chunker.enrich_single(
                text=chunk.text,
                framework=framework,
                article=chunk.metadata.get("article_number", ""),
                section=chunk.metadata.get("section_title", ""),
            )
            # Merge original metadata
            ctx.metadata.update(chunk.metadata)
            enriched_chunks.append(ctx)

        logger.info(f"  Enriched {len(enriched_chunks)} chunks with regulatory context")

        # Step 5: Index all chunks
        logger.info(f"[5/6] Indexing {len(enriched_chunks)} chunks into Qdrant...")
        if enriched_chunks:
            indexed = self.indexer.index_contextual_chunks(
                enriched_chunks,
                batch_size=settings.embedding_batch_size,
            )
        else:
            indexed = 0

        elapsed = time.time() - start_time

        # Summary
        total_downloads = download_stats_eurlex["success"] + download_stats_normattiva["success"]
        total_failed = download_stats_eurlex["failed"] + download_stats_normattiva["failed"]
        total_chunks_created = (
            download_stats_eurlex["total_chunks"] + download_stats_normattiva["total_chunks"]
        )

        stats = {
            "action": "seed",
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "data_source": data_source,
            "eurlex": download_stats_eurlex,
            "normattiva": download_stats_normattiva,
            "total_downloads_success": total_downloads,
            "total_downloads_failed": total_failed,
            "total_chunks": total_chunks_created,
            "chunks_indexed": indexed,
            "frameworks": list(CORE_FRAMEWORKS.keys()),
            "contextual_enrichment": True,
        }

        logger.info("=" * 60)
        logger.info("SEED COMPLETE")
        logger.info(f"  Data source: {data_source}")
        logger.info(
            f"  EUR-Lex:    {download_stats_eurlex['success']} OK, {download_stats_eurlex['failed']} failed"
        )
        logger.info(
            f"  Normattiva: {download_stats_normattiva['success']} OK, {download_stats_normattiva['failed']} failed"
        )
        logger.info(f"  Chunks:     {stats['chunks_indexed']} indexed (with contextual enrichment)")
        logger.info(f"  Time:       {stats['elapsed_seconds']}s")
        logger.info("=" * 60)

        return stats

    def seed_normattiva(self, frameworks: list[str]) -> list:
        """
        Seed Normattiva Italian implementations for the given frameworks.

        This searches for Italian implementing legislation and regulations
        related to each EU framework, downloads them, and returns chunks
        ready for indexing.

        Args:
            frameworks: List of EU framework codes (e.g., ["CSRD", "GDPR", "AI_ACT"])

        Returns:
            List of Chunk objects enriched with metadata (source="normattiva")
        """
        import asyncio

        from src.crawler.normattiva.client import NormattivaOpenDataClient

        logger.info(f"Seeding Normattiva implementations for {len(frameworks)} frameworks...")

        # Map EU framework codes to Italian search queries
        FRAMEWORK_SEARCH_QUERIES: dict[str, list[str]] = {  # noqa: N806 - function-scoped constant
            "CSRD": [
                "rendicontazione societaria di sostenibilità",
                "decreto legislativo recepimento direttiva 2022/2464",
            ],
            "CSDDD": [
                "dovuta diligenza imprese sostenibilità",
                "due diligence catena del valore",
            ],
            "AI_ACT": [
                "regolamento intelligenza artificiale",
                "decreto legislativo intelligenza artificiale 2024",
            ],
            "DORA": [
                "resilienza operativa digitale settore finanziario",
                "decreto legislativo recepimento DORA",
            ],
            "NIS2": [
                "sicurezza delle reti e dei sistemi informativi",
                "decreto legislativo recepimento NIS2",
                "decreto legislativo 138 2024",
            ],
            "TAXONOMY": [
                "finanza sostenibile tassonomia",
                "regolamento delegato tassonomia UE",
            ],
            "GDPR": [
                "codice protezione dati personali",
                "decreto legislativo 196 2003 privacy",
                "decreto legislativo 101 2018",
            ],
            # CRA is an EU Regulation (no transposition); national measures
            # are adaptation decrees - search for those.
            "CRA": [
                "regolamento ciberresilienza prodotti elementi digitali",
                "adeguamento regolamento 2024/2847",
            ],
        }

        all_chunks = []

        async def _seed_async():
            async with NormattivaOpenDataClient(
                rate_limit_delay=1.5,
                timeout=30.0,
                max_retries=3,
            ) as client:
                for fw in frameworks:
                    queries = FRAMEWORK_SEARCH_QUERIES.get(fw, [])
                    if not queries:
                        logger.warning(f"  No Normattiva search queries for framework: {fw}")
                        continue

                    logger.info(
                        f"  Searching Normattiva for {fw} implementations ({len(queries)} queries)..."
                    )
                    seen_urns = set()

                    for query in queries:
                        try:
                            search_result = await client.search(query, limit=10)
                            logger.info(
                                f"    Query '{query[:40]}...' → {search_result.total} results"
                            )

                            for act_summary in search_result.results:
                                # Skip duplicates
                                if act_summary.urn in seen_urns:
                                    continue
                                seen_urns.add(act_summary.urn)

                                # Only process acts that are currently in force
                                if not act_summary.in_vigore:
                                    logger.debug(f"    Skipping {act_summary.urn} (not in force)")
                                    continue

                                # Download full text
                                try:
                                    normative_text = await client.get_atto(
                                        tipo=act_summary.tipo,
                                        anno=act_summary.anno,
                                        numero=act_summary.numero,
                                    )
                                except Exception as dl_err:
                                    logger.warning(
                                        f"    Failed to download {act_summary.urn}: {dl_err}"
                                    )
                                    continue

                                if not normative_text:
                                    continue

                                # Use HTML if available, otherwise plain text
                                text_content = (
                                    normative_text.testo_html or normative_text.testo_plain
                                )
                                if not text_content or len(text_content.strip()) < 200:
                                    logger.debug(f"    Skipping {act_summary.urn}: text too short")
                                    continue

                                # Chunk the content
                                chunker = EURLexHTMLChunker(
                                    celex=act_summary.urn,  # Use URN as identifier
                                    framework=fw,
                                )
                                try:
                                    chunks = chunker.chunk_html(text_content)
                                except Exception:
                                    # If HTML chunking fails, create a single chunk from plain text
                                    from src.nlp.chunking.legal_chunker import Chunk

                                    plain = normative_text.testo_plain or text_content
                                    chunks = [
                                        Chunk(
                                            text=plain[:4000],
                                            metadata={
                                                "framework": fw,
                                                "source": "normattiva",
                                                "urn": act_summary.urn,
                                            },
                                        )
                                    ]

                                # Enrich metadata for each chunk
                                for chunk in chunks:
                                    chunk.metadata["source"] = "normattiva"
                                    chunk.metadata["urn"] = act_summary.urn
                                    chunk.metadata["tipo_atto"] = act_summary.tipo
                                    chunk.metadata["anno"] = act_summary.anno
                                    chunk.metadata["numero"] = act_summary.numero
                                    chunk.metadata["titolo"] = act_summary.titolo
                                    chunk.metadata["in_vigore"] = act_summary.in_vigore
                                    chunk.metadata["url"] = normative_text.url or ""

                                all_chunks.extend(chunks)
                                logger.info(
                                    f"    OK {act_summary.urn}: {len(chunks)} chunks "
                                    f"({act_summary.titolo[:50]}...)"
                                )

                        except Exception as q_err:
                            logger.warning(
                                f"    Search query failed for '{query[:40]}...': {q_err}"
                            )
                            continue

        try:
            asyncio.run(_seed_async())
            logger.info(
                f"  Normattiva seed complete: {len(all_chunks)} chunks from {len(frameworks)} frameworks"
            )
        except Exception as e:
            logger.error(f"Error seeding Normattiva: {e}")

        return all_chunks

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
        """Show collection statistics."""
        try:
            collection_stats = self.indexer.get_collection_stats()
        except Exception:
            collection_stats = {"status": "unavailable"}

        return {
            "qdrant": collection_stats,
            "tracked_frameworks": list(CORE_FRAMEWORKS.keys()),
            "tracked_regulations": sum(len(v) for v in CORE_FRAMEWORKS.values()),
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


def main():
    parser = argparse.ArgumentParser(description="NormaAI Ingestion Pipeline")
    parser.add_argument(
        "--action",
        choices=["seed", "update", "stats"],
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

    args = parser.parse_args()

    pipeline = IngestionPipeline()

    try:
        if args.action == "seed":
            result = pipeline.seed(recreate_collection=args.recreate)
        elif args.action == "update":
            result = pipeline.update(days_back=args.days_back)
        elif args.action == "stats":
            result = pipeline.stats()

        print("\n" + json.dumps(result, indent=2))
    finally:
        pipeline.close()


if __name__ == "__main__":
    main()
