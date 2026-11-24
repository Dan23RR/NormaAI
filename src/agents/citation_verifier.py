"""Deterministic verification of quoted passages against the retrieved texts.

NormaAI promises that a citation shown as "Verificata" quotes a passage that
was actually found, word for word, in the official text the system retrieved.
This module is that check and nothing else: pure functions, no I/O, no LLM.

Given a citation produced by the model (``framework`` / ``reference`` /
``quote_snippet``) and the chunks retrieval returned, ``verify_citation`` says
whether the quote is in one of them and, when it is, where: the chunk id, the
base act (CELEX), article, paragraph, language, consolidation date, a
server-built EUR-Lex URL and ``official_quote``, the exact span of the chunk
text that matched, so the interface shows the official wording rather than
the model's. An article that an amending act quotes and that is cited as the
amended act's article (case B of src/agents/quoted_articles.py) also reports
that amending act and article (``amending_celex``, ``amending_article``): its
wording was found there, and ``url`` is its page.

The rule (ARCHITECTURE.md, "Verifica deterministica delle citazioni"):

1. Quote and chunk text are compared after ``normalize``: NFKC, casefold,
   typographic quotes and apostrophes to ASCII, every dash to ``-``, Unicode
   spaces to a space, soft hyphens and zero-width characters removed,
   whitespace collapsed (the quote also loses surrounding quotes, punctuation
   and ellipses).
2. A quote shorter than 20 characters or 4 words is never verified: it is too
   generic to prove anything.
3. Chunks are searched by level: the cited framework and article
   (``"article"``), then any chunk of the cited framework (``"framework"``),
   then every chunk (``"any"``). The first level where the quote is found is
   recorded in ``level``.
4. Within a level the quote must be found in one chunk, starting and ending
   on word boundaries (``"exact"``): "lecito" is not found inside "illecito",
   nor "72 ore" inside "172 ore". A quote with omissions (``[...]``, ``...``,
   ``…``) is split there into parts, and EVERY part must be found in the same
   chunk, in order, on word boundaries: "non" is not found inside "nonché".
   Each part must hold a word of its own (``_has_content``): a part made only
   of function words, numbers or a list marker ("non", "not", "shall not",
   "72") takes its meaning from the words the omission removed, so it cannot
   be checked. An omission may skip at most ``MAX_OMISSION_CHARS`` characters
   of the chunk, or ``MAX_SKIPPED_POINTS_CHARS`` when the part after it starts
   a point or a paragraph (it skips whole points of a list): words stitched
   together from distant sentences are not a quote. Failing an exact match, a
   tolerant comparison, under the same rules, accepts a span whose difflib
   ratio with a part is at least 0.92 (``"fuzzy"``) only when the WORDS agree
   (``wording_differences``): every number, every number word and every word
   under six letters must be identical. The differences forgiven are
   punctuation, accents, a word split or joined at a line break, and one
   missing or extra letter inside a word of at least six letters, neither its
   first nor its last ("notifca" for "notifica"). A different letter is never
   forgiven ("consent" is not "content"), nor a letter added or dropped at the
   end of a word ("trattamenti" is not "trattamento", "requirements" is not
   "requirement").
5. A span that is close but differs in a word that matters ("48 ore" where the
   law says "72 ore") is not a verification. The result stays unverified and
   says what was almost matched: ``near_quote`` (the official wording),
   ``near_article`` (where it is) and ``differences`` (the words that differ).
6. A chunk that carries an ``org_id`` is a document uploaded by a tenant, not
   an official text: it never verifies a quote.

A literal quote can still leave out context that changes its meaning (the
"non" just before it, an exception in the next sentence, a clause the omission
skips): the interface shows the official passage so the reader sees it in
place.

When the citation names a paragraph ("Art. 50(2)"), the article level looks
in that paragraph first; ``paragraph`` reports where the quote starts.
``verify_citation`` keeps reporting a quote found at the "framework" or "any"
level, or in another paragraph, as verified: the document check
(src/document_check) reads ``level`` and tells "Citazione in un altro
articolo" itself.

``annotate_citations`` (the Q&A path) writes the result on COPIES of the
citations and adds the ``verified_citations`` / ``citations_total`` counters.
There a quote found word for word but not where its citation points is NOT a
verified citation: in another act (level "any", or another act of the cited
framework), in another article of the act cited, when the citation names an
article, or in another known paragraph than the one it names. Such a citation
gets ``verified`` False with every field above empty, and says where the
wording really is in fields of its own (``ELSEWHERE_FIELDS``), written on
every citation:

- ``found_elsewhere``: True for such a citation, False otherwise;
- ``found_in``: ``"act"``, ``"article"`` or ``"paragraph"``;
- ``found_celex``, ``found_article``, ``found_paragraph``: where it is;
- ``found_quote``: the official wording there; ``found_url``: its EUR-Lex page.

``apply_unverified_policy`` gives each such citation a caveat that names it
and flags the answer for expert review, flags with a caveat an answer that
cites nothing at all, and decides what happens to an answer whose citations
were all left unverified (``flag`` or ``strict``, see ``src.config``).
"""

from __future__ import annotations

import bisect
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from src.crawler.eurlex import celex as celex_utils

# ─── Thresholds and vocabularies ─────────────────────────────────────

MIN_QUOTE_CHARS = 20
MIN_QUOTE_WORDS = 4
# A part of a quote shorter than this is matched only word for word, never
# fuzzily: there are too few letters to tell a slip from another word.
MIN_SEGMENT_CHARS = 12
FUZZY_MIN_RATIO = 0.92
# A missing or extra letter is forgiven only in words at least this long:
# shorter words ("non", "deve", "Stati", "shall", "notify") carry too much
# meaning per letter.
MIN_SLIP_WORD_CHARS = 6
# How much of the official text an omission may skip (see _place). Measured on
# the ten live golden v2 runs of 24/10-18/11/2026 (152 distinct quotes with an
# omission, each placed in the cached official text): inside running text the
# longest omission of a verified quote was 524 characters (NIS2, Art. 23(11)),
# the median about 95; an omission that skips to the next point of a list
# reached 980 (AI Act, Art. 14(4): "... di: [...] e) intervenire ..."). 600
# keeps the first kind and stops a part from being fetched from sentences
# further away. A skip that lands on the start of a point or a paragraph
# leaves out whole points: it may reach 2000 characters, the largest Q&A
# chunk (EURLexHTMLChunker.MAX_CHUNK_SIZE).
MAX_OMISSION_CHARS = 600
MAX_SKIPPED_POINTS_CHARS = 2000

MATCH_EXACT = "exact"
MATCH_FUZZY = "fuzzy"
LEVEL_ARTICLE = "article"
LEVEL_FRAMEWORK = "framework"
LEVEL_ANY = "any"

POLICY_FLAG = "flag"
POLICY_STRICT = "strict"
UNVERIFIED_ABSTENTION_REASON = "unverified_citations"
UNVERIFIED_CONFIDENCE_CAP = 0.6

UNVERIFIED_CAVEAT_IT = (
    "Nessuno dei passaggi citati è stato ritrovato testualmente nei testi del corpus: "
    "verifica le fonti prima di usarla."
)
UNVERIFIED_CAVEAT_EN = (
    "None of the cited passages was found verbatim in the corpus texts: "
    "check the sources before using this answer."
)
UNVERIFIED_ABSTENTION_IT = (
    "Non posso fornire una risposta verificata: nessuno dei passaggi citati è stato "
    "ritrovato testualmente nei testi del corpus. Consulta direttamente le fonti ufficiali "
    "oppure richiedi una revisione esperta."
)
UNVERIFIED_ABSTENTION_EN = (
    "I cannot provide a verified answer: none of the cited passages was found verbatim "
    "in the corpus texts. Please consult the official sources directly or request an "
    "expert review."
)
# An answer that cites nothing.
NO_CITATIONS_CAVEAT_IT = (
    "La risposta non cita nessun passaggio dei testi del corpus: verifica le fonti prima di usarla."
)
NO_CITATIONS_CAVEAT_EN = (
    "The answer cites no passage of the corpus texts: check the sources before using it."
)
# The same, when some quote was found, but not where its citation points.
UNVERIFIED_ELSEWHERE_CAVEAT_IT = (
    "Nessuno dei passaggi citati è stato ritrovato testualmente nella disposizione che la "
    "risposta indica: verifica le fonti prima di usarla."
)
UNVERIFIED_ELSEWHERE_CAVEAT_EN = (
    "None of the cited passages was found verbatim in the provision the answer names: "
    "check the sources before using this answer."
)
UNVERIFIED_ELSEWHERE_ABSTENTION_IT = (
    "Non posso fornire una risposta verificata: nessuno dei passaggi citati è stato "
    "ritrovato testualmente nella disposizione che la risposta indica. Consulta direttamente "
    "le fonti ufficiali oppure richiedi una revisione esperta."
)
UNVERIFIED_ELSEWHERE_ABSTENTION_EN = (
    "I cannot provide a verified answer: none of the cited passages was found verbatim in "
    "the provision the answer names. Please consult the official sources directly or "
    "request an expert review."
)
# Each of our abstentions, in Italian and English.
_ABSTENTION_TWINS: dict[str, tuple[str, str]] = {
    text: twins
    for twins in (
        (UNVERIFIED_ABSTENTION_IT, UNVERIFIED_ABSTENTION_EN),
        (UNVERIFIED_ELSEWHERE_ABSTENTION_IT, UNVERIFIED_ELSEWHERE_ABSTENTION_EN),
    )
    for text in twins
}

