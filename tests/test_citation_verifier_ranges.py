"""Two right citations the live golden run of 2026-11-24 left unverified.

- A range of paragraphs ("Art. 9(2)-(3)", "Art. 14(9)-(10)") was read as its
  first paragraph only: a quote of the second was "found in another paragraph".
- An article an amending act quotes is labelled as the amended act's article
  ([32024L1760, Art. 37] for the text Directive (EU) 2026/470 puts in the
  CSDDD); cited as the amending act's own article ([32026L0470, Art. 4]), where
  the wording stands too, it was "found in another act".
"""

from __future__ import annotations

from src.agents.citation_verifier import annotate_citations, cited_paragraphs, verify_citation

ART_9 = (
    "Articolo 9\n"
    "1. L'entità finanziaria individua i servizi TIC che sostengono funzioni essenziali.\n"
    "2. Prima di concludere un accordo l'entità valuta i rischi connessi al fornitore terzo.\n"
    "3. La politica specifica che la valutazione di cui al paragrafo 2 deve essere "
    "documentata e i suoi risultati devono essere utilizzati per aggiornare la valutazione "
    "dei rischi."
)
RTS_CHUNK = {
    "framework": "DORA",
    "celex": "32024R1773",
    "article": "Art. 9",
    "lang": "it",
    "text": ART_9,
}
PAR_3 = (
    "La politica specifica che la valutazione di cui al paragrafo 2 deve essere documentata "
    "e i suoi risultati devono essere utilizzati per aggiornare la valutazione dei rischi"
)

NEW_ART_37 = (
    "Gli Stati membri adottano e pubblicano, entro il 26 luglio 2028, le disposizioni "
    "legislative, regolamentari e amministrative necessarie per conformarsi alla presente "
    "direttiva."
)
QUOTED_CHUNK = {
    "framework": "CSDDD",
    "celex": "32026L0470",
    "article": "Art. 4",
    "citation_celex": "32024L1760",
    "citation_article": "Art. 37",
    "lang": "it",
    "text": NEW_ART_37,
}
QUOTE_37 = (
    "Gli Stati membri adottano e pubblicano, entro il 26 luglio 2028, le disposizioni legislative"
)


def _one(citation: dict, chunk: dict) -> dict:
    result = annotate_citations({"answer": "x", "citations": [citation]}, [chunk])
    return result["citations"][0]


def test_a_range_of_paragraphs_is_read_whole() -> None:
    assert cited_paragraphs("Art. 9(2)-(3)") == "2-3"
    assert cited_paragraphs("art. 9, par. 2-3") == "2-3"
    assert cited_paragraphs("Art. 14(9)-(10)") == "9-10"
    # Points of one paragraph are not a range of paragraphs.
    assert cited_paragraphs("Art. 14(2)(a)-(c)") == "2"
    assert cited_paragraphs("Art. 50(2)") == "2"
    assert cited_paragraphs("Art. 113") is None


def test_a_quote_of_a_paragraph_inside_the_cited_range_is_verified() -> None:
    cited = _one(
        {"framework": "32024R1773", "reference": "Art. 9(2)-(3)", "quote_snippet": PAR_3},
        RTS_CHUNK,
    )
    assert cited["verified"] is True
    assert not cited["found_elsewhere"]


def test_a_quote_outside_the_cited_range_is_still_found_elsewhere() -> None:
    cited = _one(
        {"framework": "32024R1773", "reference": "Art. 9(1)", "quote_snippet": PAR_3},
        RTS_CHUNK,
    )
    assert cited["verified"] is False
    assert cited["found_elsewhere"] is True and cited["found_in"] == "paragraph"


def test_the_amending_acts_own_article_verifies_the_wording_it_inserts() -> None:
    cited = _one(
        {"framework": "32026L0470", "reference": "Art. 4", "quote_snippet": QUOTE_37},
        QUOTED_CHUNK,
    )
    assert cited["verified"] is True
    assert not cited["found_elsewhere"]
    assert cited["amending_celex"] == "32026L0470"


def test_the_amended_article_still_verifies_as_before() -> None:
    out = verify_citation(
        {"framework": "32024L1760", "reference": "Art. 37", "quote_snippet": QUOTE_37},
        [QUOTED_CHUNK],
    )
    assert out.verified and out.level == "article" and out.celex == "32024L1760"


def test_another_article_of_the_amending_act_is_not_verified() -> None:
    cited = _one(
        {"framework": "32026L0470", "reference": "Art. 5", "quote_snippet": QUOTE_37},
        QUOTED_CHUNK,
    )
    assert cited["verified"] is False
    assert cited["found_elsewhere"] is True
