"""A consolidated text dated after the day of the check is not the text in force.

CELLAR lists consolidated texts ahead of their date: in November 2026 the
Accounting Directive (2013/34/EU) had one as consolidated on 30 January 2027
(02013L0034-20270130), and the check, which took the newest version, read the
2027 text as the law in force. The check now takes the newest version whose
date is not after its day, says that a later one exists, and the re-check
neither reads it nor calls it a change before its date. Offline, with a
stand-in for CELLAR.
"""

from __future__ import annotations

import re

from src.document_check.check import (
    NOT_FOUND,
    OUTDATED,
    VALID,
    VERIFIED,
    build_lock,
    check_text,
    recheck,
)
from src.document_check.official import ArticleText, TextUnavailableError, Version
from tests.test_document_check import _article

DIRECTIVE = "32013L0034"
ART3_2023 = (
    "Articolo 3\nCategorie di imprese e di gruppi\n"
    "1. Ai fini dell'applicazione di una o più delle opzioni di cui all'articolo 36, gli Stati "
    "membri definiscono microimprese le imprese che alla data di chiusura del bilancio non "
    "superano i limiti numerici di almeno due dei tre criteri seguenti: totale dello stato "
    "patrimoniale: 350 000 EUR; ricavi netti delle vendite e delle prestazioni: 700 000 EUR.\n"
    "2. Piccole imprese.\n3. Medie imprese.\n4. Grandi imprese."
)
ART3_2026 = ART3_2023.replace("350 000 EUR", "450 000 EUR").replace("700 000 EUR", "900 000 EUR")
ART3_2027 = ART3_2026.replace("Grandi imprese.", "Grandi imprese, con le nuove soglie.")
QUOTE_2026 = "totale dello stato patrimoniale: 450 000 EUR; ricavi netti delle vendite e delle prestazioni: 900 000 EUR"
QUOTE_2027 = "Grandi imprese, con le nuove soglie"
QUOTE_2023 = QUOTE_2026.replace("450 000", "350 000").replace("900 000", "700 000")


class AheadSource:
    """CELLAR stand-in: the Accounting Directive with a consolidated text dated in 2027."""

    def __init__(self) -> None:
        self.asked: list[str] = []
        self._articles = {
            DIRECTIVE: ART3_2023,
            "02013L0034-20240109": ART3_2023,
            "02013L0034-20260318": ART3_2026,
            "02013L0034-20270130": ART3_2027,
        }

    def versions(self, celex: str) -> list[Version]:
        if celex != DIRECTIVE:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        return [
            Version(DIRECTIVE, None),
            Version("02013L0034-20240109", "2024-01-09"),
            Version("02013L0034-20260318", "2026-03-18"),
            Version("02013L0034-20270130", "2027-01-30"),
        ]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        self.asked.append(version.celex)
        return [_article("Art. 3", self._articles[version.celex])]


def _one(text: str, source: AheadSource, today: str, **kwargs):
    [finding] = check_text(text, source, today=today, **kwargs).findings
    return finding


def test_a_version_dated_after_the_check_is_not_the_text_in_force():
    source = AheadSource()
    f = _one("Le soglie sono all'art. 3, par. 1, della Direttiva 2013/34/UE.", source, "2026-11-18")
    assert f.status is VALID
    assert f.version is not None and f.version.celex == "02013L0034-20260318"
    assert f.article is not None and f.article.text == ART3_2026
    assert (
        "Esiste già il testo consolidato al 30/01/2027, non ancora applicabile: il controllo è "
        "fatto sul testo consolidato al 18/03/2026." in f.messages
    )
    assert "02013L0034-20270130" not in source.asked
    [entry] = build_lock(
        check_text("Art. 3 della Direttiva 2013/34/UE.", AheadSource(), today="2026-11-18")
    )["dipendenze"]
    assert entry["versione"] == "02013L0034-20260318" and entry["consolidato_al"] == "2026-03-18"


def test_from_its_date_that_version_is_the_text_in_force():
    f = _one("Le soglie sono all'art. 3 della Direttiva 2013/34/UE.", AheadSource(), "2027-01-30")
    assert f.version is not None and f.version.celex == "02013L0034-20270130"
    assert not any("non ancora applicabile" in m for m in f.messages)


def test_quotes_are_judged_on_the_text_in_force_on_the_day_of_the_check():
    today = "2026-11-18"
    verified = _one(f"L'art. 3 della Direttiva 2013/34/UE: «{QUOTE_2026}».", AheadSource(), today)
    assert verified.status is VERIFIED
    # The words of 2027 are not in force yet: not verified, and not "outdated" either.
    ahead = _one(
        f"L'art. 3 della Direttiva 2013/34/UE prevede: «{QUOTE_2027} di bilancio».",
        AheadSource(),
        today,
    )
    assert ahead.status is NOT_FOUND
    outdated = _one(f"L'art. 3 della Direttiva 2013/34/UE: «{QUOTE_2023}».", AheadSource(), today)
    assert outdated.status is OUTDATED
    assert (
        outdated.before_version is not None
        and outdated.before_version.celex == "02013L0034-20240109"
    )


def test_the_recheck_does_not_call_a_version_not_yet_applicable_a_change():
    lock = build_lock(
        check_text("Vedi l'art. 3 della Direttiva 2013/34/UE.", AheadSource(), today="2026-11-18")
    )
    source = AheadSource()
    [change] = recheck(lock, source, today="2026-11-18")
    assert change.code == "invariato"
    assert re.search(r"testo consolidato al 30/01/2027, non ancora applicabile", change.message)
    assert source.asked == []
    [later] = recheck(lock, AheadSource(), today="2027-02-01")
    assert later.code == "cambiato" and later.after == ART3_2027