# Where a quote found word for word, but not where its citation points, is
# (annotate_citations): in another act, another article, another paragraph.
FOUND_IN_ACT = "act"
FOUND_IN_ARTICLE = "article"
FOUND_IN_PARAGRAPH = "paragraph"
# The fields annotate_citations writes on every citation next to CITATION_FIELDS.
ELSEWHERE_FIELDS: tuple[str, ...] = (
    "found_elsewhere",
    "found_in",
    "found_celex",
    "found_article",
    "found_paragraph",
    "found_quote",
    "found_url",
)

# Framework keys of the seeded registry (src.crawler.eurlex.client.FRAMEWORK_ORDER)
# and the names a model writes for them. Only used to MATCH a citation to the
# chunks; a key that is not listed still matches a chunk carrying the same key.
_KNOWN_FRAMEWORKS: tuple[str, ...] = (
    "CSRD",
    "CSDDD",
    "AI_ACT",
    "DORA",
    "NIS2",
    "TAXONOMY",
    "GDPR",
    "CRA",
)
_FRAMEWORK_ALIASES: dict[str, str] = {
    "AIACT": "AI_ACT",
    "EU_AI_ACT": "AI_ACT",
    "ARTIFICIAL_INTELLIGENCE_ACT": "AI_ACT",
    "EU_TAXONOMY": "TAXONOMY",
    "TAXONOMY_REGULATION": "TAXONOMY",
    "TASSONOMIA": "TAXONOMY",
    "TASSONOMIA_UE": "TAXONOMY",
    "NIS_2": "NIS2",
    "CYBER_RESILIENCE_ACT": "CRA",
    "DIGITAL_OPERATIONAL_RESILIENCE_ACT": "DORA",
    "GENERAL_DATA_PROTECTION_REGULATION": "GDPR",
    "RGPD": "GDPR",
    "CS3D": "CSDDD",
    # ESRS Set 1 is seeded under CSRD, but it is an act of its own: Delegated
    # Regulation (EU) 2023/2772, cited by its CELEX (see principal_celex).
    "ESRS": "32023R2772",
}
# How a caveat names the framework of a principal act: "(AI Act)".
_FRAMEWORK_NAMES: dict[str, tuple[str, str]] = {
    "AI_ACT": ("AI Act", "AI Act"),
    "TAXONOMY": ("Tassonomia", "Taxonomy"),
}

# ─── Normalization ───────────────────────────────────────────────────

_APOSTROPHES = "\u2018\u2019\u201a\u201b\u2032\u2035\u02bb\u02bc`\u00b4\u2039\u203a"
_DOUBLE_QUOTES = "\u201c\u201d\u201e\u201f\u2033\u2036\u00ab\u00bb"
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2043\u2212\ufe58\ufe63\uff0d"
_SPACES = (
    "\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u202f\u205f\u3000\u0085\u2028\u2029"
)
_REMOVED = "\u00ad\u200b\u200c\u200d\u2060\ufeff"

_CHAR_MAP: dict[int, str | None] = {
    **{ord(c): "'" for c in _APOSTROPHES},
    **{ord(c): '"' for c in _DOUBLE_QUOTES},
    **{ord(c): "-" for c in _DASHES},
    **{ord(c): " " for c in _SPACES},
    **{ord(c): None for c in _REMOVED},
    ord("\u2026"): "...",
}

# The markers EUR-Lex writes inside a consolidated text: "\u25bcB" and "\u25bcM6" open
# the original wording and each amendment, "\u25baM2" opens an inserted passage and
# "\u25c4" closes it. They are not part of the law, and the model quotes the wording
# without them: both sides of the comparison read them as a space.
_CONSOLIDATION_MARKER_RE = re.compile(r"[\u25bc\u25ba](?:[A-Z]{1,2}\d{0,3}(?![A-Za-z]))?|\u25c4")

# Stripped from both ends of a quote: whitespace, quotes, sentence punctuation,
# dashes; the bracketed omission markers are removed by _strip_edges too.
_EDGE_CHARS = " '\".,;:!?-"
_EDGE_MARKERS = ("[...]", "(...)")
# Omission markers inside a quote (after normalization "…" is already "...").
_OMISSION_RE = re.compile(r"\s*(?:\[\.\.\.\]|\(\.\.\.\)|\.{3,})\s*")


def _fold(cluster: str) -> str:
    """Normalize one grapheme cluster (a base character and its combining marks)."""
    text = cluster.translate(_CHAR_MAP)
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text).translate(_CHAR_MAP).casefold()
    return "".join(" " if ch.isspace() else ch for ch in text)


def _normalize_with_map(text: str) -> tuple[str, list[int], list[int]]:
    """Normalized ``text`` plus, per normalized character, its source span.

    ``starts[k]`` / ``ends[k]`` delimit the characters of ``text`` that produced
    normalized character ``k``, so a match found on the normalized form maps
    back to the exact original wording (``official_quote``). Runs of whitespace
    collapse to one space; leading and trailing whitespace is dropped.
    """
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    n = len(text)
    # EUR-Lex consolidation markers count as whitespace (_CONSOLIDATION_MARKER_RE).
    marker_end: dict[int, int] = {}
    if "\u25bc" in text or "\u25ba" in text or "\u25c4" in text:
        marker_end = {m.start(): m.end() for m in _CONSOLIDATION_MARKER_RE.finditer(text)}
    i = 0
    while i < n:
        if i in marker_end:
            j = marker_end[i]
            if out and out[-1] != " ":
                out.append(" ")
                starts.append(i)
                ends.append(j)
            elif out:
                ends[-1] = j
            i = j
            continue
        ch = text[i]
        j = i + 1
        while j < n and text[j] >= "\u0300" and unicodedata.combining(text[j]):
            j += 1
        if ch < "\x80" and j == i + 1:
            folded = " " if ch.isspace() else ("'" if ch == "`" else ch.lower())
        else:
            folded = _fold(text[i:j])
        for fc in folded:
            if fc == " ":
                if not out:
                    continue
                if out[-1] == " ":
                    ends[-1] = j
                    continue
            out.append(fc)
            starts.append(i)
            ends.append(j)
        i = j
    if out and out[-1] == " ":
        out.pop()
        starts.pop()
        ends.pop()
    return "".join(out), starts, ends


def _strip_edges(text: str) -> str:
    previous = None
    while text != previous:
        previous = text
        text = text.strip(_EDGE_CHARS)
        for marker in _EDGE_MARKERS:
            if text.startswith(marker):
                text = text[len(marker) :]
            if text.endswith(marker):
                text = text[: -len(marker)]
    return text


def normalize(text: str) -> str:
    """Canonical form used to compare a quote with the official text.

    NFKC, casefold, typographic quotes and apostrophes to ASCII, every dash to
    ``-``, non-breaking and other Unicode spaces to a space, soft hyphens and
    zero-width characters removed, whitespace collapsed, then surrounding
    quotes, punctuation and ellipses stripped.
    """
    folded, _, _ = _normalize_with_map(str(text or ""))
    return _strip_edges(folded)


# ─── References: framework, article, CELEX ───────────────────────────

_LATIN_SUFFIXES = "bis|ter|quater|quinquies|sexies|septies|octies|novies|nonies|decies"
_NUMBER = rf"(?P<num>\d{{1,4}})(?:[\s-]?(?P<latin>{_LATIN_SUFFIXES})\b|(?P<letter>[a-z])(?![a-z]))?"
_ARTICLE_RE = re.compile(
    rf"\b(?:articles?|articol[oi]|artikel|arts?|artt)\b\.?\s*{_NUMBER}", re.IGNORECASE
)
_RECITAL_RE = re.compile(
    r"\b(?:recitals?|considerand[oi]|erw[äa]gungsgrund)\b\.?\s*\(?(?P<num>\d{1,3})\)?",
    re.IGNORECASE,
)
_ANNEX_RE = re.compile(
    r"\b(?:annex(?:es)?|annexe|allegat[oi]|anhang)\b\.?\s*(?P<num>[IVXLCDM]+|\d{1,3}|[A-Z])\b",
    re.IGNORECASE,
)
_BARE_NUMBER_RE = re.compile(rf"^\s*{_NUMBER}(?![\d/.])", re.IGNORECASE)
# A numbered paragraph at the start of a line of an article: "2. Providers ...".
_PARAGRAPH_LINE_RE = re.compile(r"(?m)^[ \t]*(\d{1,3})\.[ \t]+\S")
# The paragraph a reference names after the article: ", par. 2", "paragrafo 2".
_PARAGRAPH_REF_RE = re.compile(
    r"[\s,;]*\b(?:par(?:agrafo|agraph|a)?|comma)\b\.?\s*(\d{1,3})\b", re.IGNORECASE
)


