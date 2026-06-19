"""Tests for the conversation-history router (src/api/routers/conversations.py).

Endpoints under test:
- GET    /api/v1/conversations                       list (paginated summaries)
- POST   /api/v1/conversations                       create
- GET    /api/v1/conversations/{id}                  get full conversation
- POST   /api/v1/conversations/{id}/messages         add message
- DELETE /api/v1/conversations/{id}                  delete (204)
- GET    /api/v1/conversations/{id}/context          formatted LLM context

Coverage focus (per task brief):
- auth required (401 without token / invalid token)
- happy paths (list, get, create, delete, context)
- pagination bounds (limit/offset -> 422 on out-of-range)
- not-found -> 404 when the conversation does not exist
- IDOR / org-scoping: a user can only read/delete conversations the manager
  returns for THEIR (user_id, org_id); a foreign-org conversation surfaces as
  ``None`` from ``conversation_manager.get_conversation`` -> 404, and the DB
  session is always opened scoped to the caller's JWT org_id.
- message-role validation -> 422

Pattern notes
-------------
Mirrors tests/test_gdpr_router.py: a bare ``TestClient(app)`` (NOT the ``with``
context manager, to skip lifespan), rate limiting disabled. The conversations
router does NOT take its DB session via a FastAPI dependency - it calls
``db_manager.session(org_id=...)`` directly and drives ``conversation_manager``
- so ``dependency_overrides`` cannot reach it. Instead we patch
``src.api.routers.conversations.db_manager`` with a fake whose ``.session()`` is
an async context manager, and ``src.api.routers.conversations.conversation_manager``
with an object whose methods are ``AsyncMock``. Both patches are scoped per-test
(``with patch(...)``), and the app fixture clears ``app.dependency_overrides`` on
teardown, so this file never pollutes sibling test files (e.g. test_leads, which
re-imports the routers against a MagicMock engine).
"""

from __future__ import annotations

import contextlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROUTER = "src.api.routers.conversations"


# ──────────────────────────────────────────────────────────────────────────
#  Fake async DB layer (only ``list_conversations`` and the raw DELETE touch
#  ``session.execute`` directly; everything else goes through the manager).
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)``."""

    def __init__(self, rows: list | None = None) -> None:
        self._rows = rows or []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession.

    ``execute`` returns the configured rows for SELECTs and an empty result for
    writes (DELETE). ``commit``/``rollback``/``close`` are no-ops. The raw rows
    are returned verbatim so ``list_conversations`` indexes them by position.
    """

    def __init__(self, rows: list | None = None) -> None:
        self._rows = rows or []
        self.executed: list[str] = []
        self.committed = False

    async def execute(self, stmt, *args, **kwargs):  # noqa: ANN001
        text = str(stmt)
        self.executed.append(text)
        if text.lstrip().upper().startswith("DELETE"):
            return _FakeResult(rows=[])
        return _FakeResult(rows=self._rows)

    async def commit(self):
        self.committed = True

    async def rollback(self):  # pragma: no cover - not exercised on happy path
        pass

    async def close(self):
        pass


def _make_fake_db_manager(session: _FakeSession):
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


def _make_fake_manager(**method_returns):
    """Build a fake ``conversation_manager`` with AsyncMock methods.

    Pass e.g. ``get_conversation=<dict|None>`` to set return values, or a
    callable/side_effect via ``..._side_effect``.
    """
    mgr = MagicMock(name="fake_conversation_manager")
    for name in (
        "create_conversation",
        "add_message",
        "get_conversation",
        "get_context_for_qa",
    ):
        setattr(mgr, name, AsyncMock(name=name))
    for key, val in method_returns.items():
        if key.endswith("_side_effect"):
            getattr(mgr, key[: -len("_side_effect")]).side_effect = val
        else:
            getattr(mgr, key).return_value = val
    return mgr


def _conv_dict(conv_id, user_id, *, client_id=None, messages=None):
    """A conversation dict in the exact shape ``ConversationManager`` returns."""
    return {
        "id": str(conv_id),
        "user_id": str(user_id),
        "client_id": str(client_id) if client_id else None,
        "messages": messages if messages is not None else [],
        "created_at": "2026-06-01T10:00:00+00:00",
        "updated_at": "2026-06-01T10:05:00+00:00",
    }


