"""Offline schema checks for the golden set v2 (test_cases/golden_v2.jsonl).

Run explicitly (tests/validation is excluded from the default offline suite):

    python -m pytest tests/validation/test_golden_v2_schema.py -q -p no:cacheprovider -o addopts=""

No network: the EUR-Lex re-verification lives in verify_golden_v2.py.
"""

import json
import re
from collections import Counter

import pytest

from tests.validation.golden_v2 import (
    GOLDEN_V2_PATH,
    check_answer,
    load_golden_v2,
    load_golden_v2_test_cases,
)
from tests.validation.metrics import calculate_test_metrics
from tests.validation.schemas import (
    CELEX_PATTERN,
    GOLDEN_ID_PATTERN,
    GoldenFramework,
    GoldenKind,
    GoldenLang,
    GoldenV2Record,
    GoldenVerification,
)

REQUIRED_TOP_LEVEL = {
    "id",
    "lang",
    "framework",
    "question",
    "kind",
    "expected",
    "source_url",
    "verified_on",
    "verification",
    "notes",
}
REQUIRED_EXPECTED = {
    "celex",
    "article",
    "paragraph",
    "quote",
    "answer_must_contain",
    "answer_must_not_contain",
    "abstain",
}
COVERAGE = {
    # framework -> articles that the set must cover (task brief)
    GoldenFramework.AI_ACT: {"50", "113", "3", "6", "26", "5"},
    GoldenFramework.GDPR: {"6", "13", "17", "30", "33", "35"},
    GoldenFramework.NIS2: {"21", "23", "3"},
    GoldenFramework.DORA: {"5", "17", "18", "19", "28"},
    GoldenFramework.CSRD: {"19a", "29a"},
    GoldenFramework.CSDDD: {"2", "37"},
    GoldenFramework.TAXONOMY: {"3", "8"},
    GoldenFramework.CRA: {"14", "71"},
}


@pytest.fixture(scope="module")
def raw_records() -> list[dict]:
    lines = GOLDEN_V2_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture(scope="module")
def records() -> list[GoldenV2Record]:
    return load_golden_v2()


def test_file_is_one_json_object_per_line(raw_records):
    assert 80 <= len(raw_records) <= 120
    for rec in raw_records:
        assert isinstance(rec, dict)
        assert set(rec) >= REQUIRED_TOP_LEVEL, f"{rec.get('id')}: missing top-level keys"
        assert set(rec["expected"]) >= REQUIRED_EXPECTED, f"{rec['id']}: missing expected keys"


def test_every_record_validates_against_schema(records, raw_records):
    assert len(records) == len(raw_records)


def test_ids_unique_and_well_formed(records):
    ids = [r.id for r in records]
    assert len(ids) == len(set(ids)), "duplicate ids"
    for rid in ids:
        assert re.match(GOLDEN_ID_PATTERN, rid), rid


def test_enums(records):
    for r in records:
        assert r.lang in (GoldenLang.IT, GoldenLang.EN)
        assert isinstance(r.kind, GoldenKind)
        assert isinstance(r.framework, GoldenFramework)
        assert isinstance(r.verification, GoldenVerification)


def test_celex_patterns_and_source_urls(records):
    for r in records:
        exp = r.expected
        for celex in (exp.celex, exp.quote_celex):
            if celex is not None:
                assert re.match(CELEX_PATTERN, celex), f"{r.id}: bad CELEX {celex}"
        if not exp.abstain:
            assert exp.celex and exp.article, r.id
            assert r.source_url and r.source_url.startswith("https://eur-lex.europa.eu/"), r.id
            cited = exp.quote_celex or exp.celex
            assert cited in r.source_url, f"{r.id}: source_url does not point at {cited}"


def test_fetched_records_have_quotes_in_question_language(records):
    for r in records:
        if r.verification == GoldenVerification.FETCHED and not r.expected.abstain:
            quote = r.expected.quote
            assert len(quote.strip()) >= 30, f"{r.id}: quote too short to be a passage"
            # Cheap language sanity check on the quote.
            low = quote.lower()
            if r.lang == GoldenLang.IT:
                assert " shall " not in low, f"{r.id}: English quote on an Italian question"
            else:
                assert " di " not in f" {low} " or " shall " in low or " the " in low, r.id


def test_abstain_consistency(records):
    for r in records:
        exp = r.expected
        if r.kind == GoldenKind.REFUSE:
            assert exp.abstain, r.id
        if exp.abstain:
            assert r.kind in (GoldenKind.REFUSE, GoldenKind.INJECTION), r.id
            assert exp.quote == "" and not exp.answer_must_contain, r.id
        else:
            assert exp.quote.strip() or r.verification == GoldenVerification.UNVERIFIED, r.id
            assert r.framework != GoldenFramework.NONE, r.id