def _article_number(match: re.Match[str]) -> str:
    suffix = (match.group("latin") or match.group("letter") or "").lower()
    return f"{match.group('num')}{suffix}"


def parse_article(reference: Any) -> str | None:
    """Canonical key of the provision a reference names, or None.

    ``"Art. 50"``, ``"articolo 50"``, ``"50"``, ``"50(1)"`` and
    ``"art. 50, par. 1"`` all give ``"art:50"``; ``"Art. 19a"`` gives
    ``"art:19a"``, ``"Art. 12 bis"`` ``"art:12bis"``; recitals and annexes give
    ``"recital:45"`` and ``"annex:III"``.
    """
    text = str(reference or "").strip()
    if not text:
        return None
    m = _ARTICLE_RE.search(text)
    if m:
        return f"art:{_article_number(m)}"
    m = _RECITAL_RE.search(text)
    if m:
        return f"recital:{m.group('num')}"
    m = _ANNEX_RE.search(text)
    if m:
        return f"annex:{m.group('num').upper()}"
    m = _BARE_NUMBER_RE.match(text)
    if m:
        return f"art:{_article_number(m)}"
    return None


# Inserted articles carry a letter in English ("19a") and a Latin adverb in
# Italian ("19 bis"): the same provision. Keys keep the form of their language
# (article_label shows them as the chunker labels units); comparisons go
# through same_article.
_LATIN_TO_LETTER = {
    "bis": "a",
    "ter": "b",
    "quater": "c",
    "quinquies": "d",
    "sexies": "e",
    "septies": "f",
    "octies": "g",
    "novies": "h",
    "nonies": "h",
    "decies": "i",
}


def _canonical_article(key: str) -> str:
    kind, _, number = key.partition(":")
    if kind == "art":
        m = re.match(rf"^(\d+)({_LATIN_SUFFIXES})$", number)
        if m:
            return f"art:{m.group(1)}{_LATIN_TO_LETTER[m.group(2)]}"
    return key


def same_article(a: str | None, b: str | None) -> bool:
    """True when two parse_article keys name the same provision ("art:19a" = "art:19bis")."""
    return a is not None and b is not None and _canonical_article(a) == _canonical_article(b)


def article_label(key: str | None) -> str | None:
    """Display form of a ``parse_article`` key, as the chunker labels units."""
    if not key:
        return None
    kind, _, number = key.partition(":")
    if kind == "art":
        m = re.match(rf"^(\d+)({_LATIN_SUFFIXES})$", number)
        return f"Art. {m.group(1)} {m.group(2)}" if m else f"Art. {number}"
    if kind == "recital":
        return f"Recital {number}"
    if kind == "annex":
        return f"Annex {number}"
    return None


_CELEX_PREFIX_RE = re.compile(r"(?i)celex\s*:?\s*(\S+)$")
# An act followed by the unit it cites: "32026L0470, Art. 4", "AI Act art. 50(2)".
_TRAILING_UNIT_RE = re.compile(
    r"(?i)^(?P<act>.*?\S)[\s,;:\-\N{EN DASH}]+"
    r"(?:art(?:icle|icolo|\.)?|recital|considerando|annex|allegato)\s*(?:\d|[IVXLC]+\b)"
)


