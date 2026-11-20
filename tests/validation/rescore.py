"""Score a stored golden v2 report again with the current checks (no API, no model).

    python -m tests.validation.rescore tests/validation/reports/golden_v2_api_<run>.json
    python -m tests.validation.rescore <report.json> --out-dir <dir>   # also writes files

The stored answers (``normaai_output`` of each result) are scored against the
records of test_cases/golden_v2.jsonl by metrics.calculate_test_metrics, as the
runner scores a live run. The output prints each measure as the report scored
it ("stored": its numbers, and the measures it predates computed from its own
verdicts) next to the current checks ("re-scored"), then the cases whose
verdict changed and why. With --out-dir the re-scored report is written there
as <name>_rescored.json and .txt. A result whose record is no longer in the
golden set is left out and listed.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

from .golden_v2 import GOLDEN_V2_PATH, load_golden_v2_test_cases
from .metrics import aggregate_suite_results, calculate_test_metrics
from .runner import generate_report
from .schemas import SuiteResult, TestCase, TestResult


def rescore(
    report: SuiteResult, cases: list[TestCase]
) -> tuple[SuiteResult, SuiteResult, list[str]]:
    """(stored, rescored, left_out): the report's verdicts and the current ones.

    ``stored`` aggregates the results as the report holds them, so its measures
    come from the checks of the run's day; ``rescored`` scores the same answers
    again. ``left_out`` are the results whose record is not in ``cases``.
    """
    case_map = {tc.id: tc for tc in cases}
    kept = [r for r in report.results if r.test_case_id in case_map]
    left_out = [r.test_case_id for r in report.results if r.test_case_id not in case_map]
    used = [case_map[r.test_case_id] for r in kept]
    stored = aggregate_suite_results(report.suite_name, kept, used)
    stored.run_timestamp = report.run_timestamp
    again: list[TestResult] = []
    for old in kept:
        new = calculate_test_metrics(
            case_map[old.test_case_id], old.normaai_output, old.execution_time_ms, old.error
        )
        new.run_timestamp = old.run_timestamp
        again.append(new)
    rescored = aggregate_suite_results(report.suite_name, again, used)
    rescored.run_timestamp = report.run_timestamp
    return stored, rescored, left_out


def _ratio(got: int | None, total: int | None) -> str:
    return "n/a" if got is None or not total else f"{got} / {total}"


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


MEASURES = (
    ("Passed (recall >= threshold, abstain records included)", "passed"),
    ("Answerable: expected article cited", "answerable_article_cited"),
    ("Answerable: answered, no abstention", "answerable_answered"),
    ("Answerable: content checks passed", "answerable_content_passed"),
    ("Answerable: article cited and content checks passed", "answerable_article_and_content"),
    ("Abstain records: abstained", "abstain_abstained"),
    ("Abstain records: content checks passed", "abstain_content_passed"),
    ("Content checks passed, all records", "content_checks_passed"),
    ("Citations verified word for word, all answers together", "citations_verified"),
    ("Verified citations, mean of the answers", "avg_verified_citation_rate"),
)


def _value(suite: SuiteResult, key: str) -> str:
    if key == "passed":
        return _ratio(suite.passed_cases, suite.total_cases)
    if key == "avg_verified_citation_rate":
        return _percent(suite.avg_verified_citation_rate)
    if key == "citations_verified":
        return _ratio(suite.citations_verified, suite.citations_scored)
    if key == "content_checks_passed":
        return _ratio(suite.content_checks_passed, suite.content_checks_total)
    total = suite.abstain_cases if key.startswith("abstain_") else suite.answerable_cases
    return _ratio(getattr(suite, key), total)


def _changes(stored: SuiteResult, rescored: SuiteResult) -> list[str]:
    """One line per case whose answer checks changed verdict."""
    lines = []
    for old, new in zip(stored.results, rescored.results, strict=True):
        before, after = old.answer_checks or {}, new.answer_checks or {}
        if before.get("passed") == after.get("passed") and before.get("abstained") == after.get(
            "abstained"
        ):
            continue
        why = []
        if before.get("abstained") != after.get("abstained"):
            why.append(f"abstained {before.get('abstained')} -> {after.get('abstained')}")
        if before.get("forbidden") != after.get("forbidden"):
            why.append(f"forbidden {before.get('forbidden')} -> {after.get('forbidden')}")
        if after.get("forbidden_excused"):
            why.append(f"mentioned only: {after['forbidden_excused']}")
        lines.append(
            f"  {new.test_case_id}: passed {before.get('passed')} -> {after.get('passed')}"
            f" ({'; '.join(why) or 'content'})"
        )
    return lines


def comparison(name: str, stored: SuiteResult, rescored: SuiteResult, left_out: list[str]) -> str:
    width = max(len(label) for label, _ in MEASURES)
    lines = [
        f"{name}: {rescored.total_cases} results scored again against {GOLDEN_V2_PATH.name}",
        "",
        f"{'Measure'.ljust(width)}  {'Stored':>12}  {'Re-scored':>12}",
    ]
    for label, key in MEASURES:
        lines.append(
            f"{label.ljust(width)}  {_value(stored, key):>12}  {_value(rescored, key):>12}"
        )
    changed = _changes(stored, rescored)
    lines += ["", f"Answer checks that changed verdict: {len(changed)}", *changed]
    if left_out:
        lines += ["", f"Left out, no longer in the golden set: {', '.join(left_out)}"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("report", type=pathlib.Path, help="a golden v2 report (.json)")
    parser.add_argument("--golden", type=pathlib.Path, default=GOLDEN_V2_PATH, help="golden JSONL")
    parser.add_argument(
        "--out-dir", type=pathlib.Path, default=None, help="write the re-scored report here"
    )
    args = parser.parse_args(argv)

    report = SuiteResult.model_validate_json(args.report.read_text(encoding="utf-8"))
    stored, rescored, left_out = rescore(report, load_golden_v2_test_cases(args.golden))
    print(comparison(args.report.name, stored, rescored, left_out))
    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stem = args.out_dir / f"{args.report.stem}_rescored"
        stem.with_suffix(".json").write_text(rescored.model_dump_json(indent=2), encoding="utf-8")
        stem.with_suffix(".txt").write_text(generate_report(rescored, "api"), encoding="utf-8")
        print(f"\nWritten: {stem.with_suffix('.json')} and .txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
