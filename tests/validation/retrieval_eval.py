"""Retrieval-only evaluation of the golden v2 set (no LLM calls, no cost).

For every golden v2 question that expects an article, run the retrieval the Q&A
agents run (src.agents.nodes.retrieve_node: keyword framework detection, hybrid
search, 15 chunks, up to 20 when several frameworks are detected) and check
whether a chunk of the expected article is among the results. Also reports the
rank of AI Act Art. 50 for four chatbot questions that do not name the article.

The question is searched alone, without the record's company profile (the API
golden run sends it, and retrieve_node falls back to its single framework when
no framework keyword is detected), so the numbers stay comparable with the first
measurement: 77 of 90 on 2026-10-24.

Qdrant, collection and dense model come from the settings, as in the app:
QDRANT_HOST / QDRANT_PORT, QDRANT_COLLECTION, EMBEDDING_MODEL and
EMBEDDING_DIMENSION (the model's query prefix follows the model). To compare two
dense models, re-embed the corpus into a second collection
(scripts/reembed_collection.py) and run once per collection, e.g. in PowerShell:

    python -m tests.validation.retrieval_eval --label mpnet
    $env:QDRANT_COLLECTION = "eu_regulations_e5"
    $env:EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
    $env:EMBEDDING_DIMENSION = "1024"
    python -m tests.validation.retrieval_eval --label e5-large

Writes <out-dir>/retrieval_<label>.json (default: tests/validation/reports/retrieval/,
git-ignored) and prints a summary line plus the Art. 50 ranks. Needs a running
Qdrant with a seeded collection and loads the dense model, so it is not part of
the pytest suite (test_retrieval_eval.py covers the scoring offline). Exit code
0; 1 when retrieval fails; 2 when the collection was built with another model.

Matching: an expected article counts as found when a retrieved chunk labelled
"Art. ..." carries the same number, letter suffix included ("19a"). Italian
Latin suffixes read as letters, as in the golden set metric
(tests.validation.metrics.normalize_article): "Art. 19 bis" is "19a". Runs before
2026-10-26 read it as "19", which undercounted the CSRD cases on Art. 19a and 29a.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import Any

from .golden_v2 import GOLDEN_V2_PATH, load_golden_v2_test_cases
from .metrics import normalize_article

DEFAULT_OUT_DIR = pathlib.Path(__file__).parent / "reports" / "retrieval"
AI_ACT_CELEX = "32024R1689"
# Chatbot questions that need AI Act Art. 50 (transparency) without naming it.
NATURAL_ART50 = (
    "Il chatbot sul sito della nostra azienda deve dichiarare di essere un'intelligenza artificiale? Da quando?",
    "Does the chatbot on our website have to tell visitors that it is an AI?",
    "Il nostro assistente virtuale per i clienti deve avvisare che è un sistema di IA?",
    "Do we need to tell customers they are talking to a bot on our customer service chat?",
)
SUMMARY_KEYS = ("label", "cases_with_expected_article", "expected_article_in_top15", "rate")
LABEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

Retrieve = Callable[[str], list[dict[str, Any]]]


# ─── Scoring (pure) ──────────────────────────────────────────────


def article_number(label: object) -> str | None:
    """First article number of a label, lower-case: "Art. 19a(1)" and "Art. 19 bis" -> "19a"."""
    m = re.search(r"(\d+[a-z]?)", normalize_article(str(label or "")))
    return m.group(1) if m else None


def expected_articles(case: Any) -> set[str]:
    """Article numbers a golden case expects (empty for refusal / out-of-corpus cases)."""
    return {article_number(f.article) for f in case.expected_findings} - {None}


def retrieved_articles(results: Iterable[dict[str, Any]]) -> set[str]:
    """Article numbers of the retrieved chunks labelled "Art. ..." (recitals, annexes ignored)."""
    labels = (str(r.get("article") or "") for r in results)
    return {article_number(label) for label in labels if label.startswith("Art.")} - {None}


def art50_rank(results: list[dict[str, Any]]) -> int | None:
    """0-based rank of the first AI Act Art. 50 chunk; None when it was not retrieved."""
    return next(
        (
            i
            for i, r in enumerate(results)
            if str(r.get("article") or "") == "Art. 50"
            and str(r.get("celex") or "").startswith(AI_ACT_CELEX)
        ),
        None,
    )


def evaluate(cases: Iterable[Any], retrieve: Retrieve) -> tuple[list[dict], list[dict]]:
    """Score every case that expects an article, then rank Art. 50 for NATURAL_ART50.

    Returns (rows, art50): one row per scored case ({id, framework, expected,
    hit}) and one entry per chatbot question ({query, art50_rank, top3}).
    """
    rows = []
    for case in cases:
        expected = expected_articles(case)
        if not expected:
            continue  # abstention / refusal cases have no expected article
        hit = bool(expected & retrieved_articles(retrieve(case.query)))
        rows.append(
            {
                "id": case.id,
                "framework": case.expected_findings[0].framework.value,
                "expected": sorted(expected),
                "hit": hit,
            }
        )
    art50 = []
    for query in NATURAL_ART50:
        results = retrieve(query)
        art50.append(
            {
                "query": query,
                "art50_rank": art50_rank(results),
                "top3": [f"{r.get('celex')} {r.get('article')}" for r in results[:3]],
            }
        )
    return rows, art50


def summarise(label: str, rows: list[dict], art50: list[dict]) -> dict[str, Any]:
    """The JSON report (same keys as the first measurement's retrieval_*.json files)."""
    by_framework: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        by_framework[row["framework"]][0] += int(row["hit"])
        by_framework[row["framework"]][1] += 1
    hits = sum(int(row["hit"]) for row in rows)
    return {
        "label": label,
        "cases_with_expected_article": len(rows),
        "expected_article_in_top15": hits,
        "rate": round(hits / len(rows), 3) if rows else 0.0,
        "by_framework": {fw: f"{h}/{n}" for fw, (h, n) in sorted(by_framework.items())},
        "art50_natural_language": art50,
        "misses": [row["id"] for row in rows if not row["hit"]],
    }


# ─── Retrieval (needs Qdrant + the dense model) ──────────────────


def retrieve(query: str) -> list[dict[str, Any]]:
    """The chunks the Q&A agents get for ``query`` (src.agents.nodes.retrieve_node).

    retrieve_node uses ``app_state.indexer`` (set by main) and turns a Qdrant
    failure into an empty result plus an error: here that error stops the run
    instead of being scored as a miss.
    """
    from src.agents.nodes import retrieve_node

    out = retrieve_node({"query": query})
    if out.get("error"):
        raise RuntimeError(out["error"])
    return list(out.get("retrieved_chunks") or [])


def _label(value: str) -> str:
    if not LABEL_RE.match(value):
        raise argparse.ArgumentTypeError("use letters, digits, '.', '_' or '-' (e.g. e5-large)")
    return value


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--label", required=True, type=_label, help="name of the run, used in the file name"
    )
    parser.add_argument(
        "--out-dir",
        type=pathlib.Path,
        default=DEFAULT_OUT_DIR,
        help="where retrieval_<label>.json goes (default: tests/validation/reports/retrieval)",
    )
    parser.add_argument("--golden", type=pathlib.Path, default=GOLDEN_V2_PATH, help="golden JSONL")
    args = parser.parse_args(argv)

    # Heavy imports only now: --help needs neither Qdrant nor the model.
    from src.api.app_state import app_state
    from src.config import get_settings
    from src.nlp.embedding.indexer import HybridIndexer, indexer_kwargs_from_settings

    settings = get_settings()
    # A batch job: allow slow Qdrant answers on a busy machine (default request timeout: 5 s).
    indexer = HybridIndexer(**indexer_kwargs_from_settings(settings), qdrant_timeout=120)
    corpus = indexer.get_corpus_info() or {}
    built_with = corpus.get("embedding_model")
    if built_with and str(built_with).lower() != str(settings.embedding_model).lower():
        print(
            f"collection {indexer.COLLECTION_NAME} was built with {built_with} but "
            f"EMBEDDING_MODEL={settings.embedding_model}: the queries would be embedded "
            "in another vector space. Set the model of the collection you evaluate.",
            file=sys.stderr,
        )
        return 2
    app_state.indexer = indexer  # retrieve_node reuses it (one model load, not one per query)

    try:
        rows, art50 = evaluate(load_golden_v2_test_cases(args.golden), retrieve)
    except RuntimeError as e:
        print(f"retrieval failed: {e}", file=sys.stderr)
        return 1

    summary = summarise(args.label, rows, art50)
    summary["config"] = {
        "collection": indexer.COLLECTION_NAME,
        "embedding_model": indexer.embedding_model_name,
        "embedding_dim": indexer.embedding_dim,
        "query_prefix": indexer.query_prefix,
        "passage_prefix": indexer.passage_prefix,
        "corpus_embedding_model": built_with,
        "corpus_as_of": corpus.get("corpus_as_of"),
        "golden_file": args.golden.name,
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"retrieval_{args.label}.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    line = {key: summary[key] for key in SUMMARY_KEYS}
    line["by_framework"] = summary["by_framework"]
    print(json.dumps(line, ensure_ascii=False))
    for entry in art50:
        print("Art. 50 rank", entry["art50_rank"], "|", entry["query"][:70], "|", entry["top3"])
    print(f"written {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
