"""Documents built to make the check slow: the work must grow with the text, not faster.

A document may have up to 400,000 characters (``document_check_max_chars``).
Before 18 November 2026 the extraction grew with the square of the text (a
name defined for an act was looked for in the rest of the text once per
definition, every reference was compared with every act and quote): 13 KB
took 1.6 s, and the 400 KB texts below took from 40 s to several minutes.
Each quote not in the provision it cites was then looked for in the whole act
and its versions, a few tenths of a second each, without limit; and a .docx
could unpack to 200 MB. Offline, with the stand-in for CELLAR of
test_document_check.
"""

from __future__ import annotations

import io
import os
import time
import zipfile

import pytest

from src.document_check import check as check_module
from src.document_check import service
from src.document_check.check import ALTERED, NOT_FOUND, VERIFIED, check_text
from src.document_check.extract import _act_mentions, extract_references
from src.document_check.service import DocumentCheckError
from tests.test_document_check import FakeSource

SIZE = 400_000
# Seconds for one 400 KB document. The extraction takes one or two seconds on a
# laptop; before, the texts below took 40 s to several minutes.
BUDGET = 15.0


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


# ─── Quotes: the cited provision first, the whole act within a budget ─


def _chunks_read(monkeypatch) -> list[int]:
    """How many official units the verifier is given at each call."""
    sizes: list[int] = []
    real = check_module.verify_citation

    def spy(citation, chunks):
        sizes.append(len(chunks))
        return real(citation, chunks)

    monkeypatch.setattr(check_module, "verify_citation", spy)
    return sizes


def test_a_quote_in_the_cited_provision_is_verified_on_that_provision_alone(monkeypatch):
    sizes = _chunks_read(monkeypatch)
    text = (
        "Ai sensi dell'art. 13 del GDPR, il titolare «fornisce all'interessato, nel momento in cui "
        "i dati personali sono ottenuti, le seguenti informazioni»."
    )
    [finding] = check_text(text, FakeSource()).findings
    assert finding.status is VERIFIED
    assert sizes == [1]


def test_quotes_not_in_the_cited_provision_stop_at_the_budget(monkeypatch):
    monkeypatch.setattr(check_module, "WIDE_SEARCHES", 4)
    sizes = _chunks_read(monkeypatch)
    lines = [
        f"L'art. 4 dell'AI Act dice che «ogni dipendente deve superare l'esame numero {n} ogni anno»."
        for n in range(4)
    ]
    findings = check_text("\n".join(lines), FakeSource()).findings
    assert [f.status for f in findings] == [NOT_FOUND] * 4
    # The AI Act of the stand-in has a text in force and two earlier versions:
    # three searches of the whole act for the first quote, the fourth and last
    # one for the second quote, none for the other two.
    assert sum(1 for size in sizes if size > 1) == 4
    unsearched = [any("dividilo in parti" in m for m in f.messages) for f in findings]
    assert unsearched == [False, True, True, True]
    assert any("Le versioni precedenti non sono state cercate" in m for m in findings[1].messages)
    assert "La citazione non è nel testo vigente." in findings[1].messages
    for finding in findings[2:]:
        assert "La citazione non è nella disposizione citata." in finding.messages
        assert any("Il resto dell'atto e le versioni precedenti" in m for m in finding.messages)


def test_the_same_quote_twice_is_searched_once(monkeypatch):
    sizes = _chunks_read(monkeypatch)
    line = "L'art. 4 dell'AI Act dice che «ogni dipendente deve superare un esame annuale»."
    findings = check_text(f"{line}\n{line}", FakeSource()).findings
    assert [f.status for f in findings] == [NOT_FOUND, NOT_FOUND]
    assert sum(1 for size in sizes if size > 1) == 3  # the text in force, two earlier versions


def test_an_altered_quote_past_the_budget_is_still_reported_as_altered(monkeypatch):
    monkeypatch.setattr(check_module, "WIDE_SEARCHES", 0)
    text = (
        "L'art. 13 del GDPR dispone: «il responsabile del trattamento fornisce all'interessato, nel "
        "momento in cui i dati personali sono ottenuti, le seguenti informazioni»."
    )
    [finding] = check_text(text, FakeSource()).findings
    assert finding.status is ALTERED
    assert finding.differences == [{"quoted": "responsabile", "official": "titolare"}]
    assert any("non sono stati cercati" in m for m in finding.messages)


def test_a_document_full_of_invented_quotes_makes_a_bounded_number_of_searches(monkeypatch):
    sizes = _chunks_read(monkeypatch)
    lines = [
        f"L'art. {4 if n % 2 else 50} dell'AI Act prevede "
        + " ".join(f"«ogni dipendente supera l'esame numero {n}-{k} ogni anno»" for k in range(12))
        for n in range(150)
    ]
    started = time.perf_counter()
    findings = check_text("\n".join(lines), FakeSource()).findings
    elapsed = time.perf_counter() - started
    assert len(findings) == 150 and all(f.status is NOT_FOUND for f in findings)
    assert sum(1 for size in sizes if size > 1) == check_module.WIDE_SEARCHES
    assert elapsed < BUDGET


# ─── Uploaded files: what a .docx may unpack to ──────────────────────


def _docx_with(parts: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    docx = pytest.importorskip("docx")
    buffer = io.BytesIO()
    document = docx.Document()
    document.add_paragraph("Ai sensi dell'art. 13 del GDPR il titolare informa.")
    document.save(buffer)
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as source,
        zipfile.ZipFile(out, "w", compression) as target,
    ):
        for info in source.infolist():
            target.writestr(info.filename, source.read(info.filename))
        for name, data in parts.items():
            target.writestr(name, data)
    return out.getvalue()


def test_a_docx_that_unpacks_to_more_than_20_mb_is_refused():
    bomb = _docx_with({"word/media/vuoto.bin": b"\0" * (21 * 1024 * 1024)})
    assert len(bomb) < 100 * 1024  # a few tens of kilobytes on the wire
    with pytest.raises(DocumentCheckError) as error:
        service.text_from_bytes("bomba.docx", bomb)
    assert error.value.code == "unreadable_file"


def test_a_docx_with_a_part_packed_a_thousand_times_is_refused():
    packed = _docx_with({"word/media/vuoto.bin": b"\0" * (5 * 1024 * 1024)})
    with pytest.raises(DocumentCheckError) as error:
        service.text_from_bytes("compresso.docx", packed)
    assert error.value.code == "unreadable_file"


def test_a_docx_with_a_large_image_is_read():
    image = os.urandom(3 * 1024 * 1024)  # does not pack: like a photo
    text = service.text_from_bytes("foto.docx", _docx_with({"word/media/foto.jpg": image}))
    assert "art. 13 del GDPR" in text
