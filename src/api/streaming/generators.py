"""SSE event generators for the Intelligence streaming endpoints.

Extracted from ``src/api/routers/intelligence.py`` to keep the router thin: this
module holds the per-task async generators that drive ``/qa/stream``,
``/gap-analysis/stream`` and ``/monitor/stream`` (draft -> token chunks ->
citations -> optional CoVe verification -> done). The heavy agent/CoVe imports
stay function-local so importing this module is cheap.

Honesty rules enforced here (audit, phase 1):

- an agent failure (LLM / retrieval / timeout) is an ``error`` event with an
  Italian message and ``recoverable=False`` - it is never streamed as tokens and
  never followed by a ``done`` event;
- ``done.confidence_score`` is the pipeline's own score; a missing score is 0.0
  with ``requires_review=True``, never a made-up default;
- ``done.cove_applied`` is True only when the CoVe orchestrator actually ran and
  emitted its own ``done``; if CoVe was requested but failed, a recoverable
  ``error`` event says so and the final ``done`` carries ``cove_applied=False``
  and ``requires_review=True`` (the answer is unverified);
- citation ``verified`` is emitted only when a verifier produced it: for Q&A
  the deterministic citation verifier (src.agents.citation_verifier), True only
  when the quote was found word for word in a retrieved official text; the
  unverified-citation policy is re-applied here (idempotent) so the stream and
  ``POST /qa`` serve the same decision, and CoVe cannot clear its flag.
"""

import json
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, TypeGuard, get_args

import structlog

from src.agents.citation_verifier import (
    UNVERIFIED_CONFIDENCE_CAP,
    apply_unverified_policy,
    citation_counters,
    policy_mode,
    unverified_policy_applies,
)
from src.api.errors import ResultFailure, classify_result
from src.api.streaming.sse import (
    CitationEvent,
    CitationLevel,
    CitationMatch,
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    SSEEvent,
    TokenEvent,
)
from src.auth.dependencies import CurrentUser
from src.config import get_settings

logger = structlog.get_logger()

_CHUNK_SIZE = 80

# Catch-all for unexpected exceptions: the raw text goes to the logs, never to
# the browser (same masking as the JSON routers' generic 500).
_INTERNAL_ERROR_MESSAGE = "Errore interno durante l'analisi. Riprova più tardi."

_COVE_FAILED_MESSAGE = (
    "La verifica Chain-of-Verification non è stata completata: "
    "la risposta è servita senza verifica e richiede revisione esperta."
)

# EUR-Lex interface languages accepted in the citation link (ISO 639-1, upper).
_EURLEX_LANGUAGES = frozenset(
    {
        "BG", "CS", "DA", "DE", "EL", "EN", "ES", "ET", "FI", "FR", "GA", "HR", "HU",
        "IT", "LT", "LV", "MT", "NL", "PL", "PT", "RO", "SK", "SL", "SV",
    }
)  # fmt: skip


def eurlex_celex_url(celex: str, language: str = "it") -> str:
    """Canonical EUR-Lex link for a CELEX number in the requested interface language.

    Defaults to Italian; ``/EN/`` when the report language is English (any other
    EUR-Lex language code is honoured, unknown codes fall back to Italian). The
    old ``/eli/<celex>`` form was not a valid EUR-Lex URL.
    """
    lang = (language or "it").strip().upper()
    if lang not in _EURLEX_LANGUAGES:
        lang = "IT"
    return f"https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:{celex}"


def _primary_celex_for_framework(framework: str) -> str:
    """CELEX of the primary act of a framework (first seeded entry), or ''."""
    if not framework:
        return ""
    try:
        from src.crawler.eurlex.client import CORE_FRAMEWORKS
    except Exception:  # noqa: BLE001 - citation link is best-effort
        return ""
    celex_map = CORE_FRAMEWORKS.get(str(framework).upper()) or {}
    return next(iter(celex_map), "")


_MATCH_VALUES: frozenset[str] = frozenset(get_args(CitationMatch))
_LEVEL_VALUES: frozenset[str] = frozenset(get_args(CitationLevel))


def _is_match(value: str) -> TypeGuard[CitationMatch]:
    return value in _MATCH_VALUES


