"""Registration mode + invite codes.

Covers:
- settings.registration_mode: default ``invite``, validation of the literal
- POST /api/v1/auth/register under the three modes (closed -> 403, invite ->
  needs a pending code, open -> unchanged + a supplied code is still validated)
- invite redemption: org-less invite founds a new org (role admin), org invite
  joins it (invite role), the redemption UPDATE is conditional (race-safe) and
  runs BEFORE the user row is created, a lost race -> 403
- POST/GET /api/v1/auth/invites: admin-only, own-org by default, staff-only
  for other organizations / org-less invites, validation, listing scope
- the invite helpers (code hashing, status) and the 008 migration metadata

Pattern notes
-------------
Same bare-app + ``dependency_overrides`` pattern as tests/test_auth_router.py.
The fake session dispatches on the statement type so a SELECT on invites,
a SELECT on organizations and the redemption UPDATE can each be scripted.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.sql import Select, Update

from src.auth.invites import (
    INVALID_INVITE_DETAIL,
    REGISTRATIONS_CLOSED_DETAIL,
    find_redeemable_invite,
    generate_invite_code,
    hash_invite_code,
    invite_status,
    new_invite,
)
from src.auth.security import create_access_token, decode_token
from src.config import Settings
from src.db.models import Invite, Organization, User

STAFF_EMAIL = "ops@normaai.org"

# ──────────────────────────────────────────────────────────────────────────
#  Module-cache isolation (mirrors test_auth_router.py)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_module_cache():
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


# ──────────────────────────────────────────────────────────────────────────
#  Fakes
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None, rowcount: int = 0) -> None:
        self._scalar = scalar
        self._rows = rows or []
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Statement-aware fake AsyncSession.

    - SELECT ... FROM invites        -> the configured ``invite`` (or None)
    - SELECT ... FROM organizations  -> an id when ``org_exists``
    - UPDATE invites                 -> ``update_rowcount`` (1 = redeemed)
    ``flush`` assigns ids to added rows that lack one (like the real flush).
    """

    def __init__(
        self,
        *,
        invite: Invite | None = None,
        invites: list[Invite] | None = None,
        org_exists: bool = True,
        update_rowcount: int = 1,
        commit_error: Exception | None = None,
    ) -> None:
        self.invite = invite
        self.invites = invites if invites is not None else ([invite] if invite else [])
        self.org_exists = org_exists
        self.update_rowcount = update_rowcount
        self.commit_error = commit_error
        self.added: list = []
        self.statements: list = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt, *_a, **_k):
        self.statements.append(stmt)
        if isinstance(stmt, Update):
            return _FakeResult(rowcount=self.update_rowcount)
        if isinstance(stmt, Select):
            sql = str(stmt).lower()
            if "from invites" in sql:
                return _FakeResult(scalar=self.invite, rows=self.invites)
            if "from organizations" in sql:
                return _FakeResult(scalar=uuid.uuid4() if self.org_exists else None)
        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        if self.commit_error is not None:
            raise self.commit_error
        await self.flush()
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, obj):
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(UTC)

    # Helpers for assertions
    @property
    def updates(self) -> list:
        return [s for s in self.statements if isinstance(s, Update)]

    def added_of(self, cls):
        return [o for o in self.added if isinstance(o, cls)]


def _pending_invite(org_id: uuid.UUID | None, email: str = "invitee@acme.com", role="member"):
    invite, code = new_invite(email=email, org_id=org_id, role=role)
    return invite, code


# ──────────────────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app, limiter

        limiter.enabled = False
        try:
            yield app
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    return TestClient(app_objects)


@pytest.fixture
def override_db(app_objects):
    from src.auth.router import get_db_session

    def _apply(session: _FakeSession) -> _FakeSession:
        async def _fake():
            yield session

        app_objects.dependency_overrides[get_db_session] = _fake
        return session

    return _apply


@pytest.fixture
def mode(app_objects):
    """Patch the registration mode seen by the auth router."""
    from src.config import get_settings

    def _apply(value: str):
        patched = get_settings().model_copy(update={"registration_mode": value})
        cm = patch("src.auth.router.get_settings", return_value=patched)
        cm.start()
        _cms.append(cm)
        return patched

    _cms: list = []
    yield _apply
    for cm in _cms:
        cm.stop()


@pytest.fixture
def staff_settings():
    """Make STAFF_EMAIL staff for the duration of the test."""
    from src.config import get_settings

    patched = get_settings().model_copy(update={"staff_emails": [STAFF_EMAIL]})
    with patch("src.auth.dependencies.get_settings", return_value=patched):
        yield patched


