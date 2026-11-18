"""Calibration of QA_MIN_DENSE_SCORE from a golden v2 run (metrics.relevance_calibration).

Every Q&A answer reports ``best_dense_score``, the score the threshold is
compared with; the run says up to which value no answerable record abstains.
"""

from tests.validation.golden_v2 import load_golden_v2_test_cases
from tests.validation.metrics import aggregate_suite_results, relevance_calibration
from tests.validation.response_parser import _parse_qa
from tests.validation.runner import generate_report
from tests.validation.schemas import TestResult


def _cases():
    cases = load_golden_v2_test_cases()
    answerable = [tc for tc in cases if not tc.expected_answer["abstain"]]
    abstain = [tc for tc in cases if tc.expected_answer["abstain"]]
    return cases, answerable, abstain


def _result(case_id, score):
    output = {"answer": "x", "citations": []}
    if score is not None:
        output["best_dense_score"] = score
    return TestResult(test_case_id=case_id, normaai_output=output)


def test_the_lowest_answerable_score_and_the_abstentions_below_it():
    cases, answerable, abstain = _cases()
    results = [
        _result(answerable[0].id, 0.86),
        _result(answerable[1].id, 0.82),
        _result(answerable[2].id, 0.90),
        _result(abstain[0].id, 0.79),
        _result(abstain[1].id, 0.85),
        _result(abstain[2].id, None),  # not scored
    ]
    calibration = relevance_calibration(results, cases)
    assert calibration["answerable_scored"] == 3 and calibration["abstain_scored"] == 2
    assert calibration["answerable_min"] == 0.82
    assert calibration["answerable_min_case"] == answerable[1].id
    assert calibration["answerable_median"] == 0.86
    assert calibration["abstain_max"] == 0.85
    assert calibration["abstain_below_answerable_min"] == [abstain[0].id]


def test_none_when_no_answer_carries_the_score():
    cases, answerable, _ = _cases()
    assert relevance_calibration([_result(answerable[0].id, None)], cases) is None


def test_the_parser_keeps_the_score():
    parsed = _parse_qa({"answer": "a", "citations": [], "best_dense_score": 0.8123}, {})
    assert parsed["best_dense_score"] == 0.8123
    assert "best_dense_score" not in _parse_qa({"answer": "a", "citations": []}, {})


def test_the_report_carries_the_calibration():
    cases, answerable, abstain = _cases()
    results = [_result(answerable[0].id, 0.84), _result(abstain[0].id, 0.71)]
    suite = aggregate_suite_results("golden_v2", results, cases)
    assert suite.relevance_calibration["abstain_below_answerable_min"] == [abstain[0].id]
    report = generate_report(suite, mode="api")
    assert "RELEVANCE: best_dense_score" in report
    assert f"min 0.8400 ({answerable[0].id})" in report
