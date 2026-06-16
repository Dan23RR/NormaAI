"""Streaming LLM wrapper for real-time token and delta streaming.

Provides async streaming interfaces for both Gemini and Anthropic providers,
yielding tokens as they arrive from the LLM. Supports both raw token streaming
and JSON-response streaming.

Features:
- Provider abstraction (Gemini / Anthropic)
- Automatic error handling and logging
- Respects LLM settings (temperature, max_tokens, timeout)
- Retry logic for transient failures (via tenacity)
- Circuit breaker integration for service degradation
"""

import asyncio
import logging
from collections.abc import AsyncIterator

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.llm import NonRetryableLLMError, RetryableLLMError, _classify_error
from src.config import get_settings
from src.resilience import llm_circuit, require_circuit

logger = logging.getLogger(__name__)


# ─── Streaming LLM Initialization ───────────────────────────────


def _get_gemini_client():
    """Initialize Google Gemini client for streaming."""
    import google.generativeai as genai

    settings = get_settings()
    genai.configure(api_key=settings.google_api_key)
    return genai


def _get_anthropic_client():
    """Initialize Anthropic async client for streaming."""
    from anthropic import AsyncAnthropic

    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)


def _get_openrouter_client():
    """Initialize OpenAI-compatible async client pointed at OpenRouter."""
    from openai import AsyncOpenAI

    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": settings.normaai_public_url,
            "X-Title": "NormaAI",
        },
    )


# ─── Core Streaming Functions ──────────────────────────────────


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _astream_gemini_with_retry(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Internal: stream from Gemini with retry on transient errors.

    Uses google.generativeai with stream=True for async streaming.
    """
    try:
        genai = _get_gemini_client()
        settings = get_settings()

        # Build request with proper configuration
        generation_config = {
            "temperature": settings.llm_temperature,
            "max_output_tokens": settings.llm_max_tokens,
        }

        # Format messages for Gemini
        # Note: Gemini's API expects a single text prompt, not a message format
        # We'll combine system + user prompt
        full_prompt = f"{system_prompt}\n\n{user_message}"

        # Stream from Gemini
        response = await genai.GenerativeModel(
            model_name=settings.gemini_model_analysis,
            generation_config=generation_config,
        ).generate_content_async(
            full_prompt,
            stream=True,
        )

        # Yield chunks as they arrive
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    except Exception as e:
        raise _classify_error(e) from e


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _astream_anthropic_with_retry(
    system_prompt: str, user_message: str
) -> AsyncIterator[str]:
    """Internal: stream from Anthropic with retry on transient errors.

    Uses anthropic.AsyncAnthropic with streaming context manager.
    """
    try:
        client = _get_anthropic_client()
        settings = get_settings()

        # Stream using context manager
        async with client.messages.stream(
            model=settings.anthropic_model_analysis,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            # Yield text deltas as they arrive
            async for text in stream.text_stream:
                yield text

    except Exception as e:
        raise _classify_error(e) from e


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _astream_openrouter_with_retry(
    system_prompt: str, user_message: str
) -> AsyncIterator[str]:
    """Internal: stream from OpenRouter (OpenAI-compatible chat completions)."""
    try:
        client = _get_openrouter_client()
        settings = get_settings()

        stream = await client.chat.completions.create(
            model=settings.openrouter_model_analysis,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    except Exception as e:
        raise _classify_error(e) from e


# ─── Public Streaming Interface ────────────────────────────────


async def astream_llm(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream tokens from LLM in real-time.

    Provider is determined by src.config.llm_provider setting
    (gemini / anthropic / openrouter).
    Tokens are yielded as they arrive from the LLM.

    Features:
    - Circuit breaker (fast-fail when LLM is down)
    - Exponential backoff retry (3 attempts for transient errors)
    - Proper error handling and logging
    - Respects temperature, max_tokens, timeout from config

    Args:
        system_prompt: System instruction for the LLM
        user_message: User message/query

    Yields:
        Token strings as they arrive from the LLM

    Raises:
        NonRetryableLLMError: Auth or config errors (not retried)
        RetryableLLMError: Transient errors after max retries exhausted
        asyncio.CancelledError: If client disconnects

    Example:
        ```python
        async for token in astream_llm(
            "You are a helpful assistant.",
            "Explain GDPR in one sentence."
        ):
            print(token, end="", flush=True)
        ```
    """
    settings = get_settings()

    if not settings.active_api_key:
        key_name = {"gemini": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
            settings.llm_provider, "ANTHROPIC_API_KEY"
        )
        error_msg = f"{key_name} not configured. Add it to your .env file."
        logger.error("llm_api_key_missing", extra={"key": key_name})
        raise NonRetryableLLMError(error_msg)

    require_circuit(llm_circuit)

    try:
        # Hold one concurrency permit for the duration of the stream (a streaming
        # call occupies a provider slot just like a unary one) — same per-call cap
        # that protects against the SNC/CoVe fan-out stampede.
        from src.resilience import get_llm_semaphore

        async with get_llm_semaphore():
            if settings.llm_provider == "gemini":
                async for token in _astream_gemini_with_retry(system_prompt, user_message):
                    yield token
            elif settings.llm_provider == "openrouter":
                async for token in _astream_openrouter_with_retry(system_prompt, user_message):
                    yield token
            else:  # anthropic
                async for token in _astream_anthropic_with_retry(system_prompt, user_message):
                    yield token

        llm_circuit.record_success()

    except NonRetryableLLMError as e:
        llm_circuit.record_failure()
        logger.error(
            "llm_non_retryable_error",
            extra={
                "provider": settings.llm_provider,
                "error": str(e),
            },
        )
        raise

    except RetryableLLMError as e:
        llm_circuit.record_failure()
        logger.error(
            "llm_retryable_exhausted",
            extra={
                "provider": settings.llm_provider,
                "error": str(e),
            },
        )
        raise

    except asyncio.CancelledError:
        logger.info("llm_stream_cancelled", extra={"reason": "client disconnected"})
        raise

    except Exception as e:
        llm_circuit.record_failure()
        logger.error(
            "llm_unexpected_error",
            extra={
                "provider": settings.llm_provider,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        raise


async def astream_llm_json(system_prompt: str, user_message: str) -> AsyncIterator[str]:
    """Stream tokens from LLM with JSON response instruction.

    Same as astream_llm, but appends instruction to return JSON.
    The caller should accumulate tokens and parse the complete JSON response.

    This is useful for structured responses where you want streaming
    updates but also need to parse the final JSON result.

    Args:
        system_prompt: System instruction for the LLM
        user_message: User message/query

    Yields:
        Raw token strings (caller should accumulate and parse JSON)

    Raises:
        Same as astream_llm

    Example:
        ```python
        accumulated = ""
        async for token in astream_llm_json(
            "You are a JSON API.",
            "Return regulatory article metadata as JSON."
        ):
            accumulated += token
            print(token, end="", flush=True)

        # Parse final JSON
        import json
        result = json.loads(accumulated)
        ```
    """
    # Append JSON instruction to user message
    json_instruction = "\n\nRespond with valid JSON only. No markdown, no explanation."
    augmented_message = user_message + json_instruction

    # Stream with augmented message
    async for token in astream_llm(system_prompt, augmented_message):
        yield token
