"""Unit tests for ``src.db.engine`` - DatabaseSessionManager lifecycle and the
RLS pool-checkin hook MECHANICS.

The full multi-tenant pool-isolation regression needs a real (non-superuser)
Postgres and lives in ``tests/test_rls_pool_isolation.py`` (skip-gated on
``POSTGRES_RLS_TEST_URL``). This file deliberately requires NO Postgres and NO
real ``test.db``: it asserts the *mechanics* with mocks and fake sessions -

  * ``init()`` builds the engine + sessionmaker and registers the ``checkin``
    listener ONLY for a postgresql backend, NOT for sqlite.
  * ``session(org_id)`` registers an ``after_begin`` listener that re-applies the
    org GUC (``set_config(..., is_local=true)``) at EVERY transaction (so it
    survives the connection release on commit), and removes it on teardown.
  * ``session()`` without an org registers no listener and never sets the GUC.
  * ``session()`` before ``init()`` raises RuntimeError("...not initialized...").
  * the exception path rolls back, removes the listener, and closes.
  * ``close()`` disposes the engine and resets ``_engine``/``_sessionmaker``.
  * ``get_db_session`` / ``get_scoped_db_session`` / ``get_tenant_session``
    drive ``db_manager.session(...)`` correctly.
  * ``_reset_rls_on_checkin`` fail-closed: when the reset coroutine raises, the
    connection record is invalidated (favour isolation over availability).

Anti-pollution: this file does NOT import ``src.api.main`` or any router, so it
adds nothing to ``sys.modules`` that other suites re-import; it only ever mutates
a fresh ``DatabaseSessionManager()`` (or patches the module-level ``db_manager``
inside a ``with`` block that restores it). It never opens a real connection.

NOTE on the sqlite branch: ``aiosqlite`` is not installed in this environment,
so a real ``sqlite+aiosqlite`` async engine cannot be built. The "no listener
for sqlite" / "listener for postgresql" branch in ``init()`` is therefore tested
by patching ``create_async_engine`` (to a fake engine whose backend name we
control) and ``event.listen`` (to observe whether the listener was registered),
which exercises the exact branch in ``init()`` without needing any driver. The
postgresql-backend paths that don't require a live connection (``init`` +
``close``) ARE exercised against a real lazily-built asyncpg engine.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

import src.db.engine as engine_mod
from src.db.engine import (
    RLS_GUC,
    DatabaseSessionManager,
    _reset_rls_on_checkin,
    get_db_session,
    get_scoped_db_session,
    get_tenant_session,
)

PG_DSN = "postgresql+asyncpg://u:pw@localhost:5432/normaai_test_unused"


# ───────────────────────── test doubles ─────────────────────────


class FakeSession:
    """Records body operations and carries a ``sync_session`` MagicMock.

    The RLS org GUC is applied by an ``after_begin`` listener registered on
    ``sync_session`` (re-asserted at every transaction begin so it survives the
    connection release on commit), NOT by a direct execute on this session - so
    tests observe the listener via patched ``event.listen``/``event.remove``.
    """

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.sync_session = MagicMock(name="sync_session")

    async def execute(self, stmt, params=None):
        self.calls.append(("execute", str(stmt), params))
        return MagicMock(name="Result")

    async def commit(self):
        self.calls.append(("commit",))

    async def rollback(self):
        self.calls.append(("rollback",))

    async def close(self):
        self.calls.append(("close",))


def _execute_sqls(session: FakeSession) -> list[str]:
    return [c[1] for c in session.calls if c[0] == "execute"]


def _make_fake_async_engine(backend: str) -> MagicMock:
    """A stand-in for an AsyncEngine exposing ``.url.get_backend_name()`` and a
    ``.sync_engine`` (the object ``init`` registers the checkin listener on)."""
    fake = MagicMock(name=f"AsyncEngine[{backend}]")
    fake.url.get_backend_name.return_value = backend
    return fake


# ───────────────────────── init() / listener registration ─────────────────────────


class TestInitListenerRegistration:
    def test_postgresql_registers_checkin_listener(self):
        """A real (lazily-built, not connected) asyncpg engine must get the
        ``_reset_rls_on_checkin`` hook wired on its sync_engine."""
        mgr = DatabaseSessionManager()
        try:
            mgr.init(PG_DSN)
            assert mgr._engine is not None
            assert mgr._sessionmaker is not None
            assert mgr._engine.url.get_backend_name() == "postgresql"
            assert event.contains(
                mgr._engine.sync_engine, "checkin", _reset_rls_on_checkin
            ), "postgresql engine must register the RLS checkin reset hook"
        finally:
            # dispose without awaiting close() (no event loop needed here): the
            # lazily-built engine never opened a connection.
            mgr._engine.sync_engine.dispose()

    def test_postgresql_listen_called_with_checkin_and_hook(self):
        """Branch-level check that does not depend on event.contains semantics:
        ``event.listen`` is invoked exactly with (sync_engine, 'checkin', hook)."""
        with (
            patch.object(
                engine_mod,
                "create_async_engine",
                return_value=_make_fake_async_engine("postgresql"),
            ) as cae,
            patch.object(engine_mod.event, "listen") as mock_listen,
        ):
            mgr = DatabaseSessionManager()
            mgr.init(PG_DSN)
            assert cae.called
            assert mock_listen.call_count == 1
            args = mock_listen.call_args.args
            assert args[1] == "checkin"
            assert args[2] is _reset_rls_on_checkin

    def test_sqlite_does_not_register_checkin_listener(self):
        """SQLite has no GUCs: ``init`` must NOT register the checkin hook.

        Patched engine because aiosqlite is absent; the branch under test
        (``backend == "postgresql"``) is still exercised faithfully.
        """
        with (
            patch.object(
                engine_mod,
                "create_async_engine",
                return_value=_make_fake_async_engine("sqlite"),
            ),
            patch.object(engine_mod.event, "listen") as mock_listen,
        ):
            mgr = DatabaseSessionManager()
            mgr.init("sqlite+aiosqlite:///:memory:")
            assert mgr._engine is not None
            assert mgr._sessionmaker is not None
            assert not mock_listen.called, "sqlite must NOT register the RLS checkin hook"

    def test_init_uses_explicit_dsn_over_settings(self):
        """The ``dsn`` argument overrides ``settings.database_url``."""
        captured: dict = {}

        def fake_create(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return _make_fake_async_engine("postgresql")

        with (
            patch.object(engine_mod, "create_async_engine", side_effect=fake_create),
            patch.object(engine_mod.event, "listen"),
        ):
            mgr = DatabaseSessionManager()
            mgr.init(PG_DSN)
        assert captured["url"] == PG_DSN
        # pool tuning that the module promises is actually forwarded.
        assert captured["kwargs"]["pool_size"] == 10
        assert captured["kwargs"]["max_overflow"] == 20
        assert captured["kwargs"]["pool_pre_ping"] is True
        assert captured["kwargs"]["pool_recycle"] == 3600


# ───────────────────────── close() ─────────────────────────


class TestClose:
    async def test_close_disposes_and_resets_state(self):
        disposed = {"called": False}

        async def fake_dispose():
            disposed["called"] = True

        fake_engine = _make_fake_async_engine("postgresql")
        fake_engine.dispose = fake_dispose

        mgr = DatabaseSessionManager()
        mgr._engine = fake_engine
        mgr._sessionmaker = MagicMock()

        await mgr.close()

        assert disposed["called"] is True
        assert mgr._engine is None
        assert mgr._sessionmaker is None

    async def test_close_when_uninitialized_is_noop(self):
        mgr = DatabaseSessionManager()
        # No engine -> must not raise and must leave state cleared.
        await mgr.close()
        assert mgr._engine is None
        assert mgr._sessionmaker is None


# ───────────────────────── session() GUC mechanics ─────────────────────────


def _registered_after_begin(mock_listen: MagicMock):
    """Return (target, listener_fn) for the single after_begin registration."""
    assert mock_listen.call_count == 1, "exactly one listener should be registered"
    target, ident, fn = mock_listen.call_args.args
    assert ident == "after_begin"
    return target, fn


class TestSessionMechanics:
    async def test_not_initialized_raises_runtime_error(self):
        mgr = DatabaseSessionManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            async with mgr.session():
                pass

    async def test_session_with_org_registers_after_begin_listener_that_sets_guc(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        with (
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove") as mock_remove,
        ):
            async with mgr.session(org_id="org-123") as s:
                assert s is fake
            # listener registered on the session's sync_session for after_begin
            target, fn = _registered_after_begin(mock_listen)
            assert target is fake.sync_session
            # and the listener, fired with a connection, sets the GUC
            # transaction-local (is_local=true) with the bound org value.
            conn = MagicMock()
            fn(MagicMock(), MagicMock(), conn)
            stmt, params = conn.execute.call_args.args
            assert str(stmt) == f"SELECT set_config('{RLS_GUC}', :v, true)"
            assert params == {"v": "org-123"}
            # removed in finally (no listener leak across pooled sessions)
            assert mock_remove.call_count == 1
        assert ("close",) in fake.calls

    async def test_session_org_id_is_stringified(self):
        """A non-string org_id (e.g. UUID) is bound as str() inside the listener."""
        import uuid

        org = uuid.uuid4()
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake
        with (
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove"),
        ):
            async with mgr.session(org_id=org):
                pass
            _, fn = _registered_after_begin(mock_listen)
            conn = MagicMock()
            fn(MagicMock(), MagicMock(), conn)
            assert conn.execute.call_args.args[1] == {"v": str(org)}

    async def test_session_without_org_registers_no_listener(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        with (
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove") as mock_remove,
        ):
            async with mgr.session() as s:
                assert s is fake
        assert not mock_listen.called
        assert not mock_remove.called
        # No GUC plumbing - only close.
        assert [c[0] for c in fake.calls] == ["close"]

    async def test_session_empty_org_id_treated_as_no_org(self):
        """``org_id=""`` is falsy -> NO listener (no accidental empty tenant ctx)."""
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake
        with (
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove"),
        ):
            async with mgr.session(org_id=""):
                pass
        assert not mock_listen.called
        assert [c[0] for c in fake.calls] == ["close"]

    async def test_session_exception_rolls_back_removes_listener_and_closes(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        with (
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove") as mock_remove,
            pytest.raises(ValueError, match="boom"),
        ):
            async with mgr.session(org_id="org-x"):
                raise ValueError("boom")

        kinds = [c[0] for c in fake.calls]
        # body raised -> rollback (except) -> close (finally)
        assert kinds == ["rollback", "close"]
        # listener was registered then removed even on the error path
        assert mock_listen.call_count == 1
        assert mock_remove.call_count == 1

    async def test_session_no_org_does_not_swallow_body_exception(self):
        """The no-org path still propagates a body error after rollback + close."""
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake
        with pytest.raises(KeyError):
            async with mgr.session():
                raise KeyError("nope")
        kinds = [c[0] for c in fake.calls]
        assert kinds == ["rollback", "close"]


# ───────────────────────── FastAPI dependency generators ─────────────────────────


class TestDependencyGenerators:
    async def test_get_db_session_drives_no_org_session(self):
        fake = FakeSession()
        with patch.object(engine_mod.db_manager, "_sessionmaker", lambda: fake):
            gen = get_db_session()
            yielded = await gen.__anext__()
            assert yielded is fake
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
        # no-org -> only close, no GUC.
        assert [c[0] for c in fake.calls] == ["close"]

    async def test_get_scoped_db_session_sets_org_guc(self):
        fake = FakeSession()
        with (
            patch.object(engine_mod.db_manager, "_sessionmaker", lambda: fake),
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove"),
        ):
            gen = get_scoped_db_session("org-555")
            yielded = await gen.__anext__()
            assert yielded is fake
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
            # the org GUC is applied via the after_begin listener
            _, _, fn = mock_listen.call_args.args
            conn = MagicMock()
            fn(MagicMock(), MagicMock(), conn)
            assert conn.execute.call_args.args[1] == {"v": "org-555"}

    def test_get_tenant_session_returns_async_gen_dependency(self):
        dep = get_tenant_session()
        assert callable(dep)
        assert inspect.isasyncgenfunction(dep)

    async def test_get_tenant_session_applies_users_org_id(self):
        dep = get_tenant_session()
        fake = FakeSession()
        user = MagicMock()
        user.org_id = "org-77"
        with (
            patch.object(engine_mod.db_manager, "_sessionmaker", lambda: fake),
            patch.object(engine_mod.event, "listen") as mock_listen,
            patch.object(engine_mod.event, "remove"),
        ):
            agen = dep(user=user)
            yielded = await agen.__anext__()
            assert yielded is fake
            with pytest.raises(StopAsyncIteration):
                await agen.__anext__()
            # str(user.org_id) is bound into the after_begin GUC setter.
            _, _, fn = mock_listen.call_args.args
            conn = MagicMock()
            fn(MagicMock(), MagicMock(), conn)
            assert conn.execute.call_args.args[1] == {"v": "org-77"}
        assert [c[0] for c in fake.calls] == ["close"]


# ───────────────────────── _reset_rls_on_checkin fail-closed hook ─────────────────────────


class TestResetRlsOnCheckin:
    def test_asyncpg_run_async_path_executes_reset_and_does_not_invalidate(self):
        executed: dict = {}

        def run_async(coro_fn):
            # asyncpg drives the coroutine factory with the raw connection.
            conn = MagicMock()
            coro_fn(conn)
            executed["sql"] = conn.execute.call_args.args[0]

        dbapi = MagicMock()
        dbapi.run_async = run_async
        record = MagicMock()

        _reset_rls_on_checkin(dbapi, record)

        assert executed["sql"] == f"RESET {RLS_GUC}"
        assert not record.invalidate.called

    def test_sync_cursor_path_executes_reset_and_closes_cursor(self):
        dbapi = MagicMock()
        dbapi.run_async = None  # force the sync-driver fallback
        cursor = MagicMock()
        dbapi.cursor.return_value = cursor
        record = MagicMock()

        _reset_rls_on_checkin(dbapi, record)

        cursor.execute.assert_called_once_with(f"RESET {RLS_GUC}")
        assert cursor.close.called
        assert not record.invalidate.called

    def test_run_async_failure_invalidates_connection_fail_closed(self):
        """The headline guarantee: if the reset coroutine raises, the connection
        is hard-invalidated so it can never re-enter the pool carrying a stale
        tenant org_id."""
        dbapi = MagicMock()
        dbapi.run_async.side_effect = RuntimeError("reset failed")
        record = MagicMock()

        _reset_rls_on_checkin(dbapi, record)

        assert record.invalidate.called, "a failed reset MUST invalidate the connection"

    def test_sync_cursor_failure_invalidates_connection(self):
        dbapi = MagicMock()
        dbapi.run_async = None
        cursor = MagicMock()
        cursor.execute.side_effect = RuntimeError("reset failed")
        dbapi.cursor.return_value = cursor
        record = MagicMock()

        _reset_rls_on_checkin(dbapi, record)

        # cursor is still closed (finally) and the connection is invalidated.
        assert cursor.close.called
        assert record.invalidate.called

    def test_double_failure_is_swallowed(self):
        """If even invalidate() raises, the hook must not propagate (a pool
        checkin callback raising would be worse than the reconnect cost)."""
        dbapi = MagicMock()
        dbapi.run_async.side_effect = RuntimeError("reset failed")
        record = MagicMock()
        record.invalidate.side_effect = RuntimeError("invalidate failed")

        # Must not raise.
        _reset_rls_on_checkin(dbapi, record)

        assert record.invalidate.called
