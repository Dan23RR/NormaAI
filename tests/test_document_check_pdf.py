"""Tests for src/document_check/pdf.py: the report of a check as a PDF with a letterhead.

The checks are the stored ones the API renders (``serialize.check_from_json``),
made by ``service.check_document`` on the documents of tests/documents_support.py
or written by hand for the outcomes that document does not have (a repealed
article, an Italian provision). The PDFs are read back with pypdf: the text of
each page, the size of the font each piece of text is written in, the links,
the images and the metadata.
"""

from __future__ import annotations

import io
import re
from html import unescape
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from PIL import Image
from pypdf import PdfReader

from src.document_check import pdf as pdf_module
from src.document_check import report, serialize, service
from src.document_check.extract import Reference
from src.document_check.pdf import (
    COMPARED_WITH,
    DIFF_LEGEND,
    FOOT_CREDIT,
    KICKER,
    NO_REFERENCES,
    NOT_READ_INTRO,
    OWN_ARTICLES_INTRO,
    OWN_ARTICLES_TITLE,
    credit_runs,
    diff_runs,
    highlight_parts,
    pdf_filename,
    render_pdf,
)
from src.reports.generator import AI_NOTICE_IT
from src.reports.letterhead import Letterhead, normalize_logo
from tests.documents_support import CLEAN_DOCUMENT, DOCUMENT, FakeSource

if TYPE_CHECKING:
    from src.document_check.check import DocumentCheck

STUDIO = Letterhead(
    name="Studio Legale Rossi & Associati",
    address="Via dell’Università 12\n20121 Milano (MI)",
    contact="tel. 02 1234567 · info@rossi.example",
    footer_note="Documento riservato al cliente.",
    configured=True,
)


def _check(text: str = DOCUMENT, filename: str = "Informativa «clienti».docx") -> DocumentCheck:
    outcome = service.check_document(FakeSource(), filename=filename, text=text)
    return serialize.check_from_json(
        outcome.findings,
        document=outcome.filename,
        checked_on="2026-11-24",
        document_date="2026-01-12",
        lang=outcome.lang,
    )


def _stored(**fields) -> dict:
    """A stored finding (the JSON of ``service.check_object``) with the given fields."""
    finding = {
        "id": "f1",
        "group": "correggere",
        "status": {"code": "abrogata", "label": "Non c'è più"},
        "line": 4,
        "raw": "art. 7 del d.lgs. 1/2020",
        "context": "Si applica l'art. 7 del d.lgs. 1/2020.",
        "act": {
            "source": "normattiva",
            "id": "urn:nir:stato:decreto.legislativo:2020;1",
            "name": "D.Lgs. 1/2020",
            "label": "D.Lgs. 1/2020",
        },
        "provision": {"key": "art:7", "label": "art. 7", "paragraphs": []},
        "version": None,
        "url": None,
        "messages": [],
        "quotes": [],
        "official_quote": None,
        "altered_quote": None,
        "differences": [],
        "before": None,
        "after_text": "",
        "dependency": None,
        "rule": None,
    }
    finding.update(fields)
    return finding


def _from_json(findings: list[dict]) -> DocumentCheck:
    return serialize.check_from_json(
        findings, document="nota.txt", checked_on="2026-11-24", document_date=None, lang="IT"
    )


def _png(size=(400, 120), color=(10, 58, 156, 255)) -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", size, color).save(out, "PNG")
    return out.getvalue()


def _flat(text: str) -> str:
    """Text as the PDF reads back: one space between words (lines break anywhere)."""
    return " ".join(text.split())


