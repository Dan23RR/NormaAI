"""Tests for src/agents/graph.py - LangGraph assembly + the run_*/arun_* API.

This module is NOT SQL-DB-backed. Everything external (LLM, Qdrant, the CoVe
orchestrator, the SNC trust layer) is mocked so the compiled LangGraph runs
deterministically. We assert:

  - GRAPH STRUCTURE: the sync and async graphs register the expected nodes,
    wire the conditional edges (route_to_agent, snc_route_to_next, the CoVe
    gate), and both compile.
  - SINGLETONS: _get_sync_graph / _get_async_graph build once and are cached,
    and the build dispatch (sync vs async node variants) is correct.
  - INITIAL STATE: _create_initial_state sanitizes and shapes the state dict
    (incl. org_id, cove_enabled, task_type) exactly as the run_* wrappers feed
    it into the graph.
  - PURE HELPERS: _extract_result, _apply_cove_to_result.
  - THE WRAPPERS: run_qa/run_gap_analysis/run_monitor_check and the async
    arun_* trio, end-to-end through the REAL compiled graph with every heavy
    node (retrieve / agent / snc / cove) patched, returning a result dict with
    the expected keys including org_id propagation into retrieve.
  - ERROR HANDLING: _run_graph / _arun_graph translate bad input and graph
    failures into the structured error envelope.

Nothing here touches a real LLM / Qdrant / network / DB.
"""

import json
from contextlib import contextmanager
from unittest.mock import patch

import src.agents.graph as graph_mod
from src.agents.graph import (
    _ERROR_RESPONSE,
    _apply_cove_to_result,
    _create_initial_state,
    _extract_result,
)

# ─────────────────────────────────────────────────────────────────────────────
# Test doubles for the heavy nodes
# ─────────────────────────────────────────────────────────────────────────────


def _fake_retrieve_factory(capture: dict | None = None):
    """Return a retrieve_node replacement that records the state it saw.

    The real node hits Qdrant; this one returns a fixed chunk list and, if a
    capture dict is supplied, records org_id / query so tests can assert
    propagation through _create_initial_state -> graph -> retrieve.
    """

    def _fake_retrieve(state):
        if capture is not None:
            capture["org_id"] = state.get("org_id")
            capture["query"] = state.get("query")
            capture["task_type"] = state.get("task_type")
        return {"retrieved_chunks": [{"framework": "GDPR", "text": "grounding chunk"}]}

    return _fake_retrieve


def _fake_agent_factory(confidence: float = 0.95, answer: str = "Mocked answer"):
    """Return an agent-node replacement that writes a deterministic result_json."""

    def _fake_agent(state):
        result = {
            "answer": answer,
            "confidence_score": confidence,
            "citations": [],
            "requires_expert_review": confidence < 0.8,
        }
        return {
            "result_json": json.dumps(result),
            "confidence_score": confidence,
            "requires_review": confidence < 0.8,
        }

    return _fake_agent


def _fake_snc_factory(action: str = "ADMIT_HIGH"):
    """SNC node replacement: tag the action, pass the draft through untouched."""

    def _fake_snc(state):
        state["snc_action"] = action
        return state

    return _fake_snc


