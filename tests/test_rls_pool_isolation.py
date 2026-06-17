"""Integration test: the RLS org context must NOT bleed across pooled connections.

This is the explicit multi-tenant regression the code review asked for. It is
gated on ``POSTGRES_RLS_TEST_URL`` which MUST point at a NON-superuser,
NON-BYPASSRLS Postgres role: a superuser/owner bypasses RLS, so the assertions
would pass vacuously. The fixture self-checks the role and skips loudly if it is
privileged, so the test can never give a false green.

To run it, set ``POSTGRES_RLS_TEST_URL`` to a NON-superuser role; otherwise it
skips cleanly. CI can gate it by provisioning such a role (see the code-review
follow-ups). Locally: POSTGRES_RLS_TEST_URL=postgresql+asyncpg://u:pw@localhost/db
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import src.db.engine as engine_mod
from src.db.engine import DatabaseSessionManager

RLS_URL = os.environ.get("POSTGRES_RLS_TEST_URL")

pytestmark = pytest.mark.skipif(
    not RLS_URL,
    reason="POSTGRES_RLS_TEST_URL not set (needs a non-superuser Postgres role)",
)

ORG_A = str(uuid.uuid4())
ORG_B = str(uuid.uuid4())
TABLE = "rls_pool_isolation_test"


async def _names(session) -> set[str]:
    result = await session.execute(text(f"SELECT name FROM {TABLE}"))
    return {row[0] for row in result.fetchall()}


@pytest_asyncio.fixture
async def manager():
    # pool_size=1 / max_overflow=0 forces every session to reuse the SAME
    # physical connection, so any org-context bleed across sessions is observable.
    engine = create_async_engine(RLS_URL, pool_size=1, max_overflow=0)
    if engine.url.get_backend_name() == "postgresql":
        event.listen(engine.sync_engine, "checkin", engine_mod._reset_rls_on_checkin)

    async with engine.begin() as conn:
        privileged = (
            await conn.execute(
                text(
                    "SELECT rolsuper OR rolbypassrls FROM pg_roles " "WHERE rolname = current_user"
                )
            )
        ).scalar()
        if privileged:
            await engine.dispose()
            pytest.skip(
                "POSTGRES_RLS_TEST_URL role is superuser/bypassrls; "
                "RLS would be bypassed and the test cannot prove isolation"
            )
        # Seed BEFORE forcing RLS (the owner has no INSERT policy under FORCE).
        await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await conn.execute(
            text(
                f"CREATE TABLE {TABLE} ("
                "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),"
                "  org_id uuid NOT NULL,"
                "  name text NOT NULL)"
            )
        )
        await conn.execute(
            text(f"INSERT INTO {TABLE} (org_id, name) VALUES (:a, 'A-secret'), (:b, 'B-secret')"),
            {"a": ORG_A, "b": ORG_B},
        )
        await conn.execute(
            text(
                f"CREATE POLICY {TABLE}_iso ON {TABLE} "
                "USING (org_id::text = current_setting('app.current_org_id', true))"
            )
        )
        await conn.execute(text(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY"))
        await conn.execute(text(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY"))

    mgr = DatabaseSessionManager()
    mgr._engine = engine
    mgr._sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield mgr
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await engine.dispose()


async def test_scoped_sessions_do_not_bleed_across_pool(manager):
    async with manager.session(org_id=ORG_A) as s:
        assert await _names(s) == {"A-secret"}
    # Same physical connection (pool_size=1) -> must now see ONLY org B.
    async with manager.session(org_id=ORG_B) as s:
        assert await _names(s) == {"B-secret"}, "org context bled across the pooled connection"


async def test_no_org_session_is_fail_closed_after_scoped(manager):
    async with manager.session(org_id=ORG_A) as s:
        assert await _names(s) == {"A-secret"}
    # A no-org session must inherit NOTHING from the previous tenant.
    async with manager.session() as s:
        assert await _names(s) == set(), "no-org session inherited a stale org context"


async def test_reset_survives_exception_in_session(manager):
    # This is the fix's headline value: even when the session's finally reset is
    # disrupted, the pool checkin hook still clears the context.
    with pytest.raises(RuntimeError):
        async with manager.session(org_id=ORG_A) as s:
            assert await _names(s) == {"A-secret"}
            raise RuntimeError("boom inside session")
    async with manager.session() as s:
        assert await _names(s) == set()
    async with manager.session(org_id=ORG_B) as s:
        assert await _names(s) == {"B-secret"}
