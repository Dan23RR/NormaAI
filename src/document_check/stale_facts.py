"""Statements about the law that an amendment made untrue: stale facts.

A document can state a rule in its own words instead of quoting it: "the
obligations for Annex III systems apply from 2 August 2026 (Article 113)". The
reference is valid and there is no quote to verify, yet the date is one that
the Digital Omnibus on AI (Regulation (EU) 2026/1744, in force since 27 July
2026) changed. Each rule below describes one such statement: the words that
state the old rule, what else the sentence must and must not say, the
provision that states the rule now and the words of its official text that
confirm the change.

Pure functions, no network, like ``extract``. A rule fires on a sentence when:

1. a ``claim`` pattern matches outside quotation marks (a quote is the
   verifier's job: an old wording quoted is a "Citazione superata");
2. every ``topic`` pattern matches (what the sentence is about; for the AI
   literacy rule, also that it is the law's rule and not a company's aim);
3. no ``unless`` pattern matches: the correct statements that use the same
   words ("Article 50 applies from 2 August 2026");
4. the sentence neither states the rule in force (``current``) nor says that
   the rule changed or no longer holds (``CHANGE_WORDS``: "originally",
   "postponed", "no longer", "Omnibus", "inizialmente", "rinviato", "non più");
5. no reference in the sentence belongs to another act, unless one belongs to
   the rule's act ("Article 10(5) GDPR" is not the AI Act).

``check`` then reads the provision in force on the official source, shows the
``passage`` that states the rule now and asserts the rule's message only when
that passage says what ``in_force`` expects. A sentence is split at a line
break, a semicolon, or a full stop before the next word, never after an
abbreviation ("art.", "par.", "n.", "d.lgs.").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from typing import NamedTuple

from src.document_check.extract import Provision, Reference, extract_references, quote_spans

AI_ACT = "32024R1689"
DIGITAL_OMNIBUS = "Regolamento (UE) 2026/1744"


class Words(NamedTuple):
    """A pattern in English and one in Italian; either may be empty. Case is ignored."""

    en: str = ""
    it: str = ""

    def search(self, text: str) -> re.Match[str] | None:
        pattern = _compiled(self)
        return pattern.search(text) if pattern is not None else None


@cache
def _compiled(words: Words) -> re.Pattern[str] | None:
    parts = [p for p in words if p]
    if not parts:
        return None
    return re.compile("|".join(f"(?:{p})" for p in parts), re.IGNORECASE)


def _either(*words: Words) -> Words:
    """One Words that matches where any of ``words`` matches."""
    return Words(
        "|".join(f"(?:{w.en})" for w in words if w.en),
        "|".join(f"(?:{w.it})" for w in words if w.it),
    )


# ─── Dates as documents write them ───────────────────────────────────

_MONTHS_EN = (
    "January February March April May June July August September October November December"
).split()
_MONTHS_IT = (
    "gennaio febbraio marzo aprile maggio giugno luglio agosto settembre ottobre novembre dicembre"
).split()


def day_words(number: int, month: int, year: int) -> Words:
    """A day as a document writes it.

    English: "2 August 2026", "2nd of August 2026", "2 Aug. 2026", "August 2,
    2026", "2026-08-02", "from August 2026". Italian: "2 agosto 2026",
    "02/08/2026", "2.8.2026", "dall'agosto 2026", "entro agosto 2026".
    """
    en, it = _MONTHS_EN[month - 1], _MONTHS_IT[month - 1]
    names = rf"(?:{en}|{en[:3]}\.?)"
    ordinal = rf"0?{number}(?:st|nd|rd|th)?"
    return Words(
        en=(
            rf"\b{ordinal}\s+(?:of\s+)?{names}\s+{year}\b|\b{names}\s+{ordinal},?\s+{year}\b"
            rf"|\b(?:from|as\s+of|by|starting(?:\s+(?:in|from))?|beginning(?:\s+in)?)\s+{en}"
            rf"\s+{year}\b|\b{year}-{month:02d}-{number:02d}\b"
        ),
        it=(
            rf"\b0?{number}[°º]?\s+{it}\s+{year}\b|\b0?{number}[./]0?{month}[./]{year}\b"
            rf"|\b(?:a\s+(?:partire|decorrere)\s+)?(?:dall['’]\s?|da\s+|entro\s+)"
            rf"(?:il\s+mese\s+di\s+)?{it}\s+{year}\b"
        ),
    )


# ─── Rules ───────────────────────────────────────────────────────────

# The sentence says the rule changed, or denies the old one: it is not stating it.
CHANGE_WORDS = Words(
    en=(
        r"\bno\s+longer\b|\bnot\s+any\s+longer\b|\boriginally\b|\binitially\b|\bpreviously\b"
        r"|\bformerly\b|\bpostpon(?:ed|ement)\b|\bdelayed\b|\bdeferred\b|\bpushed\s+back\b"
        r"|\bmoved\b|\brepealed\b|\b(?:was|were)\s+(?:originally\s+)?(?:due|set|scheduled"
        r"|expected|planned)\b|\bnot\s+(?:required|obliged)\b|\bOmnibus\b|\b2026/1744\b"
    ),
    it=(
        r"\bnon\s+(?:è\s+|sono\s+)?più\b(?!\s+tardi)|\binizialmente\b|\boriginariamente\b"
        r"|\bin\s+origine\b|\bin\s+precedenza\b|\bprecedentemente\b|\brinviat[oaie]\b"
        r"|\bposticipat[oaie]\b|\bdifferit[oaie]\b|\bslittat[oaie]\b|\bspostat[oaie]\b"
        r"|\bprorogat[oaie]\b|\bsoppress[oaie]\b|\babrogat[oaie]\b|\bera(?:no)?\s+previst[oaie]\b"
        r"|\bnon\s+(?:è|sono)\s+(?:richiest|tenut|obbligat)[oaie]\b"
        r"|\bnon\s+(?:impone|richiede|obbliga)\b"
    ),
)

# Correct statements that name a date of the AI Act next to high-risk systems:
# Article 50 and the general-purpose AI models keep their dates; the transitional
# periods of Article 111 (2030), the sandboxes and the exceptions are other rules.
_OTHER_DATES = Words(
    en=(
        r"\bArt(?:icles?|s?\.)?\s*50\b|\btransparen(?:cy|t)\b|\bgeneral[\s-]purpose\b|\bGPAI\b"
        r"|\bsandbox(?:es)?\b|\b2030\b|\bexcept\b|\bexcluding\b|\bother\s+than\b"
        r"|\bapart\s+from\b|\bwith\s+the\s+exception\b|\bbut\s+not\b"
    ),
    it=(
        r"\bart(?:t?\.|icol[oi])?\s*50\b|\btrasparenz[ae]\b|\buso\s+generale\b"
        r"|\bfinalit[àa]\s+generali\b|\bspazi?\s+di\s+sperimentazione\b|\bad\s+eccezione\b"
        r"|\beccetto\b|\btranne\b|\bsalvo\b|\bma\s+non\b|\besclus[oiae]\b"
    ),
)
_HIGH_RISK_DATES_NOW = _either(day_words(2, 12, 2027), day_words(2, 8, 2028))
# Point (c) of the third paragraph of Article 113, with its points (i) and (ii).
_ART113_POINT_C = r"(?m)^[ \t]*\(?c\)[^\n]*(?:\n[ \t]*\(?(?:i{1,3}|iv|v)\)[^\n]*)*"
_ANNEX_III_NOW = r"\b2\s+(?:December|dicembre)\s+2027\b[^;]*\b(?:Annex|allegato)\s+III\b"
_ANNEX_I_NOW = r"\b2\s+(?:August|agosto)\s+2028\b[^;]*\b(?:Annex|allegato)\s+I\b(?![IVX])"
_PARAGRAPH_1 = r"(?m)^[ \t]*1\.[ \t][^\n]*"


@dataclass(frozen=True)
class Part(Provision):
    """A provision named down to the part a rule is about."""

    name: str = ""

    @property
    def label(self) -> str:
        return self.name or super().label


@dataclass(frozen=True)
class Rule:
    """A rule of law as it was before an amendment, and how a document states it."""

    id: str
    act: str  # CELEX of the act whose rule changed
    provision: str  # parse_article key of the provision that states the rule now
    claim: Words  # the old rule, as a document writes it (matched outside quotes)
    topic: tuple[Words, ...]  # what else the sentence must say: every one of them
    unless: Words  # correct statements that use the same words
    current: Words  # the rule in force, as a document writes it
    passage: str  # where the official text states the rule now (English and Italian)
    in_force: tuple[str, ...]  # what that passage must say for ``message`` to hold
    message: str  # what is no longer true and what is, in Italian
    name: str = ""  # the provision as the report names it, when more than an article
    paragraphs: tuple[str, ...] = ()
    was_in: str = ""  # the provision that stated the old rule, when it is another one
    since: str = "2026-07-27"  # the first day the old rule was no longer the law
    by: str = DIGITAL_OMNIBUS  # the act that changed it

    @property
    def part(self) -> Provision:
        """The provision that states the rule now, named as the report names it."""
        return Part(self.provision, self.paragraphs, name=self.name)

    def applies(self, sentence: str) -> bool:
        """Conditions 2 to 4: the topic is there, nothing says the statement is right."""
        if any(words.search(sentence) is None for words in self.topic):
            return False
        return not any(
            words.search(sentence) for words in (self.unless, self.current, CHANGE_WORDS)
        )


RULES: tuple[Rule, ...] = (
    Rule(
        id="R1",
        act=AI_ACT,
        provision="art:113",
        name="art. 113, terzo comma, lettera c), punto i)",
        claim=day_words(2, 8, 2026),
        topic=(
            Words(
                en=r"\bhigh[\s-]risk\b|\bAnnex\s+III\b|\bArt(?:icle|\.)?\s*6\s*\(\s*2\s*\)",
                it=(
                    r"\balto\s+rischio\b|\ballegato\s+III\b"
                    r"|\bart(?:icolo|\.)?\s*6,?\s*(?:paragrafo|par\.)\s*2\b"
                ),
            ),
        ),
        unless=_OTHER_DATES,
        current=_HIGH_RISK_DATES_NOW,
        passage=_ART113_POINT_C,
        in_force=(_ANNEX_III_NOW, _ANNEX_I_NOW),
        message=(
            "Gli obblighi per i sistemi di IA ad alto rischio non si applicano più dal 2 agosto "
            "2026: si applicano dal 2 dicembre 2027 ai sistemi dell'allegato III e dal 2 agosto "
            "2028 a quelli dell'allegato I."
        ),
    ),
    Rule(
        id="R2",
        act=AI_ACT,
        provision="art:113",
        name="art. 113, terzo comma, lettera c), punto ii)",
        claim=day_words(2, 8, 2027),
        topic=(
            Words(
                en=(
                    r"\bAnnex\s+I\b(?![IVX])|\bsafety\s+components?\b"
                    r"|\bArt(?:icle|\.)?\s*6\s*\(\s*1\s*\)|\bUnion\s+harmoni[sz]ation\s+legislation\b"
                ),
                it=(
                    r"\ballegato\s+I\b(?![IVX])|\bcomponent[ei]\s+di\s+sicurezza\b"
                    r"|\bart(?:icolo|\.)?\s*6,?\s*(?:paragrafo|par\.)\s*1\b"
                    r"|\bnormativa\s+(?:dell['’]\s?Unione\s+)?di\s+armonizzazione\b"
                ),
            ),
        ),
        # The delegated acts of Article 2 on Annex I systems are due by 2 August 2027.
        unless=_either(
            _OTHER_DATES, Words(en=r"\bdelegated\s+acts?\b", it=r"\batt[oi]\s+delegat[oi]\b")
        ),
        current=_HIGH_RISK_DATES_NOW,
        passage=_ART113_POINT_C,
        in_force=(_ANNEX_I_NOW,),
        message=(
            "Gli obblighi per i sistemi di IA ad alto rischio dell'allegato I (componenti di "
            "sicurezza di prodotti) non si applicano più dal 2 agosto 2027: si applicano dal 2 "
            "agosto 2028."
        ),
    ),
    Rule(
        id="R3",
        act=AI_ACT,
        provision="art:4",
        paragraphs=("1",),
        claim=Words(
            en=(
                r"(?:\b(?:ensure|guarantee)s?\b[\s,]+)?(?:\bto\s+(?:the|their|its)\s+best\s+extent"
                r"(?:\s+possible)?[\s,]+)?(?:\b(?:an?|the)\s+)?\b(?:sufficient|adequate)\s+"
                r"(?:level|degree)\s+of\s+AI[\s-]literacy\b"
                r"|\bsufficient(?:ly)?\s+AI[\s-]litera(?:cy|te)\b"
                r"|\bto\s+(?:the|their|its)\s+best\s+extent\b"
            ),
            it=(
                r"(?:\bgarantir(?:e|ne)\b[\s,]+)?(?:\bnella\s+misura\s+del\s+possibile[\s,]+)?"
                r"(?:\bun\s+)?\blivello\s+(?:sufficiente|adeguato)\s+di\s+alfabetizzazione\b"
                r"|\b(?:sufficiente|adeguata)\s+alfabetizzazione\b"
                r"|\bnella\s+misura\s+del\s+possibile\b"
            ),
        ),
        topic=(
            Words(en=r"\bAI[\s-]litera(?:cy|te)\b", it=r"\balfabetizzazione\b"),
            # The law's rule, not a company's aim ("we aim at a sufficient level of AI literacy").
            Words(
                en=(
                    r"\bArt(?:icle|\.)?\s*4\b|\bAI\s?Act\b|\bRegulation\b|\bproviders?\b"
                    r"|\bdeployers?\b|\bobligations?\b|\bobliged\b"
                ),
                it=(
                    r"\bart(?:icolo|\.)?\s*4\b|\bregolamento\b|\bfornitor[ei]\b|\bdeployer\b"
                    r"|\bobblig\w*"
                ),
            ),
        ),
        unless=Words(),
        current=Words(
            en=r"\bsupport\w*\s+(?:the\s+)?development\s+of\s+AI[\s-]literacy\b|\bspecific\s+level\b",
            it=(
                r"\bsostener\w*\s+lo\s+sviluppo\s+dell['’]\s?alfabetizzazione\b"
                r"|\blivello\s+specifico\b"
            ),
        ),
        passage=_PARAGRAPH_1,
        in_force=(
            r"\bsupport\s+the\s+development\s+of\s+AI\s+literacy\b"
            r"|\bsostenere\s+lo\s+sviluppo\s+dell['’]\s?alfabetizzazione\b",
            r"\bnot\s+require\b.*\bspecific\s+level\b|\bnon\s+impone\b.*\blivello\s+specifico\b",
        ),
        message=(
            "L'art. 4 non chiede più di garantire un livello sufficiente di alfabetizzazione in "
            "materia di IA: fornitori e deployer adottano misure per sostenerne lo sviluppo, e "
            "l'obbligo non impone di garantire un livello specifico."
        ),
    ),
    Rule(
        id="R4",
        act=AI_ACT,
        provision="art:4bis",
        claim=Words(
            en=(
                r"\bArt(?:icle|\.)?\s*10\s*\(\s*5\s*\)|\bArticle\s+10,?\s+(?:paragraph|para\.?)\s*5\b"
                r"|\b(?:paragraph|para\.?)\s*5\s+of\s+Article\s+10\b"
            ),
            it=(
                r"\bart(?:icolo|\.)?\s*10,?\s*(?:paragrafo|par\.|comma)\s*5\b"
                r"|\b(?:paragrafo|par\.)\s*5,?\s+dell['’]\s?art(?:icolo|\.)?\s*10\b"
            ),
        ),
        topic=(
            Words(
                en=r"\bspecial\s+categor(?:y|ies)\b|\bsensitive\s+(?:personal\s+)?data\b|\bbias(?:es)?\b",
                it=r"\bcategori[ae]\s+particolar[ie]\b|\bdati\s+sensibili\b|\bdistorsion[ei]\b",
            ),
        ),
        unless=Words(),
        current=Words(en=r"\bArt(?:icle|\.)?\s*4\s*a\b", it=r"\bart(?:icolo|\.)?\s*4[\s-]*bis\b"),
        passage=_PARAGRAPH_1,
        in_force=(
            r"\bspecial\s+categories\s+of\s+personal\s+data\b"
            r"|\bcategorie\s+particolari\s+di\s+dati\s+personali\b",
            r"\bbias\b|\bdistorsioni\b",
        ),
        message=(
            "Il trattamento di categorie particolari di dati personali per rilevare e correggere "
            "le distorsioni è ora nell'art. 4 bis, non più nell'art. 10, paragrafo 5."
        ),
        was_in="art:10",
    ),
)


# ─── Sentences ───────────────────────────────────────────────────────

# A sentence ends at a line break, at a semicolon, or at ".", "!", "?" followed by
# a space and the next word; not at the full stop of an abbreviation.
_BREAK = re.compile(r"\n|;(?=\s)|[.!?…]+(?=[\"'»”’)\]]*\s+[\"'«“‘(\[]*\w)")
_ABBREVIATION = re.compile(
    r"(?:^|[^\w.])(?:artt?|parr?|nn?|lett|co|cfr|es|ecc|reg|dir|nos?|paras?|pp|pagg?|sez|sec"
    r"|cap|vol|segg?|ss|cf|vs|etc|ca|approx|e\.g|i\.e|d\.lgs|d\.l|d\.p\.r|c\.c|c\.p|mr|mrs|ms"
    r"|dr|prof|st|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)$",
    re.IGNORECASE,
)
_INITIAL = re.compile(r"(?:^|[^\w.])[a-z]$")  # "l. 241/1990", "d. lgs.", "p. 4"


def _ends_with_abbreviation(text: str, period: int) -> bool:
    before = text[max(0, period - 16) : period]
    return bool(_ABBREVIATION.search(before) or _INITIAL.search(before))


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Start and end of each sentence of ``text``, surrounding spaces left out."""
    spans: list[tuple[int, int]] = []

    def add(start: int, end: int) -> None:
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            spans.append((start, end))

    start = 0
    for m in _BREAK.finditer(text):
        if m.group(0) == "." and _ends_with_abbreviation(text, m.start()):
            continue
        add(start, m.start() if m.group(0) == "\n" else m.end())
        start = m.end()
    add(start, len(text))
    return spans