def _is_level(value: str) -> TypeGuard[CitationLevel]:
    return value in _LEVEL_VALUES


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _str_list(value: Any) -> list[str]:
    """A list of non-empty strings from a result field (a lone string becomes one item)."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _citation_event(cit: dict[str, Any], language: str) -> CitationEvent:
    """Map a result citation dict to a CitationEvent without inventing fields.

    A citation the verifier confirmed (``verified`` True) is described by the
    official text it was found in: its article, paragraph, wording
    (``official_quote``), chunk, language and server-built URL. Otherwise the
    event carries the model's reference and quote, and the link falls back to
    the primary act of the cited framework.
    """
    framework = str(cit.get("framework") or "")
    verified = cit.get("verified")
    verified = verified if isinstance(verified, bool) else None
    official = verified is True
    if official:
        # The verifier's provenance only: the passage may belong to another act
        # than the cited framework (level "any"), so no fallback is guessed.
        celex = str(cit.get("celex") or "")
        url = cit.get("url") or None
    else:
        celex = str(cit.get("celex") or "") or _primary_celex_for_framework(framework)
        url = cit.get("url") or (eurlex_celex_url(celex, language) if celex else None)
    reference = cit.get("reference") or cit.get("article_ref") or cit.get("article") or ""
    quote = (cit.get("official_quote") if official else None) or (
        cit.get("quote_snippet") or cit.get("quote")
    )
    grounded = cit.get("grounded")
    match, level = str(cit.get("match") or ""), str(cit.get("level") or "")
    return CitationEvent(
        framework=framework or None,
        celex=celex,
        urn=cit.get("urn"),
        article=str((cit.get("article") if official else None) or reference),
        paragraph=_text_or_none(cit.get("paragraph")) if official else None,
        title=str(cit.get("title") or framework),
        url=url,
        quote=_text_or_none(quote),
        verified=verified,
        match=match if official and _is_match(match) else None,
        level=level if official and _is_level(level) else None,
        chunk_id=_text_or_none(cit.get("chunk_id")) if official else None,
        lang=_text_or_none(cit.get("lang")) if official else None,
        consolidated_as_of=_text_or_none(cit.get("consolidated_as_of")) if official else None,
        grounded=grounded if isinstance(grounded, bool) else None,
    )


def _token_events(text: str) -> list[TokenEvent]:
    """Chunk the answer text for a smooth streaming UX."""
    if not isinstance(text, str) or not text:
        return []
    return [
        TokenEvent(content=text[i : i + _CHUNK_SIZE], index=i // _CHUNK_SIZE)
        for i in range(0, len(text), _CHUNK_SIZE)
    ]


def _failure_event(failure: ResultFailure, task: str) -> ErrorEvent:
    """Terminal error event for a failed draft (the stream ends here)."""
    logger.warning(
        f"{task}_stream_agent_error",
        error_code=failure.error_code,
        status_code=failure.status_code,
        upstream=failure.upstream,
    )
    return ErrorEvent(message=failure.detail, recoverable=False, error_code=failure.error_code)


def _honest_confidence(result: dict[str, Any]) -> tuple[float, bool]:
    """(confidence, requires_review) taken from the result, never invented.

    A missing or unparseable score is reported as 0.0 AND forces expert review:
    nothing in the pipeline scored this answer, so no default may stand in.
    """
    raw = result.get("confidence_score")
    try:
        confidence = None if raw is None else float(raw)
    except (TypeError, ValueError):
        confidence = None
    if confidence is None:
        return 0.0, True
    confidence = max(0.0, min(1.0, confidence))
    return confidence, bool(result.get("requires_expert_review"))


def _result_fields(result: dict[str, Any], *, with_citations: bool) -> dict[str, Any]:
    """What the ``done`` event reports about the answer beyond its score.

    ``caveats``, ``related_frameworks``, ``abstention_reason`` and the corpus
    date for every task; the citation counters for Q&A (``with_citations``).
    """
    fields: dict[str, Any] = {
        "caveats": _str_list(result.get("caveats")),
        "related_frameworks": _str_list(result.get("related_frameworks")),
        "abstention_reason": _text_or_none(result.get("abstention_reason")),
        "corpus_as_of": _text_or_none(getattr(get_settings(), "corpus_as_of", None)),
    }
    if with_citations:
        verified, total = citation_counters(result)
        fields["verified_citations"] = verified
        fields["citations_total"] = total
    return fields


def _done_event(
    result: dict[str, Any], text: str, *, cove_failed: bool, with_citations: bool = False
) -> DoneEvent:
    """Final event for the non-CoVe path (or the CoVe-failed fallback)."""
    confidence, requires_review = _honest_confidence(result)
    return DoneEvent(
        total_tokens=len(text.split()) if isinstance(text, str) else 0,
        confidence_score=confidence,
        requires_review=requires_review or cove_failed,
        cove_applied=False,
        **_result_fields(result, with_citations=with_citations),
    )


def _cove_done_event(done: DoneEvent, result: dict[str, Any], *, with_citations: bool) -> DoneEvent:
    """The CoVe orchestrator's own ``done``, completed with the answer's fields.

    CoVe revises the text, not the citations: when none of them was verified
    its score and review verdict cannot clear the unverified-citation flag.
    """
    update = _result_fields(result, with_citations=with_citations)
    if with_citations and unverified_policy_applies(result):
        update["requires_review"] = True
        update["confidence_score"] = min(done.confidence_score, UNVERIFIED_CONFIDENCE_CAP)
    return done.model_copy(update=update)


def _gap_summary_text(result: dict[str, Any]) -> str:
    """Text to stream for a gap analysis (the agent returns structured JSON).

    Falls back to a compact one-line digest built from the real fields, then to
    the JSON itself - never to a Python ``repr`` of the dict.
    """
    for key in ("summary", "answer", "executive_summary"):
        value = result.get(key)
        if isinstance(value, str) and value:
            return value
    parts: list[str] = []
    framework = result.get("framework")
    if framework:
        parts.append(f"{framework} gap analysis.")
    score = result.get("overall_score")
    if isinstance(score, int | float):
        parts.append(f"Overall compliance score: {float(score):.1f}%.")
    counts = result.get("status_summary")
    if isinstance(counts, dict) and counts:
        rendered = ", ".join(
            f"{v} {str(k).replace('_', ' ')}" for k, v in counts.items() if isinstance(v, int)
        )
        if rendered:
            parts.append(f"Requirements: {rendered}.")
    requirements = result.get("requirements")
    if isinstance(requirements, list) and requirements and not counts:
        parts.append(f"{len(requirements)} requirements assessed.")
    return " ".join(parts) if parts else json.dumps(result, ensure_ascii=False, default=str)


async def _run_cove(
    query: str,
    profile_dict: dict[str, Any] | None,
    result: dict[str, Any],
    task_type: str,
) -> AsyncIterator[SSEEvent]:
    """Drive the CoVe orchestrator and forward its events.

    Raises if the orchestrator cannot be built or crashes; the caller turns that
    into an honest fallback. The orchestrator emits its own ``done`` (with
    ``cove_applied`` set by it) or a terminal ``error``.
    """
    from src.agents.cove.models import CoVeConfig
    from src.agents.cove.orchestrator import CoVeOrchestrator

    indexer = None
    normattiva_client = None
    try:
        from src.api.app_state import app_state

        indexer = getattr(app_state, "indexer", None)
        # Wire the Normattiva client so CoVe actually validates Italian URN
        # citations; without it _validate_citations silently skips them.
        normattiva_client = getattr(app_state, "normattiva_client", None)
    except (ImportError, AttributeError):
        pass

    orchestrator = CoVeOrchestrator(
        indexer=indexer, normattiva_client=normattiva_client, config=CoVeConfig(enabled=True)
    )
    draft_state = {
        "query": query,
        "company_profile": profile_dict or {},
        "result_json": json.dumps(result, ensure_ascii=False, default=str),
        "task_type": task_type,
    }
    async for event in orchestrator.run(draft_state, task_type):
        yield event


async def _stream_task(
    *,
    task: str,
    run_agent: Callable[[], Awaitable[dict[str, Any]]],
    draft_message: str,
    query: str,
    profile_dict: dict[str, Any] | None,
    enable_cove: bool,
    text_of: Callable[[dict[str, Any]], str],
    language: str = "it",
    emit_citations: bool = False,
) -> AsyncIterator[SSEEvent]:
    """Shared driver for the three streaming tasks."""
    try:
        yield PhaseChangeEvent(phase="draft", message=draft_message)
        result = await run_agent()

        failure = classify_result(result)
        if failure is not None:
            yield _failure_event(failure, task)
            return  # no done event after a failed draft

        if not isinstance(result, dict):
            result = {"answer": str(result)}
        if emit_citations:
            # Q&A: the same unverified-citation decision as POST /qa (idempotent
            # on an answer the agent node already verified).
            result = apply_unverified_policy(
                result, mode=policy_mode(get_settings()), language=language
            )
        text = text_of(result)
        for token in _token_events(text):
            yield token

        if emit_citations:
            for cit in result.get("citations") or []:
                try:
                    yield _citation_event(cit, language)
                except Exception:  # noqa: BLE001 - skip malformed citations
                    continue

        cove_failed = False
        # An abstention has no answer to revise: CoVe is skipped (as in the graph).
        if enable_cove and not result.get("abstention_reason"):
            try:
                async for event in _run_cove(query, profile_dict, result, task):
                    if isinstance(event, DoneEvent):
                        event = _cove_done_event(event, result, with_citations=emit_citations)
                    yield event
                # The orchestrator owns the terminal event (its own done, or a
                # non-recoverable error): never add a second done after it.
                return
            except Exception as cove_err:  # noqa: BLE001
                cove_failed = True
                logger.warning(f"cove_{task}_stream_fallback", error=str(cove_err))
                yield ErrorEvent(
                    message=_COVE_FAILED_MESSAGE, recoverable=True, error_code="cove_failed"
                )

        yield _done_event(result, text, cove_failed=cove_failed, with_citations=emit_citations)
    except Exception as e:  # noqa: BLE001
        logger.error(f"{task}_stream_error", error=str(e), traceback=traceback.format_exc())
        yield ErrorEvent(
            message=_INTERNAL_ERROR_MESSAGE, recoverable=False, error_code="internal_error"
        )


async def qa_stream_generator(
    question: str,
    profile_dict: dict[str, Any] | None,
    user: CurrentUser,
    enable_cove: bool,
    language: str = "it",
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for Q&A streaming response.

    Calls the real agent graph, streams the result as SSE events (tokens and
    citations with EUR-Lex links in ``language``), and optionally runs the CoVe
    anti-hallucination pipeline.
    """

    async def run_agent() -> dict[str, Any]:
        from src.agents.graph import arun_qa

        return await arun_qa(
            question,
            profile_dict,
            cove_enabled=enable_cove,
            org_id=str(user.org_id),
            language=language,
        )

    def text_of(result: dict[str, Any]) -> str:
        answer = result.get("answer", result.get("raw_response"))
        return answer if isinstance(answer, str) else ""

    async for event in _stream_task(
        task="qa",
        run_agent=run_agent,
        draft_message="Generating initial response...",
        query=question,
        profile_dict=profile_dict,
        enable_cove=enable_cove,
        text_of=text_of,
        language=language,
        emit_citations=True,
    ):
        yield event


