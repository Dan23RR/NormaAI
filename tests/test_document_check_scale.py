"""Documents built to make the check slow: the work must grow with the text, not faster.

A document may have up to 400,000 characters (``document_check_max_chars``).
Before 18 November 2026 the extraction grew with the square of the text (a
name defined for an act was looked for in the rest of the text once per
definition, every reference was compared with every act and quote): 13 KB
took 1.6 s and 400 KB would have taken minutes. Offline, no official text.
"""

from __future__ import annotations

import time

import pytest

from src.document_check.extract import _act_mentions, extract_references

SIZE = 400_000
# Seconds for one 400 KB document. A linear extraction takes about one second
# on a laptop; the quadratic one took minutes.
BUDGET = 10.0


def _repeat(unit: str, size: int = SIZE) -> str:
    return (unit * (size // len(unit) + 1))[:size]


def _amended_far_back(size: int = SIZE) -> str:
    """An amending act, then thousands of other acts, then articles cited as amended by it."""
    head = "Il Regolamento (UE) 2024/1689 e il Regolamento (UE) 2026/1744 " + "GDPR " * (size // 10)
    return head + _repeat(
        "l'articolo 50, come modificato dal Regolamento (UE) 2026/1744, ", size - len(head)
    )


def _definitions(size: int = SIZE) -> str:
    """Thousands of acts, each with names defined for it and used right after."""
    parts: list[str] = []
    n = total = 0
    while total < size:
        part = (
            f"Il Regolamento (UE) 2016/{600 + n % 300} (di seguito «Regolamento{n}» o «R{n}») "
            f"e il Regolamento{n} all'art. {n % 99 + 1} del Regolamento{n}, "
        )
        parts.append(part)
        total += len(part)
        n += 1
    return "".join(parts)[:size]


ADVERSARIAL = {
    "many definitions": _definitions,
    "one name defined again and again": lambda: _repeat(
        "Il Regolamento (UE) 2016/679 (di seguito «Regolamento») vale; art. 5 del Regolamento. "
    ),
    "references, acts and quotes on one line": lambda: _repeat(
        "art. 13, par. 1, del GDPR e l'art. 6(1)(f) GDPR, Regolamento (UE) 2024/1689, "
        "«il titolare del trattamento fornisce all'interessato le seguenti informazioni» "
        "come modificato dal Regolamento (UE) 2026/1744; d.lgs. 196/2003, art. 2-ter; "
    ),
    "an amending act far back on the line": _amended_far_back,
    "paragraphs first, one per line": lambda: _repeat(
        "Il paragrafo 9 dell'articolo 50 e il comma 1-bis dell'art. 13 del GDPR.\n"
    ),
}


@pytest.mark.parametrize("kind", list(ADVERSARIAL))
def test_a_long_crafted_document_is_read_in_seconds(kind):
    text = ADVERSARIAL[kind]()
    assert len(text) == SIZE
    started = time.perf_counter()
    refs = extract_references(text)
    elapsed = time.perf_counter() - started
    assert refs
    assert elapsed < BUDGET, f"{kind}: {elapsed:.1f} s for {SIZE:,} characters"


def test_a_name_means_the_act_of_its_latest_definition():
    refs = extract_references(
        "Il Regolamento (UE) 2016/679 (di seguito «Regolamento») si applica; vedi l'art. 13 del "
        "Regolamento.\nIl Regolamento (UE) 2024/1689 (di seguito «Regolamento») vale per l'IA; "
        "vedi l'art. 50 del Regolamento."
    )
    assert [(r.provisions[0].key, r.act.key if r.act else None) for r in refs] == [
        ("art:13", "32016R0679"),
        ("art:50", "32024R1689"),
    ]


def test_a_name_is_not_read_before_its_definition_or_inside_a_word():
    text = (
        "Il Codice vale. Il Regolamento (UE) 2016/679 (di seguito «Codice» o «Reg. UE») e il "
        "Codicetto: art. 6 del Codice, art. 7 del Reg. UE."
    )
    mentions = [(text[m.start : m.end], m.act.key) for m in _act_mentions(text)]
    assert mentions == [
        ("Regolamento (UE) 2016/679", "32016R0679"),
        ("Codice", "32016R0679"),
        ("Reg. UE", "32016R0679"),
    ]
    assert _act_mentions(text)[1].start == text.index("Codice, art. 7")
