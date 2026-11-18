"""Staff gate: the ``users.is_staff`` flag, honoured only on a verified email.

- ``is_staff`` is True only for an account the database marks staff AND whose
  email address is verified; an unverified address is never staff.
- ``require_staff`` raises the Italian 403 for anyone else.
- Neither the token's email claim nor any other claim makes anyone staff: the
  account check of ``get_current_user`` reads the flag from the database.
- STAFF_EMAILS is no longer a setting; the startup check warns when it is set.
- Access tokens still carry the ``email`` claim (logs, the verified-email
  fast path); refresh tokens and legacy tokens do not break decoding.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from src.auth import dependencies as deps
from src.auth.dependencies import (
    STAFF_ONLY_DETAIL,
    AccountState,
    CurrentUser,
    is_staff,
    require_staff,
)
from src.auth.security import create_access_token, create_refresh_token, decode_token
from src.config import Settings

STAFF_EMAIL = "ops@normaai.org"


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, app_secret_key="x" * 40, **overrides)


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


class TestIsStaff:
    def _user(self, *, staff: bool, verified: bool | None) -> CurrentUser:
        return CurrentUser(
            uuid.uuid4(),
            uuid.uuid4(),
            "admin",
            email=STAFF_EMAIL,
            email_verified=verified,
            is_staff=staff,
        )

    def test_flag_and_verified_email_make_staff(self):
        assert is_staff(self._user(staff=True, verified=True)) is True

    @pytest.mark.parametrize("verified", [False, None])
    def test_unverified_email_is_never_staff(self, verified):
        assert is_staff(self._user(staff=True, verified=verified)) is False

    def test_without_the_flag_a_staff_address_is_not_staff(self):
        assert is_staff(self._user(staff=False, verified=True)) is False

    async def test_require_staff_403_for_non_staff(self):
        with pytest.raises(HTTPException) as exc:
            await require_staff(self._user(staff=True, verified=False))
        assert exc.value.status_code == 403
        assert exc.value.detail == STAFF_ONLY_DETAIL
        assert STAFF_ONLY_DETAIL == "Operazione riservata al personale NormaAI."

    async def test_require_staff_passes_staff_through(self):
        user = self._user(staff=True, verified=True)
        assert await require_staff(user) is user


@pytest.mark.live_account
class TestTheTokenCannotMakeStaff:
    """get_current_user takes is_staff and email_verified from the database."""

    def _account(self, user_id, org_id, **fields) -> AccountState:
        values = {
            "user_id": user_id,
            "org_id": org_id,
            "role": "admin",
            "is_active": True,
            "is_staff": False,
            "email": STAFF_EMAIL,
            "email_verified": True,
        }
        values.update(fields)
        return AccountState(**values)

    async def _current(self, account: AccountState, token: str) -> CurrentUser:
        with patch.object(deps, "load_account", new=AsyncMock(return_value=account)):
            return await deps.get_current_user(_credentials(token))

    async def test_staff_address_in_the_token_without_the_flag(self):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(
            user_id, org_id, "admin", email=STAFF_EMAIL, email_verified=True
        )
        user = await self._current(self._account(user_id, org_id), token)
        assert user.email == STAFF_EMAIL
        assert is_staff(user) is False
        with pytest.raises(HTTPException) as exc:
            await require_staff(user)
        assert exc.value.status_code == 403

    async def test_a_staff_claim_in_the_token_is_ignored(self):
        """Even a validly signed token carrying is_staff=true gives nothing."""
        from jose import jwt

        from src.auth import security

        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        claims = decode_token(create_access_token(user_id, org_id, "admin")).model_dump()
        payload = {
            "sub": claims["sub"],
            "org_id": claims["org_id"],
            "role": "admin",
            "type": "access",
            "jti": claims["jti"],
            "exp": claims["exp"],
            "iat": claims["iat"],
            "iss": security._get_jwt_issuer(),
            "aud": security._get_jwt_audience(),
            "is_staff": True,
            "staff": True,
        }
        token = jwt.encode(payload, security._get_signing_key(), algorithm=security.get_algorithm())
        user = await self._current(self._account(user_id, org_id), token)
        assert user.is_staff is False
        assert is_staff(user) is False

    async def test_flag_on_an_unverified_account_is_not_staff(self):
        """The scenario of a staff address registered by someone who never confirmed it."""
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(
            user_id, org_id, "admin", email=STAFF_EMAIL, email_verified=True
        )
        account = self._account(user_id, org_id, is_staff=True, email_verified=False)
        user = await self._current(account, token)
        assert user.email_verified is False  # the database, not the claim
        with pytest.raises(HTTPException):
            await require_staff(user)

    async def test_the_flag_on_a_verified_account_is_staff(self):
        user_id, org_id = uuid.uuid4(), uuid.uuid4()
        token = create_access_token(user_id, org_id, "admin")  # no claims at all
        user = await self._current(self._account(user_id, org_id, is_staff=True), token)
        assert await require_staff(user) is user


class TestStaffEmailsIsGone:
    def test_the_setting_no_longer_exists(self, monkeypatch):
        monkeypatch.setenv("STAFF_EMAILS", STAFF_EMAIL)
        settings = _settings()
        assert not hasattr(settings, "staff_emails")
        assert not hasattr(settings, "is_staff_email")

    async def test_a_staff_address_in_the_env_makes_nobody_staff(self, monkeypatch):
        monkeypatch.setenv("STAFF_EMAILS", STAFF_EMAIL)
        token = create_access_token(
            uuid.uuid4(), uuid.uuid4(), "admin", email=STAFF_EMAIL, email_verified=True
        )
        user = await deps.get_current_user(_credentials(token))
        assert is_staff(user) is False

    def test_startup_warns_when_it_is_still_set(self, monkeypatch, caplog):
        from src import config

        monkeypatch.setenv("STAFF_EMAILS", STAFF_EMAIL)
        with (
            patch.object(config, "get_settings", return_value=_settings()),
            caplog.at_level(logging.WARNING, logger="normaai.config"),
        ):
            config.validate_settings_or_exit()
        assert any("STAFF_EMAILS is no longer read" in r.getMessage() for r in caplog.records)
        assert any("scripts/staff.py grant" in r.getMessage() for r in caplog.records)

    def test_no_warning_without_it(self, monkeypatch, caplog):
        from src import config

        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        with (
            patch.object(config, "get_settings", return_value=_settings()),
            caplog.at_level(logging.WARNING, logger="normaai.config"),
        ):
            config.validate_settings_or_exit()
        assert not any("STAFF_EMAILS" in r.getMessage() for r in caplog.records)


class TestEmailClaim:
    def test_access_token_carries_email_claim(self):
        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "member", email="a@b.io")
        assert decode_token(token).email == "a@b.io"

    def test_access_token_without_email_decodes_to_none(self):
        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "member")
        assert decode_token(token).email is None

    def test_refresh_token_has_no_email_claim(self):
        token = create_refresh_token(uuid.uuid4(), uuid.uuid4(), "member")
        assert decode_token(token).email is None

    async def test_get_current_user_exposes_email(self):
        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "admin", email="ops@normaai.org")
        user = await deps.get_current_user(_credentials(token))
        assert user.email == "ops@normaai.org"

    def test_account_from_claims_is_never_staff(self):
        payload = decode_token(
            create_access_token(uuid.uuid4(), uuid.uuid4(), "admin", email=STAFF_EMAIL)
        )
        account = deps.account_from_claims(payload)
        assert account.is_staff is False
        assert replace(account, is_staff=True).is_staff is True  # frozen, replaced only
