"""Tests for the local LLM (Ollama) client: src/agents/local_llm.py.

Covers the local Qwen micro-agent HTTP client used for fast routing/NER:
- get_local_llm: ChatOllama factory wiring from settings
- _ainvoke_local_with_retry: happy path, error classification, retry-on-transient
- acall_local_llm: disabled gate, circuit-open gate, success parsing,
  graceful None on timeout / connection / unexpected errors, circuit bookkeeping
- _record_metric: no-op when metrics unavailable, increments when available,
  swallows internal exceptions

All external deps are mocked. No real network, no Ollama, no DB.

Complements (does NOT duplicate) tests/test_local_router.py, which exercises
src/agents/router.py (RouterResult, keyword fallback, validate/sanitize, routing).
This file targets the lower-level Ollama client those routes depend on.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import local_llm
from src.agents.llm import NonRetryableLLMError, RetryableLLMError


def _settings(**overrides):
    """Build a minimal settings stub for the local LLM client."""
    base = {
        "local_llm_enabled": True,
        "local_llm_base_url": "http://localhost:11434",
        "local_llm_model": "qwen3.5:4b",
        "local_llm_temperature": 0.0,
        "local_llm_max_tokens": 512,
        "local_llm_timeout_seconds": 10,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


# ─── TestGetLocalLLM ──────────────────────────────────────────────


class TestGetLocalLLM:
    def test_constructs_chatollama_from_settings(self):
        """get_local_llm wires every ChatOllama kwarg from settings."""
        fake_instance = object()
        chat_ollama = MagicMock(return_value=fake_instance)
        settings = _settings(
            local_llm_base_url="http://ollama:9999",
            local_llm_model="qwen-test",
            local_llm_temperature=0.3,
            local_llm_max_tokens=256,
            local_llm_timeout_seconds=7,
        )

        with (
            patch.dict(
                "sys.modules",
                {"langchain_ollama": MagicMock(ChatOllama=chat_ollama)},
            ),
            patch("src.config.get_settings", return_value=settings),
        ):
            result = local_llm.get_local_llm()

        assert result is fake_instance
        chat_ollama.assert_called_once_with(
            base_url="http://ollama:9999",
            model="qwen-test",
            temperature=0.3,
            num_predict=256,
            timeout=7,
        )


# ─── TestAinvokeLocalWithRetry ────────────────────────────────────


class TestAinvokeLocalWithRetry:
    @pytest.mark.asyncio
    async def test_happy_path_returns_content(self):
        """Returns the .content of the ChatOllama response message."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content='{"frameworks": ["CSRD"]}'))

        with patch("src.agents.local_llm.get_local_llm", return_value=mock_llm):
            content = await local_llm._ainvoke_local_with_retry("sys", "user")

        assert content == '{"frameworks": ["CSRD"]}'
        # Both system + user messages forwarded as a single list.
        sent = mock_llm.ainvoke.await_args.args[0]
        assert [m.content for m in sent] == ["sys", "user"]

    @pytest.mark.asyncio
    async def test_connection_error_classified_retryable_and_reraised(self):
        """A connection error becomes RetryableLLMError after retries exhaust."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("Connection refused"))

        with (
            patch("src.agents.local_llm.get_local_llm", return_value=mock_llm),
            pytest.raises(RetryableLLMError),
        ):
            await local_llm._ainvoke_local_with_retry("sys", "user")

        # stop_after_attempt(2): exactly two invocations, then reraise.
        assert mock_llm.ainvoke.await_count == 2

    @pytest.mark.asyncio
    async def test_auth_error_classified_non_retryable_no_retry(self):
        """A NonRetryableLLMError is NOT retried (only RetryableLLMError is)."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("invalid api_key"))

        with (
            patch("src.agents.local_llm.get_local_llm", return_value=mock_llm),
            pytest.raises(NonRetryableLLMError),
        ):
            await local_llm._ainvoke_local_with_retry("sys", "user")

        # No retry: 'invalid'/'api_key' classify as non-retryable -> single call.
        assert mock_llm.ainvoke.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_then_success(self):
        """First transient failure retries; second attempt succeeds."""
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[Exception("timeout occurred"), MagicMock(content="ok")]
        )

        with patch("src.agents.local_llm.get_local_llm", return_value=mock_llm):
            content = await local_llm._ainvoke_local_with_retry("sys", "user")

        assert content == "ok"
        assert mock_llm.ainvoke.await_count == 2


# ─── TestAcallLocalLLM ────────────────────────────────────────────


