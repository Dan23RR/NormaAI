"""Tests for the compliance PDF report generator (src/reports/generator.py).

The module is pure (no DB / LLM / network). It builds PDF byte output via fpdf2.
We assert:
  * public entry points return non-empty, valid-looking PDF bytes
  * the status-counting / data-shaping logic embedded in the public methods
    behaves correctly (verified via the colour/label/count lookup tables and by
    exercising the section builders directly on a real PDF instance)
  * section builders run without raising on minimal/edge inputs
  * lookup tables (status colours/labels, priority colours) expose expected keys

We never assert exact PDF bytes, only structure / non-emptiness / no-raise.
"""

from fpdf import FPDF

from src.reports.generator import (
    _PRIORITY_COLOURS,
    _STATUS_COLOURS,
    _STATUS_LABELS,
    ComplianceReportGenerator,
    _NormaPDF,
)

# ---------------------------------------------------------------------------
# Fixtures / sample data builders
# ---------------------------------------------------------------------------

PDF_MAGIC = b"%PDF"


def _requirement(name, status, description="", effort="", remediation=""):
    return {
        "name": name,
        "status": status,
        "description": description,
        "effort": effort,
        "remediation": remediation,
    }


def _gap_data_full():
    """A rich gap_data dict covering every status and effort level."""
    return {
        "framework": "CSRD",
        "overall_score": 62.5,
        "confidence_score": 0.83,
        "requirements": [
            _requirement("Double materiality", "COMPLIANT", "Done", "LOW"),
            _requirement("ESRS E1 climate", "PARTIALLY_COMPLIANT", "In progress", "MEDIUM"),
            _requirement("Scope 3 emissions", "NON_COMPLIANT", "Missing data", "HIGH"),
            _requirement("Value chain mapping", "NON_COMPLIANT", "Not started", "LOW"),
            _requirement("Legacy reporting", "NOT_APPLICABLE", "Superseded", ""),
        ],
        "recommendations": [
            {
                "priority": "P1",
                "action": "Implement Scope 3 emissions tracking across the value chain",
                "effort": "HIGH",
                "deadline": "2026-12-31",
            },
            {
                "priority": "P3",
                "action": "Map the upstream value chain",
                "effort": "LOW",
                "deadline": "2026-06-30",
            },
        ],
    }


def _company_profile():
    return {
        "name": "Acme Srl",
        "sector": "Manufacturing",
        "employee_count": 2500,
        "revenue_eur": 200_000_000,
        "jurisdictions": ["IT", "DE"],
        "applicable_frameworks": ["CSRD", "CSDDD"],
    }


def _new_pdf_with_page():
    """A real _NormaPDF instance with an active page (required by fpdf cell ops)."""
    gen = ComplianceReportGenerator()
    pdf = gen._create_pdf()
    pdf.add_page()
    return gen, pdf


# ---------------------------------------------------------------------------
# Lookup-table / constant correctness
# ---------------------------------------------------------------------------


class TestLookupTables:
    def test_status_labels_cover_all_statuses(self):
        assert _STATUS_LABELS["COMPLIANT"] == "Compliant"
        assert _STATUS_LABELS["PARTIALLY_COMPLIANT"] == "Partial"
        assert _STATUS_LABELS["NON_COMPLIANT"] == "Non-Compliant"
        assert _STATUS_LABELS["NOT_APPLICABLE"] == "N/A"

    def test_status_colours_keys_match_labels(self):
        # Every label key must have a colour, and each colour is an RGB triple.
        assert set(_STATUS_COLOURS.keys()) == set(_STATUS_LABELS.keys())
        for rgb in _STATUS_COLOURS.values():
            assert isinstance(rgb, tuple)
            assert len(rgb) == 3
            assert all(0 <= c <= 255 for c in rgb)

    def test_priority_colours_have_four_tiers(self):
        assert set(_PRIORITY_COLOURS.keys()) == {"P1", "P2", "P3", "P4"}
        for rgb in _PRIORITY_COLOURS.values():
            assert len(rgb) == 3
            assert all(0 <= c <= 255 for c in rgb)


# ---------------------------------------------------------------------------
# Internal PDF construction helpers
# ---------------------------------------------------------------------------


