"""Tests for src/document_check/stale_facts: statements about rules an amendment changed.

Offline: the official texts come from OmnibusSource, a small stand-in for CELLAR
with the AI Act as adopted and as consolidated on 27 July 2026 (after the
Digital Omnibus on AI, Regulation (EU) 2026/1744), in English and in Italian.
The articles are shortened from the official texts.
"""

from __future__ import annotations

import importlib.util
import re
from html import escape
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.citation_verifier import parse_article
from src.document_check import serialize
from src.document_check.check import (
    CHANGED,
    MISSING,
    STALE,
    STALE_UNCONFIRMED,
    UNAVAILABLE,
    VALID,
    build_lock,
    check_text,
)
from src.document_check.official import ArticleText, TextUnavailableError, Version, find_article
from src.document_check.report import render_html, summary_lines
from src.document_check.stale_facts import (
    RULES,
    day_words,
    find_statements,
    official_passage,
    sentence_spans,
)
from tests.test_document_check import DOCUMENT, FakeSource

AI_ACT = "32024R1689"
CONSOLIDATED = "02024R1689-20260727"

ART4_OLD = {
    "EN": (
        "Article 4\nAI literacy\nProviders and deployers of AI systems shall take measures to "
        "ensure, to their best extent, a sufficient level of AI literacy of their staff and other "
        "persons dealing with the operation and use of AI systems on their behalf."
    ),
    "IT": (
        "Articolo 4\nAlfabetizzazione in materia di IA\nI fornitori e i deployer dei sistemi di IA "
        "adottano misure per garantire nella misura del possibile un livello sufficiente di "
        "alfabetizzazione in materia di IA del loro personale nonché di qualsiasi altra persona che "
        "si occupa del funzionamento e dell'utilizzo dei sistemi di IA per loro conto."
    ),
}
ART4_NEW = {
    "EN": (
        "Article 4\nAI literacy\n1. Providers and deployers of AI systems shall take measures to "
        "support the development of AI literacy of their staff and other persons dealing with the "
        "operation and use of AI systems on their behalf. This obligation does not require "
        "providers or deployers to guarantee any specific level of AI literacy of any individual.\n"
        "2. The Commission and the Member States shall support and facilitate the efforts of "
        "providers and deployers of AI systems, in particular SMEs."
    ),
    "IT": (
        "Articolo 4\nAlfabetizzazione in materia di IA\n1. I fornitori e i deployer di sistemi di IA "
        "adottano misure volte a sostenere lo sviluppo dell'alfabetizzazione in materia di IA del "
        "loro personale. Tale obbligo non impone ai fornitori o ai deployer di garantire un livello "
        "specifico di alfabetizzazione in materia di IA per alcuna persona.\n2. La Commissione e gli "
        "Stati membri sostengono e agevolano gli sforzi dei fornitori e dei deployer di sistemi di "
        "IA, in particolare delle PMI."
    ),
}
ART4A = {
    "EN": (
        "Article 4a\nProcessing of special categories of personal data for bias detection and "
        "correction\n1. To the extent strictly necessary to ensure bias detection and correction in "
        "relation to high-risk AI systems in accordance with Article 10(2), points (f) and (g), of "
        "this Regulation, providers of such systems may exceptionally process special categories "
        "of personal data, subject to appropriate safeguards for the fundamental rights and "
        "freedoms of natural persons.\n(a) the bias detection and correction cannot be effectively "
        "fulfilled by processing other data, including synthetic or anonymised data;\n2. Providers "
        "and deployers of other AI systems and models may exceptionally process special categories "
        "of personal data to the extent that such processing is strictly necessary."
    ),
    "IT": (
        "Articolo 4 bis\nTrattamento di categorie particolari di dati personali ai fini del "
        "rilevamento e della correzione delle distorsioni\n1. Nella misura strettamente necessaria "
        "a garantire il rilevamento e la correzione delle distorsioni in relazione ai sistemi di IA "
        "ad alto rischio in conformità dell'articolo 10, paragrafo 2, lettere f) e g), del presente "
        "regolamento, i fornitori di tali sistemi possono eccezionalmente trattare categorie "
        "particolari di dati personali, fatte salve le tutele adeguate per i diritti e le libertà "
        "fondamentali delle persone fisiche.\na) il rilevamento e la correzione delle distorsioni "
        "non possono essere realizzati efficacemente mediante il trattamento di altri dati;\n2. I "
        "fornitori e i deployer di altri sistemi e modelli di IA possono eccezionalmente trattare "
        "categorie particolari di dati personali."
    ),
}
ART10_OLD = {
    "EN": (
        "Article 10\nData and data governance\n1. High-risk AI systems shall be developed on the "
        "basis of data sets that meet the quality criteria.\n2. Data sets shall be subject to data "
        "governance practices.\n3. Data sets shall be relevant.\n4. Data sets shall take into "
        "account the setting.\n5. To the extent that it is strictly necessary for the purpose of "
        "ensuring bias detection and correction, the providers of such systems may exceptionally "
        "process special categories of personal data.\n6. Paragraphs 2 to 5 apply only to the "
        "testing data sets."
    ),
    "IT": (
        "Articolo 10\nDati e governance dei dati\n1. I sistemi di IA ad alto rischio sono sviluppati "
        "sulla base di set di dati che soddisfano i criteri di qualità.\n2. I set di dati sono "
        "soggetti a pratiche di governance.\n3. I set di dati sono pertinenti.\n4. I set di dati "
        "tengono conto dell'ambito.\n5. Nella misura in cui ciò sia strettamente necessario al fine "
        "di garantire il rilevamento e la correzione delle distorsioni, i fornitori di tali sistemi "
        "possono eccezionalmente trattare categorie particolari di dati personali.\n6. I paragrafi "
        "da 2 a 5 si applicano solo ai set di dati di prova."
    ),
}
ART10_NEW = {
    lang: re.sub(r"\n5\. [^\n]*", "", text)
    .replace("2 to 5", "2, 3 and 4")
    .replace("2 a 5", "2 a 4")
    for lang, text in ART10_OLD.items()
}
ART113_OLD = {
    "EN": (
        "Article 113\nEntry into force and application\nThis Regulation shall enter into force on "
        "the twentieth day following that of its publication in the Official Journal of the "
        "European Union.\nIt shall apply from 2 August 2026.\nHowever:\n(a) Chapters I and II shall "
        "apply from 2 February 2025;\n(b) Chapter III Section 4, Chapter V, Chapter VII and Chapter "
        "XII and Article 78 shall apply from 2 August 2025, with the exception of Article 101;\n"
        "(c) Article 6(1) and the corresponding obligations in this Regulation shall apply from "
        "2 August 2027."
    ),
    "IT": (
        "Articolo 113\nEntrata in vigore e applicazione\nIl presente regolamento entra in vigore il "
        "ventesimo giorno successivo alla pubblicazione nella Gazzetta ufficiale dell'Unione "
        "europea.\nSi applica a decorrere dal 2 agosto 2026.\nTuttavia:\na) I capi I e II si "
        "applicano a decorrere dal 2 febbraio 2025;\nb) Il capo III, sezione 4, il capo V, il capo "
        "VII, il capo XII e l'articolo 78 si applicano a decorrere dal 2 agosto 2025, ad eccezione "
        "dell'articolo 101;\nc) L'articolo 6, paragrafo 1, e i corrispondenti obblighi di cui al "
        "presente regolamento si applicano a decorrere dal 2 agosto 2027."
    ),
}
ART113_NEW = {
    "EN": ART113_OLD["EN"].split("\n(c)")[0]
    + (
        "\n(c) Chapter III, Sections 1, 2, and 3, with the exception of Article 6(5), shall apply "
        "from:\n(i) 2 December 2027 as regards AI systems classified as high-risk pursuant to "
        "Article 6(2) and Annex III; and\n(ii) 2 August 2028 as regards AI systems classified as "
        "high-risk pursuant to Article 6(1) and Annex I;\n(d) Articles 102 to 110 shall apply from "
        "27 July 2026."
    ),
    "IT": ART113_OLD["IT"].split("\nc)")[0]
    + (
        "\nc) Il capo III, sezioni 1, 2 e 3, ad eccezione dell'articolo 6, paragrafo 5, si applica "
        "a decorrere dal:\ni) 2 dicembre 2027 per quanto riguarda i sistemi di IA classificati come "
        "ad alto rischio ai sensi dell'articolo 6, paragrafo 2, e dell'allegato III; e\nii) 2 agosto "
        "2028 per quanto riguarda i sistemi di IA classificati come ad alto rischio ai sensi "
        "dell'articolo 6, paragrafo 1, e dell'allegato I;\nd) Gli articoli da 102 a 110 si applicano "
        "a decorrere dal 27 luglio 2026."
    ),
}
ART50 = {
    "EN": (
        "Article 50\nTransparency obligations\n1. Providers shall ensure that AI systems intended "
        "to interact directly with natural persons are designed so that the persons are informed."
    ),
    "IT": (
        "Articolo 50\nObblighi di trasparenza\n1. I fornitori garantiscono che i sistemi di IA "
        "destinati a interagire con le persone fisiche le informino."
    ),
}
ANNEX_I = {"EN": "ANNEX I\nList of Union harmonisation legislation", "IT": "ALLEGATO I\nElenco"}
ANNEX_III = {"EN": "ANNEX III\nHigh-risk AI systems", "IT": "ALLEGATO III\nSistemi ad alto rischio"}
# How the chunker labels the inserted article in each language.
ART4A_LABEL = {"EN": "Art. 4a", "IT": "Art. 4 bis"}


