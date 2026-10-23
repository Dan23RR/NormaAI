"""Email verification: signed token round trip, endpoints, gating dependency.

- src/auth/tokens.py + src/auth/verification.py: purpose-bound HMAC tokens,
  bound to the email they were issued for, expiring, tamper-evident.
- POST /api/v1/auth/verify-email / resend-verification.
- Registration: verification email scheduled unless the invite email matches.
- ``require_verified_email``: off by default; when on, the token claim is the
  fast path and the DB the fallback; fail closed with the Italian 403.
- src/email_client.send_verification_email is a logged no-op without a key.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.auth import dependencies as deps
from src.auth import verification
from src.auth.dependencies import CurrentUser, require_verified_email
from src.auth.security import create_access_token, decode_token, hash_password
from src.auth.tokens import make_signed_token, verify_signed_token
from src.auth.verification import (
    EMAIL_NOT_VERIFIED_DETAIL,
    INVALID_VERIFICATION_TOKEN_DETAIL,
    build_verification_url,
    make_email_verification_token,
    parse_email_verification_token,
    verify_email_verification_token,
)

# ──────────────────────────────────────────────────────────────────────────
#  Tokens
# ──────────────────────────────────────────────────────────────────────────


class TestVerificationToken:
    def test_round_trip_is_bound_to_email_case_insensitively(self):
        uid = uuid.uuid4()
        token = make_email_verification_token(uid, "Founder@Acme.com")
        assert parse_email_verification_token(token) == uid
        assert verify_email_verification_token(token, "founder@acme.com") == uid
        assert verify_email_verification_token(token, " FOUNDER@ACME.COM ") == uid

    def test_other_email_or_user_rejected(self):
        uid = uuid.uuid4()
        token = make_email_verification_token(uid, "a@b.io")
        assert verify_email_verification_token(token, "other@b.io") is None
        # Same email but a different subject (user id swap) fails the MAC.
        swapped = f"{uuid.uuid4()}.{token.split('.')[1]}.{token.split('.')[2]}"
        assert verify_email_verification_token(swapped, "a@b.io") is None

    def test_expired_token_rejected(self):
        uid = uuid.uuid4()
        token = make_email_verification_token(uid, "a@b.io", ttl_hours=-1)
        assert parse_email_verification_token(token) is None
        assert verify_email_verification_token(token, "a@b.io") is None

    @pytest.mark.parametrize(
        "bad", ["", "garbage", "a.b", "x.notanint.sig", "not-a-uuid.9999999999.sig"]
    )
    def test_malformed_tokens_rejected(self, bad):
        assert parse_email_verification_token(bad) is None
        assert verify_email_verification_token(bad, "a@b.io") is None

    def test_tampered_signature_rejected(self):
        token = make_email_verification_token(uuid.uuid4(), "a@b.io")
        subject, exp, sig = token.split(".")
        flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
        assert verify_email_verification_token(f"{subject}.{exp}.{flipped}", "a@b.io") is None

    def test_purpose_separation(self):
        # A token minted for another purpose with the same subject/expiry
        # never verifies as an email-verification token.
        uid = str(uuid.uuid4())
        exp = datetime.now(UTC) + timedelta(hours=1)
        other = make_signed_token("codex-dl", uid, exp, binding="a@b.io")
        assert (
            verify_signed_token(verification.EMAIL_VERIFICATION_PURPOSE, other, binding="a@b.io")
            is None
        )
        assert verify_signed_token("codex-dl", other, binding="a@b.io") == uid

    def test_subject_with_dot_refused(self):
        with pytest.raises(ValueError):
            make_signed_token("p", "a.b", datetime.now(UTC) + timedelta(hours=1))

    def test_verification_url_uses_public_url(self):
        from src.config import get_settings

        patched = get_settings().model_copy(update={"normaai_public_url": "https://app.example/"})
        with patch("src.auth.verification.get_settings", return_value=patched):
            assert (
                build_verification_url("tok.1.sig")
                == "https://app.example/verify-email?token=tok.1.sig"
            )


# ──────────────────────────────────────────────────────────────────────────
#  Email sending
# ──────────────────────────────────────────────────────────────────────────


class TestVerificationEmail:
    def test_noop_without_resend_key(self, monkeypatch):
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
        from src.email_client import send_verification_email

        ok, err = send_verification_email("a@b.io", "Ada", "https://x/verify-email?token=t")
        assert (ok, err) == (False, "resend_not_configured")

    def test_template_carries_link_and_italian_subject(self):
        captured = {}

        def fake_send(**kwargs):
            captured.update(kwargs)
            return True, None

        with patch("src.email_client._send_via_resend", side_effect=fake_send):
            from src.email_client import send_verification_email

            ok, _ = send_verification_email(
                "a@b.io", "Ada", "https://x/verify-email?token=t", ttl_hours=48
            )
        assert ok is True
        assert captured["to_email"] == "a@b.io"
        assert "Conferma" in captured["subject"]
        assert "https://x/verify-email?token=t" in captured["html"]
        assert "https://x/verify-email?token=t" in captured["text"]
        assert captured["tags"] == [{"name": "campaign", "value": "email_verification"}]

    def test_helper_never_raises(self):
        with patch(
            "src.email_client.send_verification_email", side_effect=RuntimeError("smtp down")
        ):
            ok, err = verification.send_verification_email(uuid.uuid4(), "a@b.io", "Ada")
        assert ok is False and "RuntimeError" in (err or "")

    def test_helper_mints_a_valid_token_for_the_user(self):
        uid = uuid.uuid4()
        captured = {}

        def fake_send(*, to_email, recipient_name, verify_url):
            captured["url"] = verify_url
            return True, None

        with patch("src.email_client.send_verification_email", side_effect=fake_send):
            assert verification.send_verification_email(uid, "a@b.io", "Ada") == (True, None)
        token = captured["url"].split("token=", 1)[1]
        assert verify_email_verification_token(token, "a@b.io") == uid


# ──────────────────────────────────────────────────────────────────────────
#  require_verified_email dependency
# ──────────────────────────────────────────────────────────────────────────


def _settings(require: bool):
    from src.config import get_settings

    return get_settings().model_copy(update={"require_email_verification": require})


def _user(email_verified=None) -> CurrentUser:
    return CurrentUser(
        uuid.uuid4(), uuid.uuid4(), "member", email="a@b.io", email_verified=email_verified
    )


class TestRequireVerifiedEmail:
    async def test_off_by_default_passes_unverified(self):
        from src.config import get_settings

        assert get_settings().require_email_verification is False
        user = _user(email_verified=False)
        with patch.object(deps, "_email_verified_in_db", new=AsyncMock(side_effect=AssertionError)):
            assert await require_verified_email(user) is user

    async def test_claim_true_is_fast_path(self):
        user = _user(email_verified=True)
        with (
            patch.object(deps, "get_settings", return_value=_settings(True)),
            patch.object(deps, "_email_verified_in_db", new=AsyncMock(side_effect=AssertionError)),
        ):
            assert await require_verified_email(user) is user

    async def test_db_fallback_accepts_verified_user(self):
        user = _user(email_verified=False)  # token minted before verification
        with (
            patch.object(deps, "get_settings", return_value=_settings(True)),
            patch.object(deps, "_email_verified_in_db", new=AsyncMock(return_value=True)),
        ):
            assert await require_verified_email(user) is user
        assert user.email_verified is True

    async def test_unverified_user_gets_italian_403(self):
        user = _user(email_verified=None)
        with (
            patch.object(deps, "get_settings", return_value=_settings(True)),
            patch.object(deps, "_email_verified_in_db", new=AsyncMock(return_value=False)),
            pytest.raises(HTTPException) as exc,
        ):
            await require_verified_email(user)
        assert exc.value.status_code == 403
        assert exc.value.detail == EMAIL_NOT_VERIFIED_DETAIL
        assert exc.value.detail == "Conferma l'indirizzo email per usare NormaAI."

    async def test_db_error_fails_closed(self):
        user = _user(email_verified=False)
        with (
            patch.object(deps, "get_settings", return_value=_settings(True)),
            patch.object(
                deps, "_email_verified_in_db", new=AsyncMock(side_effect=RuntimeError("db down"))
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await require_verified_email(user)
        assert exc.value.status_code == 403


# ──────────────────────────────────────────────────────────────────────────
#  Endpoints (bare app, fake DB session - mirrors test_auth_router.py)
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


class _FakeUser:
    def __init__(self, *, email="founder@acme.com", email_verified=False, org_id=None):
        self.id = uuid.uuid4()
        self.org_id = org_id or uuid.uuid4()
        self.email = email
        self.name = "Founder"
        self.hashed_password = hash_password("supersecret123")
        self.role = "admin"
        self.is_active = True
        self.email_verified = email_verified


class _FakeOrg:
    def __init__(self, org_id):
        self.id = org_id
        self.name = "Acme Srl"


class _FakeResult:
    def __init__(self, *, scalar=None, row=None):
        self._scalar = scalar
        self._row = row

    def scalar_one_or_none(self):
        return self._scalar

    def one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, *, user=None, row=None):
        self.user = user
        self.row = row
        self.added: list = []
        self.committed = False

    async def execute(self, *_a, **_k):
        return _FakeResult(scalar=self.user, row=self.row)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def commit(self):
        await self.flush()
        self.committed = True

    async def rollback(self):
        pass

    async def refresh(self, _obj):
        pass


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
    from src.auth.router import get_db_session

    def _apply(session: _FakeSession) -> _FakeSession:
        async def _fake():
            yield session

        app_objects.dependency_overrides[get_db_session] = _fake
        return session

    return _apply


def _bearer(user: _FakeUser, **claims) -> dict:
    token = create_access_token(user.id, user.org_id, user.role, email=user.email, **claims)
    return {"Authorization": f"Bearer {token}"}


class TestVerifyEmailEndpoint:
    def test_valid_token_verifies(self, client, override_db):
        user = _FakeUser()
        session = override_db(_FakeSession(user=user))
        token = make_email_verification_token(user.id, user.email)
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "verified", "email": user.email}
        assert user.email_verified is True
        assert session.committed is True

    def test_replay_is_idempotent(self, client, override_db):
        user = _FakeUser(email_verified=True)
        session = override_db(_FakeSession(user=user))
        token = make_email_verification_token(user.id, user.email)
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 200
        assert r.json()["status"] == "already_verified"
        assert session.committed is False

    def test_garbage_token_is_400(self, client, override_db):
        session = override_db(_FakeSession(user=None))
        r = client.post("/api/v1/auth/verify-email", json={"token": "definitely-not-a-token"})
        assert r.status_code == 400
        assert r.json()["detail"] == INVALID_VERIFICATION_TOKEN_DETAIL
        assert r.json()["detail"] == "Token di verifica non valido o scaduto."
        assert session.committed is False

    def test_token_for_old_email_is_400(self, client, override_db):
        user = _FakeUser(email="new@acme.com")
        override_db(_FakeSession(user=user))
        token = make_email_verification_token(user.id, "old@acme.com")
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 400
        assert user.email_verified is False

    def test_unknown_user_is_400(self, client, override_db):
        override_db(_FakeSession(user=None))
        token = make_email_verification_token(uuid.uuid4(), "ghost@acme.com")
        r = client.post("/api/v1/auth/verify-email", json={"token": token})
        assert r.status_code == 400


class TestResendVerificationEndpoint:
    def test_requires_auth(self, client, override_db):
        override_db(_FakeSession())
        assert client.post("/api/v1/auth/resend-verification").status_code == 401

    def test_sends_for_unverified_user(self, client, override_db):
        user = _FakeUser(email_verified=False)
        override_db(_FakeSession(user=user))
        with patch("src.auth.router.send_verification_email") as send:
            r = client.post("/api/v1/auth/resend-verification", headers=_bearer(user))
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "sent", "email": user.email}
        send.assert_called_once_with(user.id, user.email, user.name)

    def test_already_verified_does_not_send(self, client, override_db):
        user = _FakeUser(email_verified=True)
        override_db(_FakeSession(user=user))
        with patch("src.auth.router.send_verification_email") as send:
            r = client.post("/api/v1/auth/resend-verification", headers=_bearer(user))
        assert r.status_code == 200
        assert r.json()["status"] == "already_verified"
        send.assert_not_called()


class TestRegistrationVerification:
    def test_open_registration_schedules_email_and_unverified_claim(self, client, override_db):
        session = override_db(_FakeSession())
        with patch("src.auth.router.send_verification_email") as send:
            r = client.post(
                "/api/v1/auth/register",
                json={
                    "email": "founder@acme.com",
                    "password": "supersecret123",
                    "name": "Founder",
                    "organization_name": "Acme Srl",
                },
            )
        assert r.status_code == 201, r.text
        from src.db.models import User

        (user,) = [o for o in session.added if isinstance(o, User)]
        assert user.email_verified is False
        send.assert_called_once_with(user.id, "founder@acme.com", "Founder")
        assert decode_token(r.json()["access_token"]).email_verified is False

    @pytest.mark.parametrize(
        ("invite_email", "registered", "expected_verified"),
        [
            ("founder@acme.com", "Founder@Acme.com", True),
            ("cfo@acme.com", "founder@acme.com", False),
        ],
    )
    def test_invite_email_match_verifies_automatically(
        self, client, override_db, invite_email, registered, expected_verified
    ):
        from tests.test_invites import _FakeSession as _InviteSession
        from tests.test_invites import _pending_invite

        invite, code = _pending_invite(None, email=invite_email)
        session = override_db(_InviteSession(invite=invite))
        with patch("src.auth.router.send_verification_email") as send:
            r = client.post(
                "/api/v1/auth/register",
                json={
                    "email": registered,
                    "password": "supersecret123",
                    "name": "Founder",
                    "organization_name": "Acme Srl",
                    "invite_code": code,
                },
            )
        assert r.status_code == 201, r.text
        from src.db.models import User

        (user,) = session.added_of(User)
        assert user.email_verified is expected_verified
        assert decode_token(r.json()["access_token"]).email_verified is expected_verified
        assert send.called is (not expected_verified)


class TestMeExposesVerification:
    def test_me_reports_email_verified(self, client, override_db):
        user = _FakeUser(email_verified=True)
        override_db(_FakeSession(row=(user, _FakeOrg(user.org_id))))
        with patch("src.auth.router.token_blacklist") as bl:
            bl.is_blacklisted = AsyncMock(return_value=False)
            r = client.get("/api/v1/auth/me", headers=_bearer(user))
        assert r.status_code == 200, r.text
        assert r.json()["email_verified"] is True


class TestIntelligenceGate:
    def _qa(self, client, headers):
        with patch("src.agents.graph.arun_qa", new_callable=AsyncMock) as qa:
            qa.return_value = {"answer": "ok", "citations": [], "confidence_score": 0.9}
            return client.post(
                "/api/v1/qa", json={"question": "What is the CSRD?"}, headers=headers
            )

    def test_unverified_user_blocked_when_required(self, client):
        user = _FakeUser(email_verified=False)
        with (
            patch("src.auth.dependencies.get_settings", return_value=_settings(True)),
            patch("src.auth.dependencies._email_verified_in_db", new=AsyncMock(return_value=False)),
        ):
            r = self._qa(client, _bearer(user, email_verified=False))
        assert r.status_code == 403
        assert r.json()["detail"] == EMAIL_NOT_VERIFIED_DETAIL

    def test_verified_claim_passes_when_required(self, client):
        user = _FakeUser(email_verified=True)
        with patch("src.auth.dependencies.get_settings", return_value=_settings(True)):
            r = self._qa(client, _bearer(user, email_verified=True))
        assert r.status_code == 200, r.text

    def test_not_required_by_default(self, client):
        user = _FakeUser(email_verified=False)
        r = self._qa(client, _bearer(user, email_verified=False))
        assert r.status_code == 200, r.text
