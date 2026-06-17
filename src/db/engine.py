"""Async database engine and session management with RLS enforcement."""

import contextlib
import logging
from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

logger = logging.getLogger(__name__)

# Connection-scoped GUC that drives the PostgreSQL Row-Level-Security policies.
RLS_GUC = "app.current_org_id"


def _reset_rls_on_checkin(dbapi_connection, connection_record):
    """Pool 'checkin' hook: clear the RLS org GUC on the raw connection.

    The org context is a *connection-scoped* GUC (set_config(..., is_local=false))
    so it survives the multiple commits a request performs. The application-level
    reset in ``session()``'s finally block is best-effort and can be skipped
    (task cancellation, a connection error during teardown). This hook runs on
    EVERY return-to-pool, so a physical connection can never re-enter the pool
    still carrying a previous tenant's org_id and bleed it into the next session
    (notably a no-org ``get_db_session`` that never sets the GUC itself).

    Registered only for PostgreSQL engines (see ``init``); SQLite has no GUCs.
    asyncpg exposes ``run_async`` to drive a coroutine from this sync pool event;
    we fall back to a sync cursor for sync drivers.
    """
    try:
        run_async = getattr(dbapi_connection, "run_async", None)
        if run_async is not None:
            run_async(lambda conn: conn.execute(f"RESET {RLS_GUC}"))
        else:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute(f"RESET {RLS_GUC}")
            finally:
                cursor.close()
    except Exception:  # noqa: BLE001
        # If we cannot guarantee a clean org context, do NOT reuse this
        # connection: hard-invalidate it (favour tenant isolation over the
        # small availability cost of an extra reconnect).
        try:
            connection_record.invalidate()
        except Exception:  # noqa: BLE001
            logger.warning("rls_checkin_reset_failed_invalidate_failed")


class DatabaseSessionManager:
    """Manages async database connections with RLS enforcement."""

    def __init__(self):
        self._engine: AsyncEngine | None = None
        self._sessionmaker: async_sessionmaker[AsyncSession] | None = None

    def init(self, dsn: str | None = None):
        settings = get_settings()
        url = dsn or settings.database_url
        self._engine = create_async_engine(
            url,
            echo=settings.app_env == "development",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        # Guarantee the RLS org context is cleared whenever a connection returns
        # to the pool (defence that does NOT depend on the session finally-block).
        if self._engine.url.get_backend_name() == "postgresql":
            event.listen(self._engine.sync_engine, "checkin", _reset_rls_on_checkin)
        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self):
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def session(self, org_id: str | None = None) -> AsyncIterator[AsyncSession]:
        """Get a database session with optional RLS org_id enforcement.

        Args:
            org_id: Organization ID for Row-Level Security. When set,
                    PostgreSQL RLS policies will filter data to this org.

        Tenant isolation guarantee: the connection-scoped GUC set below is reset
        on every pool checkin (see ``_reset_rls_on_checkin``), so a no-org
        session can never inherit a stale org context from a pooled connection.

        Defence-in-depth only: RLS is bypassed when the app connects as a
        superuser or the table owner. Production MUST use a NON-superuser role
        with FORCE ROW LEVEL SECURITY (see docs/DEPLOY_HETZNER.md), otherwise
        this context is advisory and tenant isolation is not actually enforced.
        """
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseSessionManager is not initialized. Call init() first.")
        session = self._sessionmaker()
        try:
            # `SET LOCAL` would be lost across the multiple commits a request
            # performs, so we use connection-scoped set_config(..., is_local=false).
            if org_id:
                await session.execute(
                    text(f"SELECT set_config('{RLS_GUC}', :org_id, false)"),
                    {"org_id": str(org_id)},
                )
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            # Eager best-effort reset (the pool checkin hook is the real
            # guarantee; this just clears it sooner for the common path).
            if org_id:
                try:
                    await session.execute(text(f"SELECT set_config('{RLS_GUC}', '', false)"))
                    await session.commit()
                except Exception:  # noqa: BLE001 - best-effort; pool checkin still resets
                    pass
            await session.close()

    @contextlib.asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        if self._engine is None:
            raise RuntimeError("DatabaseSessionManager is not initialized.")
        async with self._engine.begin() as connection:
            try:
                yield connection
            except Exception:
                await connection.rollback()
                raise


db_manager = DatabaseSessionManager()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for database sessions (no RLS).

    Use for public endpoints or admin operations that span organizations.
    For tenant-scoped data access, use get_tenant_session instead.
    """
    async with db_manager.session() as session:
        yield session


async def get_scoped_db_session(org_id: str) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency for RLS-scoped database sessions."""
    async with db_manager.session(org_id=org_id) as session:
        yield session


def get_tenant_session():
    """FastAPI dependency that automatically applies RLS using the authenticated user's org_id.

    Combines JWT authentication with Row-Level Security in a single dependency.
    This should be the default for all tenant-scoped endpoints.

    Usage:
        @router.get("/my-data")
        async def my_data(
            user: CurrentUser = Depends(get_current_user),
            db: AsyncSession = Depends(get_tenant_session()),
        ):
            # All queries in this session are automatically filtered by org_id
            ...
    """
    from fastapi import Depends

    from src.auth.dependencies import CurrentUser, get_current_user

    async def _get_session(
        user: CurrentUser = Depends(get_current_user),
    ) -> AsyncIterator[AsyncSession]:
        async with db_manager.session(org_id=str(user.org_id)) as session:
            yield session

    return _get_session
