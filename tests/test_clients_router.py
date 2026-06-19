"""Tests for the client-management router (src/api/routers/clients.py).

Endpoints under test (mounted at /api/v1/*):
- GET    /api/v1/clients               -> list clients for caller's org (200)
- POST   /api/v1/clients               -> create a client (201)
- GET    /api/v1/clients/{client_id}   -> fetch one client (200 / 404)
- PUT    /api/v1/clients/{client_id}   -> update a client (200 / 404 / 422)
- DELETE /api/v1/clients/{client_id}   -> delete a client (204 / 404)

Coverage goals (asserting REAL behavior read from the source):
- auth required: every endpoint 401s without a token / with a garbage token
- list happy path returns the org's clients serialized via ClientResponse
- create happy path returns 201 + the new client; create validation -> 422
- get happy path (200) and not-found (404)
- update happy path (partial), empty-body -> 422, not-found -> 404
- delete happy path (204) and not-found (404)
- org-scoping / IDOR: the handler scopes the DB session to the caller's JWT
  org_id, and _get_client_or_404 filters on (id, org_id) so a client owned by
  another org is indistinguishable from a missing one (404, never 200).
- path validation: a non-UUID client_id -> 422 (FastAPI uuid coercion).

Pattern notes
-------------
Mirrors tests/test_gdpr_router.py: bare ``TestClient(app)`` (no lifespan, rate
limiting disabled). The clients router does NOT take the DB session via a
FastAPI dependency - it calls ``db_manager.session(org_id=...)`` directly - so
``dependency_overrides`` cannot reach it. Instead we patch
``src.api.routers.clients.db_manager`` with a fake whose ``.session()`` is an
async context manager yielding a fake AsyncSession.

Isolation (mirrors test_critical_routers.py / test_auth_router.py): the
``app_objects`` fixture clears ``app.dependency_overrides`` on teardown, and an
autouse fixture evicts ``src.api.main`` + router modules from ``sys.modules``
after each test, so the REAL ``src.db.engine`` binding cached here never leaks
into the sys.modules-patching isolation used by test_leads / test_api_integration.
"""

from __future__ import annotations

import contextlib
import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────
#  Module-cache isolation (mirrors test_critical_routers.py / test_auth_router.py)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """Importing ``src.api.main`` caches it + the router submodules bound to the
    REAL ``src.db.engine``. test_leads / test_api_integration re-import those
    fresh against a MagicMock engine via sys.modules patching, so we evict the
    modules this file cached to avoid a spurious
    "DatabaseSessionManager is not initialized" in a later test."""
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

    Supports both access shapes the clients router uses:
      - list_clients:        ``.scalars().all()``      (a list of Client rows)
      - _get_client_or_404:  ``.scalar_one_or_none()`` (a single Client or None)
    """

    def __init__(self, *, rows: list | None = None, scalar=None) -> None:
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession used by the clients router.

    ``execute`` returns a pre-seeded result. ``add`` records objects;
    ``commit``/``refresh``/``delete``/``rollback`` are no-ops that record that
    they happened (so org-scoping/commit can be asserted)."""

    def __init__(self, *, result: _FakeResult | None = None) -> None:
        self._result = result or _FakeResult()
        self.added: list = []
        self.deleted: list = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, *_args, **_kwargs):
        return self._result

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        # Real ORM refresh would reload server-side defaults; our Client fixtures
        # already carry created_at/updated_at, so this is a no-op.
        pass

    async def delete(self, obj):
        self.deleted.append(obj)

    async def rollback(self):  # pragma: no cover - not exercised on happy path
        self.rolled_back = True


def _make_fake_db_manager(session: _FakeSession):
    """Build a fake ``db_manager`` whose ``.session(...)`` is an async CM that
    records the org_id it was scoped to (org-scoping proof)."""

    fake = MagicMock(name="fake_db_manager")

    @contextlib.asynccontextmanager
    async def _session(org_id: str | None = None):
        fake.last_org_id = org_id
        yield session

    fake.session = _session
    fake.last_org_id = None
    return fake


def _make_client(org_id: uuid.UUID, *, client_id: uuid.UUID | None = None, name: str = "Acme Srl"):
    """Build a REAL ORM Client so ClientResponse.from_attributes serializes it
    exactly like production. created_at/updated_at are set explicitly because no
    DB round-trip populates the server defaults under the fake session."""
    from src.db.models import Client

    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return Client(
        id=client_id or uuid.uuid4(),
        org_id=org_id,
        name=name,
        sector="Manufacturing",
        employee_count=2500,
        revenue_eur=200_000_000,
        jurisdictions=["IT", "DE"],
        applicable_frameworks=["CSRD", "CSDDD"],
        created_at=now,
        updated_at=now,
    )


# ──────────────────────────────────────────────────────────────────────────
#  App / client fixtures (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked (mirrors
    test_gdpr_router.py). Clears ``app.dependency_overrides`` on teardown so
    nothing leaks into sibling test files."""
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


# ──────────────────────────────────────────────────────────────────────────
#  Auth required
# ──────────────────────────────────────────────────────────────────────────