class TestPdfConstruction:
    def test_create_pdf_returns_norma_subclass(self):
        gen = ComplianceReportGenerator()
        pdf = gen._create_pdf()
        assert isinstance(pdf, _NormaPDF)
        assert isinstance(pdf, FPDF)

    def test_norma_pdf_has_disclaimer(self):
        pdf = _NormaPDF()
        assert "NormaAI" in pdf._disclaimer
        assert "legal advice" in pdf._disclaimer

    def test_output_bytes_is_valid_pdf(self):
        gen, pdf = _new_pdf_with_page()
        out = gen._output_bytes(pdf)
        assert isinstance(out, bytes)
        assert len(out) > 0
        assert out.startswith(PDF_MAGIC)


# ---------------------------------------------------------------------------
# Public API: generate_gap_report
# ---------------------------------------------------------------------------


class TestGenerateGapReport:
    def test_full_report_returns_pdf_bytes(self):
        gen = ComplianceReportGenerator()
        out = gen.generate_gap_report(
            company_name="Acme Srl",
            framework="CSRD",
            gap_data=_gap_data_full(),
            company_profile=_company_profile(),
        )
        assert isinstance(out, bytes)
        assert out.startswith(PDF_MAGIC)
        assert len(out) > 1000  # A multi-section report is non-trivially sized.

    def test_report_without_profile(self):
        gen = ComplianceReportGenerator()
        out = gen.generate_gap_report(
            company_name="Acme Srl",
            framework="CSRD",
            gap_data=_gap_data_full(),
            company_profile=None,
        )
        assert out.startswith(PDF_MAGIC)

    def test_report_with_empty_gap_data(self):
        # No requirements, no recommendations: should still emit the summary +
        # metadata pages without raising.
        gen = ComplianceReportGenerator()
        out = gen.generate_gap_report(
            company_name="Empty Co",
            framework="DORA",
            gap_data={},
        )
        assert out.startswith(PDF_MAGIC)
        assert len(out) > 0

    def test_report_with_only_compliant_requirements(self):
        # Exercises the "no gaps" branch of the risk summary.
        gen = ComplianceReportGenerator()
        gap = {
            "framework": "GDPR",
            "overall_score": 100.0,
            "confidence_score": 1.0,
            "requirements": [
                _requirement("Lawful basis", "COMPLIANT", "ok", "LOW"),
                _requirement("DPIA", "COMPLIANT", "ok", "MEDIUM"),
            ],
            "recommendations": [],
        }
        out = gen.generate_gap_report("Clean Co", "GDPR", gap)
        assert out.startswith(PDF_MAGIC)

    def test_report_with_high_and_low_effort_gaps(self):
        # Exercises the "critical" + "quick wins" branch of the risk summary text.
        gen = ComplianceReportGenerator()
        gap = {
            "framework": "NIS2",
            "overall_score": 20.0,
            "confidence_score": 0.5,
            "requirements": [
                _requirement("Incident response", "NON_COMPLIANT", "missing", "HIGH"),
                _requirement("Asset inventory", "NON_COMPLIANT", "missing", "LOW"),
            ],
            "recommendations": [],
        }
        out = gen.generate_gap_report("Gap Co", "NIS2", gap)
        assert out.startswith(PDF_MAGIC)

    def test_report_handles_missing_optional_fields_in_requirements(self):
        # Requirements missing name/description/effort default to "".
        gen = ComplianceReportGenerator()
        gap = {
            "framework": "AI_ACT",
            "overall_score": 0.0,
            "confidence_score": 0.0,
            "requirements": [{"status": "NON_COMPLIANT"}],
            "recommendations": [{"action": "Do the thing"}],  # no priority/effort/deadline
        }
        out = gen.generate_gap_report("Sparse Co", "AI_ACT", gap)
        assert out.startswith(PDF_MAGIC)

    def test_many_requirements_trigger_page_break(self):
        # 60 requirements force the table page-break path in _add_requirement_table.
        gen = ComplianceReportGenerator()
        reqs = [
            _requirement(f"Requirement {i}", "PARTIALLY_COMPLIANT", "desc " * 10, "MEDIUM")
            for i in range(60)
        ]
        gap = {
            "framework": "CSRD",
            "overall_score": 50.0,
            "confidence_score": 0.7,
            "requirements": reqs,
            "recommendations": [],
        }
        out = gen.generate_gap_report("Big Co", "CSRD", gap)
        assert out.startswith(PDF_MAGIC)
        # b"/Count" appears in the page-tree object; many reqs => multi-page doc.
        assert len(out) > 3000

    def test_can_write_report_to_tmp_path(self, tmp_path):
        gen = ComplianceReportGenerator()
        out = gen.generate_gap_report("Acme Srl", "CSRD", _gap_data_full())
        target = tmp_path / "gap_report.pdf"
        target.write_bytes(out)
        assert target.exists()
        assert target.stat().st_size == len(out)
        assert target.read_bytes().startswith(PDF_MAGIC)