def _article(label: str, text: str) -> ArticleText:
    key = parse_article(label)
    assert key is not None
    return ArticleText(key, label, text, tuple(re.findall(r"(?m)^(\d{1,3})\.\s", text)))


def _texts(lang: str, *, new: bool) -> list[ArticleText]:
    articles = [
        _article("Art. 4", (ART4_NEW if new else ART4_OLD)[lang]),
        _article("Art. 10", (ART10_NEW if new else ART10_OLD)[lang]),
        _article("Art. 50", ART50[lang]),
        _article("Art. 113", (ART113_NEW if new else ART113_OLD)[lang]),
        _article("Annex I", ANNEX_I[lang]),
        _article("Annex III", ANNEX_III[lang]),
    ]
    if new:
        articles.append(_article(ART4A_LABEL[lang], ART4A[lang]))
    return articles


class OmnibusSource:
    """CELLAR stand-in: the AI Act as adopted and on 27/07/2026, in English and in Italian."""

    def __init__(self) -> None:
        self._versions = {AI_ACT: [Version(AI_ACT, None), Version(CONSOLIDATED, "2026-07-27")]}
        self._articles = {
            (celex, lang): _texts(lang, new=celex == CONSOLIDATED)
            for celex in (AI_ACT, CONSOLIDATED)
            for lang in ("EN", "IT")
        }
        self.asked: list[tuple[str, str]] = []
        self.unreadable: set[str] = set()
        self.unreachable = False

    def versions(self, celex: str) -> list[Version]:
        if self.unreachable or celex not in self._versions:
            raise TextUnavailableError(f"elenco delle versioni di {celex} non disponibile")
        return self._versions[celex]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        self.asked.append((version.celex, lang))
        if version.celex in self.unreadable:
            raise TextUnavailableError(f"CELLAR non ha il testo di {version.celex} in {lang}")
        return self._articles[(version.celex, lang)]


