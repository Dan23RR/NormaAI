"""Unit tests for the Chain-of-Verification (CoVe) anti-hallucination pipeline.

Tests cover:
- CoVe model validation (Claim, VerificationStep, CoVeResult)
- CoVeConfig defaults and overrides
- Claim extraction from sample LLM output
- Verification planning for extracted claims
- SSE event types emitted during the pipeline
"""

import pytest

from src.agents.cove.models import (
    CitationCheck,
    Claim,
    CoVeConfig,
    CoVeResult,
    DraftResult,
    RevisionResult,
    VerificationPlan,
    VerificationQuestion,
    VerificationStep,
)

# ------------------------------------------------------------------ #
#  Model Validation Tests                                             #
# ------------------------------------------------------------------ #


class TestClaimModel:
    def test_claim_with_all_fields(self):
        claim = Claim(
            text="CSRD requires sustainability reporting for companies with 1000+ employees",
            citation="Art. 19a CSRD",
            article_ref="19a",
            framework="CSRD",
            confidence=0.92,
        )
        assert (
            claim.text
            == "CSRD requires sustainability reporting for companies with 1000+ employees"
        )
        assert claim.citation == "Art. 19a CSRD"
        assert claim.framework == "CSRD"
        assert claim.confidence == 0.92

    def test_claim_with_defaults(self):
        claim = Claim(text="Some claim")
        assert claim.citation is None
        assert claim.article_ref is None
        assert claim.framework is None
        assert claim.confidence == 0.5

    def test_claim_confidence_bounds(self):
        with pytest.raises(Exception):
            Claim(text="Bad claim", confidence=1.5)
        with pytest.raises(Exception):
            Claim(text="Bad claim", confidence=-0.1)


class TestVerificationStepModel:
    def test_verified_step(self):
        step = VerificationStep(
            claim_index=0,
            claim=Claim(text="CSRD threshold is 1000 employees"),
            question="What is the employee threshold for CSRD?",
            answer="After Omnibus I, the threshold is 1,000 employees",
            evidence_chunks=[{"text": "Article 19a...", "celex": "32022L2464"}],
            verified=True,
            confidence=0.95,
            discrepancy=None,
        )
        assert step.verified is True
        assert step.confidence == 0.95
        assert step.discrepancy is None

    def test_unverified_step(self):
        step = VerificationStep(
            claim_index=1,
            claim=Claim(text="CSDDD deadline is 2026"),
            question="What is the CSDDD transposition deadline?",
            answer="The transposition deadline is 26 July 2028 (Omnibus I, Directive (EU) 2026/470)",
            evidence_chunks=[],
            verified=False,
            confidence=0.3,
            discrepancy="Claimed 2026, but actual deadline is 26 July 2028",
        )
        assert step.verified is False
        assert "2028" in step.discrepancy


class TestCoVeResultModel:
    def test_complete_result(self):
        result = CoVeResult(
            draft=DraftResult(
                text="CSRD applies to large companies...",
                claims=[Claim(text="CSRD applies")],
                raw_json={"answer": "CSRD applies to large companies..."},
                confidence=0.8,
            ),
            plan=VerificationPlan(
                questions=[
                    VerificationQuestion(
                        claim_index=0,
                        question="Does CSRD apply to large companies?",
                        search_query="CSRD scope large companies",
                    )
                ],
                estimated_time_seconds=5.0,
            ),
            verifications=[
                VerificationStep(
                    claim_index=0,
                    claim=Claim(text="CSRD applies"),
                    question="Does CSRD apply?",
                    answer="Yes, confirmed",
                    verified=True,
                    confidence=0.95,
                )
            ],
            revision=RevisionResult(
                original_text="CSRD applies to large companies...",
                revised_text="CSRD applies to large companies...",
                changes_made=[],
                claims_corrected=0,
                claims_removed=0,
                confidence=0.95,
            ),
            citation_checks=[
                CitationCheck(
                    celex="32022L2464",
                    article="Art. 19a",
                    exists=True,
                    is_current=True,
                    url="https://eur-lex.europa.eu/eli/dir/2022/2464",
                )
            ],
            total_time_seconds=12.3,
            phases_completed=5,
        )
        assert result.phases_completed == 5
        assert len(result.verifications) == 1
        assert result.citation_checks[0].exists is True