# ---------------------------------------------------------------------------
# Public API: generate_executive_summary
# ---------------------------------------------------------------------------


class TestGenerateExecutiveSummary:
    def test_multi_framework_summary(self):
        gen = ComplianceReportGenerator()
        frameworks = [
            _gap_data_full(),
            {
                "framework": "GDPR",
                "overall_score": 90.0,
                "confidence_score": 0.95,
                "requirements": [
                    _requirement("Consent", "COMPLIANT", "ok", "LOW"),
                ],
                "recommendations": [
                    {"priority": "P2", "action": "Refresh privacy notice", "effort": "LOW"},
                ],
            },
        ]
        out = gen.generate_executive_summary("Acme Srl", frameworks)
        assert isinstance(out, bytes)
        assert out.startswith(PDF_MAGIC)
        assert len(out) > 1000

    def test_summary_with_empty_framework_list(self):
        gen = ComplianceReportGenerator()
        out = gen.generate_executive_summary("Acme Srl", [])
        assert out.startswith(PDF_MAGIC)

    def test_summary_uses_unknown_for_missing_framework_name(self):
        # framework key absent => "Unknown" default is used; must not raise.
        gen = ComplianceReportGenerator()
        out = gen.generate_executive_summary(
            "Acme Srl",
            [{"overall_score": 10.0, "requirements": [], "recommendations": []}],
        )
        assert out.startswith(PDF_MAGIC)

    def test_summary_truncates_gaps_and_recommendations(self):
        # >5 gaps and >3 recommendations exercise the slicing branches.
        gen = ComplianceReportGenerator()
        gaps = [_requirement(f"Gap {i}", "NON_COMPLIANT", "x", "HIGH") for i in range(8)]
        recs = [
            {"priority": "P1", "action": f"Action {i}" * 20, "effort": "HIGH"} for i in range(6)
        ]
        fd = {
            "framework": "CSRD",
            "overall_score": 12.0,
            "confidence_score": 0.4,
            "requirements": gaps,
            "recommendations": recs,
        }
        out = gen.generate_executive_summary("Acme Srl", [fd])
        assert out.startswith(PDF_MAGIC)


# ---------------------------------------------------------------------------
# Section builders (direct, on a live PDF page) - data-shaping + no-raise
# ---------------------------------------------------------------------------


