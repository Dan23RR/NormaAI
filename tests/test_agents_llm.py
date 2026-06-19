"""Tests for src.agents.llm: provider routing, error classification, JSON
parsing/repair, error-response construction, and the sync/async call paths
(circuit breaker + semaphore + tenacity retry) with the provider SDKs mocked.

No real LLM/network calls: get_llm() and the LangChain client are always patched.
Settings are injected via a lightweight stub so we can exercise every provider
branch without touching the real (lru_cached) Settings or any .env.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.llm import (
    NonRetryableLLMError,
    RetryableLLMError,
    _classify_error,
    _make_error_response,
    acall_llm,
    call_llm,
    extract_confidence,
    format_retrieved_chunks,
    get_llm,
    parse_json_response,
)
from src.resilience import llm_circuit

# ─── Helpers / Fixtures ──────────────────────────────────────────


def _make_settings(provider="gemini", api_key="test-key", **overrides):
    """Build a stub Settings object exposing only what llm.py reads."""
    s = SimpleNamespace(
        llm_provider=provider,
        llm_temperature=0.3,
        llm_max_tokens=2048,
        llm_timeout_seconds=30,
        gemini_model_analysis="gemini-2.5-flash",
        anthropic_model_analysis="claude-sonnet-4-5",
        openrouter_model_analysis="some/free-model:free",
        openrouter_base_url="https://openrouter.ai/api/v1",
        normaai_public_url="https://normaai.org",
        google_api_key="" if provider != "gemini" else api_key,
        anthropic_api_key="" if provider != "anthropic" else api_key,
        openrouter_api_key="" if provider != "openrouter" else api_key,
    )
    # active_api_key is a real @property on Settings; emulate it here.
    s.active_api_key = api_key
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


@pytest.fixture(autouse=True)
def _reset_circuit():
    """Keep the shared llm_circuit singleton clean between tests."""
    llm_circuit.reset()
    yield
    llm_circuit.reset()


def _patch_settings(settings):
    """Patch the get_settings symbol that llm.py imports locally."""
    return patch("src.config.get_settings", return_value=settings)


# ─── TestClassifyError ───────────────────────────────────────────


class TestClassifyError:
    @pytest.mark.parametrize(
        "msg",
        [
            "Rate limit exceeded",
            "quota exhausted",
            "HTTP 429 Too Many Requests",
            "Model overloaded, try again",
            "503 Service Unavailable",
            "Read timeout after 30s",
            "Connection reset by peer",
        ],
    )
    def test_retryable_keywords(self, msg):
        result = _classify_error(Exception(msg))
        assert isinstance(result, RetryableLLMError)
        assert str(result) == msg

    @pytest.mark.parametrize(
        "msg",
        [
            "Authentication failed",
            "Invalid api_key provided",
            "permission denied",
            "403 Forbidden",
        ],
    )
    def test_non_retryable_keywords(self, msg):
        result = _classify_error(Exception(msg))
        assert isinstance(result, NonRetryableLLMError)

    def test_unknown_defaults_to_retryable(self):
        # Default assumption is "transient", so unknown errors are retryable.
        result = _classify_error(Exception("something weird happened"))
        assert isinstance(result, RetryableLLMError)

    def test_retryable_checked_before_non_retryable(self):
        # A message containing BOTH a retryable and non-retryable keyword:
        # retryable is evaluated first, so it wins.
        result = _classify_error(Exception("auth rate limit"))
        assert isinstance(result, RetryableLLMError)


# ─── TestGetLLM (provider selection) ─────────────────────────────


class TestGetLLM:
    def test_gemini_provider_selected(self):
        settings = _make_settings(provider="gemini", api_key="g-key")
        fake_cls = MagicMock(return_value="GEMINI_LLM")
        with (
            _patch_settings(settings),
            patch.dict(
                "sys.modules",
                {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=fake_cls)},
            ),
        ):
            result = get_llm()
        assert result == "GEMINI_LLM"
        _, kwargs = fake_cls.call_args
        assert kwargs["model"] == "gemini-2.5-flash"
        assert kwargs["temperature"] == 0.3
        assert kwargs["google_api_key"] == "g-key"
        assert kwargs["max_output_tokens"] == 2048

    def test_openrouter_provider_selected(self):
        settings = _make_settings(provider="openrouter", api_key="or-key")
        fake_cls = MagicMock(return_value="OR_LLM")
        with (
            _patch_settings(settings),
            patch.dict("sys.modules", {"langchain_openai": MagicMock(ChatOpenAI=fake_cls)}),
        ):
            result = get_llm()
        assert result == "OR_LLM"
        _, kwargs = fake_cls.call_args
        assert kwargs["model"] == "some/free-model:free"
        assert kwargs["api_key"] == "or-key"
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
        # OpenRouter attribution headers
        assert kwargs["default_headers"]["X-Title"] == "NormaAI"
        assert kwargs["default_headers"]["HTTP-Referer"] == "https://normaai.org"

    def test_anthropic_is_the_fallback_branch(self):
        # Any provider that is not gemini/openrouter falls through to Anthropic.
        settings = _make_settings(provider="anthropic", api_key="a-key")
        fake_cls = MagicMock(return_value="ANTHROPIC_LLM")
        with (
            _patch_settings(settings),
            patch.dict("sys.modules", {"langchain_anthropic": MagicMock(ChatAnthropic=fake_cls)}),
        ):
            result = get_llm()
        assert result == "ANTHROPIC_LLM"
        _, kwargs = fake_cls.call_args
        assert kwargs["model"] == "claude-sonnet-4-5"
        assert kwargs["anthropic_api_key"] == "a-key"
        assert kwargs["max_tokens"] == 2048

    def test_temperature_override_takes_precedence(self):
        settings = _make_settings(provider="gemini")
        fake_cls = MagicMock(return_value="LLM")
        with (
            _patch_settings(settings),
            patch.dict(
                "sys.modules",
                {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=fake_cls)},
            ),
        ):
            get_llm(temperature=0.95)
        _, kwargs = fake_cls.call_args
        assert kwargs["temperature"] == 0.95

    def test_temperature_zero_override_not_ignored(self):
        # 0.0 is falsy but a legitimate override; the code uses `is None`,
        # so an explicit 0.0 must reach the client (not the configured 0.3).
        settings = _make_settings(provider="gemini")
        fake_cls = MagicMock(return_value="LLM")
        with (
            _patch_settings(settings),
            patch.dict(
                "sys.modules",
                {"langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=fake_cls)},
            ),
        ):
            get_llm(temperature=0.0)
        _, kwargs = fake_cls.call_args
        assert kwargs["temperature"] == 0.0


# ─── TestMakeErrorResponse ───────────────────────────────────────


class TestMakeErrorResponse:
    def _resp(self, msg, provider="gemini"):
        with _patch_settings(_make_settings(provider=provider)):
            return _make_error_response(msg)

    def test_shape_is_consistent(self):
        r = self._resp("anything")
        assert r["confidence_score"] == 0.0
        assert r["requires_expert_review"] is True
        assert "error" in r

    def test_auth_error_mentions_api_key(self):
        r = self._resp("Authentication failed: invalid api_key")
        assert "Invalid API key" in r["error"]
        assert "gemini" in r["error"]

    def test_timeout_error(self):
        r = self._resp("Request timeout exceeded")
        assert "timed out" in r["error"]

    def test_rate_limit_error(self):
        r = self._resp("429 rate limit hit")
        assert "Rate limited" in r["error"]

    def test_overloaded_error(self):
        r = self._resp("Model overloaded")
        assert "overloaded" in r["error"]

    def test_circuit_error(self):
        r = self._resp("circuit is open")
        assert "temporarily unavailable" in r["error"]

    def test_generic_error_includes_provider_and_message(self):
        r = self._resp("kaboom", provider="anthropic")
        assert "anthropic" in r["error"]
        assert "kaboom" in r["error"]


# ─── TestParseJsonResponse ───────────────────────────────────────


class TestParseJsonResponse:
    def test_direct_json(self):
        result = parse_json_response('{"answer": "hi", "confidence_score": 0.8}')
        assert result["answer"] == "hi"
        assert result["confidence_score"] == 0.8

    def test_json_with_surrounding_whitespace(self):
        result = parse_json_response('  \n {"a": 1}\n  ')
        assert result["a"] == 1

    def test_json_in_fenced_code_block(self):
        content = '```json\n{"answer": "fenced"}\n```'
        assert parse_json_response(content)["answer"] == "fenced"

    def test_json_in_plain_code_block(self):
        content = '```\n{"answer": "plain"}\n```'
        assert parse_json_response(content)["answer"] == "plain"

    def test_json_with_leading_prose_via_brace_scan(self):
        content = 'Here is your result:\n{"answer": "scanned", "x": 2}\nThanks!'
        result = parse_json_response(content)
        assert result["answer"] == "scanned"
        assert result["x"] == 2

    def test_invalid_json_falls_back_to_raw_text(self):
        content = "This is not JSON at all."
        result = parse_json_response(content)
        assert result["answer"] == content
        assert result["citations"] == []
        assert result["confidence_score"] == 0.5
        assert result["requires_expert_review"] is True
        assert "parse_warning" in result

    def test_empty_string_falls_back(self):
        result = parse_json_response("")
        assert "answer" in result
        assert result["parse_warning"]

    def test_non_string_input_is_stringified(self):
        # A dict is not a str; it gets str()'d, which is not valid JSON,
        # so it lands in the fallback with the repr as the answer.
        result = parse_json_response({"already": "dict"})
        assert "already" in result["answer"]
        assert "parse_warning" in result

    def test_nested_braces_use_outermost_boundaries(self):
        content = 'prefix {"outer": {"inner": 5}} suffix'
        result = parse_json_response(content)
        assert result["outer"] == {"inner": 5}

    def test_code_block_preferred_over_brace_scan(self):
        # The fenced block holds the canonical JSON; brace-scan would grab
        # a larger, broken span. Code-block extraction runs first.
        content = 'noise {bad\n```json\n{"answer": "from_block"}\n```\nmore }noise'
        result = parse_json_response(content)
        assert result["answer"] == "from_block"


# ─── TestExtractConfidence ───────────────────────────────────────


class TestExtractConfidence:
    def test_valid_float(self):
        assert extract_confidence({"confidence_score": 0.73}) == 0.73

    def test_string_numeric_coerced(self):
        assert extract_confidence({"confidence_score": "0.42"}) == 0.42

    def test_clamped_above_one(self):
        assert extract_confidence({"confidence_score": 5.0}) == 1.0

    def test_clamped_below_zero(self):
        assert extract_confidence({"confidence_score": -3.0}) == 0.0

    def test_missing_key_returns_zero(self):
        assert extract_confidence({}) == 0.0

    def test_non_dict_returns_zero(self):
        assert extract_confidence("nope") == 0.0
        assert extract_confidence(None) == 0.0
        assert extract_confidence([0.9]) == 0.0

    def test_unparseable_string_returns_zero(self):
        assert extract_confidence({"confidence_score": "high"}) == 0.0

    def test_none_value_returns_zero(self):
        # float(None) raises TypeError → caught → 0.0
        assert extract_confidence({"confidence_score": None}) == 0.0


# ─── TestFormatRetrievedChunks ───────────────────────────────────


class TestFormatRetrievedChunks:
    def test_empty_list(self):
        assert format_retrieved_chunks([]) == "No relevant regulatory text found."

    def test_none_is_treated_as_empty(self):
        assert format_retrieved_chunks(None) == "No relevant regulatory text found."

    def test_dict_chunk_renders_citation(self):
        chunks = [{"framework": "CSRD", "article_number": "Art. 19a", "text": "body"}]
        out = format_retrieved_chunks(chunks)
        assert "[CSRD, Art. 19a]" in out
        assert "Source 1" in out
        assert "body" in out

    def test_dict_chunk_missing_fields_uses_placeholders(self):
        out = format_retrieved_chunks([{"text": "only text"}])
        assert "[?, ?]" in out
        assert "only text" in out

    def test_string_chunk(self):
        out = format_retrieved_chunks(["raw paragraph"])
        assert "Source 1" in out
        assert "raw paragraph" in out

    def test_multiple_chunks_numbered_sequentially(self):
        out = format_retrieved_chunks(
            [
                {"framework": "GDPR", "article_number": "Art. 5", "text": "a"},
                "plain second",
            ]
        )
        assert "Source 1" in out
        assert "Source 2" in out
        assert "GDPR" in out
        assert "plain second" in out


# ─── TestCallLLM (sync path) ─────────────────────────────────────


class TestCallLLM:
    def test_missing_api_key_short_circuits(self):
        settings = _make_settings(provider="gemini", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings):
            result = call_llm("sys", "user")
        assert "GOOGLE_API_KEY not configured" in result["error"]
        assert result["confidence_score"] == 0.0
        assert result["requires_expert_review"] is True

    def test_missing_api_key_message_per_provider(self):
        settings = _make_settings(provider="openrouter", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings):
            result = call_llm("sys", "user")
        assert "OPENROUTER_API_KEY" in result["error"]

    def test_open_circuit_returns_graceful_error(self):
        # An OPEN circuit degrades to the standardized error dict (it previously
        # raised ServiceUnavailableError uncaught into the agent graph -- fixed).
        for _ in range(5):
            llm_circuit.record_failure()
        settings = _make_settings(provider="gemini", api_key="k")
        with _patch_settings(settings):
            result = call_llm("sys", "user")
        assert result["confidence_score"] == 0.0
        assert result["requires_expert_review"] is True
        assert "unavailable" in result["error"].lower()

    def test_successful_call_parses_response_and_records_success(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.invoke.return_value = MagicMock(
            content='{"answer": "ok", "confidence_score": 0.9}'
        )
        with _patch_settings(settings), patch("src.agents.llm.get_llm", return_value=fake_llm):
            result = call_llm("system prompt", "user message")
        assert result["answer"] == "ok"
        assert result["confidence_score"] == 0.9
        # The two messages (system + human) were passed to invoke.
        sent = fake_llm.invoke.call_args[0][0]
        assert len(sent) == 2
        # Circuit recorded a success (failure count cleared, success counted).
        assert llm_circuit.is_available is True

    def test_provider_exception_returns_error_response(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("invalid api_key")
        with _patch_settings(settings), patch("src.agents.llm.get_llm", return_value=fake_llm):
            result = call_llm("sys", "user")
        assert "Invalid API key" in result["error"]
        assert result["confidence_score"] == 0.0

    def test_failure_increments_circuit(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("boom")
        with _patch_settings(settings), patch("src.agents.llm.get_llm", return_value=fake_llm):
            call_llm("sys", "user")
        # One failure recorded; below threshold of 5 → still available.
        assert llm_circuit._failure_count == 1


# ─── TestAcallLLM (async path) ───────────────────────────────────


class TestAcallLLM:
    async def test_missing_api_key_short_circuits(self):
        settings = _make_settings(provider="anthropic", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings):
            result = await acall_llm("sys", "user")
        assert "ANTHROPIC_API_KEY not configured" in result["error"]

    async def test_open_circuit_returns_graceful_error(self):
        # Same as the sync path: an OPEN circuit degrades to the error dict
        # instead of propagating ServiceUnavailableError into the agent graph.
        for _ in range(5):
            llm_circuit.record_failure()
        settings = _make_settings(provider="gemini", api_key="k")
        with _patch_settings(settings):
            result = await acall_llm("sys", "user")
        assert result["confidence_score"] == 0.0
        assert result["requires_expert_review"] is True
        assert "unavailable" in result["error"].lower()

    async def test_successful_async_call(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(
            return_value=MagicMock(content='{"answer": "async ok", "confidence_score": 0.7}')
        )
        with _patch_settings(settings), patch("src.agents.llm.get_llm", return_value=fake_llm):
            result = await acall_llm("sys", "user", temperature=0.5)
        assert result["answer"] == "async ok"
        assert llm_circuit.is_available is True

    async def test_non_retryable_error_not_retried(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("invalid api_key"))
        with _patch_settings(settings), patch("src.agents.llm.get_llm", return_value=fake_llm):
            result = await acall_llm("sys", "user")
        # NonRetryable → single attempt, error response returned.
        assert fake_llm.ainvoke.await_count == 1
        assert "Invalid API key" in result["error"]
        assert llm_circuit._failure_count == 1

    async def test_retryable_error_exhausts_attempts(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(side_effect=RuntimeError("rate limit 429"))
        # Patch tenacity's sleep so the exponential backoff is instant.
        with (
            _patch_settings(settings),
            patch("src.agents.llm.get_llm", return_value=fake_llm),
            patch("tenacity.nap.time.sleep", return_value=None),
        ):
            result = await acall_llm("sys", "user")
        # stop_after_attempt(3) → exactly 3 invocations before giving up.
        assert fake_llm.ainvoke.await_count == 3
        assert "Rate limited" in result["error"]

    async def test_retryable_then_success_recovers(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(
            side_effect=[
                RuntimeError("overloaded 503"),
                MagicMock(content='{"answer": "recovered", "confidence_score": 0.6}'),
            ]
        )
        with (
            _patch_settings(settings),
            patch("src.agents.llm.get_llm", return_value=fake_llm),
            patch("tenacity.nap.time.sleep", return_value=None),
        ):
            result = await acall_llm("sys", "user")
        assert result["answer"] == "recovered"
        assert fake_llm.ainvoke.await_count == 2
        # A successful run clears the failure count.
        assert llm_circuit._failure_count == 0

    async def test_temperature_propagates_to_get_llm(self):
        settings = _make_settings(provider="gemini", api_key="k")
        fake_llm = MagicMock()
        fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps({"answer": "x"})))
        captured = {}

        def _capture(temperature=None):
            captured["temperature"] = temperature
            return fake_llm

        with _patch_settings(settings), patch("src.agents.llm.get_llm", side_effect=_capture):
            await acall_llm("sys", "user", temperature=0.88)
        assert captured["temperature"] == 0.88
