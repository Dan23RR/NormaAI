"""Tests for the GDPR data-subject-rights router (src/api/routers/gdpr.py).

Endpoints under test:
- GET  /api/v1/gdpr/export  (Art. 15 access / Art. 20 portability) - admin only
- POST /api/v1/gdpr/erase   (Art. 17 right to be forgotten) - admin only, confirm-gated

These are compliance-critical, destructive endpoints, so the tests cover:
- auth required (401 without token / invalid token)
- role gate (403 for non-admin members)
- happy path shape (export payload keys, erase confirmation/deleted counts)
- the erase confirmation guard (400 when confirm_org_id != caller org)
- erase request validation (422 when confirm_org_id missing)
- org-scoping: the handler derives org_id from the JWT (user.org_id), never from
  client input, so a caller can only ever export/erase their OWN org's data.
- erase idempotency: a second erase of an already-empty org returns zeroed counts.

Pattern notes
-------------
This uses the same bare ``TestClient(app)`` setup as test_leads.py /
test_api_integration.py (plain TestClient, NOT the ``with`` context manager, to
skip lifespan; rate limiting disabled). The GDPR router does NOT take the DB
session via a FastAPI dependency - it calls ``db_manager.session(org_id=...)``
directly - so a ``dependency_overrides`` injection cannot reach it. Instead we
patch ``src.api.routers.gdpr.db_manager`` with a fake whose ``.session()`` is an
async context manager yielding a fake AsyncSession. The fake DB and the
``app.dependency_overrides`` we set for role tests are both torn down by the
fixtures below so this file does NOT pollute module/global state for other tests
(e.g. test_leads, which re-imports the routers against a MagicMock engine).
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────
#  Fake async DB layer
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)``.

    Supports both access shapes the router uses:
      - SELECT ...  -> ``.scalars().all()``  (rows / id columns)
      - DELETE ...  -> ``.rowcount``         (number of deleted rows)
    """

    def __init__(self, rows: list | None = None, rowcount: int = 0) -> None:
        self._rows = rows or []
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession.

    ``execute`` is dispatched by SQL operation: SELECTs return the configured
    rows, DELETEs return a configured rowcount (defaulting to len(rows) of the
    matching table). ``commit``/``rollback``/``close`` are no-ops.
    """

    def __init__(self, *, rows_by_model: dict, delete_counts: dict | None = None) -> None:
        # rows_by_model: {"User": [...], "Client": [...], ...}
        self._rows_by_model = rows_by_model
        self._delete_counts = delete_counts or {}
        self.deleted_models: list[str] = []
        self.committed = False

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN001
        text = str(stmt)
        if text.lstrip().upper().startswith("DELETE"):
            model = _model_from_sql(text)
            self.deleted_models.append(model)
            count = self._delete_counts.get(model, len(self._rows_by_model.get(model, [])))
            return _FakeResult(rowcount=count)
        # SELECT
        model = _model_from_sql(text)
        return _FakeResult(rows=self._rows_by_model.get(model, []))

    async def commit(self):
        self.committed = True

    async def rollback(self):  # pragma: no cover - not exercised on happy path
        pass

    async def close(self):
        pass


def _model_from_sql(sql_text: str) -> str:
    """Map a rendered SQL string to the logical model key used in our fakes.

    The router's statements each touch exactly one target table name (the
    foreign-key columns are ``client_id`` / ``user_id``, which do NOT contain the
    plural table substrings), so a simple table-name scan is unambiguous.
    """
    lowered = sql_text.lower()
    for table, key in (
        ("conversations", "Conversation"),
        ("assessments", "Assessment"),
        ("clients", "Client"),
        ("alerts", "Alert"),
        ("users", "User"),
    ):
        if table in lowered:
            return key
    return "Unknown"


def _make_fake_db_manager(session: _FakeSession):
    """Build a fake ``db_manager`` whose ``.session(...)`` is an async CM."""

    fake = MagicMock(name="fake_db_manager")

    @contextlib.asynccontextmanager
    async def _session(org_id: str | None = None):  # noqa: ANN001
        # record the org_id the router scoped the session to (org-scoping proof)
        fake.last_org_id = org_id
        yield session

    fake.session = _session
    fake.last_org_id = None
    return fake


# ──────────────────────────────────────────────────────────────────────────
#  TestClient fixture (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked.

    Mirrors the test_leads.py fixture. Yields (app, app_state, limiter) and
    guarantees ``app.dependency_overrides`` is cleared on teardown so role-test
    overrides never leak into sibling test files.
    """
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
            # Critical: never leave overrides set for other test files.
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
def admin_headers(user_id, org_id):
    from src.auth.security import create_access_token

    token = create_access_token(user_id=user_id, org_id=org_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def member_headers(user_id, org_id):
    from src.auth.security import create_access_token

    token = create_access_token(user_id=user_id, org_id=org_id, role="member")
    return {"Authorization": f"Bearer {token}"}


# ──────────────────────────────────────────────────────────────────────────
#  Auth / role gating
# ──────────────────────────────────────────────────────────────────────────


class TestAuthRequired:
    def test_export_requires_auth(self, client):
        r = client.get("/api/v1/gdpr/export")
        assert r.status_code == 401

    def test_erase_requires_auth(self, client):
        r = client.post("/api/v1/gdpr/erase", json={"confirm_org_id": str(uuid.uuid4())})
        assert r.status_code == 401

    def test_export_rejects_invalid_token(self, client):
        r = client.get(
            "/api/v1/gdpr/export",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401

    def test_erase_rejects_invalid_token(self, client):
        r = client.post(
            "/api/v1/gdpr/erase",
            json={"confirm_org_id": str(uuid.uuid4())},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401

    def test_export_forbidden_for_member(self, client, member_headers):
        """require_role('admin') must 403 a non-admin (member) token."""
        r = client.get("/api/v1/gdpr/export", headers=member_headers)
        assert r.status_code == 403

    def test_erase_forbidden_for_member(self, client, member_headers, org_id):
        r = client.post(
            "/api/v1/gdpr/erase",
            json={"confirm_org_id": str(org_id)},
            headers=member_headers,
        )
        assert r.status_code == 403


# ──────────────────────────────────────────────────────────────────────────
#  Export happy path + payload shape + org scoping
# ──────────────────────────────────────────────────────────────────────────


def _real_rows(org_id, user_id):
    """Build REAL ORM instances so ``_row_to_dict`` (which uses sqlalchemy
    inspect) serializes them exactly like production."""
    from src.db.models import Alert, Assessment, Client, Conversation, User

    u = User(id=user_id, org_id=org_id, email="admin@acme.test", name="Admin", role="admin")
    c = Client(id=uuid.uuid4(), org_id=org_id, name="Acme Client")
    conv = Conversation(id=uuid.uuid4(), user_id=user_id, client_id=c.id, messages=[])
    a = Assessment(id=uuid.uuid4(), client_id=c.id, framework="CSRD", overall_score=42.0)
    al = Alert(
        id=uuid.uuid4(),
        client_id=c.id,
        severity="HIGH",
        framework="CSRD",
        title="t",
        description="d",
    )
    return {
        "User": [u],
        "Client": [c],
        "Conversation": [conv],
        "Assessment": [a],
        "Alert": [al],
    }


class TestExport:
    def test_export_happy_path_shape(self, client, admin_headers, org_id, user_id):
        rows = _real_rows(org_id, user_id)
        session = _FakeSession(rows_by_model=rows)
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.get("/api/v1/gdpr/export", headers=admin_headers)

        assert r.status_code == 200
        data = r.json()
        # The export envelope must expose every data category for portability.
        for key in (
            "org_id",
            "exported_at",
            "users",
            "clients",
            "conversations",
            "assessments",
            "alerts",
        ):
            assert key in data, f"missing export key: {key}"

        # org_id in the payload is the caller's JWT org (org-scoping), as a str.
        assert data["org_id"] == str(org_id)
        # Lists are populated from the (fake) DB rows.
        assert len(data["users"]) == 1
        assert len(data["clients"]) == 1
        assert len(data["conversations"]) == 1
        assert len(data["assessments"]) == 1
        assert len(data["alerts"]) == 1
        # Row serialization: UUIDs are stringified, columns preserved.
        assert data["users"][0]["email"] == "admin@acme.test"
        assert data["users"][0]["org_id"] == str(org_id)

    def test_export_scopes_session_to_caller_org(self, client, admin_headers, org_id, user_id):
        """The DB session must be opened with the caller's org_id (RLS scope),
        never an attacker-supplied value (there is no input to supply)."""
        session = _FakeSession(rows_by_model=_real_rows(org_id, user_id))
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.get("/api/v1/gdpr/export", headers=admin_headers)

        assert r.status_code == 200
        assert fake_db.last_org_id == str(org_id)

    def test_export_empty_org_returns_empty_lists(self, client, admin_headers, org_id):
        """An org with no users/clients yields empty collections, not an error,
        and short-circuits the dependent queries (user_ids/client_ids empty)."""
        session = _FakeSession(rows_by_model={})  # nothing for any model
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.get("/api/v1/gdpr/export", headers=admin_headers)

        assert r.status_code == 200
        data = r.json()
        assert data["users"] == []
        assert data["clients"] == []
        assert data["conversations"] == []
        assert data["assessments"] == []
        assert data["alerts"] == []


# ──────────────────────────────────────────────────────────────────────────
#  Erase: confirmation guard, happy path, idempotency, org scoping
# ──────────────────────────────────────────────────────────────────────────


class TestEraseValidation:
    def test_erase_missing_confirm_field_is_422(self, client, admin_headers):
        """ErasureRequest.confirm_org_id is required -> Pydantic 422."""
        r = client.post("/api/v1/gdpr/erase", json={}, headers=admin_headers)
        assert r.status_code == 422

    def test_erase_wrong_confirm_org_is_400(self, client, admin_headers, org_id):
        """Confirmation guard: confirm_org_id must equal the caller's org_id.

        This is the destructive-action safety gate AND the IDOR guard: passing a
        DIFFERENT org's id (an attempt to erase someone else's data) is rejected
        before any DB write."""
        other_org = str(uuid.uuid4())
        assert other_org != str(org_id)

        # db_manager must NOT be touched on the 400 path; if it is, the fake's
        # async CM would still work, but we assert no delete happened.
        session = _FakeSession(rows_by_model={})
        fake_db = _make_fake_db_manager(session)
        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.post(
                "/api/v1/gdpr/erase",
                json={"confirm_org_id": other_org},
                headers=admin_headers,
            )

        assert r.status_code == 400
        assert "confirm_org_id" in r.json()["detail"]
        # No deletion was performed for the mismatched confirmation.
        assert session.deleted_models == []


class TestEraseHappyPath:
    def test_erase_success_returns_deleted_counts(self, client, admin_headers, org_id, user_id):
        client_id = uuid.uuid4()
        rows = {
            # erase reads Client.id and User.id (scalars of id columns)
            "Client": [client_id],
            "User": [user_id],
        }
        delete_counts = {
            "Assessment": 3,
            "Alert": 2,
            "Conversation": 4,
            "Client": 1,
        }
        session = _FakeSession(rows_by_model=rows, delete_counts=delete_counts)
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.post(
                "/api/v1/gdpr/erase",
                json={"confirm_org_id": str(org_id)},
                headers=admin_headers,
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "erased"
        assert data["org_id"] == str(org_id)
        assert data["deleted"] == {
            "assessments": 3,
            "alerts": 2,
            "conversations": 4,
            "clients": 1,
        }
        # The session was committed (writes are durable, not rolled back).
        assert session.committed is True
        # Session scoped to the caller's org for RLS.
        assert fake_db.last_org_id == str(org_id)

    def test_erase_purges_org_chunks_from_vector_store(
        self, client, app_objects, admin_headers, org_id, user_id
    ):
        """Art. 17 erasure must also remove the org's uploaded vector chunks."""
        _app, app_state, _limiter = app_objects
        indexer = MagicMock()
        app_state.indexer = indexer

        session = _FakeSession(rows_by_model={"Client": [uuid.uuid4()], "User": [user_id]})
        fake_db = _make_fake_db_manager(session)

        # The router imports app_state from src.api.app_state lazily inside the
        # handler; patch that module's singleton so our indexer is the one used.
        with (
            patch("src.api.routers.gdpr.db_manager", fake_db),
            patch("src.api.app_state.app_state", app_state),
        ):
            r = client.post(
                "/api/v1/gdpr/erase",
                json={"confirm_org_id": str(org_id)},
                headers=admin_headers,
            )

        assert r.status_code == 200
        indexer.delete_org_chunks.assert_called_once_with(str(org_id))

    def test_erase_vector_store_failure_does_not_break_response(
        self, client, app_objects, admin_headers, org_id, user_id
    ):
        """Vector-store erasure is best-effort: a Qdrant error is swallowed and
        the DB erasure result is still returned 200."""
        _app, app_state, _limiter = app_objects
        indexer = MagicMock()
        indexer.delete_org_chunks.side_effect = RuntimeError("qdrant down")
        app_state.indexer = indexer

        session = _FakeSession(rows_by_model={"Client": [uuid.uuid4()], "User": [user_id]})
        fake_db = _make_fake_db_manager(session)

        with (
            patch("src.api.routers.gdpr.db_manager", fake_db),
            patch("src.api.app_state.app_state", app_state),
        ):
            r = client.post(
                "/api/v1/gdpr/erase",
                json={"confirm_org_id": str(org_id)},
                headers=admin_headers,
            )

        assert r.status_code == 200
        assert r.json()["status"] == "erased"

    def test_erase_idempotent_on_empty_org(self, client, admin_headers, org_id):
        """Erasing an already-empty org is a no-op that still returns 200 with
        zeroed counts (idempotency: a re-run after a prior erase is safe)."""
        session = _FakeSession(rows_by_model={})  # no clients, no users
        fake_db = _make_fake_db_manager(session)

        with patch("src.api.routers.gdpr.db_manager", fake_db):
            r = client.post(
                "/api/v1/gdpr/erase",
                json={"confirm_org_id": str(org_id)},
                headers=admin_headers,
            )

        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "erased"
        assert data["deleted"] == {
            "clients": 0,
            "conversations": 0,
            "assessments": 0,
            "alerts": 0,
        }
        # With no client_ids and no user_ids, only the Client delete runs.
        assert "Assessment" not in session.deleted_models
        assert "Alert" not in session.deleted_models
        assert "Conversation" not in session.deleted_models