def _statements(check):
    return [f for f in check.findings if f.rule]


def _flat(text: str) -> str:
    return " ".join(text.split())


RULE = {rule.id: rule for rule in RULES}
# The provision as it was the day before the change, for the rules whose rule stayed in it.
BEFORE = {"R1": ART113_OLD, "R2": ART113_OLD, "R3": ART4_OLD}
# Rule, language of the sentence, the sentence, the words that state the old rule.
POSITIVE = [
    (
        "R1",
        "EN",
        "The obligations for Annex III systems apply from 2 August 2026 (Article 113 of the AI Act).",
        "2 August 2026",
    ),
    (
        "R1",
        "IT",
        "Gli obblighi per i sistemi ad alto rischio dell'allegato III si applicano dal 2 agosto 2026 "
        "(art. 113 dell'AI Act).",
        "2 agosto 2026",
    ),
    (
        "R2",
        "EN",
        "High-risk AI systems that are safety components of products covered by Annex I must "
        "comply from 2 August 2027.",
        "2 August 2027",
    ),
    (
        "R2",
        "IT",
        "Per i sistemi ad alto rischio che sono componenti di sicurezza di prodotti dell'allegato I "
        "gli obblighi si applicano dal 2 agosto 2027.",
        "2 agosto 2027",
    ),
    (
        "R3",
        "EN",
        "Providers and deployers shall ensure, to their best extent, a sufficient level of AI "
        "literacy (Article 4 of the AI Act).",
        "ensure, to their best extent, a sufficient level of AI literacy",
    ),
    (
        "R3",
        "IT",
        "In base all'art. 4 dell'AI Act fornitori e deployer devono garantire nella misura del "
        "possibile un livello sufficiente di alfabetizzazione in materia di IA.",
        "garantire nella misura del possibile un livello sufficiente di alfabetizzazione",
    ),
    (
        "R4",
        "EN",
        "Providers may process special categories of data under Article 10(5) of the AI Act.",
        "Article 10(5)",
    ),
    (
        "R4",
        "IT",
        "L'art. 10, par. 5, dell'AI Act consente ai fornitori di trattare categorie particolari di "
        "dati personali per correggere le distorsioni.",
        "art. 10, par. 5",
    ),
]
NEGATIVE = [
    "Article 50 applies from 2 August 2026.",
    "The AI Act applies from 2 August 2026.",
    "GPAI models placed before 2 August 2025 must comply by 2 August 2027.",
    "Annex III obligations apply from 2 December 2027.",
    "L'articolo 50 si applica dal 2 agosto 2026.",
    "L'AI Act si applica dal 2 agosto 2026.",
    "I modelli GPAI immessi sul mercato prima del 2 agosto 2025 devono conformarsi entro il 2 "
    "agosto 2027.",
    "Gli obblighi dell'allegato III si applicano dal 2 dicembre 2027.",
]
# Correct sentences that use the words of an old rule.
ALSO_NEGATIVE = [
    # A real answer of an AI assistant (17/11/2026): the history of Article 4, not its rule today.
    "Original Article 4 (applied from 2 February 2025). Providers and deployers had to ensure a "
    "sufficient level of AI literacy among their staff and others operating AI systems on their "
    "behalf.",
    "Before the amendment, Article 4 of the AI Act required providers to ensure a sufficient level "
    "of AI literacy.",
    "Under the old text, the obligations for Annex III systems applied from 2 August 2026.",
    "Nel testo originario dell'AI Act gli obblighi per i sistemi dell'allegato III dovevano "
    "applicarsi dal 2 agosto 2026.",
    "Secondo la formulazione previgente dell'art. 4, fornitori e deployer garantivano un livello "
    "sufficiente di alfabetizzazione in materia di IA.",
    "Annex III obligations, originally due from 2 August 2026, now apply from 2 December 2027.",
    "Gli obblighi per i sistemi ad alto rischio, inizialmente previsti dal 2 agosto 2026, sono "
    "stati rinviati.",
    "After the Digital Omnibus, high-risk obligations no longer apply from 2 August 2026.",
    "Providers are no longer required to ensure a sufficient level of AI literacy.",
    "Providers of high-risk systems used by public authorities placed on the market before "
    "2 August 2026 have until 2 August 2030.",
    "By 2 August 2027 the Commission adopts delegated acts on Annex I high-risk systems.",
    "Article 10(5) of the GDPR is not about special categories of data.",
    "Article 4a of the AI Act replaces Article 10(5) on special categories of personal data.",
    # A company's aim, not a statement of the law.
    "We aim to build a sufficient level of AI literacy across all teams.",
    "Puntiamo a un livello sufficiente di alfabetizzazione in materia di IA in tutti i team.",
    # The old wording in a quote is the verifier's job ("Citazione superata").
    "Deployers «take measures to ensure, to their best extent, a sufficient level of AI literacy "
    "of their staff» (Article 4 of the AI Act).",
]
EXAMPLE = (
    "Providers may process special categories of data under Article 10(5) of the AI Act. "
    "Providers and deployers shall ensure, to their best extent, a sufficient level of AI literacy "
    "(Article 4 of the AI Act). The obligations for Annex III systems apply from 2 August 2026 "
    "(Article 113 of the AI Act). Article 50 applies from 2 August 2026."
)


