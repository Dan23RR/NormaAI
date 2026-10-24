"""The golden-set hook of the citation verifier: tests/validation/metrics.py.

``verified_citation_rate`` reads the pipeline's own ``verified`` flags (or the
``verified_citations`` / ``citations_total`` counters) and is informational:
the suite's pass/fail thresholds do not change.
"""

import pytest


class TestVerifiedCitationRateMetric:
    def test_counters_are_preferred(self):
        from tests.validation.metrics import verified_citation_rate

        assert verified_citation_rate({"verified_citations": 1, "citations_total": 4}) == 0.25
        # A strict abstention withheld its citations; the counters still score it.
        assert (
            verified_citation_rate({"citations": [], "verified_citations": 0, "citations_total": 2})
            == 0.0
        )
        assert verified_citation_rate({"verified_citations": 0, "citations_total": 0}) is None

    def test_flags_when_there_are_no_counters(self):
        from tests.validation.metrics import verified_citation_rate

        output = {"citations": [{"verified": True}, {"verified": False}, {"article": "Art. 5"}]}
        assert verified_citation_rate(output) == pytest.approx(1 / 3)
        # No flag at all (pre-verifier output, demo run): nothing to score.
        assert verified_citation_rate({"citations": [{"article": "Art. 5"}]}) is None
        assert verified_citation_rate({"citations": []}) is None
        assert verified_citation_rate("x") is None

    def test_wired_into_test_and_suite_metrics(self):
        from tests.validation.golden_v2 import load_golden_v2
        from tests.validation.metrics import aggregate_suite_results, calculate_test_metrics

        case = next(r for r in load_golden_v2() if not r.expected.abstain).to_test_case()
        raw_pipeline_answer = {
            "answer": "x",
            "citations": [
                # A raw pipeline citation: the verifier left article=None (not found).
                {
                    "reference": case.expected_findings[0].article,
                    "article": None,
                    "verified": False,
                },
                {"reference": "Art. 999", "article": None, "verified": False},
            ],
            "verified_citations": 0,
            "citations_total": 2,
        }
        result = calculate_test_metrics(case, raw_pipeline_answer)
        assert result.verified_citation_rate == 0.0
        # The model's reference is what the recall counts (no crash on article=None).
        assert result.true_positives == [case.expected_findings[0].article]

        scored = calculate_test_metrics(
            case, {"answer": "x", "citations": [], "verified_citations": 1, "citations_total": 1}
        )
        suite = aggregate_suite_results("s", [result, scored], [case])
        assert suite.avg_verified_citation_rate == pytest.approx(0.5)
        # Informational only: the pass/fail thresholds are unchanged.
        assert (suite.recall_threshold, suite.precision_threshold, suite.f1_threshold) == (
            0.95,
            0.80,
            0.87,
        )

    def test_api_parser_keeps_flags_and_counters(self):
        from tests.validation.response_parser import _parse_qa

        parsed = _parse_qa(
            {
                "answer": "x",
                "citations": [
                    {"framework": "GDPR", "reference": "Art. 5", "verified": True},
                    {"framework": "GDPR", "reference": "Art. 6", "verified": None},
                ],
                "verified_citations": 1,
                "citations_total": 2,
            },
            {},
        )
        assert parsed["citations"][0]["verified"] is True
        assert "verified" not in parsed["citations"][1]
        assert (parsed["verified_citations"], parsed["citations_total"]) == (1, 2)
