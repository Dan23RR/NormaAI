"""The golden v2 measures, each on its own, and the re-scoring of a stored report.

``passed_cases`` counts the cases whose recall reaches the threshold: a record
that expects an abstention expects no citation, so it is "passed" whatever the
system answers. The 96 / 101 of 2026-11-09 was 85 of 90 answerable questions
with the expected article cited, plus the 11 abstention records.
"""

import json

from tests.validation import rescore as rescore_mod
from tests.validation import schemas
from tests.validation.golden_v2 import load_golden_v2_test_cases
from tests.validation.metrics import (
    aggregate_suite_results,
    calculate_test_metrics,
    verified_citation_counts,
)
from tests.validation.runner import generate_report

CASES = load_golden_v2_test_cases()
BY_ID = {tc.id: tc for tc in CASES}


def _cited(article, verified=True):
    return {"article": article, "text": "quote", "framework": "GDPR", "verified": verified}


def _run(case_id, answer, citations, **output):
    tc = BY_ID[case_id]
    return calculate_test_metrics(tc, {"answer": answer, "citations": citations, **output})


def _suite(results):
    return aggregate_suite_results("golden_v2", results, [BY_ID[r.test_case_id] for r in results])


def test_the_abstain_records_pass_by_definition():
    # A refuse record answered with an invented article is still "passed": it
    # expects no citation. Its answer checks are what catch it.
    wrong = _run(
        "refuse-004", "L'articolo 999 stabilisce il diritto all'oblio.", [_cited("Art. 999")]
    )
    assert wrong.recall == 1.0
    assert wrong.answer_checks["passed"] is False
    suite = _suite([wrong])
    assert suite.passed_cases == 1
    assert (suite.abstain_abstained, suite.abstain_content_passed) == (0, 0)


def test_each_measure_on_its_own():
    results = [
        # answerable, article cited, content right
        _run(
            "gdpr-033-001",
            "Entro 72 ore dalla conoscenza della violazione [GDPR, Art. 33(1)].",
            [_cited("Art. 33(1)")],
        ),
        # answerable, article cited, but an abstention in its opening
        _run(
            "gdpr-017-002",
            "I don't have sufficient information to answer this [GDPR, Art. 17(3)].",
            [_cited("Art. 17(3)")],
        ),
        # answerable, another article cited, content right
        _run(
            "nis2-023-002",
            "Within 72 hours of becoming aware of it [NIS2, Art. 23(1)].",
            [_cited("Art. 23(1)", verified=False)],
        ),
        # answerable, ended in an error
        calculate_test_metrics(BY_ID["dora-028-001"], {}, error="HTTP 503"),
        # abstain record, abstained
        _run("refuse-001", "Non dispongo di informazioni sufficienti per rispondere.", []),
        # abstain record, invented the answer
        _run("refuse-004", "L'articolo 999 stabilisce il diritto all'oblio.", [_cited("Art. 999")]),
    ]
    suite = _suite(results)
    # Kept for the tools that read reports: the number the runner always printed.
    assert (suite.total_cases, suite.passed_cases, suite.error_cases) == (6, 4, 1)
    assert suite.answerable_cases == 4
    assert suite.answerable_article_cited == 2
    assert suite.answerable_answered == 2
    assert suite.answerable_content_passed == 2
    assert suite.answerable_article_and_content == 1
    assert (suite.abstain_cases, suite.abstain_abstained, suite.abstain_content_passed) == (2, 1, 1)
    assert (suite.content_checks_passed, suite.content_checks_total) == (3, 6)
    # Every answer together: 3 of 4 citations verified (the abstention has none).
    assert (suite.citations_verified, suite.citations_scored) == (3, 4)
    report = generate_report(suite, mode="api")
    assert "Answerable: expected article cited: 2 / 4" in report
    assert "Abstain cases: abstained: 1 / 2" in report


def test_a_legacy_suite_has_no_golden_measures():
    tc = load_golden_v2_test_cases()[0].model_copy(update={"expected_answer": None})
    suite = aggregate_suite_results(
        "golden_set", [calculate_test_metrics(tc, {"citations": []})], [tc]
    )
    assert suite.answerable_cases is None and suite.content_checks_total is None
    assert "EACH MEASURE ON ITS OWN" not in generate_report(suite)


def test_the_pipeline_abstention_reason_counts():
    result = _run(
        "gdpr-033-001",
        "Non posso rispondere con una fonte: nessuno dei passaggi trovati è abbastanza vicino.",
        [],
        abstention_reason="low_relevance",
    )
    assert result.answer_checks["abstained"] is True


def test_verified_citation_counts():
    assert verified_citation_counts({"verified_citations": 2, "citations_total": 3}) == (2, 3)
    assert verified_citation_counts({"verified_citations": 0, "citations_total": 0}) is None
    assert verified_citation_counts({"citations": [_cited("Art. 1"), {"article": "x"}]}) == (1, 2)
    assert verified_citation_counts({"citations": [{"article": "x"}]}) is None


# ─── Re-scoring a stored report ───────────────────────────────────


def _stored_report():
    """A report as the runner of 2026-11-18 stored it: the old verdicts kept."""
    good = _run(
        "csrd-19a-001",
        "Si applica alle imprese con ricavi superiori a 450.000.000 EUR e più di 1.000 "
        "dipendenti [CSRD, Art. 19 bis]. Un'impresa che ne supera una sola non rientra "
        "nell'obbligo.",
        [_cited("Art. 19a")],
    )
    old = good.model_copy(
        update={
            "answer_checks": {
                "passed": False,
                "expected_abstain": False,
                "abstained": True,  # the checker of the day: "non rientra"
                "missing": [],
                "forbidden": [],
            }
        }
    )
    gone = schemas.TestResult(test_case_id="removed-001", normaai_output={"answer": "x"})
    return schemas.SuiteResult(suite_name="golden_v2", results=[old, gone], total_cases=2)


def test_rescore_compares_the_stored_and_the_current_verdicts():
    stored, rescored, left_out = rescore_mod.rescore(_stored_report(), CASES)
    assert left_out == ["removed-001"]
    assert (stored.answerable_answered, rescored.answerable_answered) == (0, 1)
    assert (stored.content_checks_passed, rescored.content_checks_passed) == (0, 1)
    text = rescore_mod.comparison("report.json", stored, rescored, left_out)
    assert "Answerable: answered, no abstention" in text
    assert "csrd-19a-001: passed False -> True (abstained True -> False)" in text
    assert "removed-001" in text


def test_rescore_cli_writes_the_rescored_report(tmp_path, capsys):
    report = tmp_path / "golden_v2_api_2026-11-18T10-46-13.json"
    report.write_text(_stored_report().model_dump_json(), encoding="utf-8")
    assert rescore_mod.main([str(report), "--out-dir", str(tmp_path / "out")]) == 0
    written = json.loads(
        (tmp_path / "out" / "golden_v2_api_2026-11-18T10-46-13_rescored.json").read_text(
            encoding="utf-8"
        )
    )
    assert written["answerable_answered"] == 1
    assert written["passed_cases"] == 1  # the existing fields are kept
    assert (tmp_path / "out" / "golden_v2_api_2026-11-18T10-46-13_rescored.txt").is_file()
    assert "Re-scored" in capsys.readouterr().out
