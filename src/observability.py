"""Logging, Sentry, OpenTelemetry + Prometheus observability stack.

Provides:
- Real logging configuration (setup_logging): root/uvicorn/structlog loggers
  driven by settings.log_level, one consistent format (plain or JSON) for
  stdlib and structlog records, and a dedicated ``normaai.audit`` logger that
  is never filtered below INFO
- Optional Sentry error tracking (setup_sentry) with the FastAPI integration
- Distributed tracing (Jaeger via OTLP)
- Prometheus metrics endpoint (/metrics)
- LLM call tracking (latency, tokens, cost)
- Request metrics (count, latency p50/p95/p99, error rate)

Initialize once at startup via setup_logging() / setup_sentry() /
setup_observability().
"""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TextIO

import structlog

if TYPE_CHECKING:
    from src.config import Settings

logger = logging.getLogger(__name__)

APP_VERSION = "0.3.0"

# Logger that carries the audit trail (see src.audit). Configured at INFO
# regardless of the global level so audit events are never filtered out.
AUDIT_LOGGER_NAME = "normaai.audit"

# uvicorn installs its own handlers on these; we route them through the root
# handler so server/access logs share the application format.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Third-party loggers that are too chatty at INFO.
_NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "asyncio", "watchfiles")

# Marker attribute on the handler we install, so re-running setup_logging
# (import time + lifespan, or test re-imports) replaces it instead of stacking.
_HANDLER_MARK = "_normaai_log_handler"


# ─── Logging ──────────────────────────────────────────────────────


def _parse_level(name: str | None) -> int:
    """Map a LOG_LEVEL string to a logging level, defaulting to INFO."""
    level = logging.getLevelName(str(name or "INFO").strip().upper())
    if isinstance(level, int):
        return level
    logger.warning("invalid_log_level", extra={"log_level": name, "fallback": "INFO"})
    return logging.INFO


def _shared_processors() -> list[Any]:
    """Processors applied to BOTH structlog events and foreign stdlib records."""
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]


def build_log_formatter(json_output: bool) -> logging.Formatter:
    """Formatter rendering stdlib and structlog records the same way.

    plain: ``2026-10-23T10:00:00Z [info     ] event   [logger] key=value``
    json:  ``{"event": ..., "level": ..., "logger": ..., "timestamp": ..., ...}``
    """
    renderer: Any
    render_chain: list[Any] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta]
    if json_output:
        render_chain.append(structlog.processors.format_exc_info)
        renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        # plain_traceback: with `rich` installed the default formatter renders ANSI
        # boxes with locals - unreadable in server logs and a PII leak risk.
        renderer = structlog.dev.ConsoleRenderer(
            colors=False, exception_formatter=structlog.dev.plain_traceback
        )
    render_chain.append(renderer)
    return structlog.stdlib.ProcessorFormatter(
        # ExtraAdder lifts ``extra={...}`` fields of stdlib records into the
        # event dict so they are rendered instead of silently dropped.
        foreign_pre_chain=[structlog.stdlib.ExtraAdder(), *_shared_processors()],
        processors=render_chain,
    )


