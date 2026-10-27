"""Offline checks for the retrieval-only golden v2 evaluation (retrieval_eval.py).

The scoring helpers run on the shipped golden_v2.jsonl with a fake retrieval;
main() runs with a fake indexer. No Qdrant, no model download.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config import get_settings
from src.nlp.embedding.indexer import indexer_kwargs_from_settings
from tests.validation import retrieval_eval as ev
from tests.validation.golden_v2 import load_golden_v2_test_cases

ART50_HIT = {"article": "Art. 50", "celex": "32024R1689"}


@pytest.mark.parametrize(
    ("label", "number"),
    [
        ("Art. 19a(1)", "19a"),
        ("Art. 5(1)(a)", "5"),
        ("Art. 50", "50"),
        ("Annex XIV", None),
        (None, None),
        # Italian Latin suffixes are English letters (Art. 19 bis = Art. 19a).
        ("Art. 19 bis", "19a"),
        ("Art. 29-quinquies", "29d"),
    ],
)
def test_article_number(label, number):
    assert ev.article_number(label) == number


def test_retrieved_articles_count_only_article_chunks():
    results = [
        {"article": "Art. 19a"},
        {"article": "Recital 7"},
        {"article": "Annex II"},
        {"article": "Art. ?"},
        {"article": None},
    ]
    assert ev.retrieved_articles(results) == {"19a"}


def test_art50_rank_only_counts_the_ai_act():
    results = [{"article": "Art. 50", "celex": "32016R0679"}, {"article": "Art. 6"}, ART50_HIT]
    assert ev.art50_rank(results) == 2
    assert ev.art50_rank(results[:2]) is None


def test_evaluate_scores_the_90_cases_that_expect_an_article():
    cases = load_golden_v2_test_cases()
    by_query = {c.query: [{"article": f"Art. {n}"} for n in ev.expected_articles(c)] for c in cases}

    def perfect(query):
        return by_query.get(query) or [ART50_HIT]

    rows, art50 = ev.evaluate(cases, perfect)
    # 101 records minus the abstention / refusal ones (the 77-of-90 baseline).
    assert len(rows) == 90
    assert all(row["hit"] for row in rows)
    assert [entry["art50_rank"] for entry in art50] == [0, 0, 0, 0]

    rows, art50 = ev.evaluate(cases, lambda query: [])
    assert not any(row["hit"] for row in rows)
    assert [entry["art50_rank"] for entry in art50] == [None] * 4


def test_summarise_keeps_the_report_keys():
    rows = [
        {"id": "a", "framework": "GDPR", "expected": ["5"], "hit": True},
        {"id": "b", "framework": "GDPR", "expected": ["6"], "hit": False},
        {"id": "c", "framework": "DORA", "expected": ["28"], "hit": True},
    ]
    summary = ev.summarise("x", rows, [])
    assert summary == {
        "label": "x",
        "cases_with_expected_article": 3,
        "expected_article_in_top15": 2,
        "rate": 0.667,
        "by_framework": {"DORA": "1/1", "GDPR": "1/2"},
        "art50_natural_language": [],
        "misses": ["b"],
    }
    assert ev.summarise("empty", [], [])["rate"] == 0.0


def test_retrieve_stops_on_a_retrieval_error():
    failure = {"retrieved_chunks": [], "error": "Knowledge base retrieval failed: down"}
    with (
        patch("src.agents.nodes.retrieve_node", return_value=failure),
        pytest.raises(RuntimeError, match="retrieval failed"),
    ):
        ev.retrieve("q")
    with patch("src.agents.nodes.retrieve_node", return_value={"retrieved_chunks": [ART50_HIT]}):
        assert ev.retrieve("q") == [ART50_HIT]


def test_help_needs_no_qdrant(capsys):
    with (
        patch("src.nlp.embedding.indexer.HybridIndexer") as indexer_cls,
        pytest.raises(SystemExit) as exit_info,
    ):
        ev.main(["--help"])
    assert exit_info.value.code == 0
    assert "--label" in capsys.readouterr().out
    indexer_cls.assert_not_called()


def test_label_must_be_file_name_safe():
    with pytest.raises(SystemExit) as exit_info:
        ev.main(["--label", "../e5 large"])
    assert exit_info.value.code == 2


def _fake_indexer(corpus_model):
    indexer = MagicMock()
    indexer.get_corpus_info.return_value = {
        "embedding_model": corpus_model,
        "corpus_as_of": "2026-10-24",
    }
    indexer.COLLECTION_NAME = "eu_regulations"
    indexer.embedding_model_name = get_settings().embedding_model
    indexer.embedding_dim = 768
    indexer.query_prefix = indexer.passage_prefix = ""
    return indexer


def test_main_builds_the_indexer_from_settings_and_writes_the_report(tmp_path):
    indexer = _fake_indexer(get_settings().embedding_model)
    with (
        patch("src.nlp.embedding.indexer.HybridIndexer", return_value=indexer) as indexer_cls,
        patch("src.api.app_state.app_state.indexer", None),
        patch.object(ev, "retrieve", return_value=[ART50_HIT]),
    ):
        code = ev.main(["--label", "unit", "--out-dir", str(tmp_path)])

    assert code == 0
    # The fixed bug: model, dimension and collection come from the settings.
    indexer_cls.assert_called_once_with(
        **indexer_kwargs_from_settings(get_settings()), qdrant_timeout=120
    )
    report = json.loads((tmp_path / "retrieval_unit.json").read_text(encoding="utf-8"))
    assert report["cases_with_expected_article"] == 90
    assert report["config"]["collection"] == "eu_regulations"
    assert report["config"]["corpus_as_of"] == "2026-10-24"


def test_main_reranks_like_the_api_and_records_it(tmp_path):
    from src.api.app_state import app_state

    reranker = MagicMock(model_path=Path("/app/models/reranker/model.onnx"))
    with (
        patch(
            "src.nlp.embedding.indexer.HybridIndexer",
            return_value=_fake_indexer(get_settings().embedding_model),
        ),
        patch("src.nlp.embedding.reranker.reranker_from_settings", return_value=reranker),
        patch("src.api.app_state.app_state.indexer", None),
        patch("src.api.app_state.app_state.reranker", None),
        patch.object(ev, "retrieve", return_value=[ART50_HIT]),
    ):
        code = ev.main(["--label", "unit", "--out-dir", str(tmp_path)])
        assert app_state.reranker is reranker  # retrieve_node reranks as in the API

    assert code == 0
    config = json.loads((tmp_path / "retrieval_unit.json").read_text(encoding="utf-8"))["config"]
    assert config["reranker"] == str(Path("/app/models/reranker/model.onnx"))
    assert config["reranker_candidates"] == get_settings().reranker_candidates
    assert config["reranker_search_depth"] == get_settings().reranker_search_depth


def test_main_refuses_a_collection_built_with_another_model(tmp_path, capsys):
    indexer = _fake_indexer("intfloat/multilingual-e5-large")
    retrieval = MagicMock()
    with (
        patch("src.nlp.embedding.indexer.HybridIndexer", return_value=indexer),
        patch("src.api.app_state.app_state.indexer", None),
        patch.object(ev, "retrieve", retrieval),
    ):
        code = ev.main(["--label", "unit", "--out-dir", str(tmp_path)])

    assert code == 2
    assert "multilingual-e5-large" in capsys.readouterr().err
    retrieval.assert_not_called()
    assert not list(tmp_path.iterdir())


def test_default_report_dir_is_git_ignored():
    # Local experiment results: the default folder must stay out of git.
    repo_root = Path(__file__).resolve().parents[2]
    rel = ev.DEFAULT_OUT_DIR.resolve().relative_to(repo_root).as_posix()
    ignored = (repo_root / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"{rel}/" in ignored