def normalize_framework(name: Any) -> str:
    """Canonical framework key: ``"AI Act"`` -> ``"AI_ACT"``, ``"nis 2"`` -> ``"NIS2"``.

    A CELEX number is mapped to its base act (``02024R1689-20260727`` ->
    ``32024R1689``); an unknown name is returned in the same upper-case,
    underscore-joined form, so it still matches a chunk with the same key.
    An article, recital or annex written after the act is dropped
    (``"32026L0470, Art. 4"`` -> ``"32026L0470"``): the citation names its
    unit in its own field.
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
    # The model sometimes writes the cited article into the framework.
    trailing = _TRAILING_UNIT_RE.match(raw)
    if trailing:
        raw = trailing.group("act")
    # The model sometimes copies the label's "CELEX 32024R2847" as the framework.
    prefixed = _CELEX_PREFIX_RE.match(raw)
    if prefixed and celex_utils.parse_celex(prefixed.group(1).upper()) is not None:
        raw = prefixed.group(1)
    if celex_utils.parse_celex(raw.upper()) is not None:
        return celex_utils.base_celex(raw.upper())
    key = re.sub(r"[^A-Z0-9]+", "_", raw.upper()).strip("_")
    if key in _FRAMEWORK_ALIASES:
        return _FRAMEWORK_ALIASES[key]
    if key in _KNOWN_FRAMEWORKS:
        return key
    padded = f"_{key}_"
    for alias in sorted(_FRAMEWORK_ALIASES, key=len, reverse=True):
        if f"_{alias}_" in padded:
            return _FRAMEWORK_ALIASES[alias]
    for known in _KNOWN_FRAMEWORKS:
        if f"_{known}_" in padded:
            return known
    return key


@lru_cache(maxsize=1)
def _principal_acts() -> dict[str, str]:
    """Framework key -> CELEX of its principal act: its first basic act in TRACKED_ACTS."""
    from src.crawler.eurlex.client import TRACKED_ACTS

    principals: dict[str, str] = {}
    for act in TRACKED_ACTS:
        if act.kind == "basic":
            principals.setdefault(act.framework, act.celex)
    return principals


def principal_celex(framework: Any) -> str | None:
    """CELEX of the act a framework key names, or None for a CELEX or an unknown key.

    A framework groups acts (src.crawler.eurlex.client.TRACKED_ACTS): CSRD
    holds the CSRD, the Accounting Directive, ESRS Set 1 and the Omnibus
    directives; AI_ACT the AI Act and the Digital Omnibus on AI. The key names
    the first basic act of the group (CSRD: 32022L2464, AI_ACT: 32024R1689),
    its principal act; every other act of the group is cited by its CELEX.
    """
    return _principal_acts().get(normalize_framework(framework))


def _tracked_act(celex: str) -> Any:
    from src.crawler.eurlex.client import get_tracked_act

    return get_tracked_act(celex)


def base_celex(chunk: dict[str, Any]) -> str | None:
    """The base act of a chunk: ``celex`` or ``source_celex``, never a consolidated id.

    ``02024R1689-20260727`` (a CELLAR consolidated version) becomes
    ``32024R1689``. A non-CELEX identifier (an uploaded document) is returned
    as it is; None when the chunk carries neither field.
    """
    raw_ids = [str(chunk.get(key) or "").strip() for key in ("celex", "source_celex")]
    for raw in raw_ids:
        if raw and celex_utils.parse_celex(raw) is not None:
            return celex_utils.base_celex(raw)
    return next((raw for raw in raw_ids if raw), None)


def eurlex_url(celex: str | None, lang: str | None) -> str | None:
    """EUR-Lex page of an act in the chunk's language, built server-side.

    ``https://eur-lex.europa.eu/legal-content/{IT|EN}/TXT/?uri=CELEX:{celex}``;
    English when the language is unknown, None for a non-CELEX identifier.
    """
    if not celex:
        return None
    return celex_utils.eurlex_txt_url(celex, celex_utils.normalize_lang(lang, "EN"))


# ─── Results ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class VerificationResult:
    """Outcome of verifying one citation; every field is None when not verified."""

    verified: bool = False
    match: str | None = None  # "exact" | "fuzzy"
    level: str | None = None  # "article" | "framework" | "any"
    chunk_id: str | None = None
    celex: str | None = None
    article: str | None = None
    paragraph: str | None = None
    lang: str | None = None
    consolidated_as_of: str | None = None
    url: str | None = None
    official_quote: str | None = None
    # An article verified in the text of the act that amends it (B in
    # src/agents/quoted_articles.py): that act and its article; ``url`` is its page.
    amending_celex: str | None = None
    amending_article: str | None = None
    # Set only when NOT verified and a passage almost matched: the official
    # wording, where it is, and the words that differ ({"quoted", "official"}).
    near_quote: str | None = None
    near_article: str | None = None
    differences: list[dict[str, str]] | None = None

    def as_fields(self) -> dict[str, Any]:
        """The fields written on the citation dict (all keys, None included)."""
        return asdict(self)


CITATION_FIELDS: tuple[str, ...] = tuple(f.name for f in fields(VerificationResult))
_UNVERIFIED = VerificationResult()


@dataclass
class _Chunk:
    """A retrieved chunk prepared once for every citation of an answer."""

    data: dict[str, Any]
    text: str
    norm: str
    starts: list[int]
    ends: list[int]
    frameworks: frozenset[str]
    article_key: str | None
    celex: str | None
    # Normalized positions where a point or a paragraph starts (_point_starts).
    points: frozenset[int] | None = None
    # For an article an amending act quotes (case B of quoted_articles): the
    # amending act and its own article, where the wording stands too.
    source_celex: str | None = None
    source_article_key: str | None = None


def _prepare(chunks: Any) -> list[_Chunk]:
    prepared: list[_Chunk] = []
    for chunk in chunks or []:
        data = chunk if isinstance(chunk, dict) else {"text": str(chunk)}
        if data.get("org_id") not in (None, ""):
            # A tenant's own upload: retrievable for the answer, never official text.
            continue
        text = str(data.get("text") or "")
        norm, starts, ends = _normalize_with_map(text)
        if not norm:
            continue
        names = [data.get("framework"), *(data.get("frameworks") or [])]
        # An article quoted by an amending act is cited as the amended act's article.
        quoted = bool(data.get("citation_celex"))
        article = data.get("article") or data.get("article_number")
        prepared.append(
            _Chunk(
                data=data,
                text=text,
                norm=norm,
                starts=starts,
                ends=ends,
                frameworks=frozenset(k for k in (normalize_framework(n) for n in names) if k),
                article_key=parse_article(data["citation_article"] if quoted else article),
                celex=str(data["citation_celex"]) if quoted else base_celex(data),
                source_celex=base_celex(data) if quoted else None,
                source_article_key=parse_article(article) if quoted else None,
            )
        )
    return prepared


def _quote_of(citation: dict[str, Any]) -> str:
    return str(citation.get("quote_snippet") or citation.get("quote") or "")


def _reference_of(citation: dict[str, Any]) -> str:
    # The model's own reference first: on a citation that already went through
    # the verifier, ``article`` is the verified location, not what was cited.
    return str(
        citation.get("reference") or citation.get("article_ref") or citation.get("article") or ""
    )


def _segments(quote: str) -> list[str]:
    """Every part of a normalized quote, split at its omission marks: all must be found."""
    parts = _OMISSION_RE.split(quote)
    if len(parts) == 1:
        return [quote] if quote else []
    return [p for p in (_strip_edges(part) for part in parts) if p]


def _specific_enough(segments: list[str]) -> bool:
    content = " ".join(segments)
    return len(content) >= MIN_QUOTE_CHARS and len(content.split()) >= MIN_QUOTE_WORDS


# Words that carry no meaning of their own, in Italian and English (accents
# removed): articles, prepositions, conjunctions, pronouns, auxiliary and modal
# verbs, negations and the adverbs that set the scope of a rule ("solo", "only",
# "senza", "unless"). A part between omissions made only of these, of numbers
# or of a list marker ("non", "not", "shall not", "72", "(a)") takes its
# meaning from the text the omission removed, so it is never verified.
_FUNCTION_WORDS = frozenset(
    "il lo la i gli le l un uno una di d a da in con su per tra fra del dello della dei "
    "degli delle dell al allo alla ai agli alle all dal dallo dalla dai dagli dalle dall nel "
    "nello nella nei negli nelle nell sul sullo sulla sui sugli sulle sull col coi e ed o od "
    "ma ne se che anche oppure ovvero ossia nonche inoltre pero perche poiche come quando "
    "mentre sia non piu meno gia solo soltanto sempre mai almeno ancora cosi quindi dunque "
    "pure senza salvo tranne eccetto si ci vi li mi ti esso essa essi esse cio cui chi quale "
    "quali questo questa questi queste quello quella quelli quelle tale tali ogni ciascun "
    "ciascuno ciascuna nessun nessuno nessuna alcun alcuno alcuna alcuni alcune altro altra "
    "altri altre stesso stessa stessi stesse loro suo sua suoi sue sono siano sara saranno "
    "era erano essere stato stata stati state ha hanno abbia abbiano avere avuto puo possono "
    "possa possano potra potranno deve devono debba debbano dovra dovranno viene vengono "
    "venga vengano "
    "the an of to on at by for with from as into onto upon about under over between "
    "within without and or nor but if that which who whom whose this these those it its "
    "they them their he she his her there here is are be been being was were am shall "
    "should may might must will would can could do does did done not no never neither "
    "either has have had having any all each every such so than then where when what also "
    "only more less other same own both unless except".split()
)


def _has_content(part: str) -> bool:
    """True when a part of a quote holds a word of its own (see _FUNCTION_WORDS)."""
    return any(
        len(word) >= 3 and not word.isdigit() and _without_marks(word) not in _FUNCTION_WORDS
        for word in _WORD_RE.findall(part)
    )


def _on_word_boundaries(text: str, start: int, end: int) -> bool:
    """True when ``text[start:end]`` neither starts nor ends inside a word."""
    if 0 < start < len(text) and text[start - 1].isalnum() and text[start].isalnum():
        return False
    return not (0 < end < len(text) and text[end - 1].isalnum() and text[end].isalnum())


# A line that starts a point or a paragraph: before the text, at most a number
# or a letter that numbers it ("4.", "e)", "(iv)", a dash or a bullet), opening
# quotation marks and the markers of a consolidated text (a black pointer or
# triangle with its code, "M1", "B").
_CONSOLIDATION_MARK = (
    r"[\N{BLACK RIGHT-POINTING POINTER}\N{BLACK LEFT-POINTING POINTER}"
    r"\N{BLACK DOWN-POINTING TRIANGLE}\N{BLACK UP-POINTING TRIANGLE}]\s*(?:[A-Z]\d{0,3})?\s*"
)
_POINT_START_RE = re.compile(
    r"[\s'\"\N{LEFT SINGLE QUOTATION MARK}\N{RIGHT SINGLE QUOTATION MARK}"
    r"\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}"
    r"\N{LEFT-POINTING DOUBLE ANGLE QUOTATION MARK}"
    r"\N{RIGHT-POINTING DOUBLE ANGLE QUOTATION MARK}]*"
    rf"(?:{_CONSOLIDATION_MARK})*"
    r"(?:\(?(?:\d{1,3}[a-z]?|[a-z]{1,2}|[ivxlc]{1,6})[.)]"
    r"|[\-\N{HYPHEN}-\N{HORIZONTAL BAR}\N{BULLET}])?"
    rf"\s*(?:{_CONSOLIDATION_MARK})*",
    re.IGNORECASE,
)


def _gram_size(length: int) -> int:
    return 8 if length >= 32 else max(4, length // 4)


# How many places of a chunk a part is aligned with, at most, when it is not
# found word for word (the best-supported offsets, see _fuzzy_spans).
_FUZZY_PLACES = 8


def _fuzzy_spans(needle: str, text: str) -> list[tuple[int, int, float]]:
    """Spans of ``text`` whose difflib ratio with ``needle`` is >= 0.92, best first.

    Comparing every window of the needle's length is quadratic, so the windows
    worth comparing are located first: each k-gram of the needle that occurs in
    the text votes for the offset where the needle would start, and only the
    best-supported offsets (at least a quarter of the k-grams, at most
    _FUZZY_PLACES places) are aligned with difflib. A near-copy with a few
    scattered differences (punctuation, a mistyped letter) keeps most k-grams
    intact and collects the votes; a paraphrase or a fabricated quote does not.
    """
    length = len(needle)
    if length < MIN_SEGMENT_CHARS or len(text) < length * FUZZY_MIN_RATIO:
        return []
    gram = _gram_size(length)
    stride = max(1, gram // 2)
    votes: dict[int, int] = {}
    n_grams = 0
    for i in range(0, length - gram + 1, stride):
        n_grams += 1
        piece = needle[i : i + gram]
        k = text.find(piece)
        while k != -1:
            votes[k - i] = votes.get(k - i, 0) + 1
            k = text.find(piece, k + 1)
    if not votes:
        return []

    width = max(3, math.ceil(length * (1 - FUZZY_MIN_RATIO)))
    offsets = sorted(votes)
    support: dict[int, int] = {}
    lo = hi = running = 0
    for offset in offsets:
        while hi < len(offsets) and offsets[hi] <= offset + width:
            running += votes[offsets[hi]]
            hi += 1
        while offsets[lo] < offset - width:
            running -= votes[offsets[lo]]
            lo += 1
        support[offset] = running
    needed = max(2, math.ceil(0.25 * n_grams))

    centers: list[int] = []
    for offset in sorted(support, key=lambda o: (-support[o], o)):
        if support[offset] < needed or len(centers) == _FUZZY_PLACES:
            break
        if all(abs(offset - c) > width for c in centers):
            centers.append(offset)

    found: list[tuple[int, int, float]] = []
    for center in centers:
        r_start = max(0, center - width)
        r_end = min(len(text), center + length + width)
        region = text[r_start:r_end]
        blocks = [
            b
            for b in SequenceMatcher(None, needle, region, autojunk=False).get_matching_blocks()
            if b.size >= 3
        ]
        if not blocks:
            continue
        first, last = blocks[0], blocks[-1]
        s = r_start + max(0, first.b - first.a)
        e = r_start + min(len(region), last.b + last.size + (length - last.a - last.size))
        if e <= s:
            continue
        matcher = SequenceMatcher(None, needle, text[s:e], autojunk=False)
        if matcher.real_quick_ratio() < FUZZY_MIN_RATIO or matcher.quick_ratio() < FUZZY_MIN_RATIO:
            continue
        ratio = matcher.ratio()
        if ratio >= FUZZY_MIN_RATIO:
            found.append((s, e, ratio))
    return sorted(found, key=lambda span: -span[2])


# ─── Do the words agree? ─────────────────────────────────────────────

# A word of a normalized text: a run of digits or a run of letters.
_WORD_RE = re.compile(r"\d+|[^\W\d_]+")
# Words that state a number, in Italian and English. "eight" and "eighty" are one
# letter apart: a number word is compared like a number, never forgiven a slip.
_NUMBER_WORDS = frozenset(
    "zero uno una due tre quattro cinque sei sette otto nove dieci undici dodici tredici "
    "quattordici quindici sedici diciassette diciotto diciannove venti trenta quaranta "
    "cinquanta sessanta settanta ottanta novanta cento mille mila milione milioni miliardo "
    "miliardi one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty "
    "seventy eighty ninety hundred thousand million billion".split()
)
# Italian compounds: "ventuno", "trentasei", "duecento", "tremila".
_NUMBER_COMPOUND_RE = re.compile(
    r"^(?:vent|trent|quarant|cinquant|sessant|settant|ottant|novant)\w+$|^\w+(?:cento|mila)$"
)


def _without_marks(word: str) -> str:
    """The word without accents: "perché" and "perche'" are the same word."""
    decomposed = unicodedata.normalize("NFD", word)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _is_number_word(word: str) -> bool:
    return word in _NUMBER_WORDS or bool(_NUMBER_COMPOUND_RE.match(word))


def _one_letter_slip(a: str, b: str) -> bool:
    """One missing or extra letter inside a long ordinary word: a typing slip.

    Both words have at least MIN_SLIP_WORD_CHARS letters and one of them has a
    letter more, which is neither its first nor its last ("notifca" for
    "notifica"). A different letter in the same place is another word
    ("consent", "content") and a letter added or dropped at the end is another
    form of it ("trattamenti", "requirements"): neither is forgiven. Numbers
    and number words never are.
    """
    if abs(len(a) - len(b)) != 1 or min(len(a), len(b)) < MIN_SLIP_WORD_CHARS:
        return False
    if not (a.isalpha() and b.isalpha()) or _is_number_word(a) or _is_number_word(b):
        return False
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1 :] == short for i in range(1, len(long) - 1))


def _same_word(a: str, b: str) -> bool:
    a, b = _without_marks(a), _without_marks(b)
    return a == b or _one_letter_slip(a, b)


def wording_differences(quote: str, official: str) -> list[tuple[str, str]]:
    """The words of ``quote`` that the official wording does not have, and vice versa.

    Both texts are in normalized form. Punctuation and spacing never count.
    Words are aligned in order; a stretch that differs is forgiven when it is
    the same letters split differently ("infor- mazioni", "15 000"), or when
    each word has its counterpart and the two differ only by accents or by a
    letter missing or added inside a long word (see ``_one_letter_slip``).
    Anything else is returned as ``(quoted words, official words)``: a
    changed number, a changed, added or dropped word, a different letter, a
    different ending. An empty list means the wording is the same.
    """
    quoted = _WORD_RE.findall(quote)
    official_words = _WORD_RE.findall(official)
    differences: list[tuple[str, str]] = []
    matcher = SequenceMatcher(None, quoted, official_words, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        ours, theirs = quoted[i1:i2], official_words[j1:j2]
        if "".join(map(_without_marks, ours)) == "".join(map(_without_marks, theirs)):
            continue
        if len(ours) == len(theirs) and all(
            _same_word(a, b) for a, b in zip(ours, theirs, strict=True)
        ):
            continue
        differences.append((" ".join(ours), " ".join(theirs)))
    return differences


def _whole_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen a span so that it does not begin or end in the middle of a word."""
    while 0 < start < len(text) and text[start - 1].isalnum() and text[start].isalnum():
        start -= 1
    while 0 < end < len(text) and text[end - 1].isalnum() and text[end].isalnum():
        end += 1
    return start, end


