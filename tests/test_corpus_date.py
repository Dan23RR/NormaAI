"""The corpus date users see ("Corpus al ...") comes from the collection.

``src.api.app_state.corpus_as_of`` reads the date the seed or
``--action update`` recorded in the corpus metadata point, and falls back to the
CORPUS_AS_OF setting only when the collection says nothing. Every place that
shows the date goes through it: the metadata of /qa, the ``done`` event of
the stream, GET /api/v1/stats and the PDF reports.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.api import app_state as state_mod
from src.api.app_state import app_state, corpus_as_of


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """As tests/test_system_router.py: evict the app and routers this file imports,
    so the sys.modules patching of test_leads / test_api_integration stays intact."""
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture
def collection():
    """The API's indexer with a corpus metadata point; restored afterwards."""
    saved = (app_state.indexer, app_state.qdrant_available)
    indexer = MagicMock(name="HybridIndexer")
    indexer.get_corpus_info.return_value = {"kind": "corpus_meta", "corpus_as_of": "2026-11-18"}
    app_state.indexer, app_state.qdrant_available = indexer, True
    state_mod.reset_corpus_date()
    yield indexer
    app_state.indexer, app_state.qdrant_available = saved
    state_mod.reset_corpus_date()


def test_the_recorded_date_wins_over_the_setting(collection):
    assert corpus_as_of("2026-02-28") == "2026-11-18"


@pytest.mark.parametrize(
    "info", [None, {}, {"corpus_as_of": ""}, {"corpus_as_of": 20261118}, "not a dict"]
)
def test_without_a_recorded_date_the_setting(collection, info):
    collection.get_corpus_info.return_value = info
    assert corpus_as_of("2026-02-28") == "2026-02-28"
    assert corpus_as_of(None) is None
    state_mod.reset_corpus_date()
    assert corpus_as_of("") is None


def test_qdrant_down_gives_the_setting_and_never_raises(collection):
    collection.get_corpus_info.side_effect = RuntimeError("connection refused")
    assert corpus_as_of("2026-02-28") == "2026-02-28"
    app_state.qdrant_available = False
    assert corpus_as_of("2026-02-28") == "2026-02-28"


def test_without_the_indexer_the_setting():
    saved = app_state.indexer
    app_state.indexer = None
    try:
        assert corpus_as_of(" 2026-02-28 ") == "2026-02-28"
    finally:
        app_state.indexer = saved


def test_the_collection_is_read_once_every_few_minutes(collection, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(state_mod.time, "monotonic", lambda: clock[0])
    assert corpus_as_of() == "2026-11-18"
    collection.get_corpus_info.return_value = {"corpus_as_of": "2026-12-01"}
    clock[0] += state_mod.CORPUS_DATE_TTL_SECONDS - 1
    assert corpus_as_of() == "2026-11-18"
    clock[0] += 2
    assert corpus_as_of() == "2026-12-01"
    assert collection.get_corpus_info.call_count == 2


def test_another_indexer_is_read_again(collection):
    assert corpus_as_of() == "2026-11-18"
    other = MagicMock()
    other.get_corpus_info.return_value = {"corpus_as_of": "2027-01-04"}
    app_state.indexer = other
    assert corpus_as_of() == "2027-01-04"


def test_the_stream_done_event_carries_the_recorded_date(collection):
    from src.api.streaming import generators

    fields = generators._result_fields({}, with_citations=False)
    assert fields["corpus_as_of"] == "2026-11-18"


def test_qa_metadata_carries_the_recorded_date(collection):
    from src.api.routers import intelligence

    user = SimpleNamespace(org_id="org-1")
    settings = MagicMock(corpus_as_of="2026-02-28", active_model="claude-haiku-5-5")
    with patch.object(intelligence, "get_settings", return_value=settings):
        meta = intelligence._build_metadata(user)
    assert meta["corpus_as_of"] == "2026-11-18"


def test_the_pdf_footer_carries_the_recorded_date(collection):
    from src.reports.generator import _NormaPDF

    assert "Regulatory corpus as of 2026-11-18" in _NormaPDF()._disclaimer


def test_stats_fall_back_to_the_setting_without_a_point(collection):
    from fastapi.testclient import TestClient

    from src.api.main import app

    collection.get_corpus_info.return_value = None
    collection.get_collection_stats.return_value = {"points_count": 10}
    settings = MagicMock(corpus_as_of="2026-02-28")
    with patch("src.api.routers.system.get_settings", return_value=settings):
        body = TestClient(app).get("/api/v1/stats").json()
    assert body["corpus_as_of"] == "2026-02-28"
