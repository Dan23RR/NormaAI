"""Tests for the OpenTelemetry + Prometheus observability stack (src.observability).

The optional ``opentelemetry-*`` and ``prometheus-client`` extras may or may not
be installed in the environment running the suite (absent in CI, often PRESENT
in dev venvs). The tests therefore never assume the ambient import state:

* **Degraded mode** is SIMULATED by the ``degraded`` fixture: it forces
  ``_metrics_available``/``_tracer_available`` to False and removes the
  module-level metric singletons; monkeypatch restores everything on teardown.
  Every public function must then be a safe no-op / sentinel response. We
  deliberately do NOT ``importlib.reload()`` the module to fake absence: with
  prometheus-client installed, a re-executed module would re-register its
  collectors against the global registry and raise "Duplicated timeseries".

* **Instrumented mode** -- we flip the module flags with ``patch.object`` and
  inject ``MagicMock`` stand-ins for the otel/prometheus/FastAPIInstrumentor
  names *where they are looked up* (the ``src.observability`` module globals,
  ``create=True`` because they may be absent). This exercises the happy paths
  and the graceful-degradation ``try/except`` branches inside
  ``setup_observability`` without touching the heavy libs.

No real exporters are created and the shared sqlite test.db is never opened.
"""
# ruff: noqa: SIM117 -- the context-manager-under-test is kept nested inside
# its patch/pytest.raises scaffolding deliberately, for readability.

import io
import json
import logging
import os
import re
import sys
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest
import structlog

import src.observability as obs

_METRIC_SINGLETONS = (
    "APP_INFO",
    "REQUEST_COUNT",
    "REQUEST_LATENCY",
    "LLM_CALL_COUNT",
    "LLM_CALL_LATENCY",
    "LLM_TOKENS",
    "CIRCUIT_STATE",
    "ACTIVE_REQUESTS",
)


@pytest.fixture
def degraded(monkeypatch):
    """Force src.observability into its degraded state, whatever is installed.

    Flags off + metric singletons removed = exactly the module state produced by
    an import with the optional extras missing. monkeypatch restores both the
    flags and any deleted attributes on teardown.
    """
    monkeypatch.setattr(obs, "_metrics_available", False)
    monkeypatch.setattr(obs, "_tracer_available", False)
    for name in _METRIC_SINGLETONS:
        if hasattr(obs, name):
            monkeypatch.delattr(obs, name)
    return obs


# --------------------------------------------------------------------------- #
# Degraded module state (simulated by the fixture)
# --------------------------------------------------------------------------- #
class TestModuleState:
    def test_degraded_fixture_flags_off(self, degraded):
        # The fixture reproduces the "extras not installed" import state
        # deterministically, on any machine.
        assert degraded._metrics_available is False
        assert degraded._tracer_available is False

    def test_metric_singletons_not_defined_when_unavailable(self, degraded):
        # In degraded state none of the Prometheus collectors exist as module
        # attributes (the `if _metrics_available:` block never ran).
        for name in _METRIC_SINGLETONS:
            assert not hasattr(degraded, name), f"{name} should be absent in degraded mode"

    def test_public_api_is_present(self):
        # Functions are defined unconditionally regardless of optional libs.
        assert callable(obs.setup_observability)
        assert callable(obs.get_metrics_response)
        assert callable(obs.track_llm_call)
        assert callable(obs.record_llm_tokens)


# --------------------------------------------------------------------------- #
# get_metrics_response()
# --------------------------------------------------------------------------- #
class TestGetMetricsResponse:
    def test_degraded_returns_sentinel_plaintext(self, degraded):
        body, content_type = degraded.get_metrics_response()
        assert body == "# Prometheus client not installed\n"
        assert content_type == "text/plain"

    def test_available_delegates_to_generate_latest(self):
        generate_latest = MagicMock(return_value=b"# HELP normaai_x\n")
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "generate_latest", generate_latest, create=True),
            patch.object(
                obs,
                "CONTENT_TYPE_LATEST",
                "text/plain; version=0.0.4; charset=utf-8",
                create=True,
            ),
        ):
            body, content_type = obs.get_metrics_response()

        # Real behavior: returns exactly what generate_latest produced plus the
        # prometheus content type constant -- not the sentinel.
        assert body == b"# HELP normaai_x\n"
        assert content_type == "text/plain; version=0.0.4; charset=utf-8"
        generate_latest.assert_called_once_with()


