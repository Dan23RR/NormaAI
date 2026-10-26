#!/usr/bin/env python3
"""Re-embed a Qdrant collection with another dense model, for an A/B test.

Copies every point of SOURCE into TARGET with the same id, payload and sparse
"bm25" vector; only the "dense" vector is recomputed, with MODEL. Each point is
embedded on exactly the text the indexer embeds for a passage (the context
header + chunk text that src.nlp.embedding.indexer.stored_passage_text rebuilds
from the payload) behind the model's passage prefix ("passage: " for e5).
TARGET is created by HybridIndexer.setup_collection, so it gets the vector
names, the sparse IDF modifier and the payload indexes of a seeded collection.
The corpus metadata point is rewritten for TARGET (MODEL, a placeholder vector
of the new size, the origin under "reembedded_from"). SOURCE is only read.

    python scripts/reembed_collection.py --source eu_regulations --target eu_regulations_e5 --model intfloat/multilingual-e5-large --dim 1024
    python scripts/reembed_collection.py ... --dry-run    # read SOURCE, print the plan

Run from the repository root; Qdrant comes from QDRANT_HOST / QDRANT_PORT (or
--host / --port). --dry-run reads SOURCE and checks MODEL against FastEmbed's
model list, then prints the plan: it loads no model and writes nothing. A real
run downloads MODEL on first use (FastEmbed cache, ~2.2 GB for
multilingual-e5-large) and embeds every chunk on CPU: expect a long run.
Rerunning into the same TARGET overwrites the same ids; --recreate-target
empties it first. Exit code 0; 1 when Qdrant fails or the copy is incomplete;
2 when the plan is refused (SOURCE missing or without the indexer's layout,
MODEL not listed or of another size, TARGET existing with another layout).

Afterwards evaluate TARGET (python -m tests.validation.retrieval_eval) or serve
it with QDRANT_COLLECTION=<target> EMBEDDING_MODEL=<model> EMBEDDING_DIMENSION=<dim>.
"""

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client.models import PointStruct, SparseVector  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.nlp.embedding.indexer import (  # noqa: E402
    CORPUS_META_ID,
    CORPUS_META_KIND,
    DENSE_VECTOR,
    PAYLOAD_INDEX_FIELDS,
    SPARSE_VECTOR,
    HybridIndexer,
    stored_passage_text,
)

PROGRESS_EVERY = 50  # batches between two progress lines


# ─── Reading SOURCE (and TARGET) ─────────────────────────────────


def _modifier(sparse_params: Any) -> str | None:
    modifier = getattr(sparse_params, "modifier", None)
    return None if modifier is None else str(getattr(modifier, "value", modifier)).lower()


def collection_layout(client: Any, name: str) -> dict[str, Any] | None:
    """Point count and named vectors of a collection; None when it does not exist."""
    if not client.collection_exists(name):
        return None
    params = client.get_collection(name).config.params
    dense = params.vectors if isinstance(params.vectors, dict) else {"": params.vectors}
    return {
        "points": client.count(collection_name=name, exact=True).count,
        "dense": {vector: cfg.size for vector, cfg in dense.items()},
        "sparse": {vector: _modifier(cfg) for vector, cfg in (params.sparse_vectors or {}).items()},
    }


def source_problems(layout: dict[str, Any]) -> list[str]:
    """Why SOURCE cannot be copied as is into a collection the indexer creates."""
    problems = []
    if set(layout["dense"]) != {DENSE_VECTOR}:
        problems.append(
            f"SOURCE dense vectors {sorted(layout['dense'])}, expected '{DENSE_VECTOR}'"
        )
    if set(layout["sparse"]) != {SPARSE_VECTOR}:
        problems.append(
            f"SOURCE sparse vectors {sorted(layout['sparse'])}, expected '{SPARSE_VECTOR}'"
        )
    elif layout["sparse"][SPARSE_VECTOR] != "idf":
        problems.append(
            f"SOURCE '{SPARSE_VECTOR}' has no IDF modifier but TARGET would, so BM25 would "
            "change too: reseed SOURCE first (python -m src.pipeline --action seed --recreate)"
        )
    return problems


