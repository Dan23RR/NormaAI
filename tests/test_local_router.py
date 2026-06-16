"""Tests for local LLM router: framework routing, complexity gate, NER.

Tests cover:
- RouterResult serialization
- Keyword fallback detection (CSRD, GDPR italian, multi-framework, no match)
- Validate and sanitize (valid output, invalid frameworks, unknown complexity)
- Complexity gate branching
- Async routing with mock local LLM
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes import complexity_gate_branch
from src.agents.router import (
    _VALID_FRAMEWORKS,
    RouterResult,
    _keyword_fallback,
    _validate_and_sanitize,
    aroute_query,
)

# ─── TestRouterResult ─────────────────────────────────────────────


class TestRouterResult:
    def test_default_values(self):
        r = RouterResult()
        assert r.frameworks == []
        assert r.complexity == "medium"
        assert r.entities == {"article_refs": [], "deadlines": [], "thresholds": []}
        assert r.source == "keyword_fallback"

    def test_custom_values(self):
        r = RouterResult(
            frameworks=["CSRD", "GDPR"],
            complexity="complex",
            entities={"article_refs": ["Art. 19a"], "deadlines": [], "thresholds": []},
            source="local_llm",
        )
        assert r.frameworks == ["CSRD", "GDPR"]
        assert r.complexity == "complex"
        assert r.source == "local_llm"


# ─── TestKeywordFallback ─────────────────────────────────────────


class TestKeywordFallback:
    def test_detect_csrd(self):
        result = _keyword_fallback("What are the CSRD requirements?")
        assert "CSRD" in result.frameworks
        assert result.source == "keyword_fallback"

    def test_detect_gdpr_italian(self):
        result = _keyword_fallback("Come funziona la protezione dei dati personali?")
        assert "GDPR" in result.frameworks

    def test_detect_multi_framework(self):
        result = _keyword_fallback("How does DORA relate to NIS2?")
        assert "DORA" in result.frameworks
        assert "NIS2" in result.frameworks

    def test_no_match_returns_all(self):
        result = _keyword_fallback("Tell me about EU regulations")
        assert set(result.frameworks) == _VALID_FRAMEWORKS

    def test_complexity_always_medium(self):
        result = _keyword_fallback("CSRD question")
        assert result.complexity == "medium"


# ─── TestValidateAndSanitize ─────────────────────────────────────


class TestValidateAndSanitize:
    def test_valid_output(self):
        raw = {
            "frameworks": ["CSRD", "GDPR"],
            "complexity": "complex",
            "entities": {
                "article_refs": ["Art. 19a"],
                "deadlines": ["2025-01-01"],
                "thresholds": ["500 employees"],
            },
        }
        result = _validate_and_sanitize(raw)
        assert result.frameworks == ["CSRD", "GDPR"]
        assert result.complexity == "complex"
        assert result.entities["article_refs"] == ["Art. 19a"]
        assert result.source == "local_llm"

    def test_invalid_frameworks_filtered(self):
        raw = {"frameworks": ["CSRD", "INVALID_FW", "MiFID"], "complexity": "simple"}
        result = _validate_and_sanitize(raw)
        assert result.frameworks == ["CSRD"]

    def test_all_invalid_frameworks_returns_all(self):
        raw = {"frameworks": ["INVALID", "FAKE"], "complexity": "simple"}
        result = _validate_and_sanitize(raw)
        assert set(result.frameworks) == _VALID_FRAMEWORKS

    def test_empty_frameworks_returns_all(self):
        raw = {"frameworks": [], "complexity": "medium"}
        result = _validate_and_sanitize(raw)
        assert set(result.frameworks) == _VALID_FRAMEWORKS

    def test_unknown_complexity_defaults_to_medium(self):
        raw = {"frameworks": ["DORA"], "complexity": "very_hard"}
        result = _validate_and_sanitize(raw)
        assert result.complexity == "medium"

    def test_missing_entities_defaults(self):
        raw = {"frameworks": ["NIS2"], "complexity": "simple"}
        result = _validate_and_sanitize(raw)
        assert result.entities == {"article_refs": [], "deadlines": [], "thresholds": []}

    def test_non_list_frameworks_handled(self):
        raw = {"frameworks": "CSRD", "complexity": "simple"}
        result = _validate_and_sanitize(raw)
        assert set(result.frameworks) == _VALID_FRAMEWORKS


# ─── TestComplexityGateBranch ─────────────────────────────────────


class TestComplexityGateBranch:
    def test_simple_routes_to_simple_response(self):
        state = {"complexity_tier": "simple"}
        assert complexity_gate_branch(state) == "simple_response"

    def test_medium_routes_to_retrieve(self):
        state = {"complexity_tier": "medium"}
        assert complexity_gate_branch(state) == "retrieve"

    def test_complex_routes_to_retrieve(self):
        state = {"complexity_tier": "complex"}
        assert complexity_gate_branch(state) == "retrieve"

    def test_empty_defaults_to_retrieve(self):
        state = {}
        assert complexity_gate_branch(state) == "retrieve"


# ─── TestAsyncRouting ─────────────────────────────────────────────


class TestAsyncRouting:
    @pytest.mark.asyncio
    async def test_local_llm_result_used(self):
        """When local LLM returns valid result, it should be used."""
        mock_result = {
            "frameworks": ["CSRD"],
            "complexity": "simple",
            "entities": {"article_refs": ["Art. 8"], "deadlines": [], "thresholds": []},
        }
        with patch(
            "src.agents.router.acall_local_llm", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await aroute_query("CSRD Article 8 requirements", "qa")
            assert result.frameworks == ["CSRD"]
            assert result.complexity == "simple"
            assert result.source == "local_llm"

    @pytest.mark.asyncio
    async def test_fallback_on_none(self):
        """When local LLM returns None, keyword fallback should be used."""
        with patch("src.agents.router.acall_local_llm", new_callable=AsyncMock, return_value=None):
            result = await aroute_query("CSRD requirements", "qa")
            assert "CSRD" in result.frameworks
            assert result.source == "keyword_fallback"

    @pytest.mark.asyncio
    async def test_minimum_complexity_enforcement_gap_analysis(self):
        """Gap analysis should never be classified as 'simple'."""
        mock_result = {
            "frameworks": ["CSRD"],
            "complexity": "simple",
            "entities": {"article_refs": [], "deadlines": [], "thresholds": []},
        }
        with patch(
            "src.agents.router.acall_local_llm", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await aroute_query("CSRD gap analysis", "gap_analysis")
            assert result.complexity == "medium"  # Enforced minimum

    @pytest.mark.asyncio
    async def test_minimum_complexity_enforcement_monitor(self):
        """Monitor should never be classified as 'simple'."""
        mock_result = {
            "frameworks": ["DORA"],
            "complexity": "simple",
            "entities": {"article_refs": [], "deadlines": [], "thresholds": []},
        }
        with patch(
            "src.agents.router.acall_local_llm", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await aroute_query("DORA update", "monitor")
            assert result.complexity == "medium"

    @pytest.mark.asyncio
    async def test_qa_allows_simple(self):
        """QA task should allow 'simple' complexity."""
        mock_result = {
            "frameworks": ["GDPR"],
            "complexity": "simple",
            "entities": {"article_refs": [], "deadlines": [], "thresholds": []},
        }
        with patch(
            "src.agents.router.acall_local_llm", new_callable=AsyncMock, return_value=mock_result
        ):
            result = await aroute_query("What is GDPR?", "qa")
            assert result.complexity == "simple"