class _Read:
    """What a PDF says: the text of each page, and the size of the font of each piece."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.reader = PdfReader(io.BytesIO(data))
        self.pages: list[str] = []
        self.sizes: list[list[tuple[str, float]]] = []
        for page in self.reader.pages:
            pieces: list[tuple[str, float]] = []

            def visit(text, cm, tm, font, size, pieces=pieces):
                if text.strip():
                    pieces.append((text, abs(size * tm[0]) if tm[0] else size))

            self.pages.append(page.extract_text(visitor_text=visit))
            self.sizes.append(pieces)

    @property
    def text(self) -> str:
        return _flat(" ".join(self.pages))

    def links(self) -> list[str]:
        found = []
        for page in self.reader.pages:
            for annotation in page.get("/Annots") or []:
                action = annotation.get_object().get("/A") or {}
                if "/URI" in action:
                    found.append(str(action["/URI"]))
        return found


# ─── Pieces shared with the HTML report ──────────────────────────────


class TestSameWordsAsTheHtml:
    @pytest.mark.parametrize(
        ("before", "after"),
        [
            ("I fornitori adottano misure", "I fornitori e i deployer adottano misure"),
            ("uno due tre", "uno tre quattro"),
            (" ".join(f"w{i}" for i in range(60)) + " fine", " ".join(f"w{i}" for i in range(60))),
            ("a < b & «c»", "a > b & «c»"),
            ("", "nuovo testo"),
        ],
    )
    def test_diff_runs_are_what_diff_html_shows(self, before, after):
        tags = {"equal": "{}", "delete": "<del>{}</del>", "insert": "<ins>{}</ins>"}
        rebuilt = " ".join(
            tags[op].format(report.escape(words)) for op, words in diff_runs(before, after)
        )
        assert rebuilt == report.diff_html(before, after)

    @pytest.mark.parametrize(
        ("context", "raw"),
        [
            ("Ai sensi dell'art. 4 dell'AI Act, i deployer", "art. 4 dell'AI Act"),
            ("Vedi l'art.\n13   del GDPR e altro", "art. 13 del GDPR"),
            ("nessun riferimento qui", "art. 99"),
            ("a < b: art. 5 & c", "art. 5"),
        ],
    )
    def test_highlight_parts_are_what_the_html_marks(self, context, raw):
        before, match, after = highlight_parts(context, raw)
        rebuilt = (
            report.escape(before)
            + (f"<mark>{report.escape(match)}</mark>" if match else "")
            + report.escape(after)
        )
        assert rebuilt == report._highlight(context, raw)

    def test_credit_runs_are_the_credit_of_the_html(self):
        runs = credit_runs()
        text = "".join(t for t, _ in runs)
        assert text == unescape(re.sub(r"<[^>]+>", "", report._NORMATTIVA_CREDIT))
        assert [link for _, link in runs if link] == [
            "https://www.normattiva.it/",
            "https://dati.normattiva.it/",
            "https://creativecommons.org/licenses/by/4.0/deed.it",
        ]

    def test_the_fixed_sentences_are_the_ones_of_the_html(self):
        own = Reference(
            start=0,
            end=0,
            provisions=[],
            act=None,
            quotes=[],
            raw="art. 12",
            line=9,
            context="art. 12 del presente contratto",
        )
        check = _check()
        check.own_articles = [own]
        html = unescape(report.render_html(check))
        for sentence in (NOT_READ_INTRO, OWN_ARTICLES_TITLE, OWN_ARTICLES_INTRO):
            assert sentence in html, sentence
        empty = unescape(report.render_html(_from_json([])))
        assert NO_REFERENCES in empty


# ─── The PDF ─────────────────────────────────────────────────────────


class TestReport:
    def test_the_report_with_its_letterhead(self):
        check = _check()
        read = _Read(render_pdf(check, STUDIO, rechecked_on="2026-11-20"))
        text = read.text
        first = _flat(read.pages[0])
        # The letterhead heads the first page.
        assert first.startswith(
            "Studio Legale Rossi & Associati Via dell’Università 12 20121 Milano (MI) "
            "tel. 02 1234567 · info@rossi.example"
        )
        # The heading of the check, the counts.
        assert KICKER in first
        assert "Informativa «clienti».docx" in first
        assert (
            "Controllato il 24/11/2026 sui testi consolidati di EUR-Lex. "
            "Data del documento: 12/01/2026. Norme citate ricontrollate il 20/11/2026."
        ) in first
        assert "3 da correggere 1 da controllare 1 a posto 1 fuori copertura" in first
        assert DIFF_LEGEND in first
        # Every group, every finding, as in the HTML.
        for title in (
            "Da correggere",
            "Da controllare",
            "A posto",
            "Atti che il controllo non legge",
        ):
            assert title in text
        for label in (
            "Citazione superata",
            "Citazione diversa dal testo ufficiale",
            "Non esiste nel testo vigente",
            "Atto non indicato",
            "Citazione verificata",
        ):
            assert label in text
        assert "Riga 2: Ai sensi dell'art. 4 dell'AI Act, i deployer" in text
        assert "Nel documento: «adottano misure per garantire nella misura del possibile" in text
        assert (
            "Differenze tra il testo consolidato al 12/07/2024 e il testo consolidato al 27/07/2026"
            in text
        )
        assert "Differenze tra la citazione nel documento e il testo ufficiale" in text
        assert "Testo ufficiale: «Le informazioni di cui ai paragrafi da 1 a 4" in text
        assert "Il documento non dice di quale atto è questo riferimento." in text
        # The texts compared with: their date, on the cards and in the table of what is fine.
        assert f"{COMPARED_WITH}: testo consolidato al 27/07/2026." in text
        assert (
            "art. 13 del GDPR GDPR, art. 13 Citazione verificata testo consolidato al 04/05/2016"
            in text
        )
        # The acts not read, with why.
        assert NOT_READ_INTRO in text
        assert "Questa fonte non legge i testi italiani: da controllare a mano." in text
        # The notes on the sources, as at the foot of the HTML.
        assert _flat(report._FOOTER) in text
        assert _flat(report._FOOTER_ITALIAN) in text
        assert "Testi italiani: Normattiva, dati aperti di dati.normattiva.it" in text

    def test_normaai_only_in_small_at_the_foot_of_every_page(self):
        read = _Read(render_pdf(_check(), STUDIO))
        pages = len(read.pages)
        assert pages >= 2
        for number, page in enumerate(read.pages, 1):
            flat = _flat(page)
            assert flat.endswith(f"Pagina {number} di {pages} · {FOOT_CREDIT}")
            assert "Documento riservato al cliente." in flat  # the practice's note
        assert read.text.count("NormaAI") == pages
        sizes = [size for pieces in read.sizes for text, size in pieces if "NormaAI" in text]
        assert sizes and max(sizes) <= 7.5
        # The practice's name is large on the first page.
        name_sizes = [s for text, s in read.sizes[0] if "Studio Legale Rossi" in text]
        assert max(name_sizes) >= 14

    def test_the_other_pages_carry_the_name_of_the_practice(self):
        read = _Read(render_pdf(_check(), STUDIO))
        second = _flat(read.pages[1])
        assert second.startswith("Studio Legale Rossi & Associati Informativa «clienti».docx")

    def test_links_to_the_texts_in_force(self):
        read = _Read(render_pdf(_check(), STUDIO))
        links = read.links()
        assert (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02024R1689-20260727" in links
        )
        assert (
            "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:02016R0679-20160504" in links
        )
        assert (
            "https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196"
            in links
        )
        assert "https://creativecommons.org/licenses/by/4.0/deed.it" in links
        assert "Testo vigente su EUR-Lex" in read.text

    def test_metadata_name_the_practice_and_say_nothing_of_ai(self):
        data = render_pdf(_check(), STUDIO)
        meta = PdfReader(io.BytesIO(data)).metadata
        assert meta["/Author"] == "Studio Legale Rossi & Associati"
        assert meta["/Creator"] == "NormaAI"
        assert meta["/Title"] == "Controllo del documento: Informativa «clienti».docx"
        assert meta.get("/Keywords") in (None, "")
        assert b"AIGenerated" not in data and b"normaai:AIGenerated" not in data
        assert AI_NOTICE_IT not in _Read(data).text
        assert b"/Lang (it)" in data or b"/Lang(it)" in data

    def test_the_logo_is_on_the_first_page(self):
        logo, logo_type = normalize_logo(_png())
        with_logo = Letterhead(name="Studio Rossi", logo=logo, logo_type=logo_type, configured=True)
        reader = PdfReader(io.BytesIO(render_pdf(_check(), with_logo)))
        assert len(reader.pages[0].images) == 1
        assert all(len(page.images) == 0 for page in reader.pages[1:])
        without = PdfReader(io.BytesIO(render_pdf(_check(), Letterhead(name="Studio Rossi"))))
        assert all(len(page.images) == 0 for page in without.pages)

    def test_a_logo_that_does_not_read_does_not_stop_the_report(self):
        broken = Letterhead(name="Studio Rossi", logo=b"not an image", logo_type="image/png")
        read = _Read(render_pdf(_check(), broken))
        assert read.pages[0].startswith("Studio Rossi")
        assert len(read.reader.pages[0].images) == 0

    def test_without_a_letterhead_the_name_of_the_organisation(self):
        read = _Read(render_pdf(_check(CLEAN_DOCUMENT), Letterhead(name="Studio Bianchi")))
        assert _flat(read.pages[0]).startswith(f"Studio Bianchi {KICKER}")
        assert DIFF_LEGEND not in read.text  # no differences to read

    def test_a_document_without_references(self):
        read = _Read(render_pdf(_from_json([]), STUDIO))
        assert NO_REFERENCES in read.text
        assert "0 da correggere 0 da controllare 0 a posto 0 fuori copertura" in read.text

    def test_a_repealed_article_and_an_italian_provision(self):
        last = "Articolo 7 Testo dell'articolo abrogato. " + "parola " * 400
        repealed = _stored(
            before={"version_label": "testo in vigore fino al 31/12/2025", "text": last},
            messages=["L'art. 7 non c'è più nel testo vigente."],
        )
        italian = _stored(
            id="f2",
            group="a_posto",
            status={"code": "esiste", "label": "Articolo vigente"},
            line=5,
            raw="art. 13 del d.lgs. 196/2003",
            context="Resta fermo l'art. 13 del d.lgs. 196/2003.",
            version={"id": "x", "as_of": "2026-11-24", "label": "testo vigente al 24/11/2026"},
            url="https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2003;196~art13",
        )
        read = _Read(render_pdf(_from_json([repealed, italian]), STUDIO))
        text = read.text
        assert "Ultimo testo: testo in vigore fino al 31/12/2025" in text
        assert "[...]" in text and text.count("parola") < 250  # cut like the HTML
        assert "testo vigente al 24/11/2026" in text
        assert italian["url"] in read.links()

    def test_a_long_check_goes_on_over_the_pages(self):
        check = _check("\n".join([DOCUMENT] * 12))
        read = _Read(render_pdf(check, STUDIO))
        assert len(read.pages) > 8
        assert read.text.count("Citazione superata") == 12
        # The table of what is fine repeats its headings on a new page.
        assert sum("Riga Nel documento Norma Esito" in _flat(page) for page in read.pages) >= 1

    def test_without_the_fonts_helvetica_and_latin1(self):
        with patch.object(pdf_module, "_FONTS_DIR", pdf_module._FONTS_DIR / "missing"):
            data = render_pdf(_check(), Letterhead(name="Studio “Rossi” – àèìòù"))
        read = _Read(data)
        assert read.pages[0].startswith('Studio "Rossi" - àèìòù')
        assert "Citazione superata" in read.text


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Policy uso IA.pdf", "Policy uso IA.controllo.pdf"),
        ("nota.txt", "nota.controllo.pdf"),
        ("a/b:c*?.docx", "a_b_c_.controllo.pdf"),
        ("", "report.controllo.pdf"),
        ("senza estensione", "senza estensione.controllo.pdf"),
    ],
)
def test_pdf_filename(filename, expected):
    assert pdf_filename(filename) == expected