# --------------------------------------------------------------------------- #
# track_llm_call() context manager
# --------------------------------------------------------------------------- #
class TestTrackLLMCall:
    def test_degraded_is_safe_noop(self):
        # No metric objects exist; the context manager must still run cleanly.
        with obs.track_llm_call("gemini", "flash"):
            pass  # body executes without AttributeError

    def test_degraded_still_propagates_exception(self):
        with pytest.raises(ValueError, match="boom"):
            with obs.track_llm_call("gemini", "flash"):
                raise ValueError("boom")

    def test_available_success_records_count_and_latency(self):
        call_count = MagicMock()
        call_latency = MagicMock()
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "LLM_CALL_COUNT", call_count, create=True),
            patch.object(obs, "LLM_CALL_LATENCY", call_latency, create=True),
        ):
            with obs.track_llm_call("gemini", "flash-2.5"):
                pass

        # Counter labelled with status="success" and incremented exactly once.
        call_count.labels.assert_called_once_with(
            provider="gemini", model="flash-2.5", status="success"
        )
        call_count.labels.return_value.inc.assert_called_once_with()

        # Histogram observed with a non-negative elapsed time.
        call_latency.labels.assert_called_once_with(provider="gemini", model="flash-2.5")
        observe = call_latency.labels.return_value.observe
        observe.assert_called_once()
        (elapsed,) = observe.call_args.args
        assert isinstance(elapsed, float)
        assert elapsed >= 0.0

    def test_available_error_records_error_status_and_reraises(self):
        call_count = MagicMock()
        call_latency = MagicMock()
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "LLM_CALL_COUNT", call_count, create=True),
            patch.object(obs, "LLM_CALL_LATENCY", call_latency, create=True),
        ):
            with pytest.raises(RuntimeError, match="upstream 500"):
                with obs.track_llm_call("openai", "gpt-4o"):
                    raise RuntimeError("upstream 500")

        # status flips to "error" on the failure path...
        call_count.labels.assert_called_once_with(provider="openai", model="gpt-4o", status="error")
        call_count.labels.return_value.inc.assert_called_once_with()
        # ...and the finally-block still records latency even on error.
        call_latency.labels.assert_called_once_with(provider="openai", model="gpt-4o")
        call_latency.labels.return_value.observe.assert_called_once()

    def test_metric_flag_read_in_finally_not_at_entry(self):
        # The contextmanager checks `_metrics_available` only in its finally
        # block. If metrics are unavailable, neither object is consulted even
        # though we provide them, proving the guard genuinely gates the writes.
        call_count = MagicMock()
        call_latency = MagicMock()
        with (
            patch.object(obs, "_metrics_available", False),
            patch.object(obs, "LLM_CALL_COUNT", call_count, create=True),
            patch.object(obs, "LLM_CALL_LATENCY", call_latency, create=True),
        ):
            with obs.track_llm_call("gemini", "flash"):
                pass

        call_count.labels.assert_not_called()
        call_latency.labels.assert_not_called()


