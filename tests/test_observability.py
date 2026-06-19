"""Tests for the OpenTelemetry + Prometheus observability stack (src.observability).

The optional ``opentelemetry-*`` and ``prometheus-client`` extras are NOT
installed in the test environment, so at import time the module sets
``_metrics_available = False`` and ``_tracer_available = False`` and never
defines the module-level metric singletons (REQUEST_COUNT, LLM_TOKENS, ...).

Two test surfaces follow from that:

* **Degraded mode** (real module state) -- every public function must be a
  safe no-op / sentinel response and never touch a metric object or import
  ``src.config``. No real exporters, registries, or network are involved.

* **Instrumented mode** -- we flip the module flags with ``patch.object`` and
  inject ``MagicMock`` stand-ins for the otel/prometheus/FastAPIInstrumentor
  names *where they are looked up* (the ``src.observability`` module globals,
  ``create=True`` because they are absent in degraded mode). This exercises the
  happy paths and the graceful-degradation ``try/except`` branches inside
  ``setup_observability`` without importing the heavy libs.

No real exporters are created and the shared sqlite test.db is never opened.
"""
# ruff: noqa: SIM117 -- the context-manager-under-test is kept nested inside
# its patch/pytest.raises scaffolding deliberately, for readability.

import os
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

import src.observability as obs


# --------------------------------------------------------------------------- #
# Import-time module state
# --------------------------------------------------------------------------- #
class TestModuleState:
    def test_optional_libs_absent_in_test_env(self):
        # The whole test design hinges on the extras being uninstalled here.
        # If this ever flips, the degraded-mode tests below need revisiting.
        assert obs._metrics_available is False
        assert obs._tracer_available is False

    def test_metric_singletons_not_defined_when_unavailable(self):
        # The `if _metrics_available:` block at module scope never ran, so none
        # of the Prometheus collectors exist as module attributes.
        for name in (
            "APP_INFO",
            "REQUEST_COUNT",
            "REQUEST_LATENCY",
            "LLM_CALL_COUNT",
            "LLM_CALL_LATENCY",
            "LLM_TOKENS",
            "CIRCUIT_STATE",
            "ACTIVE_REQUESTS",
        ):
            assert not hasattr(obs, name), f"{name} should be absent in degraded mode"

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
    def test_degraded_returns_sentinel_plaintext(self):
        body, content_type = obs.get_metrics_response()
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