# How far into a line the start of a point may be: "(viii) " and a consolidation
# marker before it.
_POINT_PREFIX_MAX = 24


def _point_starts(chunk: _Chunk) -> frozenset[int]:
    """Normalized positions where a point or a paragraph of the chunk starts.

    A position counts when its line holds nothing before it but what
    _POINT_START_RE allows: "e) intervenire" starts a point both at "e" and at
    "intervenire". Computed once per chunk, the first time an omission longer
    than MAX_OMISSION_CHARS asks for it.
    """
    if chunk.points is None:
        found: set[int] = set()
        text = chunk.text
        line = 0
        while line <= len(text):
            newline = text.find("\n", line)
            end = len(text) if newline == -1 else newline
            for orig in range(line, min(end, line + _POINT_PREFIX_MAX) + 1):
                if _POINT_START_RE.fullmatch(text, line, orig) is None:
                    continue
                k = bisect.bisect_left(chunk.starts, orig)
                if k < len(chunk.starts) and chunk.starts[k] == orig:
                    found.add(k)
            line = end + 1
        chunk.points = frozenset(found)
    return chunk.points


def _gap_allowed(chunk: _Chunk, previous_end: int, start: int) -> bool:
    """The omission rule between two parts (MAX_OMISSION_CHARS, MAX_SKIPPED_POINTS_CHARS)."""
    gap = start - previous_end
    if gap < 0:
        return False
    return gap <= MAX_OMISSION_CHARS or (
        gap <= MAX_SKIPPED_POINTS_CHARS and start in _point_starts(chunk)
    )


@dataclass(frozen=True)
class _Span:
    """Where one part of a quote may be; a fuzzy span carries its ratio and differences."""

    start: int
    end: int
    ratio: float = 1.0
    differences: tuple[tuple[str, str], ...] = ()


def _spans_of(
    part: str, chunk: _Chunk, tolerant: bool, cache: dict[tuple[str, bool], list[_Span]]
) -> list[_Span]:
    """Every place of the chunk where a part may be, in order.

    Its occurrences on word boundaries; with ``tolerant``, for a part of at
    least MIN_SEGMENT_CHARS, also the spans that match it fuzzily, widened to
    whole words, with the words that differ (empty when they agree).
    """
    key = (part, tolerant)
    if key in cache:
        return cache[key]
    text = chunk.norm
    spans: list[_Span] = []
    k = text.find(part)
    while k != -1:
        if _on_word_boundaries(text, k, k + len(part)):
            spans.append(_Span(k, k + len(part)))
        k = text.find(part, k + 1)
    if tolerant:
        exact = {(span.start, span.end) for span in spans}
        for start, end, ratio in _fuzzy_spans(part, text):
            start, end = _whole_words(text, start, end)
            if (start, end) not in exact:
                exact.add((start, end))
                differences = tuple(wording_differences(part, text[start:end]))
                spans.append(_Span(start, end, ratio, differences))
        spans.sort(key=lambda span: (span.start, -span.ratio))
    cache[key] = spans
    return spans


def _place(
    parts: list[str],
    chunk: _Chunk,
    first: tuple[int, int] | None = None,
    *,
    tolerant: bool = False,
    literal: bool = True,
    cache: dict[tuple[str, bool], list[_Span]] | None = None,
) -> list[_Span] | None:
    """Where every part of a quote is in one chunk, in order, under the omission rules.

    Each part stands on word boundaries; part i+1 starts after part i ends, at
    most MAX_OMISSION_CHARS later, or at most MAX_SKIPPED_POINTS_CHARS later
    when it starts a point or a paragraph. ``first`` bounds where the first
    part may start (the cited paragraph). A part may occur several times and
    its first occurrence may leave no room for the next parts while a later
    one does, so the first occurrences do not always make a placement. The
    places of each part are listed (_spans_of), then kept, from the last part
    back to the first, only when some place of the next part can follow them;
    the placement then takes, part by part, the first place that follows the
    previous one, and moves each part, from the last back to the first, as
    close as it can go to the next ("Il titolare del trattamento [...]
    documenta": the words that open paragraph 5, not the same words earlier).
    Steps: places x log(places). With ``tolerant`` the fuzzy spans count too;
    ``literal`` keeps only those whose words agree (else a near match may come
    out). None when the parts cannot be placed.
    """
    cache = {} if cache is None else cache
    lists: list[list[_Span]] = []
    for i, part in enumerate(parts):
        spans = _spans_of(part, chunk, tolerant, cache)
        if literal:
            spans = [span for span in spans if not span.differences]
        if i == 0 and first is not None:
            spans = [span for span in spans if first[0] <= span.start <= first[1]]
        if not spans:
            return None
        lists.append(spans)

    points = _point_starts(chunk) if len(parts) > 1 else frozenset()
    feasible: list[list[_Span]] = [[] for _ in parts]
    feasible[-1] = lists[-1]
    for i in range(len(parts) - 2, -1, -1):
        after = feasible[i + 1]
        starts = [span.start for span in after]
        point_starts = [start for start in starts if start in points]
        kept = []
        for span in lists[i]:
            j = bisect.bisect_left(starts, span.end)
            if j < len(starts) and starts[j] - span.end <= MAX_OMISSION_CHARS:
                kept.append(span)
                continue
            j = bisect.bisect_right(point_starts, span.end + MAX_OMISSION_CHARS)
            if j < len(point_starts) and point_starts[j] - span.end <= MAX_SKIPPED_POINTS_CHARS:
                kept.append(span)
        if not kept:
            return None
        feasible[i] = kept

    placed = [feasible[0][0]]
    for i in range(1, len(parts)):
        previous = placed[-1]
        starts = [span.start for span in feasible[i]]
        j = bisect.bisect_left(starts, previous.end)
        placed.append(
            next(span for span in feasible[i][j:] if _gap_allowed(chunk, previous.end, span.start))
        )

    for i in range(len(parts) - 2, -1, -1):
        following = placed[i + 1]
        starts = [span.start for span in lists[i]]
        j = bisect.bisect_left(starts, following.start)
        for span in reversed(lists[i][:j]):
            if span.start <= placed[i].start:
                break
            if span.end > following.start or not _gap_allowed(chunk, span.end, following.start):
                continue
            if i > 0 and not _gap_allowed(chunk, placed[i - 1].end, span.start):
                continue
            placed[i] = span
            break
    return placed


