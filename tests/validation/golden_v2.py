"""Golden set v2: loader and answer checks.

The set lives in ``test_cases/golden_v2.jsonl`` (one record per line, schema in
``schemas.GoldenV2Record``). ``load_golden_v2`` parses and validates it;
``check_answer`` scores a system answer against a record's expectations
(answer_must_contain / answer_must_not_contain / abstain). Both are offline.

How the set was built and verified: see GOLDEN_V2.md and verify_golden_v2.py.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schemas import GoldenV2Record, TestCase

GOLDEN_V2_PATH = Path(__file__).parent / "test_cases" / "golden_v2.jsonl"

# Phrases that mark an abstention in the Q&A agent's answers (prompts/qa_bot.txt
# prescribes the English sentence; Italian variants cover language matching).
ABSTAIN_MARKERS: tuple[str, ...] = (
    "don't have sufficient information",
    "do not have sufficient information",
    "cannot answer",
    "unable to answer",
    "outside the scope",
    "out of scope",
    "not covered by",
    "qualified legal professional",
    "non dispongo di informazioni sufficienti",
    "non ho informazioni sufficienti",
    "non sono in grado di rispondere",
    "non posso rispondere",
    "non rientra",
    "al di fuori dell'ambito",
    "non è coperto",
    "professionista legale",
)


def load_golden_v2(path: Path | str = GOLDEN_V2_PATH) -> list[GoldenV2Record]:
    """Parse and validate the JSONL file; raises on the first invalid record."""
    path = Path(path)
    records: list[GoldenV2Record] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(GoldenV2Record.model_validate(json.loads(line)))
            except (ValueError, TypeError) as e:  # pydantic ValidationError is a ValueError
                raise ValueError(f"{path.name}:{line_no}: {e}") from e
    return records


def load_golden_v2_test_cases(path: Path | str = GOLDEN_V2_PATH) -> list[TestCase]:
    """The set as legacy TestCase objects, for the runner."""
    return [record.to_test_case() for record in load_golden_v2(path)]


def looks_like_abstention(answer: str, citations: list | None) -> bool:
    low = (answer or "").lower()
    return any(marker in low for marker in ABSTAIN_MARKERS) or not citations


def check_answer(expected: dict, answer: str | None, citations: list | None) -> dict:
    """Score a system answer against a record's expectations.

    Returns {"passed", "expected_abstain", "abstained", "missing", "forbidden"}:
    - missing: required facts (answer_must_contain) absent from the answer
    - forbidden: strings from answer_must_not_contain present in the answer
    - abstained: the answer reads as an abstention (marker phrase or no citations)
    An abstain record passes when the system abstained and said nothing
    forbidden; any other record passes when every required fact is present,
    nothing forbidden is present and the system did not abstain.
    Matching is case-insensitive substring matching.
    """
    text = answer or ""
    low = text.lower()
    must = [s for s in expected.get("answer_must_contain", []) if s]
    must_not = [s for s in expected.get("answer_must_not_contain", []) if s]
    missing = [s for s in must if s.lower() not in low]
    forbidden = [s for s in must_not if s.lower() in low]
    expected_abstain = bool(expected.get("abstain"))
    abstained = looks_like_abstention(text, citations)
    if expected_abstain:
        passed = abstained and not forbidden
    else:
        passed = not missing and not forbidden and not abstained
    return {
        "passed": passed,
        "expected_abstain": expected_abstain,
        "abstained": abstained,
        "missing": missing,
        "forbidden": forbidden,
    }