def _headers(role="admin", email=None, org_id=None, user_id=None):
    token = create_access_token(user_id or uuid.uuid4(), org_id or uuid.uuid4(), role, email=email)
    return {"Authorization": f"Bearer {token}"}


def _register_body(**overrides) -> dict:
    body = {
        "email": "invitee@acme.com",
        "password": "supersecret123",
        "name": "Invitee",
        "organization_name": "Acme Srl",
    }
    body.update(overrides)
    return body


# ──────────────────────────────────────────────────────────────────────────
#  Settings
# ──────────────────────────────────────────────────────────────────────────


class TestRegistrationModeSetting:
    def test_default_is_invite(self, monkeypatch):
        monkeypatch.delenv("REGISTRATION_MODE", raising=False)
        assert Settings(_env_file=None, app_secret_key="x" * 40).registration_mode == "invite"

    def test_invalid_mode_rejected(self, monkeypatch):
        monkeypatch.delenv("REGISTRATION_MODE", raising=False)
        with pytest.raises(Exception):
            Settings(_env_file=None, app_secret_key="x" * 40, registration_mode="anyone")

    def test_suite_runs_in_open_mode(self):
        # conftest pins the suite to open mode so legacy register tests still pass.
        from src.config import get_settings

        assert get_settings().registration_mode == "open"


# ──────────────────────────────────────────────────────────────────────────
#  Invite helpers
# ──────────────────────────────────────────────────────────────────────────


class TestInviteHelpers:
    def test_code_is_unguessable_and_hash_is_sha256(self):
        code = generate_invite_code()
        assert len(code) >= 30 and code != generate_invite_code()
        assert hash_invite_code(f"  {code} ") == hashlib.sha256(code.encode()).hexdigest()

    def test_new_invite_stores_hash_not_code(self):
        invite, code = new_invite(email="Someone@Acme.com", org_id=None)
        assert invite.code_hash == hash_invite_code(code)
        assert code not in (invite.code_hash, invite.email)
        assert invite.email == "someone@acme.com"  # normalised
        assert invite.role == "member"
        assert invite_status(invite) == "pending"
        assert timedelta(days=13) < invite.expires_at - datetime.now(UTC) <= timedelta(days=14)

    def test_status_used_wins_over_expired(self):
        invite, _ = new_invite(email="a@b.io", org_id=None)
        invite.expires_at = datetime.now(UTC) - timedelta(days=1)
        assert invite_status(invite) == "expired"
        invite.used_at = datetime.now(UTC)
        assert invite_status(invite) == "used"

    def test_status_handles_naive_datetimes(self):
        invite, _ = new_invite(email="a@b.io", org_id=None)
        invite.expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        assert invite_status(invite) == "pending"

    async def test_find_redeemable_skips_query_for_blank_code(self):
        session = _FakeSession()
        assert await find_redeemable_invite(session, None) is None
        assert await find_redeemable_invite(session, "   ") is None
        assert session.statements == []

    async def test_find_redeemable_rejects_used_and_expired(self):
        invite, code = new_invite(email="a@b.io", org_id=None)
        assert await find_redeemable_invite(_FakeSession(invite=invite), code) is invite
        invite.used_at = datetime.now(UTC)
        assert await find_redeemable_invite(_FakeSession(invite=invite), code) is None


# ──────────────────────────────────────────────────────────────────────────
#  Register: modes
# ──────────────────────────────────────────────────────────────────────────


