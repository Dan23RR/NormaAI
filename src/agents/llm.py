"""LLM helpers: provider abstraction, JSON parsing, confidence extraction.

Provides both sync (call_llm) and async (acall_llm) interfaces.
The async path uses LangChain's native .ainvoke() to avoid blocking
the FastAPI event loop - critical for concurrent request handling.

Retry strategy: exponential backoff via tenacity for transient failures
(rate limits, overload, timeouts). Non-retryable errors (auth, config)
fail immediately.
"""

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.resilience import ServiceUnavailableError, llm_circuit, require_circuit

logger = logging.getLogger(__name__)


# ─── Retryable exception detection ───────────────────────────────


class RetryableLLMError(Exception):
    """Transient LLM error (rate limit, overload, timeout)."""

    pass


class NonRetryableLLMError(Exception):
    """Permanent LLM error (auth, config, invalid input)."""

    pass


def _classify_error(e: Exception) -> Exception:
    """Classify an LLM error as retryable or not."""
    msg = str(e).lower()
    if any(
        kw in msg for kw in ("rate", "quota", "429", "overloaded", "503", "timeout", "connection")
    ):
        return RetryableLLMError(str(e))
    if any(kw in msg for kw in ("auth", "api_key", "invalid", "permission", "forbidden")):
        return NonRetryableLLMError(str(e))
    return RetryableLLMError(str(e))  # Default: assume transient


# ─── LLM Instance Factory ────────────────────────────────────────


def get_llm(temperature: float | None = None):
    """Create LLM instance based on configured provider (Gemini/Anthropic/OpenRouter).

    temperature: override the configured default. CRITICAL for the SNC trust
    layer - without a non-zero temperature the K stochastic samples are
    identical, so the diversity/entropy signal (and the whole trust score) is
    inert. Pass an explicit value for sampling-based governance.
    """
    from src.config import get_settings

    settings = get_settings()
    temp = settings.llm_temperature if temperature is None else temperature

    if settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model_analysis,
            temperature=temp,
            max_output_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            google_api_key=settings.google_api_key,
        )
    elif settings.llm_provider == "openrouter":
        # OpenAI-compatible gateway: hundreds of models behind one key,
        # including free tiers (real-LLM tests without paid quota).
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openrouter_model_analysis,
            temperature=temp,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_base_url,
            default_headers={
                # OpenRouter attribution headers (ranking/analytics)
                "HTTP-Referer": settings.normaai_public_url,
                "X-Title": "NormaAI",
            },
        )
    else:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=settings.anthropic_model_analysis,
            temperature=temp,
            max_tokens=settings.llm_max_tokens,
            timeout=settings.llm_timeout_seconds,
            anthropic_api_key=settings.anthropic_api_key,
        )


def _make_error_response(error_msg: str) -> dict:
    """Build a standardized error response dict."""
    from src.config import get_settings

    settings = get_settings()

    if (
        "auth" in error_msg.lower()
        or "api_key" in error_msg.lower()
        or "invalid" in error_msg.lower()
    ):
        detail = f"Invalid API key for {settings.llm_provider}. Check your .env file."
    elif "timeout" in error_msg.lower():
        detail = f"LLM timed out after {settings.llm_timeout_seconds}s. Try a simpler query."
    elif "rate" in error_msg.lower() or "quota" in error_msg.lower() or "429" in error_msg:
        detail = f"Rate limited by {settings.llm_provider} API. Wait a moment and retry."
    elif "overloaded" in error_msg.lower() or "503" in error_msg:
        detail = f"{settings.llm_provider} is temporarily overloaded. Retry in 30 seconds."
    elif "circuit" in error_msg.lower():
        detail = "LLM service is temporarily unavailable. The system is recovering."
    else:
        detail = f"LLM error ({settings.llm_provider}): {error_msg}"

    return {
        "error": detail,
        "confidence_score": 0.0,
        "requires_expert_review": True,
    }


# ─── Synchronous LLM Call (preserved for tests & scripts) ────────