def configure_structlog() -> None:
    """Route structlog through stdlib logging (rendering happens in the handler)."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *_shared_processors(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


def setup_logging(settings: Settings | None = None, *, stream: TextIO | None = None) -> None:
    """Configure logging for real, from settings. Idempotent.

    - root logger: level ``settings.log_level``, ONE stream handler (stderr)
      with the plain/JSON formatter; a previous handler installed by this
      function is replaced, foreign handlers (pytest, callers) are kept
    - uvicorn loggers: their own handlers are dropped and they propagate to the
      root handler, so server/access lines share the application format
    - ``normaai.audit``: pinned at INFO so the audit trail is emitted even when
      LOG_LEVEL is WARNING (propagation bypasses the root level)
    - structlog: configured to render through the same formatter
    """
    if settings is None:
        from src.config import get_settings

        settings = get_settings()

    level = _parse_level(getattr(settings, "log_level", "INFO"))
    json_output = getattr(settings, "log_format", "plain") == "json"

    configure_structlog()

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(build_log_formatter(json_output))
    setattr(handler, _HANDLER_MARK, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _HANDLER_MARK, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _UVICORN_LOGGERS:
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
        uv_logger.setLevel(level)

    audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)
    audit_logger.setLevel(min(level, logging.INFO))
    audit_logger.propagate = True

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    logger.info(
        "logging_configured",
        extra={
            "log_level": logging.getLevelName(level),
            "log_format": "json" if json_output else "plain",
        },
    )


# ─── Sentry (optional) ────────────────────────────────────────────


def setup_sentry(settings: Settings | None = None) -> bool:
    """Initialise Sentry when ``settings.sentry_dsn`` is set and the SDK is installed.

    Returns True when the SDK was initialised. A missing DSN disables it; a
    missing SDK (optional extra) logs a warning instead of failing startup.
    """
    if settings is None:
        from src.config import get_settings

        settings = get_settings()

    dsn = str(getattr(settings, "sentry_dsn", None) or "").strip()
    if not dsn:
        logger.info("sentry_disabled", extra={"reason": "SENTRY_DSN not set"})
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        logger.warning(
            "sentry_sdk_not_installed",
            extra={"hint": "install the optional extra: poetry install -E sentry"},
        )
        return False

    environment = getattr(settings, "app_env", "development")
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=f"normaai@{APP_VERSION}",
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logger.info("sentry_initialized", extra={"environment": environment})
    return True


# ─── Metrics (Prometheus-compatible) ─────────────────────────────

_metrics_available = False
_tracer_available = False

try:
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    _tracer_available = True
except ImportError:
    _tracer_available = False

try:
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        Counter,
        Gauge,
        Histogram,
        Info,
        generate_latest,
    )

    _metrics_available = True
except ImportError:
    _metrics_available = False


# ─── Prometheus Metrics Definitions ──────────────────────────────

if _metrics_available:
    APP_INFO = Info("normaai", "NormaAI application info")

    REQUEST_COUNT = Counter(
        "normaai_http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
    )

    REQUEST_LATENCY = Histogram(
        "normaai_http_request_duration_seconds",
        "HTTP request latency",
        ["method", "endpoint"],
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0],
    )

    LLM_CALL_COUNT = Counter(
        "normaai_llm_calls_total",
        "Total LLM API calls",
        ["provider", "model", "status"],
    )

    LLM_CALL_LATENCY = Histogram(
        "normaai_llm_call_duration_seconds",
        "LLM call latency",
        ["provider", "model"],
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0],
    )

    LLM_TOKENS = Counter(
        "normaai_llm_tokens_total",
        "Total LLM tokens consumed",
        ["provider", "direction"],  # direction: input/output
    )

    QDRANT_QUERY_LATENCY = Histogram(
        "normaai_qdrant_query_duration_seconds",
        "Qdrant search latency",
        buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    )

    CACHE_HITS = Counter("normaai_cache_hits_total", "Cache hits", ["task_type"])
    CACHE_MISSES = Counter("normaai_cache_misses_total", "Cache misses", ["task_type"])

    CIRCUIT_STATE = Gauge(
        "normaai_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=half_open, 2=open)",
        ["service"],
    )

    ACTIVE_REQUESTS = Gauge("normaai_active_requests", "Currently processing requests")

    # ─── Local LLM Metrics ──────────────────────────────────────
    LOCAL_LLM_CALL_COUNT = Counter(
        "normaai_local_llm_calls_total",
        "Total local LLM calls",
        ["status"],  # success / error / fallback
    )

    LOCAL_LLM_CALL_LATENCY = Histogram(
        "normaai_local_llm_call_duration_seconds",
        "Local LLM call latency",
        buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0],
    )

    COMPLEXITY_GATE_COUNT = Counter(
        "normaai_complexity_gate_total",
        "Complexity gate routing decisions",
        ["tier"],  # simple / medium / complex
    )

    SIMPLE_RESPONSE_CACHE_HITS = Counter(
        "normaai_simple_response_cache_hits_total",
        "Simple response cache hits (bypassed remote LLM)",
    )


def setup_observability(app=None) -> None:
    """Initialize observability stack. Call once at startup."""
    if _metrics_available:
        from src.config import get_settings

        settings = get_settings()
        APP_INFO.info(
            {
                "version": APP_VERSION,
                "environment": settings.app_env,
                "llm_provider": settings.llm_provider,
            }
        )
        logger.info("prometheus_metrics_initialized")

    if _tracer_available:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        resource = Resource.create({"service.name": "normaai", "service.version": APP_VERSION})
        provider = TracerProvider(resource=resource)
        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            logger.info("opentelemetry_tracing_initialized", extra={"endpoint": otlp_endpoint})
        except Exception as e:
            logger.warning("opentelemetry_init_failed", extra={"error": str(e)})

        if app is not None:
            try:
                FastAPIInstrumentor.instrument_app(app)
                logger.info("fastapi_instrumented")
            except Exception as e:
                logger.warning("fastapi_instrumentation_failed", extra={"error": str(e)})


def get_metrics_response():
    """Generate Prometheus metrics response for /metrics endpoint."""
    if not _metrics_available:
        return "# Prometheus client not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST


@contextmanager
def track_llm_call(provider: str, model: str):
    """Context manager to track LLM call metrics."""
    start = time.perf_counter()
    status = "success"
    try:
        yield
    except Exception:
        status = "error"
        raise
    finally:
        elapsed = time.perf_counter() - start
        if _metrics_available:
            LLM_CALL_COUNT.labels(provider=provider, model=model, status=status).inc()
            LLM_CALL_LATENCY.labels(provider=provider, model=model).observe(elapsed)


def record_llm_tokens(provider: str, input_tokens: int, output_tokens: int) -> None:
    """Record LLM token usage for cost tracking."""
    if _metrics_available:
        LLM_TOKENS.labels(provider=provider, direction="input").inc(input_tokens)
        LLM_TOKENS.labels(provider=provider, direction="output").inc(output_tokens)
