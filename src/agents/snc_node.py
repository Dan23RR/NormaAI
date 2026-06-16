"""LangGraph node that wraps the SNC governance layer.

Inserts after the agent_node (monitor/gap/qa) and before confidence_check.
Reads the draft response from state['result_json'], generates K-1 additional
samples, and writes:

  state['snc_decision']     — full SNCDecision dict
  state['snc_action']       — ADMIT_HIGH | ADMIT_MID | ABSTAIN
  state['confidence_score'] — overwritten with SNC trust score
  state['result_json']      — overwritten with modal cluster representative
  state['requires_expert_review'] — True if action == ABSTAIN
  state['snc_audit']        — serialized audit blob for compliance logging

The downstream graph routing (existing should_route_to_cove) uses the new
trust score automatically. We add a stricter SNC routing if the action is
ABSTAIN (skip CoVe, return immediately).
"""

from __future__ import annotations

import json
import logging

from src.agents.snc_layer import (
    SNCConfig,
    SNCDecision,
    serialize_decision,
    snc_governance,
)
from src.config import get_settings

logger = logging.getLogger(__name__)


def _build_system_prompt_for_resample(state: dict) -> str:
    """Reconstruct the system prompt used by the agent node, for K-1 resampling.

    The agent nodes (monitor_agent_node, gap_analyst_node, qa_bot_node)
    each load their prompt from prompts/<task>.txt; we reuse the same
    prompt to keep samples conditioned identically.
    """
    from pathlib import Path

    task = state.get("task_type", "qa")
    prompt_name = {
        "monitor": "regulatory_monitor",
        "gap_analysis": "gap_analyst",
        "qa": "qa_bot",
    }.get(task, "qa_bot")

    prompts_dir = Path(__file__).parent.parent / "prompts"
    path = prompts_dir / f"{prompt_name}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("snc_prompt_not_found", extra={"path": str(path)})
    return ""


def _build_user_message(state: dict) -> str:
    """Reconstruct the user message used by the agent node.

    Combines the query, the company profile, and the retrieved chunks
    in the same format the agent_node expects.
    """
    from src.agents.llm import format_retrieved_chunks

    query = state.get("query", "")
    profile = state.get("company_profile") or {}
    chunks = state.get("retrieved_chunks") or []
    parts = [f"User query: {query}"]
    if profile:
        parts.append(f"Company profile: {json.dumps(profile, ensure_ascii=False)}")
    if chunks:
        parts.append("Regulatory context:")
        parts.append(format_retrieved_chunks(chunks))
    return "\n\n".join(parts)


def _config_from_settings() -> SNCConfig:
    """Read SNC configuration from app settings (with sane defaults)."""
    s = get_settings()
    return SNCConfig(
        k=getattr(s, "snc_k", 3),
        temperature=getattr(s, "snc_temperature", 0.7),
        theta_high=getattr(s, "snc_theta_high", 0.85),
        theta_low=getattr(s, "snc_theta_low", 0.50),
        enabled=getattr(s, "snc_enabled", True),
    )


# ─── Async LangGraph node ────────────────────────────────────────


async def async_snc_governance_node(state: dict) -> dict:
    """Async LangGraph node that applies SNC governance to the agent draft.

    Reads state['result_json'] (the agent's first draft), generates K-1
    additional samples concurrently, computes the trust score, and writes
    the decision back to state. Failure is non-fatal: on any exception
    we fall through with the original draft and log a warning.
    """
    cfg = _config_from_settings()

    if not cfg.enabled:
        # SNC layer disabled: pass through without modification.
        return state

    # Parse the draft from state.
    draft_json = state.get("result_json", "{}")
    try:
        initial = json.loads(draft_json) if isinstance(draft_json, str) else draft_json
        if not isinstance(initial, dict):
            initial = {"answer": str(draft_json), "citations": []}
    except (json.JSONDecodeError, TypeError):
        initial = {"answer": str(draft_json), "citations": []}

    # If the draft already has an error, don't try to resample.
    if "error" in initial:
        logger.info("snc_skipped_due_to_draft_error")
        return state

    system_prompt = _build_system_prompt_for_resample(state)
    user_message = _build_user_message(state)

    if not system_prompt or not user_message:
        logger.warning("snc_skipped_missing_prompt_or_message")
        return state

    try:
        decision: SNCDecision = await snc_governance(
            initial_response=initial,
            system_prompt=system_prompt,
            user_message=user_message,
            config=cfg,
        )
    except Exception as e:
        logger.error("snc_governance_failed", extra={"error": str(e)})
        return state

    # Write decision back to state.
    state["snc_decision"] = serialize_decision(decision)
    state["snc_action"] = decision.action
    state["confidence_score"] = decision.trust  # overwrite legacy confidence
    state["result_json"] = json.dumps(decision.modal_answer, ensure_ascii=False)
    state["requires_expert_review"] = decision.action == "ABSTAIN"
    state["snc_audit"] = state["snc_decision"]

    logger.info(
        "snc_node_complete",
        extra={
            "action": decision.action,
            "trust": round(decision.trust, 4),
            "n_clusters": decision.n_clusters,
        },
    )
    return state


# ─── Sync LangGraph node (for tests/scripts) ─────────────────────


def snc_governance_node(state: dict) -> dict:
    """Sync wrapper of async_snc_governance_node (tests/CLI).

    Uses asyncio.run() to drive the async path. Not for use inside a
    running event loop (FastAPI uses async_snc_governance_node directly).
    """
    import asyncio

    try:
        return asyncio.run(async_snc_governance_node(state))
    except RuntimeError as e:
        # Already in event loop: fall back to pass-through with warning.
        logger.warning("snc_sync_node_in_event_loop", extra={"error": str(e)})
        return state


# ─── Routing helper for graph edges ──────────────────────────────


def snc_route_to_next(state: dict) -> str:
    """Conditional edge: route based on SNC action.

    Returns one of:
      - "abstain_response": skip CoVe, return abstention immediately.
      - "confidence_check": existing path (CoVe gate decides).

    The high-trust case (ADMIT_HIGH) is handled inside confidence_check
    because the legacy confidence_check threshold is the same as theta_high.
    """
    action = state.get("snc_action")
    if action == "ABSTAIN":
        return "abstain_response"
    return "confidence_check"


def abstain_response_node(state: dict) -> dict:
    """Terminal node for ABSTAIN: return a structured abstention payload.

    The downstream serializer expects state['result_json']; we overwrite
    it with a JSON document that explicitly signals expert review.
    """
    abstention_payload = {
        "answer": (
            "Non posso fornire una risposta sufficientemente affidabile su questa "
            "domanda. La verifica automatica ha rilevato incertezza significativa "
            "tra i candidati di risposta generati. Si raccomanda revisione esperta."
        ),
        "citations": [],
        "confidence_score": state.get("confidence_score", 0.0),
        "requires_expert_review": True,
        "abstention_reason": "snc_low_trust",
        "snc_audit": state.get("snc_audit", {}),
    }
    state["result_json"] = json.dumps(abstention_payload, ensure_ascii=False)
    state["requires_expert_review"] = True
    return state
