"""Amending acts: quoted articles and chapters of the amended act.

An amending article quotes whole articles of the act it amends ("the following
Article is inserted: «Article 2a ...»"). EUR-Lex marks those quoted headings
like real ones, so the chunker used to label them "Art. ?" (heading with a
quote) or as articles of the amending act itself ("Article 29e" inside a quoted
«CHAPTER 6c»), and the quoted chapter became the section of every later
article. The units and their text are unchanged; only the labels are: a quoted
unit keeps the amending article's label and records the quoted article.
"""

import pytest

from src.nlp.chunking.legal_chunker import (
    EURLexHTMLChunker,
    amended_act_celex,
    continues_article_numbering,
    quoted_article_number,
)

AMENDING_EN = """<html><body>
<p class="oj-doc-ti">DIRECTIVE (EU) 2099/9 OF THE EUROPEAN PARLIAMENT AND OF THE COUNCIL</p>
<p class="oj-normal">HAVE ADOPTED THIS DIRECTIVE:</p>
<p class="oj-ti-art">Article 1</p>
<p class="oj-sti-art">Amendments to Directive 2013/34/EU</p>
<p class="oj-normal">Directive 2013/34/EU is amended as follows:</p>
<p class="oj-normal">(1) the following Article is inserted:</p>
<p class="oj-ti-art">‘Article 29ca</p>
<p class="oj-sti-art">Sustainability reporting standards for voluntary use</p>
<p class="oj-normal">1. In order to facilitate voluntary reporting, the Commission shall adopt delegated acts.’;</p>
<p class="oj-normal">(2) the following Chapter is inserted:</p>
<p class="oj-ti-section-1">‘CHAPTER 6c</p>
<p class="oj-ti-section-2">DIGITAL SUPPORT MEASURES</p>
<p class="oj-ti-art">Article 29e</p>
<p class="oj-sti-art">Digital portal for sustainability reporting</p>
<p class="oj-normal">The Commission shall provide for a dedicated portal through which undertakings can access information.’;</p>
<p class="oj-ti-art">Article 2</p>
<p class="oj-sti-art">Transposition</p>
<p class="oj-normal">1. Member States shall bring into force the laws necessary to comply with this Directive by 19 March 2027.</p>
</body></html>"""

AMENDING_IT = """<html><body>
<p class="oj-normal">HANNO ADOTTATO LA PRESENTE DIRETTIVA:</p>
<p class="oj-ti-section-1">CAPO III</p>
<p class="oj-ti-section-2">DISPOSIZIONI FINALI</p>
<p class="oj-ti-art">Articolo 25</p>
<p class="oj-sti-art">Modifiche del regolamento (UE) 2019/2088</p>
<p class="oj-normal">Il regolamento (UE) 2019/2088 è così modificato:</p>
<p class="oj-normal">1) è inserito l’articolo seguente:</p>
<p class="oj-ti-art">«Articolo 2 bis</p>
<p class="oj-sti-art">Principio di non causare danni significativi</p>
<p class="oj-normal">1. Le autorità europee di vigilanza elaborano progetti di norme tecniche.»;</p>
<p class="oj-ti-art">«Articolo 29 quater bis</p>
<p class="oj-sti-art">Principi di rendicontazione ad uso volontario</p>
<p class="oj-normal">1. Al fine di agevolare la comunicazione volontaria, la Commissione adotta atti delegati.»;</p>
<p class="oj-ti-art">Articolo 26</p>
<p class="oj-sti-art">Riesame</p>
<p class="oj-normal">1. Entro il 13 luglio 2022 la Commissione pubblica una relazione sull’applicazione.</p>
</body></html>"""


# Several articles inserted by one quotation: only the first heading has the quote.
AMENDING_AI = """<html><body>
<p class="oj-normal">HAVE ADOPTED THIS REGULATION:</p>
<p class="oj-ti-art">Article 1</p>
<p class="oj-sti-art">Amendments to Regulation (EU) 2024/1689</p>
<p class="oj-normal">Regulation (EU) 2024/1689 is amended as follows:</p>
<p class="oj-normal">(25) the following Articles are inserted:</p>
<p class="oj-ti-art">‘Article 75a</p>
<p class="oj-sti-art">Mutual assistance for market surveillance</p>
<p class="oj-normal">1. Market surveillance authorities shall cooperate with each other.</p>
<p class="oj-ti-art">Article 75b</p>
<p class="oj-sti-art">Supervision of testing in real world conditions</p>
<p class="oj-normal">1. Market surveillance authorities shall supervise the testing.</p>
<p class="oj-ti-art">Article 75c</p>
<p class="oj-sti-art">Guidance</p>
<p class="oj-normal">The Commission shall issue guidance on the application of this Section.’;</p>
<p class="oj-ti-art">Article 2</p>
<p class="oj-sti-art">Entry into force</p>
<p class="oj-normal">This Regulation shall enter into force on the third day following its publication.</p>
</body></html>"""


def _chunks(html, celex="32099L0009", lang="EN"):
    return EURLexHTMLChunker(celex=celex, framework="CSRD", lang=lang).chunk_html(html)


def _labels(chunks):
    return [
        (c.metadata["article"], c.metadata["quoted_article"], c.metadata["section_title"])
        for c in chunks
        if c.metadata["chunk_type"] == "article"
    ]


# ─── Helpers ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text, number",
    [
        ("‘Article 2a", "2a"),
        ("«Article 4", "4"),
        ("‘Article 29ca", "29ca"),
        ("«Articolo 2 bis", "2 bis"),
        ("«Articolo 29 quater bis", "29 quater bis"),
        ("“Article 75c Fines", "75c"),
        ("Article 2a", None),  # not quoted
        ("‘personal data’ means any information", None),
    ],
)
def test_quoted_article_number(text, number):
    assert quoted_article_number(text) == number