@dataclass
class _Found:
    """Where a quote was found; ``differences`` is non-empty for a near match only."""

    chunk: _Chunk
    spans: list[tuple[int, int]]
    match: str
    differences: list[tuple[str, str]]


def _search(
    segments: list[str],
    candidates: list[_Chunk],
    windows: dict[int, tuple[int, int]] | None = None,
) -> _Found | None:
    """An exact match, else the best literal fuzzy match, else the best near match.

    With ``windows`` (chunk id -> where the first part may start) only the
    chunks it lists are searched, each within its window.
    """
    if windows is not None:
        candidates = [c for c in candidates if id(c) in windows]

    def first(chunk: _Chunk) -> tuple[int, int] | None:
        return windows[id(chunk)] if windows is not None else None

    caches: dict[int, dict[tuple[str, bool], list[_Span]]] = {}
    for chunk in candidates:
        cache = caches.setdefault(id(chunk), {})
        exact = _place(segments, chunk, first(chunk), cache=cache)
        if exact:
            return _Found(chunk, [(s.start, s.end) for s in exact], MATCH_EXACT, [])
    literal: tuple[_Found, float] | None = None
    near: tuple[_Found, float] | None = None
    for chunk in candidates:
        cache = caches.setdefault(id(chunk), {})
        placed = _place(segments, chunk, first(chunk), tolerant=True, cache=cache)
        if placed is not None:
            ratio = min(s.ratio for s in placed)
            if literal is None or ratio > literal[1]:
                where = [(s.start, s.end) for s in placed]
                literal = (_Found(chunk, where, MATCH_FUZZY, []), ratio)
            continue
        if literal is not None:
            continue  # a literal match wins over any near one
        placed = _place(segments, chunk, first(chunk), tolerant=True, literal=False, cache=cache)
        if placed is None:
            continue
        ratio = min(s.ratio for s in placed)
        if near is None or ratio > near[1]:
            differences = [d for s in placed for d in s.differences]
            where = [(s.start, s.end) for s in placed]
            near = (_Found(chunk, where, MATCH_FUZZY, differences), ratio)
    if literal is not None:
        return literal[0]
    return near[0] if near is not None else None


def parse_paragraph(reference: Any) -> str | None:
    """Number of the paragraph an article reference names, or None.

    ``"Art. 50(2)"``, ``"art. 50, par. 2"``, ``"articolo 50, paragrafo 2"`` and
    ``"50(2)"`` give ``"2"``; ``"Art. 6(1)(f)"`` gives ``"1"``. A recital, an
    annex or an article named without a paragraph gives None.
    """
    text = str(reference or "").strip()
    key = parse_article(text)
    if not key or not key.startswith("art:"):
        return None
    m = _ARTICLE_RE.search(text) or _BARE_NUMBER_RE.match(text)
    if m is None:
        return None
    rest = text[m.end() :]
    p = re.match(r"\s*\((\d{1,3})\)", rest) or _PARAGRAPH_REF_RE.match(rest)
    return p.group(1) if p else None


# A range of paragraphs after the first one: "(2)-(3)", "(9) - (10)", "par. 2-3".
_PARAGRAPH_TO_RE = re.compile(r"\s*[-\N{EN DASH}]\s*\(?(\d{1,3})\)?")


def cited_paragraphs(reference: Any) -> str | None:
    """The paragraph, or range of paragraphs, an article reference names, or None.

    ``"Art. 50(2)"`` gives ``"2"``, ``"Art. 9(2)-(3)"`` and ``"art. 9, par. 2-3"``
    give ``"2-3"`` (the form _paragraph_range reads). A quote cited with a range
    may stand in any paragraph of it.
    """
    first = parse_paragraph(reference)
    if first is None:
        return None
    text = str(reference or "").strip()
    m = _ARTICLE_RE.search(text) or _BARE_NUMBER_RE.match(text)
    rest = text[m.end() :] if m is not None else ""
    p = re.match(r"\s*\((\d{1,3})\)", rest) or _PARAGRAPH_REF_RE.match(rest)
    to = _PARAGRAPH_TO_RE.match(rest, p.end()) if p is not None else None
    if to is not None and int(to.group(1)) > int(first):
        return f"{first}-{to.group(1)}"
    return first


def _paragraph_range(value: Any) -> tuple[int, int] | None:
    """``"2"`` -> (2, 2), ``"3-4"`` -> (3, 4); None when the paragraph is not known."""
    m = re.fullmatch(r"\s*(\d{1,3})\s*(?:-\s*(\d{1,3})\s*)?", str(value or ""))
    if not m:
        return None
    lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
    return (lo, hi) if lo <= hi else None


def _covers(value: Any, paragraph: str) -> bool:
    """True unless ``value`` and ``paragraph`` are known paragraphs (or ranges) that do not meet."""
    span, wanted = _paragraph_range(value), _paragraph_range(paragraph)
    return span is None or wanted is None or (span[0] <= wanted[1] and wanted[0] <= span[1])


def _paragraph_window(chunk: _Chunk, paragraph: str) -> tuple[int, int] | None:
    """Where in the chunk the cited paragraph is, as a window for the first part.

    The numbered lines of an article chunk ("2. ...") mark its paragraphs; the
    text before the first one belongs to the chunk's own ``paragraph`` field.
    A chunk whose paragraph is not known is searched whole. None when the
    chunk does not hold the paragraph.
    """
    whole = (0, len(chunk.norm))
    if not (chunk.article_key and chunk.article_key.startswith("art:")):
        return whole
    lines = [
        (m.group(1), bisect.bisect_left(chunk.starts, m.start(1)))
        for m in _PARAGRAPH_LINE_RE.finditer(chunk.text)
    ]
    own = chunk.data.get("paragraph")
    if not lines:
        return whole if _covers(own, paragraph) else None
    # The numbered lines of the cited paragraph (or of each paragraph of a range).
    inside = [i for i, (number, _start) in enumerate(lines) if _covers(number, paragraph)]
    if inside:
        last = inside[-1]
        end = lines[last + 1][1] if last + 1 < len(lines) else len(chunk.norm)
        return (lines[inside[0]][1], end)
    if lines[0][1] > 0 and _paragraph_range(own) is not None and _covers(own, paragraph):
        return (0, lines[0][1])
    return None


def _paragraph_windows(chunks: list[_Chunk], paragraph: str) -> dict[int, tuple[int, int]]:
    windows: dict[int, tuple[int, int]] = {}
    for chunk in chunks:
        window = _paragraph_window(chunk, paragraph)
        if window is not None:
            windows[id(chunk)] = window
    return windows


def _paragraph_at(chunk: _Chunk, position: int) -> str | None:
    """Paragraph of an article that contains ``position`` of the original text."""
    if chunk.article_key and chunk.article_key.startswith("art:"):
        number = None
        for m in _PARAGRAPH_LINE_RE.finditer(chunk.text):
            if m.start() > position:
                break
            number = m.group(1)
        if number:
            return number
    paragraph = chunk.data.get("paragraph")
    return str(paragraph) if paragraph not in (None, "") else None


def _chunk_id(data: dict[str, Any]) -> str | None:
    for key in ("id", "chunk_id", "point_id"):
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _consolidated_as_of(data: dict[str, Any]) -> str | None:
    if data.get("consolidated_as_of"):
        return str(data["consolidated_as_of"])
    for key in ("source_celex", "celex"):
        derived = celex_utils.consolidated_as_of(str(data.get(key) or "").strip())
        if derived:
            return derived
    return None


def _official_piece(text: str) -> str:
    """A span of the official text as shown to the user, without consolidation markers."""
    if "\u25bc" in text or "\u25ba" in text or "\u25c4" in text:
        text = re.sub(r"\s*(?:" + _CONSOLIDATION_MARKER_RE.pattern + r")\s*", " ", text)
    return text.strip()


