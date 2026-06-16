"""FastAPI middleware: request ID, timing, metrics, and security headers.

Extracted from main.py for single-responsibility.
"""

import threading
import time
import uuid
from collections import defaultdict, deque

import structlog
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


# ─── Request Metrics ──────────────────────────────────────────────


class RequestMetrics:
    """Thread-safe request metrics collector with bounded memory."""

    MAX_LATENCIES = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self.total_requests = 0
        self.error_count = 0
        self.endpoint_counts: dict[str, int] = defaultdict(int)
        self.endpoint_latencies: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=RequestMetrics.MAX_LATENCIES)
        )

    def record(self, endpoint: str, latency: float, is_error: bool = False):
        with self._lock:
            self.total_requests += 1
            self.endpoint_counts[endpoint] += 1
            self.endpoint_latencies[endpoint].append(latency)
            if is_error:
                self.error_count += 1

    def summary(self) -> dict:
        with self._lock:
            result = {
                "total_requests": self.total_requests,
                "error_count": self.error_count,
                "endpoints": {},
            }
            for ep, count in self.endpoint_counts.items():
                latencies = list(self.endpoint_latencies.get(ep, []))
                result["endpoints"][ep] = {
                    "count": count,
                    "avg_latency_ms": round(sum(latencies) / len(latencies) * 1000, 1)
                    if latencies
                    else 0,
                    "max_latency_ms": round(max(latencies) * 1000, 1) if latencies else 0,
                    "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)] * 1000, 1)
                    if len(latencies) >= 20
                    else 0,
                }
            return result


metrics = RequestMetrics()


# ─── Security Headers Middleware ──────────────────────────────────


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response.

    Headers:
    - X-Content-Type-Options: nosniff — prevent MIME-type sniffing
    - X-Frame-Options: DENY — prevent clickjacking
    - X-XSS-Protection: 0 — disable legacy XSS filter (modern CSP is better)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: restrict dangerous APIs
    - Strict-Transport-Security: HSTS (production only)
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )

        # HSTS only in production (requires HTTPS)
        from src.config import get_settings

        if get_settings().app_env == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response


def register_middleware(app: FastAPI) -> None:
    """Register all middleware on the FastAPI app."""

    # Security headers (outermost — runs first)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def add_request_id_middleware(request: Request, call_next):
        """Generate and attach a unique request ID to every request."""
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def add_timing_and_metrics_middleware(request: Request, call_next):
        """Add X-Process-Time header and record metrics."""
        start = time.perf_counter()
        endpoint = f"{request.method} {request.url.path}"

        try:
            response = await call_next(request)
            elapsed = time.perf_counter() - start
            is_error = response.status_code >= 400
            metrics.record(endpoint, elapsed, is_error=is_error)
            response.headers["X-Process-Time"] = f"{elapsed:.3f}s"
            return response
        except Exception as e:
            elapsed = time.perf_counter() - start
            metrics.record(endpoint, elapsed, is_error=True)
            logger.error("middleware_error", endpoint=endpoint, error=str(e))
            raise
