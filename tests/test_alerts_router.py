"""Tests for the alerts router (src/api/routers/alerts.py).

Endpoints under test (mounted at /api/v1/*):
- GET   /api/v1/alerts/summary           -> dashboard counts (200)
- GET   /api/v1/alerts                    -> paginated list, X-Unread-Count header (200)
- GET   /api/v1/alerts/{id}               -> single alert (200 / 404)
- POST  /api/v1/alerts                    -> create (201 / 404 / 422)
- PATCH /api/v1/alerts/{id}/read          -> mark read (200 / 404)
- PATCH /api/v1/alerts/{id}/dismiss       -> dismiss (200 / 404)

Coverage goals (asserting REAL behavior read from the source):
- auth required (401 without token / invalid token) on every endpoint
- list happy path + pagination echo + X-Unread-Count header
- get-by-id happy path + 404 for an alert outside the caller's org (IDOR guard)
- create happy path (201) + create against a client in ANOTHER org -> 404 (IDOR)
- create validation: missing required fields / blank title / bad UUID -> 422
- mark-read / dismiss happy paths + 404 for a foreign alert (IDOR)
- malformed path UUID -> 422
- org-scoping: db_manager.session(org_id=...) is always opened with the caller's
  JWT org_id (RLS scope), never client-supplied input.

Pattern notes
-------------
The alerts router does NOT take the DB session via a FastAPI dependency - it calls
``db_manager.session(org_id=...)`` directly inside each handler - so an
``app.dependency_overrides`` injection cannot reach it. Following
tests/test_gdpr_router.py, we patch ``src.api.routers.alerts.db_manager`` with a
fake whose ``.session(...)`` is an ``@asynccontextmanager`` yielding a fake
AsyncSession. NO real DB (test.db) is touched, so this file is safe to run in
parallel with other router test files.

Isolation: this file imports ``src.api.main`` like test_leads.py /
test_gdpr_router.py / test_auth_router.py (bare ``TestClient(app)``, no lifespan,
rate limiting off). The ``app_objects`` fixture clears
``app.dependency_overrides`` on teardown, and an autouse fixture evicts the
``src.api.main`` / router modules from ``sys.modules`` after each test (mirroring
test_critical_routers.py) so the REAL ``src.db.engine`` binding cached here never
leaks into the sys.modules-patching isolation used by test_leads.
"""

from __future__ import annotations

import contextlib
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

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
#  Fake async DB layer
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)``.

    Supports the three access shapes the alerts router uses:
      - count queries:                 ``.scalar()``           (an int)
      - _verify_client_org/_get_alert: ``.scalar_one_or_none()`` (a row or None)
      - list data query:               ``.scalars().all()``    (a list of rows)
      - summary group-by:              ``.all()``              (rows w/ attrs)
    """

    def __init__(self, *, scalar=None, scalar_one=None, rows=None, group_rows=None):
        self._scalar = scalar
        self._scalar_one = scalar_one
        self._rows = rows if rows is not None else []
        self._group_rows = group_rows if group_rows is not None else []

    def scalar(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        return self

    def all(self):
        # ``.scalars().all()`` (list rows) AND group-by ``.all()`` share this
        # object; the router never mixes both on one statement, so return whatever
        # was seeded. group_rows wins when present.
        return list(self._group_rows) if self._group_rows else list(self._rows)


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession.

    ``execute`` is dispatched by the rendered SQL so each handler's distinct
    statements get the right pre-seeded result. ``add``/``commit``/``refresh``
    are recorded no-ops. Configure via the keyword fields below.
    """

    def __init__(
        self,
        *,
        client=None,  # row returned by _verify_client_org (SELECT FROM clients)
        alert=None,  # row returned by _get_alert_for_org (SELECT alerts JOIN clients)
        list_rows=None,  # rows for the list data query
        total=0,  # list/summary total count
        unread=0,  # unread count
        severity_rows=None,  # summary group-by severity rows
        framework_rows=None,  # summary group-by framework rows
    ):
        self._client = client
        self._alert = alert
        self._list_rows = list_rows if list_rows is not None else []
        self._total = total
        self._unread = unread
        self._severity_rows = severity_rows if severity_rows is not None else []
        self._framework_rows = framework_rows if framework_rows is not None else []

        self.added: list = []
        self.committed = False
        self.refreshed: list = []
        self._count_calls = 0

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN001
        # Collapse whitespace (SQLAlchemy renders multi-line statements) so the
        # substring matching below does not depend on newline placement.
        text = " ".join(str(stmt).lower().split())

        # COUNT queries: list uses two (total then unread), summary uses two
        # (total then unread) plus group-bys. Distinguish by call order for the
        # two scalar counts.
        if "count(" in text and "group by" not in text:
            self._count_calls += 1
            # First count seen in a handler is the "total", second is "unread".
            value = self._total if self._count_calls == 1 else self._unread
            return _FakeResult(scalar=value)

        # Summary group-by aggregates.
        if "group by" in text:
            if "group by alerts.severity" in text:
                return _FakeResult(group_rows=self._severity_rows)
            if "group by alerts.framework" in text:
                return _FakeResult(group_rows=self._framework_rows)
            return _FakeResult(group_rows=[])

        # _verify_client_org: SELECT ... FROM clients (no join to alerts).
        if "from clients" in text and "from alerts" not in text:
            return _FakeResult(scalar_one=self._client)

        # _get_alert_for_org: SELECT alerts ... JOIN clients ... (single row).
        if "from alerts" in text and "limit" not in text and "count(" not in text:
            return _FakeResult(scalar_one=self._alert)

        # list data query: SELECT alerts ... ORDER BY ... LIMIT ... OFFSET.
        if "from alerts" in text and "limit" in text:
            return _FakeResult(rows=self._list_rows)

        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, obj):
        # A real commit+refresh populates server-default columns (created_at).
        # Mirror that so AlertResponse.model_validate (which requires a non-null
        # created_at) succeeds on the freshly inserted row.
        from datetime import UTC, datetime

        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 6, 1, tzinfo=UTC)
        self.refreshed.append(obj)

    async def close(self):
        pass