def _result(
    chunk: _Chunk, spans: list[tuple[int, int]], match: str, level: str
) -> VerificationResult:
    pieces = [_official_piece(chunk.text[chunk.starts[a] : chunk.ends[b - 1]]) for a, b in spans]
    data = chunk.data
    lang = celex_utils.normalize_lang(data.get("lang"), "") or None
    raw_article = str(data.get("article") or data.get("article_number") or "").strip()
    amending_celex = base_celex(data) if data.get("citation_celex") else None
    return VerificationResult(
        verified=True,
        match=match,
        level=level,
        chunk_id=_chunk_id(data),
        celex=chunk.celex,
        article=article_label(chunk.article_key) or raw_article or None,
        paragraph=_paragraph_at(chunk, chunk.starts[spans[0][0]]),
        lang=lang,
        consolidated_as_of=_consolidated_as_of(data),
        url=eurlex_url(amending_celex or chunk.celex, lang),
        official_quote=" [...] ".join(pieces),
        amending_celex=amending_celex,
        amending_article=(raw_article or None) if amending_celex else None,
    )


def _of_act(chunk: _Chunk, celex: str | None) -> bool:
    """True when the chunk may belong to the act ``celex`` (always true when it is None).

    A chunk of another act (its CELEX, base or quoted, says so) does not; a
    chunk without a CELEX cannot be told apart and stays.
    """
    return celex is None or not _is_celex(chunk.celex) or chunk.celex == celex


def _verify(citation: Any, chunks: list[_Chunk]) -> VerificationResult:
    if not isinstance(citation, dict) or not chunks:
        return _UNVERIFIED
    segments = _segments(normalize(_quote_of(citation)))
    if not segments or not _specific_enough(segments):
        return _UNVERIFIED
    if len(segments) > 1 and not all(_has_content(part) for part in segments):
        return _UNVERIFIED

    framework = normalize_framework(citation.get("framework"))
    reference = _reference_of(citation)
    article = parse_article(reference)
    paragraph = cited_paragraphs(reference)
    levels: list[tuple[str, list[_Chunk]]] = []
    if framework:
        # An article an amending act quotes is labelled as the amended act's
        # article; cited as the amending act's own article, the wording is there too.
        of_framework = [
            c
            for c in chunks
            if framework in c.frameworks
            or (c.celex and framework == c.celex)
            or (c.source_celex and framework == c.source_celex)
        ]
        if article:
            # A framework key names its principal act: the article of another act
            # of the group (an amending or delegated act) is another article.
            principal = principal_celex(framework)
            levels.append(
                (
                    LEVEL_ARTICLE,
                    [
                        c
                        for c in of_framework
                        if (same_article(c.article_key, article) and _of_act(c, principal))
                        or (
                            c.source_celex == framework
                            and same_article(c.source_article_key, article)
                        )
                    ],
                )
            )
        levels.append((LEVEL_FRAMEWORK, of_framework))
    levels.append((LEVEL_ANY, chunks))

    searched: set[int] = set()
    near: _Found | None = None
    for level, candidates in levels:
        fresh = [c for c in candidates if id(c) not in searched]
        searched.update(id(c) for c in fresh)
        if not fresh:
            continue
        found = None
        if level == LEVEL_ARTICLE and paragraph:
            # The cited paragraph first: the same words may stand in two of them.
            found = _search(segments, fresh, _paragraph_windows(fresh, paragraph))
        if found is None or found.differences:
            anywhere = _search(segments, fresh)
            if anywhere is not None and (found is None or not anywhere.differences):
                found = anywhere
        if found is None:
            continue
        if not found.differences:
            return _result(found.chunk, found.spans, found.match, level)
        # Close, but a word that matters differs: keep the nearest one (the
        # cited article is searched first) and go on, the literal wording may
        # be in another provision.
        if near is None:
            near = found
    return _near_result(near) if near is not None else _UNVERIFIED


def _near_result(found: _Found) -> VerificationResult:
    """Not verified, with the official wording that almost matched and what differs."""
    chunk = found.chunk
    pieces = [
        _official_piece(chunk.text[chunk.starts[a] : chunk.ends[b - 1]]) for a, b in found.spans
    ]
    raw_article = str(chunk.data.get("article") or chunk.data.get("article_number") or "").strip()
    return VerificationResult(
        near_quote=" [...] ".join(pieces),
        near_article=article_label(chunk.article_key) or raw_article or None,
        differences=[{"quoted": ours, "official": theirs} for ours, theirs in found.differences],
    )


def verify_citation(citation: dict[str, Any], chunks: list[dict[str, Any]]) -> VerificationResult:
    """Verify one citation's quote against the retrieved chunks (see module docstring)."""
    return _verify(citation, _prepare(chunks))


def verify_citations(
    citations: list[Any], chunks: list[dict[str, Any]]
) -> list[VerificationResult]:
    """Verify every citation of an answer, normalizing each chunk only once."""
    prepared = _prepare(chunks)
    return [_verify(citation, prepared) for citation in citations or []]


# ─── Answer-level annotation and policy ──────────────────────────────


def count_verified(citations: Any) -> tuple[int, int]:
    """(verified, total) from the ``verified`` flags of a citation list."""
    items = citations if isinstance(citations, list) else []
    verified = sum(1 for c in items if isinstance(c, dict) and c.get("verified") is True)
    return verified, len(items)


def _is_celex(value: Any) -> bool:
    return isinstance(value, str) and celex_utils.parse_celex(value) is not None


def _found_in(citation: dict[str, Any], outcome: VerificationResult) -> str | None:
    """Where a verified quote is, when that is not where its citation points.

    ``"act"``: in another act than the one cited (level "any", or another act
    of the cited framework); ``"article"``: in another article of the act
    cited, when the citation names one; ``"paragraph"``: in the article cited,
    but in another paragraph than the one it names, when both are known. None
    when the quote is where the citation says, or nothing contradicts it.
    """
    if not outcome.verified:
        return None
    framework = normalize_framework(citation.get("framework"))
    if not framework:
        return None
    reference = _reference_of(citation)
    if outcome.level == LEVEL_ARTICLE:
        if outcome.amending_celex and framework == outcome.amending_celex:
            # Cited as the amending act's own article, where the wording stands:
            # its paragraphs are not those of the article it replaces.
            return None
        cited = _paragraph_range(cited_paragraphs(reference))
        found = _paragraph_range(outcome.paragraph)
        if cited and found and not (found[0] <= cited[1] and cited[0] <= found[1]):
            return FOUND_IN_PARAGRAPH
        return None
    cited_act = framework if _is_celex(framework) else principal_celex(framework)
    found_act = outcome.celex if _is_celex(outcome.celex) else None
    if cited_act and found_act and cited_act != found_act:
        return FOUND_IN_ACT
    if outcome.level == LEVEL_ANY and not (cited_act and found_act == cited_act):
        return FOUND_IN_ACT
    return FOUND_IN_ARTICLE if parse_article(reference) else None


def _annotated(citation: dict[str, Any], outcome: VerificationResult) -> dict[str, Any]:
    where = _found_in(citation, outcome)
    if where is None:
        return {
            **citation,
            **outcome.as_fields(),
            "found_elsewhere": False,
            **dict.fromkeys(ELSEWHERE_FIELDS[1:]),
        }
    return {
        **citation,
        **_UNVERIFIED.as_fields(),
        "found_elsewhere": True,
        "found_in": where,
        "found_celex": outcome.celex,
        "found_article": outcome.article,
        "found_paragraph": outcome.paragraph,
        "found_quote": outcome.official_quote,
        "found_url": outcome.url,
    }


def annotate_citations(result: dict[str, Any], chunks: list[Any] | None) -> dict[str, Any]:
    """Write the verification fields on COPIES of the citations, plus the counters.

    The citation dicts may be shared (e.g. with the SNC samples), so they are
    never modified in place. Non-dict citations are kept as they are and count
    as unverified. A quote found word for word, but not where its citation
    points (see ``_found_in``), is not a verified citation: it gets
    ``verified`` False with the other fields of ``verify_citation`` empty, and
    ``found_elsewhere`` True with where the wording really is (module
    docstring). Sets ``verified_citations`` and ``citations_total``.
    """
    citations = result.get("citations")
    items = citations if isinstance(citations, list) else []
    outcomes = verify_citations(items, chunks or [])
    annotated = [
        _annotated(cit, outcome) if isinstance(cit, dict) else cit
        for cit, outcome in zip(items, outcomes, strict=True)
    ]
    if isinstance(citations, list):
        result["citations"] = annotated
    result["verified_citations"] = sum(
        1 for cit in annotated if isinstance(cit, dict) and cit.get("verified") is True
    )
    result["citations_total"] = len(items)
    return result


