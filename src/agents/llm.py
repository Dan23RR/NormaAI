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
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.agents.citation_verifier import base_celex
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


_CLAUDE_MAJOR = re.compile(r"claude-(?:[a-z]+-)?(\d+)")


# Claude 5 models think adaptively by default, and thinking tokens count toward
# max_tokens: with 4096 the reasoning used up the budget and the JSON answer was
# cut off. This floor leaves room for the reasoning plus the answer; only the
# tokens actually generated are billed.
CLAUDE_5_MIN_MAX_TOKENS = 16000


def _claude_major(model: str) -> int | None:
    match = _CLAUDE_MAJOR.match(model or "")
    return int(match.group(1)) if match else None


def anthropic_accepts_temperature(model: str) -> bool:
    """Whether an Anthropic model accepts the ``temperature`` parameter.

    Claude 5 and later models reject it (HTTP 400, "`temperature` is deprecated
    for this model"); earlier ones (claude-3-*, claude-*-4-*) accept it. For a
    name that cannot be parsed the parameter is left out, because the API
    default is accepted by every model.
    """
    major = _claude_major(model)
    return major is not None and major < 5


def anthropic_max_tokens(model: str, configured: int) -> int:
    """``max_tokens`` for an Anthropic request.

    Claude 5 and later (and names that cannot be parsed) get at least
    CLAUDE_5_MIN_MAX_TOKENS, so adaptive thinking cannot truncate the answer;
    earlier models keep the configured value.
    """
    major = _claude_major(model)
    if major is not None and major < 5:
        return configured
    return max(configured, CLAUDE_5_MIN_MAX_TOKENS)


