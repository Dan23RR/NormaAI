"""Tests for the conversation-persistence SERVICE (src/conversations.py).

Target under test: ``ConversationManager`` and the module-level
``conversation_manager`` singleton. This is the persistence layer that the
conversations router drives - the router itself is covered by
tests/test_conversations_router.py, so here we exercise the service methods
DIRECTLY against a fake ``AsyncSession``.

Why no real DB / no app import
------------------------------
``ConversationManager`` takes the SQLAlchemy ``AsyncSession`` as an explicit
argument on every method (it does NOT reach for a module-level ``db_manager`` -
there is none in src/conversations.py), so the cleanest, fully parallel-safe way
to test it is to pass a hand-rolled fake session. We therefore never touch the
shared sqlite ``test.db`` and never import the FastAPI app, so this file cannot
pollute module/global state for the other test files running concurrently.

The fake session captures every ``execute(stmt, params)`` call so the tests can
assert on the rendered SQL (INSERT / UPDATE / SELECT) and the bound parameters
(the real behaviour: which columns get written, that an empty messages array is
seeded, that metadata is only attached when supplied, that the user_id ownership
filter is bound, etc.). For SELECTs the fake returns a configured row so the
serialization branches in ``get_conversation`` are covered.

Coverage focus:
- create_conversation: returns a fresh UUID, INSERTs with the right params, commits
- add_message: message shape (role/content/timestamp), metadata gating, UPDATE, commit
- get_conversation: None on no row; UUID stringification; messages parsed from a
  JSON string OR passed through as a dict/list; None client_id; None created_at;
  the user_id ownership filter is bound into the params
- get_context_for_qa: empty on missing/empty conv; "[ROLE]: content" formatting;
  the max_messages tail window; graceful defaults for missing role/content keys
- error handling: a failing execute propagates (no commit swallowing)
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid

import pytest

from src.conversations import ConversationManager, conversation_manager

# NOTE: pytest is configured with ``asyncio_mode = "auto"`` (pyproject.toml), so
# ``async def test_*`` coroutines are collected and run without an explicit
# ``@pytest.mark.asyncio`` / module ``pytestmark`` (which would also wrongly tag
# the one sync test below and emit a warning).


# ──────────────────────────────────────────────────────────────────────────
#  Fake async session
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)`` for a SELECT.

    ``get_conversation`` only ever calls ``.fetchone()`` on the result.
    """

    def __init__(self, row: tuple | None = None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy ``AsyncSession``.

    Records each ``(rendered_sql, params)`` pair in ``self.calls`` so tests can
    assert on the statements issued and parameters bound. SELECTs return the
    single configured ``select_row``; writes return an empty result.
    ``commit`` flips ``self.commit_count``. Optionally raises on execute to
    simulate a DB error.
    """

    def __init__(self, select_row: tuple | None = None, *, raise_on_execute: bool = False) -> None:
        self._select_row = select_row
        self._raise_on_execute = raise_on_execute
        self.calls: list[tuple[str, dict]] = []
        self.commit_count = 0

    async def execute(self, stmt, params=None, *args, **kwargs):  # noqa: ANN001
        if self._raise_on_execute:
            raise RuntimeError("db unavailable")
        rendered = str(stmt)
        self.calls.append((rendered, params or {}))
        if rendered.lstrip().upper().startswith("SELECT"):
            return _FakeResult(row=self._select_row)
        return _FakeResult(row=None)

    async def commit(self):
        self.commit_count += 1


def _sql_ops(session: _FakeSession) -> list[str]:
    """The leading SQL verb (INSERT/UPDATE/SELECT/...) of each executed stmt."""
    return [c[0].lstrip().split(None, 1)[0].upper() for c in session.calls]


# ──────────────────────────────────────────────────────────────────────────
#  create_conversation
# ──────────────────────────────────────────────────────────────────────────


class TestCreateConversation:
    async def test_returns_valid_uuid(self):
        mgr = ConversationManager()
        session = _FakeSession()

        conv_id = await mgr.create_conversation(
            session, client_id=str(uuid.uuid4()), user_id="user-1"
        )

        # The returned id must be a parseable UUID string (uuid4 generated).
        parsed = uuid.UUID(conv_id)
        assert str(parsed) == conv_id

    async def test_issues_single_insert_and_commits(self):
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.create_conversation(session, client_id=None, user_id="user-1")

        assert _sql_ops(session) == ["INSERT"]
        assert session.commit_count == 1

    async def test_insert_params_bind_caller_identity_and_empty_messages(self):
        mgr = ConversationManager()
        session = _FakeSession()
        client_id = str(uuid.uuid4())

        conv_id = await mgr.create_conversation(session, client_id=client_id, user_id="user-42")

        _sql, params = session.calls[0]
        # The generated id is the one returned to the caller.
        assert params["id"] == conv_id
        assert params["client_id"] == client_id
        assert params["user_id"] == "user-42"
        # A brand-new conversation seeds an EMPTY messages array (JSON-encoded).
        assert params["messages"] == "[]"
        assert json.loads(params["messages"]) == []
        # created_at == updated_at on creation (single ``:now`` bind, timezone-aware UTC).
        assert isinstance(params["now"], _dt.datetime)
        assert params["now"].tzinfo is not None

    async def test_accepts_null_client_id(self):
        """client_id is nullable (a conversation need not be tied to a client)."""
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.create_conversation(session, client_id=None, user_id="u")

        assert session.calls[0][1]["client_id"] is None

    async def test_distinct_ids_across_calls(self):
        mgr = ConversationManager()
        session = _FakeSession()

        a = await mgr.create_conversation(session, client_id=None, user_id="u")
        b = await mgr.create_conversation(session, client_id=None, user_id="u")

        assert a != b


# ──────────────────────────────────────────────────────────────────────────
#  add_message
# ──────────────────────────────────────────────────────────────────────────


class TestAddMessage:
    async def test_issues_update_and_commits(self):
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.add_message(session, "conv-1", role="user", content="hi")

        assert _sql_ops(session) == ["UPDATE"]
        assert session.commit_count == 1

    async def test_message_payload_has_role_content_timestamp(self):
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.add_message(session, "conv-1", role="assistant", content="hello world")

        _sql, params = session.calls[0]
        assert params["conv_id"] == "conv-1"
        # The bound ``message`` param is a JSON array holding the single message.
        payload = json.loads(params["message"])
        assert isinstance(payload, list) and len(payload) == 1
        msg = payload[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "hello world"
        # timestamp is an ISO-8601 string the json column can store.
        assert isinstance(msg["timestamp"], str)
        _dt.datetime.fromisoformat(msg["timestamp"])  # parses without error

    async def test_metadata_omitted_when_not_provided(self):
        """No ``metadata`` key is written when the caller passes none/empty."""
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.add_message(session, "conv-1", role="user", content="q")

        msg = json.loads(session.calls[0][1]["message"])[0]
        assert "metadata" not in msg

    async def test_metadata_included_when_provided(self):
        mgr = ConversationManager()
        session = _FakeSession()
        meta = {"confidence_score": 0.91, "citations": ["CSRD Art. 19a"]}

        await mgr.add_message(session, "conv-1", role="assistant", content="answer", metadata=meta)

        msg = json.loads(session.calls[0][1]["message"])[0]
        assert msg["metadata"] == meta

    async def test_empty_metadata_dict_is_treated_as_absent(self):
        """An empty dict is falsy -> the implementation does not attach metadata."""
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.add_message(session, "conv-1", role="user", content="q", metadata={})

        msg = json.loads(session.calls[0][1]["message"])[0]
        assert "metadata" not in msg

    async def test_update_targets_the_named_conversation(self):
        mgr = ConversationManager()
        session = _FakeSession()

        await mgr.add_message(session, "the-target-conv", role="user", content="x")

        sql, params = session.calls[0]
        assert "conversations" in sql.lower()
        assert params["conv_id"] == "the-target-conv"


# ──────────────────────────────────────────────────────────────────────────
#  get_conversation
# ──────────────────────────────────────────────────────────────────────────


def _row(
    *,
    conv_id=None,
    client_id=None,
    user_id="user-1",
    messages=None,
    created_at=None,
):
    """A DB row tuple in the column order get_conversation selects:
    (id, client_id, user_id, messages, created_at)."""
    return (
        conv_id if conv_id is not None else uuid.uuid4(),
        client_id,
        user_id,
        messages if messages is not None else [],
        created_at,
    )


class TestGetConversation:
    async def test_returns_none_when_no_row(self):
        mgr = ConversationManager()
        session = _FakeSession(select_row=None)

        result = await mgr.get_conversation(session, "missing-id")

        assert result is None
        # A SELECT was attempted (we did query before returning None).
        assert _sql_ops(session) == ["SELECT"]

    async def test_stringifies_uuid_columns(self):
        mgr = ConversationManager()
        cid = uuid.uuid4()
        client = uuid.uuid4()
        uid = uuid.uuid4()
        session = _FakeSession(
            select_row=_row(conv_id=cid, client_id=client, user_id=uid, messages=[])
        )

        result = await mgr.get_conversation(session, str(cid))

        assert result["id"] == str(cid)
        assert result["client_id"] == str(client)
        assert result["user_id"] == str(uid)

    async def test_null_client_id_serializes_to_none(self):
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(client_id=None, messages=[]))

        result = await mgr.get_conversation(session, "c")

        assert result["client_id"] is None

    async def test_messages_passed_through_when_already_a_list(self):
        """When the json column is materialized as a Python list, it is returned
        verbatim (no double-decode)."""
        mgr = ConversationManager()
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        session = _FakeSession(select_row=_row(messages=msgs))

        result = await mgr.get_conversation(session, "c")

        assert result["messages"] == msgs

    async def test_messages_parsed_when_json_string(self):
        """When the column arrives as a JSON string, it is json.loads'd into a list."""
        mgr = ConversationManager()
        msgs = [{"role": "user", "content": "hi"}]
        session = _FakeSession(select_row=_row(messages=json.dumps(msgs)))

        result = await mgr.get_conversation(session, "c")

        assert result["messages"] == msgs

    async def test_created_at_isoformatted_when_present(self):
        mgr = ConversationManager()
        ts = _dt.datetime(2026, 6, 1, 10, 0, 0, tzinfo=_dt.UTC)
        session = _FakeSession(select_row=_row(messages=[], created_at=ts))

        result = await mgr.get_conversation(session, "c")

        assert result["created_at"] == ts.isoformat()

    async def test_created_at_none_when_absent(self):
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(messages=[], created_at=None))

        result = await mgr.get_conversation(session, "c")

        assert result["created_at"] is None

    async def test_user_id_filter_is_bound_for_ownership(self):
        """The ownership filter binds the supplied user_id (IDOR guard parameter)."""
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(messages=[]))

        await mgr.get_conversation(session, "conv-9", user_id="owner-42")

        _sql, params = session.calls[0]
        assert params["id"] == "conv-9"
        assert params["user_id"] == "owner-42"

    async def test_user_id_filter_defaults_to_none(self):
        """With no user_id the filter param is None (the SQL's IS NULL branch
        keeps the no-filter path in the same static statement)."""
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(messages=[]))

        await mgr.get_conversation(session, "conv-9")

        assert session.calls[0][1]["user_id"] is None