async def gap_analysis_stream_generator(
    framework: str,
    profile_dict: dict[str, Any],
    user: CurrentUser,
    enable_cove: bool,
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for gap analysis streaming response.

    Calls the real gap analysis agent and streams results as SSE events.
    """

    async def run_agent() -> dict[str, Any]:
        from src.agents.graph import arun_gap_analysis

        return await arun_gap_analysis(
            framework, profile_dict, cove_enabled=enable_cove, org_id=str(user.org_id)
        )

    async for event in _stream_task(
        task="gap_analysis",
        run_agent=run_agent,
        draft_message=f"Analyzing {framework} requirements...",
        query=framework,
        profile_dict=profile_dict,
        enable_cove=enable_cove,
        text_of=_gap_summary_text,
    ):
        yield event


async def monitor_stream_generator(
    regulation_change: str,
    profile_dict: dict[str, Any],
    user: CurrentUser,
    enable_cove: bool,
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for monitor check streaming response.

    Calls the real monitor agent and streams impact analysis as SSE events.
    """

    async def run_agent() -> dict[str, Any]:
        from src.agents.graph import arun_monitor_check

        return await arun_monitor_check(
            regulation_change, profile_dict, cove_enabled=enable_cove, org_id=str(user.org_id)
        )

    def text_of(result: dict[str, Any]) -> str:
        summary = result.get("impact_summary", result.get("answer"))
        return summary if isinstance(summary, str) else json.dumps(result, ensure_ascii=False)

    async for event in _stream_task(
        task="monitor",
        run_agent=run_agent,
        draft_message="Analyzing regulatory change impact...",
        query=regulation_change,
        profile_dict=profile_dict,
        enable_cove=enable_cove,
        text_of=text_of,
    ):
        yield event