# --------------------------------------------------------------------------- #
# record_llm_tokens()
# --------------------------------------------------------------------------- #
class TestRecordLLMTokens:
    def test_degraded_is_noop(self):
        # No LLM_TOKENS collector defined; must not raise.
        assert obs.record_llm_tokens("gemini", 10, 20) is None

    def test_available_records_input_and_output_directions(self):
        tokens = MagicMock()
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "LLM_TOKENS", tokens, create=True),
        ):
            obs.record_llm_tokens("gemini", 100, 250)

        # Two distinct labelled series: input and output.
        assert tokens.labels.call_args_list == [
            ({"provider": "gemini", "direction": "input"},),
            ({"provider": "gemini", "direction": "output"},),
        ]
        # Each incremented by its respective token count (not by 1).
        assert tokens.labels.return_value.inc.call_args_list == [
            ((100,),),
            ((250,),),
        ]

    def test_available_zero_tokens_still_increments_both(self):
        tokens = MagicMock()
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "LLM_TOKENS", tokens, create=True),
        ):
            obs.record_llm_tokens("anthropic", 0, 0)

        assert tokens.labels.return_value.inc.call_args_list == [((0,),), ((0,),)]


# --------------------------------------------------------------------------- #
# setup_observability() -- metrics branch
# --------------------------------------------------------------------------- #
class TestSetupObservabilityMetrics:
    def test_both_flags_off_does_not_import_settings(self):
        # With both libs absent setup must do nothing and, crucially, never
        # reach `from src.config import get_settings`.
        with (
            patch.object(obs, "_metrics_available", False),
            patch.object(obs, "_tracer_available", False),
            patch("src.config.get_settings") as get_settings,
        ):
            obs.setup_observability()
        get_settings.assert_not_called()

    def test_metrics_branch_populates_app_info_from_settings(self):
        app_info = MagicMock()
        settings = MagicMock(app_env="testing", llm_provider="gemini")
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "_tracer_available", False),
            patch.object(obs, "APP_INFO", app_info, create=True),
            patch("src.config.get_settings", return_value=settings) as get_settings,
        ):
            obs.setup_observability()

        get_settings.assert_called_once_with()
        app_info.info.assert_called_once_with(
            {
                "version": "0.3.0",
                "environment": "testing",
                "llm_provider": "gemini",
            }
        )

    def test_metrics_branch_reads_live_settings_values(self):
        # The environment/provider in APP_INFO come straight from get_settings,
        # not from hard-coded strings.
        app_info = MagicMock()
        settings = MagicMock(app_env="production", llm_provider="anthropic")
        with (
            patch.object(obs, "_metrics_available", True),
            patch.object(obs, "_tracer_available", False),
            patch.object(obs, "APP_INFO", app_info, create=True),
            patch("src.config.get_settings", return_value=settings),
        ):
            obs.setup_observability()

        payload = app_info.info.call_args.args[0]
        assert payload["environment"] == "production"
        assert payload["llm_provider"] == "anthropic"


# --------------------------------------------------------------------------- #
# setup_observability() -- tracer branch
# --------------------------------------------------------------------------- #
def _enter_tracer(stack, **overrides):
    """Enable the tracer branch on the live module and inject otel mocks.

    Flips ``_tracer_available`` True / ``_metrics_available`` False and replaces
    each otel symbol looked up in ``src.observability`` with a MagicMock
    (``create=True`` because the symbols are absent in degraded mode). All
    patches are entered on the supplied ``ExitStack`` and torn down with it.
    Returns the dict of injected mocks keyed by symbol name.
    """
    names = {
        "trace": MagicMock(),
        "Resource": MagicMock(),
        "TracerProvider": MagicMock(),
        "OTLPSpanExporter": MagicMock(),
        "BatchSpanProcessor": MagicMock(),
        "FastAPIInstrumentor": MagicMock(),
    }
    names.update(overrides)
    stack.enter_context(patch.object(obs, "_metrics_available", False))
    stack.enter_context(patch.object(obs, "_tracer_available", True))
    for name, mock in names.items():
        stack.enter_context(patch.object(obs, name, mock, create=True))
    return names


