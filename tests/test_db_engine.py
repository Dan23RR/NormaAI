"""Unit tests for ``src.db.engine`` — DatabaseSessionManager lifecycle and the
RLS pool-checkin hook MECHANICS.

The full multi-tenant pool-isolation regression needs a real (non-superuser)
Postgres and lives in ``tests/test_rls_pool_isolation.py`` (skip-gated on
``POSTGRES_RLS_TEST_URL``). This file deliberately requires NO Postgres and NO
real ``test.db``: it asserts the *mechanics* with mocks and fake sessions —

  * ``init()`` builds the engine + sessionmaker and registers the ``checkin``
    listener ONLY for a postgresql backend, NOT for sqlite.
  * ``session(org_id)`` sets the connection-scoped GUC via
    ``set_config(..., false)`` and best-effort resets+commits it in ``finally``.
  * ``session()`` without an org never touches the GUC.
  * ``session()`` before ``init()`` raises RuntimeError("...not initialized...").
  * the exception path rolls back, still resets the GUC, and closes.
  * a failing best-effort reset is swallowed (the pool checkin is the real
    guarantee) and the session is still closed.
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
    """Records every awaited operation so tests can assert the exact SQL/order.

    ``fail_reset`` forces the best-effort reset (``set_config(..., '')``) in the
    ``finally`` block to raise, to exercise the swallow-and-still-close path.
    """

    def __init__(self, *, fail_reset: bool = False) -> None:
        self.calls: list[tuple] = []
        self.fail_reset = fail_reset

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if self.fail_reset and "set_config('app.current_org_id', ''" in sql:
            self.calls.append(("execute_RAISE", sql, params))
            raise RuntimeError("simulated reset failure")
        self.calls.append(("execute", sql, params))
        return MagicMock(name="Result")

    async def commit(self):
        self.calls.append(("commit",))

    async def rollback(self):
        self.calls.append(("rollback",))

    async def close(self):
        self.calls.append(("close",))


def _execute_sqls(session: FakeSession) -> list[str]:
    return [c[1] for c in session.calls if c[0] in ("execute", "execute_RAISE")]


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


class TestSessionMechanics:
    async def test_not_initialized_raises_runtime_error(self):
        mgr = DatabaseSessionManager()
        with pytest.raises(RuntimeError, match="not initialized"):
            async with mgr.session():
                pass

    async def test_session_with_org_sets_and_resets_guc(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        async with mgr.session(org_id="org-123") as s:
            assert s is fake

        sqls = _execute_sqls(fake)
        # 1) connection-scoped SET (is_local=false), bound param, not f-string'd
        assert sqls[0] == f"SELECT set_config('{RLS_GUC}', :org_id, false)"
        assert fake.calls[0] == (
            "execute",
            f"SELECT set_config('{RLS_GUC}', :org_id, false)",
            {"org_id": "org-123"},
        )
        # 2) finally: best-effort reset to empty + commit, then close
        assert sqls[1] == f"SELECT set_config('{RLS_GUC}', '', false)"
        kinds = [c[0] for c in fake.calls]
        assert kinds == ["execute", "execute", "commit", "close"]

    async def test_session_org_id_is_stringified(self):
        """A non-string org_id (e.g. UUID) is passed as str() in the bound param."""
        import uuid

        org = uuid.uuid4()
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake
        async with mgr.session(org_id=org):
            pass
        assert fake.calls[0][2] == {"org_id": str(org)}

    async def test_session_without_org_never_touches_guc(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        async with mgr.session() as s:
            assert s is fake

        # No SET, no reset, no commit — only close.
        assert _execute_sqls(fake) == []
        assert [c[0] for c in fake.calls] == ["close"]

    async def test_session_empty_org_id_treated_as_no_org(self):
        """``org_id=""`` is falsy -> the GUC must NOT be set (guards against an
        accidental empty-string tenant context)."""
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake
        async with mgr.session(org_id=""):
            pass
        assert _execute_sqls(fake) == []
        assert [c[0] for c in fake.calls] == ["close"]

    async def test_session_exception_rolls_back_resets_and_closes(self):
        fake = FakeSession()
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        with pytest.raises(ValueError, match="boom"):
            async with mgr.session(org_id="org-x"):
                raise ValueError("boom")

        kinds = [c[0] for c in fake.calls]
        # SET -> rollback (except) -> reset (finally) -> commit -> close
        assert kinds == ["execute", "rollback", "execute", "commit", "close"]
        assert _execute_sqls(fake)[1] == f"SELECT set_config('{RLS_GUC}', '', false)"

    async def test_session_best_effort_reset_failure_is_swallowed_and_closes(self):
        """If the finally reset raises, it is swallowed (the pool checkin hook is
        the real guarantee) and the session is STILL closed."""
        fake = FakeSession(fail_reset=True)
        mgr = DatabaseSessionManager()
        mgr._sessionmaker = lambda: fake

        # Must NOT propagate the reset failure.
        async with mgr.session(org_id="org-x"):
            pass

        kinds = [c[0] for c in fake.calls]
        assert kinds == ["execute", "execute_RAISE", "close"]
        # commit never ran (reset raised before it); close still ran.
        assert "commit" not in kinds
        assert ("close",) in fake.calls

    async def test_session_no_org_does_not_swallow_body_exception(self):
        """The no-org path has no SET/reset; an error in the body still
        propagates after rollback + close."""
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
        with patch.object(engine_mod.db_manager, "_sessionmaker", lambda: fake):
            gen = get_scoped_db_session("org-555")
            yielded = await gen.__anext__()
            assert yielded is fake
            with pytest.raises(StopAsyncIteration):
                await gen.__anext__()
        assert fake.calls[0][2] == {"org_id": "org-555"}
        assert _execute_sqls(fake)[0] == f"SELECT set_config('{RLS_GUC}', :org_id, false)"

    def test_get_tenant_session_returns_async_gen_dependency(self):
        dep = get_tenant_session()
        assert callable(dep)
        assert inspect.isasyncgenfunction(dep)

    async def test_get_tenant_session_applies_users_org_id(self):
        dep = get_tenant_session()
        fake = FakeSession()
        user = MagicMock()
        user.org_id = "org-77"
        with patch.object(engine_mod.db_manager, "_sessionmaker", lambda: fake):
            agen = dep(user=user)
            yielded = await agen.__anext__()
            assert yielded is fake
            with pytest.raises(StopAsyncIteration):
                await agen.__anext__()
        # str(user.org_id) is bound into the SET, and it is reset on teardown.
        assert fake.calls[0][2] == {"org_id": "org-77"}
        assert [c[0] for c in fake.calls] == ["execute", "execute", "commit", "close"]


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
