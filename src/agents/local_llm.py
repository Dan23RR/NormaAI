"""Local LLM client for Qwen micro-agents via Ollama.

Handles fast local inference (~50ms) for:
- Framework routing
- Complexity scoring
- Named entity extraction (NER)

Returns None on any error so callers can fall back to keyword-based routing
without try/except blocks. Circuit breaker is separate from the remote LLM
circuit to avoid cross-contamination of failure states.
"""

import logging
import time

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.llm import RetryableLLMError, _classify_error, parse_json_response
from src.resilience import local_llm_circuit

logger = logging.getLogger(__name__)


def get_local_llm():
    """Create a ChatOllama instance for the local Qwen model."""
    from langchain_ollama import ChatOllama

    from src.config import get_settings

    settings = get_settings()
    return ChatOllama(
        base_url=settings.local_llm_base_url,
        model=settings.local_llm_model,
        temperature=settings.local_llm_temperature,
        num_predict=settings.local_llm_max_tokens,
        timeout=settings.local_llm_timeout_seconds,
    )


@retry(
    retry=retry_if_exception_type(RetryableLLMError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=5),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _ainvoke_local_with_retry(system_prompt: str, user_message: str) -> str:
    """Internal: invoke local LLM async with retry on transient errors."""
    try:
        llm = get_local_llm()
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        response = await llm.ainvoke(messages)
        return response.content
    except Exception as e:
        raise _classify_error(e) from e


async def acall_local_llm(system_prompt: str, user_message: str) -> dict | None:
    """Call the local LLM asynchronously. Returns None on any error.

    Callers should always have a fallback path when this returns None.
    The circuit breaker prevents repeated calls to a failing local LLM,
    opening after 3 failures and recovering after 30 seconds.
    """
    from src.config import get_settings

    settings = get_settings()
    if not settings.local_llm_enabled:
        return None

    if not local_llm_circuit.is_available:
        logger.debug("local_llm_circuit_open: skipping local LLM call")
        _record_metric("fallback")
        return None

    start = time.perf_counter()
    try:
        content = await _ainvoke_local_with_retry(system_prompt, user_message)
        local_llm_circuit.record_success()
        elapsed = time.perf_counter() - start
        _record_metric("success", elapsed)
        return parse_json_response(content)
    except Exception as e:
        local_llm_circuit.record_failure()
        elapsed = time.perf_counter() - start
        _record_metric("error", elapsed)
        logger.warning("local_llm_call_failed: %s", e)
        return None


def _record_metric(status: str, duration: float | None = None) -> None:
    """Record Prometheus metrics for local LLM calls."""
    try:
        from src.observability import _metrics_available

        if not _metrics_available:
            return
        from src.observability import LOCAL_LLM_CALL_COUNT, LOCAL_LLM_CALL_LATENCY

        LOCAL_LLM_CALL_COUNT.labels(status=status).inc()
        if duration is not None:
            LOCAL_LLM_CALL_LATENCY.observe(duration)
    except Exception:
        pass