def citation_counters(result: dict[str, Any]) -> tuple[int, int]:
    """(verified_citations, citations_total) of an answer, from its counters or its flags."""
    verified, total = result.get("verified_citations"), result.get("citations_total")
    if (
        isinstance(verified, int)
        and isinstance(total, int)
        and not isinstance(verified, bool)
        and not isinstance(total, bool)
    ):
        return verified, total
    return count_verified(result.get("citations"))


def unverified_policy_applies(result: Any) -> bool:
    """True for a real answer (no error, no abstention) whose citations are all unverified."""
    if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
        return False
    if result.get("abstention_reason"):
        return False
    verified, total = citation_counters(result)
    return total > 0 and verified == 0


def _elsewhere(result: dict[str, Any]) -> list[dict[str, Any]]:
    citations = result.get("citations")
    items = citations if isinstance(citations, list) else []
    return [c for c in items if isinstance(c, dict) and c.get("found_elsewhere") is True]


def policy_requires_review(result: Any) -> bool:
    """True when the citation policy flags a real answer for expert review.

    It cites nothing, all its citations are unverified, or one of them was
    found in another act, article or paragraph than the one cited.
    """
    if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
        return False
    if result.get("abstention_reason"):
        return False
    _, total = citation_counters(result)
    return total == 0 or unverified_policy_applies(result) or bool(_elsewhere(result))


def policy_mode(settings: Any) -> str:
    """The configured policy (``Settings.citation_verification``); ``flag`` if unset/unknown."""
    mode = getattr(settings, "citation_verification", POLICY_FLAG)
    return mode if mode in (POLICY_FLAG, POLICY_STRICT) else POLICY_FLAG


def _is_english(language: str | None) -> bool:
    return str(language or "").strip().lower()[:2] == "en"


def _cap_confidence(result: dict[str, Any]) -> None:
    if result.get("confidence_score") is None:
        return  # nothing scored this answer: no number is invented here
    try:
        result["confidence_score"] = min(
            float(result["confidence_score"]), UNVERIFIED_CONFIDENCE_CAP
        )
    except (TypeError, ValueError):
        result["confidence_score"] = UNVERIFIED_CONFIDENCE_CAP


def act_name(celex: str | None, english: bool = False) -> str | None:
    """How a caveat names an act, from its CELEX: "Regolamento (UE) 2024/1689 (AI Act)".

    From 2015 on acts are numbered year/number with "(UE)", a tracked
    delegated or implementing act says so ("Regolamento delegato (UE)
    2023/2772") and the principal act of a framework adds its name; the
    directives of 2010-2014 read "Direttiva 2013/34/UE"; anything else is
    named by its CELEX. None without a CELEX.
    """
    if not celex:
        return None
    m = re.fullmatch(r"3(\d{4})([RLD])(\d{4})", celex)
    if m is None:
        return f"CELEX {celex}"
    year, kind, number = m.group(1), m.group(2), str(int(m.group(3)))
    if int(year) >= 2015:
        act = _tracked_act(celex)
        eli_type = getattr(act, "eli_type", "")
        it, en = {
            "R": ("Regolamento", "Regulation"),
            "L": ("Direttiva", "Directive"),
            "D": ("Decisione", "Decision"),
        }[kind]
        if eli_type in ("reg_del", "dir_del"):
            it, en = f"{it} delegat{'o' if kind == 'R' else 'a'}", f"Delegated {en}"
        elif eli_type in ("reg_impl", "dir_impl"):
            it, en = f"{it} di esecuzione", f"Implementing {en}"
        name = f"{en} (EU) {year}/{number}" if english else f"{it} (UE) {year}/{number}"
        framework = next((k for k, v in _principal_acts().items() if v == celex), None)
        if framework:
            label = _FRAMEWORK_NAMES.get(framework, (framework, framework))[1 if english else 0]
            name = f"{name} ({label})"
        return name
    if kind == "L" and int(year) >= 2010:
        return f"Directive {year}/{number}/EU" if english else f"Direttiva {year}/{number}/UE"
    return f"CELEX {celex}"


def _elsewhere_caveat(citation: dict[str, Any], english: bool) -> str:
    """The caveat that names a citation whose wording is in another act, article or paragraph."""
    label = ", ".join(
        part
        for part in (str(citation.get("framework") or "").strip(), _reference_of(citation).strip())
        if part
    )
    article = str(citation.get("found_article") or "").strip()
    paragraph = str(citation.get("found_paragraph") or "").strip()
    if article and paragraph:
        article = f"{article}, {'para.' if english else 'par.'} {paragraph}"
    where = citation.get("found_in")
    places = [article] if article else []
    if where == FOUND_IN_ACT:
        name = act_name(str(citation.get("found_celex") or "") or None, english)
        places = [name, *places] if name else places
    place = f", {', '.join(places)}" if places else ""
    if english:
        kind = {
            FOUND_IN_ARTICLE: "in another article of the same act",
            FOUND_IN_PARAGRAPH: "in another paragraph of the same article",
        }.get(str(where), "in another act")
        return f"The citation [{label}] is not verified: the quoted text is {kind}{place}."
    kind = {
        FOUND_IN_ARTICLE: "in un altro articolo dello stesso atto",
        FOUND_IN_PARAGRAPH: "in un altro paragrafo dello stesso articolo",
    }.get(str(where), "in un altro atto")
    return f"La citazione [{label}] non è verificata: il testo citato si trova {kind}{place}."


def _caveat_list(result: dict[str, Any]) -> list[Any]:
    caveats = result.get("caveats")
    if isinstance(caveats, str):
        return [caveats] if caveats.strip() else []
    return list(caveats) if isinstance(caveats, list) else []


def apply_unverified_policy(
    result: Any, *, mode: str = POLICY_FLAG, language: str | None = None
) -> Any:
    """Apply the unverified-citation policy; idempotent, safe on cached answers.

    Always makes sure ``verified_citations`` / ``citations_total`` are present
    (computed from the ``verified`` flags when an answer predates them). On an
    answer that is not an error nor an abstention:

    - an answer with no citation at all gets ``requires_expert_review = True``
      and the caveat that says so, under either policy (nothing to verify: it
      is not turned into an abstention);
    - each citation whose wording was found in another act, article or
      paragraph (``found_elsewhere``) gets a caveat that names it and where
      the wording is, and the answer ``requires_expert_review = True``;
    - when none of its citations is verified, ``flag`` also caps the
      confidence at 0.6 and adds the unverified caveat (the "elsewhere"
      variant when some quote was found elsewhere); ``strict`` turns the
      answer into an abstention with ``abstention_reason =
      "unverified_citations"``: the text says why, citations and caveats are
      emptied, the counters keep how many citations were rejected.

    The caveats are in Italian, or English when ``language`` is English; the
    ones this policy added in the other language are removed.
    """
    if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
        return result
    verified, total = citation_counters(result)
    result["verified_citations"] = verified
    result["citations_total"] = total
    english = _is_english(language)

    if result.get("abstention_reason"):
        # Already an abstention. Our own one is re-worded in the request language.
        twins = _ABSTENTION_TWINS.get(str(result.get("answer")))
        if result.get("abstention_reason") == UNVERIFIED_ABSTENTION_REASON and twins:
            result["answer"] = twins[1] if english else twins[0]
        return result
    if total == 0:
        result["requires_expert_review"] = True
        twins = (NO_CITATIONS_CAVEAT_IT, NO_CITATIONS_CAVEAT_EN)
        kept = [c for c in _caveat_list(result) if c not in twins]
        result["caveats"] = [*kept, twins[1] if english else twins[0]]
        return result
    elsewhere = _elsewhere(result)
    unverified = verified == 0
    if not (elsewhere or unverified):
        return result

    result["requires_expert_review"] = True
    if unverified:
        _cap_confidence(result)
        if mode == POLICY_STRICT:
            twins = (
                (UNVERIFIED_ELSEWHERE_ABSTENTION_IT, UNVERIFIED_ELSEWHERE_ABSTENTION_EN)
                if elsewhere
                else (UNVERIFIED_ABSTENTION_IT, UNVERIFIED_ABSTENTION_EN)
            )
            result["answer"] = twins[1] if english else twins[0]
            result["citations"] = []
            result["caveats"] = []
            result["abstention_reason"] = UNVERIFIED_ABSTENTION_REASON
            return result

    added = [_elsewhere_caveat(c, english) for c in elsewhere]
    if unverified:
        if elsewhere:
            added.append(
                UNVERIFIED_ELSEWHERE_CAVEAT_EN if english else UNVERIFIED_ELSEWHERE_CAVEAT_IT
            )
        else:
            added.append(UNVERIFIED_CAVEAT_EN if english else UNVERIFIED_CAVEAT_IT)
    ours = {
        UNVERIFIED_CAVEAT_IT,
        UNVERIFIED_CAVEAT_EN,
        UNVERIFIED_ELSEWHERE_CAVEAT_IT,
        UNVERIFIED_ELSEWHERE_CAVEAT_EN,
        *(_elsewhere_caveat(c, lang) for c in elsewhere for lang in (False, True)),
    }
    kept = [c for c in _caveat_list(result) if c not in ours]
    result["caveats"] = [*kept, *added]
    return result
