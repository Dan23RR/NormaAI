"""Corpus freshness: is the indexed version of each tracked EU act the latest one?

- ``src.pipeline.corpus_freshness``: the comparison, with a fake list of
  versions in place of CELLAR and a fake corpus metadata point in place of
  Qdrant;
- ``store_freshness`` / ``run_check_freshness``: the outcome in ``system_state``
  (``python -m src.pipeline --action check-freshness``);
- ``GET /api/v1/stats``: the ``freshness`` field, "unknown" without a database
  or before the job has run;
- the two scheduled actions of the command line.

No network, no Qdrant, no PostgreSQL.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import src.pipeline as pipeline_mod
from src.config import get_settings
from src.db.models import CORPUS_FRESHNESS_KEY, SystemState
from src.document_check.official import TextUnavailableError, Version
from src.pipeline import corpus_freshness, store_freshness
from tests.documents_support import Database

NOW = datetime(2026, 11, 11, 3, 10, tzinfo=UTC)
AI_ACT = "32024R1689"
GDPR = "32016R0679"
CSRD = "32022L2464"
OMNIBUS_AI = "32026R1744"  # an amending act: never consolidated


class FakeCellar:
    """``versions(celex)`` as the document check's source answers it."""

    def __init__(self, consolidated: dict[str, list[tuple[str, bool]]] | None = None) -> None:
        # act -> [(consolidation date, is the snapshot of the act as published)]
        self.consolidated = consolidated or {}
        self.down: set[str] = set()
        self.asked: list[str] = []

    def versions(self, celex: str) -> list[Version]:
        self.asked.append(celex)
        if celex in self.down:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        versions = [Version(celex, None)]
        for as_of, initial in self.consolidated.get(celex, []):
            versions.append(Version(f"0{celex[1:]}-{as_of.replace('-', '')}", as_of, initial))
        return versions


def _corpus(*acts: tuple[str, str, str]) -> dict:
    """A corpus metadata point: (act, language, id of the text indexed)."""
    return {
        "kind": "corpus_meta",
        "corpus_as_of": "2026-10-27",
        "acts": [
            {"celex": celex, "lang": lang, "source_celex": text_id, "chunks": 10}
            for celex, lang, text_id in acts
        ],
    }


def _all_tracked(text_ids: dict[str, str] | None = None) -> dict:
    """Every act the freshness check looks at, indexed as adopted unless said otherwise."""
    text_ids = text_ids or {}
    return _corpus(
        *[
            (act.celex, lang, text_ids.get(act.celex, act.celex))
            for act in pipeline_mod.TRACKED_ACTS
            for lang in ("EN", "IT")
        ]
    )


# ─── The comparison ──────────────────────────────────────────────────