class TestCoVeConfig:
    def test_default_config(self):
        config = CoVeConfig()
        assert config.enabled is False
        assert config.max_claims == 10
        assert config.max_verification_chunks == 5
        assert config.skip_citation_check is False
        assert config.parallel_verification is False
        assert config.timeout_per_phase_seconds == 30.0

    def test_custom_config(self):
        config = CoVeConfig(
            enabled=True,
            max_claims=5,
            skip_citation_check=True,
            timeout_per_phase_seconds=60.0,
        )
        assert config.enabled is True
        assert config.max_claims == 5
        assert config.skip_citation_check is True
        assert config.timeout_per_phase_seconds == 60.0


# ------------------------------------------------------------------ #
#  CoVe Integration in Graph Tests                                    #
# ------------------------------------------------------------------ #


class TestCoVeGraphIntegration:
    """Test that CoVe is properly wired into the LangGraph."""

    def test_graph_has_cove_node(self):
        """The compiled graph should include a cove_verification node."""
        from src.agents.graph import _build_graph

        graph = _build_graph(use_async_nodes=False)
        # LangGraph compiled graphs have .nodes attribute
        node_names = [n for n in graph.get_graph().nodes]
        assert "cove_verification" in node_names

    def test_initial_state_includes_cove_fields(self):
        """_create_initial_state should always include cove fields."""
        from src.agents.graph import _create_initial_state

        state = _create_initial_state("test query", "qa", cove_enabled=True)
        assert state["cove_enabled"] is True
        assert state["cove_result"] == {}

    def test_initial_state_cove_disabled_by_default(self):
        from src.agents.graph import _create_initial_state

        state = _create_initial_state("test query", "qa")
        assert state["cove_enabled"] is False


# ------------------------------------------------------------------ #
#  Claim Extraction Pattern Tests                                     #
# ------------------------------------------------------------------ #


class TestClaimExtraction:
    """Test the claim extraction patterns used by CoVe."""

    def test_claim_serialization_roundtrip(self):
        claim = Claim(
            text="The CSRD threshold was raised to 1000 employees",
            citation="Art. 19a",
            framework="CSRD",
            confidence=0.9,
        )
        json_data = claim.model_dump()
        restored = Claim(**json_data)
        assert restored.text == claim.text
        assert restored.confidence == claim.confidence

    def test_multiple_claims_in_result(self):
        draft = DraftResult(
            text="CSRD and CSDDD both apply. GDPR is also relevant.",
            claims=[
                Claim(text="CSRD applies", framework="CSRD"),
                Claim(text="CSDDD applies", framework="CSDDD"),
                Claim(text="GDPR is relevant", framework="GDPR"),
            ],
            raw_json={},
        )
        assert len(draft.claims) == 3
        frameworks = [c.framework for c in draft.claims]
        assert "CSRD" in frameworks
        assert "CSDDD" in frameworks
        assert "GDPR" in frameworks


# ------------------------------------------------------------------ #
#  CoVeResult Serialization Tests                                     #
# ------------------------------------------------------------------ #


class TestCoVeResultSerialization:
    def test_result_to_dict(self):
        """CoVeResult should serialize to dict cleanly for state storage."""
        result = CoVeResult(
            draft=DraftResult(text="test", claims=[], raw_json={}),
            plan=VerificationPlan(),
            verifications=[],
            revision=RevisionResult(
                original_text="test",
                revised_text="test",
            ),
            citation_checks=[],
            total_time_seconds=1.0,
            phases_completed=5,
        )
        data = result.model_dump()
        assert isinstance(data, dict)
        assert data["phases_completed"] == 5
        assert "draft" in data
        assert "revision" in data


# ------------------------------------------------------------------ #
#  Citation extraction & honest CELEX validation                     #
# ------------------------------------------------------------------ #