class TestSetupObservabilityTracer:
    def test_happy_path_wires_provider_exporter_and_app(self):
        app = MagicMock()
        with ExitStack() as stack:
            names = _enter_tracer(stack)
            obs.setup_observability(app=app)

        # Resource describes the service.
        names["Resource"].create.assert_called_once_with(
            {"service.name": "normaai", "service.version": "0.3.0"}
        )
        # Provider built from that resource, exporter attached, provider set.
        names["TracerProvider"].assert_called_once_with(
            resource=names["Resource"].create.return_value
        )
        provider = names["TracerProvider"].return_value
        provider.add_span_processor.assert_called_once()
        names["trace"].set_tracer_provider.assert_called_once_with(provider)
        # App instrumentation happens because app was provided.
        names["FastAPIInstrumentor"].instrument_app.assert_called_once_with(app)

    def test_default_otlp_endpoint_when_env_unset(self):
        env_without = dict(os.environ)
        env_without.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, env_without, clear=True))
            names = _enter_tracer(stack)
            obs.setup_observability()

        names["OTLPSpanExporter"].assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )

    def test_custom_otlp_endpoint_from_env(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch.dict(
                    os.environ,
                    {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://collector:4317"},
                )
            )
            names = _enter_tracer(stack)
            obs.setup_observability()

        assert names["OTLPSpanExporter"].call_args.kwargs["endpoint"] == "http://collector:4317"
        assert names["OTLPSpanExporter"].call_args.kwargs["insecure"] is True

    def test_app_none_skips_fastapi_instrumentation(self):
        with ExitStack() as stack:
            names = _enter_tracer(stack)
            obs.setup_observability(app=None)

        names["FastAPIInstrumentor"].instrument_app.assert_not_called()

    def test_exporter_failure_is_swallowed_and_provider_not_set(self):
        # Graceful degradation: exporter ctor raising must NOT propagate, and
        # because the failure happens before set_tracer_provider, the provider
        # is never installed globally.
        exploding_exporter = MagicMock(side_effect=RuntimeError("no grpc transport"))
        with ExitStack() as stack:
            names = _enter_tracer(stack, OTLPSpanExporter=exploding_exporter)
            obs.setup_observability()  # must not raise

        names["trace"].set_tracer_provider.assert_not_called()

    def test_exporter_failure_still_attempts_app_instrumentation(self):
        # The exporter try/except and the FastAPI try/except are independent:
        # a failed exporter does not prevent app instrumentation.
        exploding_exporter = MagicMock(side_effect=RuntimeError("boom"))
        app = MagicMock()
        with ExitStack() as stack:
            names = _enter_tracer(stack, OTLPSpanExporter=exploding_exporter)
            obs.setup_observability(app=app)

        names["FastAPIInstrumentor"].instrument_app.assert_called_once_with(app)

    def test_fastapi_instrumentation_failure_is_swallowed(self):
        instrumentor = MagicMock()
        instrumentor.instrument_app.side_effect = RuntimeError("already instrumented")
        with ExitStack() as stack:
            _enter_tracer(stack, FastAPIInstrumentor=instrumentor)
            # Should complete cleanly despite instrumentation blowing up.
            obs.setup_observability(app=MagicMock())

        instrumentor.instrument_app.assert_called_once()


# --------------------------------------------------------------------------- #
# setup_observability() -- combined behavior
# --------------------------------------------------------------------------- #
class TestSetupObservabilityCombined:
    def test_metrics_and_tracer_both_run(self):
        app_info = MagicMock()
        settings = MagicMock(app_env="testing", llm_provider="gemini")
        with ExitStack() as stack:
            # _enter_tracer sets _metrics_available False; override it back to
            # True *after* so the metrics branch also executes.
            names = _enter_tracer(stack)
            stack.enter_context(patch.object(obs, "_metrics_available", True))
            stack.enter_context(patch.object(obs, "APP_INFO", app_info, create=True))
            stack.enter_context(patch("src.config.get_settings", return_value=settings))
            obs.setup_observability(app=MagicMock())

        # Metrics side effect happened...
        app_info.info.assert_called_once()
        # ...and tracer side effect happened.
        names["trace"].set_tracer_provider.assert_called_once()

    def test_returns_none(self):
        # Documented contract: setup_observability returns None.
        with (
            patch.object(obs, "_metrics_available", False),
            patch.object(obs, "_tracer_available", False),
        ):
            assert obs.setup_observability() is None


# --------------------------------------------------------------------------- #
# setup_logging() -- real logging configuration from settings
# --------------------------------------------------------------------------- #
_LOGGERS_TOUCHED = ("", "uvicorn", "uvicorn.error", "uvicorn.access", obs.AUDIT_LOGGER_NAME)


@pytest.fixture
def logging_sandbox():
    """Snapshot and restore every logger setup_logging touches.

    setup_logging mutates process-global logging state; this keeps the other
    test files (and pytest's own capture handlers) unaffected.
    """
    saved = {}
    for name in _LOGGERS_TOUCHED:
        lg = logging.getLogger(name)
        saved[name] = (list(lg.handlers), lg.level, lg.propagate)
    yield
    for name, (handlers, level, propagate) in saved.items():
        lg = logging.getLogger(name)
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate


def _settings(level="INFO", fmt="plain"):
    return MagicMock(log_level=level, log_format=fmt)


def _our_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, "_normaai_log_handler", False)]


