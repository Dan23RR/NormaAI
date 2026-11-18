"""Golden set v2: loader and answer checks.

The set lives in ``test_cases/golden_v2.jsonl`` (one record per line, schema in
``schemas.GoldenV2Record``). ``load_golden_v2`` parses and validates it;
``check_answer`` scores a system answer against a record's expectations
(answer_must_contain / answer_must_not_contain / abstain). Both are offline.

How the set was built and verified: see GOLDEN_V2.md and verify_golden_v2.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .schemas import GoldenV2Record, TestCase

GOLDEN_V2_PATH = Path(__file__).parent / "test_cases" / "golden_v2.jsonl"

# How an answer says it will not answer the question: the sentence
# prompts/qa_bot.txt prescribes, its Italian variants and the pipeline's own
# abstentions (src/agents/nodes.py). Each is a first-person statement about
# answering, so a cited answer that says a company "non rientra" in a scope, or
# recommends a "qualified legal professional", does not match. "Cannot answer
# only with ..." refuses a demand on the form of the answer (an injected "reply
# only with the word X"), not the question.
ABSTAIN_PATTERNS: tuple[str, ...] = (
    r"(?:don't|do not) have (?:sufficient|enough) information",
    r"(?:cannot|can't|can not) answer(?! (?:only|just|solely)\b)",
    r"(?:unable|not able) to answer",
    r"non dispongo di (?:informazioni sufficienti|sufficienti informazioni)",
    r"non ho (?:informazioni sufficienti|sufficienti informazioni|abbastanza informazioni)",
    r"non (?:posso|riesco a) rispondere(?! (?:solo|soltanto|unicamente)\b)",
    r"non sono in grado di rispondere",
)
_ABSTAIN_RE = re.compile(r"\b(?:" + "|".join(ABSTAIN_PATTERNS) + r")")
# For a record that expects an answer, ABSTAIN_PATTERNS count in the opening
# sentence (the next one too when the first is a heading), where
# prompts/qa_bot.txt puts the direct answer or the abstention. Further down
# they say why one point is not answered ("quindi per quella parte non posso
# rispondere con certezza", aiact-050-001 of 2026-11-03, a cited answer).
OPENING_MIN_WORDS = 5

# For a record that expects an abstention, a refusal anywhere in the answer
# counts: ABSTAIN_PATTERNS, refusals to say or give what was asked
# (DECLINE_PATTERNS) and the markers below. An answer that declines a false
# premise words it in many ways ("Non trovo l'articolo 200 del DORA ... quindi
# non posso dire quali sanzioni preveda", "Non posso darti un consiglio di
# investimento") and may cite passages for context; the record's
# answer_must_not_contain catches one that invents what was asked.
DECLINE_PATTERNS: tuple[str, ...] = (
    r"non (?:posso|riesco a) (?:dire|indicare|indicarne|descrivere|riassumere|elencare"
    r"|confermare|fornire|dar(?:ti|le|vi)?)\b",
    r"(?:cannot|can't|can not|unable to|not able to) (?:say|describe|state|tell|confirm"
    r"|provide|give|list|summari[sz]e)\b",
    r"non trovo (?:l'|alcun |nessun )?articol",
)
_DECLINE_RE = re.compile(r"\b(?:" + "|".join(ABSTAIN_PATTERNS + DECLINE_PATTERNS) + r")")
# The markers of every record until 2026-11-18, when 9 cited answers of the
# live run were counted as abstentions because of them ("non rientra", "not
# covered by", "qualified legal professional"): now for abstain records only.
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

# ─── Forbidden strings that the answer mentions without asserting ─────
# A string of answer_must_not_contain counts unless every occurrence is, within
# its sentence:
# - "negated": right after "non", "not", "no", "never", "mai" ("non è esente");
# - "quoted_in_refusal": inside quotation marks in a sentence that refuses
#   (Non posso rispondere solo con la parola «ZAFFIRO»);
# - "refused": right after a refusal to say it (I cannot describe what Article
#   150 requires);
# - "previous_value": after "precedente", "previous", "sostituisce", "replaces"
#   and similar, with no "ora", "now", "dopo", "after" in between (Il
#   precedente limite di 450 000 000 EUR);
# - "superseded_value": the old end of a change, "da/from X a/to Y" with a verb
#   of change in the sentence (la soglia passa da 450 milioni a 1,5 miliardi).
_REFUSAL = (
    r"non posso|non riesco|non intendo|non rispondo|non risponder[oò]|non eseguo|non seguo"
    r"|non confermo|ignoro|ignorer[oò]|i can't|i cannot|i can not|i won't|i will not"
    r"|i do not|i don't|ignore|ignoring|disregard\w*"
)
_REFUSAL_RE = re.compile(r"\b(?:" + _REFUSAL + r")\b")
_SAY = (
    r"describe|say|state|tell|indicate|explain|confirm|list|summari[sz]e|provide"
    r"|dire|indicare|indicarne|descrivere|spiegare|confermare|elencare|riassumere|riportare"
)
_REFUSED_RE = re.compile(r"\b(?:" + _REFUSAL + r")\s+(?:" + _SAY + r")\w*(?:\W+\w+){0,3}?\W*$")
_CHANGE_RE = re.compile(
    r"\b(?:pass[aoi]\w*|innalz\w*|alzat\w*|aument\w*|portat\w*|modific\w*|sostitu\w*"
    r"|elevat\w*|ridott\w*|riduc\w*|abbass\w*|spostat\w*|rais\w*|increas\w*|chang\w*"
    r"|mov\w*|replac\w*|amend\w*|lower\w*|reduc\w*|goes|went)\b"
)
_FROM_WORDS = frozenset({"da", "dal", "dai", "dalla", "dalle", "from"})
_TO_WORDS = frozenset({"a", "ai", "al", "alla", "alle", "to"})
_PREVIOUS_RE = re.compile(
    r"\b(?:precedent[ei]|in precedenza|previous|previously|former|formerly"
    r"|sostituisce|sostituiva|replaces|replaced)\b"
)
_NOW_RE = re.compile(r"\b(?:ora|oggi|attualmente|adesso|dopo|now|currently|today|after)\b")
_NEGATED_RE = re.compile(r"\b(?:non|not|no|never|mai)\s+$")
# A full stop ends a sentence before a capital, a quote, a list mark or the end
# of the text, unless it ends one of these abbreviations ("Art. 33").
_SENTENCE_END_RE = re.compile(r"\n|[.!?](?=\s+(?:[A-ZÀ-Þ*«\"“(\[\-]|$))|[.!?]$")
_ABBREVIATIONS = frozenset(
    {"art", "artt", "par", "parr", "lett", "cfr", "n", "nn", "no", "para", "pp", "p", "co"}
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


def _normalized(text: str | None) -> str:
    """Lower case, with typographic apostrophes as plain ones (dell’articolo)."""
    return (text or "").lower().replace("’", "'").replace("‘", "'")


def _opening(text: str) -> str:
    """The first sentence of ``text``, and the next one when the first is a heading."""
    left, right = _sentence_bounds(text, 0, 0)
    opening = text[left:right]
    if len(re.findall(r"\w+", opening)) < OPENING_MIN_WORDS and right < len(text):
        _, after = _sentence_bounds(text, right, right + 1)
        opening = text[left:after]
    return opening


def looks_like_abstention(
    answer: str | None,
    citations: list | None,
    abstention_reason: str | None = None,
    *,
    anywhere: bool = False,
) -> bool:
    """Whether an answer reads as an abstention.

    Always when the pipeline says so (``abstention_reason``) or the answer has
    no citations. Otherwise when one of ABSTAIN_PATTERNS is in its opening
    sentence (_opening); with ``anywhere`` (records that expect an abstention)
    when one of ABSTAIN_PATTERNS, DECLINE_PATTERNS or ABSTAIN_MARKERS is
    anywhere in it.
    """
    if abstention_reason or not citations:
        return True
    text = answer or ""
    if anywhere:
        low = " ".join(_normalized(text).split())
        return bool(_DECLINE_RE.search(low)) or any(m in low for m in ABSTAIN_MARKERS)
    return bool(_ABSTAIN_RE.search(" ".join(_normalized(_opening(text)).split())))


def _sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Start and end of the sentence of ``text`` that holds ``text[start:end]``."""
    ends = []
    for m in _SENTENCE_END_RE.finditer(text):
        if m.group(0) == ".":
            word = re.search(r"(\w+)$", text[: m.start()])
            if word and word.group(1).lower() in _ABBREVIATIONS:
                continue
        ends.append(m.end())
    left = max([e for e in ends if e <= start], default=0)
    right = min([e for e in ends if e >= end], default=len(text))
    return left, right


