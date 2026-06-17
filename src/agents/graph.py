"""
NormaAI Agent Graph - LangGraph orchestration for regulatory intelligence.

Two graph variants:
- Sync graph: for tests, scripts, CLI (uses call_llm → llm.invoke)
- Async graph: for FastAPI (uses acall_llm → llm.ainvoke - non-blocking)

The async public API (arun_qa, arun_gap_analysis, arun_monitor_check)
uses the async graph with an asyncio.Semaphore to limit concurrency
and prevent thread-pool exhaustion under load.

Business logic lives in:
- sanitization.py: Input sanitization (prompt injection prevention)
- llm.py: LLM helpers (provider abstraction, JSON parsing, retry)
- nodes.py: Agent nodes (sync & async variants)
- resilience.py: Circuit breaker, concurrency limiter
"""

import asyncio
import concurrent.futures
import json
import logging
import threading

from langgraph.graph import END, START, StateGraph

from src.agents.cove.models import CoVeConfig
from src.agents.cove.orchestrator import CoVeOrchestrator
from src.agents.nodes import (
    AgentState,
    async_gap_analyst_node,
    # Local router nodes
    async_local_router_node,
    # Async variants
    async_monitor_agent_node,
    async_qa_bot_node,
    async_simple_response_node,
    complexity_gate_branch,
    confidence_check_node,
    gap_analyst_node,
    monitor_agent_node,
    qa_bot_node,
    retrieve_node,
    route_to_agent,
)
from src.agents.sanitization import sanitize_input, sanitize_profile
from src.agents.snc_node import (
    abstain_response_node,
    async_snc_governance_node,
    snc_governance_node,
    snc_route_to_next,
)
from src.config import get_settings

logger = logging.getLogger(__name__)


# ─── Graph Builders ──────────────────────────────────────────────


