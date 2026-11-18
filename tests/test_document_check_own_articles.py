"""The articles of the document itself are not articles of the law it names.

A contract that names the GDPR numbers its own articles ("Art. 5 - Durata")
and refers to them ("art. 12 del presente Contratto", "art. 7 delle Condizioni
Generali"). Until 18 November 2026 they were given to the GDPR, checked there
(valid, or not existing) and put in the lock file, so the surveillance warned
about changes that had nothing to do with the document. They are left out of
the check and of the lock, and listed as the document's own articles. Offline,
with the stand-in for CELLAR of test_document_check.
"""

from __future__ import annotations

import pytest

from src.document_check.check import build_lock, check_text
from src.document_check.extract import extract_references, own_articles
from src.document_check.report import render_html
from tests.test_document_check import FakeSource

GDPR = "32016R0679"


def _checked(text: str) -> list[tuple[str, str | None]]:
    """(provision, act) of each reference the check reads."""
    return [
        (", ".join(p.label for p in r.provisions), r.act.key if r.act else None)
        for r in extract_references(text)
    ]


def _own(text: str) -> list[str]:
    return [r.raw for r in own_articles(text)]


CONTRACT = """ACCORDO SUL TRATTAMENTO DEI DATI PERSONALI
tra Studio Rossi (Titolare) e Servizi Beta S.r.l. (Responsabile), ai sensi dell'art. 28 del Regolamento (UE) 2016/679 (GDPR).

Art. 1 - Oggetto
Il Responsabile tratta i dati per conto del Titolare secondo le istruzioni dell'art. 3 del presente Accordo.

Art. 5 - Durata
Il presente Contratto dura un anno; per il recesso vale l'art. 12 del presente Contratto e, per i corrispettivi, l'art. 7 delle Condizioni Generali.

Articolo 6 (Sicurezza)
Il Responsabile adotta le misure dell'art. 32 del GDPR e notifica le violazioni entro 24 ore (art. 33 GDPR).

Art. 33 GDPR - Notifica
Si applica anche l'art. 9 del GDPR.
"""


def test_a_contracts_own_articles_are_not_given_to_the_gdpr():
    assert _checked(CONTRACT) == [
        ("art. 28", GDPR),
        ("art. 32", GDPR),
        ("art. 33", GDPR),
        ("art. 33", GDPR),
        ("art. 9", GDPR),
    ]
    assert _own(CONTRACT) == [
        "Art. 1",
        "art. 3 del presente Accordo",
        "Art. 5",
        "art. 12 del presente Contratto",
        "art. 7 delle Condizioni Generali",
        "Articolo 6",
    ]


def test_they_are_neither_checked_nor_put_in_the_lock_file():
    source = FakeSource()
    check = check_text(CONTRACT, source, document="dpa.txt", today="2026-11-18")
    keys = {
        (f.act.key if f.act else None, f.provision.key if f.provision else None)
        for f in check.findings
    }
    assert ("32016R0679", "art:12") not in keys and ("32016R0679", "art:5") not in keys
    assert {d["chiave"] for d in build_lock(check)["dipendenze"]} <= {
        "art:28",
        "art:32",
        "art:33",
        "art:9",
        "art:13",
    }
    assert [r.raw for r in check.own_articles] == _own(CONTRACT)
    html = render_html(check)
    assert "Articoli del documento, non controllati" in html
    assert "art. 12 del presente Contratto" in html


@pytest.mark.parametrize(
    "words",
    [
        "art. 4 del presente contratto",
        "art. 4 del presente Accordo",
        "art. 4 del presente atto",
        "art. 4 del presente documento",
        "art. 4 del presente regolamento",
        "art. 4 del presente disciplinare",
        "art. 4 del presente Statuto",
        "art. 4 delle presenti condizioni",
        "art. 4 delle presenti Condizioni Generali",
        "art. 4 delle Condizioni Generali di Contratto",
        "art. 4 delle condizioni generali di servizio",
        "art. 4 delle Condizioni Generali d'uso",
        "art. 4 del contratto",
        "art. 4 dell'accordo",
        "artt. 4 e 5 del presente Contratto",
        "Article 4 of this Agreement",
        "Article 4 of this Contract",
        "Section 4 of these Terms",
        "Article 4 of these Terms",
        "Article 4 of the Terms and Conditions",
        "Article 4 hereof",
        "Article 4 herein",
        "Article 4 hereunder",
    ],
)
def test_references_to_the_document_itself(words):
    text = f"Il Regolamento (UE) 2016/679 si applica. Si veda {words}."
    assert _checked(text) == []
    if words.startswith(("art", "Art")):
        assert _own(text) == [words]


@pytest.mark.parametrize(
    "heading",
    [
        "Art. 5 - Durata",
        "Art. 5 – Durata",
        "Articolo 5 (Durata)",
        "Art. 5. Durata",
        "ARTICOLO 5 - OGGETTO",
        "Article 5 - Term",
        "Article 5. Fees",
        "Art. 5: Recesso",
    ],
)
def test_headings_of_a_contract(heading):
    text = (
        f"Il presente Contratto richiama il GDPR.\n\n{heading}\nLe parti convengono quanto segue."
    )
    assert _checked(text) == []
    assert len(_own(text)) == 1


def test_sections_are_not_references_at_all():
    assert _checked("Under the GDPR.\nSection 5. Fees\nThe fees are due monthly.") == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Il presente Contratto richiama il GDPR.\nArt. 33 GDPR - Notifica\nIl Responsabile notifica.",
            ("art. 33", GDPR),
        ),
        (
            "Il presente Contratto richiama il GDPR.\nArticolo 13 del Regolamento (UE) 2016/679\nInformativa.",
            ("art. 13", GDPR),
        ),
        (
            "Il presente Contratto richiama il GDPR.\nart. 28 del GDPR (Responsabile del trattamento)\nIl Responsabile.",
            ("art. 28", GDPR),
        ),
    ],
)
def test_an_act_named_in_the_same_sentence_wins(text, expected):
    assert _checked(text) == [expected]
    assert _own(text) == []


def test_a_notice_that_names_the_gdpr_once_keeps_its_articles():
    notice = (
        "Informativa ai sensi del Regolamento (UE) 2016/679.\n"
        "Lei ha diritto di accedere ai dati (art. 15) e di chiederne la cancellazione (art. 17).\n"
        "I suoi diritti:\n"
        "Art. 15 - Diritto di accesso\n"
        "Art. 16 - Diritto di rettifica\n"
    )
    assert _checked(notice) == [
        ("art. 15", GDPR),
        ("art. 17", GDPR),
        ("art. 15", GDPR),
        ("art. 16", GDPR),
    ]
    assert _own(notice) == []
    lock = build_lock(check_text(notice, FakeSource()))
    assert lock["dipendenze"] == [] or all(d["atto"] == GDPR for d in lock["dipendenze"])


def test_english_terms_of_service():
    terms = (
        "These Terms govern the Service. Personal data are processed under the GDPR.\n"
        "Article 3 - Fees\n"
        "Fees are set out in Article 4 of these Terms and in Article 6 hereof; Article 28 GDPR applies "
        "to processing.\n"
    )
    assert _checked(terms) == [("art. 28", GDPR)]
    assert _own(terms) == ["Article 3", "Article 4 of these Terms", "Article 6 hereof"]
