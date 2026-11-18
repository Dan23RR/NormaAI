"""Password reset (src/auth/password_reset.py, /api/v1/auth/password-reset).

Through the API on the real tables (SQLite, tests/documents_support.Database):

- the request answers the same whether or not the address has an account,
  and only an active account gets a link; only the SHA-256 of the link is
  stored; within the cooldown no second email is sent;
- the link works once, expires, and is bound to its account;
- the new password works, the old one does not, the email counts as verified,
  and every session opened before (access and refresh tokens) ends;
- both routes are rate limited per IP (AUTH_RATE_LIMIT_PASSWORD_RESET);
- staff can mint the same link from the command line (scripts/staff.py).
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.auth import dependencies as deps
from src.auth import password_reset
from src.auth.security import create_token_pair, hash_password, verify_password
from src.config import get_settings
from src.db.models import User
from tests.documents_support import Database

pytestmark = pytest.mark.live_account

OLD_PASSWORD = "vecchia-password-1"
NEW_PASSWORD = "nuova-password-123"


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


@pytest.fixture
def db(monkeypatch):
    database = Database()
    real = deps.load_account

    async def _load(user_id, manager=None):
        return await real(user_id, manager=database)

    monkeypatch.setattr(deps, "load_account", _load)
    return database


@pytest.fixture
def mailbox(monkeypatch):
    """The emails the reset would send: (to, reset_url, ttl_minutes)."""
    sent: list[tuple[str, str, int]] = []

    def _send(*, to_email, recipient_name, reset_url, ttl_minutes):
        sent.append((to_email, reset_url, ttl_minutes))
        return True, None

    monkeypatch.setattr("src.email_client.send_password_reset_email", _send)
    return sent


class _Lockouts:
    """Stand-in for src.auth.brute_force.brute_force: never locks, records resets."""

    def __init__(self) -> None:
        self.resets: list[str] = []

    async def check_and_increment(self, email, ip):
        return None

    async def reset(self, email):
        self.resets.append(email)


@pytest.fixture
def lockouts(monkeypatch):
    fake = _Lockouts()
    monkeypatch.setattr("src.auth.brute_force.brute_force", fake)
    return fake


@pytest.fixture
def client(db, lockouts):
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

        from src.api.rate_limit import limiter as shared_limiter

        # Each import of the routers adds their limits to the shared limiter
        # again: drop the ones of earlier imports (tests/test_auth_rate_limit.py).
        for attr in ("_route_limits", "_dynamic_route_limits", "_Limiter__marked_for_limiting"):
            registry = getattr(shared_limiter, attr, None)
            if isinstance(registry, dict):
                registry.clear()

        from src.api.main import app, limiter
        from src.auth import router

        async def _session():
            async with db.session() as session:
                yield session

        limiter.enabled = False
        app.dependency_overrides[router.get_db_session] = _session
        with patch.object(router, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


@pytest.fixture
def anna(db):
    org = db.add_org()
    user_id = db.add_user(org, "anna@studio.it", verified=False)
    with db.sync_session() as session:
        session.get(User, user_id).hashed_password = hash_password(OLD_PASSWORD)
        session.commit()
    return {"org": org, "id": user_id, "email": "anna@studio.it"}


def _user(db: Database, user_id: uuid.UUID) -> User:
    return db.rows(User, id=user_id)[0]


def _token(url: str) -> str:
    return url.split("token=", 1)[1]


class TestRequest:
    def test_the_answer_is_the_same_with_or_without_an_account(self, client, anna, mailbox):
        known = client.post("/api/v1/auth/password-reset", json={"email": anna["email"]})
        unknown = client.post("/api/v1/auth/password-reset", json={"email": "nobody@studio.it"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        assert known.json()["status"] == "accepted"
        assert "Se l'indirizzo corrisponde a un account attivo" in known.json()["detail"]
        # Only the real account got an email.
        assert [to for to, _, _ in mailbox] == [anna["email"]]

    def test_only_the_hash_of_the_link_is_stored(self, client, db, anna, mailbox):
        client.post("/api/v1/auth/password-reset", json={"email": anna["email"]})
        (_, url, ttl) = mailbox[0]
        assert url.startswith(
            get_settings().normaai_public_url.rstrip("/") + "/reset-password?token="
        )
        token = _token(url)
        user = _user(db, anna["id"])
        secret = token.split(".", 1)[1]
        assert user.password_reset_token_hash == password_reset.hash_secret(secret)
        assert secret not in (user.password_reset_token_hash or "")
        expires = user.password_reset_expires_at.replace(tzinfo=UTC)
        assert ttl == get_settings().password_reset_token_ttl_minutes == 30
        assert timedelta(minutes=29) < expires - datetime.now(UTC) <= timedelta(minutes=30)

    def test_no_second_email_within_the_cooldown(self, client, anna, mailbox):
        for _ in range(3):
            assert (
                client.post(
                    "/api/v1/auth/password-reset", json={"email": anna["email"]}
                ).status_code
                == 202
            )
        assert len(mailbox) == 1

    def test_after_the_cooldown_a_new_link_replaces_the_old_one(self, client, db, anna, mailbox):
        client.post("/api/v1/auth/password-reset", json={"email": anna["email"]})
        with db.sync_session() as session:  # the first link was sent six minutes ago
            row = session.get(User, anna["id"])
            row.password_reset_expires_at = datetime.now(UTC) + timedelta(minutes=24)
            session.commit()
        client.post("/api/v1/auth/password-reset", json={"email": anna["email"]})
        assert len(mailbox) == 2
        first, second = _token(mailbox[0][1]), _token(mailbox[1][1])
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": first, "password": NEW_PASSWORD}
        )
        assert r.status_code == 400
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": second, "password": NEW_PASSWORD}
        )
        assert r.status_code == 200

    def test_a_deactivated_account_gets_nothing(self, client, db, mailbox):
        org = db.add_org()
        db.add_user(org, "gone@studio.it", active=False)
        assert (
            client.post("/api/v1/auth/password-reset", json={"email": "gone@studio.it"}).status_code
            == 202
        )
        assert mailbox == []

    def test_a_malformed_address_is_422(self, client, mailbox):
        assert (
            client.post("/api/v1/auth/password-reset", json={"email": "not-an-email"}).status_code
            == 422
        )


class TestConfirm:
    def _link(self, client, anna, mailbox) -> str:
        client.post("/api/v1/auth/password-reset", json={"email": anna["email"]})
        return _token(mailbox[-1][1])

    def test_the_new_password_works_the_link_works_once_and_sessions_end(
        self, client, db, anna, mailbox
    ):
        old_session = create_token_pair(anna["id"], anna["org"], "member")
        auth = {"Authorization": f"Bearer {old_session.access_token}"}
        assert client.get("/api/v1/auth/me", headers=auth).status_code == 200

        token = self._link(client, anna, mailbox)
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
        )
        assert r.status_code == 200
        assert r.json() == {"status": "password_changed", "email": anna["email"]}

        user = _user(db, anna["id"])
        assert verify_password(NEW_PASSWORD, user.hashed_password)
        assert not verify_password(OLD_PASSWORD, user.hashed_password)
        assert user.password_reset_token_hash is None and user.password_reset_expires_at is None
        assert user.email_verified is True  # the link proved the mailbox
        assert user.sessions_revoked_at is not None

        # Once only.
        again = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": token, "password": "altra-password-9"},
        )
        assert again.status_code == 400
        assert again.json()["detail"] == password_reset.INVALID_RESET_TOKEN_DETAIL

        # Every session opened before is over: the access token and the refresh token.
        assert client.get("/api/v1/auth/me", headers=auth).status_code == 401
        refreshed = client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old_session.refresh_token}
        )
        assert refreshed.status_code == 401

    def test_an_expired_link_is_refused(self, client, db, anna, mailbox):
        token = self._link(client, anna, mailbox)
        with db.sync_session() as session:
            session.get(User, anna["id"]).password_reset_expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
            session.commit()
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
        )
        assert r.status_code == 400
        assert verify_password(OLD_PASSWORD, _user(db, anna["id"]).hashed_password)

    def test_a_link_is_bound_to_its_account(self, client, db, anna, mailbox):
        token = self._link(client, anna, mailbox)
        secret = token.split(".", 1)[1]
        other = db.add_user(anna["org"], "marco@studio.it")
        for forged in (
            f"{other}.{secret}",
            f"{anna['id']}.{secret}x",
            f"{anna['id']}.",
            "not-a-token-at-all-xx",
        ):
            r = client.post(
                "/api/v1/auth/password-reset/confirm",
                json={"token": forged, "password": NEW_PASSWORD},
            )
            assert r.status_code in (400, 422), forged
        assert verify_password(OLD_PASSWORD, _user(db, anna["id"]).hashed_password)

    def test_a_short_password_is_422_and_keeps_the_link(self, client, db, anna, mailbox):
        token = self._link(client, anna, mailbox)
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "password": "corta"}
        )
        assert r.status_code == 422
        assert _user(db, anna["id"]).password_reset_token_hash is not None

    def test_a_deactivated_account_cannot_use_its_link(self, client, db, anna, mailbox):
        token = self._link(client, anna, mailbox)
        with db.sync_session() as session:
            session.get(User, anna["id"]).is_active = False
            session.commit()
        r = client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
        )
        assert r.status_code == 400

    def test_after_the_reset_the_new_password_signs_in(self, client, db, anna, mailbox, lockouts):
        token = self._link(client, anna, mailbox)
        client.post(
            "/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}
        )
        # A locked-out user can sign in with the new password at once.
        assert lockouts.resets == [anna["email"]]
        ok = client.post(
            "/api/v1/auth/login", json={"email": anna["email"], "password": NEW_PASSWORD}
        )
        bad = client.post(
            "/api/v1/auth/login", json={"email": anna["email"], "password": OLD_PASSWORD}
        )
        assert ok.status_code == 200 and bad.status_code == 401
        fresh = {"Authorization": f"Bearer {ok.json()['access_token']}"}
        # Issued after the revocation (a second later at least): accepted.
        with db.sync_session() as session:
            session.get(User, anna["id"]).sessions_revoked_at = datetime.now(UTC) - timedelta(
                seconds=5
            )
            session.commit()
        deps.invalidate_account(anna["id"])
        assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200


class TestRateLimits:
    def test_both_routes_are_limited_per_ip_by_the_setting(self, client, anna, mailbox):
        from src.api.main import limiter

        patched = get_settings().model_copy(update={"auth_rate_limit_password_reset": "2/hour"})
        limiter.reset()
        limiter.enabled = True
        try:
            with patch("src.api.rate_limit.get_settings", return_value=patched):
                codes = [
                    client.post(
                        "/api/v1/auth/password-reset", json={"email": f"x{i}@studio.it"}
                    ).status_code
                    for i in range(3)
                ]
                confirm = [
                    client.post(
                        "/api/v1/auth/password-reset/confirm",
                        json={
                            "token": f"{uuid.uuid4()}.secret-secret-secret",
                            "password": NEW_PASSWORD,
                        },
                    ).status_code
                    for _ in range(3)
                ]
        finally:
            limiter.enabled = False
            limiter.reset()
        assert codes == [202, 202, 429]
        assert confirm == [400, 400, 429]


def _staff_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "staff.py"
    spec = importlib.util.spec_from_file_location("staff_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestStaffScript:
    async def test_staff_mints_a_link_that_works(self, client, db, anna, mailbox):
        staff = _staff_script()
        message, link = await staff.reset_password(db, anna["email"])
        assert "valid 30 minutes, once" in message
        assert mailbox == []  # printed, not sent, without --send
        r = client.post(
            "/api/v1/auth/password-reset/confirm",
            json={"token": _token(link), "password": NEW_PASSWORD},
        )
        assert r.status_code == 200
        await staff.reset_password(db, anna["email"], send=True)
        assert [to for to, _, _ in mailbox] == [anna["email"]]
