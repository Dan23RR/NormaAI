"""OpenTelemetry + Prometheus observability stack.

Provides:
- Distributed tracing (Jaeger via OTLP)
- Prometheus metrics endpoint (/metrics)
- LLM call tracking (latency, tokens, cost)
- Request metrics (count, latency p50/p95/p99, error rate)

Initialize once at startup via setup_observability().
"""

import logging
import os
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

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
                "version": "0.3.0",
                "environment": settings.app_env,
                "llm_provider": settings.llm_provider,
            }
        )
        logger.info("prometheus_metrics_initialized")

    if _tracer_available:
        otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        resource = Resource.create({"service.name": "normaai", "service.version": "0.3.0"})
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
