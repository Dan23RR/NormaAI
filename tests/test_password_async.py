"""bcrypt must run off the event loop in request handlers.

``hash_password_async`` / ``verify_password_async`` wrap the sync helpers in
``asyncio.to_thread``; the login handler keeps its constant-time behaviour
(bcrypt always runs, against a valid dummy hash when the email is unknown).
"""

from __future__ import annotations

import sys
import threading
from unittest.mock import MagicMock, patch

import pytest

from src.auth import security
from src.auth.security import (
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)


class TestAsyncWrappers:
    async def test_round_trip(self):
        hashed = await hash_password_async("supersecret123")
        assert hashed.startswith("$2b$")
        assert verify_password("supersecret123", hashed)  # interoperable with sync
        assert await verify_password_async("supersecret123", hashed) is True
        assert await verify_password_async("wrong-password", hashed) is False

    async def test_hash_runs_in_worker_thread(self):
        main_thread = threading.get_ident()
        seen: list[int] = []

        def spy(password: str) -> str:
            seen.append(threading.get_ident())
            return hash_password(password)

        with patch.object(security, "hash_password", spy):
            await hash_password_async("pw-for-thread-check")
        assert seen and seen[0] != main_thread

    async def test_verify_delegates_to_to_thread(self):
        calls: list[tuple] = []

        async def fake_to_thread(fn, *args):
            calls.append((fn.__name__, args))
            return fn(*args)

        hashed = hash_password("pw")
        with patch.object(security.asyncio, "to_thread", fake_to_thread):
            assert await verify_password_async("pw", hashed) is True
        assert calls == [("verify_password", ("pw", hashed))]


# ──────────────────────────────────────────────────────────────────────────
#  Login handler keeps the constant-time dummy-hash path (now async)
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


class _NoUserResult:
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    async def execute(self, *_a, **_k):
        return _NoUserResult()


class _FakeBruteForce:
    async def check_and_increment(self, email, ip):
        return None

    async def reset(self, email):
        pass


def test_login_unknown_email_verifies_against_dummy_hash_async():
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

        from fastapi.testclient import TestClient

        from src.api.main import app, limiter
        from src.auth import router as auth_router

        limiter.enabled = False

        async def _fake_db():
            yield _FakeSession()

        app.dependency_overrides[auth_router.get_db_session] = _fake_db
        seen: list[tuple[str, str]] = []

        async def spy_verify(plain: str, hashed: str) -> bool:
            seen.append((plain, hashed))
            return await verify_password_async(plain, hashed)

        try:
            with (
                patch("src.auth.router.verify_password_async", spy_verify),
                patch("src.auth.brute_force.brute_force", _FakeBruteForce()),
            ):
                r = TestClient(app).post(
                    "/api/v1/auth/login",
                    json={"email": "ghost@acme.com", "password": "whatever123"},
                )
        finally:
            app.dependency_overrides.clear()

    assert r.status_code == 401
    # bcrypt ran exactly once, against the valid dummy hash (no early return).
    assert seen == [("whatever123", auth_router._DUMMY_PASSWORD_HASH)]
