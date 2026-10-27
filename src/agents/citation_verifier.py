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
4. Within a level the quote must be a substring of one chunk (``"exact"``). A
   quote with omissions (``[...]``, ``...``, ``…``) is split there and every
   segment of at least 12 characters must appear in the same chunk, in order.
   Failing that, a tolerant comparison accepts a span of the chunk whose
   difflib ratio with the quote is at least 0.92 (``"fuzzy"``: punctuation or
   OCR differences).

``annotate_citations`` writes the result on COPIES of the citations and adds
the ``verified_citations`` / ``citations_total`` counters;
``apply_unverified_policy`` decides what happens to an answer whose citations
were all left unverified (``flag`` or ``strict``, see ``src.config``).
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import asdict, dataclass, fields
from difflib import SequenceMatcher
from typing import Any

from src.crawler.eurlex import celex as celex_utils

# ─── Thresholds and vocabularies ─────────────────────────────────────

MIN_QUOTE_CHARS = 20
MIN_QUOTE_WORDS = 4
MIN_SEGMENT_CHARS = 12
FUZZY_MIN_RATIO = 0.92

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
    # ESRS Set 1 (Delegated Regulation 2023/2772) is seeded under CSRD.
    "ESRS": "CSRD",
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
    i = 0
    while i < n:
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


def normalize_framework(name: Any) -> str:
    """Canonical framework key: ``"AI Act"`` -> ``"AI_ACT"``, ``"nis 2"`` -> ``"NIS2"``.

    A CELEX number is mapped to its base act (``02024R1689-20260727`` ->
    ``32024R1689``); an unknown name is returned in the same upper-case,
    underscore-joined form, so it still matches a chunk with the same key.
    """
    raw = str(name or "").strip()
    if not raw:
        return ""
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


def _prepare(chunks: Any) -> list[_Chunk]:
    prepared: list[_Chunk] = []
    for chunk in chunks or []:
        data = chunk if isinstance(chunk, dict) else {"text": str(chunk)}
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
    """The parts of a normalized quote that must be found, in order."""
    parts = _OMISSION_RE.split(quote)
    if len(parts) == 1:
        return [quote] if quote else []
    return [p for p in (_strip_edges(part) for part in parts) if len(p) >= MIN_SEGMENT_CHARS]


def _specific_enough(segments: list[str]) -> bool:
    content = " ".join(segments)
    return len(content) >= MIN_QUOTE_CHARS and len(content.split()) >= MIN_QUOTE_WORDS


def _find_in_order(segments: list[str], text: str) -> list[tuple[int, int]] | None:
    """Spans of every segment, each after the previous one (greedy is optimal)."""
    spans: list[tuple[int, int]] = []
    pos = 0
    for seg in segments:
        k = text.find(seg, pos)
        if k < 0:
            return None
        spans.append((k, k + len(seg)))
        pos = k + len(seg)
    return spans


