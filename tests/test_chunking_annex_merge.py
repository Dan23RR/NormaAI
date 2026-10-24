"""Tiny annex sections are merged into their neighbours.

Found on 2026-10-24: about 10% of the corpus chunks were under 200 characters,
mostly glossary rows of ESRS Annex II ("ODS", "FPIC") and the code list of AI
Act Annex XIV ("AIH 0101"), each read as an annex section. Those short chunks
crowded the real articles out of the search results: a question about a
customer chatbot never reached AI Act Article 50.
"""

from src.nlp.chunking.legal_chunker import EURLexHTMLChunker, _Unit


def _chunker() -> EURLexHTMLChunker:
    return EURLexHTMLChunker(celex="32023R2772", framework="CSRD")


def _annex(
    section: str, body: list[str], label: str = "Annex II", title: str = "ACRONYMS"
) -> _Unit:
    return _Unit(
        "annex",
        label,
        title=title,
        section=section,
        hierarchy=f"{label} > {section}",
        heading=[f"{label} - {title}", section],
        body=list(body),
    )


def test_glossary_rows_become_one_unit_that_keeps_every_row():
    units = [
        _annex("ODS", ["Ozone-depleting substance"]),
        _annex("FPIC", ["Free, Prior and Informed Consent"]),
        _annex("REACH", ["Registration, Evaluation, Authorisation and Restriction of Chemicals"]),
    ]
    merged = _chunker()._merge_tiny_annex_units(units)
    assert len(merged) == 1
    unit = merged[0]
    assert unit.heading == ["Annex II - ACRONYMS"]
    assert unit.section == ""
    assert unit.hierarchy == "Annex II"
    assert unit.body == [
        "ODS",
        "Ozone-depleting substance",
        "FPIC",
        "Free, Prior and Informed Consent",
        "REACH",
        "Registration, Evaluation, Authorisation and Restriction of Chemicals",
    ]


def test_real_sections_stay_separate():
    a = _annex(
        "Section A. List of legislation",
        ["1. Directive 2006/42/EC " + "x" * 150],
        "Annex I",
        "List",
    )
    b = _annex(
        "Section B. Other legislation",
        ["2. Regulation (EC) No 300/2008 " + "y" * 120],
        "Annex I",
        "List",
    )
    assert len(_chunker()._merge_tiny_annex_units([a, b])) == 2


def test_merging_stops_before_the_chunk_size_limit():
    chunker = _chunker()
    rows = [_annex(f"C{i:02d}", ["z" * 100]) for i in range(40)]
    merged = chunker._merge_tiny_annex_units(rows)
    assert len(merged) > 1
    assert all(chunker._unit_text_length(u) <= chunker.MAX_CHUNK_SIZE for u in merged)
    assert sum(u.body.count("z" * 100) for u in merged) == 40


def test_sections_of_different_annexes_are_not_merged():
    a = _annex("ODS", ["Ozone-depleting substance"], "Annex I", "One")
    b = _annex("FPIC", ["Free, Prior and Informed Consent"], "Annex II", "Two")
    assert len(_chunker()._merge_tiny_annex_units([a, b])) == 2


def test_articles_are_never_merged():
    first = _Unit("article", "Art. 59", heading=["Article 59"], body=["Short."])
    second = _Unit("article", "Art. 60", heading=["Article 60"], body=["Also short."])
    assert len(_chunker()._merge_tiny_annex_units([first, second])) == 2
