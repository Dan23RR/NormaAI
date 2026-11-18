"""The account check of get_current_user: the token is not believed on its own.

On every request the account the token names is read from the database (kept
``AUTH_ACCOUNT_CACHE_SECONDS`` per process): a removed or deactivated user is
refused, a user moved out of the token's organisation is refused, a token
issued before ``users.sessions_revoked_at`` is refused, the role used is the
database's, and a revoked session (refresh family) refuses its access tokens.
A database that does not answer is a 503, never a pass.

These tests opt out of the claims stand-in of tests/conftest.py
(``live_account``): ``load_account`` reads the real tables on SQLite
(tests/documents_support.Database).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.auth import dependencies as deps
from src.auth.security import create_access_token, create_token_pair, decode_token
from src.db.models import User
from tests.documents_support import Database

pytestmark = pytest.mark.live_account


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def db(monkeypatch):
    """The real tables on SQLite; load_account reads them."""
    database = Database()
    real = deps.load_account

    async def _load(user_id, manager=None):
        return await real(user_id, manager=database)

    monkeypatch.setattr(deps, "load_account", _load)
    return database


def _update_user(db: Database, user_id: uuid.UUID, **fields) -> None:
    with db.sync_session() as session:
        user = session.get(User, user_id)
        for name, value in fields.items():
            setattr(user, name, value)
        session.commit()
    deps.invalidate_account(user_id)


def _delete_user(db: Database, user_id: uuid.UUID) -> None:
    with db.sync_session() as session:
        session.delete(session.get(User, user_id))
        session.commit()
    deps.invalidate_account(user_id)


async def _current(token: str) -> deps.CurrentUser:
    return await deps.get_current_user(_credentials(token))


async def _status(token: str) -> int:
    try:
        await _current(token)
    except HTTPException as error:
        return error.status_code
    return 200


class TestTheDatabaseDecides:
    async def test_an_existing_active_user_passes_with_the_database_values(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it", role="member", verified=False)
        token = create_access_token(user_id, org, "member", email="old@studio.it")
        user = await _current(token)
        assert (user.user_id, user.org_id, user.role) == (user_id, org, "member")
        assert user.email == "anna@studio.it"  # the account, not the claim
        assert user.email_verified is False
        assert user.is_staff is False

    async def test_a_removed_member_is_refused(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it")
        token = create_access_token(user_id, org, "member")
        assert await _status(token) == 200
        _delete_user(db, user_id)
        assert await _status(token) == 401

    async def test_a_deactivated_account_is_refused(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it")
        token = create_access_token(user_id, org, "member")
        _update_user(db, user_id, is_active=False)
        assert await _status(token) == 401

    async def test_a_token_of_another_organisation_is_refused(self, db):
        org, other = db.add_org("Alfa"), db.add_org("Beta")
        user_id = db.add_user(org, "anna@studio.it")
        assert await _status(create_access_token(user_id, other, "admin")) == 401

    async def test_a_changed_role_takes_effect_on_the_old_token(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it", role="admin")
        token = create_access_token(user_id, org, "admin")
        assert (await _current(token)).role == "admin"
        _update_user(db, user_id, role="viewer")
        user = await _current(token)
        assert user.role == "viewer"
        with pytest.raises(HTTPException) as exc:
            await deps.require_editor(user)
        assert exc.value.status_code == 403
        assert exc.value.detail == deps.READ_ONLY_DETAIL
        with pytest.raises(HTTPException):
            await deps.require_role("admin")(user)

    async def test_tokens_issued_before_the_sessions_ended_are_refused(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it")
        old = create_access_token(user_id, org, "member")
        _update_user(db, user_id, sessions_revoked_at=datetime.now(UTC) + timedelta(seconds=1))
        assert await _status(old) == 401
        # A token issued after the revocation works.
        _update_user(db, user_id, sessions_revoked_at=datetime.now(UTC) - timedelta(minutes=5))
        assert await _status(create_access_token(user_id, org, "member")) == 200

    async def test_a_database_that_does_not_answer_is_a_503(self):
        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "admin")
        with (
            patch.object(deps, "load_account", new=AsyncMock(side_effect=OSError("down"))),
            pytest.raises(HTTPException) as exc,
        ):
            await _current(token)
        assert exc.value.status_code == 503
        assert exc.value.detail == deps.ACCOUNT_CHECK_UNAVAILABLE_DETAIL

    async def test_a_malformed_identity_is_a_401_not_a_503(self):
        from jose import jwt

        from src.auth import security

        claims = decode_token(create_access_token(uuid.uuid4(), uuid.uuid4(), "admin"))
        payload = {
            "sub": "not-a-uuid",
            "org_id": claims.org_id,
            "role": "admin",
            "type": "access",
            "jti": claims.jti,
            "exp": claims.exp,
            "iat": claims.iat,
            "iss": security._get_jwt_issuer(),
            "aud": security._get_jwt_audience(),
        }
        token = jwt.encode(payload, security._get_signing_key(), algorithm=security.get_algorithm())
        loader = AsyncMock()
        with patch.object(deps, "load_account", new=loader):
            assert await _status(token) == 401
        loader.assert_not_called()


class TestRevokedSession:
    async def test_a_revoked_session_refuses_its_access_tokens(self, db):
        org = db.add_org()
        user_id = db.add_user(org, "anna@studio.it")
        pair = create_token_pair(user_id, org, "member")
        session_id = decode_token(pair.access_token).sid
        assert session_id == decode_token(pair.refresh_token).family

        class _Blacklist:
            async def is_blacklisted(self, jti, family=None):
                return family == session_id

        with patch.object(deps, "token_blacklist", _Blacklist()):
            assert await _status(pair.access_token) == 401
            other = create_token_pair(user_id, org, "member")
            assert await _status(other.access_token) == 200


class TestCache:
    def _state(self, user_id, org_id, role="member") -> deps.AccountState:
        return deps.AccountState(
            user_id=user_id,
            org_id=org_id,
            role=role,
            is_active=True,
            is_staff=False,
            email="a@b.io",
            email_verified=True,
        )

    async def test_reads_once_within_the_ttl_and_again_after_invalidation(self):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(user_id, org_id, "member")
        loader = AsyncMock(return_value=self._state(user_id, org_id))
        with patch.object(deps, "load_account", new=loader):
            await _current(token)
            await _current(token)
            assert loader.await_count == 1
            deps.invalidate_account(user_id)
            await _current(token)
            assert loader.await_count == 2

    async def test_zero_seconds_means_no_cache(self):
        from src.config import get_settings

        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(user_id, org_id, "member")
        loader = AsyncMock(return_value=self._state(user_id, org_id))
        no_cache = get_settings().model_copy(update={"auth_account_cache_seconds": 0})
        with (
            patch.object(deps, "load_account", new=loader),
            patch.object(deps, "get_settings", return_value=no_cache),
        ):
            await _current(token)
            await _current(token)
        assert loader.await_count == 2

    def test_entries_expire_and_the_cache_stays_bounded(self, monkeypatch):
        cache = deps.AccountCache()
        user_id = uuid.uuid4()
        state = self._state(user_id, uuid.uuid4())
        now = [1000.0]
        monkeypatch.setattr(deps.time, "monotonic", lambda: now[0])
        cache.put(user_id, state, ttl=30)
        assert cache.get(user_id) == (True, state)
        now[0] += 31
        assert cache.get(user_id) == (False, None)

        monkeypatch.setattr(deps.AccountCache, "MAX_ENTRIES", 3)
        for _ in range(5):
            cache.put(uuid.uuid4(), None, ttl=30)
        assert len(cache._entries) <= 3

    async def test_a_missing_account_is_cached_too(self):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(user_id, org_id, "member")
        loader = AsyncMock(return_value=None)
        with patch.object(deps, "load_account", new=loader):
            assert await _status(token) == 401
            assert await _status(token) == 401
        assert loader.await_count == 1