def message_text(message) -> str:
    """The text of an LLM reply, without reasoning blocks.

    Claude 5 models reply with a list of content blocks (a signed ``thinking``
    block, then ``text``), and other providers may too; older models return a
    plain string. Reading ``.content`` as a string turned the whole block list
    into the "answer" and broke JSON parsing, so every citation was lost. This
    keeps only the text blocks and works on langchain-core 0.3 and 1.x alike.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)
    return str(content)


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

        model = settings.anthropic_model_analysis
        return ChatAnthropic(
            model=model,
            # None leaves the parameter out of the request (Claude 5 rejects it).
            temperature=temp if anthropic_accepts_temperature(model) else None,
            max_tokens=anthropic_max_tokens(model, settings.llm_max_tokens),
            timeout=settings.llm_timeout_seconds,
            anthropic_api_key=settings.anthropic_api_key,
        )


def _make_error_response(error_msg: str) -> dict:
    """Build a standardized error response dict.

    ``error`` is the human-readable (English, log-oriented) message; ``error_code``
    is the machine-readable class the HTTP layer maps to an honest status code
    (see src.api.errors.ERROR_CODE_STATUS).
    """
    from src.config import get_settings

    settings = get_settings()

    if (
        "auth" in error_msg.lower()
        or "api_key" in error_msg.lower()
        or "invalid" in error_msg.lower()
    ):
        code = "llm_auth"
        detail = f"Invalid API key for {settings.llm_provider}. Check your .env file."
    elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
        code = "llm_timeout"
        detail = f"LLM timed out after {settings.llm_timeout_seconds}s. Try a simpler query."
    elif "rate" in error_msg.lower() or "quota" in error_msg.lower() or "429" in error_msg:
        code = "llm_rate_limited"
        detail = f"Rate limited by {settings.llm_provider} API. Wait a moment and retry."
    elif "overloaded" in error_msg.lower() or "503" in error_msg:
        code = "llm_overloaded"
        detail = f"{settings.llm_provider} is temporarily overloaded. Retry in 30 seconds."
    elif "circuit" in error_msg.lower():
        code = "llm_circuit_open"
        detail = "LLM service is temporarily unavailable. The system is recovering."
    else:
        code = "llm_provider_error"
        detail = f"LLM error ({settings.llm_provider}): {error_msg}"

    return {
        "error": detail,
        "error_code": code,
        "confidence_score": 0.0,
        "requires_expert_review": True,
    }


def _missing_key_response(settings) -> dict:
    """Error dict for a provider whose API key is not configured."""
    key_name = {"gemini": "GOOGLE_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
        settings.llm_provider, "ANTHROPIC_API_KEY"
    )
    return {
        "error": f"{key_name} not configured. Add it to your .env file.",
        "error_code": "llm_not_configured",
        "confidence_score": 0.0,
        "requires_expert_review": True,
    }


# ─── Synchronous LLM Call (preserved for tests & scripts) ────────


def call_llm(system_prompt: str, user_message: str) -> dict:
    """Call LLM synchronously. Use acall_llm() in async FastAPI paths."""
    from src.config import get_settings

    settings = get_settings()

    if not settings.active_api_key:
        return _missing_key_response(settings)

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
        return parse_json_response(message_text(response))

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
        return message_text(response)
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
        return _missing_key_response(settings)

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

# An inline citation as prompts/qa_bot.txt asks the model to write it, [AI_ACT,
# Art. 50(2)] or [GDPR, Recital 42]; an article quoted by an amending act and cited
# as the amended act's (case B of quoted_articles.py) names the CELEX instead,
# [32013L0034, Art. 29 quater bis].
_INLINE_CITATION = re.compile(
    r"\[([A-Z][A-Z0-9_]*|\d{5}[A-Z]\d{4}),\s*"
    r"((?:Art\.|Article|Articolo|Recital|Considerando|Annex|Allegato)[^\[\]]{0,60}?)\s*\]"
)
# A passage the answer quotes: "...", “...” or «...».
_QUOTED_PASSAGE = re.compile(r'"([^"]+)"|“([^”]+)”|«([^»]+)»')
# The answer field of a JSON response too broken to parse.
_ANSWER_FIELD = re.compile(
    r'"answer"\s*:\s*"(.*?)"\s*,\s*"(?:citations|confidence_score|requires_expert_review'
    r'|related_frameworks|caveats)"\s*:',
    re.DOTALL,
)
_MAX_QUOTE_REPAIRS = 50


def _loads(text: str) -> Any:
    # strict=False accepts the raw line breaks models leave inside JSON strings.
    return json.loads(text, strict=False)


def _repair_stray_quotes(text: str) -> dict[str, Any] | None:
    """Parse JSON whose strings contain unescaped double quotes.

    Quoting the law, a model writes ... prevede "per gli esercizi ..." inside the
    answer string without escaping the quotes: the string ends early and parsing
    fails right after one of them (or after a comma that followed it). Each such
    failure is repaired by escaping that quote; a failure anywhere else gives up.
    """
    for _ in range(_MAX_QUOTE_REPAIRS):
        try:
            value = _loads(text)
        except json.JSONDecodeError as e:
            i = e.pos - 1
            while i >= 0 and text[i].isspace():
                i -= 1
            if i >= 0 and text[i] == ",":
                i -= 1
                while i >= 0 and text[i].isspace():
                    i -= 1
            if i < 1 or text[i] != '"' or text[i - 1] == "\\":
                return None
            text = text[:i] + "\\" + text[i:]
            continue
        return value if isinstance(value, dict) else None
    return None


def _json_string(raw: str) -> str:
    """The value of a JSON string literal, tolerating unescaped quotes in it."""
    try:
        value = _loads(f'"{raw}"')
        if isinstance(value, str):
            return value
    except json.JSONDecodeError:
        pass
    return raw.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def _inline_citations(answer: str) -> list[dict[str, str]]:
    """Citations rebuilt from the references an answer writes in its text.

    A model that answers in prose instead of the JSON schema still names its
    sources inline, as qa_bot.txt asks ("... [GDPR, Art. 30(1)]"). Each reference
    becomes a citation that the grounding guard and the verifier check like any
    other. Its quote is the last passage the answer quotes before it, if any, so
    a verbatim quote can still be verified; an unquoted reference to an article
    that is also cited with a quote adds nothing and is dropped.
    """
    found: dict[tuple[str, str], list[str]] = {}
    start = 0
    for ref in _INLINE_CITATION.finditer(answer):
        passages = [
            next(group for group in passage.groups() if group is not None)
            for passage in _QUOTED_PASSAGE.finditer(answer, start, ref.start())
        ]
        quote = passages[-1].strip() if passages else ""
        quotes = found.setdefault((ref.group(1), ref.group(2).strip()), [])
        if quote not in quotes:
            quotes.append(quote)
        start = ref.end()
    return [
        {"framework": framework, "reference": reference, "quote_snippet": quote}
        for (framework, reference), quotes in found.items()
        for quote in ([q for q in quotes if q] or [""])
    ]


def parse_json_response(content: str) -> dict:
    """Robust JSON extraction from LLM response.

    A response that is not JSON, or JSON too broken to repair, becomes the
    answer with the citations written in its text (_inline_citations): in the
    live golden v2 of 2026-10-27, 4 correct answers out of 101 reached the user
    without sources because this fallback returned no citations.
    """
    if not isinstance(content, str):
        content = str(content)

    # Step 1: Try direct parse
    try:
        return _loads(content.strip())
    except json.JSONDecodeError:
        pass

    # Step 2: Extract from markdown code blocks
    json_block_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
    match = json_block_pattern.search(content)
    if match:
        try:
            return _loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Step 3: Find JSON object boundaries { ... }
    brace_start = content.find("{")
    brace_end = content.rfind("}")
    has_braces = brace_start != -1 and brace_end > brace_start
    if has_braces:
        try:
            return _loads(content[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    # Step 4: Escape the stray quotes of quoted law inside the JSON strings
    if match:
        repaired = _repair_stray_quotes(match.group(1).strip())
    elif has_braces:
        repaired = _repair_stray_quotes(content[brace_start : brace_end + 1])
    else:
        repaired = None
    if repaired is not None:
        return repaired

    # Step 5: Fallback: the text is the answer (or the answer field of a JSON too
    # broken to repair), with the citations it writes inline
    logger.warning("Failed to parse JSON from LLM response, returning raw text")
    field = _ANSWER_FIELD.search(content)
    answer = _json_string(field.group(1)) if field else content
    return {
        "answer": answer,
        "citations": _inline_citations(answer),
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


_ACT_TITLE_MAX = 100


def _chunk_label(chunk: dict) -> str:
    """Header of one source in the prompt: what the model must cite, and from where.

    ``[FRAMEWORK, Art. N]`` is the citation marker the model copies; the base
    CELEX, the act title and the language tell it which official text the
    passage below comes from (quotes are verified against that text). An
    article an amending act quotes (src/agents/quoted_articles.py) is labelled
    as the amended act's article, ``[CELEX, Art. N]``, with the amending act
    where its wording comes from; a consolidated article names the act that
    amended it.
    """
    celex = base_celex(chunk)
    if chunk.get("citation_celex"):
        parts = [
            f"[{chunk['citation_celex']}, {chunk['citation_article']}]",
            f"CELEX {chunk['citation_celex']}",
            f"as worded in CELEX {celex} {chunk.get('article')}, which amends it",
        ]
    else:
        framework = chunk.get("framework") or "?"
        article = chunk.get("article") or chunk.get("article_number") or "?"
        parts = [f"[{framework}, {article}]"]
        if celex:
            parts.append(f"CELEX {celex}")
        title = " ".join(str(chunk.get("act_title") or "").split())
        if title:
            if len(title) > _ACT_TITLE_MAX:
                title = title[:_ACT_TITLE_MAX].rstrip() + "..."
            parts.append(title)
    if chunk.get("paragraph"):
        parts.append(f"par. {chunk['paragraph']}")
    if chunk.get("lang"):
        parts.append(f"lang {chunk['lang']}")
    if chunk.get("amended_by_celex"):
        parts.append(
            f"amended by CELEX {chunk['amended_by_celex']} {chunk.get('amended_by_article') or ''}".rstrip()
        )
    return " | ".join(parts)


def format_retrieved_chunks(chunks: list) -> str:
    """Format retrieved chunks for inclusion in prompts, each under a labelled header."""
    if not chunks:
        return "No relevant regulatory text found."
    parts = []
    for i, chunk in enumerate(chunks, 1):
        if isinstance(chunk, dict):
            parts.append(f"--- Source {i} {_chunk_label(chunk)} ---\n{chunk.get('text', '')}\n")
        else:
            parts.append(f"--- Source {i} ---\n{str(chunk)}\n")
    return "\n".join(parts)