def target_problems(layout: dict[str, Any] | None, dim: int, recreate: bool) -> list[str]:
    """Why an existing TARGET cannot receive the copy (it is fine when absent or recreated)."""
    if layout is None or recreate:
        return []
    if layout["dense"] == {DENSE_VECTOR: dim} and layout["sparse"] == {SPARSE_VECTOR: "idf"}:
        return []
    return [
        f"TARGET exists with dense {layout['dense']} and sparse {layout['sparse']}: "
        "use --recreate-target or another --target"
    ]


def fastembed_dim(model: str) -> int | None:
    """Vector size FastEmbed lists for ``model`` (no download); None when not listed."""
    from fastembed import TextEmbedding

    for entry in TextEmbedding.list_supported_models():
        if str(entry.get("model", "")).lower() == model.lower():
            return int(entry["dim"])
    return None


# ─── Copying ─────────────────────────────────────────────────────


def _sparse(record: Any) -> SparseVector:
    vectors = record.vector if isinstance(record.vector, dict) else {}
    # Qdrant may leave out an empty sparse vector (a chunk with no words).
    return vectors.get(SPARSE_VECTOR) or SparseVector(indices=[], values=[])


def copy_points(
    source: str,
    target: HybridIndexer,
    batch_size: int,
    total: int,
    log: Callable[[str], None] = print,
) -> int:
    """Stream SOURCE into TARGET, re-embedding the dense vectors; returns the points copied.

    SOURCE is only scrolled. Its corpus metadata point is skipped (see
    rewrite_corpus_meta); every other point keeps its id, payload and sparse vector.
    """
    client = target.client
    copied, batches, offset = 0, 0, None
    started = time.monotonic()
    while True:
        records, offset = client.scroll(
            collection_name=source,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=[SPARSE_VECTOR],  # the dense vector is recomputed, not read
        )
        chunks = [
            r
            for r in records
            if str(r.id) != CORPUS_META_ID and (r.payload or {}).get("kind") != CORPUS_META_KIND
        ]
        if chunks:
            dense = target.embed_passages([stored_passage_text(r.payload or {}) for r in chunks])
            client.upsert(
                collection_name=target.COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=r.id,
                        vector={DENSE_VECTOR: vector, SPARSE_VECTOR: _sparse(r)},
                        payload=r.payload or {},
                    )
                    for r, vector in zip(chunks, dense, strict=True)
                ],
            )
            copied += len(chunks)
        batches += 1
        if offset is None or batches % PROGRESS_EVERY == 0:
            elapsed = time.monotonic() - started
            rate = copied / elapsed if elapsed > 0 else 0.0
            left = f", ~{(total - copied) / rate / 60:.0f} min left" if rate and offset else ""
            log(f"  {copied}/{total} points re-embedded ({rate:.1f}/s{left})")
        if offset is None:
            return copied


def rewrite_corpus_meta(target: HybridIndexer, source: str, meta: dict[str, Any]) -> dict:
    """Write TARGET's corpus metadata point from SOURCE's, for TARGET's model.

    write_corpus_meta sets the fields that describe the vectors (kind, model,
    placeholder vector, built_at, org_id): a first call learns which they are, the
    second carries over every other SOURCE field (acts, languages, data_source,
    ...) and records the origin, so a field added to write_corpus_meta later is
    never overwritten by the SOURCE value.
    """
    acts, as_of = meta.get("acts") or [], meta.get("corpus_as_of")
    own = target.write_corpus_meta(acts=acts, corpus_as_of=as_of)
    carried = {key: value for key, value in meta.items() if key not in own}
    carried["reembedded_from"] = {
        "collection": source,
        "embedding_model": meta.get("embedding_model"),
        "built_at": meta.get("built_at"),
    }
    return target.write_corpus_meta(acts=acts, corpus_as_of=as_of, extra=carried)


# ─── CLI ─────────────────────────────────────────────────────────