class TestRegisterModes:
    def test_closed_mode_returns_403(self, client, override_db, mode):
        mode("closed")
        session = override_db(_FakeSession())
        r = client.post("/api/v1/auth/register", json=_register_body())
        assert r.status_code == 403
        assert r.json()["detail"] == REGISTRATIONS_CLOSED_DETAIL == "Le registrazioni sono chiuse."
        assert session.added == []

    def test_invite_mode_without_code_returns_403(self, client, override_db, mode):
        mode("invite")
        session = override_db(_FakeSession())
        r = client.post("/api/v1/auth/register", json=_register_body())
        assert r.status_code == 403
        assert (
            r.json()["detail"] == INVALID_INVITE_DETAIL == "Codice di invito non valido o scaduto."
        )
        assert session.added == []

    def test_invite_mode_unknown_code_returns_403(self, client, override_db, mode):
        mode("invite")
        override_db(_FakeSession(invite=None))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code="nope"))
        assert r.status_code == 403
        assert r.json()["detail"] == INVALID_INVITE_DETAIL

    @pytest.mark.parametrize("state", ["expired", "used"])
    def test_invite_mode_rejects_expired_or_used_code(self, client, override_db, mode, state):
        mode("invite")
        invite, code = _pending_invite(None)
        if state == "expired":
            invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        else:
            invite.used_at = datetime.now(UTC)
        session = override_db(_FakeSession(invite=invite))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code=code))
        assert r.status_code == 403
        assert session.updates == []  # never tried to redeem

    def test_orgless_invite_founds_new_org_as_admin(self, client, override_db, mode):
        mode("invite")
        invite, code = _pending_invite(None)
        session = override_db(_FakeSession(invite=invite))

        r = client.post("/api/v1/auth/register", json=_register_body(invite_code=code))

        assert r.status_code == 201
        (org,) = session.added_of(Organization)
        (user,) = session.added_of(User)
        assert org.name == "Acme Srl"
        assert user.role == "admin"
        assert user.org_id == org.id
        assert session.committed is True
        # Redeemed exactly once, conditionally, and recorded the NEW user's id.
        (upd,) = session.updates
        params = upd.compile().params
        assert params["used_by"] == user.id
        assert "invites.used_at IS NULL" in str(upd)
        # Redemption ran BEFORE the user row was added (RLS ordering).
        assert session.statements.index(upd) >= 0 and user in session.added
        assert decode_token(r.json()["access_token"]).sub == str(user.id)

    def test_org_invite_joins_org_with_invite_role(self, client, override_db, mode):
        mode("invite")
        org_id = uuid.uuid4()
        invite, code = _pending_invite(org_id, role="member")
        session = override_db(_FakeSession(invite=invite))

        # organization_name is not needed when joining an existing organization.
        body = _register_body(invite_code=code)
        body.pop("organization_name")
        r = client.post("/api/v1/auth/register", json=body)

        assert r.status_code == 201
        assert session.added_of(Organization) == []  # no new org
        (user,) = session.added_of(User)
        assert user.org_id == org_id
        assert user.role == "member"
        assert decode_token(r.json()["access_token"]).org_id == str(org_id)

    def test_lost_redemption_race_returns_403_and_rolls_back(self, client, override_db, mode):
        mode("invite")
        invite, code = _pending_invite(None)
        session = override_db(_FakeSession(invite=invite, update_rowcount=0))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code=code))
        assert r.status_code == 403
        assert r.json()["detail"] == INVALID_INVITE_DETAIL
        assert session.rolled_back is True
        assert session.committed is False
        assert session.added_of(User) == []

    def test_duplicate_email_with_invite_returns_409(self, client, override_db, mode):
        from sqlalchemy.exc import IntegrityError

        mode("invite")
        invite, code = _pending_invite(None)
        err = IntegrityError("INSERT", {}, Exception("unique violation"))
        session = override_db(_FakeSession(invite=invite, commit_error=err))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code=code))
        assert r.status_code == 409
        assert session.rolled_back is True

    def test_open_mode_unchanged_without_code(self, client, override_db, mode):
        mode("open")
        session = override_db(_FakeSession())
        r = client.post("/api/v1/auth/register", json=_register_body())
        assert r.status_code == 201
        (org,) = session.added_of(Organization)
        (user,) = session.added_of(User)
        assert user.role == "admin" and user.org_id == org.id
        assert session.updates == []  # no invite involved
        assert "from invites" not in " ".join(str(s).lower() for s in session.statements)

    def test_open_mode_validates_a_supplied_code(self, client, override_db, mode):
        mode("open")
        override_db(_FakeSession(invite=None))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code="bogus"))
        assert r.status_code == 403
        assert r.json()["detail"] == INVALID_INVITE_DETAIL

    def test_open_mode_honours_org_invite(self, client, override_db, mode):
        mode("open")
        org_id = uuid.uuid4()
        invite, code = _pending_invite(org_id, role="viewer")
        session = override_db(_FakeSession(invite=invite))
        r = client.post("/api/v1/auth/register", json=_register_body(invite_code=code))
        assert r.status_code == 201
        (user,) = session.added_of(User)
        assert (user.org_id, user.role) == (org_id, "viewer")

    def test_new_org_requires_organization_name(self, client, override_db, mode):
        mode("open")
        override_db(_FakeSession())
        body = _register_body()
        body.pop("organization_name")
        r = client.post("/api/v1/auth/register", json=body)
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Invite endpoints
# ──────────────────────────────────────────────────────────────────────────