class TestAcallLocalLLM:
    @pytest.mark.asyncio
    async def test_returns_none_when_disabled(self):
        """When local_llm_enabled is False, returns None without any LLM call."""
        invoke = AsyncMock()
        with (
            patch("src.config.get_settings", return_value=_settings(local_llm_enabled=False)),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result is None
        invoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_returns_none_when_circuit_open(self):
        """An open circuit short-circuits to None and records a fallback metric."""
        invoke = AsyncMock()
        circuit = MagicMock(is_available=False)
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric") as record,
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result is None
        invoke.assert_not_awaited()
        record.assert_called_once_with("fallback")

    @pytest.mark.asyncio
    async def test_success_parses_json_and_records_success(self):
        """Happy path: parsed dict returned, circuit success recorded, metric logged."""
        circuit = MagicMock(is_available=True)
        invoke = AsyncMock(return_value='{"frameworks": ["DORA"], "complexity": "simple"}')
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric") as record,
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result == {"frameworks": ["DORA"], "complexity": "simple"}
        circuit.record_success.assert_called_once()
        circuit.record_failure.assert_not_called()
        # status="success" with an elapsed duration argument.
        assert record.call_args.args[0] == "success"
        assert record.call_args.args[1] >= 0.0

    @pytest.mark.asyncio
    async def test_error_returns_none_and_records_failure(self):
        """On invoke failure: returns None, records circuit failure + error metric."""
        circuit = MagicMock(is_available=True)
        invoke = AsyncMock(side_effect=RetryableLLMError("connection lost"))
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric") as record,
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result is None
        circuit.record_failure.assert_called_once()
        circuit.record_success.assert_not_called()
        assert record.call_args.args[0] == "error"

    @pytest.mark.asyncio
    async def test_timeout_handled_gracefully(self):
        """A timeout from the underlying client degrades to None (never raises)."""
        circuit = MagicMock(is_available=True)
        invoke = AsyncMock(side_effect=TimeoutError("read timed out"))
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric"),
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result is None
        circuit.record_failure.assert_called_once()

    @pytest.mark.asyncio
    async def test_malformed_json_falls_back_to_raw_text_dict(self):
        """Non-JSON content is rescued by parse_json_response, not an exception."""
        circuit = MagicMock(is_available=True)
        invoke = AsyncMock(return_value="not json at all")
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric"),
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        # parse_json_response fallback wraps raw text and flags review.
        assert result["answer"] == "not json at all"
        assert result["requires_expert_review"] is True
        circuit.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_embedded_json_in_markdown_parsed(self):
        """Content wrapped in a markdown code fence is still parsed to a dict."""
        circuit = MagicMock(is_available=True)
        fenced = '```json\n{"frameworks": ["NIS2"], "complexity": "medium"}\n```'
        invoke = AsyncMock(return_value=fenced)
        with (
            patch("src.config.get_settings", return_value=_settings()),
            patch("src.agents.local_llm.local_llm_circuit", circuit),
            patch("src.agents.local_llm._ainvoke_local_with_retry", invoke),
            patch("src.agents.local_llm._record_metric"),
        ):
            result = await local_llm.acall_local_llm("sys", "user")

        assert result == {"frameworks": ["NIS2"], "complexity": "medium"}


# ─── TestRecordMetric ─────────────────────────────────────────────


class TestRecordMetric:
    def test_noop_when_metrics_unavailable(self):
        """When observability metrics are off, _record_metric does nothing."""
        fake_obs = MagicMock()
        fake_obs._metrics_available = False
        with patch.dict("sys.modules", {"src.observability": fake_obs}):
            # Should not raise even though the Counter/Histogram attrs are absent.
            local_llm._record_metric("success", 0.01)

    def test_increments_counter_and_observes_latency(self):
        """When metrics are available, counter increments and latency observed."""
        count = MagicMock()
        latency = MagicMock()
        fake_obs = MagicMock(
            _metrics_available=True,
            LOCAL_LLM_CALL_COUNT=count,
            LOCAL_LLM_CALL_LATENCY=latency,
        )
        with patch.dict("sys.modules", {"src.observability": fake_obs}):
            local_llm._record_metric("success", 0.25)

        count.labels.assert_called_once_with(status="success")
        count.labels.return_value.inc.assert_called_once()
        latency.observe.assert_called_once_with(0.25)

    def test_latency_skipped_when_duration_none(self):
        """No duration => counter still increments but latency NOT observed."""
        count = MagicMock()
        latency = MagicMock()
        fake_obs = MagicMock(
            _metrics_available=True,
            LOCAL_LLM_CALL_COUNT=count,
            LOCAL_LLM_CALL_LATENCY=latency,
        )
        with patch.dict("sys.modules", {"src.observability": fake_obs}):
            local_llm._record_metric("fallback")

        count.labels.assert_called_once_with(status="fallback")
        latency.observe.assert_not_called()

    def test_swallows_internal_exception(self):
        """A failure inside metric recording must never propagate to the caller."""
        boom = MagicMock(_metrics_available=True)
        boom.LOCAL_LLM_CALL_COUNT.labels.side_effect = RuntimeError("prometheus down")
        with patch.dict("sys.modules", {"src.observability": boom}):
            # Must not raise.
            local_llm._record_metric("error", 0.5)