class TestAuthRequired:
    def test_list_requires_auth(self, client):
        r = client.get("/api/v1/clients")
        assert r.status_code == 401

    def test_create_requires_auth(self, client):
        r = client.post("/api/v1/clients", json={"name": "Acme"})
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        r = client.get(f"/api/v1/clients/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_update_requires_auth(self, client):
        r = client.put(f"/api/v1/clients/{uuid.uuid4()}", json={"name": "New"})
        assert r.status_code == 401

    def test_delete_requires_auth(self, client):
        r = client.delete(f"/api/v1/clients/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_list_rejects_invalid_token(self, client):
        r = client.get("/api/v1/clients", headers={"Authorization": "Bearer not-a-real-token"})
        assert r.status_code == 401

    def test_create_rejects_invalid_token(self, client):
        r = client.post(
            "/api/v1/clients",
            json={"name": "Acme"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
#  List
# ──────────────────────────────────────────────────────────────────────────


class TestList:
    def test_list_happy_path(self, client, auth_headers, org_id):
        c1 = _make_client(org_id, name="Acme Srl")
        c2 = _make_client(org_id, name="Beta SpA")
        session = _FakeSession(result=_FakeResult(rows=[c1, c2]))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get("/api/v1/clients", headers=auth_headers)

        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 2
        names = {row["name"] for row in data}
        assert names == {"Acme Srl", "Beta SpA"}
        # Serialized shape: UUIDs stringified, org_id present.
        assert data[0]["org_id"] == str(org_id)
        assert data[0]["jurisdictions"] == ["IT", "DE"]

    def test_list_empty_returns_empty_list(self, client, auth_headers, org_id):
        session = _FakeSession(result=_FakeResult(rows=[]))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get("/api/v1/clients", headers=auth_headers)

        assert r.status_code == 200
        assert r.json() == []

    def test_list_scopes_session_to_caller_org(self, client, auth_headers, org_id):
        """The DB session is opened with the caller's JWT org_id (RLS scope),
        never an attacker-supplied value (there is no input to supply)."""
        session = _FakeSession(result=_FakeResult(rows=[]))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get("/api/v1/clients", headers=auth_headers)

        assert r.status_code == 200
        assert fake_db.last_org_id == str(org_id)


# ──────────────────────────────────────────────────────────────────────────
#  Create
# ──────────────────────────────────────────────────────────────────────────


class TestCreate:
    def test_create_happy_path(self, client, auth_headers, org_id):
        # The router builds the Client(org_id=user.org_id, ...) itself; refresh is
        # a no-op so created_at/updated_at must already be populated. The router
        # serializes the SAME instance it added, so we pre-stamp it on add().
        captured = {}

        session = _FakeSession()
        original_add = session.add

        def _add(obj):
            now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
            obj.created_at = now
            obj.updated_at = now
            captured["obj"] = obj
            original_add(obj)

        session.add = _add
        fake_db = _make_fake_db_manager(session)

        payload = {
            "name": "Acme Srl",
            "sector": "Manufacturing",
            "employee_count": 2500,
            "revenue_eur": 200_000_000,
            "jurisdictions": ["IT", "DE"],
            "applicable_frameworks": ["CSRD", "CSDDD"],
        }
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.post("/api/v1/clients", json=payload, headers=auth_headers)

        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "Acme Srl"
        # The new client is assigned the caller's org from the JWT, not from input.
        assert data["org_id"] == str(org_id)
        assert data["sector"] == "Manufacturing"
        assert data["jurisdictions"] == ["IT", "DE"]
        # The write was committed and scoped to the caller's org.
        assert session.committed is True
        assert fake_db.last_org_id == str(org_id)
        # The added ORM object carries the caller's org_id (input cannot override).
        assert captured["obj"].org_id == org_id

    def test_create_ignores_client_supplied_org_id(self, client, auth_headers, org_id):
        """An attacker cannot create a client under another org: the payload has
        no org_id field (extra keys are ignored by Pydantic) and the handler
        always uses user.org_id from the JWT."""
        captured = {}
        session = _FakeSession()
        original_add = session.add

        def _add(obj):
            now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
            obj.created_at = now
            obj.updated_at = now
            captured["obj"] = obj
            original_add(obj)

        session.add = _add
        fake_db = _make_fake_db_manager(session)

        attacker_org = str(uuid.uuid4())
        assert attacker_org != str(org_id)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.post(
                "/api/v1/clients",
                json={"name": "Sneaky", "org_id": attacker_org},
                headers=auth_headers,
            )

        assert r.status_code == 201
        assert r.json()["org_id"] == str(org_id)
        assert captured["obj"].org_id == org_id

    def test_create_missing_name_returns_422(self, client, auth_headers):
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.post(
                "/api/v1/clients", json={"sector": "Manufacturing"}, headers=auth_headers
            )
        assert r.status_code == 422

    def test_create_empty_name_returns_422(self, client, auth_headers):
        """name has min_length=1, so an empty string is rejected."""
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.post("/api/v1/clients", json={"name": ""}, headers=auth_headers)
        assert r.status_code == 422

    def test_create_negative_employee_count_returns_422(self, client, auth_headers):
        """employee_count has ge=0."""
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.post(
                "/api/v1/clients",
                json={"name": "Acme", "employee_count": -5},
                headers=auth_headers,
            )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Get (by id)
# ──────────────────────────────────────────────────────────────────────────


class TestGet:
    def test_get_happy_path(self, client, auth_headers, org_id):
        client_id = uuid.uuid4()
        c = _make_client(org_id, client_id=client_id, name="Acme Srl")
        session = _FakeSession(result=_FakeResult(scalar=c))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get(f"/api/v1/clients/{client_id}", headers=auth_headers)

        assert r.status_code == 200
        data = r.json()
        assert data["id"] == str(client_id)
        assert data["org_id"] == str(org_id)
        assert data["name"] == "Acme Srl"

    def test_get_not_found_returns_404(self, client, auth_headers):
        """scalar_one_or_none() is None -> _get_client_or_404 raises 404."""
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get(f"/api/v1/clients/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_get_other_org_client_is_404_not_200(self, client, auth_headers, org_id):
        """IDOR guard: _get_client_or_404 filters on (id, org_id), so a client in
        another org yields no row -> 404 (indistinguishable from missing, no
        information leak). We model this with scalar=None (the WHERE excludes it)."""
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get(f"/api/v1/clients/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        # Session was scoped to the caller's own org for the lookup.
        assert fake_db.last_org_id == str(org_id)

    def test_get_invalid_uuid_returns_422(self, client, auth_headers):
        """client_id is typed uuid.UUID; a non-UUID path param -> 422."""
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.get("/api/v1/clients/not-a-uuid", headers=auth_headers)
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Update
# ──────────────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_happy_path(self, client, auth_headers, org_id):
        client_id = uuid.uuid4()
        c = _make_client(org_id, client_id=client_id, name="Old Name")
        session = _FakeSession(result=_FakeResult(scalar=c))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.put(
                f"/api/v1/clients/{client_id}",
                json={"name": "New Name", "sector": "Energy"},
                headers=auth_headers,
            )

        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "New Name"
        assert data["sector"] == "Energy"
        assert data["id"] == str(client_id)
        # The update was committed.
        assert session.committed is True

    def test_update_empty_body_returns_422(self, client, auth_headers, org_id):
        """The handler raises 422 when model_dump(exclude_unset=True) is empty
        (no fields provided to update)."""
        session = _FakeSession(result=_FakeResult(scalar=_make_client(org_id)))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.put(f"/api/v1/clients/{uuid.uuid4()}", json={}, headers=auth_headers)

        assert r.status_code == 422
        assert "no fields" in r.json()["detail"].lower()

    def test_update_not_found_returns_404(self, client, auth_headers):
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.put(
                f"/api/v1/clients/{uuid.uuid4()}",
                json={"name": "Whatever"},
                headers=auth_headers,
            )

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()

    def test_update_invalid_field_value_returns_422(self, client, auth_headers, org_id):
        """revenue_eur has ge=0; a negative value is rejected before any DB hit."""
        session = _FakeSession(result=_FakeResult(scalar=_make_client(org_id)))
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.put(
                f"/api/v1/clients/{uuid.uuid4()}",
                json={"revenue_eur": -1},
                headers=auth_headers,
            )
        assert r.status_code == 422

    def test_update_scopes_session_to_caller_org(self, client, auth_headers, org_id):
        client_id = uuid.uuid4()
        c = _make_client(org_id, client_id=client_id)
        session = _FakeSession(result=_FakeResult(scalar=c))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.put(
                f"/api/v1/clients/{client_id}",
                json={"name": "Renamed"},
                headers=auth_headers,
            )

        assert r.status_code == 200
        assert fake_db.last_org_id == str(org_id)


# ──────────────────────────────────────────────────────────────────────────
#  Delete
# ──────────────────────────────────────────────────────────────────────────


class TestDelete:
    def test_delete_happy_path_returns_204(self, client, auth_headers, org_id):
        client_id = uuid.uuid4()
        c = _make_client(org_id, client_id=client_id)
        session = _FakeSession(result=_FakeResult(scalar=c))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.delete(f"/api/v1/clients/{client_id}", headers=auth_headers)

        assert r.status_code == 204
        # The client was deleted and the transaction committed.
        assert session.deleted == [c]
        assert session.committed is True

    def test_delete_not_found_returns_404(self, client, auth_headers):
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.delete(f"/api/v1/clients/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        # Nothing was deleted for a non-existent client.
        assert session.deleted == []

    def test_delete_other_org_client_is_404(self, client, auth_headers, org_id):
        """IDOR guard on delete: a client owned by another org is filtered out by
        the (id, org_id) WHERE -> 404, never deleted."""
        session = _FakeSession(result=_FakeResult(scalar=None))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.clients.db_manager", fake_db):
            r = client.delete(f"/api/v1/clients/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        assert session.deleted == []
        assert fake_db.last_org_id == str(org_id)
