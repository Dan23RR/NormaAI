"""Rate limits: shared storage, in-memory fallback, the default limit.

- The counters live in Redis (RATE_LIMIT_STORAGE_URI, else REDIS_URL), so all
  API processes count the same requests; "memory://" keeps them per process
  (the test suite pins it, tests/conftest.py).
- When Redis cannot be reached the limiter keeps limiting from memory, with a
  warning, instead of failing or letting everything through.
- RATE_LIMIT_DEFAULT is the limit of every route that declares none
  (SlowAPIMiddleware); a route's own limit still applies to it.
"""

from __future__ import annotations

import logging
import sys

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from limits.storage import MemoryStorage, RedisStorage
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api import rate_limit
from src.api.rate_limit import (
    build_limiter,
    check_limiter_storage,
    rate_limit_exceeded_handler,
    rate_limit_storage_uri,
)
from src.config import Settings


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """One test imports src.api.main: evict it and the routers afterwards, like
    the router tests do, so no later test gets modules bound to a mock engine."""
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


def _settings(**overrides) -> Settings:
    return Settings(_env_file=None, app_secret_key="x" * 40, **overrides)


class TestWhereTheCountersLive:
    def test_redis_url_by_default(self, monkeypatch):
        monkeypatch.delenv("RATE_LIMIT_STORAGE_URI", raising=False)
        settings = _settings(redis_url="redis://cache:6379/0")
        assert rate_limit_storage_uri(settings) == "redis://cache:6379/0"

    def test_an_explicit_uri_wins(self):
        settings = _settings(redis_url="redis://cache:6379/0", rate_limit_storage_uri="memory://")
        assert rate_limit_storage_uri(settings) == "memory://"

    def test_without_redis_memory(self):
        assert (
            rate_limit_storage_uri(_settings(redis_url="", rate_limit_storage_uri=""))
            == "memory://"
        )

    def test_redis_storage_with_the_memory_fallback(self):
        limiter = build_limiter(
            _settings(redis_url="redis://127.0.0.1:1/0", rate_limit_storage_uri="")
        )
        assert isinstance(limiter._storage, RedisStorage)
        assert limiter._in_memory_fallback_enabled is True

    def test_memory_storage_needs_no_fallback(self):
        limiter = build_limiter(_settings(rate_limit_storage_uri="memory://"))
        assert isinstance(limiter._storage, MemoryStorage)
        assert limiter._in_memory_fallback_enabled is False

    def test_the_app_limiter_follows_the_settings(self):
        from src.config import get_settings

        # tests/conftest.py: counters in memory, no default limit in the suite.
        assert get_settings().rate_limit_storage_uri == "memory://"
        assert get_settings().rate_limit_default == ""
        assert isinstance(rate_limit.limiter._storage, MemoryStorage)
        assert rate_limit.limiter._default_limits == []

    def test_the_default_limit_is_100_a_minute(self, monkeypatch):
        monkeypatch.delenv("RATE_LIMIT_DEFAULT", raising=False)
        settings = _settings(rate_limit_storage_uri="memory://")
        assert settings.rate_limit_default == "100/minute"
        limiter = build_limiter(settings)
        defaults = [str(limit.limit) for group in limiter._default_limits for limit in group]
        assert defaults == ["100 per 1 minute"]

    def test_the_app_applies_the_default_through_the_middleware(self):
        from unittest.mock import MagicMock, patch

        from src.config import get_settings

        with (
            patch("src.api.lifespan.validate_settings_or_exit", return_value=get_settings()),
            patch.dict(
                "sys.modules",
                {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
            ),
        ):
            from src.api.main import app

        assert any(m.cls is SlowAPIMiddleware for m in app.user_middleware)
        assert app.state.limiter is rate_limit.limiter


def _app(limiter) -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/plain")
    async def plain():
        return {"ok": True}

    @app.get("/own")
    @limiter.limit("5/minute")
    async def own(request: Request):
        return {"ok": True}

    return app


class TestTheDefaultLimit:
    def test_routes_without_a_limit_get_rate_limit_default(self):
        limiter = build_limiter(
            _settings(rate_limit_storage_uri="memory://", rate_limit_default="2/minute")
        )
        client = TestClient(_app(limiter))
        assert [client.get("/plain").status_code for _ in range(3)] == [200, 200, 429]
        r = client.get("/plain")
        assert r.json()["detail"].startswith("Troppe richieste")
        assert int(r.headers["Retry-After"]) >= 1

    def test_a_route_with_its_own_limit_keeps_it(self):
        limiter = build_limiter(
            _settings(rate_limit_storage_uri="memory://", rate_limit_default="2/minute")
        )
        client = TestClient(_app(limiter))
        assert [client.get("/own").status_code for _ in range(6)] == [200] * 5 + [429]

    def test_an_empty_default_means_no_default(self):
        limiter = build_limiter(
            _settings(rate_limit_storage_uri="memory://", rate_limit_default="")
        )
        client = TestClient(_app(limiter))
        assert {client.get("/plain").status_code for _ in range(5)} == {200}


class TestRedisDown:
    def test_the_limits_still_hold_from_memory_with_a_warning(self, monkeypatch, caplog):
        limiter = build_limiter(
            _settings(
                redis_url="redis://127.0.0.1:1/0",
                rate_limit_storage_uri="",
                rate_limit_default="2/minute",
            )
        )

        def _down(*_args, **_kwargs):
            raise ConnectionError("redis down")

        monkeypatch.setattr(limiter._storage, "incr", _down)
        monkeypatch.setattr(limiter._storage, "get", _down)
        monkeypatch.setattr(limiter._storage, "check", lambda: False)
        client = TestClient(_app(limiter))
        with caplog.at_level(logging.WARNING, logger="slowapi"):
            codes = [client.get("/plain").status_code for _ in range(3)]
        assert codes == [200, 200, 429]  # counted in memory, not failed open
        assert limiter._storage_dead is True
        assert any("falling back to in-memory" in r.getMessage() for r in caplog.records)


class TestStartupCheck:
    def test_memory_is_a_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger=rate_limit.logger.name):
            assert (
                check_limiter_storage(build_limiter(_settings(rate_limit_storage_uri="memory://")))
                is False
            )
        assert any("per process" in r.getMessage() for r in caplog.records)

    def test_an_unreachable_redis_is_a_warning(self, monkeypatch, caplog):
        settings = _settings(redis_url="redis://127.0.0.1:1/0", rate_limit_storage_uri="")
        limiter = build_limiter(settings)
        monkeypatch.setattr(limiter._storage, "check", lambda: False)
        monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
        with caplog.at_level(logging.WARNING, logger=rate_limit.logger.name):
            assert check_limiter_storage(limiter) is False
        assert any("Redis does not answer" in r.getMessage() for r in caplog.records)

    def test_a_reachable_redis_is_fine(self, monkeypatch):
        settings = _settings(redis_url="redis://127.0.0.1:1/0", rate_limit_storage_uri="")
        limiter = build_limiter(settings)
        monkeypatch.setattr(limiter._storage, "check", lambda: True)
        monkeypatch.setattr(rate_limit, "get_settings", lambda: settings)
        assert check_limiter_storage(limiter) is True


@pytest.mark.parametrize(
    "uri", ["redis://h:6379/0", "rediss://h:6380/0", "redis+sentinel://h:26379/m"]
)
def test_shared_schemes_count_as_redis(uri):
    assert rate_limit_storage_uri(_settings(redis_url=uri, rate_limit_storage_uri="")) == uri