class _FakeCoVeEvent:
    """Minimal stand-in for an SSEEvent exposing model_dump()."""

    def __init__(self, payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeCoVeOrchestrator:
    """Drop-in for CoVeOrchestrator: run() yields one 'done' SSE event.

    The graph's cove node reads event.model_dump() and extracts the last event
    whose type == 'done', so a single done event is enough to drive the
    confidence-rewrite path deterministically.
    """

    done_payload = {
        "type": "done",
        "confidence_score": 0.42,
        "cove_applied": True,
        "requires_review": True,
        "revised_text": "CoVe-revised answer",
    }

    def __init__(self, *args, **kwargs):
        pass

    async def run(self, state, task_type):
        yield _FakeCoVeEvent({"type": "phase", "message": "verifying"})
        yield _FakeCoVeEvent(dict(self.done_payload))


@contextmanager
def _patched_graph(
    *,
    confidence: float = 0.95,
    snc_action: str = "ADMIT_HIGH",
    retrieve_capture: dict | None = None,
    fake_cove: bool = False,
):
    """Patch heavy nodes on the graph module and force a fresh singleton build.

    _build_graph captures the node callables by their module-level names at
    add_node() time, so patching them on graph_mod + resetting the cached
    singletons makes the rebuilt graph use the doubles. The conditional-edge
    routers (route_to_agent, snc_route_to_next, should_route_to_cove) are left
    REAL so routing behavior is exercised genuinely.
    """
    retrieve = _fake_retrieve_factory(retrieve_capture)
    agent = _fake_agent_factory(confidence=confidence)
    snc = _fake_snc_factory(snc_action)

    patches = [
        patch.object(graph_mod, "retrieve_node", retrieve),
        patch.object(graph_mod, "qa_bot_node", agent),
        patch.object(graph_mod, "gap_analyst_node", agent),
        patch.object(graph_mod, "monitor_agent_node", agent),
        patch.object(graph_mod, "async_qa_bot_node", agent),
        patch.object(graph_mod, "async_gap_analyst_node", agent),
        patch.object(graph_mod, "async_monitor_agent_node", agent),
        patch.object(graph_mod, "snc_governance_node", snc),
        patch.object(graph_mod, "async_snc_governance_node", snc),
    ]
    if fake_cove:
        patches.append(patch.object(graph_mod, "CoVeOrchestrator", _FakeCoVeOrchestrator))

    prev_sync = graph_mod._sync_graph_instance
    prev_async = graph_mod._async_graph_instance
    for p in patches:
        p.start()
    # Force rebuild AFTER the patches are live.
    graph_mod._sync_graph_instance = None
    graph_mod._async_graph_instance = None
    try:
        yield
    finally:
        for p in patches:
            p.stop()
        # Restore prior singletons so we don't leak doubles into other tests.
        graph_mod._sync_graph_instance = prev_sync
        graph_mod._async_graph_instance = prev_async


# ─────────────────────────────────────────────────────────────────────────────
# Graph structure
# ─────────────────────────────────────────────────────────────────────────────

_EXPECTED_NODES = {
    "retrieve",
    "monitor_agent",
    "gap_analyst",
    "qa_bot",
    "snc_governance",
    "abstain_response",
    "confidence_check",
    "cove_verification",
}


class TestGraphStructure:
    def test_sync_graph_compiles(self):
        compiled = graph_mod._build_graph(use_async_nodes=False)
        assert compiled is not None
        # Has the LangGraph invoke surface.
        assert hasattr(compiled, "invoke")
        assert hasattr(compiled, "ainvoke")

    def test_async_graph_compiles(self):
        compiled = graph_mod._build_graph(use_async_nodes=True)
        assert compiled is not None
        assert hasattr(compiled, "ainvoke")

    def test_sync_and_async_register_same_node_set(self):
        sync_nodes = set(graph_mod._build_graph(use_async_nodes=False).get_graph().nodes.keys())
        async_nodes = set(graph_mod._build_graph(use_async_nodes=True).get_graph().nodes.keys())
        # Same logical node set regardless of sync/async variant.
        assert sync_nodes >= _EXPECTED_NODES
        assert async_nodes >= _EXPECTED_NODES
        assert sync_nodes == async_nodes

    def test_start_edge_goes_to_retrieve_in_standard_path(self):
        # local_llm_enabled defaults to False -> START wires directly to retrieve
        # (no local_router / simple_response nodes present).
        compiled = graph_mod._build_graph(use_async_nodes=False)
        nodes = set(compiled.get_graph().nodes.keys())
        assert "local_router" not in nodes
        assert "simple_response" not in nodes
        edges = compiled.get_graph().edges
        start_targets = {e.target for e in edges if e.source == "__start__"}
        assert start_targets == {"retrieve"}

    def test_retrieve_has_three_conditional_agent_edges(self):
        edges = graph_mod._build_graph(use_async_nodes=False).get_graph().edges
        retrieve_targets = {e.target for e in edges if e.source == "retrieve"}
        assert retrieve_targets == {"monitor_agent", "gap_analyst", "qa_bot"}
        # And they are conditional, not unconditional.
        assert all(getattr(e, "conditional", False) for e in edges if e.source == "retrieve")

    def test_all_agents_feed_snc_governance(self):
        edges = graph_mod._build_graph(use_async_nodes=False).get_graph().edges
        for agent in ("monitor_agent", "gap_analyst", "qa_bot"):
            targets = {e.target for e in edges if e.source == agent}
            assert targets == {"snc_governance"}, agent

    def test_snc_governance_branches_to_abstain_or_confidence(self):
        edges = graph_mod._build_graph(use_async_nodes=False).get_graph().edges
        targets = {e.target for e in edges if e.source == "snc_governance"}
        assert targets == {"abstain_response", "confidence_check"}

    def test_confidence_check_has_cove_gate(self):
        edges = graph_mod._build_graph(use_async_nodes=False).get_graph().edges
        targets = {e.target for e in edges if e.source == "confidence_check"}
        # Conditional gate: low-confidence + cove_enabled -> cove_verification,
        # otherwise straight to END.
        assert targets == {"cove_verification", "__end__"}

    def test_terminal_edges_reach_end(self):
        edges = graph_mod._build_graph(use_async_nodes=False).get_graph().edges
        assert {e.target for e in edges if e.source == "abstain_response"} == {"__end__"}
        assert {e.target for e in edges if e.source == "cove_verification"} == {"__end__"}


# ─────────────────────────────────────────────────────────────────────────────
# Singletons / build dispatch
# ─────────────────────────────────────────────────────────────────────────────


class TestGraphSingletons:
    def test_get_sync_graph_is_cached(self):
        graph_mod._sync_graph_instance = None
        try:
            g1 = graph_mod._get_sync_graph()
            g2 = graph_mod._get_sync_graph()
            assert g1 is g2
        finally:
            graph_mod._sync_graph_instance = None

    def test_get_async_graph_is_cached(self):
        graph_mod._async_graph_instance = None
        try:
            g1 = graph_mod._get_async_graph()
            g2 = graph_mod._get_async_graph()
            assert g1 is g2
        finally:
            graph_mod._async_graph_instance = None

    def test_sync_and_async_singletons_are_distinct(self):
        graph_mod._sync_graph_instance = None
        graph_mod._async_graph_instance = None
        try:
            assert graph_mod._get_sync_graph() is not graph_mod._get_async_graph()
        finally:
            graph_mod._sync_graph_instance = None
            graph_mod._async_graph_instance = None

    def test_build_dispatches_to_async_node_variants(self):
        # use_async_nodes=True must register the async agent/snc callables.
        with patch.object(graph_mod, "StateGraph") as mock_sg:
            instance = mock_sg.return_value
            instance.compile.return_value = "COMPILED"
            graph_mod._build_graph(use_async_nodes=True)
            registered = {c.args[0]: c.args[1] for c in instance.add_node.call_args_list}
        assert registered["qa_bot"] is graph_mod.async_qa_bot_node
        assert registered["gap_analyst"] is graph_mod.async_gap_analyst_node
        assert registered["monitor_agent"] is graph_mod.async_monitor_agent_node
        assert registered["snc_governance"] is graph_mod.async_snc_governance_node

    def test_build_dispatches_to_sync_node_variants(self):
        with patch.object(graph_mod, "StateGraph") as mock_sg:
            instance = mock_sg.return_value
            instance.compile.return_value = "COMPILED"
            graph_mod._build_graph(use_async_nodes=False)
            registered = {c.args[0]: c.args[1] for c in instance.add_node.call_args_list}
        assert registered["qa_bot"] is graph_mod.qa_bot_node
        assert registered["gap_analyst"] is graph_mod.gap_analyst_node
        assert registered["monitor_agent"] is graph_mod.monitor_agent_node
        assert registered["snc_governance"] is graph_mod.snc_governance_node
        # retrieve is always the sync node (Qdrant client is sync).
        assert registered["retrieve"] is graph_mod.retrieve_node


# ─────────────────────────────────────────────────────────────────────────────
# _create_initial_state
# ─────────────────────────────────────────────────────────────────────────────


class TestCreateInitialState:
    def test_shapes_full_state_dict(self):
        state = _create_initial_state("What is GDPR?", "qa")
        # Required keys the downstream nodes/serializer rely on.
        for key in (
            "query",
            "task_type",
            "org_id",
            "company_profile",
            "retrieved_chunks",
            "result_json",
            "confidence_score",
            "requires_review",
            "cove_enabled",
            "cove_result",
        ):
            assert key in state
        assert state["task_type"] == "qa"
        assert state["result_json"] == "{}"
        assert state["confidence_score"] == 0.0
        assert state["requires_review"] is False
        assert state["retrieved_chunks"] == []

    def test_normal_query_passes_through_sanitizer(self):
        state = _create_initial_state("What are CSRD requirements?", "qa")
        assert state["query"] == "What are CSRD requirements?"

    def test_org_id_and_cove_flag_propagate(self):
        state = _create_initial_state("q", "qa", cove_enabled=True, org_id="org-123")
        assert state["org_id"] == "org-123"
        assert state["cove_enabled"] is True

    def test_defaults_org_none_and_cove_false(self):
        state = _create_initial_state("q", "qa")
        assert state["org_id"] is None
        assert state["cove_enabled"] is False

    def test_none_profile_becomes_empty_dict(self):
        state = _create_initial_state("q", "qa", company_profile=None)
        assert state["company_profile"] == {}

    def test_profile_is_sanitized_and_preserved(self):
        profile = {"name": "Acme Srl", "sector": "Manufacturing"}
        state = _create_initial_state("q", "gap_analysis", company_profile=profile)
        assert state["company_profile"]["name"] == "Acme Srl"
        assert state["company_profile"]["sector"] == "Manufacturing"


# ─────────────────────────────────────────────────────────────────────────────
# _extract_result
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractResult:
    def test_parses_dict_json(self):
        state = {"result_json": json.dumps({"answer": "A", "confidence_score": 0.9})}
        out = _extract_result(state)
        assert out == {"answer": "A", "confidence_score": 0.9}

    def test_non_dict_json_wrapped(self):
        # A JSON array is valid JSON but not a dict -> wrapped as raw_response.
        state = {"result_json": json.dumps([1, 2, 3])}
        out = _extract_result(state)
        assert out["raw_response"] == "[1, 2, 3]"
        assert out["confidence_score"] == 0.5

    def test_malformed_json_wrapped(self):
        state = {"result_json": "not json {{{"}
        out = _extract_result(state)
        assert out["raw_response"] == "not json {{{"
        assert out["confidence_score"] == 0.5

    def test_missing_result_json_defaults_to_empty_dict(self):
        assert _extract_result({}) == {}


# ─────────────────────────────────────────────────────────────────────────────
# _apply_cove_to_result
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyCoveToResult:
    def test_revised_text_replaces_answer(self):
        state = {"result_json": json.dumps({"answer": "draft", "confidence_score": 0.5})}
        done = {"revised_text": "verified", "confidence_score": 0.42, "requires_review": True}
        _apply_cove_to_result(state, done)
        result = json.loads(state["result_json"])
        assert result["answer"] == "verified"
        assert result["confidence_score"] == 0.42
        assert result["requires_expert_review"] is True
        assert result["cove_applied"] is True

    def test_no_revised_text_keeps_answer(self):
        state = {"result_json": json.dumps({"answer": "draft"})}
        done = {"confidence_score": 0.7}
        _apply_cove_to_result(state, done)
        result = json.loads(state["result_json"])
        assert result["answer"] == "draft"
        assert result["cove_applied"] is True

    def test_malformed_result_json_is_noop(self):
        state = {"result_json": "not json"}
        _apply_cove_to_result(state, {"revised_text": "x"})
        # Left untouched on parse failure.
        assert state["result_json"] == "not json"

    def test_non_dict_json_is_noop(self):
        state = {"result_json": json.dumps([1, 2])}
        _apply_cove_to_result(state, {"revised_text": "x"})
        assert state["result_json"] == json.dumps([1, 2])


# ─────────────────────────────────────────────────────────────────────────────
# Sync wrappers end-to-end through the compiled graph
# ─────────────────────────────────────────────────────────────────────────────


class TestSyncWrappers:
    def test_run_qa_returns_result_dict(self):
        with _patched_graph(confidence=0.95):
            out = graph_mod.run_qa("What is GDPR?")
        assert out["answer"] == "Mocked answer"
        assert out["confidence_score"] == 0.95
        assert "citations" in out

    def test_run_gap_analysis_routes_through_gap_node(self):
        # route_to_agent maps task_type 'gap_analysis' -> gap_analyst; both
        # agent doubles share output so we assert the wrapper completes.
        with _patched_graph(confidence=0.9):
            out = graph_mod.run_gap_analysis("CSRD", {"name": "Acme"})
        assert out["answer"] == "Mocked answer"
        assert out["confidence_score"] == 0.9

    def test_run_monitor_check_routes_through_monitor_node(self):
        with _patched_graph(confidence=0.88):
            out = graph_mod.run_monitor_check("New DORA RTS", {"name": "Acme"})
        assert out["answer"] == "Mocked answer"
        assert out["confidence_score"] == 0.88

    def test_run_qa_passes_query_into_retrieve(self):
        cap = {}
        with _patched_graph(retrieve_capture=cap):
            graph_mod.run_qa("Spiega il GDPR")
        assert cap["query"] == "Spiega il GDPR"
        assert cap["task_type"] == "qa"

    def test_abstain_path_returns_abstention_payload(self):
        # SNC action ABSTAIN routes to abstain_response -> END (skips CoVe).
        with _patched_graph(snc_action="ABSTAIN"):
            out = graph_mod.run_qa("ambiguous question")
        assert out["requires_expert_review"] is True
        assert out["abstention_reason"] == "snc_low_trust"
        assert out["citations"] == []


# ─────────────────────────────────────────────────────────────────────────────
# Async wrappers end-to-end through the compiled async graph
# ─────────────────────────────────────────────────────────────────────────────


class TestAsyncWrappers:
    async def test_arun_qa_returns_result_dict(self):
        with _patched_graph(confidence=0.95):
            out = await graph_mod.arun_qa("What is GDPR?")
        assert out["answer"] == "Mocked answer"
        assert out["confidence_score"] == 0.95

    async def test_arun_qa_propagates_org_id_into_retrieve(self):
        cap = {}
        with _patched_graph(retrieve_capture=cap):
            await graph_mod.arun_qa("q", org_id="tenant-42")
        assert cap["org_id"] == "tenant-42"

    async def test_arun_qa_default_org_id_is_none(self):
        cap = {}
        with _patched_graph(retrieve_capture=cap):
            await graph_mod.arun_qa("q")
        assert cap["org_id"] is None

    async def test_arun_gap_analysis_completes(self):
        cap = {}
        with _patched_graph(retrieve_capture=cap, confidence=0.9):
            out = await graph_mod.arun_gap_analysis("CSRD", {"name": "Acme"}, org_id="t1")
        assert out["confidence_score"] == 0.9
        assert cap["task_type"] == "gap_analysis"
        assert cap["org_id"] == "t1"

    async def test_arun_monitor_check_completes(self):
        cap = {}
        with _patched_graph(retrieve_capture=cap, confidence=0.85):
            out = await graph_mod.arun_monitor_check("DORA change", {"name": "Acme"}, org_id="t2")
        assert out["answer"] == "Mocked answer"
        assert cap["task_type"] == "monitor"
        assert cap["org_id"] == "t2"

    async def test_arun_abstain_path(self):
        with _patched_graph(snc_action="ABSTAIN"):
            out = await graph_mod.arun_qa("ambiguous")
        assert out["requires_expert_review"] is True
        assert out["abstention_reason"] == "snc_low_trust"


# ─────────────────────────────────────────────────────────────────────────────
# CoVe gate: low confidence + cove_enabled -> cove_verification rewrites result
# ─────────────────────────────────────────────────────────────────────────────


class TestCoVeGate:
    def test_cove_gate_rewrites_result_when_enabled_and_low_confidence(self):
        # confidence 0.5 < 0.85 and cove_enabled=True -> should_route_to_cove
        # routes to cove_verification, which (with the fake orchestrator) emits
        # a done event whose revised_text replaces the answer.
        with _patched_graph(confidence=0.5, fake_cove=True):
            out = graph_mod.run_qa("low-confidence query", cove_enabled=True)
        assert out["answer"] == "CoVe-revised answer"
        assert out["confidence_score"] == 0.42
        assert out["cove_applied"] is True
        assert out["requires_expert_review"] is True

    def test_cove_gate_skipped_when_disabled(self):
        # cove_enabled defaults to False -> straight to END, no rewrite even at
        # low confidence. The fake orchestrator must NOT run.
        with _patched_graph(confidence=0.5, fake_cove=True):
            out = graph_mod.run_qa("low-confidence query", cove_enabled=False)
        assert out["answer"] == "Mocked answer"
        assert "cove_applied" not in out

    def test_cove_gate_skipped_when_confidence_high(self):
        # High confidence (>= 0.85) bypasses CoVe even when enabled.
        with _patched_graph(confidence=0.95, fake_cove=True):
            out = graph_mod.run_qa("confident query", cove_enabled=True)
        assert out["answer"] == "Mocked answer"
        assert "cove_applied" not in out

    async def test_async_cove_gate_rewrites_result(self):
        with _patched_graph(confidence=0.5, fake_cove=True):
            out = await graph_mod.arun_qa("low-confidence query", cove_enabled=True)
        assert out["answer"] == "CoVe-revised answer"
        assert out["confidence_score"] == 0.42


# ─────────────────────────────────────────────────────────────────────────────
# Error handling in _run_graph / _arun_graph
# ─────────────────────────────────────────────────────────────────────────────


class TestErrorHandling:
    def test_run_graph_rejects_non_dict_state(self):
        out = graph_mod._run_graph("not a dict")
        assert out["error"] == "Invalid input for analysis."
        assert out["confidence_score"] == 0.0
        assert out["requires_expert_review"] is True

    def test_run_graph_handles_unexpected_exception(self):
        # A graph whose invoke raises a generic Exception -> _ERROR_RESPONSE.
        class Boom:
            def invoke(self, state):
                raise KeyError("boom")

        with patch.object(graph_mod, "_get_sync_graph", return_value=Boom()):
            out = graph_mod._run_graph({"query": "x"})
        assert out == _ERROR_RESPONSE
        assert out["requires_expert_review"] is True

    def test_run_graph_handles_runtime_error(self):
        class Boom:
            def invoke(self, state):
                raise RuntimeError("kaboom")

        with patch.object(graph_mod, "_get_sync_graph", return_value=Boom()):
            out = graph_mod._run_graph({"query": "x"})
        assert out["error"] == "Analysis execution failed. Please try again."

    async def test_arun_graph_rejects_non_dict_state(self):
        out = await graph_mod._arun_graph("not a dict")
        assert out["error"] == "Invalid input for analysis."

    async def test_arun_graph_handles_unexpected_exception(self):
        class Boom:
            async def ainvoke(self, state):
                raise KeyError("boom")

        with patch.object(graph_mod, "_get_async_graph", return_value=Boom()):
            out = await graph_mod._arun_graph({"query": "x"})
        assert out == _ERROR_RESPONSE

    async def test_arun_graph_handles_runtime_error(self):
        class Boom:
            async def ainvoke(self, state):
                raise RuntimeError("kaboom")

        with patch.object(graph_mod, "_get_async_graph", return_value=Boom()):
            out = await graph_mod._arun_graph({"query": "x"})
        assert out["error"] == "Analysis execution failed. Please try again."