class TestCorpusFreshness:
    def test_without_corpus_metadata_the_answer_is_unknown(self):
        cellar = FakeCellar()
        for corpus in (None, {}, {"acts": []}, {"acts": "x"}):
            outcome = corpus_freshness(corpus, cellar.versions, NOW)
            assert outcome["status"] == "unknown"
            assert outcome["checked_at"] is None and outcome["outdated"] == []
            assert outcome["reason"] == "corpus metadata not available"
        assert cellar.asked == []  # nothing to compare: CELLAR is not asked

    def test_a_corpus_with_the_latest_versions_is_ok(self):
        cellar = FakeCellar(
            {AI_ACT: [("2024-07-12", True), ("2026-07-27", False)], GDPR: [("2016-05-04", True)]}
        )
        corpus = _all_tracked({AI_ACT: "02024R1689-20260727"})
        outcome = corpus_freshness(corpus, cellar.versions, NOW)
        assert outcome["status"] == "ok"
        assert outcome["checked_at"] == "2026-11-11T03:10:00Z"
        assert outcome["outdated"] == [] and outcome["missing"] == [] and outcome["unknown"] == []
        assert outcome["corpus_as_of"] == "2026-10-27"
        tracked = [a.celex for a in pipeline_mod.TRACKED_ACTS if a.consolidated]
        assert outcome["acts"] == len(tracked)
        assert sorted(cellar.asked) == sorted(tracked)

    def test_an_older_consolidated_text_is_outdated(self):
        cellar = FakeCellar({AI_ACT: [("2024-07-12", True), ("2026-07-27", False)]})
        corpus = _all_tracked({AI_ACT: "02024R1689-20240712"})
        outcome = corpus_freshness(corpus, cellar.versions, NOW)
        assert outcome["status"] == "outdated"
        assert outcome["outdated"] == [
            {
                "celex": AI_ACT,
                "indexed": "02024R1689-20240712",
                "latest": "02024R1689-20260727",
                "langs": ["EN", "IT"],
            }
        ]
        assert outcome["checked_at"] == "2026-11-11T03:10:00Z"

    def test_the_act_as_adopted_is_behind_a_real_consolidated_text(self):
        cellar = FakeCellar({CSRD: [("2023-01-05", True), ("2026-03-18", False)]})
        outcome = corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert outcome["outdated"] == [
            {
                "celex": CSRD,
                "indexed": CSRD,
                "latest": "02022L2464-20260318",
                "langs": ["EN", "IT"],
            }
        ]

    def test_the_act_as_adopted_is_not_behind_cellars_snapshot_of_itself(self):
        # The only "consolidated" text is the act as published: same words.
        cellar = FakeCellar({GDPR: [("2016-05-04", True)]})
        outcome = corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert outcome["status"] == "ok" and outcome["outdated"] == []

    def test_one_language_behind(self):
        cellar = FakeCellar({AI_ACT: [("2024-07-12", True), ("2026-07-27", False)]})
        corpus = _all_tracked()
        for entry in corpus["acts"]:
            if entry["celex"] == AI_ACT and entry["lang"] == "EN":
                entry["source_celex"] = "02024R1689-20260727"
        outcome = corpus_freshness(corpus, cellar.versions, NOW)
        assert outcome["outdated"] == [
            {
                "celex": AI_ACT,
                "indexed": AI_ACT,
                "latest": "02024R1689-20260727",
                "langs": ["IT"],
            }
        ]

    def test_amending_acts_are_not_looked_up(self):
        cellar = FakeCellar()
        corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert OMNIBUS_AI not in cellar.asked
        assert AI_ACT in cellar.asked

    def test_an_act_cellar_cannot_list_is_unknown_not_fresh(self):
        cellar = FakeCellar()
        cellar.down = {GDPR}
        outcome = corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert outcome["unknown"] == [GDPR]
        assert outcome["status"] == "unknown"  # nothing found outdated, but not everything asked
        assert outcome["checked_at"] == "2026-11-11T03:10:00Z"

        cellar.consolidated = {AI_ACT: [("2026-07-27", False)]}
        outcome = corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert outcome["status"] == "outdated" and outcome["unknown"] == [GDPR]

    def test_cellar_down_for_every_act(self):
        cellar = FakeCellar()
        cellar.down = {a.celex for a in pipeline_mod.TRACKED_ACTS}
        outcome = corpus_freshness(_all_tracked(), cellar.versions, NOW)
        assert outcome["status"] == "unknown" and outcome["checked_at"] is None
        assert outcome["acts"] == 0 and len(outcome["unknown"]) > 10

    def test_tracked_acts_the_corpus_does_not_hold(self):
        cellar = FakeCellar()
        outcome = corpus_freshness(_corpus((GDPR, "IT", GDPR)), cellar.versions, NOW)
        assert GDPR not in outcome["missing"] and AI_ACT in outcome["missing"]
        assert outcome["status"] == "ok" and outcome["acts"] == 1
        assert cellar.asked == [GDPR]

    def test_the_corpus_may_name_an_act_by_its_consolidated_id(self):
        cellar = FakeCellar({AI_ACT: [("2026-07-27", False)]})
        corpus = _corpus(("02024R1689-20260727", "IT", "02024R1689-20260727"))
        outcome = corpus_freshness(corpus, cellar.versions, NOW)
        assert outcome["outdated"] == [] and AI_ACT not in outcome["missing"]


# ─── Stored outcome ──────────────────────────────────────────────────


