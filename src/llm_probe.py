"""Can the model provider answer with the configured key and model?

GET /readyz asks (src/api/routers/system.py), and so does the startup. One
request to the provider's endpoint for the configured model, with the
configured key and a 5-second timeout. It generates nothing, so it costs no
tokens:

    anthropic   GET https://api.anthropic.com/v1/models/<ANTHROPIC_MODEL>
    gemini      GET https://generativelanguage.googleapis.com/v1beta/models/<GEMINI_MODEL>
    mistral     GET <MISTRAL_BASE_URL>/models/<MISTRAL_MODEL>
    openrouter  GET <OPENROUTER_BASE_URL>/key (the key's remaining credit)

It finds a revoked or wrong key and a model id the provider does not serve.
Anthropic, Google and Mistral say nothing about the credit or the quota left
until a generation is refused: an exhausted credit shows up as failed answers
instead, logged at ERROR (so in Sentry when SENTRY_DSN is set) and, after five
failures in a row, as the open LLM circuit, which /readyz reports as well. The
spending limit set at the provider sends its own warning (docs/RUNBOOK.md, 4).

The answer is kept 5 minutes when the provider accepted the key and 1 minute
when it did not, per API process, and concurrent callers share one request, so
a public /readyz cannot make the API call the provider more often than that.
The key goes in a request header only: it is never in a URL, a log line or an
answer. Under APP_ENV=testing nothing is sent.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import structlog

logger = structlog.get_logger()

PROBE_TIMEOUT_SECONDS = 5.0
# How long an answer is reused: a good one for 5 minutes, a failure for 1.
OK_TTL_SECONDS = 300.0
FAILED_TTL_SECONDS = 60.0

ANTHROPIC_API = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
GEMINI_API = "https://generativelanguage.googleapis.com/v1beta"

# The reasons /readyz reports in "llm" (with "circuit_open", set by the router).
OK = "ok"
NOT_CHECKED = "not_checked"
MISSING_KEY = "missing_key"
KEY_REJECTED = "key_rejected"
MODEL_NOT_FOUND = "model_not_found"
NO_CREDIT = "no_credit"
RATE_LIMITED = "rate_limited"
PROVIDER_ERROR = "provider_error"
UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ProbeResult:
    """What the provider said: ``ok`` and a reason from the list above."""

    ok: bool
    reason: str
    checked_at: float
    status_code: int | None = None

    def fresh(self, now: float) -> bool:
        ttl = OK_TTL_SECONDS if self.ok else FAILED_TTL_SECONDS
        return now - self.checked_at < ttl


_cache: dict[tuple[str, ...], ProbeResult] = {}
_inflight: dict[tuple[str, ...], asyncio.Task[ProbeResult]] = {}


def _cache_key(settings: Any) -> tuple[str, ...]:
    # A digest, not the key: the cache must not keep a second copy of it.
    digest = hashlib.sha256(str(settings.active_api_key).encode()).hexdigest()[:16]
    return (str(settings.llm_provider), str(settings.active_model), _base_url(settings), digest)


def _base_url(settings: Any) -> str:
    if settings.llm_provider == "mistral":
        return str(settings.mistral_base_url).rstrip("/")
    if settings.llm_provider == "openrouter":
        return str(settings.openrouter_base_url).rstrip("/")
    return ""


def probe_request(settings: Any) -> tuple[str, dict[str, str]]:
    """The URL and headers of the probe for the configured provider."""
    provider = settings.llm_provider
    key = str(settings.active_api_key)
    model = str(settings.active_model)
    if provider == "anthropic":
        url = f"{ANTHROPIC_API}/models/{quote(model, safe='')}"
        return url, {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    if provider == "gemini":
        name = model if model.startswith("models/") else f"models/{model}"
        return f"{GEMINI_API}/{quote(name, safe='/')}", {"x-goog-api-key": key}
    if provider == "mistral":
        url = f"{_base_url(settings)}/models/{quote(model, safe='')}"
        return url, {"Authorization": f"Bearer {key}"}
    if provider == "openrouter":
        return f"{_base_url(settings)}/key", {"Authorization": f"Bearer {key}"}
    raise ValueError(f"no probe for LLM_PROVIDER={provider!r}")


def interpret(provider: str, status_code: int, payload: Any) -> str:
    """The reason for an answer of the provider (``ok`` when it is usable)."""
    if status_code == 200:
        if provider == "openrouter" and isinstance(payload, dict):
            data = payload.get("data")
            remaining = data.get("limit_remaining") if isinstance(data, dict) else None
            if isinstance(remaining, int | float) and remaining <= 0:
                return NO_CREDIT
        return OK
    if status_code in (401, 403):
        return KEY_REJECTED
    if status_code == 400 and provider == "gemini":
        # Google answers 400 (API_KEY_INVALID) to a key it does not know.
        return KEY_REJECTED
    if status_code == 404:
        return MODEL_NOT_FOUND
    if status_code == 402:
        return NO_CREDIT
    if status_code == 429:
        return RATE_LIMITED
    return PROVIDER_ERROR


async def _ask(settings: Any, transport: httpx.AsyncBaseTransport | None = None) -> ProbeResult:
    url, headers = probe_request(settings)
    try:
        async with httpx.AsyncClient(
            timeout=PROBE_TIMEOUT_SECONDS, transport=transport, follow_redirects=False
        ) as client:
            reply = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        # The type only: some messages repeat the request, and the request
        # carries the key in a header.
        logger.debug("llm_probe_unreachable", error=type(e).__name__)
        return ProbeResult(False, UNREACHABLE, time.time())
    payload: Any = None
    if settings.llm_provider == "openrouter" and reply.status_code == 200:
        try:
            payload = reply.json()
        except ValueError:
            payload = None
    reason = interpret(settings.llm_provider, reply.status_code, payload)
    return ProbeResult(reason == OK, reason, time.time(), reply.status_code)


async def llm_readiness(
    settings: Any, *, transport: httpx.AsyncBaseTransport | None = None
) -> ProbeResult:
    """The provider's verdict on the configured key and model, from the cache when fresh.

    Never raises. ``transport`` replaces the network in tests.
    """
    now = time.time()
    if not settings.active_api_key:
        return ProbeResult(False, MISSING_KEY, now)
    if settings.app_env == "testing" and transport is None:
        return ProbeResult(True, NOT_CHECKED, now)
    key = _cache_key(settings)
    cached = _cache.get(key)
    if cached is not None and cached.fresh(now):
        return cached

    loop = asyncio.get_running_loop()
    task = _inflight.get(key)
    if task is None or task.done() or task.get_loop() is not loop:
        task = loop.create_task(_refresh(key, settings, cached, transport))
        _inflight[key] = task
    try:
        # Shielded: a caller that goes away does not cancel the shared request.
        return await asyncio.shield(task)
    except Exception as e:  # noqa: BLE001 - a bug here must not turn into a 500
        logger.warning("llm_probe_error", error=type(e).__name__)
        return ProbeResult(False, PROVIDER_ERROR, time.time())
    finally:
        if task.done() and _inflight.get(key) is task:
            del _inflight[key]


async def _refresh(
    key: tuple[str, ...],
    settings: Any,
    previous: ProbeResult | None,
    transport: httpx.AsyncBaseTransport | None,
) -> ProbeResult:
    """One request for every caller waiting on it: ask, log a change, keep the answer."""
    result = await _ask(settings, transport)
    _report_change(previous, result, settings)
    _cache[key] = result
    return result


def _report_change(previous: ProbeResult | None, result: ProbeResult, settings: Any) -> None:
    """Log a change once: ERROR when the provider stops accepting (Sentry sees it)."""
    was_ok = previous.ok if previous is not None else None
    if result.ok and was_ok is not True:
        logger.info("llm_probe_ok", provider=settings.llm_provider, model=settings.active_model)
    elif not result.ok and was_ok is not False:
        logger.error(
            "llm_probe_failed",
            provider=settings.llm_provider,
            model=settings.active_model,
            reason=result.reason,
            status_code=result.status_code,
        )


def reset_cache() -> None:
    """Forget every answer (tests, or after the key changed in a running process)."""
    _cache.clear()
    _inflight.clear()
