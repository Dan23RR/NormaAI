"""Tests for the system router (src/api/routers/system.py).

Endpoints under test:
- GET /health                     -> liveness probe, ALWAYS 200 (public)
- GET /readyz                     -> readiness probe, 200 ready / 503 not_ready (public)
- GET /api/v1/stats               -> public base shape; admin token adds extra keys
- GET /api/v1/metrics             -> admin only (require_role("admin"))
- GET /api/v1/metrics/prometheus  -> static PROMETHEUS_BEARER_TOKEN OR admin JWT

Coverage goals (asserting REAL behavior read from the source):
- /health is public, 200, and reports qdrant/llm sub-states (never gated on deps).
- /readyz returns 200 + "ready" when deps are up, 503 + "not_ready" when one is down.
- /api/v1/stats works WITHOUT a token (get_optional_user) and exposes the base shape.
- /api/v1/stats with an admin token exposes the admin-only extras (environment,
  llm_provider, llm_model, metrics) and base callers do NOT see them.
- /api/v1/stats reports status="degraded" when a dependency is unavailable.
- /api/v1/stats swallows a Qdrant stats failure (status "unavailable", no 500).
- /api/v1/metrics requires admin (401 no token, 403 member, 200 admin) + shape.
- the prometheus-scrape auth: correct static token (200), incorrect token (401),
  empty/no token (401), and the admin-JWT fallback (200 admin / 403 member).

Pattern notes
-------------
Mirrors test_gdpr_router.py / test_auth_router.py: bare ``TestClient(app)`` (no
lifespan, rate limiting off). The system router takes NO DB session, so there is
nothing to override there - but it reads ``app_state`` (qdrant/llm availability,
indexer) and, for the prometheus endpoint, ``get_settings().prometheus_bearer_token``.
We set ``app_state`` flags on the shared singleton inside the test and patch
``src.api.routers.system.get_settings`` for the bearer-token cases.

Isolation: the ``app_objects`` fixture clears ``app.dependency_overrides`` on
teardown, and an autouse fixture evicts ``src.api.main`` / the router submodules
from ``sys.modules`` after each test (mirroring test_critical_routers.py) so the
REAL ``src.db.engine`` binding cached here never leaks into the sys.modules-patching
isolation used by test_leads / test_api_integration.
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import create_access_token

# ──────────────────────────────────────────────────────────────────────────
#  Module-cache isolation (mirrors test_critical_routers.py / test_auth_router.py)
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
#  App / client fixtures (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked (mirrors
    test_leads.py / test_gdpr_router.py). Yields (app, app_state) and clears
    ``app.dependency_overrides`` on teardown so nothing leaks into sibling files.
    Defaults: both deps available (qdrant + llm up), indexer is a MagicMock."""
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

        app_state.qdrant_available = True
        app_state.llm_available = True
        app_state.indexer = MagicMock()
        limiter.enabled = False

        try:
            yield app, app_state
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    app, _state = app_objects
    return TestClient(app)


@pytest.fixture
def app_state(app_objects):
    _app, state = app_objects
    return state


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