def call_llm(system_prompt: str, user_message: str) -> dict:
    """Call LLM synchronously. Use acall_llm() in async FastAPI paths."""
    from src.config import get_settings

    settings = get_settings()

    if not settings.active_api_key:
        key_name = {"gemini": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
            settings.llm_provider, "ANTHROPIC_API_KEY"
        )
        return {
            "error": f"{key_name} not configured. Add it to your .env file.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }

    # Circuit check inside its own guard: an OPEN circuit must degrade to the
    # standardized error dict (what every caller expects), not raise
    # ServiceUnavailableError up into the agent graph.
    try:
        require_circuit(llm_circuit)
    except ServiceUnavailableError as e:
        logger.warning(f"LLM circuit open ({settings.llm_provider}): {e}")
        return _make_error_response(f"LLM circuit open: {e}")

    try:
        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        response = llm.invoke(messages)
        llm_circuit.record_success()
        return parse_json_response(response.content)

    except Exception as e:
        llm_circuit.record_failure()
        logger.error(f"LLM call failed ({settings.llm_provider}): {e}")
        return _make_error_response(str(e))


# ─── Async LLM Call (native .ainvoke - non-blocking) ─────────────


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _ainvoke_llm_with_retry(
    system_prompt: str, user_message: str, temperature: float | None = None
) -> str:
    """Internal: invoke LLM async with retry on transient errors."""
    try:
        llm = get_llm(temperature=temperature)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        raise _classify_error(e) from e


async def acall_llm(
    system_prompt: str, user_message: str, temperature: float | None = None
) -> dict:
    """Call LLM asynchronously using native .ainvoke().

    This is the preferred path for FastAPI endpoints.
    It does NOT block the asyncio event loop.

    Features:
    - Circuit breaker (fast-fail when LLM is down)
    - Exponential backoff retry (3 attempts for transient errors)
    - Concurrency limited by the caller's semaphore
    """
    from src.config import get_settings

    settings = get_settings()

    if not settings.active_api_key:
        key_name = {"gemini": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
            settings.llm_provider, "ANTHROPIC_API_KEY"
        )
        return {
            "error": f"{key_name} not configured. Add it to your .env file.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }

    # Circuit check inside its own guard (see call_llm): an OPEN circuit degrades
    # to the standardized error dict instead of raising into the agent graph.
    try:
        require_circuit(llm_circuit)
    except ServiceUnavailableError as e:
        logger.warning(f"LLM circuit open ({settings.llm_provider}): {e}")
        return _make_error_response(f"LLM circuit open: {e}")

    try:
        # Acquire the concurrency permit PER LLM CALL so the SNC/CoVe fan-out
        # (K resamples + N verifications per request) cannot stampede the provider.
        from src.resilience import get_llm_semaphore

        async with get_llm_semaphore():
            content = await _ainvoke_llm_with_retry(
                system_prompt, user_message, temperature=temperature
            )
        llm_circuit.record_success()
        return parse_json_response(content)

    except NonRetryableLLMError as e:
        llm_circuit.record_failure()
        # stdlib logger: structured fields MUST go via extra={...}; passing them
        # as kwargs raises TypeError inside the handler and masks the real error.
        logger.error(
            "llm_non_retryable_error",
            extra={"provider": settings.llm_provider, "error": str(e)},
        )
        return _make_error_response(str(e))

    except RetryableLLMError as e:
        llm_circuit.record_failure()
        logger.error(
            "llm_retryable_exhausted",
            extra={"provider": settings.llm_provider, "error": str(e)},
        )
        return _make_error_response(str(e))

    except Exception as e:
        llm_circuit.record_failure()
        logger.error(
            "llm_unexpected_error",
            extra={"provider": settings.llm_provider, "error": str(e)},
        )
        return _make_error_response(str(e))


# ─── Response Parsing ─────────────────────────────────────────────


def parse_json_response(content: str) -> dict:
    """Robust JSON extraction from LLM response."""
    if not isinstance(content, str):
        content = str(content)

    # Step 1: Try direct parse
    try:
        return json.loads(content.strip())
    except json.JSONDecodeError:
        pass

    # Step 2: Extract from markdown code blocks
    json_block_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    match = json_block_pattern.search(content)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Step 3: Find JSON object boundaries { ... }
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(content[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    # Step 4: Fallback
    logger.warning("Failed to parse JSON from LLM response, returning raw text")
    return {
        "answer": content,
        "citations": [],
        "confidence_score": 0.5,
        "requires_expert_review": True,
        "parse_warning": "Response was not valid JSON; returning raw text.",
    }


def extract_confidence(result: dict) -> float:
    """Safely extract confidence score from result dict."""
    if not isinstance(result, dict):
        return 0.0
    score = result.get("confidence_score", 0.0)
    try:
        return max(0.0, min(1.0, float(score)))
    except (ValueError, TypeError):
        return 0.0


def format_retrieved_chunks(chunks: list) -> str:
    """Format retrieved chunks for inclusion in prompts."""
    if not chunks:
        return "No relevant regulatory text found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        if isinstance(chunk, dict):
            citation = f"[{chunk.get('framework', '?')}, {chunk.get('article_number', '?')}]"
            parts.append(f"--- Source {i} {citation} ---\n{chunk.get('text', '')}\n")
        else:
            parts.append(f"--- Source {i} ---\n{str(chunk)}\n")
    return "\n".join(parts)
