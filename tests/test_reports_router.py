"""Tests for the reports router (src/api/routers/reports.py).

Endpoints under test (mounted at /api/v1/reports/*):
- POST /api/v1/reports/gap-analysis        -> generate a single-framework PDF (StreamingResponse)
- POST /api/v1/reports/executive-summary   -> generate a multi-framework PDF (StreamingResponse)
- GET  /api/v1/reports/history             -> list prior reports for the caller's org

Coverage goals (asserting REAL behavior read from the source):
- auth required: 401 without a token / with an invalid token on every endpoint
- gap-analysis happy path: PDF bytes streamed with the right media type + filename
- gap-analysis validation: 422 when framework / company name is missing or invalid
- gap-analysis 503 when LLM / Qdrant services are unavailable (_require_services)
- gap-analysis 502 when the agent returns an {"error": ...} payload
- executive-summary happy path: PDF streamed; gap analysis run per framework
- executive-summary validation: 422 on empty / oversized frameworks list
- executive-summary 502 when ALL framework analyses fail
- history happy path: returns metadata items + pagination
- history org-scoping: the DB session is opened with the caller's JWT org_id
- history 404-equivalent empty: an org with no reports returns an empty list, 200
- history validation: 422 on out-of-range limit / negative offset
- history DB-unavailable: a "not initialized" RuntimeError degrades to an
  empty result with a warning (not a 500)

Pattern notes
-------------
Mirrors test_gdpr_router.py / test_auth_router.py: bare ``TestClient(app)`` (no
lifespan, rate limiting disabled). The report generator and the agent graph are
mocked so no real LLM / Qdrant / PDF rendering happens. The history endpoint
calls ``db_manager.session(org_id=...)`` directly (NOT via a FastAPI
dependency), so it is reached by patching ``src.api.routers.reports.db_manager``
with a fake whose ``.session()`` is an async context manager yielding a fake
AsyncSession (exact pattern from test_gdpr_router.py).

Isolation: the ``app_objects`` fixture clears ``app.dependency_overrides`` on
teardown, and an autouse fixture evicts ``src.api.main`` / the router submodules
from ``sys.modules`` after each test (mirroring test_critical_routers.py /
test_auth_router.py) so the REAL ``src.db.engine`` binding cached here never
leaks into the sys.modules-patching isolation used by test_leads. This file must
pass in any suite order.
"""

from __future__ import annotations