# ─── Statements ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Statement:
    """A sentence of a document that states a rule as it was before an amendment."""

    rule: Rule
    start: int  # the words that state the old rule
    end: int
    words: str  # those words as written: "2 August 2026"
    line: int  # 1-based line of the document
    context: str  # the sentence (the part around ``words`` when it is very long)


_CONTEXT_WIDTH = 200


def _context(text: str, start: int, end: int, lo: int, hi: int) -> str:
    left, right = max(lo, start - _CONTEXT_WIDTH), min(hi, end + _CONTEXT_WIDTH)
    snippet = " ".join(text[left:right].split())
    return ("… " if left > lo else "") + snippet + (" …" if right < hi else "")


def _masked(text: str) -> str:
    """``text`` with the inside of its quotes blanked out, every position kept."""
    parts: list[str] = []
    last = 0
    for start, end in quote_spans(text):
        parts.extend((text[last:start], " " * (end - start)))
        last = end
    parts.append(text[last:])
    return "".join(parts)


def find_statements(text: str, references: list[Reference] | None = None) -> list[Statement]:
    """The sentences of ``text`` that state a rule of ``RULES`` as it was before it changed.

    ``references`` are those ``extract_references`` gives for ``text`` (found
    again when not given): a sentence whose references all belong to another
    act is not about the rule's act.
    """
    refs = extract_references(text) if references is None else references
    plain = _masked(text)
    found: list[Statement] = []
    for lo, hi in sentence_spans(text):
        sentence = text[lo:hi]
        acts = {
            r.act.key
            for r in refs
            if lo <= r.start < hi and r.act is not None and not r.act_inferred
        }
        for rule in RULES:
            m = rule.claim.search(plain[lo:hi])
            if m is None or not rule.applies(sentence) or (acts and rule.act not in acts):
                continue
            start, end = lo + m.start(), lo + m.end()
            found.append(
                Statement(
                    rule=rule,
                    start=start,
                    end=end,
                    words=" ".join(text[start:end].split()),
                    line=text.count("\n", 0, start) + 1,
                    context=_context(text, start, end, lo, hi),
                )
            )
    return found


def official_passage(rule: Rule, text: str) -> str | None:
    """The words of the provision in force that state the rule now, or None.

    None when the passage is not in ``text`` or does not say what ``in_force``
    expects: the text read is older than the change, or the provision changed
    again. The rule's message is shown only when this gives a passage.
    """
    m = re.search(rule.passage, text, re.IGNORECASE)
    if m is None:
        return None
    passage = " ".join(m.group(0).split())
    if not all(re.search(p, passage, re.IGNORECASE) for p in rule.in_force):
        return None
    return passage