# ─── Sentences and words ─────────────────────────────────────────────


class TestSentences:
    def _sentences(self, text):
        return [text[start:end] for start, end in sentence_spans(text)]

    def test_abbreviations_do_not_end_a_sentence(self):
        text = (
            "Ai sensi dell'art. 4, par. 1, del d.lgs. n. 196/2003 si applica. "
            "Vedi e.g. l'Allegato III. Poi un'altra."
        )
        assert self._sentences(text) == [
            "Ai sensi dell'art. 4, par. 1, del d.lgs. n. 196/2003 si applica.",
            "Vedi e.g. l'Allegato III.",
            "Poi un'altra.",
        ]

    def test_lines_and_semicolons_end_a_sentence(self):
        assert self._sentences("Primo; secondo.\n\n- terzo: 2 agosto 2026") == [
            "Primo;",
            "secondo.",
            "- terzo: 2 agosto 2026",
        ]

    @pytest.mark.parametrize(
        "written",
        [
            "2 August 2026",
            "2nd of August 2026",
            "2 Aug. 2026",
            "August 2, 2026",
            "2026-08-02",
            "from August 2026",
            "2 agosto 2026",
            "02/08/2026",
            "2.8.2026",
            "dall'agosto 2026",
            "entro agosto 2026",
        ],
    )
    def test_how_documents_write_a_day(self, written):
        assert day_words(2, 8, 2026).search(f"Obblighi ad alto rischio: {written}.")

    @pytest.mark.parametrize(
        "other",
        ["12 August 2026", "2 August 2025", "22 agosto 2026", "2/8/20261", "in August 2026"],
    )
    def test_other_days_are_not_the_day(self, other):
        assert day_words(2, 8, 2026).search(f"High-risk obligations: {other}.") is None


