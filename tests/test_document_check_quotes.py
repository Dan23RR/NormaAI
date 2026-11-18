"""Quotes checked where they are: in the paragraph cited.

A quote cited as paragraph 2 that is in paragraph 1 is not verified: it is
"Citazione in un altro paragrafo" (for Italian law, "in un altro comma"), to
be corrected.

Offline: a stand-in for CELLAR with paragraphs 1 and 2 of Article 33 of the
GDPR in Italian and in English (the official wording), and the Normattiva
answers recorded in tests/fixtures/normattiva.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.document_check.check import (
    OTHER_COMMA,
    OTHER_PARAGRAPH,
    VERIFIED,
    check_text,
)
from src.document_check.normattiva import NormattivaTextSource
from src.document_check.official import ArticleText, TextUnavailableError, Version
from src.document_check.serialize import findings_to_json, summarize
from src.document_check.sources import OfficialSources
from tests.test_document_check import _article
from tests.test_document_check_normattiva import NoEuSource, RecordedApi

GDPR = "32016R0679"
ART33_IT = (
    "Articolo 33\nNotifica di una violazione dei dati personali all'autorità di controllo\n"
    "1. In caso di violazione dei dati personali, il titolare del trattamento notifica la "
    "violazione all'autorità di controllo competente a norma dell'articolo 55 senza "
    "ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto a "
    "conoscenza, a meno che sia improbabile che la violazione dei dati personali presenti un "
    "rischio per i diritti e le libertà delle persone fisiche.\n"
    "2. Il responsabile del trattamento informa il titolare del trattamento senza ingiustificato "
    "ritardo dopo essere venuto a conoscenza della violazione."
)
ART33_EN = (
    "Article 33\nNotification of a personal data breach to the supervisory authority\n"
    "1. In the case of a personal data breach, the controller shall without undue delay and, "
    "where feasible, not later than 72 hours after having become aware of it, notify the "
    "personal data breach to the supervisory authority competent in accordance with Article 55, "
    "unless the personal data breach is unlikely to result in a risk to the rights and freedoms "
    "of natural persons.\n"
    "2. The processor shall notify the controller without undue delay after becoming aware of a "
    "personal data breach."
)
QUOTE_IT = (
    "senza ingiustificato ritardo e, ove possibile, entro 72 ore dal momento in cui ne è venuto "
    "a conoscenza"
)
QUOTE_EN = (
    "the controller shall without undue delay and, where feasible, not later than 72 hours after "
    "having become aware of it, notify the personal data breach"
)


class BilingualSource:
    """CELLAR stand-in: Article 33 of the GDPR in Italian and English; records what it reads."""

    def __init__(self, langs: tuple[str, ...] = ("IT", "EN")) -> None:
        self.langs = set(langs)
        self.asked: list[tuple[str, str]] = []

    def versions(self, celex: str) -> list[Version]:
        if celex != GDPR:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        return [Version(GDPR, None), Version("02016R0679-20160504", "2016-05-04")]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        lang = lang.upper()
        self.asked.append((version.celex, lang))
        if lang not in self.langs:
            raise TextUnavailableError(f"CELLAR non ha il testo di {version.celex} in {lang}")
        return [_article("Art. 33", ART33_IT if lang == "IT" else ART33_EN)]


def _one(text: str, source: Any, **kwargs: Any):
    kwargs.setdefault("today", "2026-11-18")
    check = check_text(text, source, **kwargs)
    assert len(check.findings) == 1, [f.reference.raw for f in check.findings]
    return check.findings[0]


# ─── The paragraph cited ─────────────────────────────────────────────


def test_a_quote_cited_as_paragraph_2_that_is_in_paragraph_1_is_to_be_corrected():
    f = _one(
        f"Ai sensi dell'art. 33, par. 2, del GDPR, il titolare notifica «{QUOTE_IT}».",
        BilingualSource(),
    )
    assert f.status is OTHER_PARAGRAPH
    assert f.status.code == "altro_paragrafo" and f.status.group == "correggere"
    assert f.official_quote is not None and "entro 72 ore" in f.official_quote
    assert (
        "La citazione è nel testo vigente, parola per parola, ma nel par. 1, non nel par. 2 citato."
        in f.messages
    )
    [item] = findings_to_json(
        check_text(f"Art. 33, par. 2, GDPR: «{QUOTE_IT}».", BilingualSource()), {}
    )
    assert item["status"] == {"code": "altro_paragrafo", "label": "Citazione in un altro paragrafo"}
    assert summarize([item])[0] == "correggere"


@pytest.mark.parametrize(
    "reference",
    [
        "art. 33, par. 1, del GDPR",
        "art. 33 del GDPR",
        "art. 33, parr. 1 e 2, del GDPR",
        "Article 33(1) GDPR",
    ],
)
def test_a_quote_in_the_paragraph_cited_or_with_no_paragraph_cited_is_verified(reference):
    f = _one(f"Come prevede l'{reference}, il titolare notifica «{QUOTE_IT}».", BilingualSource())
    assert f.status is VERIFIED
    assert "La citazione è nel testo vigente, parola per parola." in f.messages


def test_a_quote_of_paragraph_2_cited_as_paragraph_1():
    quote = "il responsabile del trattamento informa il titolare del trattamento senza ingiustificato ritardo"
    f = _one(f"L'art. 33, paragrafo 1, del GDPR prevede che «{quote}».", BilingualSource())
    assert f.status is OTHER_PARAGRAPH
    assert any("ma nel par. 2, non nel par. 1 citato" in m for m in f.messages)


@pytest.fixture
def italian(tmp_path) -> OfficialSources:
    return OfficialSources(NoEuSource(), NormattivaTextSource(tmp_path, RecordedApi()))  # type: ignore[arg-type]


AI_LAW_QUOTE = (
    "l'utilizzo di sistemi di intelligenza artificiale nelle professioni intellettuali è "
    "finalizzato al solo esercizio delle attività strumentali e di supporto all'attività "
    "professionale"
)


def test_an_italian_quote_of_another_comma_is_to_be_corrected(italian):
    f = _one(
        f"L'art. 13, comma 2, della legge 132/2025 dispone che «{AI_LAW_QUOTE}».",
        italian,
        today="2026-11-11",
    )
    assert f.status is OTHER_COMMA
    assert f.status.code == "altro_comma" and f.status.group == "correggere"
    assert any("ma nel comma 1, non nel comma 2 citato" in m for m in f.messages)
    ok = _one(
        f"L'art. 13, comma 1, della legge 132/2025 dispone che «{AI_LAW_QUOTE}».",
        italian,
        today="2026-11-11",
    )
    assert ok.status is VERIFIED