# ──────────────────────────────────────────────────────────────────────────
#  TestClient fixture (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked.

    Mirrors the test_gdpr_router.py fixture. Guarantees
    ``app.dependency_overrides`` is cleared on teardown so nothing leaks into
    sibling test files.
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
        r = client.get("/api/v1/conversations")
        assert r.status_code == 401

    def test_get_requires_auth(self, client):
        r = client.get(f"/api/v1/conversations/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_create_requires_auth(self, client):
        r = client.post("/api/v1/conversations", json={})
        assert r.status_code == 401

    def test_delete_requires_auth(self, client):
        r = client.delete(f"/api/v1/conversations/{uuid.uuid4()}")
        assert r.status_code == 401

    def test_add_message_requires_auth(self, client):
        r = client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"role": "user", "content": "hi there"},
        )
        assert r.status_code == 401

    def test_context_requires_auth(self, client):
        r = client.get(f"/api/v1/conversations/{uuid.uuid4()}/context")
        assert r.status_code == 401

    def test_list_rejects_invalid_token(self, client):
        r = client.get(
            "/api/v1/conversations",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
#  LIST: happy path, pagination bounds, org scoping
# ──────────────────────────────────────────────────────────────────────────


class TestListConversations:
    def test_list_happy_path(self, client, auth_headers, user_id):
        import datetime as _dt

        ts = _dt.datetime(2026, 6, 1, 10, 0, 0, tzinfo=_dt.UTC)
        # rows: (id, client_id, user_id, messages, created_at, updated_at)
        rows = [
            (uuid.uuid4(), None, user_id, [{"role": "user", "content": "q"}], ts, ts),
            (uuid.uuid4(), uuid.uuid4(), user_id, [], ts, ts),
        ]
        session = _FakeSession(rows=rows)
        fake_db = _make_fake_db_manager(session)

        with patch(f"{ROUTER}.db_manager", fake_db):
            r = client.get("/api/v1/conversations", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert len(body["data"]) == 2
        # message_count is derived from the messages column length.
        assert body["data"][0]["message_count"] == 1
        assert body["data"][1]["message_count"] == 0
        assert body["data"][0]["user_id"] == str(user_id)

    def test_list_parses_json_string_messages(self, client, auth_headers, user_id):
        """The messages column may arrive as a JSON string; the router json.loads
        it before counting."""
        import datetime as _dt

        ts = _dt.datetime(2026, 6, 1, 10, 0, 0, tzinfo=_dt.UTC)
        rows = [
            (
                uuid.uuid4(),
                None,
                user_id,
                '[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]',
                ts,
                ts,
            ),
        ]
        session = _FakeSession(rows=rows)
        fake_db = _make_fake_db_manager(session)

        with patch(f"{ROUTER}.db_manager", fake_db):
            r = client.get("/api/v1/conversations", headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["data"][0]["message_count"] == 2

    def test_list_empty(self, client, auth_headers):
        session = _FakeSession(rows=[])
        fake_db = _make_fake_db_manager(session)

        with patch(f"{ROUTER}.db_manager", fake_db):
            r = client.get("/api/v1/conversations", headers=auth_headers)

        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_list_scopes_session_to_caller_org(self, client, auth_headers, org_id):
        session = _FakeSession(rows=[])
        fake_db = _make_fake_db_manager(session)

        with patch(f"{ROUTER}.db_manager", fake_db):
            r = client.get("/api/v1/conversations", headers=auth_headers)

        assert r.status_code == 200
        # The DB session was opened scoped to the JWT org (RLS), never client input.
        assert fake_db.last_org_id == str(org_id)

    def test_list_limit_too_high_is_422(self, client, auth_headers):
        r = client.get("/api/v1/conversations?limit=101", headers=auth_headers)
        assert r.status_code == 422

    def test_list_limit_too_low_is_422(self, client, auth_headers):
        r = client.get("/api/v1/conversations?limit=0", headers=auth_headers)
        assert r.status_code == 422

    def test_list_negative_offset_is_422(self, client, auth_headers):
        r = client.get("/api/v1/conversations?offset=-1", headers=auth_headers)
        assert r.status_code == 422

    def test_list_accepts_valid_pagination(self, client, auth_headers):
        session = _FakeSession(rows=[])
        fake_db = _make_fake_db_manager(session)

        with patch(f"{ROUTER}.db_manager", fake_db):
            r = client.get("/api/v1/conversations?limit=50&offset=10", headers=auth_headers)

        assert r.status_code == 200


# ──────────────────────────────────────────────────────────────────────────
#  GET one: happy path, not-found, IDOR / org-scoping
# ──────────────────────────────────────────────────────────────────────────


class TestGetConversation:
    def test_get_happy_path(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        conv = _conv_dict(
            conv_id,
            user_id,
            messages=[
                {
                    "role": "user",
                    "content": "What is CSRD?",
                    "timestamp": "2026-06-01T10:00:00+00:00",
                }
            ],
        )
        mgr = _make_fake_manager(get_conversation=conv)
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["id"] == str(conv_id)
        assert body["data"]["user_id"] == str(user_id)
        assert len(body["data"]["messages"]) == 1
        assert body["data"]["messages"][0]["content"] == "What is CSRD?"

    def test_get_not_found_is_404(self, client, auth_headers):
        """Manager returns None (no such conversation) -> 404."""
        mgr = _make_fake_manager(get_conversation=None)
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        assert r.json()["detail"] == "Conversation not found."

    def test_get_passes_caller_identity_for_ownership(self, client, auth_headers, user_id, org_id):
        """IDOR guard: the handler queries with the caller's OWN user_id and scopes
        the session to the caller's org_id. A foreign conversation can therefore
        never be addressed via someone else's identity."""
        conv_id = uuid.uuid4()
        mgr = _make_fake_manager(get_conversation=_conv_dict(conv_id, user_id))
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(f"/api/v1/conversations/{conv_id}", headers=auth_headers)

        assert r.status_code == 200
        # session scoped to caller org
        assert fake_db.last_org_id == str(org_id)
        # ownership filter uses the caller's user_id from the JWT, not any input
        _args, kwargs = mgr.get_conversation.call_args
        assert kwargs["user_id"] == str(user_id)
        assert kwargs["conversation_id"] == str(conv_id)

    def test_get_foreign_org_conversation_is_404(self, client, auth_headers):
        """IDOR: a conversation belonging to ANOTHER org/user is invisible. The
        manager applies the (user_id) filter and returns None for a row owned by
        someone else -> the endpoint 404s rather than leaking it."""
        mgr = _make_fake_manager(get_conversation=None)  # filtered out by user_id
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────────────
#  CREATE
# ──────────────────────────────────────────────────────────────────────────


class TestCreateConversation:
    def test_create_happy_path_returns_201(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        mgr = _make_fake_manager(
            create_conversation=str(conv_id),
            get_conversation=_conv_dict(conv_id, user_id),
        )
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.post("/api/v1/conversations", json={}, headers=auth_headers)

        assert r.status_code == 201
        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["id"] == str(conv_id)
        # create_conversation was called with the caller's user_id.
        _a, kwargs = mgr.create_conversation.call_args
        assert kwargs["user_id"] == str(user_id)

    def test_create_with_client_id(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        client_id = uuid.uuid4()
        mgr = _make_fake_manager(
            create_conversation=str(conv_id),
            get_conversation=_conv_dict(conv_id, user_id, client_id=client_id),
        )
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.post(
                "/api/v1/conversations",
                json={"client_id": str(client_id)},
                headers=auth_headers,
            )

        assert r.status_code == 201
        _a, kwargs = mgr.create_conversation.call_args
        assert kwargs["client_id"] == str(client_id)

    def test_create_invalid_client_id_is_422(self, client, auth_headers):
        """client_id must be a UUID -> a non-UUID string fails Pydantic validation."""
        r = client.post(
            "/api/v1/conversations",
            json={"client_id": "not-a-uuid"},
            headers=auth_headers,
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  ADD MESSAGE: validation, not-found, happy path
# ──────────────────────────────────────────────────────────────────────────


class TestAddMessage:
    def test_add_message_happy_path(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        # First get_conversation: ownership check; final get_conversation: updated state.
        updated = _conv_dict(
            conv_id,
            user_id,
            messages=[{"role": "user", "content": "hi there"}],
        )
        mgr = _make_fake_manager(get_conversation=updated)
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.post(
                f"/api/v1/conversations/{conv_id}/messages",
                json={"role": "user", "content": "hi there"},
                headers=auth_headers,
            )

        assert r.status_code == 200
        assert r.json()["data"]["messages"][0]["content"] == "hi there"
        mgr.add_message.assert_awaited_once()

    def test_add_message_not_found_is_404(self, client, auth_headers):
        mgr = _make_fake_manager(get_conversation=None)
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.post(
                f"/api/v1/conversations/{uuid.uuid4()}/messages",
                json={"role": "user", "content": "hello"},
                headers=auth_headers,
            )

        assert r.status_code == 404
        # No message was written to a non-existent conversation.
        mgr.add_message.assert_not_awaited()

    def test_add_message_invalid_role_is_422(self, client, auth_headers):
        """role must be 'user' or 'assistant' (field_validator)."""
        r = client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"role": "system", "content": "hello"},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_add_message_empty_content_is_422(self, client, auth_headers):
        """content has min_length=1."""
        r = client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"role": "user", "content": ""},
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_add_message_too_long_content_is_422(self, client, auth_headers):
        """content has max_length=10000."""
        r = client.post(
            f"/api/v1/conversations/{uuid.uuid4()}/messages",
            json={"role": "user", "content": "x" * 10001},
            headers=auth_headers,
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  DELETE: happy path (204), not-found, org-scoping (IDOR)
# ──────────────────────────────────────────────────────────────────────────


class TestDeleteConversation:
    def test_delete_happy_path_204(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        mgr = _make_fake_manager(get_conversation=_conv_dict(conv_id, user_id))
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers)

        assert r.status_code == 204
        # A DELETE statement was issued and committed.
        assert any(s.lstrip().upper().startswith("DELETE") for s in session.executed)
        assert session.committed is True

    def test_delete_not_found_is_404(self, client, auth_headers):
        mgr = _make_fake_manager(get_conversation=None)
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.delete(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        # Ownership failed -> no DELETE statement should have run.
        assert not any(s.lstrip().upper().startswith("DELETE") for s in session.executed)

    def test_delete_foreign_conversation_is_404_no_write(self, client, auth_headers):
        """IDOR: deleting another org/user's conversation. The ownership probe
        (filtered by the caller's user_id) returns None -> 404 BEFORE any DELETE,
        so a caller can never destroy a row they do not own."""
        mgr = _make_fake_manager(get_conversation=None)
        session = _FakeSession()
        fake_db = _make_fake_db_manager(session)

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.delete(f"/api/v1/conversations/{uuid.uuid4()}", headers=auth_headers)

        assert r.status_code == 404
        assert session.committed is False

    def test_delete_scopes_session_to_caller_org(self, client, auth_headers, user_id, org_id):
        conv_id = uuid.uuid4()
        mgr = _make_fake_manager(get_conversation=_conv_dict(conv_id, user_id))
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.delete(f"/api/v1/conversations/{conv_id}", headers=auth_headers)

        assert r.status_code == 204
        assert fake_db.last_org_id == str(org_id)


# ──────────────────────────────────────────────────────────────────────────
#  CONTEXT: happy path, not-found, max_messages bounds
# ──────────────────────────────────────────────────────────────────────────


class TestConversationContext:
    def test_context_happy_path(self, client, auth_headers, user_id):
        conv_id = uuid.uuid4()
        mgr = _make_fake_manager(
            get_conversation=_conv_dict(conv_id, user_id),
            get_context_for_qa="[USER]: hi\n[ASSISTANT]: hello",
        )
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(f"/api/v1/conversations/{conv_id}/context", headers=auth_headers)

        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert body["data"]["context"] == "[USER]: hi\n[ASSISTANT]: hello"

    def test_context_not_found_is_404(self, client, auth_headers):
        mgr = _make_fake_manager(get_conversation=None)
        fake_db = _make_fake_db_manager(_FakeSession())

        with (
            patch(f"{ROUTER}.db_manager", fake_db),
            patch(f"{ROUTER}.conversation_manager", mgr),
        ):
            r = client.get(
                f"/api/v1/conversations/{uuid.uuid4()}/context",
                headers=auth_headers,
            )

        assert r.status_code == 404

    def test_context_max_messages_too_high_is_422(self, client, auth_headers):
        r = client.get(
            f"/api/v1/conversations/{uuid.uuid4()}/context?max_messages=101",
            headers=auth_headers,
        )
        assert r.status_code == 422

    def test_context_max_messages_too_low_is_422(self, client, auth_headers):
        r = client.get(
            f"/api/v1/conversations/{uuid.uuid4()}/context?max_messages=0",
            headers=auth_headers,
        )
        assert r.status_code == 422
