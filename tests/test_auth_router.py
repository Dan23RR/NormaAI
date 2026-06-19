"""Tests for the authentication router (src/auth/router.py).

Endpoints under test (mounted at /api/v1/auth/*):
- POST /api/v1/auth/register  -> create org+user, return TokenPair (201)
- POST /api/v1/auth/login     -> authenticate, return TokenPair (200)
- POST /api/v1/auth/refresh   -> rotate refresh token (200)
- POST /api/v1/auth/logout    -> blacklist the access token (204)
- GET  /api/v1/auth/me        -> current user profile (200)

Coverage goals (asserting REAL behavior read from the source):
- register happy path returns an access/refresh token pair (201)
- duplicate email (DB IntegrityError) -> 409
- register validation errors (short password / bad email) -> 422
- login happy path returns a token pair (200)
- login wrong password -> 401
- login unknown email -> 401 (constant-time dummy-hash path)
- login on a deactivated account -> 403
- brute-force lockout wiring: a lockout message from brute_force -> 429
- refresh rotates the token (issues a NEW pair, blacklists the old jti)
- refresh with an access token (wrong type) -> 401
- refresh reuse of a blacklisted token -> 401 + family revoked
- refresh with a garbage token -> 401
- logout with no token -> 401; logout with a valid token -> 204 + blacklisted
- /me happy path returns the profile; /me without a token -> 401

Pattern notes
-------------
The auth router takes its DB session via ``Depends(get_db_session)``, so the
fake async session is injected through ``app.dependency_overrides`` (preferred
over deep import patching). The ``brute_force`` and ``token_blacklist``
singletons are swapped for in-memory fakes via ``patch`` for the duration of a
single request.

Isolation: this file imports ``src.api.main`` like test_leads.py /
test_gdpr_router.py (bare ``TestClient(app)``, no lifespan, rate limiting off).
The ``app_objects`` fixture clears ``app.dependency_overrides`` on teardown, and
an autouse fixture evicts the ``src.api.main`` / router / ``src.auth.router``
modules from ``sys.modules`` after each test (mirroring test_critical_routers.py)
so the REAL ``src.db.engine`` binding cached here never leaks into the
sys.modules-patching isolation used by test_leads / test_api_integration.
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
)

# ──────────────────────────────────────────────────────────────────────────
#  Module-cache isolation (mirrors test_critical_routers.py)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """Importing ``src.api.main`` caches it + the router submodules bound to the
    REAL ``src.db.engine``. test_leads / test_api_integration re-import those
    fresh against a MagicMock engine via sys.modules patching, so we must evict
    the modules this file cached, or a later leads test would spuriously raise
    "DatabaseSessionManager is not initialized"."""
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


# ──────────────────────────────────────────────────────────────────────────
#  Fake async DB session
# ──────────────────────────────────────────────────────────────────────────


class _FakeResult:
    """Result of an awaited ``session.execute(stmt)``.

    Supports the two access shapes the auth router uses:
      - login/refresh:  ``.scalar_one_or_none()``  (a single User or None)
      - /me:            ``.one_or_none()``          (a (User, Organization) row)
    """

    def __init__(self, *, scalar=None, row=None) -> None:
        self._scalar = scalar
        self._row = row

    def scalar_one_or_none(self):
        return self._scalar

    def one_or_none(self):
        return self._row


class _FakeSession:
    """Minimal stand-in for an SQLAlchemy AsyncSession used by the auth router.

    ``execute`` returns a pre-seeded result (the caller decides what a SELECT
    yields). ``add`` records objects; ``flush``/``commit``/``rollback``/``refresh``
    are no-ops unless ``commit_error`` is set (to simulate a UNIQUE violation).
    """

    def __init__(self, *, result: _FakeResult | None = None, commit_error: Exception | None = None):
        self._result = result or _FakeResult()
        self._commit_error = commit_error
        self.added: list = []
        self.committed = False
        self.rolled_back = False

    async def execute(self, *_args, **_kwargs):
        return self._result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        if self._commit_error is not None:
            raise self._commit_error
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def refresh(self, _obj):
        pass


# ──────────────────────────────────────────────────────────────────────────
#  Fake brute-force + token blacklist singletons
# ──────────────────────────────────────────────────────────────────────────


class _FakeBruteForce:
    """check_and_increment returns ``lockout_msg`` (None => allowed)."""

    def __init__(self, lockout_msg: str | None = None):
        self.lockout_msg = lockout_msg
        self.reset_called_with: str | None = None

    async def check_and_increment(self, email: str, ip: str) -> str | None:
        return self.lockout_msg

    async def reset(self, email: str) -> None:
        self.reset_called_with = email


class _FakeBlacklist:
    """In-memory token blacklist mirroring the real TokenBlacklist contract."""

    def __init__(self) -> None:
        self.jtis: set[str] = set()
        self.families: set[str] = set()

    async def blacklist_token(self, jti: str, _expires_at) -> bool:
        self.jtis.add(jti)
        return True

    async def blacklist_token_family(self, family: str) -> bool:
        self.families.add(family)
        return True

    async def is_blacklisted(self, jti: str, family: str | None = None) -> bool:
        if jti in self.jtis:
            return True
        if family and family in self.families:
            return True
        return False


# ──────────────────────────────────────────────────────────────────────────
#  Fake ORM objects (the router never relies on DB-generated ids for tokens)
# ──────────────────────────────────────────────────────────────────────────


class _FakeUser:
    def __init__(
        self,
        *,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        email: str,
        password: str,
        role: str = "admin",
        is_active: bool = True,
        name: str = "Tester",
    ):
        self.id = user_id
        self.org_id = org_id
        self.email = email
        self.name = name
        self.hashed_password = hash_password(password)
        self.role = role
        self.is_active = is_active


class _FakeOrg:
    def __init__(self, *, org_id: uuid.UUID, name: str = "Acme Srl"):
        self.id = org_id
        self.name = name


# ──────────────────────────────────────────────────────────────────────────
#  App / client fixtures (bare app, no lifespan, rate-limit disabled)
# ──────────────────────────────────────────────────────────────────────────


@pytest.fixture
def app_objects():
    """Import the FastAPI app with heavy lifespan deps mocked (mirrors
    test_leads.py / test_gdpr_router.py). Clears ``app.dependency_overrides``
    on teardown so injected fakes never leak into sibling test files."""
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
            yield app
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    return TestClient(app_objects)


@pytest.fixture
def override_db(app_objects):
    """Return a helper that overrides ``get_db_session`` with a given fake
    session for the duration of the test (cleared by app_objects teardown)."""
    # get_db_session is patched out via sys.modules (src.db.engine -> MagicMock)
    # in app_objects, but the router captured the REAL function object at import
    # time as its Depends marker. Override the real symbol the router depends on.
    from src.auth.router import get_db_session

    def _apply(session: _FakeSession):
        async def _fake_get_db_session():
            yield session

        app_objects.dependency_overrides[get_db_session] = _fake_get_db_session
        return session

    return _apply


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def user_id():
    return uuid.uuid4()


# ──────────────────────────────────────────────────────────────────────────
#  Register
# ──────────────────────────────────────────────────────────────────────────


class TestRegister:
    def test_register_success_returns_token_pair(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "founder@acme.com",
                "password": "supersecret123",
                "name": "Founder",
                "organization_name": "Acme Srl",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        # Tokens are well-formed and distinct in type.
        assert decode_token(body["access_token"]).type == "access"
        assert decode_token(body["refresh_token"]).type == "refresh"

    def test_register_duplicate_email_returns_409(self, client, override_db):
        from sqlalchemy.exc import IntegrityError

        # The DB UNIQUE constraint surfaces as IntegrityError on commit().
        err = IntegrityError("INSERT", {}, Exception("unique violation"))
        session = override_db(_FakeSession(commit_error=err))

        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "dupe@acme.com",
                "password": "supersecret123",
                "name": "Dupe",
                "organization_name": "Acme Srl",
            },
        )
        assert r.status_code == 409
        assert "already registered" in r.json()["detail"].lower()
        # The handler rolled back after the integrity error.
        assert session.rolled_back is True

    def test_register_short_password_returns_422(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "x@acme.com",
                "password": "short",  # < min_length 8
                "name": "X",
                "organization_name": "Acme",
            },
        )
        assert r.status_code == 422

    def test_register_invalid_email_returns_422(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "supersecret123",
                "name": "X",
                "organization_name": "Acme",
            },
        )
        assert r.status_code == 422

    def test_register_missing_organization_name_returns_422(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/register",
            json={
                "email": "x@acme.com",
                "password": "supersecret123",
                "name": "X",
            },
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Login
# ──────────────────────────────────────────────────────────────────────────


class TestLogin:
    def test_login_success_returns_token_pair(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        bf = _FakeBruteForce(lockout_msg=None)

        with patch("src.auth.brute_force.brute_force", bf):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": "founder@acme.com", "password": "supersecret123"},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["access_token"]
        assert body["refresh_token"]
        # The token sub is the real user id (not "None").
        assert decode_token(body["access_token"]).sub == str(user_id)
        # Successful login resets the brute-force counter.
        assert bf.reset_called_with == "founder@acme.com"

    def test_login_wrong_password_returns_401(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        bf = _FakeBruteForce(lockout_msg=None)

        with patch("src.auth.brute_force.brute_force", bf):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": "founder@acme.com", "password": "WRONG-password"},
            )

        assert r.status_code == 401
        assert "invalid email or password" in r.json()["detail"].lower()
        # On a failed login the counter is NOT reset.
        assert bf.reset_called_with is None

    def test_login_unknown_email_returns_clean_401(self, app_objects, override_db):
        # Anti-enumeration guard: for an UNKNOWN email the handler runs
        # verify_password against a VALID dummy bcrypt hash, so a non-existent
        # user yields the SAME clean 401 + message as a wrong password for an
        # existing user -- the two are indistinguishable (no 500-vs-401 leak).
        # Regression test for the previously-invalid _dummy_hash that made
        # bcrypt.checkpw raise ValueError("Invalid salt") -> HTTP 500.
        from fastapi.testclient import TestClient

        override_db(_FakeSession(result=_FakeResult(scalar=None)))
        bf = _FakeBruteForce(lockout_msg=None)
        prod_client = TestClient(app_objects, raise_server_exceptions=False)

        with patch("src.auth.brute_force.brute_force", bf):
            r = prod_client.post(
                "/api/v1/auth/login",
                json={"email": "ghost@acme.com", "password": "whatever123"},
            )

        assert r.status_code == 401
        assert "invalid email or password" in r.json()["detail"].lower()

    def test_login_deactivated_account_returns_403(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id,
            org_id=org_id,
            email="dormant@acme.com",
            password="supersecret123",
            is_active=False,
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        bf = _FakeBruteForce(lockout_msg=None)

        with patch("src.auth.brute_force.brute_force", bf):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": "dormant@acme.com", "password": "supersecret123"},
            )

        assert r.status_code == 403
        assert "deactivated" in r.json()["detail"].lower()

    def test_login_brute_force_lockout_returns_429(self, client, override_db, user_id, org_id):
        # A non-None lockout message from brute_force short-circuits with 429,
        # BEFORE any DB query / password check.
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        bf = _FakeBruteForce(lockout_msg="Too many failed login attempts. Account locked.")

        with patch("src.auth.brute_force.brute_force", bf):
            r = client.post(
                "/api/v1/auth/login",
                json={"email": "founder@acme.com", "password": "supersecret123"},
            )

        assert r.status_code == 429
        assert "locked" in r.json()["detail"].lower()
        # Lockout path must not reset the counter.
        assert bf.reset_called_with is None

    def test_login_invalid_email_format_returns_422(self, client, override_db):
        override_db(_FakeSession())
        r = client.post(
            "/api/v1/auth/login",
            json={"email": "not-an-email", "password": "whatever"},
        )
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Refresh (token rotation)
# ──────────────────────────────────────────────────────────────────────────


class TestRefresh:
    def test_refresh_rotates_token(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        blacklist = _FakeBlacklist()

        refresh = create_refresh_token(user_id, org_id, "admin")
        old = decode_token(refresh)

        with patch("src.auth.router.token_blacklist", blacklist):
            r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})

        assert r.status_code == 200
        body = r.json()
        new_refresh = decode_token(body["refresh_token"])
        # A NEW refresh token was issued (different jti)...
        assert new_refresh.jti != old.jti
        # ...within the SAME family (rotation, not a new family).
        assert new_refresh.family == old.family
        # The OLD refresh jti is now blacklisted (rotation invalidates it).
        assert old.jti in blacklist.jtis

    def test_refresh_with_access_token_returns_401(self, client, override_db, user_id, org_id):
        override_db(_FakeSession(result=_FakeResult(scalar=None)))
        access = create_access_token(user_id, org_id, "admin")

        with patch("src.auth.router.token_blacklist", _FakeBlacklist()):
            r = client.post("/api/v1/auth/refresh", json={"refresh_token": access})

        assert r.status_code == 401
        assert "refresh token" in r.json()["detail"].lower()

    def test_refresh_reuse_revokes_family(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        override_db(_FakeSession(result=_FakeResult(scalar=user)))
        blacklist = _FakeBlacklist()

        refresh = create_refresh_token(user_id, org_id, "admin")
        tok = decode_token(refresh)
        # Simulate the token already having been used (its jti is blacklisted).
        blacklist.jtis.add(tok.jti)

        with patch("src.auth.router.token_blacklist", blacklist):
            r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})

        assert r.status_code == 401
        assert "revoked" in r.json()["detail"].lower()
        # Reuse detection blacklists the WHOLE family (compromise response).
        assert tok.family in blacklist.families

    def test_refresh_garbage_token_returns_401(self, client, override_db):
        override_db(_FakeSession())
        with patch("src.auth.router.token_blacklist", _FakeBlacklist()):
            r = client.post("/api/v1/auth/refresh", json={"refresh_token": "not-a-jwt"})
        assert r.status_code == 401
        assert "invalid or expired" in r.json()["detail"].lower()

    def test_refresh_user_gone_returns_401(self, client, override_db, user_id, org_id):
        # Valid, non-reused refresh token but the user no longer exists.
        override_db(_FakeSession(result=_FakeResult(scalar=None)))
        refresh = create_refresh_token(user_id, org_id, "admin")

        with patch("src.auth.router.token_blacklist", _FakeBlacklist()):
            r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})

        assert r.status_code == 401
        assert "not found" in r.json()["detail"].lower()

    def test_refresh_missing_field_returns_422(self, client, override_db):
        override_db(_FakeSession())
        r = client.post("/api/v1/auth/refresh", json={})
        assert r.status_code == 422


# ──────────────────────────────────────────────────────────────────────────
#  Logout
# ──────────────────────────────────────────────────────────────────────────


class TestLogout:
    def test_logout_without_token_returns_401(self, client):
        r = client.post("/api/v1/auth/logout")
        assert r.status_code == 401
        assert "no token" in r.json()["detail"].lower()

    def test_logout_blacklists_token_returns_204(self, client, user_id, org_id):
        access = create_access_token(user_id, org_id, "admin")
        tok = decode_token(access)
        blacklist = _FakeBlacklist()

        with patch("src.auth.router.token_blacklist", blacklist):
            r = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert r.status_code == 204
        # The access token's jti is now blacklisted.
        assert tok.jti in blacklist.jtis

    def test_logout_invalid_token_is_noop_204(self, client):
        # decode_token raises ValueError -> handler returns (204) without raising.
        blacklist = _FakeBlacklist()
        with patch("src.auth.router.token_blacklist", blacklist):
            r = client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": "Bearer garbage-token"},
            )
        assert r.status_code == 204
        # Nothing was blacklisted for an undecodable token.
        assert blacklist.jtis == set()


# ──────────────────────────────────────────────────────────────────────────
#  /me
# ──────────────────────────────────────────────────────────────────────────


class TestMe:
    def test_me_without_token_returns_401(self, client):
        r = client.get("/api/v1/auth/me")
        assert r.status_code == 401

    def test_me_invalid_token_returns_401(self, client):
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_me_happy_path_returns_profile(self, client, override_db, user_id, org_id):
        user = _FakeUser(
            user_id=user_id, org_id=org_id, email="founder@acme.com", password="supersecret123"
        )
        org = _FakeOrg(org_id=org_id, name="Acme Srl")
        override_db(_FakeSession(result=_FakeResult(row=(user, org))))
        access = create_access_token(user_id, org_id, "admin")

        with patch("src.auth.router.token_blacklist", _FakeBlacklist()):
            r = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert r.status_code == 200
        body = r.json()
        assert body["id"] == str(user_id)
        assert body["email"] == "founder@acme.com"
        assert body["organization_name"] == "Acme Srl"
        assert body["role"] == "admin"

    def test_me_user_not_found_returns_404(self, client, override_db, user_id, org_id):
        # Valid token, but the join yields no row (user deleted) -> 404.
        override_db(_FakeSession(result=_FakeResult(row=None)))
        access = create_access_token(user_id, org_id, "admin")

        with patch("src.auth.router.token_blacklist", _FakeBlacklist()):
            r = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {access}"},
            )

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()