def _make_fake_db_manager(session: _FakeSession):
    """Build a fake ``db_manager`` whose ``.session(...)`` is an async CM and
    records the org_id it was scoped to (org-scoping / RLS proof)."""
    fake = MagicMock(name="fake_db_manager")

    @contextlib.asynccontextmanager
    async def _session(org_id: str | None = None):  # noqa: ANN001
        fake.last_org_id = org_id
        yield session

    fake.session = _session
    fake.last_org_id = None
    return fake


def _make_alert(*, client_id=None, alert_id=None, **overrides):
    """Build a REAL Alert ORM instance so AlertResponse.model_validate serializes
    it exactly like production (from_attributes)."""
    from src.db.models import Alert

    fields = dict(
        id=alert_id or uuid.uuid4(),
        client_id=client_id or uuid.uuid4(),
        regulation_id=None,
        severity="HIGH",
        framework="CSRD",
        title="Quarterly CSRD deadline approaching",
        description="Submit double-materiality report.",
        actions_required=["Prepare report"],
        deadline=None,
        is_read=False,
        is_dismissed=False,
    )
    fields.update(overrides)
    # created_at has a server_default; AlertResponse requires it, so set it.
    from datetime import UTC, datetime

    fields.setdefault("created_at", datetime(2026, 6, 1, tzinfo=UTC))
    return Alert(**fields)


def _make_client(*, org_id, client_id=None):
    from src.db.models import Client

    return Client(id=client_id or uuid.uuid4(), org_id=org_id, name="Acme Client")


# ──────────────────────────────────────────────────────────────────────────
#  App / client fixtures (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked (mirrors
    test_gdpr_router.py). Clears ``app.dependency_overrides`` on teardown."""
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
def patch_db():
    """Helper: patch the alerts router's db_manager with a fake for one request."""

    @contextlib.contextmanager
    def _apply(session: _FakeSession):
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.alerts.db_manager", fake_db):
            yield fake_db

    return _apply


# ──────────────────────────────────────────────────────────────────────────
#  Auth required
# ──────────────────────────────────────────────────────────────────────────