def _gram_size(length: int) -> int:
    return 8 if length >= 32 else max(4, length // 4)


def _fuzzy_span(needle: str, text: str, start: int = 0) -> tuple[int, int, float] | None:
    """Best span of ``text[start:]`` whose difflib ratio with ``needle`` is >= 0.92.

    Comparing every window of the needle's length is quadratic, so the windows
    worth comparing are located first: each k-gram of the needle that occurs in
    the text votes for the offset where the needle would start, and only the
    best-supported offsets (at least a quarter of the k-grams, at most three
    places) are aligned with difflib. A near-copy with a few scattered
    differences (punctuation, a mistyped letter) keeps most k-grams intact and
    collects the votes; a paraphrase or a fabricated quote does not.
    """
    length = len(needle)
    if length < MIN_SEGMENT_CHARS or len(text) - start < length * FUZZY_MIN_RATIO:
        return None
    gram = _gram_size(length)
    stride = max(1, gram // 2)
    votes: dict[int, int] = {}
    n_grams = 0
    for i in range(0, length - gram + 1, stride):
        n_grams += 1
        piece = needle[i : i + gram]
        k = text.find(piece, start)
        while k != -1:
            votes[k - i] = votes.get(k - i, 0) + 1
            k = text.find(piece, k + 1)
    if not votes:
        return None

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
        if support[offset] < needed or len(centers) == 3:
            break
        if all(abs(offset - c) > width for c in centers):
            centers.append(offset)

    best: tuple[int, int, float] | None = None
    for center in centers:
        r_start = max(start, center - width)
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
        if ratio >= FUZZY_MIN_RATIO and (best is None or ratio > best[2]):
            best = (s, e, ratio)
    return best


def _find_tolerant(segments: list[str], text: str) -> tuple[list[tuple[int, int]], float] | None:
    """Like _find_in_order, but a segment may also match fuzzily (lowest ratio returned)."""
    spans: list[tuple[int, int]] = []
    pos = 0
    worst = 1.0
    for seg in segments:
        k = text.find(seg, pos)
        if k >= 0:
            spans.append((k, k + len(seg)))
            pos = k + len(seg)
            continue
        found = _fuzzy_span(seg, text, pos)
        if found is None:
            return None
        s, e, ratio = found
        spans.append((s, e))
        pos = e
        worst = min(worst, ratio)
    return spans, worst


def _search(
    segments: list[str], candidates: list[_Chunk]
) -> tuple[_Chunk, list[tuple[int, int]], str] | None:
    for chunk in candidates:
        spans = _find_in_order(segments, chunk.norm)
        if spans:
            return chunk, spans, MATCH_EXACT
    best: tuple[_Chunk, list[tuple[int, int]], float] | None = None
    for chunk in candidates:
        found = _find_tolerant(segments, chunk.norm)
        if found and (best is None or found[1] > best[2]):
            best = (chunk, found[0], found[1])
    if best is not None:
        return best[0], best[1], MATCH_FUZZY
    return None


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


def _result(
    chunk: _Chunk, spans: list[tuple[int, int]], match: str, level: str
) -> VerificationResult:
    pieces = [chunk.text[chunk.starts[a] : chunk.ends[b - 1]].strip() for a, b in spans]
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


def _verify(citation: Any, chunks: list[_Chunk]) -> VerificationResult:
    if not isinstance(citation, dict) or not chunks:
        return _UNVERIFIED
    segments = _segments(normalize(_quote_of(citation)))
    if not segments or not _specific_enough(segments):
        return _UNVERIFIED

    framework = normalize_framework(citation.get("framework"))
    article = parse_article(_reference_of(citation))
    levels: list[tuple[str, list[_Chunk]]] = []
    if framework:
        of_framework = [
            c for c in chunks if framework in c.frameworks or (c.celex and framework == c.celex)
        ]
        if article:
            levels.append(
                (LEVEL_ARTICLE, [c for c in of_framework if same_article(c.article_key, article)])
            )
        levels.append((LEVEL_FRAMEWORK, of_framework))
    levels.append((LEVEL_ANY, chunks))

    searched: set[int] = set()
    for level, candidates in levels:
        fresh = [c for c in candidates if id(c) not in searched]
        searched.update(id(c) for c in fresh)
        if not fresh:
            continue
        found = _search(segments, fresh)
        if found is not None:
            chunk, spans, match = found
            return _result(chunk, spans, match, level)
    return _UNVERIFIED


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


def annotate_citations(result: dict[str, Any], chunks: list[Any] | None) -> dict[str, Any]:
    """Write the verification fields on COPIES of the citations, plus the counters.

    The citation dicts may be shared (e.g. with the SNC samples), so they are
    never modified in place. Non-dict citations are kept as they are and count
    as unverified. Sets ``verified_citations`` and ``citations_total``.
    """
    citations = result.get("citations")
    items = citations if isinstance(citations, list) else []
    outcomes = verify_citations(items, chunks or [])
    if isinstance(citations, list):
        result["citations"] = [
            {**cit, **outcome.as_fields()} if isinstance(cit, dict) else cit
            for cit, outcome in zip(items, outcomes, strict=True)
        ]
    result["verified_citations"] = sum(1 for outcome in outcomes if outcome.verified)
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


def apply_unverified_policy(
    result: Any, *, mode: str = POLICY_FLAG, language: str | None = None
) -> Any:
    """Apply the unverified-citation policy; idempotent, safe on cached answers.

    Always makes sure ``verified_citations`` / ``citations_total`` are present
    (computed from the ``verified`` flags when an answer predates them). When
    the answer is not an error nor an abstention and none of its citations is
    verified:

    - ``flag``: ``requires_expert_review = True``, confidence capped at 0.6 and
      the caveat added to ``caveats`` (Italian, or English when ``language``
      is English; the other twin is removed);
    - ``strict``: the answer becomes an abstention with ``abstention_reason =
      "unverified_citations"``: the text says why, citations and caveats are
      emptied, the counters keep how many citations were rejected.
    """
    if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
        return result
    verified, total = citation_counters(result)
    result["verified_citations"] = verified
    result["citations_total"] = total
    english = _is_english(language)

    if result.get("abstention_reason"):
        # Already an abstention. Our own one is re-worded in the request language.
        if result.get("abstention_reason") == UNVERIFIED_ABSTENTION_REASON and result.get(
            "answer"
        ) in (UNVERIFIED_ABSTENTION_IT, UNVERIFIED_ABSTENTION_EN):
            result["answer"] = UNVERIFIED_ABSTENTION_EN if english else UNVERIFIED_ABSTENTION_IT
        return result
    if total == 0 or verified > 0:
        return result

    result["requires_expert_review"] = True
    _cap_confidence(result)
    if mode == POLICY_STRICT:
        result["answer"] = UNVERIFIED_ABSTENTION_EN if english else UNVERIFIED_ABSTENTION_IT
        result["citations"] = []
        result["caveats"] = []
        result["abstention_reason"] = UNVERIFIED_ABSTENTION_REASON
        return result

    caveats = result.get("caveats")
    if isinstance(caveats, str):
        caveats = [caveats] if caveats.strip() else []
    elif not isinstance(caveats, list):
        caveats = []
    kept = [c for c in caveats if c not in (UNVERIFIED_CAVEAT_IT, UNVERIFIED_CAVEAT_EN)]
    result["caveats"] = [*kept, UNVERIFIED_CAVEAT_EN if english else UNVERIFIED_CAVEAT_IT]
    return result