class TestStore:
    async def test_one_row_rewritten_at_every_run(self):
        db = Database()
        await store_freshness(db.session, {"status": "ok", "outdated": []}, NOW)
        await store_freshness(db.session, {"status": "outdated", "outdated": [{"celex": "x"}]}, NOW)
        (row,) = db.rows(SystemState)
        assert row.key == CORPUS_FRESHNESS_KEY
        assert row.value == {"status": "outdated", "outdated": [{"celex": "x"}]}
        # system_state belongs to no tenant.
        assert db.session_orgs == [None, None]

    def test_the_job_without_qdrant_stores_unknown(self):
        db = Database()
        manager = MagicMock()
        manager.session = db.session
        manager.close = MagicMock(side_effect=lambda: _done())
        indexer = MagicMock()
        indexer.get_corpus_info.return_value = None  # Qdrant down, or no metadata point
        with (
            patch.object(pipeline_mod, "HybridIndexer", return_value=indexer),
            patch("src.db.engine.db_manager", manager),
            patch("src.document_check.sources.default_source") as default_source,
        ):
            outcome = pipeline_mod.run_check_freshness()
        assert outcome["status"] == "unknown" and outcome["checked_at"] is None
        default_source.assert_not_called()  # no corpus, nothing to ask CELLAR
        manager.init.assert_called_once()
        (row,) = db.rows(SystemState)
        assert row.value["status"] == "unknown"

    def test_the_job_when_qdrant_cannot_even_be_built(self):
        db = Database()
        manager = MagicMock()
        manager.session = db.session
        manager.close = MagicMock(side_effect=lambda: _done())
        with (
            patch.object(pipeline_mod, "HybridIndexer", side_effect=RuntimeError("no qdrant")),
            patch("src.db.engine.db_manager", manager),
        ):
            outcome = pipeline_mod.run_check_freshness()
        assert outcome["status"] == "unknown"
        assert db.rows(SystemState)[0].value["reason"] == "corpus metadata not available"

    def test_the_job_compares_and_stores(self):
        db = Database()
        manager = MagicMock()
        manager.session = db.session
        manager.close = MagicMock(side_effect=lambda: _done())
        indexer = MagicMock()
        indexer.get_corpus_info.return_value = _all_tracked({AI_ACT: "02024R1689-20240712"})
        cellar = FakeCellar({AI_ACT: [("2024-07-12", True), ("2026-07-27", False)]})
        with (
            patch.object(pipeline_mod, "HybridIndexer", return_value=indexer),
            patch("src.db.engine.db_manager", manager),
            patch("src.document_check.sources.default_source", return_value=cellar) as source,
        ):
            outcome = pipeline_mod.run_check_freshness()
        source.assert_called_once()  # one source for the whole run
        assert outcome["status"] == "outdated"
        assert db.rows(SystemState)[0].value["outdated"][0]["celex"] == AI_ACT


async def _done() -> None:
    return None


# ─── GET /api/v1/stats ───────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_module_cache():
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture
def stats_client():
    """The bare app of the other router tests, with the engine module it sees."""
    engine = MagicMock()
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": engine},
        ),
    ):
        mock_settings.return_value = get_settings()

        from fastapi.testclient import TestClient

        from src.api.main import app, app_state, limiter

        app_state.qdrant_available = True
        app_state.llm_available = True
        app_state.indexer = MagicMock()
        limiter.enabled = False
        try:
            yield TestClient(app), engine
        finally:
            app.dependency_overrides.clear()