class TestAuthRequired:
    def test_list_requires_auth(self, client):
        assert client.get("/api/v1/alerts").status_code == 401

    def test_summary_requires_auth(self, client):
        assert client.get("/api/v1/alerts/summary").status_code == 401

    def test_get_requires_auth(self, client):
        assert client.get(f"/api/v1/alerts/{uuid.uuid4()}").status_code == 401

    def test_create_requires_auth(self, client):
        r = client.post(
            "/api/v1/alerts",
            json={
                "client_id": str(uuid.uuid4()),
                "severity": "HIGH",
                "framework": "CSRD",
                "title": "x",
            },
        )
        assert r.status_code == 401

    def test_mark_read_requires_auth(self, client):
        assert client.patch(f"/api/v1/alerts/{uuid.uuid4()}/read").status_code == 401

    def test_dismiss_requires_auth(self, client):
        assert client.patch(f"/api/v1/alerts/{uuid.uuid4()}/dismiss").status_code == 401

    def test_list_rejects_invalid_token(self, client):
        r = client.get("/api/v1/alerts", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
#  List
# ──────────────────────────────────────────────────────────────────────────


class TestListAlerts:
    def test_list_happy_path(self, client, auth_headers, org_id):
        a1 = _make_alert(severity="CRITICAL")
        a2 = _make_alert(severity="LOW")
        session = _FakeSession(list_rows=[a1, a2], total=2, unread=1)

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.get("/api/v1/alerts", headers=auth_headers)
            # Session scoped to the caller's JWT org (RLS), as a str.
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 2
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert len(body["alerts"]) == 2
        # Unread count is surfaced in the response header.
        assert r.headers["X-Unread-Count"] == "1"

    def test_list_echoes_pagination_params(self, client, auth_headers):
        session = _FakeSession(list_rows=[], total=0, unread=0)
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get("/api/v1/alerts?limit=10&offset=5", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["limit"] == 10
        assert body["offset"] == 5
        assert body["alerts"] == []

    def test_list_limit_over_max_is_422(self, client, auth_headers):
        # limit has le=200; 999 must be rejected by query validation.
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get("/api/v1/alerts?limit=999", headers=auth_headers)
        assert r.status_code == 422

    def test_list_negative_offset_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get("/api/v1/alerts?offset=-1", headers=auth_headers)
        assert r.status_code == 422

    def test_list_bad_severity_filter_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get("/api/v1/alerts?severity=NOPE", headers=auth_headers)
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Get by id  (incl. IDOR / org-scoping)
# ──────────────────────────────────────────────────────────────────────────


class TestGetAlert:
    def test_get_happy_path(self, client, auth_headers, org_id):
        alert_id = uuid.uuid4()
        alert = _make_alert(alert_id=alert_id, title="Specific alert")
        session = _FakeSession(alert=alert)

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.get(f"/api/v1/alerts/{alert_id}", headers=auth_headers)
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == str(alert_id)
        assert body["title"] == "Specific alert"

    def test_get_foreign_alert_returns_404(self, client, auth_headers):
        # _get_alert_for_org joins Client on org_id; an alert in ANOTHER org is
        # invisible to the query, which yields None -> 404 (the IDOR guard).
        session = _FakeSession(alert=None)
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get(f"/api/v1/alerts/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_get_malformed_uuid_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.get("/api/v1/alerts/not-a-uuid", headers=auth_headers)
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Create  (happy path, IDOR via foreign client, validation)
# ──────────────────────────────────────────────────────────────────────────


def _create_payload(client_id):
    return {
        "client_id": str(client_id),
        "severity": "HIGH",
        "framework": "CSRD",
        "title": "New CSRD obligation detected",
        "description": "A new reporting requirement applies.",
        "actions_required": ["Review", "Assign owner"],
    }


class TestCreateAlert:
    def test_create_happy_path_returns_201(self, client, auth_headers, org_id):
        client_id = uuid.uuid4()
        owned_client = _make_client(org_id=org_id, client_id=client_id)
        session = _FakeSession(client=owned_client)

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.post("/api/v1/alerts", json=_create_payload(client_id), headers=auth_headers)
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 201
        body = r.json()
        assert body["title"] == "New CSRD obligation detected"
        assert body["severity"] == "HIGH"
        assert body["framework"] == "CSRD"
        assert body["client_id"] == str(client_id)
        assert body["is_read"] is False
        assert body["is_dismissed"] is False
        # The handler persisted the new alert.
        assert len(session.added) == 1
        assert session.committed is True

    def test_create_foreign_client_returns_404(self, client, auth_headers):
        # _verify_client_org filters Client by (id, org_id); a client in another
        # org is not found -> 404 BEFORE any insert (IDOR guard on create).
        session = _FakeSession(client=None)
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts", json=_create_payload(uuid.uuid4()), headers=auth_headers
            )

        assert r.status_code == 404
        assert "client not found" in r.json()["detail"].lower()
        # No alert was added when client ownership check failed.
        assert session.added == []
        assert session.committed is False

    def test_create_missing_client_id_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts",
                json={"severity": "HIGH", "framework": "CSRD", "title": "x"},
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_create_blank_title_is_422(self, client, auth_headers):
        # title has min_length=1; an empty string must be rejected.
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts",
                json={
                    "client_id": str(uuid.uuid4()),
                    "severity": "HIGH",
                    "framework": "CSRD",
                    "title": "",
                },
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_create_bad_severity_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts",
                json={
                    "client_id": str(uuid.uuid4()),
                    "severity": "URGENT",  # not a SeverityEnum member
                    "framework": "CSRD",
                    "title": "x",
                },
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_create_bad_framework_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts",
                json={
                    "client_id": str(uuid.uuid4()),
                    "severity": "HIGH",
                    "framework": "SOX",  # not a FrameworkEnum member
                    "title": "x",
                },
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_create_bad_client_id_uuid_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.post(
                "/api/v1/alerts",
                json={
                    "client_id": "not-a-uuid",
                    "severity": "HIGH",
                    "framework": "CSRD",
                    "title": "x",
                },
                headers=auth_headers,
            )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Mark read / dismiss  (happy path, IDOR 404)
# ──────────────────────────────────────────────────────────────────────────


class TestMarkRead:
    def test_mark_read_happy_path(self, client, auth_headers, org_id):
        alert_id = uuid.uuid4()
        alert = _make_alert(alert_id=alert_id, is_read=False)
        session = _FakeSession(alert=alert)

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.patch(f"/api/v1/alerts/{alert_id}/read", headers=auth_headers)
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == str(alert_id)
        assert body["is_read"] is True
        assert session.committed is True

    def test_mark_read_foreign_alert_returns_404(self, client, auth_headers):
        session = _FakeSession(alert=None)
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.patch(f"/api/v1/alerts/{uuid.uuid4()}/read", headers=auth_headers)
        assert r.status_code == 404
        # Nothing committed when the alert is not in the caller's org.
        assert session.committed is False

    def test_mark_read_malformed_uuid_is_422(self, client, auth_headers):
        session = _FakeSession()
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.patch("/api/v1/alerts/nope/read", headers=auth_headers)
        assert r.status_code == 422


class TestDismiss:
    def test_dismiss_happy_path(self, client, auth_headers, org_id):
        alert_id = uuid.uuid4()
        alert = _make_alert(alert_id=alert_id, is_read=False, is_dismissed=False)
        session = _FakeSession(alert=alert)

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.patch(f"/api/v1/alerts/{alert_id}/dismiss", headers=auth_headers)
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 200
        body = r.json()
        assert body["is_dismissed"] is True
        # Dismissing also marks the alert read (source sets both).
        assert body["is_read"] is True
        assert session.committed is True

    def test_dismiss_foreign_alert_returns_404(self, client, auth_headers):
        session = _FakeSession(alert=None)
        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)):
            r = client.patch(f"/api/v1/alerts/{uuid.uuid4()}/dismiss", headers=auth_headers)
        assert r.status_code == 404
        assert session.committed is False


# ──────────────────────────────────────────────────────────────────────────
#  Summary
# ──────────────────────────────────────────────────────────────────────────


class TestSummary:
    def test_summary_happy_path(self, client, auth_headers, org_id):
        sev_rows = [
            MagicMock(severity="CRITICAL", count=3),
            MagicMock(severity="LOW", count=1),
        ]
        fw_rows = [MagicMock(framework="CSRD", count=4)]
        session = _FakeSession(
            total=4,
            unread=2,
            severity_rows=sev_rows,
            framework_rows=fw_rows,
        )

        with patch("src.api.routers.alerts.db_manager", _make_fake_db_manager(session)) as fake_db:
            r = client.get("/api/v1/alerts/summary", headers=auth_headers)
            assert fake_db.last_org_id == str(org_id)

        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 4
        assert body["total_unread"] == 2
        assert {c["severity"] for c in body["by_severity"]} == {"CRITICAL", "LOW"}
        assert body["by_framework"][0]["framework"] == "CSRD"
        assert body["by_framework"][0]["count"] == 4
