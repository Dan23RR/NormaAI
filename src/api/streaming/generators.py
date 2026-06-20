"""SSE event generators for the Intelligence streaming endpoints.

Extracted from ``src/api/routers/intelligence.py`` to keep the router thin: this
module holds the per-task async generators that drive ``/qa/stream``,
``/gap-analysis/stream`` and ``/monitor/stream`` (draft -> token chunks ->
citations -> optional CoVe verification -> done). Behaviour is unchanged; only
the location moved. The heavy agent/CoVe imports stay function-local so importing
this module is cheap.
"""

import json
import traceback
from collections.abc import AsyncIterator
from typing import Any

import structlog

from src.api.streaming.sse import (
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    PhaseChangeEvent,
    SSEEvent,
    TokenEvent,
)
from src.auth.dependencies import CurrentUser

logger = structlog.get_logger()


async def qa_stream_generator(
    question: str,
    profile_dict: dict[str, Any] | None,
    user: CurrentUser,
    enable_cove: bool,
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for Q&A streaming response.

    Calls the real agent graph, streams the result as SSE events,
    and optionally runs the CoVe anti-hallucination pipeline.
    """
    try:
        from src.agents.graph import arun_qa

        # Phase 1: Draft - call the real agent graph
        yield PhaseChangeEvent(phase="draft", message="Generating initial response...")
        result = await arun_qa(
            question, profile_dict, cove_enabled=enable_cove, org_id=str(user.org_id)
        )

        # Stream the answer as token events
        answer = result.get("answer", result.get("raw_response", str(result)))
        if isinstance(answer, str) and answer:
            # Send the answer in chunks for smooth streaming UX
            chunk_size = 80
            for i in range(0, len(answer), chunk_size):
                yield TokenEvent(content=answer[i : i + chunk_size], index=i // chunk_size)

        # Emit citation events
        citations = result.get("citations", [])
        for cit in citations:
            try:
                yield CitationEvent(
                    celex=cit.get("celex", cit.get("reference", "")),
                    urn=cit.get("urn"),
                    article=cit.get("reference", cit.get("article_ref", "")),
                    title=cit.get("title", cit.get("framework", "")),
                    url=cit.get("url", f"https://eur-lex.europa.eu/eli/{cit.get('celex', '')}"),
                    verified=False,
                )
            except Exception:
                pass  # Skip malformed citations

        # Phase 2-5: CoVe verification (if enabled)
        if enable_cove:
            try:
                from src.agents.cove.models import CoVeConfig
                from src.agents.cove.orchestrator import CoVeOrchestrator

                indexer = None
                normattiva_client = None
                try:
                    from src.api.app_state import app_state

                    indexer = getattr(app_state, "indexer", None)
                    # Wire the Normattiva client so CoVe actually validates Italian
                    # URN citations; without it _validate_citations silently skips them.
                    normattiva_client = getattr(app_state, "normattiva_client", None)
                except (ImportError, AttributeError):
                    pass

                config = CoVeConfig(enabled=True)
                orchestrator = CoVeOrchestrator(
                    indexer=indexer, normattiva_client=normattiva_client, config=config
                )
                draft_state = {
                    "query": question,
                    "company_profile": profile_dict or {},
                    "result_json": json.dumps(result, ensure_ascii=False, default=str),
                    "task_type": "qa",
                }

                async for event in orchestrator.run(draft_state, "qa"):
                    yield event
                return  # CoVe emits its own DoneEvent
            except Exception as cove_err:
                logger.warning("cove_stream_fallback", error=str(cove_err))

        # Send completion event
        confidence = result.get("confidence_score", 0.85)
        yield DoneEvent(
            total_tokens=len(answer.split()) if isinstance(answer, str) else 0,
            confidence_score=float(confidence) if confidence else 0.85,
            requires_review=result.get("requires_expert_review", False),
            cove_applied=enable_cove,
        )
    except Exception as e:
        logger.error("qa_stream_error", error=str(e), traceback=traceback.format_exc())
        yield ErrorEvent(message=str(e), recoverable=False)


async def gap_analysis_stream_generator(
    framework: str,
    profile_dict: dict[str, Any],
    user: CurrentUser,
    enable_cove: bool,
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for gap analysis streaming response.

    Calls the real gap analysis agent and streams results as SSE events.
    """
    try:
        from src.agents.graph import arun_gap_analysis

        # Phase 1: Draft - run the real gap analysis
        yield PhaseChangeEvent(phase="draft", message=f"Analyzing {framework} requirements...")
        result = await arun_gap_analysis(
            framework, profile_dict, cove_enabled=enable_cove, org_id=str(user.org_id)
        )

        # Stream the result summary
        summary = result.get("summary", result.get("answer", str(result)))
        if isinstance(summary, str) and summary:
            chunk_size = 80
            for i in range(0, len(summary), chunk_size):
                yield TokenEvent(content=summary[i : i + chunk_size], index=i // chunk_size)

        # Phase 2-5: CoVe verification (if enabled)
        if enable_cove:
            try:
                from src.agents.cove.models import CoVeConfig
                from src.agents.cove.orchestrator import CoVeOrchestrator

                indexer = None
                normattiva_client = None
                try:
                    from src.api.app_state import app_state

                    indexer = getattr(app_state, "indexer", None)
                    # Wire the Normattiva client so CoVe actually validates Italian
                    # URN citations; without it _validate_citations silently skips them.
                    normattiva_client = getattr(app_state, "normattiva_client", None)
                except (ImportError, AttributeError):
                    pass

                config = CoVeConfig(enabled=True)
                orchestrator = CoVeOrchestrator(
                    indexer=indexer, normattiva_client=normattiva_client, config=config
                )
                draft_state = {
                    "query": framework,
                    "company_profile": profile_dict,
                    "result_json": json.dumps(result, ensure_ascii=False, default=str),
                    "task_type": "gap_analysis",
                }

                async for event in orchestrator.run(draft_state, "gap_analysis"):
                    yield event
                return
            except Exception as cove_err:
                logger.warning("cove_gap_stream_fallback", error=str(cove_err))

        confidence = result.get("confidence_score", 0.80)
        yield DoneEvent(
            total_tokens=len(str(summary).split()) if summary else 0,
            confidence_score=float(confidence) if confidence else 0.80,
            requires_review=result.get("requires_expert_review", True),
            cove_applied=enable_cove,
        )
    except Exception as e:
        logger.error("gap_analysis_stream_error", error=str(e), traceback=traceback.format_exc())
        yield ErrorEvent(message=str(e), recoverable=False)


async def monitor_stream_generator(
    regulation_change: str,
    profile_dict: dict[str, Any],
    user: CurrentUser,
    enable_cove: bool,
) -> AsyncIterator[SSEEvent]:
    """Generate SSE events for monitor check streaming response.

    Calls the real monitor agent and streams impact analysis as SSE events.
    """
    try:
        from src.agents.graph import arun_monitor_check

        # Phase 1: Draft - run the real monitor analysis
        yield PhaseChangeEvent(phase="draft", message="Analyzing regulatory change impact...")
        result = await arun_monitor_check(
            regulation_change, profile_dict, cove_enabled=enable_cove, org_id=str(user.org_id)
        )

        # Stream the impact summary
        summary = result.get("impact_summary", result.get("answer", str(result)))
        if isinstance(summary, str) and summary:
            chunk_size = 80
            for i in range(0, len(summary), chunk_size):
                yield TokenEvent(content=summary[i : i + chunk_size], index=i // chunk_size)

        # Phase 2-5: CoVe verification (if enabled)
        if enable_cove:
            try:
                from src.agents.cove.models import CoVeConfig
                from src.agents.cove.orchestrator import CoVeOrchestrator

                indexer = None
                normattiva_client = None
                try:
                    from src.api.app_state import app_state

                    indexer = getattr(app_state, "indexer", None)
                    # Wire the Normattiva client so CoVe actually validates Italian
                    # URN citations; without it _validate_citations silently skips them.
                    normattiva_client = getattr(app_state, "normattiva_client", None)
                except (ImportError, AttributeError):
                    pass

                config = CoVeConfig(enabled=True)
                orchestrator = CoVeOrchestrator(
                    indexer=indexer, normattiva_client=normattiva_client, config=config
                )
                draft_state = {
                    "query": regulation_change,
                    "company_profile": profile_dict,
                    "result_json": json.dumps(result, ensure_ascii=False, default=str),
                    "task_type": "monitor",
                }

                async for event in orchestrator.run(draft_state, "monitor"):
                    yield event
                return
            except Exception as cove_err:
                logger.warning("cove_monitor_stream_fallback", error=str(cove_err))

        confidence = result.get("confidence_score", 0.90)
        yield DoneEvent(
            total_tokens=len(str(summary).split()) if summary else 0,
            confidence_score=float(confidence) if confidence else 0.90,
            requires_review=result.get("requires_expert_review", False),
            cove_applied=enable_cove,
        )
    except Exception as e:
        logger.error("monitor_stream_error", error=str(e), traceback=traceback.format_exc())
        yield ErrorEvent(message=str(e), recoverable=False)
