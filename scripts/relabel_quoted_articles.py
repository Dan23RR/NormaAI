#!/usr/bin/env python3
"""Relabel the chunks of amending acts that quote articles of the act they amend.

Before the fix in src/nlp/chunking/legal_chunker.py, a heading quoted by an
amending article ("«Article 2a", in Article 25 of Regulation (EU) 2020/852)
became a unit labelled "Art. ?", an unquoted heading inside a quoted chapter
("Article 29e" under «CHAPTER 6c» in Directive (EU) 2026/470) became an article
of the amending act, and the quoted chapter became the section of every later
article. This script gives the chunks already in Qdrant the labels a new seed
would give them, without downloading the acts again:

- a quoted unit takes the label, title, section and hierarchy of the amending
  act's own article, plus ``quoted_article`` ("Art. 2a") and ``amended_celex``;
- an own article keeps its label and gets back the act's own section.

The chunk text does not change, but the point id hashes the article label and
the dense vector embeds a "[framework | article | section]" header, so a
changed chunk is written as a new point (same text, payload and BM25 vector,
dense vector of the new header with the collection's model) and its old point
is deleted. Only shared-corpus points (no org_id) are read.

    python scripts/relabel_quoted_articles.py            # dry run: print the changes
    python scripts/relabel_quoted_articles.py --apply    # write them

The collection and the dense model come from QDRANT_COLLECTION, EMBEDDING_MODEL
and EMBEDDING_DIMENSION (one run per collection); --apply refuses a collection
whose corpus metadata names another model. Rerunning finds nothing to change.
Exit code 0; 1 when Qdrant fails; 2 when --apply is refused.
"""

import argparse
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client.models import PointIdsList, PointStruct, SparseVector  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.nlp.chunking.legal_chunker import (  # noqa: E402
    amended_act_celex,
    continues_article_numbering,
    quoted_article_number,
)
from src.nlp.embedding.indexer import (  # noqa: E402
    CORPUS_META_ID,
    DENSE_VECTOR,
    SPARSE_VECTOR,
    HybridIndexer,
    indexer_kwargs_from_settings,
    make_point_id,
    stored_passage_text,
)

LABEL_KEYS = (
    "article",
    "article_number",
    "title",
    "section_title",
    "hierarchy",
    "quoted_article",
    "amended_celex",
)
_OPENING_QUOTES = "‘“'\"«"


def _quoted(text: str | None) -> bool:
    return bool(text) and text[0] in _OPENING_QUOTES


def relabel_act(payloads: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """New labels for the chunks of one act and language, given in chunk order.

    Returns, for each payload, the label fields (LABEL_KEYS) the fixed chunker
    gives it, or None when they do not change. Follows the chunker's rules on
    the stored chunks: a unit starts at a part "1" (or a chunk without parts), a
    quoted heading is the first line of its text, a quoted chapter shows as a
    section that starts with a quote, and after a quoted article or chapter a
    heading that does not continue the act's own numbering is quoted too.
    """
    out: list[dict[str, Any] | None] = []
    own: dict[str, Any] | None = None  # labels of the act's own current article
    own_section = ""  # the act's own section (the chunker's section_heading)
    previous_section: str | None = None
    in_quotation = False
    unit: dict[str, Any] | None = None
    for p in payloads:
        if p.get("chunk_type") != "article":
            out.append(None)
            continue
        if p.get("part") in (None, "1", 1):
            section = p.get("section_title") or ""
            if not _quoted(section):
                own_section = section
            elif section != previous_section:
                in_quotation = True
            previous_section = section
            article = p.get("article") or ""
            stored_number = article[5:] if article.startswith("Art. ") else ""
            number = None
            if article == "Art. ?":
                first_line = (p.get("text") or "").split("\n", 1)[0]
                number = quoted_article_number(first_line)
            if number is None and in_quotation and own is not None and not p.get("quoted_article"):
                if not continues_article_numbering(stored_number, own["article"]):
                    number = stored_number
            if number is not None and own is not None:
                unit = {
                    **own,
                    "quoted_article": f"Art. {number}",
                    "amended_celex": amended_act_celex(own["title"]),
                }
                in_quotation = True
            else:
                unit = {
                    "article": article,
                    "article_number": p.get("article_number") or article,
                    "title": p.get("title"),
                    "section_title": own_section,
                    "hierarchy": (
                        p.get("hierarchy")
                        if not _quoted(section)
                        else (f"{own_section} > {article}" if own_section else article)
                    ),
                    "quoted_article": p.get("quoted_article"),
                    "amended_celex": p.get("amended_celex"),
                }
                if unit["quoted_article"] is None:
                    own = {**unit}
                    in_quotation = False
                else:  # relabelled by an earlier run: still a quotation
                    in_quotation = True
        new = {key: (unit or {}).get(key) for key in LABEL_KEYS}
        old = {key: p.get(key) for key in LABEL_KEYS}
        out.append(new if new != old else None)
    return out


# ─── Qdrant ──────────────────────────────────────────────────────


def _sparse(record: Any) -> SparseVector:
    vectors = record.vector if isinstance(record.vector, dict) else {}
    return vectors.get(SPARSE_VECTOR) or SparseVector(indices=[], values=[])


def plan(client: Any, collection: str) -> list[tuple[Any, dict[str, Any]]]:
    """(record, new payload) for every shared-corpus chunk whose labels change."""
    acts: dict[tuple[str, str], list[Any]] = defaultdict(list)
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=collection,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=[SPARSE_VECTOR],
        )
        for r in records:
            payload = r.payload or {}
            if str(r.id) == CORPUS_META_ID or payload.get("org_id") is not None:
                continue
            acts[(payload.get("celex") or "", payload.get("lang") or "")].append(r)
        if offset is None:
            break
    changes = []
    for key in sorted(acts):
        records = sorted(acts[key], key=lambda r: (r.payload or {}).get("chunk_index") or 0)
        for record, labels in zip(
            records, relabel_act([r.payload or {} for r in records]), strict=True
        ):
            if labels is not None:
                changes.append((record, {**(record.payload or {}), **labels}))
    return changes


