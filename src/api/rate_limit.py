"""Rate limiter singleton and 429 response shaping.

Extracted from main.py so routers can import the limiter
without importing the entire main module (breaks circular imports).

Key functions:
- ``_rate_limit_key`` (the limiter default): user_id from the JWT when present,
  else the spoof-resistant client IP from ``src.audit.get_client_ip``.
- ``client_ip_key``: ALWAYS the client IP. Used by the unauthenticated auth
  endpoints (register/login/refresh) where a per-user key is meaningless.
- ``settings_limit``: a per-request limit provider that reads the limit string
  from ``Settings`` so limits are configurable (and patchable in tests).

The 429 handler (``rate_limit_exceeded_handler``) returns the FastAPI-standard
``detail`` field (the Italian UI renders ``detail``) plus a ``Retry-After``
header computed from the limiter's window stats.
"""

import logging
import math
import time
from collections.abc import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from src.audit import AuditAction, AuditOutcome, audit_log, get_client_ip
from src.config import get_settings

logger = logging.getLogger(__name__)

# Fallback Retry-After when the limiter cannot report its window (never 0: a
# client that retries immediately would just hit the limit again).
_FALLBACK_RETRY_AFTER_SECONDS = 60


def client_ip_key(request: Request) -> str:
    """Per-IP rate limit key, resistant to X-Forwarded-For spoofing.

    Reuses ``get_client_ip`` so the limited IP is the one appended by our own
    trusted proxy, never the client-forgeable leftmost header entry (which would
    let an attacker rotate keys for free) and never the proxy's own address
    (which would make a per-IP limit a global one).
    """
    return f"ip:{get_client_ip(request)}"


def _rate_limit_key(request: Request) -> str:
    """Rate limit key: user_id from JWT if available, fallback to client IP.

    This provides per-user rate limiting for authenticated requests
    and per-IP for unauthenticated ones.
    """
    # Try to extract user_id from already-parsed JWT
    if hasattr(request.state, "user_id"):
        return f"user:{request.state.user_id}"

    # Try to extract from Authorization header without full JWT decode
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import base64
            import json

            token = auth_header[7:]
            # Decode JWT payload (middle part) without verification
            payload_b64 = token.split(".")[1]
            # Add padding
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            user_id = payload.get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass

    return client_ip_key(request)


def settings_limit(attr: str) -> Callable[[], str]:
    """Return a zero-arg limit provider reading ``Settings.<attr>`` per request.

    slowapi evaluates a callable ``limit_value`` on EVERY request, so the limit
    follows the live settings (and a test can patch ``get_settings``) instead
    of being frozen into the decorator at import time.
    """

    def _provider() -> str:
        return str(getattr(get_settings(), attr))

    _provider.__name__ = f"limit_{attr}"
    return _provider


limiter = Limiter(key_func=_rate_limit_key)


# ─── 429 response shaping ─────────────────────────────────────────


def _format_wait(seconds: int) -> str:
    """Human-readable (Italian) wait for the 429 detail message."""
    if seconds < 60:
        return "1 secondo" if seconds == 1 else f"{seconds} secondi"
    minutes = math.ceil(seconds / 60)
    return "1 minuto" if minutes == 1 else f"{minutes} minuti"


def _retry_after_seconds(request: Request) -> int:
    """Seconds until the exhausted window resets (always >= 1).

    slowapi stores the hit limit as ``(RateLimitItem, [key, scope])`` on
    ``request.state.view_rate_limit`` before raising; the limits backend reports
    the window's absolute reset time via ``get_window_stats``.
    """
    try:
        item, args = request.state.view_rate_limit
        window = limiter.limiter.get_window_stats(item, *args)
        return max(1, math.ceil(window[0] - time.time()))
    except Exception as e:  # noqa: BLE001 - the header is best-effort
        logger.debug("retry_after_unavailable: %s", e)
        return _FALLBACK_RETRY_AFTER_SECONDS


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Build the 429 response for a hit limit.

    Body: ``detail`` (what the UI shows - a per-route ``error_message`` if the
    decorator set one, else a generic Italian message with the wait), ``error``
    (the technical limit, kept for backward compatibility with the previous
    slowapi default body) and ``retry_after`` (seconds). The same value is sent
    as the ``Retry-After`` header.
    """
    retry_after = _retry_after_seconds(request)
    limit = exc.limit
    custom_message = limit.error_message if limit is not None else None
    if custom_message:
        detail = custom_message() if callable(custom_message) else str(custom_message)
    else:
        detail = f"Troppe richieste. Riprova tra {_format_wait(retry_after)}."
    limit_desc = str(limit.limit) if limit is not None else str(exc.detail)

    audit_log(
        AuditAction.RATE_LIMIT_HIT,
        AuditOutcome.DENIED,
        ip_address=get_client_ip(request),
        resource=request.url.path,
        detail=limit_desc,
    )
    return JSONResponse(
        {
            "detail": detail,
            "error": f"Rate limit exceeded: {limit_desc}",
            "retry_after": retry_after,
        },
        status_code=429,
        headers={"Retry-After": str(retry_after)},
    )
