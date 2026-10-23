"""Tests for the gap-analysis normaliser in src/api/routers/reports.py.

The normaliser feeds the PDF generator from the agent's JSON. Its field names
must match what prompts/gap_analyst.txt actually asks the model to produce
(``requirement_id`` / ``article_reference`` / ``gap_description`` /
``remediation_effort`` / ``priority``, ``top_recommendations`` as strings,
the fifth status ``IN_EVOLUTION``). Before the fix every requirement in a real
report came out as "Unknown" and the recommendations list was always empty.

Pure functions: the router module is imported function-locally and evicted
from sys.modules afterwards (same isolation rule as test_reports_router.py).
"""

import sys

import pytest


@pytest.fixture(autouse=True)
def _evict_router_modules():
    yield
    for name in list(sys.modules):
        if name == "src.api.main" or name.startswith("src.api.routers"):
            sys.modules.pop(name, None)


def _normaliser():
    from src.api.routers.reports import _normalise_gap_data

    return _normalise_gap_data


def _prompt_shaped_gap_result() -> dict:
    """Exactly the OUTPUT JSON SCHEMA of prompts/gap_analyst.txt."""
    return {
        "framework": "CSRD",
        "assessment_date": "2026-10-23",
        "overall_score": 45.0,
        "status_summary": {
            "compliant": 1,
            "partially_compliant": 1,
            "non_compliant": 1,
            "not_applicable": 1,
            "in_evolution": 1,
        },
        "requirements": [
            {
                "requirement_id": "CSRD-Art19a-1",
                "description": "Include a sustainability report in the management report.",
                "article_reference": "Art. 19a(1)",
                "status": "COMPLIANT",
                "evidence": "Annual sustainability report 2024, section 2",
                "gap_description": "",
                "remediation_effort": "n/a",
                "priority": "P4",
                "notes": "",
            },
            {
                "requirement_id": "CSRD-Art29b-1",
                "description": "Report according to the ESRS adopted by delegated acts.",
                "article_reference": "Art. 29b(1)",
                "status": "PARTIALLY_COMPLIANT",
                "evidence": "Partial ESRS E1 disclosures",
                "gap_description": "ESRS S1-S4 data points missing.",
                "remediation_effort": "2-3 weeks",
                "priority": "P2",
                "notes": "ESRS Set 1 simplified post-Omnibus",
            },
            {
                "requirement_id": "CSRD-Art34-1",
                "description": "Obtain limited assurance on the sustainability report.",
                "article_reference": "Art. 34(1)(aa)",
                "status": "NON_COMPLIANT",
                "evidence": "No evidence found",
                "gap_description": "No assurance engagement contracted.",
                "remediation_effort": "3 months",
                "priority": "P1",
                "notes": "",
            },
            {
                "requirement_id": "CSRD-Art40a-1",
                "description": "Third-country undertaking reporting.",
                "article_reference": "Art. 40a",
                "status": "NOT_APPLICABLE",
                "evidence": "EU-incorporated company",
                "gap_description": "",
                "remediation_effort": "",
                "priority": "P4",
                "notes": "",
            },
            {
                "requirement_id": "CSRD-Art19a-2",
                "description": "Scope thresholds after Omnibus I.",
                "article_reference": "Art. 19a(2)",
                "status": "IN_EVOLUTION",
                "evidence": "Directive (EU) 2026/470 transposition pending",
                "gap_description": "Threshold moves to 1,000 employees.",
                "remediation_effort": "2 days",
                "priority": "P3",
                "notes": "Re-assess after national transposition",
            },
        ],
        "top_recommendations": [
            "P1: Contract a limited assurance provider before the next reporting deadline (3 months).",
            "[P2] Close the ESRS S1-S4 data gaps (2-3 weeks).",
            "Monitor the Omnibus I transposition timeline.",
        ],
        "confidence_score": 0.82,
        "requires_expert_review": True,
        "next_assessment_date": "2027-04-01",
    }


