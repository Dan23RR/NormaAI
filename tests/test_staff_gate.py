"""Staff gate: settings.staff_emails + the ``email`` access-token claim.

- ``Settings.staff_emails`` accepts a JSON list or a comma-separated string
  (env friendly) and normalises to lowercase.
- ``is_staff`` matches the token's email claim case-insensitively and fails
  closed when the claim is missing (legacy tokens).
- ``require_staff`` raises the Italian 403 for non-staff callers.
- Access tokens minted by the auth flows carry the ``email`` claim; refresh
  tokens and legacy tokens do not break decoding.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.auth import dependencies as deps
from src.auth.dependencies import STAFF_ONLY_DETAIL, CurrentUser, is_staff, require_staff
from src.auth.security import create_access_token, create_refresh_token, decode_token
from src.config import Settings


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, app_secret_key="x" * 40, **overrides)


class TestStaffEmailsSetting:
    def test_default_is_empty(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        assert _settings().staff_emails == []

    def test_comma_separated_string_from_env(self, monkeypatch):
        monkeypatch.setenv("STAFF_EMAILS", "Ops@NormaAI.org, info@normaai.org ,,")
        assert _settings().staff_emails == ["ops@normaai.org", "info@normaai.org"]

    def test_json_list_from_env(self, monkeypatch):
        monkeypatch.setenv("STAFF_EMAILS", '["A@x.io", "b@y.io"]')
        assert _settings().staff_emails == ["a@x.io", "b@y.io"]

    def test_python_list_override(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        assert _settings(staff_emails=["Z@x.io"]).staff_emails == ["z@x.io"]

    def test_is_staff_email_case_insensitive_and_none_safe(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        s = _settings(staff_emails=["ops@normaai.org"])
        assert s.is_staff_email("OPS@normaai.org") is True
        assert s.is_staff_email("someone@acme.com") is False
        assert s.is_staff_email(None) is False
        assert s.is_staff_email("") is False


class TestIsStaff:
    def _user(self, email: str | None) -> CurrentUser:
        return CurrentUser(uuid.uuid4(), uuid.uuid4(), "admin", email=email)

    def test_staff_claim_matches(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        with patch.object(
            deps, "get_settings", return_value=_settings(staff_emails=["ops@normaai.org"])
        ):
            assert is_staff(self._user("Ops@NormaAI.org")) is True
            assert is_staff(self._user("admin@acme.com")) is False

    def test_missing_claim_is_never_staff(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        with patch.object(
            deps, "get_settings", return_value=_settings(staff_emails=["ops@normaai.org"])
        ):
            assert is_staff(self._user(None)) is False

    async def test_require_staff_403_for_non_staff(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        with patch.object(
            deps, "get_settings", return_value=_settings(staff_emails=["ops@normaai.org"])
        ):
            with pytest.raises(HTTPException) as exc:
                await require_staff(self._user("admin@acme.com"))
            assert exc.value.status_code == 403
            assert exc.value.detail == STAFF_ONLY_DETAIL
            assert STAFF_ONLY_DETAIL == "Operazione riservata al personale NormaAI."

    async def test_require_staff_passes_staff_through(self, monkeypatch):
        monkeypatch.delenv("STAFF_EMAILS", raising=False)
        user = self._user("ops@normaai.org")
        with patch.object(
            deps, "get_settings", return_value=_settings(staff_emails=["ops@normaai.org"])
        ):
            assert await require_staff(user) is user


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
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_access_token(uuid.uuid4(), uuid.uuid4(), "admin", email="ops@normaai.org")
        user = await deps.get_current_user(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
        assert user.email == "ops@normaai.org"
