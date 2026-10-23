"""Per-IP rate limits on the public auth endpoints (register/login/refresh).

Covers:
- the limit is enforced per CLIENT IP, read from settings per request
  (``auth_rate_limit_*``), with the 429 body carrying a UI-friendly ``detail``
  and the ``Retry-After`` header;
- the key is the spoof-resistant client IP: a different IP appended by the
  trusted proxy (X-Forwarded-For) gets its own bucket;
- the limiter runs BEFORE the handler, so failed attempts (401s) count too;
- the 429 handler helpers (wait formatting, Retry-After fallback).

Pattern notes
-------------
Same bare-app fixture as tests/test_auth_router.py (no lifespan, fake DB session
via ``dependency_overrides``), except the slowapi limiter is ENABLED for the
duration of a test and its in-memory storage is reset before and after, so no
counter leaks into sibling files (which run with the limiter disabled).
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from src.api.rate_limit import _format_wait, _retry_after_seconds

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
    def scalar_one_or_none(self):
        return None


class _FakeSession:
    async def execute(self, *_a, **_k):
        return _FakeResult()

    def add(self, _obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, _obj):
        pass


class _FakeBruteForce:
    async def check_and_increment(self, email, ip):
        return None

    async def reset(self, email):
        pass


# ──────────────────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────────────────


def _forget_route_registrations(limiter) -> None:
    """Drop the per-route limit registrations left by PREVIOUS imports.

    Every test re-imports the router modules (module-cache isolation above) and
    each import re-runs ``@limiter.limit``, which APPENDS to the limiter's
    per-route registry. Without this, the n-th test would evaluate n stacked
    copies of the same limit and count a single request n times.
    """
    for attr in ("_route_limits", "_dynamic_route_limits", "_Limiter__marked_for_limiting"):
        registry = getattr(limiter, attr, None)
        if isinstance(registry, dict):
            registry.clear()


@pytest.fixture
def app_objects():
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

        from src.api.rate_limit import limiter

        # The routers are about to be re-imported (and re-decorated) by main.
        _forget_route_registrations(limiter)

        from src.api.main import app

        limiter.enabled = False
        try:
            yield app
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    from src.auth.router import get_db_session

    async def _fake_db():
        yield _FakeSession()

    app_objects.dependency_overrides[get_db_session] = _fake_db
    return TestClient(app_objects)


@pytest.fixture
def limits(app_objects):
    """Enable the limiter with small auth limits; reset storage around the test."""
    from src.api.main import limiter
    from src.config import get_settings

    patched = get_settings().model_copy(
        update={
            "auth_rate_limit_register": "2/hour",
            "auth_rate_limit_login": "2/minute",
            "auth_rate_limit_refresh": "2/minute",
            "trusted_proxy_count": 1,
        }
    )
    limiter.reset()
    limiter.enabled = True
    with (
        patch("src.api.rate_limit.get_settings", return_value=patched),
        patch("src.config.get_settings", return_value=patched),
    ):
        yield limiter
    limiter.enabled = False
    limiter.reset()


def _register_body(i: int) -> dict:
    return {
        "email": f"user{i}@acme.com",
        "password": "supersecret123",
        "name": "User",
        "organization_name": "Acme Srl",
    }


# ──────────────────────────────────────────────────────────────────────────
#  Register
# ──────────────────────────────────────────────────────────────────────────


class TestRegisterRateLimit:
    def test_third_registration_from_same_ip_is_429(self, client, limits):
        assert client.post("/api/v1/auth/register", json=_register_body(1)).status_code == 201
        assert client.post("/api/v1/auth/register", json=_register_body(2)).status_code == 201

        r = client.post("/api/v1/auth/register", json=_register_body(3))
        assert r.status_code == 429
        body = r.json()
        # UI-friendly detail (Italian), technical limit kept under "error".
        assert body["detail"].startswith("Troppe richieste")
        assert "2 per 1 hour" in body["error"]
        # Retry-After is a positive number of seconds, mirrored in the body.
        retry_after = int(r.headers["Retry-After"])
        assert retry_after >= 1
        assert body["retry_after"] == retry_after

    def test_other_ip_behind_trusted_proxy_has_own_bucket(self, client, limits):
        for i in range(2):
            assert client.post("/api/v1/auth/register", json=_register_body(i)).status_code == 201
        assert client.post("/api/v1/auth/register", json=_register_body(9)).status_code == 429

        # The trusted proxy appended a different client IP -> fresh bucket.
        other = {"X-Forwarded-For": "203.0.113.7"}
        r = client.post("/api/v1/auth/register", json=_register_body(10), headers=other)
        assert r.status_code == 201

    def test_spoofed_leftmost_xff_does_not_reset_bucket(self, client, limits):
        # With ONE trusted proxy only the LAST entry is honoured, so a forged
        # leftmost entry cannot rotate the key (both requests share the real IP).
        h1 = {"X-Forwarded-For": "1.1.1.1, 203.0.113.9"}
        h2 = {"X-Forwarded-For": "2.2.2.2, 203.0.113.9"}
        assert (
            client.post("/api/v1/auth/register", json=_register_body(1), headers=h1).status_code
            == 201
        )
        assert (
            client.post("/api/v1/auth/register", json=_register_body(2), headers=h2).status_code
            == 201
        )
        assert (
            client.post("/api/v1/auth/register", json=_register_body(3), headers=h1).status_code
            == 429
        )

    def test_limit_not_applied_when_limiter_disabled(self, client, limits):
        limits.enabled = False
        for i in range(5):
            assert client.post("/api/v1/auth/register", json=_register_body(i)).status_code == 201


# ──────────────────────────────────────────────────────────────────────────
#  Login / refresh
# ──────────────────────────────────────────────────────────────────────────


class TestLoginRefreshRateLimit:
    def test_login_failures_count_and_then_429(self, client, limits):
        body = {"email": "ghost@acme.com", "password": "whatever123"}
        with patch("src.auth.brute_force.brute_force", _FakeBruteForce()):
            assert client.post("/api/v1/auth/login", json=body).status_code == 401
            assert client.post("/api/v1/auth/login", json=body).status_code == 401
            r = client.post("/api/v1/auth/login", json=body)
        assert r.status_code == 429
        assert "Troppe richieste" in r.json()["detail"]
        assert "Retry-After" in r.headers

    def test_refresh_is_limited_before_token_validation(self, client, limits):
        body = {"refresh_token": "not-a-jwt"}
        assert client.post("/api/v1/auth/refresh", json=body).status_code == 401
        assert client.post("/api/v1/auth/refresh", json=body).status_code == 401
        r = client.post("/api/v1/auth/refresh", json=body)
        assert r.status_code == 429
        assert "2 per 1 minute" in r.json()["error"]

    def test_login_and_register_buckets_are_independent(self, client, limits):
        for i in range(2):
            assert client.post("/api/v1/auth/register", json=_register_body(i)).status_code == 201
        assert client.post("/api/v1/auth/register", json=_register_body(3)).status_code == 429
        # Register exhausted, login (same IP) still allowed: limits are per route.
        with patch("src.auth.brute_force.brute_force", _FakeBruteForce()):
            r = client.post(
                "/api/v1/auth/login", json={"email": "a@b.io", "password": "whatever123"}
            )
        assert r.status_code == 401


# ──────────────────────────────────────────────────────────────────────────
#  Handler helpers
# ──────────────────────────────────────────────────────────────────────────


class TestHandlerHelpers:
    @pytest.mark.parametrize(
        ("seconds", "expected"),
        [
            (1, "1 secondo"),
            (45, "45 secondi"),
            (60, "1 minuto"),
            (61, "2 minuti"),
            (3540, "59 minuti"),
        ],
    )
    def test_format_wait(self, seconds, expected):
        assert _format_wait(seconds) == expected

    def test_retry_after_falls_back_when_window_unavailable(self):
        # No view_rate_limit on the request state -> safe positive fallback.
        request = types.SimpleNamespace(state=types.SimpleNamespace())
        assert _retry_after_seconds(request) >= 1