class TestPromptShapedRequirements:
    def test_no_requirement_is_called_unknown(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        names = [r["name"] for r in out["requirements"]]
        assert len(names) == 5
        assert "Unknown" not in names
        # requirement_id + article reference, so the table row is identifiable.
        assert names[0] == "CSRD-Art19a-1 (Art. 19a(1))"

    def test_prompt_fields_are_mapped(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        req = out["requirements"][1]
        assert req["status"] == "PARTIALLY_COMPLIANT"
        assert req["description"].startswith("Report according to the ESRS")
        assert req["remediation"] == "ESRS S1-S4 data points missing."
        assert req["effort"] == "HIGH"  # "2-3 weeks" -> upper bound 3 weeks
        assert req["article_reference"] == "Art. 29b(1)"
        assert req["evidence"] == "Partial ESRS E1 disclosures"
        assert req["priority"] == "P2"
        assert req["notes"] == "ESRS Set 1 simplified post-Omnibus"

    def test_in_evolution_status_is_preserved(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        statuses = [r["status"] for r in out["requirements"]]
        assert statuses == [
            "COMPLIANT",
            "PARTIALLY_COMPLIANT",
            "NON_COMPLIANT",
            "NOT_APPLICABLE",
            "IN_EVOLUTION",
        ]

    def test_duration_efforts_are_mapped_and_unknown_stays_blank(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        efforts = [r["effort"] for r in out["requirements"]]
        # "n/a" -> blank, "2-3 weeks" -> HIGH, "3 months" -> HIGH, "" -> blank, "2 days" -> LOW
        assert efforts == ["", "HIGH", "HIGH", "", "LOW"]

    def test_top_level_metadata_and_score_are_kept(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        assert out["framework"] == "CSRD"
        assert out["overall_score"] == 45.0
        assert out["confidence_score"] == pytest.approx(0.82)
        assert out["assessment_date"] == "2026-10-23"
        assert out["next_assessment_date"] == "2027-04-01"
        assert out["status_summary"]["in_evolution"] == 1


class TestPromptShapedRecommendations:
    def test_string_recommendations_are_not_dropped(self):
        out = _normaliser()(_prompt_shaped_gap_result(), "CSRD")
        recs = out["recommendations"]
        assert len(recs) == 3
        assert recs[0]["priority"] == "P1"
        assert recs[0]["action"].startswith("P1: Contract a limited assurance")
        assert recs[1]["priority"] == "P2"
        # No priority token in the text -> blank, not a made-up P3.
        assert recs[2]["priority"] == ""
        assert recs[2]["action"] == "Monitor the Omnibus I transposition timeline."

    def test_dict_recommendations_still_accepted(self):
        raw = {
            "recommendations": [
                {"priority": "p2", "action": "Do X", "effort": "LOW", "deadline": "2027-01-01"},
                {"recommendation": "Do Y"},
                {"text": "   "},
                "   ",
                42,
            ]
        }
        recs = _normaliser()(raw, "GDPR")["recommendations"]
        assert recs == [
            {"priority": "P2", "action": "Do X", "effort": "LOW", "deadline": "2027-01-01"},
            {"priority": "", "action": "Do Y", "effort": "", "deadline": ""},
        ]


class TestLegacyShapeStillWorks:
    def test_old_field_names(self):
        raw = {
            "framework": "GDPR",
            "overall_score": 80,
            "requirements": [
                {
                    "name": "Lawful basis",
                    "status": "compliant",
                    "description": "ok",
                    "remediation": "none",
                    "effort": "low",
                }
            ],
            "recommendations": [{"priority": "P3", "action": "Keep it up"}],
        }
        out = _normaliser()(raw, "GDPR")
        assert out["requirements"][0]["name"] == "Lawful basis"
        assert out["requirements"][0]["status"] == "COMPLIANT"
        assert out["requirements"][0]["effort"] == "LOW"
        assert out["recommendations"][0]["priority"] == "P3"

    def test_non_dict_input_yields_empty_report(self):
        out = _normaliser()("garbage", "DORA")
        assert out["framework"] == "DORA"
        assert out["requirements"] == [] and out["recommendations"] == []

    def test_score_is_derived_when_the_model_omits_it(self):
        raw = {
            "requirements": [
                {"requirement_id": "A", "status": "COMPLIANT"},
                {"requirement_id": "B", "status": "PARTIALLY_COMPLIANT"},
                {"requirement_id": "C", "status": "NON_COMPLIANT"},
                {"requirement_id": "D", "status": "NOT_APPLICABLE"},
            ]
        }
        # (1 + 0.5) / (4 - 1) * 100 = 50.0
        assert _normaliser()(raw, "NIS2")["overall_score"] == 50.0

    def test_explicit_zero_score_is_respected(self):
        raw = {"overall_score": 0, "requirements": [{"requirement_id": "A", "status": "COMPLIANT"}]}
        assert _normaliser()(raw, "NIS2")["overall_score"] == 0.0


class TestStatusAndEffortHelpers:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("IN_EVOLUTION", "IN_EVOLUTION"),
            ("in evolution", "IN_EVOLUTION"),
            ("Pending legislation", "IN_EVOLUTION"),
            ("Partially compliant", "PARTIALLY_COMPLIANT"),
            ("non-compliant", "NON_COMPLIANT"),
            ("N/A", "NOT_APPLICABLE"),
            ("Not applicable", "NOT_APPLICABLE"),
            ("Compliant", "COMPLIANT"),
            ("???", "NON_COMPLIANT"),
        ],
    )
    def test_normalise_status(self, raw, expected):
        from src.api.routers.reports import _normalise_status

        assert _normalise_status(raw) == expected

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("HIGH", "HIGH"),
            ("medium", "MEDIUM"),
            ("Low", "LOW"),
            ("8 hours", "LOW"),
            ("2-3 days", "LOW"),
            ("10 days", "MEDIUM"),
            ("1 week", "MEDIUM"),
            ("4-6 weeks", "HIGH"),
            ("3 months", "HIGH"),
            ("2 settimane", "MEDIUM"),
            ("", ""),
            (None, ""),
            ("n/a", ""),
        ],
    )
    def test_normalise_effort(self, raw, expected):
        from src.api.routers.reports import _normalise_effort

        assert _normalise_effort(raw) == expected