# ──────────────────────────────────────────────────────────────────────────
#  get_context_for_qa
# ──────────────────────────────────────────────────────────────────────────


class TestGetContextForQa:
    async def test_empty_string_when_conversation_missing(self):
        mgr = ConversationManager()
        session = _FakeSession(select_row=None)  # get_conversation -> None

        ctx = await mgr.get_context_for_qa(session, "missing")

        assert ctx == ""

    async def test_empty_string_when_no_messages(self):
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(messages=[]))

        ctx = await mgr.get_context_for_qa(session, "c")

        assert ctx == ""

    async def test_formats_role_uppercased_with_content(self):
        mgr = ConversationManager()
        msgs = [
            {"role": "user", "content": "What is CSRD?"},
            {"role": "assistant", "content": "A reporting directive."},
        ]
        session = _FakeSession(select_row=_row(messages=msgs))

        ctx = await mgr.get_context_for_qa(session, "c")

        assert ctx == "[USER]: What is CSRD?\n[ASSISTANT]: A reporting directive."

    async def test_respects_max_messages_tail_window(self):
        """Only the most recent ``max_messages`` are included (the tail)."""
        mgr = ConversationManager()
        msgs = [{"role": "user", "content": f"m{i}"} for i in range(5)]
        session = _FakeSession(select_row=_row(messages=msgs))

        ctx = await mgr.get_context_for_qa(session, "c", max_messages=2)

        # Last two only: m3, m4.
        assert ctx == "[USER]: m3\n[USER]: m4"

    async def test_max_messages_larger_than_history_returns_all(self):
        mgr = ConversationManager()
        msgs = [{"role": "user", "content": "only"}]
        session = _FakeSession(select_row=_row(messages=msgs))

        ctx = await mgr.get_context_for_qa(session, "c", max_messages=10)

        assert ctx == "[USER]: only"

    async def test_defaults_missing_role_to_user_and_missing_content_to_empty(self):
        """A malformed message (no role/content keys) falls back to role=user,
        content="" rather than raising a KeyError."""
        mgr = ConversationManager()
        session = _FakeSession(select_row=_row(messages=[{}]))

        ctx = await mgr.get_context_for_qa(session, "c")

        assert ctx == "[USER]: "