def describe(changes: list[tuple[Any, dict[str, Any]]]) -> list[str]:
    lines = []
    for record, new in changes:
        old = record.payload or {}
        what = [f"{old.get('article')} -> {new['article']}"]
        if new.get("quoted_article"):
            what.append(f"quotes {new['quoted_article']} of {new.get('amended_celex')}")
        if old.get("section_title") != new["section_title"]:
            what.append(f"section {old.get('section_title')!r} -> {new['section_title']!r}")
        lines.append(
            f"  {new.get('celex')} {new.get('lang')} #{new.get('chunk_index')}: " + "; ".join(what)
        )
    return lines


def apply(
    indexer: HybridIndexer, changes: list[tuple[Any, dict[str, Any]]], batch: int = 32
) -> int:
    """Write the relabelled chunks as new points, then delete their old points."""
    client = indexer.client
    new_ids: set[str] = set()
    now = datetime.now(UTC).isoformat()
    for start in range(0, len(changes), batch):
        part = changes[start : start + batch]
        payloads = [{**new, "indexed_at": now} for _, new in part]
        dense = indexer.embed_passages([stored_passage_text(p) for p in payloads])
        points = []
        for (record, _), payload, vector in zip(part, payloads, dense, strict=True):
            point_id = make_point_id(
                payload.get("celex") or "",
                payload.get("lang") or "",
                payload["article"],
                payload.get("chunk_index") or 0,
                payload.get("text") or "",
            )
            new_ids.add(point_id)
            points.append(
                PointStruct(
                    id=point_id,
                    vector={DENSE_VECTOR: list(vector), SPARSE_VECTOR: _sparse(record)},
                    payload=payload,
                )
            )
        client.upsert(collection_name=indexer.COLLECTION_NAME, points=points)
    stale = [str(r.id) for r, _ in changes if str(r.id) not in new_ids]
    if stale:
        client.delete(
            collection_name=indexer.COLLECTION_NAME,
            points_selector=PointIdsList(points=stale),
        )
    return len(changes)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = parser.parse_args(argv)

    settings = get_settings()
    indexer = HybridIndexer(**indexer_kwargs_from_settings(settings), qdrant_timeout=300)
    collection = indexer.COLLECTION_NAME
    try:
        changes = plan(indexer.client, collection)
    except Exception as e:  # noqa: BLE001 - report any Qdrant failure as exit 1
        print(f"reading {collection} failed: {e}")
        return 1
    print("\n".join(describe(changes)))
    acts = sorted({(new.get("celex"), new.get("lang")) for _, new in changes})
    print(f"{collection}: {len(changes)} chunks to relabel in {len(acts)} act versions {acts}")
    if not args.apply or not changes:
        return 0

    meta = indexer.client.retrieve(collection_name=collection, ids=[CORPUS_META_ID])
    corpus_model = ((meta[0].payload or {}) if meta else {}).get("embedding_model")
    if corpus_model != settings.embedding_model:
        print(
            f"refused: {collection} was embedded with {corpus_model!r}, "
            f"EMBEDDING_MODEL is {settings.embedding_model!r}"
        )
        return 2
    try:
        written = apply(indexer, changes)
    except Exception as e:  # noqa: BLE001
        print(f"writing {collection} failed: {e} (rerun to finish: the run is idempotent)")
        return 1
    print(f"{collection}: {written} chunks relabelled with {settings.embedding_model}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