class TestStats:
    def test_unknown_without_a_database(self, stats_client):
        client, _engine = stats_client
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        assert response.json()["freshness"] == {
            "status": "unknown",
            "checked_at": None,
            "outdated": [],
        }

    def test_unknown_before_the_job_has_run(self, stats_client):
        client, engine = stats_client
        engine.db_manager = Database()
        freshness = client.get("/api/v1/stats").json()["freshness"]
        assert freshness == {"status": "unknown", "checked_at": None, "outdated": []}

    def test_the_stored_outcome_is_exposed(self, stats_client):
        client, engine = stats_client
        db = Database()
        engine.db_manager = db
        cellar = FakeCellar({AI_ACT: [("2024-07-12", True), ("2026-07-27", False)]})
        outcome = corpus_freshness(
            _all_tracked({AI_ACT: "02024R1689-20240712"}), cellar.versions, NOW
        )
        with db.sync_session() as session:
            session.add(SystemState(key=CORPUS_FRESHNESS_KEY, value=outcome, updated_at=NOW))
            session.commit()

        body = client.get("/api/v1/stats").json()

        assert body["freshness"] == {
            "status": "outdated",
            "checked_at": "2026-11-11T03:10:00Z",
            "outdated": [
                {
                    "celex": AI_ACT,
                    "indexed": "02024R1689-20240712",
                    "latest": "02024R1689-20260727",
                    "langs": ["EN", "IT"],
                }
            ],
            "missing": [],
            "unknown": [],
        }
        # Read on a session of no tenant, and no more than once a minute.
        assert db.session_orgs == [None]
        client.get("/api/v1/stats")
        assert db.session_orgs == [None]

    def test_qdrant_down_does_not_hide_the_last_outcome(self, stats_client):
        client, engine = stats_client
        from src.api.main import app_state

        app_state.qdrant_available = False
        app_state.indexer = None
        db = Database()
        engine.db_manager = db
        with db.sync_session() as session:
            session.add(
                SystemState(
                    key=CORPUS_FRESHNESS_KEY,
                    value={"status": "ok", "checked_at": "2026-11-10T03:10:00Z", "outdated": []},
                    updated_at=NOW,
                )
            )
            session.commit()
        body = client.get("/api/v1/stats").json()
        assert body["status"] == "degraded"
        assert body["freshness"]["status"] == "ok"
        assert body["freshness"]["checked_at"] == "2026-11-10T03:10:00Z"

    def test_a_malformed_row_is_unknown(self, stats_client):
        client, engine = stats_client
        db = Database()
        engine.db_manager = db
        with db.sync_session() as session:
            session.add(SystemState(key=CORPUS_FRESHNESS_KEY, value=["not", "a", "dict"]))
            session.commit()
        assert client.get("/api/v1/stats").json()["freshness"]["status"] == "unknown"


# ─── Command line ────────────────────────────────────────────────────


class TestScheduledActions:
    @pytest.mark.parametrize("action", ["recheck-documents", "check-freshness"])
    def test_the_action_runs_without_building_the_ingestion_pipeline(self, action, capsys):
        job = MagicMock(return_value={"status": "ok", "nota": "è"})
        with (
            patch.dict(pipeline_mod.SCHEDULED_ACTIONS, {action: job}),
            patch.object(pipeline_mod, "IngestionPipeline") as ingestion,
            patch.object(sys, "argv", ["pipeline", "--action", action]),
        ):
            pipeline_mod.main()
        job.assert_called_once_with()
        ingestion.assert_not_called()  # no embedding model, no document processor
        assert '"status": "ok"' in capsys.readouterr().out

    def test_a_failing_job_fails_the_command(self):
        job = MagicMock(side_effect=RuntimeError("database not reachable"))
        with (
            patch.dict(pipeline_mod.SCHEDULED_ACTIONS, {"recheck-documents": job}),
            patch.object(sys, "argv", ["pipeline", "--action", "recheck-documents"]),
            pytest.raises(RuntimeError),
        ):
            pipeline_mod.main()

    def test_recheck_documents_runs_the_surveillance_on_the_default_source(self):
        from src.document_check import surveillance

        db = Database()
        manager = MagicMock()
        manager.session = db.session
        manager.close = MagicMock(side_effect=lambda: _done())
        source = MagicMock()
        seen = {}

        async def run(sessions, given_source, **kwargs):
            seen["sessions"], seen["source"] = sessions, given_source
            return surveillance.SurveillanceReport(checks=3, provisions=2)

        with (
            patch("src.db.engine.db_manager", manager),
            patch("src.document_check.sources.default_source", return_value=source),
            patch.object(surveillance, "run", side_effect=run),
        ):
            result = pipeline_mod.run_recheck_documents()
        assert seen == {"sessions": db.session, "source": source}
        assert result["checks"] == 3 and result["provisions"] == 2
        manager.init.assert_called_once()
        manager.close.assert_called_once()