# ──────────────────────────────────────────────────────────────────────────
#  Error handling
# ──────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    async def test_create_propagates_db_error_without_commit(self):
        mgr = ConversationManager()
        session = _FakeSession(raise_on_execute=True)

        with pytest.raises(RuntimeError, match="db unavailable"):
            await mgr.create_conversation(session, client_id=None, user_id="u")

        # The error surfaced before commit; no silent swallow.
        assert session.commit_count == 0

    async def test_add_message_propagates_db_error_without_commit(self):
        mgr = ConversationManager()
        session = _FakeSession(raise_on_execute=True)

        with pytest.raises(RuntimeError, match="db unavailable"):
            await mgr.add_message(session, "c", role="user", content="x")

        assert session.commit_count == 0

    async def test_get_conversation_propagates_db_error(self):
        mgr = ConversationManager()
        session = _FakeSession(raise_on_execute=True)

        with pytest.raises(RuntimeError, match="db unavailable"):
            await mgr.get_conversation(session, "c")


# ──────────────────────────────────────────────────────────────────────────
#  Module singleton
# ──────────────────────────────────────────────────────────────────────────


class TestSingleton:
    def test_module_exposes_a_conversation_manager_instance(self):
        assert isinstance(conversation_manager, ConversationManager)

    async def test_singleton_is_usable(self):
        session = _FakeSession()
        conv_id = await conversation_manager.create_conversation(
            session, client_id=None, user_id="u"
        )
        assert uuid.UUID(conv_id)