class TestSetupLogging:
    def test_installs_one_root_handler_and_applies_level(self, logging_sandbox):
        obs.setup_logging(_settings("DEBUG"), stream=io.StringIO())
        assert len(_our_handlers()) == 1
        assert logging.getLogger().level == logging.DEBUG

    def test_is_idempotent(self, logging_sandbox):
        # import-time call + lifespan call (+ test re-imports) must not stack handlers.
        foreign = logging.NullHandler()
        logging.getLogger().addHandler(foreign)
        obs.setup_logging(_settings("INFO"), stream=io.StringIO())
        obs.setup_logging(_settings("WARNING"), stream=io.StringIO())
        assert len(_our_handlers()) == 1
        assert logging.getLogger().level == logging.WARNING
        # Handlers we did not install (pytest capture, callers) are kept.
        assert foreign in logging.getLogger().handlers

    def test_uvicorn_loggers_propagate_to_root_handler(self, logging_sandbox):
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            lg.addHandler(logging.NullHandler())  # what uvicorn's LOGGING_CONFIG does
            lg.propagate = False
        obs.setup_logging(_settings("INFO"), stream=io.StringIO())
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            lg = logging.getLogger(name)
            assert lg.handlers == []
            assert lg.propagate is True
            assert lg.level == logging.INFO

    def test_invalid_level_falls_back_to_info(self, logging_sandbox):
        obs.setup_logging(_settings("VERBOSE"), stream=io.StringIO())
        assert logging.getLogger().level == logging.INFO

    def test_plain_format_has_timestamp_level_logger_and_message(self, logging_sandbox):
        stream = io.StringIO()
        obs.setup_logging(_settings("INFO"), stream=stream)
        logging.getLogger("normaai.sample").info("cache_hit: %s", "qa", extra={"ttl": 900})
        line = [ln for ln in stream.getvalue().splitlines() if "cache_hit" in ln][0]
        assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line)  # ISO timestamp
        assert "info" in line.lower()
        assert "normaai.sample" in line
        assert "cache_hit: qa" in line  # %-args formatted
        assert "ttl=900" in line  # extra={} fields rendered, not dropped

    def test_json_format_emits_one_json_object_per_line(self, logging_sandbox):
        stream = io.StringIO()
        obs.setup_logging(_settings("INFO", "json"), stream=stream)
        logging.getLogger("normaai.sample").warning("slow_query", extra={"ms": 12})
        line = [ln for ln in stream.getvalue().splitlines() if "slow_query" in ln][0]
        payload = json.loads(line)
        assert payload["event"] == "slow_query"
        assert payload["level"] == "warning"
        assert payload["logger"] == "normaai.sample"
        assert payload["ms"] == 12
        assert "timestamp" in payload

    def test_structlog_events_render_through_the_same_formatter(self, logging_sandbox):
        stream = io.StringIO()
        obs.setup_logging(_settings("INFO", "json"), stream=stream)
        structlog.get_logger("normaai.structured").info("router_loaded", module="x")
        line = [ln for ln in stream.getvalue().splitlines() if "router_loaded" in ln][0]
        payload = json.loads(line)
        assert payload["module"] == "x"
        assert payload["logger"] == "normaai.structured"
        assert payload["level"] == "info"

    def test_info_logs_are_actually_emitted(self, logging_sandbox):
        # The original bug: no root handler -> INFO lines vanished entirely.
        stream = io.StringIO()
        obs.setup_logging(_settings("INFO"), stream=stream)
        logging.getLogger("src.cache").info("redis_cache_connected")
        assert "redis_cache_connected" in stream.getvalue()

    def test_debug_is_filtered_at_info(self, logging_sandbox):
        stream = io.StringIO()
        obs.setup_logging(_settings("INFO"), stream=stream)
        logging.getLogger("src.cache").debug("hidden")
        assert "hidden" not in stream.getvalue()