def _positive(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", required=True, help="collection to copy (only read)")
    parser.add_argument("--target", required=True, help="collection to create or fill")
    parser.add_argument("--model", required=True, help="FastEmbed dense model for TARGET")
    parser.add_argument("--dim", type=_positive, required=True, help="vector size of --model")
    parser.add_argument("--host", default=None, help="Qdrant host (default: QDRANT_HOST)")
    parser.add_argument("--port", type=_positive, default=None, help="default: QDRANT_PORT")
    parser.add_argument(
        "--batch-size",
        type=_positive,
        default=None,
        help="points per scroll / embed / upsert (default: EMBEDDING_BATCH_SIZE)",
    )
    parser.add_argument(
        "--recreate-target", action="store_true", help="drop TARGET first if it exists"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan; load no model, write nothing"
    )
    args = parser.parse_args(argv)
    if args.target == args.source:
        parser.error("--target must differ from --source (SOURCE is never written)")

    settings = get_settings()
    host = args.host or settings.qdrant_host
    port = args.port or settings.qdrant_port
    batch_size = args.batch_size or settings.embedding_batch_size
    # TARGET's indexer: its collection setup, passage text and prefixes are the seed's.
    target = HybridIndexer(
        qdrant_host=host,
        qdrant_port=port,
        embedding_model=args.model,
        embedding_dim=args.dim,
        collection_name=args.target,
    )
    # Read-only view of SOURCE, used for its corpus metadata point only.
    source_view = HybridIndexer(qdrant_host=host, qdrant_port=port, collection_name=args.source)
    try:
        source_layout = collection_layout(target.client, args.source)
        target_layout = collection_layout(target.client, args.target)
    except Exception as e:
        print(f"cannot read Qdrant at {host}:{port}: {e}", file=sys.stderr)
        return 1
    if source_layout is None:
        print(f"SOURCE {args.source} does not exist on {host}:{port}", file=sys.stderr)
        return 2
    source_meta = source_view.get_corpus_info()
    listed_dim = fastembed_dim(args.model)

    problems = source_problems(source_layout) + target_problems(
        target_layout, args.dim, args.recreate_target
    )
    if listed_dim is None:
        problems.append(f"{args.model} is not in FastEmbed's TextEmbedding model list")
    elif listed_dim != args.dim:
        problems.append(
            f"FastEmbed lists {args.model} with {listed_dim} dimensions, not {args.dim}"
        )

    meta_points = 1 if source_meta else 0
    total = source_layout["points"] - meta_points
    created = (
        f"created by HybridIndexer.setup_collection (dense {args.dim} cosine, "
        f"{SPARSE_VECTOR} idf, {len(PAYLOAD_INDEX_FIELDS)} payload indexes)"
    )
    if target_layout is None:
        target_state = created
    elif args.recreate_target:
        target_state = f"exists ({target_layout['points']} points), dropped and {created}"
    else:
        target_state = f"exists ({target_layout['points']} points), same ids overwritten"
    print("Re-embed plan")
    print(f"  qdrant  {host}:{port}")
    print(
        f"  source  {args.source}: {source_layout['points']} points "
        f"({meta_points} corpus meta), dense {source_layout['dense']}, "
        f"sparse {source_layout['sparse']} - read only"
    )
    if source_meta:
        print(
            f"          corpus as of {source_meta.get('corpus_as_of')}, built "
            f"{source_meta.get('built_at')} with {source_meta.get('embedding_model')}"
        )
    print(f"  target  {args.target}: {target_state}")
    print(
        f"  model   {args.model} ({listed_dim} dims per FastEmbed), "
        f"passage prefix {target.passage_prefix!r}, query prefix {target.query_prefix!r}"
    )
    print(
        f"  work    {total} passages re-embedded in batches of {batch_size}; ids, payloads "
        f"and {SPARSE_VECTOR} vectors copied unchanged"
        + ("; corpus meta rewritten for the new model" if source_meta else "")
    )
    if problems:
        print("Refused:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 2
    if args.dry_run:
        print("Dry run: nothing written.")
        return 0

    try:
        target.setup_collection(recreate=args.recreate_target)
        copied = copy_points(args.source, target, batch_size, total)
        if source_meta:
            rewrite_corpus_meta(target, args.source, source_meta)
        written = target.client.count(collection_name=args.target, exact=True).count
    except Exception as e:
        print(f"re-embedding failed: {e}", file=sys.stderr)
        return 1
    expected = copied + meta_points
    if written != source_layout["points"] or copied != total:
        print(
            f"TARGET has {written} points, SOURCE {source_layout['points']} "
            f"({copied} of {total} copied): rerun, with --recreate-target if TARGET "
            "held other points",
            file=sys.stderr,
        )
        return 1
    print(f"Done: {expected} points in {args.target} ({copied} re-embedded with {args.model}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