@pytest.mark.parametrize(
    "title, celex",
    [
        ("Amendments to Regulation (EU) 2024/1689", "32024R1689"),
        ("Amendments to Directive 2013/34/EU", "32013L0034"),
        ("Amendments to Directive (EU) 2024/1760", "32024L1760"),
        ("Amendment to Regulation (EU) No 1093/2010", "32010R1093"),
        ("Modifiche del regolamento (UE) 2019/2088", "32019R2088"),
        ("Modifiche della direttiva 2006/43/CE", "32006L0043"),
        ("Modifica del regolamento (UE) n. 575/2013", "32013R0575"),
        ("Amendments to Directive 95/46/EC", "31995L0046"),
        ("Transposition", None),
        (None, None),
    ],
)
def test_amended_act_celex(title, celex):
    assert amended_act_celex(title) == celex


def test_continues_article_numbering():
    assert continues_article_numbering("3", "Art. 2")
    assert not continues_article_numbering("29e", "Art. 2")
    assert not continues_article_numbering("30", "Art. 2")
    assert not continues_article_numbering("3", None)
    assert not continues_article_numbering("3", "Art. 2a")


# ─── Chunking ─────────────────────────────────────────────────────


def test_quoted_units_keep_the_amending_article_and_record_the_quoted_one():
    assert _labels(_chunks(AMENDING_EN)) == [
        ("Art. 1", None, ""),
        ("Art. 1", "Art. 29ca", ""),
        ("Art. 1", "Art. 29e", ""),  # unquoted heading inside a quoted chapter
        ("Art. 2", None, ""),  # the quoted chapter is not this act's section
    ]


def test_quoted_units_carry_the_title_and_the_amended_act():
    chunks = [c for c in _chunks(AMENDING_EN) if c.metadata["chunk_type"] == "article"]
    for c in chunks[1:3]:
        assert c.metadata["title"] == "Amendments to Directive 2013/34/EU"
        assert c.metadata["article_number"] == "Art. 1"
        assert c.metadata["hierarchy"] == "Art. 1"
        assert c.metadata["amended_celex"] == "32013L0034"
    assert chunks[0].metadata["amended_celex"] is None
    assert chunks[3].metadata["title"] == "Transposition"


def test_the_text_of_every_unit_is_unchanged():
    # Same units and text as before the fix: the quoted heading starts the unit,
    # the quoted article's own title is in its text, the quoted chapter is not.
    texts = [c.text for c in _chunks(AMENDING_EN) if c.metadata["chunk_type"] == "article"]
    assert texts == [
        "Article 1\nAmendments to Directive 2013/34/EU\n"
        "Directive 2013/34/EU is amended as follows:\n(1) the following Article is inserted:",
        "‘Article 29ca\nSustainability reporting standards for voluntary use\n"
        "1. In order to facilitate voluntary reporting, the Commission shall adopt delegated "
        "acts.’;\n(2) the following Chapter is inserted:",
        "Article 29e\nDigital portal for sustainability reporting\n"
        "The Commission shall provide for a dedicated portal through which undertakings can "
        "access information.’;",
        "Article 2\nTransposition\n1. Member States shall bring into force the laws necessary "
        "to comply with this Directive by 19 March 2027.",
    ]
    assert all("CHAPTER 6c" not in t for t in texts)


def test_italian_quoted_articles_inside_a_chapter():
    chunks = _chunks(AMENDING_IT, celex="32099R0852", lang="IT")
    assert _labels(chunks) == [
        ("Art. 25", None, "CAPO III - DISPOSIZIONI FINALI"),
        ("Art. 25", "Art. 2 bis", "CAPO III - DISPOSIZIONI FINALI"),
        ("Art. 25", "Art. 29 quater bis", "CAPO III - DISPOSIZIONI FINALI"),
        ("Art. 26", None, "CAPO III - DISPOSIZIONI FINALI"),
    ]
    quoted = [c for c in chunks if c.metadata["quoted_article"]]
    assert {c.metadata["amended_celex"] for c in quoted} == {"32019R2088"}
    assert {c.metadata["hierarchy"] for c in quoted} == {"CAPO III - DISPOSIZIONI FINALI > Art. 25"}
    assert quoted[0].text.startswith("«Articolo 2 bis\nPrincipio di non causare danni")


def test_unquoted_headings_after_a_quoted_article_are_quoted_too():
    chunks = _chunks(AMENDING_AI, celex="32099R1744")
    assert _labels(chunks) == [
        ("Art. 1", None, ""),
        ("Art. 1", "Art. 75a", ""),
        ("Art. 1", "Art. 75b", ""),
        ("Art. 1", "Art. 75c", ""),
        ("Art. 2", None, ""),  # continues the act's own numbering: the quotation is over
    ]
    quoted = [c for c in chunks if c.metadata["quoted_article"]]
    assert {c.metadata["amended_celex"] for c in quoted} == {"32024R1689"}
    assert quoted[1].text.startswith("Article 75b\nSupervision of testing")


def test_acts_without_quotations_are_unchanged():
    html = AMENDING_EN.replace("‘Article 29ca", "Article 3").replace("‘CHAPTER 6c", "CHAPTER 6")
    chunks = [c for c in _chunks(html) if c.metadata["chunk_type"] == "article"]
    assert all(c.metadata["quoted_article"] is None for c in chunks)
    assert all(c.metadata["amended_celex"] is None for c in chunks)