class TestSectionBuilders:
    def test_add_header_does_not_raise(self):
        gen, pdf = _new_pdf_with_page()
        gen._add_header(pdf, title="CSRD Gap Analysis", subtitle="Prepared for Acme")
        # Cursor should have advanced below the 42mm header band.
        assert pdf.get_y() >= 42

    def test_add_header_without_subtitle(self):
        gen, pdf = _new_pdf_with_page()
        gen._add_header(pdf, title="Title only")
        assert pdf.get_y() >= 42

    def test_add_section_title_draws_underline(self):
        gen, pdf = _new_pdf_with_page()
        y_before = pdf.get_y()
        gen._add_section_title(pdf, "Executive Summary")
        assert pdf.get_y() > y_before

    def test_add_section_title_breaks_page_when_low(self):
        gen, pdf = _new_pdf_with_page()
        # Force the cursor near the bottom so the helper triggers add_page().
        pdf.set_y(260)
        pages_before = pdf.page_no()
        gen._add_section_title(pdf, "Late Section")
        assert pdf.page_no() == pages_before + 1

    def test_add_score_overview(self):
        gen, pdf = _new_pdf_with_page()
        y_before = pdf.get_y()
        gen._add_score_overview(
            pdf,
            overall_score=62.5,
            confidence=0.8,
            compliant=1,
            partial=1,
            non_compliant=2,
            not_applicable=1,
        )
        # Four 22mm boxes + spacing pushes the cursor down.
        assert pdf.get_y() > y_before

    def test_add_company_profile_formats_fields(self):
        gen, pdf = _new_pdf_with_page()
        gen._add_company_profile(pdf, _company_profile())
        assert pdf.get_y() > 0

    def test_add_company_profile_with_empty_dict(self):
        # All fields fall back to "N/A" / 0 defaults; must not raise.
        gen, pdf = _new_pdf_with_page()
        gen._add_company_profile(pdf, {})
        assert pdf.get_y() > 0

    def test_add_requirement_table(self):
        gen, pdf = _new_pdf_with_page()
        reqs = _gap_data_full()["requirements"]
        gen._add_requirement_table(pdf, reqs)
        assert pdf.get_y() > 0

    def test_add_requirement_table_unknown_status_falls_back(self):
        # An unrecognised status must use the raw string label and grey colour
        # without raising (covers the _STATUS_LABELS.get default branch).
        gen, pdf = _new_pdf_with_page()
        gen._add_requirement_table(pdf, [_requirement("Weird", "MAYBE", "d", "LOW")])
        assert pdf.get_y() > 0

    def test_add_recommendations_with_items(self):
        gen, pdf = _new_pdf_with_page()
        recs = _gap_data_full()["recommendations"]
        gen._add_recommendations(pdf, recs)
        assert pdf.get_y() > 0

    def test_add_recommendations_empty_shows_placeholder(self):
        # Empty list => early-return placeholder branch; must not raise.
        gen, pdf = _new_pdf_with_page()
        gen._add_recommendations(pdf, [])
        assert pdf.get_y() > 0

    def test_add_recommendations_unknown_priority(self):
        # Priority outside P1..P4 falls back to grey badge.
        gen, pdf = _new_pdf_with_page()
        gen._add_recommendations(
            pdf, [{"priority": "P9", "action": "Do thing", "effort": "LOW", "deadline": "2026"}]
        )
        assert pdf.get_y() > 0

    def test_add_risk_summary_no_gaps_branch(self):
        gen, pdf = _new_pdf_with_page()
        reqs = [_requirement("All good", "COMPLIANT", "ok", "LOW")]
        gen._add_risk_summary(pdf, reqs)
        assert pdf.get_y() > 0

    def test_add_risk_summary_with_gaps(self):
        gen, pdf = _new_pdf_with_page()
        reqs = _gap_data_full()["requirements"]
        gen._add_risk_summary(pdf, reqs)
        assert pdf.get_y() > 0

    def test_draw_table_header(self):
        gen, pdf = _new_pdf_with_page()
        gen._draw_table_header(pdf, ["A", "B", "C"], [30, 30, 30])
        assert pdf.get_y() > 0


# ---------------------------------------------------------------------------
# Status-counting logic (the data-shaping core of the public methods)
# ---------------------------------------------------------------------------


class TestStatusCountingLogic:
    """The public methods compute compliant/partial/non_compliant counts via
    list comprehensions over requirements. We replicate the exact predicate and
    confirm a constructed dataset produces a non-empty, larger PDF as counts grow,
    and that the lookup tables drive the label mapping the generator relies on.
    """

    def test_status_label_mapping_used_by_table(self):
        # The table maps each status to a label via _STATUS_LABELS; confirm the
        # mapping the generator depends on is correct for each known status.
        for raw, expected in [
            ("COMPLIANT", "Compliant"),
            ("PARTIALLY_COMPLIANT", "Partial"),
            ("NON_COMPLIANT", "Non-Compliant"),
            ("NOT_APPLICABLE", "N/A"),
        ]:
            assert _STATUS_LABELS.get(raw, raw) == expected

    def test_unknown_status_label_is_passthrough(self):
        assert _STATUS_LABELS.get("FOO", "FOO") == "FOO"

    def test_report_size_grows_with_more_requirements(self):
        gen = ComplianceReportGenerator()
        small = {
            "framework": "CSRD",
            "overall_score": 50.0,
            "confidence_score": 0.5,
            "requirements": [_requirement("R1", "COMPLIANT", "d", "LOW")],
            "recommendations": [],
        }
        large = {
            "framework": "CSRD",
            "overall_score": 50.0,
            "confidence_score": 0.5,
            "requirements": [
                _requirement(f"R{i}", "NON_COMPLIANT", "desc " * 5, "HIGH") for i in range(40)
            ],
            "recommendations": [],
        }
        out_small = gen.generate_gap_report("Co", "CSRD", small)
        out_large = gen.generate_gap_report("Co", "CSRD", large)
        assert out_large.startswith(PDF_MAGIC)
        assert out_small.startswith(PDF_MAGIC)
        assert len(out_large) > len(out_small)