# ─── Finding statements (no source) ──────────────────────────────────


class TestFindStatements:
    @pytest.mark.parametrize(("rule", "lang", "text", "words"), POSITIVE)
    def test_each_rule_fires_in_english_and_italian(self, rule, lang, text, words):
        [statement] = find_statements(text)
        assert statement.rule.id == rule
        assert statement.words == words
        assert statement.context == text
        assert statement.line == 1

    @pytest.mark.parametrize("text", NEGATIVE + ALSO_NEGATIVE)
    def test_correct_statements_do_not_fire(self, text):
        assert find_statements(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "Under the AI Act, staff must have a sufficient level of AI literacy.",
            "L'obbligo richiede un livello adeguato di alfabetizzazione in materia di IA.",
            "Deployers must guarantee an adequate level of AI literacy among their staff.",
        ],
    )
    def test_the_old_ai_literacy_rule_said_otherwise(self, text):
        assert [s.rule.id for s in find_statements(text)] == ["R3"]

    def test_only_the_sentence_counts(self):
        text = (
            "Article 50 applies from 2 August 2026; high-risk obligations under Annex III apply "
            "from 2 August 2026.\nAnnex I obligations apply from 2 August 2027."
        )
        found = find_statements(text)
        assert [(s.rule.id, s.line) for s in found] == [("R1", 1), ("R2", 2)]
        assert found[0].context == "high-risk obligations under Annex III apply from 2 August 2026."

    def test_the_rules(self):
        assert [rule.id for rule in RULES] == ["R1", "R2", "R3", "R4"]
        assert {(rule.act, rule.since, rule.by) for rule in RULES} == {
            (AI_ACT, "2026-07-27", "Regolamento (UE) 2026/1744")
        }
        assert [rule.part.label for rule in RULES] == [
            "art. 113, terzo comma, lettera c), punto i)",
            "art. 113, terzo comma, lettera c), punto ii)",
            "art. 4, par. 1",
            "art. 4 bis",
        ]

    @pytest.mark.parametrize("lang", ["EN", "IT"])
    def test_only_the_text_in_force_confirms_a_rule(self, lang):
        for rule in RULES:
            new = find_article(_texts(lang, new=True), rule.provision)
            old = find_article(_texts(lang, new=False), rule.provision)
            assert new is not None and official_passage(rule, new.text), rule.id
            assert old is None or official_passage(rule, old.text) is None, rule.id


# ─── Checking statements against the official text ───────────────────


