"""Async database engine and session management with RLS enforcement."""

import contextlib
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings


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
        """
        if self._sessionmaker is None:
            raise RuntimeError("DatabaseSessionManager is not initialized. Call init() first.")
        session = self._sessionmaker()
        try:
            # Set the RLS context. NOTE: `SET LOCAL` only survives the current
            # transaction — and these sessions commit multiple times per request,
            # so SET LOCAL was lost before the real queries ran and RLS saw no
            # org_id. set_config(..., is_local=false) is connection-scoped and
            # survives transaction boundaries; we RESET it in finally so a pooled
            # connection never carries one tenant's org context to the next.
            #
            # Defence-in-depth only: RLS is bypassed when the app connects as a
            # superuser or the table owner. Production MUST use a NON-superuser
            # role with FORCE ROW LEVEL SECURITY (see docs/DEPLOY_HETZNER.md).
            if org_id:
                await session.execute(
                    text("SELECT set_config('app.current_org_id', :org_id, false)"),
                    {"org_id": str(org_id)},
                )
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            if org_id:
                try:
                    await session.execute(
                        text("SELECT set_config('app.current_org_id', '', false)")
                    )
                    await session.commit()
                except Exception:  # noqa: BLE001 — best-effort reset on teardown
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
