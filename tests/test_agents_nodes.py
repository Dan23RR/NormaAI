"""Tests for the LangGraph node functions in src/agents/nodes.py.

Focus: each node's *pure* transformation of the AgentState dict, with all
external dependencies mocked (LLM via call_llm/acall_llm, retrieval via the
indexer's hybrid_search). No real network / LLM / Qdrant / DB is touched.

Complements tests/test_agents.py (route_to_agent, json/confidence/chunk helpers)
and tests/test_local_router.py (complexity_gate_branch, aroute_query) without
duplicating them. Here we cover:

  - retrieve_node: empty-query guard, single/multi-framework search dispatch,
    profile-frameworks fallback, org_id propagation, exception handling
  - the grounding guard (_apply_grounding_guard) and _pack_llm_result
  - the prompt builders (_build_monitor_prompt / _build_gap_prompt /
    _build_qa_prompt) including the injection guard prefix
  - sync agent nodes (monitor/gap/qa) wired to a mocked call_llm
  - async agent nodes wired to a mocked acall_llm
  - confidence_check_node, async_local_router_node, async_simple_response_node
  - _load_prompt (real prompts dir resolves correctly) + detect_frameworks_in_query
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import nodes
from src.agents.nodes import (
    _INJECTION_GUARD,
    _apply_grounding_guard,
    _build_gap_prompt,
    _build_monitor_prompt,
    _build_qa_prompt,
    _load_prompt,
    _pack_llm_result,
    async_gap_analyst_node,
    async_local_router_node,
    async_monitor_agent_node,
    async_qa_bot_node,
    async_simple_response_node,
    confidence_check_node,
    detect_frameworks_in_query,
    gap_analyst_node,
    monitor_agent_node,
    qa_bot_node,
    retrieve_node,
)

# ─── Helpers ──────────────────────────────────────────────────────


def _indexer_returning(results):
    """Build a mock indexer whose hybrid_search returns `results`."""
    indexer = MagicMock()
    indexer.hybrid_search.return_value = results
    return indexer


# ─── detect_frameworks_in_query ───────────────────────────────────


class TestDetectFrameworks:
    def test_detects_single_english(self):
        assert detect_frameworks_in_query("Tell me about the AI Act") == ["AI_ACT"]

    def test_detects_italian_keyword(self):
        # "protezione dei dati" -> GDPR (Italian keyword path)
        assert "GDPR" in detect_frameworks_in_query("Parlami della protezione dei dati personali")

    def test_detects_multiple(self):
        out = detect_frameworks_in_query("How does DORA interact with NIS2?")
        assert "DORA" in out and "NIS2" in out

    def test_no_match_returns_empty(self):
        assert detect_frameworks_in_query("What is the weather today?") == []

    def test_case_insensitive(self):
        assert detect_frameworks_in_query("CSRD AND csrd") == ["CSRD"]


# ─── _load_prompt (real prompts dir) ──────────────────────────────


class TestLoadPrompt:
    def test_loads_existing_prompt(self):
        # nodes.py at src/agents/ resolves 3 parents up to the repo-root prompts/.
        text = _load_prompt("qa_bot")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_missing_prompt_raises(self):
        with pytest.raises(FileNotFoundError):
            _load_prompt("definitely_not_a_real_prompt_xyz")


# ─── retrieve_node ────────────────────────────────────────────────


class TestRetrieveNode:
    def test_empty_query_short_circuits(self):
        out = retrieve_node({"query": ""})
        assert out["retrieved_chunks"] == []
        assert out["error"] == "No query provided"

    def test_single_framework_uses_filter(self):
        chunks = [{"id": "1", "framework": "CSRD", "text": "x", "score": 0.9}]
        indexer = _indexer_returning(chunks)
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "What does CSRD require?"})
        assert out["retrieved_chunks"] == chunks
        # detected framework -> single search with that framework_filter
        indexer.hybrid_search.assert_called_once()
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "CSRD"
        assert kwargs["limit"] == 15

    def test_no_framework_detected_passes_none_filter(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "Tell me something general"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] is None

    def test_org_id_propagated_to_search(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "CSRD requirements", "org_id": "org-123"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["org_id"] == "org-123"

    def test_org_id_defaults_to_none(self):
        indexer = _indexer_returning([])
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node({"query": "CSRD requirements"})
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["org_id"] is None

    def test_profile_single_framework_fallback(self):
        # No framework detected in query, but profile lists exactly one ->
        # that one is used as the filter.
        indexer = _indexer_returning([])
        state = {
            "query": "Generic question without keywords",
            "company_profile": {"applicable_frameworks": ["DORA"]},
        }
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node(state)
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "DORA"

    def test_multi_framework_dedups_and_sorts(self):
        # Two detected frameworks -> per-framework searches, dedup by id,
        # results sorted by descending score.
        def per_fw(query, limit, framework_filter, org_id):
            if framework_filter == "DORA":
                return [
                    {"id": "a", "score": 0.4},
                    {"id": "shared", "score": 0.5},
                ]
            return [
                {"id": "b", "score": 0.9},
                {"id": "shared", "score": 0.99},  # duplicate id, dropped
            ]

        indexer = MagicMock()
        indexer.hybrid_search.side_effect = per_fw
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "How does DORA relate to NIS2?"})

        ids = [c["id"] for c in out["retrieved_chunks"]]
        # 'shared' appears once (dedup); first-seen kept.
        assert ids.count("shared") == 1
        # Sorted by score descending.
        scores = [c["score"] for c in out["retrieved_chunks"]]
        assert scores == sorted(scores, reverse=True)
        # One search per detected framework.
        assert indexer.hybrid_search.call_count == 2

    def test_detected_frameworks_from_router_preferred(self):
        # state['detected_frameworks'] (from local router) overrides keyword
        # detection on the query.
        indexer = _indexer_returning([])
        state = {
            "query": "this text mentions GDPR explicitly",
            "detected_frameworks": ["AI_ACT"],
        }
        with patch("src.api.app_state.app_state.indexer", indexer):
            retrieve_node(state)
        _, kwargs = indexer.hybrid_search.call_args
        assert kwargs["framework_filter"] == "AI_ACT"

    def test_search_exception_returns_error(self):
        indexer = MagicMock()
        indexer.hybrid_search.side_effect = RuntimeError("qdrant down")
        with patch("src.api.app_state.app_state.indexer", indexer):
            out = retrieve_node({"query": "CSRD requirements"})
        assert out["retrieved_chunks"] == []
        assert "Knowledge base retrieval failed" in out["error"]
        assert "qdrant down" in out["error"]


# ─── _apply_grounding_guard ───────────────────────────────────────


class TestGroundingGuard:
    def test_non_dict_returned_unchanged(self):
        assert _apply_grounding_guard("not a dict", []) == "not a dict"

    def test_grounded_citation_not_flagged(self):
        chunks = [{"framework": "CSRD", "text": "x"}]
        result = {
            "answer": "ok",
            "citations": [{"framework": "CSRD"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_ungrounded_framework_citation_flags_and_caps(self):
        chunks = [{"framework": "CSRD", "text": "x"}]
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}],  # not in retrieved sources
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert "grounding_warning" in out
        # Confidence capped at 0.6.
        assert out["confidence_score"] == 0.6

    def test_citations_with_no_chunks_are_ungrounded(self):
        # Nothing retrieved but model produced citations -> all ungrounded.
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}, {"framework": "CSRD"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, [])
        assert out["requires_expert_review"] is True
        assert "2 citation" in out["grounding_warning"]

    def test_ungrounded_celex_in_answer_flagged(self):
        chunks = [{"framework": "GDPR", "celex": "32016R0679"}]
        result = {
            # CELEX 32024R1234 appears in the answer but is not in retrieved celex set.
            "answer": "See 32024R1234 for details.",
            "citations": [],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True

    def test_grounded_celex_in_answer_not_flagged(self):
        chunks = [{"framework": "GDPR", "celex": "32016R0679"}]
        result = {
            "answer": "Per 32016R0679 the rules apply.",
            "citations": [{"framework": "GDPR"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out

    def test_grounded_article_reference_not_flagged(self):
        # The cited article number IS present in the retrieved chunk text -> ok.
        chunks = [
            {
                "framework": "GDPR",
                "text": "Articolo 17 Diritto alla cancellazione. L'interessato ha diritto...",
                "article_number": "Article 17",
            }
        ]
        result = {
            "answer": "You may request erasure.",
            "citations": [{"framework": "GDPR", "reference": "Art. 17(1)"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_fabricated_article_reference_flags_and_caps(self):
        # The cited article number appears in NO retrieved chunk -> ungrounded.
        chunks = [
            {
                "framework": "GDPR",
                "text": "Articolo 17 Diritto alla cancellazione...",
                "article_number": "Article 17",
            }
        ]
        result = {
            "answer": "See the provision.",
            "citations": [{"framework": "GDPR", "reference": "Art. 99(3)"}],
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert out["confidence_score"] == 0.6

    def test_bad_confidence_value_falls_back_to_0_6(self):
        result = {
            "answer": "ok",
            "citations": [{"framework": "GDPR"}],
            "confidence_score": "not-a-number",
        }
        out = _apply_grounding_guard(result, [])  # no chunks -> ungrounded
        assert out["confidence_score"] == 0.6


# ─── _pack_llm_result ─────────────────────────────────────────────


class TestPackLlmResult:
    def test_high_confidence_no_review(self):
        out = _pack_llm_result({"answer": "x", "confidence_score": 0.95})
        assert json.loads(out["result_json"])["answer"] == "x"
        assert out["confidence_score"] == 0.95
        assert out["requires_review"] is False

    def test_low_confidence_requires_review(self):
        out = _pack_llm_result({"answer": "x", "confidence_score": 0.5})
        assert out["requires_review"] is True

    def test_explicit_expert_review_forces_review(self):
        out = _pack_llm_result(
            {"answer": "x", "confidence_score": 0.99, "requires_expert_review": True}
        )
        assert out["requires_review"] is True

    def test_grounding_guard_applied_when_state_given(self):
        # State with no retrieved chunks but a citation -> guard caps to 0.6
        # and forces review.
        state = {"retrieved_chunks": []}
        out = _pack_llm_result(
            {"answer": "x", "citations": [{"framework": "GDPR"}], "confidence_score": 0.99},
            state,
        )
        assert out["requires_review"] is True
        assert out["confidence_score"] == 0.6
        assert "grounding_warning" in json.loads(out["result_json"])

    def test_non_ascii_preserved_in_json(self):
        out = _pack_llm_result({"answer": "società è à", "confidence_score": 0.9})
        # ensure_ascii=False keeps accented chars literal.
        assert "società è à" in out["result_json"]


# ─── Prompt builders ──────────────────────────────────────────────


class TestPromptBuilders:
    def test_monitor_prompt_has_guard_and_query(self, sample_company_profile):
        state = {
            "query": "New CSRD amendment published",
            "company_profile": sample_company_profile,
            "retrieved_chunks": [{"framework": "CSRD", "article_number": "19a", "text": "body"}],
        }
        system_prompt, user_msg = _build_monitor_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "New CSRD amendment published"
        # Company profile fields formatted into the system prompt.
        assert "Acme Srl" in system_prompt
        # Retrieved chunk context appended.
        assert "ADDITIONAL REGULATORY CONTEXT" in system_prompt
        assert "body" in system_prompt

    def test_gap_prompt_has_guard_and_action_message(self, sample_company_profile):
        state = {"query": "CSRD", "company_profile": sample_company_profile}
        system_prompt, user_msg = _build_gap_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "Perform gap analysis for CSRD"
        assert "Annual sustainability report 2024" in system_prompt

    def test_qa_prompt_has_guard_and_serializes_profile(self, sample_company_profile):
        state = {
            "query": "Who must report under CSRD?",
            "company_profile": sample_company_profile,
            "retrieved_chunks": [{"framework": "CSRD", "article_number": "1", "text": "ctx"}],
        }
        system_prompt, user_msg = _build_qa_prompt(state)
        assert system_prompt.startswith(_INJECTION_GUARD)
        assert user_msg == "Who must report under CSRD?"
        assert "ctx" in system_prompt
        # Profile JSON-serialized into the prompt.
        assert "Acme Srl" in system_prompt

    def test_qa_prompt_empty_profile_uses_placeholder(self):
        system_prompt, _ = _build_qa_prompt({"query": "Q", "company_profile": {}})
        assert "Not available" in system_prompt

    def test_monitor_prompt_defaults_for_missing_profile(self):
        # No profile -> default tokens ("Unknown", "All", etc.) and no crash.
        system_prompt, user_msg = _build_monitor_prompt({"query": "Q"})
        assert "Unknown" in system_prompt
        assert user_msg == "Q"


# ─── Sync agent nodes (mocked call_llm) ───────────────────────────


class TestSyncAgentNodes:
    def test_monitor_node_packs_result(self, sample_company_profile):
        llm_result = {"answer": "monitor out", "confidence_score": 0.9, "citations": []}
        with patch.object(nodes, "call_llm", return_value=llm_result) as mock_llm:
            out = monitor_agent_node(
                {"query": "CSRD change", "company_profile": sample_company_profile}
            )
        mock_llm.assert_called_once()
        # First positional arg is the system prompt carrying the injection guard.
        assert mock_llm.call_args.args[0].startswith(_INJECTION_GUARD)
        assert json.loads(out["result_json"])["answer"] == "monitor out"
        assert out["confidence_score"] == 0.9
        assert out["requires_review"] is False

    def test_gap_node_packs_result(self, sample_company_profile, sample_gap_response):
        with patch.object(nodes, "call_llm", return_value=sample_gap_response):
            out = gap_analyst_node({"query": "CSRD", "company_profile": sample_company_profile})
        # sample_gap_response confidence 0.85 -> no review needed.
        assert out["confidence_score"] == 0.85
        assert out["requires_review"] is False
        assert json.loads(out["result_json"])["framework"] == "CSRD"

    def test_qa_node_grounding_guard_caps_ungrounded(self, sample_qa_response):
        # sample_qa_response cites CSRD; with empty retrieved_chunks the guard
        # treats the citation as ungrounded -> review + capped confidence.
        with patch.object(nodes, "call_llm", return_value=dict(sample_qa_response)):
            out = qa_bot_node({"query": "Who reports?", "retrieved_chunks": []})
        assert out["requires_review"] is True
        assert out["confidence_score"] == 0.6

    def test_qa_node_grounded_citation_keeps_confidence(self, sample_qa_response):
        # With a matching CSRD chunk retrieved, the CSRD citation is grounded.
        chunks = [{"framework": "CSRD", "article_number": "19a", "text": "Large undertakings..."}]
        with patch.object(nodes, "call_llm", return_value=dict(sample_qa_response)):
            out = qa_bot_node({"query": "Who reports?", "retrieved_chunks": chunks})
        assert out["confidence_score"] == 0.9
        assert out["requires_review"] is False


# ─── Async agent nodes (mocked acall_llm) ─────────────────────────


class TestAsyncAgentNodes:
    async def test_async_monitor_node(self, sample_company_profile):
        llm_result = {"answer": "async monitor", "confidence_score": 0.9, "citations": []}
        with patch.object(nodes, "acall_llm", new=AsyncMock(return_value=llm_result)) as m:
            out = await async_monitor_agent_node(
                {"query": "CSRD change", "company_profile": sample_company_profile}
            )
        m.assert_awaited_once()
        assert json.loads(out["result_json"])["answer"] == "async monitor"
        assert out["requires_review"] is False

    async def test_async_gap_node(self, sample_company_profile, sample_gap_response):
        with patch.object(nodes, "acall_llm", new=AsyncMock(return_value=sample_gap_response)):
            out = await async_gap_analyst_node(
                {"query": "CSRD", "company_profile": sample_company_profile}
            )
        assert out["confidence_score"] == 0.85

    async def test_async_qa_node_passes_messages(self):
        mock = AsyncMock(return_value={"answer": "qa", "confidence_score": 0.9, "citations": []})
        with patch.object(nodes, "acall_llm", new=mock):
            await async_qa_bot_node({"query": "Who reports?"})
        # system_prompt + user_message forwarded; user message == the query.
        args = mock.await_args.args
        assert args[0].startswith(_INJECTION_GUARD)
        assert args[1] == "Who reports?"


# ─── confidence_check_node ────────────────────────────────────────


class TestConfidenceCheckNode:
    def test_high_confidence_no_review(self):
        assert confidence_check_node({"confidence_score": 0.9}) == {"requires_review": False}

    def test_low_confidence_requires_review(self):
        assert confidence_check_node({"confidence_score": 0.7}) == {"requires_review": True}

    def test_boundary_0_8_not_flagged(self):
        # score < 0.8 triggers review; exactly 0.8 does NOT.
        assert confidence_check_node({"confidence_score": 0.8}) == {"requires_review": False}

    def test_missing_score_defaults_to_review(self):
        # Default 0.0 < 0.8 -> review.
        assert confidence_check_node({}) == {"requires_review": True}


# ─── async_local_router_node ──────────────────────────────────────


class TestAsyncLocalRouterNode:
    async def test_writes_router_fields_into_state(self):
        router_result = MagicMock()
        router_result.frameworks = ["CSRD"]
        router_result.complexity = "complex"
        router_result.entities = {"article_refs": ["Art. 8"], "deadlines": [], "thresholds": []}
        router_result.source = "local_llm"

        with patch(
            "src.agents.router.aroute_query", new=AsyncMock(return_value=router_result)
        ) as m:
            out = await async_local_router_node({"query": "CSRD Art 8", "task_type": "qa"})

        m.assert_awaited_once_with("CSRD Art 8", "qa")
        assert out["detected_frameworks"] == ["CSRD"]
        assert out["complexity_tier"] == "complex"
        assert out["extracted_entities"]["article_refs"] == ["Art. 8"]
        assert out["router_source"] == "local_llm"

    async def test_defaults_query_and_task_type(self):
        router_result = MagicMock()
        router_result.frameworks = []
        router_result.complexity = "medium"
        router_result.entities = {}
        router_result.source = "keyword_fallback"
        with patch(
            "src.agents.router.aroute_query", new=AsyncMock(return_value=router_result)
        ) as m:
            await async_local_router_node({})
        # Empty state -> defaults: query "", task_type "qa".
        m.assert_awaited_once_with("", "qa")


# ─── async_simple_response_node ───────────────────────────────────


class TestAsyncSimpleResponseNode:
    async def test_cache_hit_returns_cached_payload(self):
        cached = {"answer": "cached", "confidence_score": 0.91}
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)):
            out = await async_simple_response_node(
                {"query": "What is GDPR?", "task_type": "qa", "company_profile": {}}
            )
        assert json.loads(out["result_json"])["answer"] == "cached"
        assert out["confidence_score"] == 0.91
        assert out["requires_review"] is False
        # Cache hit does NOT escalate.
        assert "complexity_tier" not in out

    async def test_cache_hit_default_confidence(self):
        # Cached payload missing confidence_score -> default 0.8.
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value={"answer": "c"})):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out["confidence_score"] == 0.8

    async def test_cache_miss_escalates_to_medium(self):
        with patch("src.cache.response_cache.get", new=AsyncMock(return_value=None)):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out == {"complexity_tier": "medium"}

    async def test_cache_error_escalates_gracefully(self):
        # A cache exception must not crash the node; it escalates instead.
        with patch(
            "src.cache.response_cache.get",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            out = await async_simple_response_node({"query": "Q", "task_type": "qa"})
        assert out == {"complexity_tier": "medium"}