class TestCheckStatements:
    @pytest.mark.parametrize(("rule", "lang", "text", "words"), POSITIVE)
    def test_the_finding_shows_the_text_in_force_read_on_the_source(self, rule, lang, text, words):
        source = OmnibusSource()
        [f] = _statements(check_text(text, source, lang=lang))
        assert f.rule == rule
        assert f.status is STALE and f.status.group == "correggere"
        assert f.reference.raw == words and f.reference.context == text
        assert f.act is not None and f.act.key == AI_ACT and f.act_name == "AI Act"
        assert f.version is not None and f.version.celex == CONSOLIDATED
        assert (
            f.url == f"https://eur-lex.europa.eu/legal-content/{lang}/TXT/?uri=CELEX:{CONSOLIDATED}"
        )
        # The official text is the source's, read at run time.
        assert (CONSOLIDATED, lang) in source.asked
        assert f.article is not None and f.official_quote
        assert f.official_quote in _flat(f.article.text)
        assert f.messages[0] == RULE[rule].message
        assert (
            f.messages[1]
            == "La regola è cambiata il 27/07/2026, con il Regolamento (UE) 2026/1744."
        )
        if rule == "R4":
            assert f.before is None  # the old rule was in another article: nothing to compare
        else:
            assert f.before_version is not None and f.before_version.celex == AI_ACT
            assert f.before == BEFORE[rule][lang]

    def test_the_example_of_the_request(self):
        check = check_text(EXAMPLE, OmnibusSource(), document="esempio.txt")
        assert [(f.rule, f.status) for f in _statements(check)] == [
            ("R4", STALE),
            ("R3", STALE),
            ("R1", STALE),
        ]
        references = [f for f in check.findings if not f.rule]
        assert [(f.reference.raw, f.status) for f in references] == [
            ("Article 10(5) of the AI Act", MISSING),
            ("Article 4 of the AI Act", VALID),
            ("Annex III systems apply from 2 August 2026 (Article 113 of the AI Act", VALID),
            ("Article 113 of the AI Act", VALID),
            ("Article 50", VALID),
        ]
        assert len(check.group("correggere")) == 4

    def test_a_document_written_before_the_change(self):
        text = POSITIVE[0][2]
        [f] = _statements(check_text(text, OmnibusSource(), document_date="2026-03-15"))
        assert f.status is CHANGED and f.status.group == "correggere"
        assert f.messages[1] == (
            "Alla data del documento (15/03/2026) la regola era questa: è cambiata il 27/07/2026, "
            "con il Regolamento (UE) 2026/1744."
        )
        assert f.before == ART113_OLD["EN"]

    def test_a_document_written_after_the_change(self):
        text = POSITIVE[1][2]
        [f] = _statements(check_text(text, OmnibusSource(), document_date="2026-09-01"))
        assert f.status is STALE
        assert "Alla data del documento (01/09/2026) la regola era già cambiata" in f.messages[1]

    def test_a_text_in_force_that_says_otherwise_is_to_be_checked(self):
        source = OmnibusSource()
        changed_again = ART113_NEW["EN"].replace("2 December 2027", "2 March 2028")
        source._articles[(CONSOLIDATED, "EN")] = [
            a if a.key != "art:113" else _article("Art. 113", changed_again)
            for a in source._articles[(CONSOLIDATED, "EN")]
        ]
        [f] = _statements(check_text(POSITIVE[0][2], source))
        assert f.status is STALE_UNCONFIRMED and f.status.group == "controllare"
        assert f.official_quote is None and f.article is None
        assert "nel testo consolidato al 27/07/2026 l'art. 113 non lo dice" in f.messages[1]

    def test_a_text_older_than_the_change_does_not_confirm_it(self):
        source = OmnibusSource()
        source._versions[AI_ACT] = [Version(AI_ACT, None)]
        [f] = _statements(check_text(POSITIVE[4][2], source))
        assert f.status is STALE_UNCONFIRMED
        assert "nel testo originale l'art. 4 non lo dice" in f.messages[1]

    def test_unreachable_source(self):
        source = OmnibusSource()
        source.unreachable = True
        [f] = _statements(check_text(POSITIVE[6][2], source))
        assert f.status is UNAVAILABLE and f.official_quote is None
        assert f.messages[0] == RULE["R4"].message
        assert "non ha potuto confermarlo" in f.messages[1]

    def test_a_newer_version_that_cannot_be_read_is_declared(self):
        source = OmnibusSource()
        source._versions[AI_ACT].append(Version("02024R1689-20261015", "2026-10-15"))
        source.unreadable = {"02024R1689-20261015"}
        [f] = _statements(check_text(POSITIVE[0][2], source, today="2026-11-24"))
        assert f.status is STALE
        assert any("va ripetuto su EUR-Lex" in m for m in f.messages)

    def test_a_version_dated_after_the_check_is_not_the_text_in_force(self):
        # CELLAR lists consolidated texts ahead of their date: such a text is not
        # read for a statement either, as for the references (_applicable).
        source = OmnibusSource()
        source._versions[AI_ACT].append(Version("02024R1689-20270115", "2027-01-15"))
        [f] = _statements(check_text(POSITIVE[0][2], source, today="2026-11-24"))
        assert f.status is STALE
        assert f.version is not None and f.version.celex == CONSOLIDATED
        assert ("02024R1689-20270115", "EN") not in source.asked
        assert ("02024R1689-20270115", "IT") not in source.asked

    def test_the_text_in_force_is_read_once_and_only_when_a_rule_fires(self):
        source = OmnibusSource()
        text = (
            "High-risk obligations under Annex III apply from 2 August 2026. Annex I obligations "
            "apply from 2 August 2027."
        )
        assert [f.rule for f in _statements(check_text(text, source, lang="EN"))] == ["R1", "R2"]
        assert source.asked.count((CONSOLIDATED, "EN")) == 1
        quiet = OmnibusSource()
        check_text("The AI Act applies from 2 August 2026.", quiet)
        assert quiet.asked == []

    def test_quoted_old_wording_stays_a_quote(self):
        check = check_text(DOCUMENT, FakeSource(), document="doc.txt", today="2026-10-28")
        assert _statements(check) == []


