"""Sessions: lifetimes, the absolute limit, and logout on the server.

- ACCESS_TOKEN_TTL (default 15 minutes) and REFRESH_TOKEN_TTL are the settings
  the tokens are minted with;
- a session (refresh family) carries its sign-in time through every rotation
  and cannot be refreshed after SESSION_MAX_LIFETIME_DAYS (default 30);
- a refresh token issued before ``users.sessions_revoked_at`` is refused;
- logout revokes the access token, its session (so every token of the family
  stops working) and the refresh token sent in the body, even when the access
  token has already expired; it never lets one user end another's session.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jose import jwt

from src.auth import security
from src.auth.security import (
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    issued_before,
    session_expires_at,
)
from src.config import Settings, get_settings


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


class _Blacklist:
    """In-memory stand-in of the Redis token blacklist."""

    def __init__(self) -> None:
        self.jtis: set[str] = set()
        self.families: set[str] = set()

    async def blacklist_token(self, jti, _expires_at) -> bool:
        self.jtis.add(jti)
        return True

    async def blacklist_token_family(self, family) -> bool:
        self.families.add(family)
        return True

    async def is_blacklisted(self, jti, family=None) -> bool:
        return jti in self.jtis or (family is not None and family in self.families)


class _User:
    def __init__(self, user_id, org_id, *, revoked_at=None):
        self.id = user_id
        self.org_id = org_id
        self.email = "anna@studio.it"
        self.role = "member"
        self.is_active = True
        self.email_verified = True
        self.is_staff = False
        self.sessions_revoked_at = revoked_at


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


class _Session:
    def __init__(self, user):
        self.user = user

    async def execute(self, *_args, **_kwargs):
        return _Result(self.user)


@pytest.fixture
def world():
    return {"user": None, "blacklist": _Blacklist()}


@pytest.fixture
def client(world):
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        mock_settings.return_value = get_settings()

        from fastapi.testclient import TestClient

        from src.api.main import app, limiter
        from src.auth import router

        async def _session():
            yield _Session(world["user"])

        limiter.enabled = False
        app.dependency_overrides[router.get_db_session] = _session
        with (
            patch.object(router, "token_blacklist", world["blacklist"]),
            patch("src.auth.dependencies.token_blacklist", world["blacklist"]),
        ):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


def _forge(claims: dict) -> str:
    """A validly signed token with chosen claims (as an attacker never can)."""
    payload = {"iss": security._get_jwt_issuer(), "aud": security._get_jwt_audience(), **claims}
    return jwt.encode(payload, security._get_signing_key(), algorithm=security.get_algorithm())


class TestLifetimes:
    def test_access_tokens_last_access_token_ttl(self):
        token = decode_token(create_access_token(uuid.uuid4(), uuid.uuid4(), "member"))
        assert get_settings().access_token_ttl == 900
        lifetime = (token.exp - token.iat).total_seconds()
        assert 899 <= lifetime <= 901

    def test_the_settings_are_read_from_the_documented_variables(self, monkeypatch):
        monkeypatch.setenv("ACCESS_TOKEN_TTL", "600")
        monkeypatch.setenv("REFRESH_TOKEN_TTL", "86400")
        monkeypatch.setenv("SESSION_MAX_LIFETIME_DAYS", "10")
        settings = Settings(_env_file=None, app_secret_key="x" * 40)
        assert (settings.access_token_ttl, settings.refresh_token_ttl) == (600, 86400)
        assert settings.session_max_lifetime_days == 10
        with patch("src.auth.security.get_settings", return_value=settings):
            pair = create_token_pair(uuid.uuid4(), uuid.uuid4(), "member")
        assert pair.expires_in == 600

    def test_the_defaults(self, monkeypatch):
        for name in ("ACCESS_TOKEN_TTL", "REFRESH_TOKEN_TTL", "SESSION_MAX_LIFETIME_DAYS"):
            monkeypatch.delenv(name, raising=False)
        settings = Settings(_env_file=None, app_secret_key="x" * 40)
        assert settings.access_token_ttl == 900
        assert settings.refresh_token_ttl == 604_800
        assert settings.session_max_lifetime_days == 30

    def test_a_pair_is_one_session(self):
        pair = create_token_pair(uuid.uuid4(), uuid.uuid4(), "member")
        access, refresh = decode_token(pair.access_token), decode_token(pair.refresh_token)
        assert access.sid and access.sid == refresh.family
        assert refresh.auth_time is not None

    def test_a_refresh_token_never_outlives_the_session(self):
        started = datetime.now(UTC) - timedelta(days=29, hours=23)
        token = decode_token(
            create_refresh_token(uuid.uuid4(), uuid.uuid4(), "member", auth_time=started)
        )
        assert token.exp <= session_expires_at(started) + timedelta(seconds=1)
        assert token.exp - datetime.now(UTC) < timedelta(hours=2)

    def test_issued_before(self):
        now = datetime.now(UTC).replace(microsecond=0)
        assert issued_before(now, None) is False
        assert issued_before(None, now) is True
        assert issued_before(now - timedelta(seconds=1), now) is True
        assert issued_before(now, now + timedelta(milliseconds=500)) is True  # same second
        assert issued_before(now + timedelta(seconds=1), now) is False
        assert issued_before(now.replace(tzinfo=None), now - timedelta(seconds=2)) is False


class TestRefresh:
    def test_rotation_keeps_the_session_and_its_sign_in_time(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        world["user"] = _User(user_id, org_id)
        started = datetime.now(UTC) - timedelta(days=3)
        old = create_refresh_token(user_id, org_id, "member", family="fam-1", auth_time=started)
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert r.status_code == 200
        new_refresh = decode_token(r.json()["refresh_token"])
        new_access = decode_token(r.json()["access_token"])
        assert new_refresh.family == "fam-1" and new_access.sid == "fam-1"
        assert int(new_refresh.auth_time.timestamp()) == int(started.timestamp())
        assert r.json()["expires_in"] == 900

    def test_no_refresh_past_the_absolute_limit(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        world["user"] = _User(user_id, org_id)
        now = datetime.now(UTC)
        # Still within its own TTL, but the session began 31 days ago.
        old = _forge(
            {
                "sub": str(user_id),
                "org_id": str(org_id),
                "role": "member",
                "type": "refresh",
                "jti": str(uuid.uuid4()),
                "family": "fam-old",
                "auth_time": int((now - timedelta(days=31)).timestamp()),
                "iat": now - timedelta(days=1),
                "exp": now + timedelta(days=6),
            }
        )
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert r.status_code == 401
        assert "sign in again" in r.json()["detail"].lower()
        assert "fam-old" in world["blacklist"].families

    def test_a_legacy_refresh_token_counts_from_its_issue_time(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        world["user"] = _User(user_id, org_id)
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "org_id": str(org_id),
            "role": "member",
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "family": "fam-legacy",
            "exp": now + timedelta(days=6),
        }
        recent = _forge({**claims, "iat": now - timedelta(days=1)})
        assert (
            client.post("/api/v1/auth/refresh", json={"refresh_token": recent}).status_code == 200
        )
        ancient = _forge({**claims, "jti": str(uuid.uuid4()), "iat": now - timedelta(days=40)})
        assert (
            client.post("/api/v1/auth/refresh", json={"refresh_token": ancient}).status_code == 401
        )

    def test_a_refresh_token_from_before_the_sessions_ended_is_refused(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        old = create_refresh_token(user_id, org_id, "member", family="fam-2")
        world["user"] = _User(user_id, org_id, revoked_at=datetime.now(UTC) + timedelta(seconds=1))
        r = client.post("/api/v1/auth/refresh", json={"refresh_token": old})
        assert r.status_code == 401
        assert "fam-2" in world["blacklist"].families


class TestLogout:
    def test_logout_revokes_the_session_of_the_access_token(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        world["user"] = _User(user_id, org_id)
        pair = create_token_pair(user_id, org_id, "member")
        auth = {"Authorization": f"Bearer {pair.access_token}"}
        assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204
        session_id = decode_token(pair.access_token).sid
        assert session_id in world["blacklist"].families
        # The refresh token of the session is dead, and so is the access token.
        assert (
            client.post(
                "/api/v1/auth/refresh", json={"refresh_token": pair.refresh_token}
            ).status_code
            == 401
        )
        assert client.get("/api/v1/system/quota", headers=auth).status_code == 401

    def test_logout_with_an_expired_access_token_and_the_refresh_token(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        world["user"] = _User(user_id, org_id)
        pair = create_token_pair(user_id, org_id, "member")
        expired = create_access_token(
            user_id, org_id, "member", expires_delta=timedelta(seconds=-5)
        )
        r = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": pair.refresh_token},
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert r.status_code == 204
        assert decode_token(pair.refresh_token).family in world["blacklist"].families
        assert (
            client.post(
                "/api/v1/auth/refresh", json={"refresh_token": pair.refresh_token}
            ).status_code
            == 401
        )

    def test_logout_with_the_refresh_token_alone(self, client, world):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        pair = create_token_pair(user_id, org_id, "member")
        r = client.post("/api/v1/auth/logout", json={"refresh_token": pair.refresh_token})
        assert r.status_code == 204
        assert decode_token(pair.refresh_token).family in world["blacklist"].families

    def test_logout_without_any_token_is_401(self, client):
        assert client.post("/api/v1/auth/logout").status_code == 401
        assert client.post("/api/v1/auth/logout", json={}).status_code == 401

    def test_one_user_cannot_end_another_users_session(self, client, world):
        mine = create_token_pair(uuid.uuid4(), uuid.uuid4(), "member")
        theirs = create_token_pair(uuid.uuid4(), uuid.uuid4(), "member")
        r = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": theirs.refresh_token},
            headers={"Authorization": f"Bearer {mine.access_token}"},
        )
        assert r.status_code == 204
        assert decode_token(mine.access_token).sid in world["blacklist"].families
        assert decode_token(theirs.refresh_token).family not in world["blacklist"].families

    def test_an_access_token_is_not_a_refresh_token(self, client, world):
        other = create_token_pair(uuid.uuid4(), uuid.uuid4(), "member")
        r = client.post("/api/v1/auth/logout", json={"refresh_token": other.access_token})
        assert r.status_code == 204
        assert world["blacklist"].families == set()