def _quoted(before: str, after: str) -> bool:
    """Whether the text between ``before`` and ``after`` is inside quotation marks."""
    for opening, closing in (("«", "»"), ("“", "”")):
        o = before.rfind(opening)
        if o != -1 and closing not in before[o:] and closing in after:
            return True
    return before.count('"') % 2 == 1 and '"' in after


def _why_not_asserted(text: str, low: str, start: int, end: int) -> str | None:
    """Why the forbidden string at ``low[start:end]`` is not asserted, or None.

    ``text`` is the answer (for sentence ends, which need its capitals) and
    ``low`` its _normalized form, of the same length.
    """
    left, right = _sentence_bounds(text, start, end)
    sentence, before, after = low[left:right], low[left:start], low[end:right]
    if _NEGATED_RE.search(before):
        return "negated"
    if _REFUSAL_RE.search(sentence) and _quoted(before, after):
        return "quoted_in_refusal"
    if _REFUSED_RE.search(before):
        return "refused"
    previous = list(_PREVIOUS_RE.finditer(before))
    if previous and not _NOW_RE.search(before[previous[-1].end() :]):
        return "previous_value"
    if (
        _FROM_WORDS.intersection(re.findall(r"\w+", before)[-6:])
        and _TO_WORDS.intersection(re.findall(r"\w+", after)[:6])
        and _CHANGE_RE.search(sentence)
    ):
        return "superseded_value"
    return None