def _build_graph(*, use_async_nodes: bool = False):
    """Build the NormaAI agent graph.

    Args:
        use_async_nodes: If True, use async LLM nodes (for FastAPI).
                         If False, use sync nodes (for tests/scripts).

    Flow (local LLM disabled - default):
        START -> retrieve -> [route_to_agent] -> agent_node -> confidence_check -> [cove_gate] -> cove_verification? -> END

    Flow (local LLM enabled):
        START -> local_router -> [complexity_gate] ->
            simple: simple_response -> [cache_gate] -> confidence_check / retrieve
            medium/complex: retrieve -> [route_to_agent] -> agent_node -> confidence_check -> [cove_gate] -> cove_verification? -> END

    CoVe gate: If cove_enabled=True and confidence_score < 0.85, route to cove_verification.
    Otherwise route directly to END.
    """
    settings = get_settings()
    use_local_router = use_async_nodes and settings.local_llm_enabled

    graph = StateGraph(AgentState)

    # Retrieve is always sync (Qdrant client is sync)
    graph.add_node("retrieve", retrieve_node)

    if use_async_nodes:
        graph.add_node("monitor_agent", async_monitor_agent_node)
        graph.add_node("gap_analyst", async_gap_analyst_node)
        graph.add_node("qa_bot", async_qa_bot_node)
    else:
        graph.add_node("monitor_agent", monitor_agent_node)
        graph.add_node("gap_analyst", gap_analyst_node)
        graph.add_node("qa_bot", qa_bot_node)

    graph.add_node("confidence_check", confidence_check_node)

    # SNC Trust Layer - K-sample stochastic governance applied BEFORE
    # confidence_check. Generates K-1 additional samples in parallel,
    # clusters them behaviorally, computes the closed-form trust score,
    # and routes the request three ways:
    #   ADMIT_HIGH/ADMIT_MID -> confidence_check (legacy CoVe gate)
    #   ABSTAIN              -> abstain_response (skip CoVe, return abstention)
    if use_async_nodes:
        graph.add_node("snc_governance", async_snc_governance_node)
    else:
        graph.add_node("snc_governance", snc_governance_node)
    graph.add_node("abstain_response", abstain_response_node)

    # CoVe verification node - calls the full 5-phase anti-hallucination pipeline
    def cove_verification_node(state: AgentState) -> AgentState:
        """Chain-of-Verification node: verify claims and citations.

        Runs the CoVeOrchestrator synchronously for the sync graph path
        (tests/scripts). Collects all SSE events and extracts the final
        CoVe result into state['cove_result'].
        """
        try:
            config = CoVeConfig(enabled=True)
            orchestrator = CoVeOrchestrator(config=config)
            # Collect events synchronously. asyncio.run() raises RuntimeError
            # when an event loop is already running (e.g. sync graph invoked
            # from async test code), so fall back to a dedicated thread with
            # its own loop in that case.
            cove_events = []

            async def _run():
                async for event in orchestrator.run(state, state.get("task_type", "qa")):
                    cove_events.append(event.model_dump() if hasattr(event, "model_dump") else {})

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(_run())
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    pool.submit(asyncio.run, _run()).result()

            # Extract final result from events
            done_events = [e for e in cove_events if e.get("type") == "done"]
            if done_events:
                done = done_events[-1]
                state["cove_result"] = {
                    "status": "completed",
                    "confidence_score": done.get(
                        "confidence_score", state.get("confidence_score", 0.5)
                    ),
                    "cove_applied": done.get("cove_applied", True),
                    "requires_review": done.get("requires_review", False),
                    "events_count": len(cove_events),
                }
                # Update graph-level confidence with CoVe-adjusted value
                state["confidence_score"] = done.get(
                    "confidence_score", state.get("confidence_score", 0.5)
                )
                # Replace the draft with CoVe's verified text (BUG-002).
                _apply_cove_to_result(state, done)
            else:
                state["cove_result"] = {"status": "completed", "events_count": len(cove_events)}

            logger.info("cove_verification_complete", extra={"events": len(cove_events)})
        except Exception as e:
            logger.error(f"CoVe verification failed, continuing with original result: {e}")
            state["cove_result"] = {"status": "error", "error": str(e)}
        return state

    async def async_cove_verification_node(state: AgentState) -> AgentState:
        """Async CoVe verification node for the FastAPI graph path.

        Runs the CoVeOrchestrator natively async, collecting SSE events
        and updating state with verified confidence scores.
        """
        try:
            config = CoVeConfig(enabled=True)
            # Pull shared clients from app_state: indexer (evidence search) and
            # normattiva_client (Italian-law URN validation). Without the latter,
            # URN validation is silently skipped - wire it so the claim holds.
            indexer = None
            normattiva_client = None
            try:
                from src.api.app_state import app_state

                indexer = getattr(app_state, "indexer", None)
                normattiva_client = getattr(app_state, "normattiva_client", None)
            except (ImportError, AttributeError):
                pass

            orchestrator = CoVeOrchestrator(
                indexer=indexer, normattiva_client=normattiva_client, config=config
            )
            cove_events = []
            async for event in orchestrator.run(state, state.get("task_type", "qa")):
                cove_events.append(event.model_dump() if hasattr(event, "model_dump") else {})

            # Extract final result from events
            done_events = [e for e in cove_events if e.get("type") == "done"]
            if done_events:
                done = done_events[-1]
                state["cove_result"] = {
                    "status": "completed",
                    "confidence_score": done.get(
                        "confidence_score", state.get("confidence_score", 0.5)
                    ),
                    "cove_applied": done.get("cove_applied", True),
                    "requires_review": done.get("requires_review", False),
                    "events_count": len(cove_events),
                }
                state["confidence_score"] = done.get(
                    "confidence_score", state.get("confidence_score", 0.5)
                )
                # Replace the draft with CoVe's verified text (BUG-002).
                _apply_cove_to_result(state, done)
            else:
                state["cove_result"] = {"status": "completed", "events_count": len(cove_events)}

            logger.info("async_cove_verification_complete", extra={"events": len(cove_events)})
        except Exception as e:
            logger.error(f"Async CoVe verification failed, continuing with original result: {e}")
            state["cove_result"] = {"status": "error", "error": str(e)}
        return state

    if use_async_nodes:
        graph.add_node("cove_verification", async_cove_verification_node)
    else:
        graph.add_node("cove_verification", cove_verification_node)

    def should_route_to_cove(state: AgentState) -> str:
        """Conditional edge: route to CoVe if enabled and confidence is low."""
        if state.get("cove_enabled") and state.get("confidence_score", 1.0) < 0.85:
            return "cove_verification"
        return END

    if use_local_router:
        # ─── Local router path ────────────────────────────────
        graph.add_node("local_router", async_local_router_node)
        graph.add_node("simple_response", async_simple_response_node)

        graph.add_edge(START, "local_router")
        graph.add_conditional_edges(
            "local_router",
            complexity_gate_branch,
            {"simple_response": "simple_response", "retrieve": "retrieve"},
        )
        # Simple response: if cache hit → result_json is set → confidence_check
        # If cache miss → complexity_tier becomes "medium" → need retrieve
        graph.add_conditional_edges(
            "simple_response",
            lambda state: "confidence_check"
            if state.get("result_json", "{}") != "{}"
            else "retrieve",
            {"confidence_check": "confidence_check", "retrieve": "retrieve"},
        )
    else:
        # ─── Standard path (no local router) ──────────────────
        graph.add_edge(START, "retrieve")

    graph.add_conditional_edges(
        "retrieve",
        route_to_agent,
        {"monitor_agent": "monitor_agent", "gap_analyst": "gap_analyst", "qa_bot": "qa_bot"},
    )
    # Agents now feed into the SNC governance node, which then routes either
    # to confidence_check (admit paths) or to abstain_response (low trust).
    graph.add_edge("monitor_agent", "snc_governance")
    graph.add_edge("gap_analyst", "snc_governance")
    graph.add_edge("qa_bot", "snc_governance")

    graph.add_conditional_edges(
        "snc_governance",
        snc_route_to_next,
        {
            "abstain_response": "abstain_response",
            "confidence_check": "confidence_check",
        },
    )
    graph.add_edge("abstain_response", END)

    # Confidence check → CoVe gate (conditional)
    graph.add_conditional_edges(
        "confidence_check",
        should_route_to_cove,
        {"cove_verification": "cove_verification", END: END},
    )

    # CoVe verification → END
    graph.add_edge("cove_verification", END)

    return graph.compile()