# ─── Report, terminal, lock file and API ─────────────────────────────


class TestReport:
    def test_the_card_shows_the_sentence_the_message_and_the_text_in_force(self):
        check = check_text(EXAMPLE, OmnibusSource(), document="esempio.txt")
        html = render_html(check, "esempio.norma-lock.json")
        assert "Affermazione superata" in html
        assert "apply from <mark>2 August 2026</mark> (Article 113 of the AI Act)." in html
        assert escape(RULE["R1"].message) in html
        assert escape("Testo vigente dell'art. 113 (testo consolidato al 27/07/2026)") in html
        assert escape("(i) 2 December 2027 as regards AI systems classified as high-risk") in html
        link = f'href="https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{CONSOLIDATED}"'
        assert link in html
        assert "<del>" in html and "<ins>" in html  # art. 113 before and after the change

    def test_the_terminal_summary_counts_statements_apart(self):
        check = check_text(EXAMPLE, OmnibusSource(), document="esempio.txt", today="2026-11-17")
        lines = summary_lines(check)
        assert lines[0] == (
            "Controllo di esempio.txt (17/11/2026): 5 disposizioni citate, 3 affermazioni su "
            "norme cambiate."
        )
        assert lines[1] == "4 da correggere, 0 da controllare, 4 a posto, 0 fuori copertura."
        assert (
            "- riga 1, AI Act, art. 113, terzo comma, lettera c), punto i): Affermazione superata "
            "(«2 August 2026»)"
        ) in lines

    def test_the_lock_file_and_the_api_keep_the_statement(self):
        check = check_text(EXAMPLE, OmnibusSource(), document="esempio.txt")
        lock = build_lock(check)
        art113 = next(d for d in lock["dipendenze"] if d["chiave"] == "art:113")
        assert art113["riferimenti"] == ["2 August 2026", "Article 113 of the AI Act"]
        findings = serialize.findings_to_json(check, lock)
        stored = next(f for f in findings if f["rule"] == "R1")
        assert stored["status"] == {
            "code": "affermazione_superata",
            "label": "Affermazione superata",
        }
        assert stored["official_quote"].startswith("(c) Chapter III, Sections 1, 2, and 3")
        assert stored["dependency"] == {"source": "eurlex", "act": AI_ACT, "key": "art:113"}
        assert all(f["rule"] is None for f in findings if f["status"]["code"] == "valido")
        rebuilt = serialize.check_from_json(
            findings,
            document="esempio.txt",
            checked_on=check.checked_on,
            document_date=None,
            lang="EN",
        )
        html = render_html(rebuilt)
        assert escape("Testo vigente dell'art. 113 (testo consolidato al 27/07/2026)") in html

    def test_command_line(self, tmp_path, capsys):
        script = Path(__file__).resolve().parent.parent / "scripts" / "check_document.py"
        spec = importlib.util.spec_from_file_location("check_document", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        document = tmp_path / "policy.txt"
        document.write_text(EXAMPLE, encoding="utf-8")
        cache = str(tmp_path / "cache")
        with patch.object(module, "default_source", return_value=OmnibusSource()):
            assert module.main([str(document), "--data", "2026-03-15", "--cache", cache]) == 0
        out = capsys.readouterr().out
        assert "3 affermazioni su norme cambiate" in out
        assert "Cambiato dopo la data del documento («2 August 2026»)" in out
        assert (tmp_path / "policy.controllo.html").exists()
