"""Articles cited next to an act that amends another (src/document_check/extract.py).

"Article 50(2), as amended by Regulation (EU) 2026/1744" is Article 50(2) of the
AI Act, read in its consolidated text, not an article of the Digital Omnibus on
AI, which has four. Offline, with the stand-in for CELLAR of test_document_check.

The last test runs the check on the 38 answers of the Omnibus audit of
17 November 2026, which are not in the repository: it looks for a folder
``omnibus_audit/risposte`` above the repository, or the one named by
NORMAAI_OMNIBUS_ANSWERS, and reads the official texts already cached in
~/.cache/normaai/cellar (or NORMAAI_CELLAR_CACHE) without asking CELLAR. It is
skipped when either is missing, as in CI.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from src.document_check.check import MISSING, VALID, check_text
from src.document_check.extract import extract_references
from src.document_check.official import CellarTextSource, Version
from tests.test_document_check import AI_NEW, FakeSource, _article

AI_ACT = "32024R1689"
OMNIBUS = "32026R1744"

ART10 = (
    "Articolo 10\nDati e governance dei dati\n1. Testo del paragrafo uno.\n"
    "2. Testo del paragrafo due.\n3. Testo del paragrafo tre.\n4. Testo del paragrafo quattro.\n"
    "6. Testo del paragrafo sei."
)
ART113 = (
    "Articolo 113\nEntrata in vigore e applicazione\nIl presente regolamento entra in vigore il "
    "ventesimo giorno successivo alla pubblicazione.\nEsso si applica a decorrere dal 2 agosto 2026."
)


class OmnibusSource(FakeSource):
    """The stand-in for CELLAR, with the Digital Omnibus on AI (Articles 1 to 4 only) and
    Articles 10 (paragraph 5 deleted) and 113 (no numbered paragraphs) of the AI Act."""

    def __init__(self) -> None:
        super().__init__()
        self._versions[OMNIBUS] = [Version(OMNIBUS, None)]
        self._articles[OMNIBUS] = [
            _article(f"Art. {n}", f"Articolo {n}\nModifiche e entrata in vigore.")
            for n in range(1, 5)
        ]
        self._articles["02024R1689-20260727"] = [
            *AI_NEW,
            _article("Art. 10", ART10),
            _article("Art. 113", ART113),
        ]


def _one(text: str):
    refs = extract_references(text)
    assert len(refs) == 1, [r.raw for r in refs]
    return refs[0]


# ─── The article belongs to the act amended ──────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "Under Regulation (EU) 2024/1689, as amended by Regulation (EU) 2026/1744, "
        "Article 50(2) requires machine-readable marking.",
        "Article 50(2), as amended by Regulation (EU) 2026/1744, applies from 2 December 2026.",
        "Following the amendment by Regulation (EU) 2026/1744, the obligations for systems "
        "classified under Article 6(2) apply from 2 December 2027.",
        "Regulation (EU) 2026/1744, amending Article 50(2), gives providers until 2 December 2026.",
        "Regulation (EU) 2026/1744 entered into force on 27 July 2026; check the consolidated "
        "text of Article 50 before relying on it.",
        "Under the AI Act as amended by the Digital Omnibus on AI (Regulation (EU) 2026/1744), "
        "the obligations for Annex I systems apply from 2 August 2028.",
        "Il Regolamento (UE) 2024/1689, come modificato dal Regolamento (UE) 2026/1744, "
        "all'articolo 50 impone la marcatura.",
        "L'articolo 50, modificato dal Regolamento (UE) 2026/1744, si applica dal 2 dicembre 2026.",
        "Il Regolamento (UE) 2026/1744, che modifica l'articolo 50, concede tempo fino al "
        "2 dicembre 2026.",
        "Il Regolamento (UE) 2026/1744 è in vigore dal 27 luglio 2026: va letto il testo "
        "consolidato dell'articolo 50.",
    ],
)
def test_an_article_next_to_the_amending_act_is_the_amended_acts(text):
    ref = _one(text)
    assert ref.act is not None and ref.act.key == AI_ACT
    assert ref.act_inferred
    assert ref.amended_by is not None and ref.amended_by.key == OMNIBUS


@pytest.mark.parametrize(
    "text",
    [
        "Article 50(2) of Regulation (EU) 2024/1689, as amended by Regulation (EU) 2026/1744, "
        "requires machine-readable marking.",
        "L'articolo 50, paragrafo 2, del Regolamento (UE) 2024/1689, come modificato dal "
        "Regolamento (UE) 2026/1744, impone la marcatura.",
    ],
)
def test_the_amended_act_written_with_the_article_stays(text):
    ref = _one(text)
    assert ref.act is not None and ref.act.key == AI_ACT
    assert not ref.act_inferred and ref.amended_by is None


@pytest.mark.parametrize(
    "text",
    [
        "Article 4 of Regulation (EU) 2026/1744 sets its entry into force.",
        "L'articolo 1 del Regolamento (UE) 2026/1744 modifica il regolamento (UE) 2024/1689.",
    ],
)
def test_an_article_written_as_the_amending_acts_own_stays_with_it(text):
    ref = extract_references(text)[0]
    assert ref.act is not None and ref.act.key == OMNIBUS
    assert not ref.act_inferred


def test_a_paragraph_that_names_only_the_amending_act():
    refs = extract_references(
        "The Digital Omnibus on AI was published as Regulation (EU) 2026/1744.\n"
        "Article 50(2) requires machine-readable marking."
    )
    assert refs[0].act is not None and refs[0].act.key == AI_ACT and refs[0].act_inferred
    assert refs[0].amended_by is not None and refs[0].amended_by.key == OMNIBUS


def test_words_also_mark_acts_the_check_does_not_know_as_amending():
    # The words make the CSRD the amending act, with its name in between; the
    # article is the Accounting Directive's, named before.
    ref = _one(
        "Under Directive 2013/34/EU, as amended by the Corporate Sustainability Reporting "
        "Directive (Directive (EU) 2022/2464), Article 19a requires a sustainability statement."
    )
    assert ref.act is not None and ref.act.key == "32013L0034"
    assert ref.amended_by is not None and ref.amended_by.key == "32022L2464"
    # The amended act is not named: the article stays without act, not with the amending act.
    alone = _one(
        "Directive (EU) 2022/2464, amending the Accounting Directive, inserted Article 19a."
    )
    assert alone.act is None
    italian = _one(
        "Il d.lgs. 196/2003, come modificato dal d.lgs. 101/2018, all'art. 2-ter prevede una base "
        "giuridica."
    )
    assert italian.act is not None and italian.act.key == "IT:dlgs:2003:196"
    assert italian.amended_by is not None and italian.amended_by.key == "IT:dlgs:2018:101"
    unnamed = _one("L'art. 2-ter, come modificato dal d.lgs. 101/2018, prevede una base giuridica.")
    assert unnamed.act is None


# ─── Acts named side by side ─────────────────────────────────────────


def test_acts_named_side_by_side_do_not_take_the_article_after_them():
    refs = extract_references(
        "Under the AI Act, Article 4a(1) allows the processing.\n"
        "In addition to complying with Regulation (EU) 2016/679 [GDPR], Regulation (EU) 2018/1725, "
        "or Directive (EU) 2016/680, all six conditions in Article 4a(1) must be met."
    )
    assert refs[0].act is not None and refs[0].act.key == AI_ACT
    assert refs[1].act is None
    italian = _one(
        "Oltre al Regolamento (UE) 2016/679 e alla Direttiva (UE) 2016/680, vanno rispettate le "
        "condizioni dell'articolo 4 bis."
    )
    assert italian.act is None


def test_two_names_of_one_act_are_not_a_list():
    ref = _one("Il GDPR (Regolamento (UE) 2016/679) chiede trasparenza; vedi l'art. 12.")
    assert ref.act is not None and ref.act.key == "32016R0679" and ref.act_inferred


# ─── Checking ────────────────────────────────────────────────────────


def test_checked_on_the_consolidated_text_of_the_act_amended():
    check = check_text(
        "Article 50(2), as amended by Regulation (EU) 2026/1744, applies from 2 December 2026.",
        OmnibusSource(),
    )
    [finding] = check.findings
    assert finding.act is not None and finding.act.key == AI_ACT
    assert finding.status is VALID
    assert finding.version is not None and finding.version.celex == "02024R1689-20260727"
    assert (
        "Atto dedotto dal contesto: AI Act, come modificato da Regulation (EU) 2026/1744 "
        "(Omnibus digitale sull'IA)." in finding.messages
    )
    assert not any("non esiste" in m for m in finding.messages)


def test_the_amending_acts_own_article_is_checked_in_it():
    check = check_text(
        "Article 4 of Regulation (EU) 2026/1744 sets its entry into force.", OmnibusSource()
    )
    [finding] = check.findings
    assert finding.act is not None and finding.act.key == OMNIBUS
    assert finding.status is VALID


def test_a_missing_paragraph_lists_the_paragraphs_there_are():
    check = check_text(
        "Under Regulation (EU) 2024/1689, as amended by Regulation (EU) 2026/1744, Article 10(5) "
        "was deleted.",
        OmnibusSource(),
    )
    [finding] = check.findings
    assert finding.status is MISSING
    assert any("l'art. 10 ha i paragrafi 1-4 e 6." in m for m in finding.messages)


def test_an_article_without_numbered_paragraphs_keeps_its_finding():
    check = check_text(
        "Article 113(3) of Regulation (EU) 2024/1689, as amended, sets the dates.", OmnibusSource()
    )
    [finding] = check.findings
    assert finding.status is MISSING
    assert any("l'art. 113 non ha paragrafi numerati." in m for m in finding.messages)


# ─── The answers of the Omnibus audit ────────────────────────────────


def _omnibus_answers() -> Path | None:
    named = os.environ.get("NORMAAI_OMNIBUS_ANSWERS")
    folders = (
        [Path(named)]
        if named
        else [parent / "omnibus_audit" / "risposte" for parent in Path(__file__).resolve().parents]
    )
    return next((f for f in folders if f.is_dir() and any(f.glob("*.jsonl"))), None)


ANSWERS = _omnibus_answers()
CELLAR_CACHE = Path(
    os.environ.get("NORMAAI_CELLAR_CACHE") or Path.home() / ".cache" / "normaai" / "cellar"
)
CACHED = all(
    (CELLAR_CACHE / name).exists()
    for name in (
        f"{AI_ACT}.versions.json",
        "02024R1689-20260727.EN.xhtml",
        f"{OMNIBUS}.versions.json",
        f"{OMNIBUS}.EN.xhtml",
    )
)


class _Offline:
    """The EUR-Lex client of a check that must not ask CELLAR: every call fails."""

    def __getattr__(self, name: str):
        def unreachable(*args, **kwargs):
            raise ConnectionError(f"{name}: offline")

        return unreachable


@pytest.mark.skipif(
    ANSWERS is None or not CACHED,
    reason="the Omnibus audit answers or the cached official texts are not on this machine",
)
def test_the_omnibus_answers_give_no_article_to_the_omnibus(tmp_path):
    assert ANSWERS is not None
    cache = tmp_path / "cellar"
    shutil.copytree(CELLAR_CACHE, cache)  # the check writes nothing to the user's cache
    source = CellarTextSource(cache, client=_Offline())  # type: ignore[arg-type]
    findings = []
    for path in sorted(ANSWERS.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            answer = json.loads(line)
            # "\ue015" is a mark of the assistant's interface, not text.
            text = (answer.get("answer_text") or "").replace("\ue015", " ")
            if not text or str(answer.get("notes", "")).startswith("BLOCKED"):
                continue
            check = check_text(
                text,
                source,
                document=f"{path.stem}:{answer['id']}",
                lang="EN",
                document_date="2026-11-17",
                today="2026-11-17",
            )
            findings += [(check.document, f) for f in check.findings]
    assert findings
    wrong = [
        (document, f.reference.raw, f.messages)
        for document, f in findings
        if any("non esiste nel testo originale (Regulation (EU) 2026/1744" in m for m in f.messages)
        or (f.act is not None and f.act.key == OMNIBUS and f.status is MISSING)
    ]
    assert wrong == []
    # The finding the Omnibus did not cause stays: Article 113 has no numbered paragraphs.
    kept = [
        f
        for document, f in findings
        if document == "perplexity:Q01" and f.provision and f.provision.label == "art. 113, par. 3"
    ]
    assert len(kept) == 1 and kept[0].status is MISSING
    assert any("non ha paragrafi numerati" in m for m in kept[0].messages)
