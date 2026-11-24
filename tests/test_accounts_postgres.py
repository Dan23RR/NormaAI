"""Accounts on PostgreSQL, under row-level security: members, the account check,
the password reset.

Gated on ``POSTGRES_TEST_URL`` (the CI superuser): the fixture builds the
application's tables in a throw-away schema, with the row-level security of
migrations 007 and 009 on the tenant tables. The member operations then run as
the NON-superuser role of ``POSTGRES_RLS_TEST_URL`` (CI: ``rls_tester``, NOSUPERUSER
NOBYPASSRLS), the way the app runs in production, so the policies apply:

- removing a member works inside the organisation's tenant context and deletes
  the member's conversations, which the policies show only in that context;
- a member of another organisation is not reachable (404) and keeps everything;
- the last active admin is protected, with the organisation row locked;
- ``load_account`` reads the live state; a reset link works once (the
  conditional UPDATE on timestamptz).

Without the URLs the module skips, like tests/test_rls_pool_isolation.py.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.auth import dependencies as deps
from src.auth import members, password_reset
from src.db.engine import DatabaseSessionManager
from src.db.models import Assessment, Base, Client, Conversation, DocumentCheck, Organization, User

ADMIN_URL = os.environ.get("POSTGRES_TEST_URL")
RLS_URL = os.environ.get("POSTGRES_RLS_TEST_URL")

pytestmark = pytest.mark.skipif(not ADMIN_URL, reason="POSTGRES_TEST_URL not set")

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
TENANT_TABLES = ("clients", "assessments", "conversations", "document_checks")


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(f"migration_{filename[:3]}", VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _policies() -> list[str]:
    m007, m009 = _load("007_reconcile_schema.py"), _load("009_document_checks.py")
    statements = []
    for table in ("clients", "assessments", "conversations"):
        statements += list(m007.POLICIES[table].values())
    statements += list(m009.POLICIES["document_checks"].values())
    return statements


def _manager(url: str, schema: str) -> DatabaseSessionManager:
    engine = create_async_engine(url, connect_args={"server_settings": {"search_path": schema}})
    manager = DatabaseSessionManager()
    manager._engine = engine
    manager._sessionmaker = async_sessionmaker(bind=engine, expire_on_commit=False)
    return manager


def _role_of(url: str) -> str:
    from sqlalchemy.engine import make_url

    return str(make_url(url).username)


@pytest_asyncio.fixture
async def schema():
    name = f"acct_{uuid.uuid4().hex[:10]}"
    engine = create_async_engine(ADMIN_URL)
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA {name}"))
        await conn.execute(text(f"SET search_path TO {name}"))
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync.execution_options(schema_translate_map={None: name})
            )
        )
        for table in TENANT_TABLES:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
        for statement in _policies():
            await conn.execute(text(statement))
        if RLS_URL:
            role = _role_of(RLS_URL)
            await conn.execute(text(f"GRANT USAGE ON SCHEMA {name} TO {role}"))
            await conn.execute(
                text(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {name} TO {role}"
                )
            )
    try:
        yield name
    finally:
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
        await engine.dispose()


@pytest_asyncio.fixture
async def owner(schema):
    """Sessions as the superuser (bypasses RLS): to seed and to look."""
    manager = _manager(ADMIN_URL, schema)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def app_role(schema):
    """Sessions as the non-superuser role: row-level security applies."""
    if not RLS_URL:
        pytest.skip("POSTGRES_RLS_TEST_URL not set (needs a non-superuser role)")
    manager = _manager(RLS_URL, schema)
    async with manager.session() as session:
        privileged = (
            await session.execute(
                text("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar()
    if privileged:
        await manager.close()
        pytest.skip("POSTGRES_RLS_TEST_URL role bypasses RLS: it would prove nothing")
    yield manager
    await manager.close()


async def _seed(owner: DatabaseSessionManager) -> dict:
    ids = {name: uuid.uuid4() for name in ("alfa", "beta", "admin", "member", "beta_admin")}
    async with owner.session() as session:
        session.add_all(
            [
                Organization(id=ids["alfa"], name="Alfa", slug=f"alfa-{ids['alfa'].hex[:6]}"),
                Organization(id=ids["beta"], name="Beta", slug=f"beta-{ids['beta'].hex[:6]}"),
            ]
        )
        await session.flush()
        session.add_all(
            [
                User(
                    id=ids["admin"], org_id=ids["alfa"], email="a@alfa.it", name="A", role="admin"
                ),
                User(
                    id=ids["member"], org_id=ids["alfa"], email="m@alfa.it", name="M", role="member"
                ),
                User(
                    id=ids["beta_admin"],
                    org_id=ids["beta"],
                    email="a@beta.it",
                    name="B",
                    role="admin",
                ),
            ]
        )
        await session.flush()
        client_id = uuid.uuid4()
        session.add(Client(id=client_id, org_id=ids["alfa"], name="Acme"))
        await session.flush()
        session.add_all(
            [
                Conversation(id=uuid.uuid4(), user_id=ids["member"], messages=[]),
                Conversation(id=uuid.uuid4(), user_id=ids["beta_admin"], messages=[]),
                Assessment(
                    id=uuid.uuid4(),
                    client_id=client_id,
                    framework="GDPR",
                    assessed_by=ids["member"],
                ),
                DocumentCheck(
                    id=uuid.uuid4(),
                    org_id=ids["alfa"],
                    created_by=ids["member"],
                    filename="nota.txt",
                    document_sha256="0" * 64,
                    checked_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()
    return ids


async def _count(owner, model, **filters) -> int:
    async with owner.session() as session:
        stmt = select(model)
        for name, value in filters.items():
            stmt = stmt.where(getattr(model, name) == value)
        return len((await session.execute(stmt)).scalars().all())


async def test_removing_a_member_under_row_level_security(owner, app_role):
    ids = await _seed(owner)
    async with app_role.session(org_id=str(ids["alfa"])) as session:
        await members.remove_member(session, ids["alfa"], ids["member"])
        await session.commit()
    assert await _count(owner, User, id=ids["member"]) == 0
    assert await _count(owner, Conversation, user_id=ids["member"]) == 0
    assert await _count(owner, Conversation, user_id=ids["beta_admin"]) == 1
    async with owner.session() as session:
        assessed_by = (await session.execute(select(Assessment.assessed_by))).scalars().all()
        created_by = (await session.execute(select(DocumentCheck.created_by))).scalars().all()
    assert assessed_by == [None] and created_by == [None]


async def test_another_organisation_is_out_of_reach(owner, app_role):
    ids = await _seed(owner)
    async with app_role.session(org_id=str(ids["alfa"])) as session:
        with pytest.raises(members.MemberError) as exc:
            await members.remove_member(session, ids["alfa"], ids["beta_admin"])
        assert exc.value.status_code == 404
        # The policies hide the other organisation's conversations from this context.
        rows = (await session.execute(select(Conversation.user_id))).scalars().all()
        assert ids["beta_admin"] not in rows
    assert await _count(owner, User, id=ids["beta_admin"]) == 1


async def test_the_last_admin_stays(owner, app_role):
    ids = await _seed(owner)
    async with app_role.session(org_id=str(ids["alfa"])) as session:
        with pytest.raises(members.MemberError) as exc:
            await members.change_role(session, ids["alfa"], ids["admin"], "member")
        assert exc.value.status_code == 409
        await session.rollback()
        member, previous = await members.change_role(session, ids["alfa"], ids["member"], "admin")
        await session.commit()
    assert previous == "member" and member.role == "admin"
    async with app_role.session(org_id=str(ids["alfa"])) as session:
        await members.change_role(session, ids["alfa"], ids["admin"], "viewer")
        await session.commit()
    async with owner.session() as session:
        roles = dict((await session.execute(select(User.email, User.role))).all())
    assert roles["a@alfa.it"] == "viewer" and roles["m@alfa.it"] == "admin"


async def test_load_account_reads_the_live_state(owner, app_role):
    ids = await _seed(owner)
    revoked = datetime.now(UTC).replace(microsecond=0)
    async with owner.session() as session:
        user = await session.get(User, ids["admin"])
        user.is_staff = True
        user.sessions_revoked_at = revoked
        await session.commit()
    account = await deps.load_account(ids["admin"], manager=app_role)
    assert account is not None
    assert (account.org_id, account.role, account.is_staff) == (ids["alfa"], "admin", True)
    assert account.sessions_revoked_at == revoked
    assert await deps.load_account(uuid.uuid4(), manager=app_role) is None


async def test_a_reset_link_works_once(owner, app_role):
    ids = await _seed(owner)
    async with owner.session() as session:
        user = await session.get(User, ids["member"])
        token = password_reset.issue_link(user)
        await session.commit()
    async with app_role.session() as session:
        assert await password_reset.confirm_reset(session, token, "nuova-password-1") is not None
        await session.commit()
    async with app_role.session() as session:
        assert await password_reset.confirm_reset(session, token, "altra-password-2") is None
    async with owner.session() as session:
        user = await session.get(User, ids["member"])
        assert user.password_reset_token_hash is None
        assert user.sessions_revoked_at is not None
        assert user.sessions_revoked_at > datetime.now(UTC) - timedelta(minutes=1)