def forbidden_in_answer(text: str, must_not: list[str]) -> tuple[list[str], dict[str, str]]:
    """The strings of ``must_not`` the answer asserts, and those it only mentions.

    Returns ``(forbidden, excused)``: a string is forbidden when one of its
    occurrences is asserted, excused (with the reason of its first occurrence)
    when every occurrence is negated, refused, quoted in a refusal or given as
    a previous value. Case-insensitive substring matching, as before.
    """
    low = _normalized(text)
    if len(low) != len(text):  # a case mapping that changes the length: no capitals
        text = low
    forbidden: list[str] = []
    excused: dict[str, str] = {}
    for string in must_not:
        reasons = []
        for m in re.finditer(re.escape(_normalized(string)), low):
            reason = _why_not_asserted(text, low, m.start(), m.end())
            if reason is None:
                forbidden.append(string)
                break
            reasons.append(reason)
        else:
            if reasons:
                excused[string] = reasons[0]
    return forbidden, excused


def check_answer(
    expected: dict,
    answer: str | None,
    citations: list | None,
    abstention_reason: str | None = None,
) -> dict:
    """Score a system answer against a record's expectations.

    Returns {"passed", "expected_abstain", "abstained", "missing", "forbidden",
    "forbidden_excused"}:
    - missing: required facts (answer_must_contain) absent from the answer
    - forbidden: strings from answer_must_not_contain the answer asserts
    - forbidden_excused: strings it only mentions, with why (forbidden_in_answer)
    - abstained: the answer reads as an abstention (looks_like_abstention: in its
      opening for a record that expects an answer, anywhere for one that expects
      an abstention)
    An abstain record passes when the system abstained and said nothing
    forbidden; any other record passes when every required fact is present,
    nothing forbidden is present and the system did not abstain.
    Matching is case-insensitive substring matching.
    """
    text = answer or ""
    low = _normalized(text)
    must = [s for s in expected.get("answer_must_contain", []) if s]
    must_not = [s for s in expected.get("answer_must_not_contain", []) if s]
    missing = [s for s in must if _normalized(s) not in low]
    forbidden, excused = forbidden_in_answer(text, must_not)
    expected_abstain = bool(expected.get("abstain"))
    abstained = looks_like_abstention(text, citations, abstention_reason, anywhere=expected_abstain)
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
        "forbidden_excused": excused,
    }