@pytest.fixture
def admin_headers(user_id, org_id):
    token = create_access_token(user_id=user_id, org_id=org_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_headers(user_id, org_id):
    token = create_access_token(user_id=user_id, org_id=org_id, role="member")
    return {"Authorization": f"Bearer {token}"}


def _settings_with_token(token: str):
    """Build a settings stand-in for ``require_scrape_auth`` with a fixed
    prometheus_bearer_token (the only attribute that path reads)."""
    s = MagicMock(name="settings")
    s.prometheus_bearer_token = token
    return s


# ──────────────────────────────────────────────────────────────────────────
#  /health  (public liveness probe)
# ──────────────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_is_public_and_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"

    def test_health_reports_deps_up(self, client, app_state):
        app_state.qdrant_available = True
        app_state.llm_available = True
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["qdrant"] == "up"
        assert body["llm"] == "configured"

    def test_health_stays_200_when_deps_down(self, client, app_state):
        """Liveness must NOT gate on dependencies - a Qdrant outage still 200s,
        otherwise the orchestrator would kill healthy app containers."""
        app_state.qdrant_available = False
        app_state.llm_available = False
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["qdrant"] == "down"
        assert body["llm"] == "missing_key"


# ──────────────────────────────────────────────────────────────────────────
#  /readyz  (public readiness probe, 200 ready / 503 not_ready)
# ──────────────────────────────────────────────────────────────────────────


class TestReadyz:
    def test_readyz_ready_returns_200(self, client, app_state):
        app_state.qdrant_available = True
        app_state.llm_available = True
        app_state.indexer = None  # no seeded indexer -> corpus check defaults ready
        r = client.get("/readyz")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ready"
        assert body["checks"] == {"qdrant": "up", "llm": "up", "corpus": "up"}

    def test_readyz_not_ready_returns_503_when_qdrant_down(self, client, app_state):
        app_state.qdrant_available = False
        app_state.llm_available = True
        r = client.get("/readyz")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["qdrant"] == "down"
        assert body["checks"]["llm"] == "up"

    def test_readyz_not_ready_returns_503_when_llm_down(self, client, app_state):
        app_state.qdrant_available = True
        app_state.llm_available = False
        r = client.get("/readyz")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "not_ready"
        assert body["checks"]["llm"] == "down"

    def test_readyz_not_ready_when_corpus_empty(self, client, app_state):
        # qdrant/llm up but the collection has zero points -> not ready, so the
        # green liveness check can no longer hide an unseeded corpus.
        app_state.qdrant_available = True
        app_state.llm_available = True
        idx = MagicMock()
        idx.get_collection_stats.return_value = {"points_count": 0}
        app_state.indexer = idx
        try:
            r = client.get("/readyz")
            assert r.status_code == 503
            body = r.json()
            assert body["status"] == "not_ready"
            assert body["checks"]["corpus"] == "down"
        finally:
            app_state.indexer = None


# ──────────────────────────────────────────────────────────────────────────
#  /api/v1/stats  (public base shape; admin token adds extras)
# ──────────────────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_public_base_shape(self, client, app_state):
        """No token: get_optional_user yields None, base shape is returned 200."""
        app_state.qdrant_available = True
        app_state.llm_available = True
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ("status", "version", "timestamp", "qdrant_available", "llm_available"):
            assert key in data, f"missing stats key: {key}"
        assert data["status"] == "healthy"
        assert data["version"] == "0.3.0"
        assert data["qdrant_available"] is True
        assert data["llm_available"] is True
        # Anonymous callers must NOT see the admin-only extras.
        for admin_key in ("environment", "llm_provider", "llm_model", "metrics"):
            assert admin_key not in data

    def test_stats_anonymous_no_token_does_not_401(self, client):
        """The endpoint is public (get_optional_user) - missing token is fine."""
        r = client.get("/api/v1/stats")
        assert r.status_code == 200

    def test_stats_degraded_when_dep_unavailable(self, client, app_state):
        app_state.qdrant_available = False
        app_state.llm_available = True
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "degraded"
        assert data["qdrant_available"] is False

    def test_stats_qdrant_unavailable_when_indexer_missing(self, client, app_state):
        """No indexer / qdrant down -> qdrant block is {"status": "unavailable"}."""
        app_state.qdrant_available = False
        app_state.indexer = None
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["qdrant"] == {"status": "unavailable"}

    def test_stats_includes_qdrant_collection_stats(self, client, app_state):
        """When qdrant is up and an indexer exists, its collection stats are inlined."""
        indexer = MagicMock()
        indexer.get_collection_stats.return_value = {"points": 123, "status": "green"}
        app_state.indexer = indexer
        app_state.qdrant_available = True
        app_state.llm_available = True
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["qdrant"] == {"points": 123, "status": "green"}

    def test_stats_swallows_qdrant_stats_failure(self, client, app_state):
        """A get_collection_stats() error must NOT 500: it degrades to
        unavailable and flips the RESPONSE qdrant_available to False.

        Observed behavior (see bug_found in the run report): the overall
        ``status`` is computed from ``app_state.qdrant_available`` (the singleton
        flag), NOT from the local ``stats["qdrant_available"]`` that the except
        block just set to False. So when the live probe flag is still True but
        the per-request stats fetch fails, the response is internally
        inconsistent: ``qdrant_available: False`` yet ``status: "healthy"``."""
        indexer = MagicMock()
        indexer.get_collection_stats.side_effect = RuntimeError("qdrant boom")
        app_state.indexer = indexer
        app_state.qdrant_available = True
        app_state.llm_available = True
        r = client.get("/api/v1/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["qdrant"] == {"status": "unavailable"}
        # The except block overwrites the response-level flag...
        assert data["qdrant_available"] is False
        # ...but the status downgrade reads the (still-True) singleton flag, so
        # the overall status does NOT flip to "degraded" here. This asserts the
        # ACTUAL (arguably buggy) behavior, not the intuitive one.
        assert data["status"] == "healthy"

    def test_stats_admin_token_exposes_extras(self, client, app_state, admin_headers):
        app_state.qdrant_available = True
        app_state.llm_available = True
        r = client.get("/api/v1/stats", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        for admin_key in ("environment", "llm_provider", "llm_model", "metrics"):
            assert admin_key in data, f"admin stats missing key: {admin_key}"
        # The metrics summary has the RequestMetrics shape.
        assert "total_requests" in data["metrics"]
        assert "endpoints" in data["metrics"]
        # In the test environment these reflect the active settings.
        assert data["environment"] == "testing"
        assert data["llm_provider"] == "gemini"

    def test_stats_member_token_does_not_expose_extras(self, client, member_headers):
        """A non-admin authenticated caller gets the public shape only."""
        r = client.get("/api/v1/stats", headers=member_headers)
        assert r.status_code == 200
        data = r.json()
        for admin_key in ("environment", "llm_provider", "llm_model", "metrics"):
            assert admin_key not in data

    def test_stats_invalid_token_falls_back_to_public(self, client):
        """get_optional_user swallows a bad token (401 -> None), so an invalid
        token yields the public shape, not a 401."""
        r = client.get(
            "/api/v1/stats",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "metrics" not in data


# ──────────────────────────────────────────────────────────────────────────
#  /api/v1/metrics  (admin only)
# ──────────────────────────────────────────────────────────────────────────


class TestMetrics:
    def test_metrics_requires_auth(self, client):
        r = client.get("/api/v1/metrics")
        assert r.status_code == 401

    def test_metrics_rejects_invalid_token(self, client):
        r = client.get(
            "/api/v1/metrics",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401

    def test_metrics_forbidden_for_member(self, client, member_headers):
        r = client.get("/api/v1/metrics", headers=member_headers)
        assert r.status_code == 403

    def test_metrics_admin_returns_summary_shape(self, client, admin_headers):
        r = client.get("/api/v1/metrics", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "total_requests" in data
        assert "error_count" in data
        assert "endpoints" in data


# ──────────────────────────────────────────────────────────────────────────
#  /api/v1/metrics/prometheus  (static bearer token OR admin JWT)
# ──────────────────────────────────────────────────────────────────────────


class TestPrometheusScrapeAuth:
    def test_prometheus_no_token_returns_401(self, client):
        """No Authorization header and no static token configured -> 401."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token(""),
        ):
            r = client.get("/api/v1/metrics/prometheus")
        assert r.status_code == 401

    def test_prometheus_correct_static_token_returns_200(self, client):
        secret = "super-secret-scrape-token-123"
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token(secret),
        ):
            r = client.get(
                "/api/v1/metrics/prometheus",
                headers={"Authorization": f"Bearer {secret}"},
            )
        assert r.status_code == 200
        # Prometheus exposition body is text, not JSON.
        assert r.headers["content-type"].startswith("text/plain")

    def test_prometheus_incorrect_static_token_returns_401(self, client):
        """A wrong token does NOT match the static token; with no admin JWT to
        fall back to, the JWT decode fails -> 401 (not 200)."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token("the-real-token"),
        ):
            r = client.get(
                "/api/v1/metrics/prometheus",
                headers={"Authorization": "Bearer the-WRONG-token"},
            )
        assert r.status_code == 401

    def test_prometheus_empty_bearer_returns_401(self, client):
        """An ``Authorization: Bearer`` with an empty credential -> 401."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token("the-real-token"),
        ):
            r = client.get(
                "/api/v1/metrics/prometheus",
                headers={"Authorization": "Bearer "},
            )
        assert r.status_code == 401

    def test_prometheus_admin_jwt_fallback_returns_200(self, client, admin_headers):
        """A human operator with an admin JWT (no static token match) is allowed."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token("unrelated-static-token"),
        ):
            r = client.get("/api/v1/metrics/prometheus", headers=admin_headers)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/plain")

    def test_prometheus_member_jwt_returns_403(self, client, member_headers):
        """A valid but non-admin JWT is rejected by the admin-role fallback."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token("unrelated-static-token"),
        ):
            r = client.get("/api/v1/metrics/prometheus", headers=member_headers)
        assert r.status_code == 403

    def test_prometheus_garbage_jwt_returns_401(self, client):
        """An undecodable token that is not the static token -> JWT path 401."""
        with patch(
            "src.api.routers.system.get_settings",
            return_value=_settings_with_token("the-real-token"),
        ):
            r = client.get(
                "/api/v1/metrics/prometheus",
                headers={"Authorization": "Bearer garbage.jwt.value"},
            )
        assert r.status_code == 401
