"""Tests for src.agents.streaming_llm: async token-streaming wrapper.

Covers the public ``astream_llm`` / ``astream_llm_json`` generators plus the
three provider-specific internal streamers (Gemini / Anthropic / OpenRouter).

No real LLM/network: every provider SDK and the provider-client factories are
patched. Settings are injected via a lightweight stub so each provider branch
is exercised without touching the real (lru_cached) Settings or any .env. The
asyncio.Semaphore concurrency permit and the tenacity sleep are stubbed so the
tests run instantly and never block.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.agents.streaming_llm as streaming_llm
from src.agents.streaming_llm import (
    _astream_anthropic_with_retry,
    _astream_gemini_with_retry,
    _astream_openrouter_with_retry,
    _get_anthropic_client,
    _get_gemini_client,
    _get_openrouter_client,
    astream_llm,
    astream_llm_json,
)
from src.resilience import ServiceUnavailableError, llm_circuit

# ─── Helpers / Fixtures ──────────────────────────────────────────


def _make_settings(provider="gemini", api_key="test-key", **overrides):
    """Build a stub Settings object exposing only what streaming_llm.py reads."""
    s = SimpleNamespace(
        llm_provider=provider,
        llm_temperature=0.3,
        llm_max_tokens=2048,
        llm_timeout_seconds=30,
        max_concurrent_requests=4,
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
    """Patch the get_settings symbol that streaming_llm.py imports.

    streaming_llm imports ``from src.config import get_settings`` at module
    level, so the bound name to patch is on the module itself.
    """
    return patch.object(streaming_llm, "get_settings", return_value=settings)


class _NullSemaphore:
    """A no-op async context manager standing in for the LLM semaphore.

    Avoids creating a real asyncio.Semaphore (which depends on the running
    loop) and lets us assert that astream_llm acquires/releases a permit.
    """

    def __init__(self):
        self.entered = 0
        self.exited = 0

    async def __aenter__(self):
        self.entered += 1
        return self

    async def __aexit__(self, *exc):
        self.exited += 1
        return False


def _patch_semaphore(sem=None):
    """Patch src.resilience.get_llm_semaphore (imported lazily inside astream_llm)."""
    sem = sem or _NullSemaphore()
    return patch("src.resilience.get_llm_semaphore", return_value=sem), sem


async def _aiter(items):
    """Turn a list into an async iterator (one element per yield)."""
    for item in items:
        yield item


async def _collect(agen):
    """Drain an async generator into a list."""
    return [tok async for tok in agen]


def _gemini_chunk(text):
    """A Gemini stream chunk exposes a ``.text`` attribute."""
    return SimpleNamespace(text=text)


def _openrouter_chunk(content):
    """An OpenRouter (OpenAI-compatible) chunk: chunk.choices[0].delta.content."""
    delta = SimpleNamespace(content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


# ─── TestProviderClientFactories ─────────────────────────────────


class TestProviderClientFactories:
    def test_gemini_client_configured_with_api_key(self):
        settings = _make_settings(provider="gemini", api_key="g-key")
        fake_genai = MagicMock()
        with (
            _patch_settings(settings),
            patch.dict("sys.modules", {"google.generativeai": fake_genai}),
        ):
            result = _get_gemini_client()
        assert result is fake_genai
        fake_genai.configure.assert_called_once_with(api_key="g-key")

    def test_anthropic_client_built_with_api_key(self):
        settings = _make_settings(provider="anthropic", api_key="a-key")
        fake_cls = MagicMock(return_value="ANTHROPIC_CLIENT")
        fake_module = MagicMock(AsyncAnthropic=fake_cls)
        with (
            _patch_settings(settings),
            patch.dict("sys.modules", {"anthropic": fake_module}),
        ):
            result = _get_anthropic_client()
        assert result == "ANTHROPIC_CLIENT"
        fake_cls.assert_called_once_with(api_key="a-key")

    def test_openrouter_client_built_with_base_url_and_headers(self):
        settings = _make_settings(provider="openrouter", api_key="or-key")
        fake_cls = MagicMock(return_value="OR_CLIENT")
        fake_module = MagicMock(AsyncOpenAI=fake_cls)
        with (
            _patch_settings(settings),
            patch.dict("sys.modules", {"openai": fake_module}),
        ):
            result = _get_openrouter_client()
        assert result == "OR_CLIENT"
        _, kwargs = fake_cls.call_args
        assert kwargs["api_key"] == "or-key"
        assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
        assert kwargs["default_headers"]["X-Title"] == "NormaAI"
        assert kwargs["default_headers"]["HTTP-Referer"] == "https://normaai.org"


# ─── TestGeminiStreamer ──────────────────────────────────────────


class TestGeminiStreamer:
    async def test_yields_chunk_texts_in_order(self):
        settings = _make_settings(provider="gemini")
        # The Gemini client chain: genai.GenerativeModel(...).generate_content_async(...)
        fake_model = MagicMock()
        fake_model.generate_content_async = AsyncMock(
            return_value=_aiter([_gemini_chunk("Hello "), _gemini_chunk("world")])
        )
        fake_genai = MagicMock()
        fake_genai.GenerativeModel.return_value = fake_model
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_gemini_client", return_value=fake_genai),
        ):
            tokens = await _collect(_astream_gemini_with_retry("sys", "user"))
        assert tokens == ["Hello ", "world"]

    async def test_combines_system_and_user_into_prompt(self):
        settings = _make_settings(provider="gemini")
        fake_model = MagicMock()
        fake_model.generate_content_async = AsyncMock(return_value=_aiter([_gemini_chunk("ok")]))
        fake_genai = MagicMock()
        fake_genai.GenerativeModel.return_value = fake_model
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_gemini_client", return_value=fake_genai),
        ):
            await _collect(_astream_gemini_with_retry("SYSTEM", "USER"))
        # generate_content_async is called with the combined prompt + stream=True.
        args, kwargs = fake_model.generate_content_async.call_args
        assert args[0] == "SYSTEM\n\nUSER"
        assert kwargs["stream"] is True
        # generation_config carries temperature + max_output_tokens from settings.
        _, model_kwargs = fake_genai.GenerativeModel.call_args
        assert model_kwargs["model_name"] == "gemini-2.5-flash"
        assert model_kwargs["generation_config"]["temperature"] == 0.3
        assert model_kwargs["generation_config"]["max_output_tokens"] == 2048

    async def test_empty_chunk_text_is_skipped(self):
        # Only truthy chunk.text is yielded (empty deltas are filtered out).
        settings = _make_settings(provider="gemini")
        fake_model = MagicMock()
        fake_model.generate_content_async = AsyncMock(
            return_value=_aiter(
                [_gemini_chunk("a"), _gemini_chunk(""), _gemini_chunk("b"), _gemini_chunk(None)]
            )
        )
        fake_genai = MagicMock()
        fake_genai.GenerativeModel.return_value = fake_model
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_gemini_client", return_value=fake_genai),
        ):
            tokens = await _collect(_astream_gemini_with_retry("sys", "user"))
        assert tokens == ["a", "b"]

    async def test_provider_error_is_classified_and_raised(self):
        # An auth-flavoured error is classified NonRetryable → not retried,
        # raised on the first attempt.
        settings = _make_settings(provider="gemini")
        fake_genai = MagicMock()
        fake_genai.GenerativeModel.side_effect = RuntimeError("invalid api_key")
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_gemini_client", return_value=fake_genai),
            pytest.raises(streaming_llm.NonRetryableLLMError),
        ):
            await _collect(_astream_gemini_with_retry("sys", "user"))

    async def test_retryable_error_not_retried_on_stream(self):
        # By design the streaming path does NOT retry: a partial stream can't be
        # safely resumed, so a transient error (429) is classified
        # RetryableLLMError and surfaced after a SINGLE attempt for the caller to
        # retry the whole request. (The unary acall_llm path does retry: 3x.)
        settings = _make_settings(provider="gemini")
        fake_genai = MagicMock()
        fake_genai.GenerativeModel.side_effect = RuntimeError("rate limit 429")
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_gemini_client", return_value=fake_genai),
            pytest.raises(streaming_llm.RetryableLLMError),
        ):
            await _collect(_astream_gemini_with_retry("sys", "user"))
        # Constructed exactly once (no retry).
        assert fake_genai.GenerativeModel.call_count == 1


# ─── TestAnthropicStreamer ───────────────────────────────────────


class TestAnthropicStreamer:
    def _client_with_text_stream(self, texts):
        """Build a fake AsyncAnthropic whose .messages.stream() yields texts."""
        stream_obj = MagicMock()
        stream_obj.text_stream = _aiter(texts)

        stream_cm = MagicMock()
        stream_cm.__aenter__ = AsyncMock(return_value=stream_obj)
        stream_cm.__aexit__ = AsyncMock(return_value=False)

        client = MagicMock()
        client.messages.stream = MagicMock(return_value=stream_cm)
        return client

    async def test_yields_text_deltas(self):
        settings = _make_settings(provider="anthropic")
        client = self._client_with_text_stream(["The ", "quick ", "fox"])
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_anthropic_client", return_value=client),
        ):
            tokens = await _collect(_astream_anthropic_with_retry("sys", "user"))
        assert tokens == ["The ", "quick ", "fox"]

    async def test_stream_called_with_config(self):
        settings = _make_settings(provider="anthropic")
        client = self._client_with_text_stream(["x"])
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_anthropic_client", return_value=client),
        ):
            await _collect(_astream_anthropic_with_retry("SYS", "USR"))
        _, kwargs = client.messages.stream.call_args
        assert kwargs["model"] == "claude-sonnet-4-5"
        assert kwargs["max_tokens"] == 2048
        assert kwargs["temperature"] == 0.3
        assert kwargs["system"] == "SYS"
        assert kwargs["messages"] == [{"role": "user", "content": "USR"}]

    async def test_error_classified_and_not_retried_on_stream(self):
        # By design (see the Gemini streamer test): a transient error (503
        # overloaded) is classified RetryableLLMError and surfaced after a single
        # attempt -- the streaming path does not retry a partial stream.
        settings = _make_settings(provider="anthropic")
        client = MagicMock()
        client.messages.stream = MagicMock(side_effect=RuntimeError("overloaded 503"))
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_anthropic_client", return_value=client),
            pytest.raises(streaming_llm.RetryableLLMError),
        ):
            await _collect(_astream_anthropic_with_retry("sys", "user"))
        # Stream attempted exactly once (no retry).
        assert client.messages.stream.call_count == 1


# ─── TestOpenRouterStreamer ──────────────────────────────────────


class TestOpenRouterStreamer:
    async def test_yields_delta_content(self):
        settings = _make_settings(provider="openrouter")
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=_aiter([_openrouter_chunk("Hel"), _openrouter_chunk("lo")])
        )
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_openrouter_client", return_value=client),
        ):
            tokens = await _collect(_astream_openrouter_with_retry("sys", "user"))
        assert tokens == ["Hel", "lo"]

    async def test_skips_empty_deltas_and_choiceless_chunks(self):
        # delta.content == None or "" → skipped; a chunk with empty choices → skipped.
        settings = _make_settings(provider="openrouter")
        choiceless = SimpleNamespace(choices=[])
        client = MagicMock()
        client.chat.completions.create = AsyncMock(
            return_value=_aiter(
                [
                    _openrouter_chunk("a"),
                    _openrouter_chunk(None),
                    choiceless,
                    _openrouter_chunk(""),
                    _openrouter_chunk("b"),
                ]
            )
        )
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_openrouter_client", return_value=client),
        ):
            tokens = await _collect(_astream_openrouter_with_retry("sys", "user"))
        assert tokens == ["a", "b"]

    async def test_create_called_with_stream_true_and_messages(self):
        settings = _make_settings(provider="openrouter")
        client = MagicMock()
        client.chat.completions.create = AsyncMock(return_value=_aiter([_openrouter_chunk("x")]))
        with (
            _patch_settings(settings),
            patch.object(streaming_llm, "_get_openrouter_client", return_value=client),
        ):
            await _collect(_astream_openrouter_with_retry("SYS", "USR"))
        _, kwargs = client.chat.completions.create.call_args
        assert kwargs["stream"] is True
        assert kwargs["model"] == "some/free-model:free"
        assert kwargs["messages"] == [
            {"role": "system", "content": "SYS"},
            {"role": "user", "content": "USR"},
        ]


# ─── TestAstreamLLM (public dispatcher) ──────────────────────────


class TestAstreamLLM:
    async def test_missing_api_key_raises_non_retryable(self):
        settings = _make_settings(provider="gemini", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings), pytest.raises(streaming_llm.NonRetryableLLMError) as exc:
            await _collect(astream_llm("sys", "user"))
        assert "GOOGLE_API_KEY not configured" in str(exc.value)

    async def test_missing_api_key_message_per_provider(self):
        settings = _make_settings(provider="openrouter", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings), pytest.raises(streaming_llm.NonRetryableLLMError) as exc:
            await _collect(astream_llm("sys", "user"))
        assert "OPENROUTER_API_KEY" in str(exc.value)

    async def test_missing_api_key_anthropic_default_label(self):
        settings = _make_settings(provider="anthropic", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings), pytest.raises(streaming_llm.NonRetryableLLMError) as exc:
            await _collect(astream_llm("sys", "user"))
        assert "ANTHROPIC_API_KEY" in str(exc.value)

    async def test_open_circuit_raises_service_unavailable(self):
        # require_circuit() runs OUTSIDE the try block in astream_llm, so an OPEN
        # circuit propagates ServiceUnavailableError (it is NOT degraded to an
        # error dict the way the unary call_llm path does). Capture that behavior.
        for _ in range(5):
            llm_circuit.record_failure()
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()
        with _patch_settings(settings), patch_sem, pytest.raises(ServiceUnavailableError):
            await _collect(astream_llm("sys", "user"))

    async def test_gemini_routing_yields_and_records_success(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, sem = _patch_semaphore()
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(
                streaming_llm,
                "_astream_gemini_with_retry",
                return_value=_aiter(["g1", "g2"]),
            ),
        ):
            tokens = await _collect(astream_llm("sys", "user"))
        assert tokens == ["g1", "g2"]
        # A clean stream records circuit success and holds exactly one permit.
        assert llm_circuit.is_available is True
        assert llm_circuit._success_count == 1
        assert sem.entered == 1
        assert sem.exited == 1

    async def test_openrouter_routing(self):
        settings = _make_settings(provider="openrouter", api_key="k")
        patch_sem, _ = _patch_semaphore()
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(
                streaming_llm,
                "_astream_openrouter_with_retry",
                return_value=_aiter(["o1"]),
            ),
        ):
            tokens = await _collect(astream_llm("sys", "user"))
        assert tokens == ["o1"]

    async def test_anthropic_is_fallback_branch(self):
        # Any provider value that is not gemini/openrouter routes to Anthropic.
        settings = _make_settings(provider="anthropic", api_key="k")
        patch_sem, _ = _patch_semaphore()
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(
                streaming_llm,
                "_astream_anthropic_with_retry",
                return_value=_aiter(["a1", "a2"]),
            ),
        ):
            tokens = await _collect(astream_llm("sys", "user"))
        assert tokens == ["a1", "a2"]

    async def test_accumulation_reconstructs_full_message(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()
        pieces = ["Companies ", "with ", "1000 ", "employees ", "must ", "report."]
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(
                streaming_llm,
                "_astream_gemini_with_retry",
                return_value=_aiter(pieces),
            ),
        ):
            accumulated = ""
            async for tok in astream_llm("sys", "user"):
                accumulated += tok
        assert accumulated == "Companies with 1000 employees must report."

    async def test_non_retryable_error_propagates_and_records_failure(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()

        async def _boom():
            raise streaming_llm.NonRetryableLLMError("bad key")
            yield  # make it a generator (unreachable)

        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", return_value=_boom()),
            pytest.raises(streaming_llm.NonRetryableLLMError),
        ):
            await _collect(astream_llm("sys", "user"))
        # The error path records a circuit failure.
        assert llm_circuit._failure_count == 1

    async def test_retryable_error_propagates_and_records_failure(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()

        async def _boom():
            raise streaming_llm.RetryableLLMError("rate limit")
            yield

        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", return_value=_boom()),
            pytest.raises(streaming_llm.RetryableLLMError),
        ):
            await _collect(astream_llm("sys", "user"))
        assert llm_circuit._failure_count == 1

    async def test_cancelled_error_propagates_without_recording_failure(self):
        # CancelledError (client disconnect) is re-raised but must NOT be counted
        # as a circuit failure - a disconnect is not a provider outage.
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()

        async def _cancel():
            raise asyncio.CancelledError()
            yield

        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", return_value=_cancel()),
            pytest.raises(asyncio.CancelledError),
        ):
            await _collect(astream_llm("sys", "user"))
        assert llm_circuit._failure_count == 0

    async def test_unexpected_error_propagates_and_records_failure(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()

        async def _boom():
            raise ValueError("totally unexpected")
            yield

        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", return_value=_boom()),
            pytest.raises(ValueError),
        ):
            await _collect(astream_llm("sys", "user"))
        assert llm_circuit._failure_count == 1

    async def test_partial_stream_then_error_yields_then_raises(self):
        # Tokens emitted before the failure are observed by the caller; the
        # exception then surfaces. Verifies streaming is lazy, not buffered.
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()

        async def _partial():
            yield "first"
            yield "second"
            raise streaming_llm.RetryableLLMError("died mid-stream")

        seen = []
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", return_value=_partial()),
            pytest.raises(streaming_llm.RetryableLLMError),
        ):
            async for tok in astream_llm("sys", "user"):
                seen.append(tok)
        assert seen == ["first", "second"]
        assert llm_circuit._failure_count == 1


# ─── TestAstreamLLMJson ──────────────────────────────────────────


class TestAstreamLLMJson:
    async def test_appends_json_instruction_to_user_message(self):
        settings = _make_settings(provider="gemini", api_key="k")
        patch_sem, _ = _patch_semaphore()
        captured = {}

        def _capture(system_prompt, user_message):
            captured["system"] = system_prompt
            captured["user"] = user_message
            return _aiter(["{", '"a": 1', "}"])

        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(streaming_llm, "_astream_gemini_with_retry", side_effect=_capture),
        ):
            tokens = await _collect(astream_llm_json("system", "Give me JSON"))
        # System prompt is untouched; user message is augmented with the
        # JSON-only instruction (which the production code appends verbatim).
        assert captured["system"] == "system"
        assert captured["user"].startswith("Give me JSON")
        assert "valid JSON only" in captured["user"]
        assert tokens == ["{", '"a": 1', "}"]

    async def test_streams_through_unchanged_tokens(self):
        # The JSON wrapper does not transform tokens; it only augments the prompt.
        settings = _make_settings(provider="anthropic", api_key="k")
        patch_sem, _ = _patch_semaphore()
        with (
            _patch_settings(settings),
            patch_sem,
            patch.object(
                streaming_llm,
                "_astream_anthropic_with_retry",
                return_value=_aiter(['{"k":', " 42}"]),
            ),
        ):
            accumulated = "".join(await _collect(astream_llm_json("sys", "q")))
        assert accumulated == '{"k": 42}'

    async def test_json_wrapper_missing_key_still_raises(self):
        # The wrapper delegates to astream_llm, so the api-key guard still fires.
        settings = _make_settings(provider="gemini", api_key="")
        settings.active_api_key = ""
        with _patch_settings(settings), pytest.raises(streaming_llm.NonRetryableLLMError):
            await _collect(astream_llm_json("sys", "user"))