def test_unverified_share_and_kind_counts(records):
    unverified = [r for r in records if r.verification == GoldenVerification.UNVERIFIED]
    assert len(unverified) <= 0.15 * len(records), [r.id for r in unverified]
    kinds = Counter(r.kind for r in records)
    assert kinds[GoldenKind.REFUSE] >= 10
    assert kinds[GoldenKind.INJECTION] >= 6


def test_language_mix(records):
    share_it = sum(1 for r in records if r.lang == GoldenLang.IT) / len(records)
    assert 0.55 <= share_it <= 0.65, f"Italian share {share_it:.0%}, expected ~60%"


def test_framework_and_article_coverage(records):
    covered: dict[GoldenFramework, set[str]] = {}
    for r in records:
        if r.expected.article:
            covered.setdefault(r.framework, set()).add(r.expected.article)
    for framework, articles in COVERAGE.items():
        missing = articles - covered.get(framework, set())
        assert not missing, f"{framework.value}: articles not covered: {sorted(missing)}"


def test_must_not_contain_does_not_contradict_must_contain(records):
    for r in records:
        exp = r.expected
        for forbidden in exp.answer_must_not_contain:
            for required in exp.answer_must_contain:
                assert forbidden.lower() not in required.lower(), r.id


def test_dates_and_verification_flags(records):
    for r in records:
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", r.verified_on), r.id
        assert r.verified_on <= "2026-12-31", r.id


def test_bridge_to_legacy_runner(records):
    cases = load_golden_v2_test_cases()
    assert len(cases) == len(records)
    by_id = {c.id: c for c in cases}
    for r in records:
        case = by_id[r.id]
        assert case.task_type == "qa"
        assert case.query == r.question
        assert "golden_v2" in case.tags
        assert case.expected_answer is not None
        if r.expected.abstain:
            assert case.expected_findings == []
        else:
            assert len(case.expected_findings) == 1
            assert case.expected_findings[0].article.startswith(f"Art. {r.expected.article}")


def test_article_ref_rendering():
    base = {
        "id": "demo-014-001",
        "lang": "en",
        "framework": "CRA",
        "question": "A question long enough to pass validation?",
        "kind": "factual",
        "verified_on": "2026-10-23",
        "verification": "fetched",
        "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R2847",
    }
    for paragraph, ref in [
        ("2(a)", "Art. 14(2)(a)"),
        ("1", "Art. 14(1)"),
        ("(c)", "Art. 14(c)"),
        (None, "Art. 14"),
    ]:
        rec = GoldenV2Record.model_validate(
            {
                **base,
                "expected": {
                    "celex": "32024R2847",
                    "article": "14",
                    "paragraph": paragraph,
                    "quote": "x" * 40,
                },
            }
        )
        assert rec.article_ref == ref


def test_check_answer_semantics():
    exp = {
        "answer_must_contain": ["72 hours"],
        "answer_must_not_contain": ["48 hours"],
        "abstain": False,
    }
    ok = check_answer(
        exp, "Notify within 72 hours [GDPR, Art. 33(1)].", [{"article": "Art. 33(1)"}]
    )
    assert ok["passed"] and not ok["missing"] and not ok["forbidden"]
    wrong = check_answer(exp, "Notify within 48 hours.", [{"article": "Art. 33(1)"}])
    assert (
        not wrong["passed"]
        and wrong["missing"] == ["72 hours"]
        and wrong["forbidden"] == ["48 hours"]
    )
    abstained = check_answer(
        exp, "I don't have sufficient information in my regulatory database.", []
    )
    assert not abstained["passed"] and abstained["abstained"]
    refuse = {"answer_must_contain": [], "answer_must_not_contain": ["22%"], "abstain": True}
    assert check_answer(refuse, "I don't have sufficient information to answer this.", [])["passed"]
    assert not check_answer(refuse, "The rate is 22%.", [{"article": "Art. 1"}])["passed"]


def test_metrics_on_abstain_case_scores_citation_free_answer_as_correct(records):
    abstain_case = next(r for r in records if r.expected.abstain).to_test_case()
    result = calculate_test_metrics(
        abstain_case,
        {
            "answer": "I don't have sufficient information in my regulatory database.",
            "citations": [],
        },
    )
    assert result.recall == 1.0 and result.precision == 1.0
    assert result.answer_checks and result.answer_checks["passed"]
    flagged = calculate_test_metrics(
        abstain_case, {"answer": "Sure: 22%", "citations": [{"article": "Art. 1"}]}
    )
    assert flagged.precision == 0.0 and flagged.false_positives == ["Art. 1"]