class TestCitationValidation:
    """Regression guard: the 'audit-defensible' promise must not rubber-stamp."""

    def test_celex_extraction_matches_real_format(self):
        """Real CELEX (with type letter) must be extracted - the old digit-only
        regex silently missed every EU citation."""
        from src.agents.cove.orchestrator import _extract_citations_from_text

        cites = _extract_citations_from_text(
            "Under CSRD (32022L2464) and the AI Act (32024R1689) ..."
        )
        celex = {c["value"] for c in cites if c["type"] == "celex"}
        assert "32022L2464" in celex
        assert "32024R1689" in celex

    async def test_known_celex_valid_unknown_unverified(self):
        """A seeded CELEX validates; a well-formed but unseeded one is flagged
        unverified (NOT rubber-stamped) - this is the core anti-hallucination fix."""
        from src.agents.cove.models import CoVeConfig
        from src.agents.cove.orchestrator import CoVeOrchestrator

        orch = CoVeOrchestrator(config=CoVeConfig(enabled=True))
        checks = await orch._validate_citations(
            "Per la CSRD 32022L2464 e una fantomatica 39999L9999 ..."
        )
        by_celex = {c.celex: c for c in checks if c.celex}
        assert by_celex["32022L2464"].exists is True
        # Unknown, never indexed -> must be marked not-existing / unverified.
        assert by_celex["39999L9999"].exists is False


class TestCoVeRevisedTextReachesResult:
    """BUG-002 regression: the verified text must replace the draft, not vanish."""

    def test_apply_cove_overwrites_answer(self):
        import json as _json

        from src.agents.graph import _apply_cove_to_result

        state = {
            "result_json": _json.dumps(
                {"answer": "DRAFT possibly hallucinated", "confidence_score": 0.5}
            )
        }
        done = {
            "revised_text": "VERIFIED answer with checked citations",
            "confidence_score": 0.82,
            "requires_review": False,
        }
        _apply_cove_to_result(state, done)
        result = _json.loads(state["result_json"])
        assert result["answer"] == "VERIFIED answer with checked citations"
        assert result["confidence_score"] == 0.82
        assert result["cove_applied"] is True


class TestTenantScopePropagation:
    """SEC-01 regression: org_id must flow from the agent state into the search."""

    def test_initial_state_carries_org_id(self):
        from src.agents.graph import _create_initial_state

        state = _create_initial_state("q", "qa", org_id="org-A")
        assert state["org_id"] == "org-A"

    def test_retrieve_node_passes_org_id_to_search(self):
        from unittest.mock import MagicMock, patch

        from src.agents.nodes import retrieve_node

        fake_indexer = MagicMock()
        fake_indexer.hybrid_search.return_value = []
        with patch("src.api.app_state.app_state") as app_state:
            app_state.indexer = fake_indexer
            retrieve_node({"query": "CSRD scope", "org_id": "org-A"})
        assert fake_indexer.hybrid_search.called
        # Every search call must be scoped to the caller's org.
        for call in fake_indexer.hybrid_search.call_args_list:
            assert call.kwargs.get("org_id") == "org-A"


class TestGroundingGuard:
    """P4: citations not backed by retrieved sources must force review."""

    def test_ungrounded_citation_flagged(self):
        from src.agents.nodes import _apply_grounding_guard

        chunks = [{"framework": "CSRD", "celex": "32022L2464", "text": "..."}]
        result = {
            "answer": "Also covered by the AI Act 32024R1689.",
            "citations": [{"framework": "AI_ACT", "reference": "Art. 5"}],
            "confidence_score": 0.95,
        }
        out = _apply_grounding_guard(result, chunks)
        assert out["requires_expert_review"] is True
        assert out["confidence_score"] <= 0.6
        assert "grounding_warning" in out

    def test_grounded_citation_passes(self):
        from src.agents.nodes import _apply_grounding_guard

        chunks = [{"framework": "CSRD", "celex": "32022L2464", "text": "..."}]
        result = {
            "answer": "CSRD applies per 32022L2464.",
            "citations": [{"framework": "CSRD", "reference": "Art. 19a"}],
            "confidence_score": 0.9,
        }
        out = _apply_grounding_guard(result, chunks)
        assert "grounding_warning" not in out
        assert out["confidence_score"] == 0.9

    def test_citations_with_no_context_flagged(self):
        from src.agents.nodes import _apply_grounding_guard

        result = {"answer": "X", "citations": [{"framework": "GDPR"}], "confidence_score": 0.8}
        out = _apply_grounding_guard(result, [])
        assert out["requires_expert_review"] is True
