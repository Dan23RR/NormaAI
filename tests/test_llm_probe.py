"""src/llm_probe.py: the provider check behind the "llm" of GET /readyz.

The network is replaced by httpx.MockTransport: each test says what the
provider answers and checks which request went out and what /readyz is told.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import httpx
import pytest

from src import llm_probe

KEY = "sk-test-key-value-0123456789"


@pytest.fixture(autouse=True)
def _clean_cache():
    llm_probe.reset_cache()
    yield
    llm_probe.reset_cache()


def _settings(provider: str = "anthropic", **extra) -> SimpleNamespace:
    models = {
        "anthropic": "claude-haiku-5-5",
        "gemini": "gemini-3.6-flash",
        "mistral": "mistral-small-2603",
        "openrouter": "nvidia/nemotron-3-super-120b-a12b:free",
    }
    values = {
        "llm_provider": provider,
        "active_api_key": KEY,
        "active_model": models[provider],
        "app_env": "production",
        "mistral_base_url": "https://api.eu.mistral.ai/v1",
        "openrouter_base_url": "https://openrouter.ai/api/v1",
    }
    values.update(extra)
    return SimpleNamespace(**values)


class Provider:
    """A stand-in provider: records the requests, answers ``status`` with ``body``."""

    def __init__(self, status: int = 200, body: object = None, error: Exception | None = None):
        self.status, self.body, self.error = status, body, error
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, json=self.body if self.body is not None else {})

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    ("provider", "url", "header", "value"),
    [
        (
            "anthropic",
            "https://api.anthropic.com/v1/models/claude-haiku-5-5",
            "x-api-key",
            KEY,
        ),
        (
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash",
            "x-goog-api-key",
            KEY,
        ),
        (
            "mistral",
            "https://api.eu.mistral.ai/v1/models/mistral-small-2603",
            "authorization",
            f"Bearer {KEY}",
        ),
        ("openrouter", "https://openrouter.ai/api/v1/key", "authorization", f"Bearer {KEY}"),
    ],
)
def test_asks_the_model_endpoint_with_the_key_in_a_header(provider, url, header, value):
    upstream = Provider(200, {"id": "x"})
    result = _run(llm_probe.llm_readiness(_settings(provider), transport=upstream.transport))
    assert result.ok and result.reason == "ok"
    [request] = upstream.requests
    assert request.method == "GET"
    assert str(request.url) == url
    assert request.headers[header] == value
    # Never in the address, where proxies and logs would keep it.
    assert KEY not in str(request.url)


@pytest.mark.parametrize(
    ("provider", "status", "reason"),
    [
        ("anthropic", 401, "key_rejected"),
        ("anthropic", 403, "key_rejected"),
        ("anthropic", 404, "model_not_found"),
        ("gemini", 400, "key_rejected"),
        ("mistral", 400, "provider_error"),
        ("openrouter", 402, "no_credit"),
        ("anthropic", 429, "rate_limited"),
        ("anthropic", 529, "provider_error"),
    ],
)
def test_a_refusal_is_down_with_its_reason(provider, status, reason):
    upstream = Provider(status, {"error": {"message": "nope"}})
    result = _run(llm_probe.llm_readiness(_settings(provider), transport=upstream.transport))
    assert result.ok is False
    assert result.reason == reason
    assert result.status_code == status


def test_openrouter_without_credit_is_down():
    upstream = Provider(200, {"data": {"label": "x", "limit": 5, "limit_remaining": 0}})
    result = _run(llm_probe.llm_readiness(_settings("openrouter"), transport=upstream.transport))
    assert (result.ok, result.reason) == (False, "no_credit")


def test_an_unreachable_provider_is_down_and_the_error_names_no_secret(caplog):
    upstream = Provider(error=httpx.ConnectError(f"cannot connect with {KEY}"))
    with caplog.at_level(logging.DEBUG):
        result = _run(llm_probe.llm_readiness(_settings(), transport=upstream.transport))
    assert (result.ok, result.reason) == (False, "unreachable")
    assert KEY not in caplog.text


def test_without_a_key_nothing_is_sent():
    upstream = Provider(200)
    result = _run(
        llm_probe.llm_readiness(_settings(active_api_key=""), transport=upstream.transport)
    )
    assert (result.ok, result.reason) == (False, "missing_key")
    assert upstream.requests == []


def test_the_test_suite_never_calls_a_provider():
    result = _run(llm_probe.llm_readiness(_settings(app_env="testing")))
    assert (result.ok, result.reason) == (True, "not_checked")


def test_an_answer_is_reused_until_it_expires(monkeypatch):
    upstream = Provider(200)
    clock = [1_000.0]
    monkeypatch.setattr(llm_probe.time, "time", lambda: clock[0])

    async def three_calls():
        for step in (0, llm_probe.OK_TTL_SECONDS - 1, llm_probe.OK_TTL_SECONDS + 1):
            clock[0] = 1_000.0 + step
            await llm_probe.llm_readiness(_settings(), transport=upstream.transport)

    _run(three_calls())
    assert len(upstream.requests) == 2  # the first, and the one after the 5 minutes


def test_a_failure_is_asked_again_sooner(monkeypatch):
    upstream = Provider(401)
    clock = [1_000.0]
    monkeypatch.setattr(llm_probe.time, "time", lambda: clock[0])

    async def two_calls():
        await llm_probe.llm_readiness(_settings(), transport=upstream.transport)
        clock[0] += llm_probe.FAILED_TTL_SECONDS + 1
        await llm_probe.llm_readiness(_settings(), transport=upstream.transport)

    _run(two_calls())
    assert len(upstream.requests) == 2
    assert llm_probe.FAILED_TTL_SECONDS < llm_probe.OK_TTL_SECONDS


def test_concurrent_callers_share_one_request():
    seen: list[httpx.Request] = []

    async def slow(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        await asyncio.sleep(0.05)
        return httpx.Response(200, json={})

    async def many():
        transport = httpx.MockTransport(slow)
        return await asyncio.gather(
            *(llm_probe.llm_readiness(_settings(), transport=transport) for _ in range(10))
        )

    results = _run(many())
    assert all(r.ok for r in results)
    assert len(seen) == 1


def test_a_new_key_is_asked_again():
    upstream = Provider(200)

    async def two_keys():
        await llm_probe.llm_readiness(_settings(), transport=upstream.transport)
        await llm_probe.llm_readiness(
            _settings(active_api_key="sk-other"), transport=upstream.transport
        )

    _run(two_keys())
    assert len(upstream.requests) == 2


def test_a_change_is_logged_once_at_error(monkeypatch):
    events: list[tuple[str, str]] = []

    class Recorder:
        def info(self, event, **kw):
            events.append(("info", event))

        def error(self, event, **kw):
            assert KEY not in repr(kw)
            events.append(("error", event))

        def debug(self, event, **kw):
            pass

        def warning(self, event, **kw):
            events.append(("warning", event))

    monkeypatch.setattr(llm_probe, "logger", Recorder())
    clock = [1_000.0]
    monkeypatch.setattr(llm_probe.time, "time", lambda: clock[0])
    answers = iter([401, 401, 200])

    async def three():
        for _ in range(3):
            upstream = Provider(next(answers))
            await llm_probe.llm_readiness(_settings(), transport=upstream.transport)
            clock[0] += llm_probe.OK_TTL_SECONDS + 1

    _run(three())
    assert events == [("error", "llm_probe_failed"), ("info", "llm_probe_ok")]


def test_an_unknown_provider_never_raises():
    result = _run(
        llm_probe.llm_readiness(
            _settings(llm_provider="carrier-pigeon"), transport=Provider().transport
        )
    )
    assert (result.ok, result.reason) == (False, "provider_error")