import contextlib
import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────
#  Module-cache isolation (mirrors test_auth_router.py / test_critical_routers.py)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """Importing ``src.api.main`` caches it + the router submodules bound to the
    REAL ``src.db.engine``. test_leads / test_api_integration re-import those
    fresh against a MagicMock engine via sys.modules patching, so we must evict
    the modules this file cached, or a later leads test would spuriously raise
    "DatabaseSessionManager is not initialized"."""
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


# ──────────────────────────────────────────────────────────────────────────
#  Fake async DB layer (history endpoint only)
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)``.

    The history handler issues two SELECTs:
      - SELECT Assessment ... -> ``.scalars().all()`` (rows)
      - SELECT count(*)   ... -> ``.scalar()``        (an int total)
    """

    def __init__(self, *, rows: list | None = None, scalar: int | None = None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar(self):
        return self._scalar


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession used by the history route.

    ``execute`` dispatches on the rendered SQL: a ``count(`` query returns the
    configured total; any other SELECT returns the configured rows.
    """

    def __init__(self, *, rows: list | None = None, total: int | None = None) -> None:
        self._rows = rows or []
        self._total = total if total is not None else len(rows or [])
        self.execute_calls = 0

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN001
        self.execute_calls += 1
        text = str(stmt).lower()
        if "count(" in text:
            return _FakeResult(scalar=self._total)
        return _FakeResult(rows=self._rows)

    async def commit(self):  # pragma: no cover - history is read-only
        pass

    async def rollback(self):  # pragma: no cover
        pass

    async def close(self):
        pass


class _RaisingSession:
    """Session whose ``execute`` raises a given error (DB-unavailable path)."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self, *args, **kwargs):  # noqa: ANN001
        raise self._error

    async def close(self):
        pass


def _make_fake_db_manager(session):
    """Build a fake ``db_manager`` whose ``.session(...)`` is an async CM that
    records the org_id it was scoped to (org-scoping proof)."""
    fake = MagicMock(name="fake_db_manager")

    @contextlib.asynccontextmanager
    async def _session(org_id: str | None = None):  # noqa: ANN001
        fake.last_org_id = org_id
        yield session

    fake.session = _session
    fake.last_org_id = None
    return fake


class _FakeClient:
    def __init__(self, name: str, org_id: uuid.UUID) -> None:
        self.name = name
        self.org_id = org_id


class _FakeAssessment:
    """Stands in for an ORM Assessment row returned by the history SELECT."""

    def __init__(self, *, framework: str, client_name: str, org_id: uuid.UUID) -> None:
        self.id = uuid.uuid4()
        self.framework = framework
        self.overall_score = 42.0
        self.assessed_at = datetime(2026, 6, 19, 12, 0, 0, tzinfo=UTC)
        self.client = _FakeClient(client_name, org_id)


# ──────────────────────────────────────────────────────────────────────────
#  App / client fixtures (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked (mirrors
    test_gdpr_router.py). Yields (app, app_state, limiter) and clears
    ``app.dependency_overrides`` on teardown so nothing leaks to sibling files."""
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {
                "src.nlp.embedding.indexer": MagicMock(),
                "src.db.engine": MagicMock(),
            },
        ),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app, app_state, limiter

        # Default: services available so report generation is reachable.
        app_state.qdrant_available = True
        app_state.llm_available = True
        app_state.indexer = MagicMock()
        limiter.enabled = False

        try:
            yield app, app_state, limiter
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    app, _state, _limiter = app_objects
    return TestClient(app)


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def auth_headers(user_id, org_id):
    from src.auth.security import create_access_token

    token = create_access_token(user_id=user_id, org_id=org_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def profile():
    """A minimal valid CompanyProfile payload."""
    return {
        "name": "Acme Srl",
        "sector": "Manufacturing",
        "employee_count": 2500,
        "revenue_eur": 200_000_000,
        "jurisdictions": ["IT", "DE"],
        "applicable_frameworks": ["CSRD"],
        "existing_documents": "Annual sustainability report 2024",
    }


# Reusable normalised gap-analysis payload returned by the mocked agent.
_GAP_OK = {
    "framework": "CSRD",
    "overall_score": 45.0,
    "confidence_score": 0.85,
    "requirements": [],
    "recommendations": [],
}


# ──────────────────────────────────────────────────────────────────────────
#  Auth required
# ──────────────────────────────────────────────────────────────────────────


class TestAuthRequired:
    def test_gap_analysis_requires_auth(self, client, profile):
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": profile},
        )
        assert r.status_code == 401

    def test_gap_analysis_rejects_invalid_token(self, client, profile):
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": profile},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401

    def test_executive_summary_requires_auth(self, client, profile):
        r = client.post(
            "/api/v1/reports/executive-summary",
            json={"frameworks": ["CSRD"], "company_profile": profile},
        )
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/api/v1/reports/history")
        assert r.status_code == 401

    def test_history_rejects_invalid_token(self, client):
        r = client.get(
            "/api/v1/reports/history",
            headers={"Authorization": "Bearer nope"},
        )
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
#  Gap analysis: happy path, service availability, agent errors, validation
# ──────────────────────────────────────────────────────────────────────────


class TestGapAnalysis:
    def test_gap_analysis_happy_path_streams_pdf(self, client, auth_headers, profile):
        """Agent + generator are mocked; the handler must stream the PDF bytes
        with the application/pdf media type and an attachment filename."""
        pdf_bytes = b"%PDF-1.4 fake report bytes"

        async def _fake_arun(framework, profile_dict):
            return dict(_GAP_OK)

        gen_instance = MagicMock()
        gen_instance.generate_gap_report.return_value = pdf_bytes
        gen_cls = MagicMock(return_value=gen_instance)

        with (
            patch("src.agents.graph.arun_gap_analysis", _fake_arun),
            patch("src.reports.generator.ComplianceReportGenerator", gen_cls),
        ):
            r = client.post(
                "/api/v1/reports/gap-analysis",
                json={"framework": "CSRD", "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content == pdf_bytes
        # Filename is built from framework + company name.
        cd = r.headers["content-disposition"]
        assert "attachment" in cd
        assert "NormaAI_CSRD_Gap_Report_Acme_Srl.pdf" in cd
        # The generator was invoked with the framework + company name.
        _, kwargs = gen_instance.generate_gap_report.call_args
        assert kwargs["framework"] == "CSRD"
        assert kwargs["company_name"] == "Acme Srl"

    def test_gap_analysis_503_when_qdrant_unavailable(
        self, client, app_objects, auth_headers, profile
    ):
        """_require_services raises 503 if the knowledge base is unavailable."""
        _app, app_state, _limiter = app_objects
        app_state.qdrant_available = False

        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 503
        assert "qdrant" in r.json()["detail"].lower()

    def test_gap_analysis_503_when_llm_unavailable(
        self, client, app_objects, auth_headers, profile
    ):
        _app, app_state, _limiter = app_objects
        app_state.llm_available = False

        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 503
        assert "api_key" in r.json()["detail"].lower()

    def test_gap_analysis_502_when_agent_returns_error(self, client, auth_headers, profile):
        """An {"error": ...} dict from the agent surfaces as a 502 (upstream
        failure), not a generic 500."""

        async def _fake_arun(framework, profile_dict):
            return {"error": "model timed out"}

        with patch("src.agents.graph.arun_gap_analysis", _fake_arun):
            r = client.post(
                "/api/v1/reports/gap-analysis",
                json={"framework": "CSRD", "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 502
        assert "model timed out" in r.json()["detail"]

    def test_gap_analysis_500_on_generator_failure(self, client, auth_headers, profile):
        """An unexpected error inside PDF generation is masked as a generic 500
        (no internal details leaked to the client)."""

        async def _fake_arun(framework, profile_dict):
            return dict(_GAP_OK)

        gen_instance = MagicMock()
        gen_instance.generate_gap_report.side_effect = RuntimeError("reportlab boom")
        gen_cls = MagicMock(return_value=gen_instance)

        from fastapi.testclient import TestClient

        prod_client = TestClient(client.app, raise_server_exceptions=False)

        with (
            patch("src.agents.graph.arun_gap_analysis", _fake_arun),
            patch("src.reports.generator.ComplianceReportGenerator", gen_cls),
        ):
            r = prod_client.post(
                "/api/v1/reports/gap-analysis",
                json={"framework": "CSRD", "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 500
        assert "internal error" in r.json()["detail"].lower()
        # The raw exception text is NOT leaked.
        assert "reportlab" not in r.json()["detail"].lower()

    def test_gap_analysis_invalid_framework_is_422(self, client, auth_headers, profile):
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "NOT_A_FRAMEWORK", "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_gap_analysis_missing_company_name_is_422(self, client, auth_headers):
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": {"sector": "x"}},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_gap_analysis_empty_company_name_is_422(self, client, auth_headers, profile):
        """CompanyProfile.name has min_length=1, so an empty string is rejected."""
        bad = dict(profile)
        bad["name"] = ""
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD", "company_profile": bad},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_gap_analysis_missing_profile_is_422(self, client, auth_headers):
        r = client.post(
            "/api/v1/reports/gap-analysis",
            json={"framework": "CSRD"},
            headers=auth_headers,
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Executive summary: happy path, validation, all-fail aggregation
# ──────────────────────────────────────────────────────────────────────────


class TestExecutiveSummary:
    def test_executive_summary_happy_path_streams_pdf(self, client, auth_headers, profile):
        pdf_bytes = b"%PDF-1.4 exec summary"

        async def _fake_arun(framework, profile_dict):
            data = dict(_GAP_OK)
            data["framework"] = framework
            return data

        gen_instance = MagicMock()
        gen_instance.generate_executive_summary.return_value = pdf_bytes
        gen_cls = MagicMock(return_value=gen_instance)

        with (
            patch("src.agents.graph.arun_gap_analysis", _fake_arun),
            patch("src.reports.generator.ComplianceReportGenerator", gen_cls),
        ):
            r = client.post(
                "/api/v1/reports/executive-summary",
                json={"frameworks": ["CSRD", "DORA"], "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content == pdf_bytes
        assert "NormaAI_Executive_Summary_Acme_Srl.pdf" in r.headers["content-disposition"]
        # Both requested frameworks were consolidated into the summary.
        _, kwargs = gen_instance.generate_executive_summary.call_args
        assert len(kwargs["frameworks_data"]) == 2

    def test_executive_summary_partial_failure_still_succeeds(self, client, auth_headers, profile):
        """If SOME frameworks fail but at least one succeeds, the report is still
        generated from the successful subset (resilient aggregation)."""
        pdf_bytes = b"%PDF partial"

        async def _fake_arun(framework, profile_dict):
            if framework == "DORA":
                raise RuntimeError("DORA agent crashed")
            return dict(_GAP_OK, framework=framework)

        gen_instance = MagicMock()
        gen_instance.generate_executive_summary.return_value = pdf_bytes
        gen_cls = MagicMock(return_value=gen_instance)

        with (
            patch("src.agents.graph.arun_gap_analysis", _fake_arun),
            patch("src.reports.generator.ComplianceReportGenerator", gen_cls),
        ):
            r = client.post(
                "/api/v1/reports/executive-summary",
                json={"frameworks": ["CSRD", "DORA"], "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 200
        _, kwargs = gen_instance.generate_executive_summary.call_args
        # Only the surviving framework made it into the report.
        assert len(kwargs["frameworks_data"]) == 1

    def test_executive_summary_all_fail_is_502(self, client, auth_headers, profile):
        """When EVERY framework analysis errors, no report can be built -> 502."""

        async def _fake_arun(framework, profile_dict):
            return {"error": f"{framework} failed"}

        with patch("src.agents.graph.arun_gap_analysis", _fake_arun):
            r = client.post(
                "/api/v1/reports/executive-summary",
                json={"frameworks": ["CSRD", "DORA"], "company_profile": profile},
                headers=auth_headers,
            )

        assert r.status_code == 502
        assert "failed" in r.json()["detail"].lower()

    def test_executive_summary_empty_frameworks_is_422(self, client, auth_headers, profile):
        """frameworks has min_length=1 -> an empty list is a validation error."""
        r = client.post(
            "/api/v1/reports/executive-summary",
            json={"frameworks": [], "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_executive_summary_too_many_frameworks_is_422(self, client, auth_headers, profile):
        """frameworks has max_length=8 -> 9 distinct entries is rejected."""
        nine = ["CSRD", "CSDDD", "AI_ACT", "DORA", "NIS2", "TAXONOMY", "GDPR", "CRA", "CSRD"]
        r = client.post(
            "/api/v1/reports/executive-summary",
            json={"frameworks": nine, "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_executive_summary_invalid_framework_is_422(self, client, auth_headers, profile):
        r = client.post(
            "/api/v1/reports/executive-summary",
            json={"frameworks": ["CSRD", "BOGUS"], "company_profile": profile},
            headers=auth_headers,
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  History: happy path, org-scoping, empty org, validation, DB-unavailable
# ──────────────────────────────────────────────────────────────────────────


class TestHistory:
    def test_history_happy_path_returns_items(self, client, auth_headers, org_id):
        rows = [
            _FakeAssessment(framework="CSRD", client_name="Acme Srl", org_id=org_id),
            _FakeAssessment(framework="DORA", client_name="Acme Srl", org_id=org_id),
        ]
        session = _FakeSession(rows=rows, total=2)
        fake_db = _make_fake_db_manager(session)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2
        first = body["data"][0]
        assert first["report_type"] == "gap_analysis"
        assert first["framework"] in {"CSRD", "DORA"}
        assert first["company_name"] == "Acme Srl"
        assert first["overall_score"] == 42.0

    def test_history_scopes_session_to_caller_org(self, client, auth_headers, org_id):
        """The DB session must be opened with the caller's JWT org_id (RLS scope
        / IDOR guard): the org is never taken from client input."""
        session = _FakeSession(rows=[], total=0)
        fake_db = _make_fake_db_manager(session)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 200
        assert fake_db.last_org_id == str(org_id)

    def test_history_empty_org_returns_empty_list(self, client, auth_headers, org_id):
        session = _FakeSession(rows=[], total=0)
        fake_db = _make_fake_db_manager(session)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    def test_history_respects_pagination_params(self, client, auth_headers, org_id):
        session = _FakeSession(rows=[], total=0)
        fake_db = _make_fake_db_manager(session)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = client.get(
                "/api/v1/reports/history?limit=5&offset=10",
                headers=auth_headers,
            )

        assert r.status_code == 200
        pg = r.json()["pagination"]
        assert pg["limit"] == 5
        assert pg["offset"] == 10

    def test_history_limit_too_large_is_422(self, client, auth_headers):
        r = client.get("/api/v1/reports/history?limit=500", headers=auth_headers)
        assert r.status_code == 422

    def test_history_negative_offset_is_422(self, client, auth_headers):
        r = client.get("/api/v1/reports/history?offset=-1", headers=auth_headers)
        assert r.status_code == 422

    def test_history_db_uninitialized_degrades_gracefully(self, client, auth_headers, org_id):
        """A "not initialized" RuntimeError (DB never set up) is handled as an
        empty result with a warning, NOT a 500."""
        session = _RaisingSession(RuntimeError("DatabaseSessionManager is not initialized."))
        fake_db = _make_fake_db_manager(session)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0
        assert "warning" in body

    def test_history_unexpected_error_is_masked_500_json(self, client, auth_headers, org_id):
        """A NON-RuntimeError failure hits the handler's ``except Exception`` and
        is masked behind a generic JSON 500 (no internal details leaked)."""
        session = _RaisingSession(ValueError("secret connection string leaked"))
        fake_db = _make_fake_db_manager(session)

        from fastapi.testclient import TestClient

        prod_client = TestClient(client.app, raise_server_exceptions=False)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = prod_client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 500
        detail = r.json()["detail"]
        assert detail == "Failed to retrieve report history."
        # The raw exception text is NOT leaked to the client.
        assert "secret connection string" not in detail.lower()

    def test_history_generic_runtime_error_escapes_as_plain_500(self, client, auth_headers, org_id):
        """REAL BEHAVIOR (documented, not edited): the handler has

            except RuntimeError as e:
                if "not initialized" in str(e).lower(): return <empty+warning>
                raise   # <-- bare re-raise for any OTHER RuntimeError

        so a generic ``RuntimeError`` (e.g. a live connection drop) is re-raised
        UNCONVERTED. It never reaches the handler's ``except Exception`` masking
        branch, and the framework surfaces it as Starlette's default plain-text
        ``Internal Server Error`` (status 500, body is NOT JSON). The error
        string is logged but not put in the response body."""
        session = _RaisingSession(RuntimeError("connection reset by peer"))
        fake_db = _make_fake_db_manager(session)

        from fastapi.testclient import TestClient

        prod_client = TestClient(client.app, raise_server_exceptions=False)

        with patch("src.db.engine.db_manager", fake_db, create=True):
            r = prod_client.get("/api/v1/reports/history", headers=auth_headers)

        assert r.status_code == 500
        # Plain-text body, not the handler's masked JSON detail.
        assert "connection reset" not in r.text.lower()