class TestCreateInvite:
    def test_requires_auth(self, client):
        assert client.post("/api/v1/auth/invites", json={"email": "a@b.io"}).status_code == 401

    def test_member_is_forbidden(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites", json={"email": "a@b.io"}, headers=_headers(role="member")
        )
        assert r.status_code == 403

    def test_admin_invites_into_own_org(self, client, override_db):
        org_id = uuid.uuid4()
        admin_id = uuid.uuid4()
        session = override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "CFO@Acme.com"},
            headers=_headers(org_id=org_id, user_id=admin_id),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["organization_id"] == str(org_id)
        assert body["email"] == "cfo@acme.com"
        assert body["role"] == "member"
        assert body["status"] == "pending"
        assert len(body["code"]) >= 30
        (invite,) = session.added_of(Invite)
        assert invite.code_hash == hash_invite_code(body["code"])
        assert invite.created_by == admin_id
        assert session.committed is True
        # Only the hash is persisted.
        assert body["code"] != invite.code_hash

    def test_admin_cannot_mint_new_org_invite(self, client, override_db):
        session = override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "new_organization": True},
            headers=_headers(),
        )
        assert r.status_code == 403
        assert r.json()["detail"] == "Operazione riservata al personale NormaAI."
        assert session.added == []

    def test_admin_cannot_target_other_org(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "organization_id": str(uuid.uuid4())},
            headers=_headers(),
        )
        assert r.status_code == 403

    def test_staff_mints_new_org_invite_as_admin_role(self, client, override_db, staff_settings):
        session = override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "founder@new.io", "new_organization": True, "role": "viewer"},
            headers=_headers(email=STAFF_EMAIL),
        )
        assert r.status_code == 201, r.text
        assert r.json()["organization_id"] is None
        assert r.json()["role"] == "admin"  # founder of the new org, whatever was asked
        (invite,) = session.added_of(Invite)
        assert invite.org_id is None

    def test_staff_targets_other_existing_org(self, client, override_db, staff_settings):
        other = uuid.uuid4()
        override_db(_FakeSession(org_exists=True))
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "organization_id": str(other), "role": "admin"},
            headers=_headers(email=STAFF_EMAIL),
        )
        assert r.status_code == 201
        assert r.json()["organization_id"] == str(other)
        assert r.json()["role"] == "admin"

    def test_staff_unknown_org_is_404(self, client, override_db, staff_settings):
        override_db(_FakeSession(org_exists=False))
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "organization_id": str(uuid.uuid4())},
            headers=_headers(email=STAFF_EMAIL),
        )
        assert r.status_code == 404

    @pytest.mark.parametrize("days", [0, 91])
    def test_expiry_bounds(self, client, override_db, days):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "expires_in_days": days},
            headers=_headers(),
        )
        assert r.status_code == 422

    def test_custom_expiry_and_role(self, client, override_db):
        session = override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/invites",
            json={"email": "a@b.io", "expires_in_days": 3, "role": "viewer"},
            headers=_headers(),
        )
        assert r.status_code == 201
        (invite,) = session.added_of(Invite)
        assert invite.role == "viewer"
        assert timedelta(days=2) < invite.expires_at - datetime.now(UTC) <= timedelta(days=3)


class TestListInvites:
    def test_requires_admin(self, client, override_db):
        override_db(_FakeSession())
        assert client.get("/api/v1/auth/invites").status_code == 401
        assert (
            client.get("/api/v1/auth/invites", headers=_headers(role="member")).status_code == 403
        )

    def test_admin_sees_only_own_org(self, client, override_db):
        org_id = uuid.uuid4()
        own, _ = _pending_invite(org_id)
        used, _ = _pending_invite(org_id, email="old@acme.com")
        used.used_at = datetime.now(UTC)
        session = override_db(_FakeSession(invites=[own, used]))

        r = client.get("/api/v1/auth/invites", headers=_headers(org_id=org_id))

        assert r.status_code == 200, r.text
        statuses = {row["email"]: row["status"] for row in r.json()}
        assert statuses == {"invitee@acme.com": "pending", "old@acme.com": "used"}
        assert all("code" not in row for row in r.json())  # never re-exposed
        (stmt,) = session.statements
        assert "invites.org_id = " in str(stmt)  # scoped to the caller's org

    def test_staff_lists_everything(self, client, override_db, staff_settings):
        invite, _ = _pending_invite(None)
        session = override_db(_FakeSession(invites=[invite]))
        r = client.get("/api/v1/auth/invites", headers=_headers(email=STAFF_EMAIL))
        assert r.status_code == 200
        assert r.json()[0]["organization_id"] is None
        (stmt,) = session.statements
        assert "invites.org_id = " not in str(stmt)


# ──────────────────────────────────────────────────────────────────────────
#  Migration metadata
# ──────────────────────────────────────────────────────────────────────────


def test_migration_008_chain_and_contents():
    path = Path(__file__).resolve().parent.parent / "alembic" / "versions" / "008_invites.py"
    spec = importlib.util.spec_from_file_location("migration_008_invites", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "008_invites"
    assert module.down_revision == "006_lead_download_email_tracking"
    source = path.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "invites"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source and "FORCE ROW LEVEL SECURITY" in source
    assert "invites_no_org_context" in source