class TestAuditLogger:
    def test_audit_logger_is_pinned_at_info(self, logging_sandbox):
        obs.setup_logging(_settings("WARNING"), stream=io.StringIO())
        audit = logging.getLogger(obs.AUDIT_LOGGER_NAME)
        assert audit.level == logging.INFO
        assert audit.propagate is True

    def test_audit_events_are_emitted_even_when_root_level_is_warning(self, logging_sandbox):
        from src.audit import AuditAction, audit_log

        stream = io.StringIO()
        obs.setup_logging(_settings("WARNING", "json"), stream=stream)
        audit_log(AuditAction.QA_QUERY, user_id="u-1", org_id="o-1", resource="/api/v1/qa")
        lines = [ln for ln in stream.getvalue().splitlines() if "audit_event" in ln]
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["logger"] == "normaai.audit"
        assert payload["audit"] is True
        assert payload["action"] == "data.qa.query"
        assert payload["user_id"] == "u-1"
        assert payload["level"] == "info"


# --------------------------------------------------------------------------- #
# setup_sentry() -- optional, settings-driven
# --------------------------------------------------------------------------- #
class TestSetupSentry:
    def test_disabled_without_dsn(self):
        assert obs.setup_sentry(MagicMock(sentry_dsn=None)) is False
        assert obs.setup_sentry(MagicMock(sentry_dsn="")) is False
        assert obs.setup_sentry(MagicMock(sentry_dsn="   ")) is False

    def test_initialises_sdk_with_fastapi_integration(self):
        fake_sdk = MagicMock()
        fastapi_mod = MagicMock()
        starlette_mod = MagicMock()
        with patch.dict(
            sys.modules,
            {
                "sentry_sdk": fake_sdk,
                "sentry_sdk.integrations": MagicMock(),
                "sentry_sdk.integrations.fastapi": fastapi_mod,
                "sentry_sdk.integrations.starlette": starlette_mod,
            },
        ):
            ok = obs.setup_sentry(
                MagicMock(sentry_dsn="https://key@o1.ingest.sentry.io/1", app_env="production")
            )
        assert ok is True
        fake_sdk.init.assert_called_once()
        kwargs = fake_sdk.init.call_args.kwargs
        assert kwargs["dsn"] == "https://key@o1.ingest.sentry.io/1"
        assert kwargs["environment"] == "production"
        assert kwargs["send_default_pii"] is False
        assert kwargs["release"] == f"normaai@{obs.APP_VERSION}"
        assert fastapi_mod.FastApiIntegration.return_value in kwargs["integrations"]
        assert starlette_mod.StarletteIntegration.return_value in kwargs["integrations"]

    def test_missing_sdk_is_graceful(self):
        # The SDK is an optional extra: without it, startup must not fail.
        with patch.dict(sys.modules, {"sentry_sdk": None}):
            assert (
                obs.setup_sentry(MagicMock(sentry_dsn="https://key@o1.ingest.sentry.io/1")) is False
            )