# ─── Thread-Safe Graph Singletons ─────────────────────────────────

_sync_graph_lock = threading.Lock()
_sync_graph_instance = None

_async_graph_lock = threading.Lock()
_async_graph_instance = None


def _get_sync_graph():
    """Get or build the sync graph (for tests/scripts)."""
    global _sync_graph_instance
    if _sync_graph_instance is None:
        with _sync_graph_lock:
            if _sync_graph_instance is None:
                logger.info("Building sync NormaAI agent graph...")
                _sync_graph_instance = _build_graph(use_async_nodes=False)
    return _sync_graph_instance


def _get_async_graph():
    """Get or build the async graph (for FastAPI)."""
    global _async_graph_instance
    if _async_graph_instance is None:
        with _async_graph_lock:
            if _async_graph_instance is None:
                logger.info("Building async NormaAI agent graph...")
                _async_graph_instance = _build_graph(use_async_nodes=True)
    return _async_graph_instance


# ─── Internal Helpers ─────────────────────────────────────────────


def _create_initial_state(
    query: str,
    task_type: str,
    company_profile: dict | None = None,
    cove_enabled: bool = False,
    org_id: str | None = None,
) -> dict:
    return {
        "query": sanitize_input(query),
        "task_type": task_type,
        "org_id": org_id,
        "company_profile": sanitize_profile(company_profile) if company_profile else {},
        "retrieved_chunks": [],
        "result_json": "{}",
        "confidence_score": 0.0,
        "requires_review": False,
        "error": "",
        # Local router fields (populated by async_local_router_node)
        "detected_frameworks": [],
        "complexity_tier": "",
        "extracted_entities": {},
        "router_source": "",
        # Chain-of-Verification fields
        "cove_enabled": cove_enabled,
        "cove_result": {},
    }


