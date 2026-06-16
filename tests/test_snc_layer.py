"""Unit tests for the SNC governance layer.

Tests the pure logic (no LLM calls): behavioral clustering, trust formula,
entropy computation, decision serialization. The async snc_governance()
end-to-end is covered separately in test_snc_node.py with mocked LLM.
"""

import math

import pytest

from src.agents.snc_layer import (
    SNCConfig,
    SNCDecision,
    _normalize_citations,
    _shannon_entropy_normalized,
    behavior_key,
    serialize_decision,
    trust_thermodynamic,
)

# ─── Behavioral clustering: domain-specific (citations as identity) ─────


class TestBehavioralClustering:
    def test_three_phrasings_same_citation_cluster_identically(self):
        c = [{"framework": "GDPR", "article_number": "5"}]
        k1 = behavior_key({"answer": "Articolo 5 GDPR.", "citations": c})
        k2 = behavior_key({"answer": "gdpr art 5", "citations": c})
        k3 = behavior_key({"answer": "Riferimento art. 5 del Reg.", "citations": c})
        assert k1 == k2 == k3

    def test_distinct_citations_distinct_clusters(self):
        k1 = behavior_key(
            {"answer": "X", "citations": [{"framework": "GDPR", "article_number": "5"}]}
        )
        k2 = behavior_key(
            {"answer": "X", "citations": [{"framework": "GDPR", "article_number": "6"}]}
        )
        assert k1 != k2

    def test_citation_order_invariance(self):
        ka = behavior_key(
            {
                "answer": "X",
                "citations": [
                    {"framework": "GDPR", "article_number": "5"},
                    {"framework": "GDPR", "article_number": "6"},
                ],
            }
        )
        kb = behavior_key(
            {
                "answer": "X",
                "citations": [
                    {"framework": "GDPR", "article_number": "6"},
                    {"framework": "GDPR", "article_number": "5"},
                ],
            }
        )
        assert ka == kb

    def test_urn_based_clustering(self):
        u = "urn:nir:stato:decreto.legislativo:2003-06-30;196"
        k1 = behavior_key({"answer": "D.Lgs. 196/2003", "citations": [{"urn": u}]})
        k2 = behavior_key({"answer": "codice privacy", "citations": [{"urn": u}]})
        assert k1 == k2

    def test_celex_based_clustering(self):
        k1 = behavior_key({"answer": "Reg UE", "citations": [{"celex": "32024L0001"}]})
        k2 = behavior_key({"answer": "Direttiva", "citations": [{"celex": "32024L0001"}]})
        assert k1 == k2

    def test_no_citation_token_sort_equivalence(self):
        k1 = behavior_key({"answer": "la base giuridica e il consenso", "citations": []})
        k2 = behavior_key({"answer": "il consenso e la base giuridica", "citations": []})
        assert k1 == k2

    def test_non_dict_input_handled(self):
        k = behavior_key("plain string")
        assert isinstance(k, tuple)
        assert k[0] == "txt"


# ─── Trust thermodynamics ──────────────────────────────────────────────


class TestTrustFormula:
    def test_perfect_agreement_recovers_ppv(self):
        assert trust_thermodynamic(0.8, 0.0) == 0.8

    def test_zero_t_comp_recovers_ppv(self):
        assert trust_thermodynamic(0.8, 0.5, t_comp=0.0) == pytest.approx(0.8)

    def test_max_disagreement_discounts(self):
        ppv = 0.9
        expected = ppv * math.exp(-1.0)
        assert trust_thermodynamic(ppv, 1.0, t_comp=1.0) == pytest.approx(expected)

    def test_adaptive_t_comp(self):
        # Default T_comp = 0.5 + (1 - PPV)
        ppv, sigma = 0.6, 0.5
        expected = ppv * math.exp(-sigma * (0.5 + (1 - 0.6)))
        assert trust_thermodynamic(ppv, sigma) == pytest.approx(expected)

    def test_clamps_invalid_inputs(self):
        # Negative PPV clamped to 0
        assert trust_thermodynamic(-0.1, 0.0) == 0.0
        # PPV > 1 clamped to 1
        assert trust_thermodynamic(1.5, 0.0) == 1.0


# ─── Entropy ──────────────────────────────────────────────────────────


class TestEntropy:
    def test_single_cluster_zero_entropy(self):
        assert _shannon_entropy_normalized([5]) == 0.0
        assert _shannon_entropy_normalized([100]) == 0.0

    def test_uniform_distribution_max_entropy(self):
        assert _shannon_entropy_normalized([1, 1, 1, 1, 1]) == pytest.approx(1.0)

    def test_skewed_distribution_intermediate(self):
        v = _shannon_entropy_normalized([4, 1])
        assert 0.0 < v < 1.0

    def test_empty_or_zero_returns_zero(self):
        assert _shannon_entropy_normalized([]) == 0.0
        assert _shannon_entropy_normalized([0, 0]) == 0.0


# ─── Configuration ────────────────────────────────────────────────────


class TestConfig:
    def test_defaults_aligned_with_legacy_threshold(self):
        cfg = SNCConfig()
        # theta_high == 0.85 matches the existing confidence_check threshold.
        assert cfg.theta_high == 0.85
        assert cfg.theta_low == 0.50
        assert cfg.k == 3
        assert cfg.enabled is True


# ─── Serialization ────────────────────────────────────────────────────


class TestSerialization:
    def test_serialize_decision_round_trip(self):
        d = SNCDecision(
            action="ADMIT_HIGH",
            trust=0.85,
            ppv=0.9,
            sigma_calib=0.1,
            t_comp=0.6,
            n_clusters=1,
            modal_answer={"answer": "X", "citations": []},
            samples=[
                {"answer": "X", "confidence_score": 0.9, "citations": []},
            ],
        )
        s = serialize_decision(d)
        for key in [
            "action",
            "trust",
            "ppv",
            "sigma_calib",
            "t_comp",
            "n_clusters",
            "n_samples",
            "samples_summary",
        ]:
            assert key in s
        assert s["action"] == "ADMIT_HIGH"
        assert s["n_clusters"] == 1
        assert isinstance(s["samples_summary"], list)
        assert s["samples_summary"][0]["n_citations"] == 0


# ─── Citation normalization ───────────────────────────────────────────


class TestCitationNormalization:
    def test_urn_takes_precedence(self):
        # When urn is present, it is the cluster identity.
        c = [{"urn": "urn:foo", "framework": "GDPR", "article_number": "5"}]
        keys = _normalize_citations(c)
        assert keys == ("urn:urn:foo",)

    def test_celex_when_no_urn(self):
        c = [{"celex": "32024L0001"}]
        keys = _normalize_citations(c)
        assert keys == ("celex:32024L0001",)

    def test_framework_article_fallback(self):
        c = [{"framework": "GDPR", "article_number": "5"}]
        keys = _normalize_citations(c)
        assert keys == ("GDPR:5",)

    def test_handles_non_dict_citations(self):
        c = ["just a string"]
        keys = _normalize_citations(c)
        assert len(keys) == 1