def _apply_cove_to_result(state: dict, done: dict) -> None:
    """Write CoVe's verified output back into result_json (BUG-002).

    Without this, the CoVe node only nudged a separate confidence variable and
    the caller still returned the ORIGINAL unverified draft. Now the revised
    text and adjusted confidence/review flag replace the draft in result_json,
    which is what _extract_result returns to the client.
    """
    try:
        result = json.loads(state.get("result_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        return
    if not isinstance(result, dict):
        return
    revised = done.get("revised_text")
    if revised:
        result["answer"] = revised
    if done.get("confidence_score") is not None:
        result["confidence_score"] = done["confidence_score"]
    result["requires_expert_review"] = bool(
        done.get("requires_review", result.get("requires_expert_review", False))
    )
    result["cove_applied"] = True
    state["result_json"] = json.dumps(result)


def _extract_result(state: dict) -> dict:
    result_json = state.get("result_json", "{}")
    try:
        result = json.loads(result_json)
        if isinstance(result, dict):
            return result
        return {"raw_response": str(result), "confidence_score": 0.5}
    except (json.JSONDecodeError, TypeError):
        return {"raw_response": str(result_json), "confidence_score": 0.5}


_ERROR_RESPONSE = {
    "error": "An unexpected error occurred during analysis.",
    "confidence_score": 0.0,
    "requires_expert_review": True,
}


def _run_graph(state: dict) -> dict:
    """Run the sync graph (for tests/scripts)."""
    try:
        if not isinstance(state, dict):
            raise ValueError("State must be a dictionary")
        graph = _get_sync_graph()
        final_state = graph.invoke(state)
        return _extract_result(final_state)
    except ValueError as e:
        logger.error("invalid_graph_input: %s", e)
        return {
            "error": "Invalid input for analysis.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except RuntimeError as e:
        logger.error("graph_runtime_error: %s", e)
        return {
            "error": "Analysis execution failed. Please try again.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except TimeoutError as e:
        logger.error("graph_timeout: %s", e)
        return {
            "error": "Graph execution timed out.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except Exception:
        logger.error("unexpected_graph_error", exc_info=True)
        return {**_ERROR_RESPONSE}


async def _arun_graph(state: dict) -> dict:
    """Run the async graph (for FastAPI - non-blocking).

    Concurrency is bounded PER LLM CALL inside acall_llm (so the SNC/CoVe
    fan-out is capped at the provider), NOT once per request - wrapping the
    whole graph in the same semaphore would both under-count the fan-out and
    risk deadlock once every permit holds a request needing more permits.
    Uses native .ainvoke() on the LangGraph compiled graph.
    """
    try:
        if not isinstance(state, dict):
            raise ValueError("State must be a dictionary")

        graph = _get_async_graph()
        final_state = await graph.ainvoke(state)
        return _extract_result(final_state)

    except ValueError as e:
        logger.error("invalid_graph_input: %s", e)
        return {
            "error": "Invalid input for analysis.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except RuntimeError as e:
        logger.error("graph_runtime_error: %s", e)
        return {
            "error": "Analysis execution failed. Please try again.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except TimeoutError:
        logger.error("graph_async_timeout")
        return {
            "error": "Graph execution timed out.",
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
    except Exception:
        logger.error("unexpected_async_graph_error", exc_info=True)
        return {**_ERROR_RESPONSE}


# ─── Public Sync API (tests/scripts) ─────────────────────────────


def run_qa(query: str, company_profile: dict | None = None, cove_enabled: bool = False) -> dict:
    """Sync Q&A for tests and scripts.

    Args:
        query: The user's question
        company_profile: Optional company context
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
    """
    return _run_graph(
        _create_initial_state(query, "qa", company_profile, cove_enabled=cove_enabled)
    )


def run_gap_analysis(framework: str, company_profile: dict, cove_enabled: bool = False) -> dict:
    """Sync gap analysis for tests and scripts.

    Args:
        framework: EU framework code (e.g., "GDPR", "CSRD")
        company_profile: Company context for assessment
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
    """
    return _run_graph(
        _create_initial_state(framework, "gap_analysis", company_profile, cove_enabled=cove_enabled)
    )


def run_monitor_check(
    regulation_change: str, company_profile: dict, cove_enabled: bool = False
) -> dict:
    """Sync monitor for tests and scripts.

    Args:
        regulation_change: Description of the regulatory change to assess
        company_profile: Company context for impact assessment
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
    """
    return _run_graph(
        _create_initial_state(
            regulation_change, "monitor", company_profile, cove_enabled=cove_enabled
        )
    )


# ─── Public Async API (FastAPI - native async, no to_thread) ─────


async def arun_qa(
    query: str,
    company_profile: dict | None = None,
    cove_enabled: bool = False,
    org_id: str | None = None,
) -> dict:
    """Async Q&A - uses native .ainvoke(), does NOT block the event loop.

    Args:
        query: The user's question
        company_profile: Optional company context
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
        org_id: Tenant scope for retrieval (None => shared regulatory corpus only)
    """
    return await _arun_graph(
        _create_initial_state(
            query, "qa", company_profile, cove_enabled=cove_enabled, org_id=org_id
        )
    )


async def arun_gap_analysis(
    framework: str,
    company_profile: dict,
    cove_enabled: bool = False,
    org_id: str | None = None,
) -> dict:
    """Async gap analysis - uses native .ainvoke(), does NOT block the event loop.

    Args:
        framework: EU framework code (e.g., "GDPR", "CSRD")
        company_profile: Company context for assessment
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
        org_id: Tenant scope for retrieval (None => shared regulatory corpus only)
    """
    return await _arun_graph(
        _create_initial_state(
            framework,
            "gap_analysis",
            company_profile,
            cove_enabled=cove_enabled,
            org_id=org_id,
        )
    )


async def arun_monitor_check(
    regulation_change: str,
    company_profile: dict,
    cove_enabled: bool = False,
    org_id: str | None = None,
) -> dict:
    """Async monitor - uses native .ainvoke(), does NOT block the event loop.

    Args:
        regulation_change: Description of the regulatory change to assess
        company_profile: Company context for impact assessment
        cove_enabled: If True, enable Chain-of-Verification verification for low-confidence results
        org_id: Tenant scope for retrieval (None => shared regulatory corpus only)
    """
    return await _arun_graph(
        _create_initial_state(
            regulation_change,
            "monitor",
            company_profile,
            cove_enabled=cove_enabled,
            org_id=org_id,
        )
    )
