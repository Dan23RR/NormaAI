"""
Legal Document Chunker - structural chunking of EU legal acts.

EU legislation follows a strict hierarchy:
  Act -> Preamble (citations + recitals) -> Enacting terms (Part / Title /
  Chapter / Section / Article / Paragraph / Point) -> Annexes

This chunker turns EUR-Lex HTML (the CELLAR XHTML "oj-*" markup as well as the
flatter legal-content HTML, Normattiva pages and markdown wrapped in a single
``<p>``) into retrieval units that follow that hierarchy:

- the preamble (title + citations) is one ``preamble`` chunk
- every recital is its own ``recital N`` chunk, never mixed with articles
- every article is one chunk (``Art. 5``) with its title in the metadata;
  a long article is split at paragraph boundaries and each part keeps the
  heading plus the paragraph numbers it covers
- annexes are chunked per ``Annex I`` / section (``Section A. ...``) unit
- numbered paragraphs and points keep their number glued to their own text
  (``1. The purpose...``, ``(a) remote biometric...``) even when EUR-Lex puts
  the number in a separate table cell
- text is linearised with a space between inline elements and a newline
  between blocks, so words are never glued across tags

Every chunk carries the same metadata keys (see ``_chunk_metadata``), including
``celex``, ``eli``, ``lang``, ``article``, ``paragraph``, ``title``,
``framework``, ``url``, ``consolidated_as_of`` and ``chunk_index`` - the
indexer derives its deterministic point id from them.
"""

from __future__ import annotations

import logging
import re
import warnings
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Comment, NavigableString, Tag, XMLParsedAsHTMLWarning

from src.crawler.eurlex import celex as celex_utils

# CELLAR serves XHTML; we parse it with the lxml HTML parser on purpose (it
# handles both CELLAR XHTML and the legal-content HTML). Silence the noisy
# "looks like an XML document" advisory so seed logs stay readable.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger(__name__)


@dataclass
class LegalChunk:
    """A semantically meaningful chunk of EU legal text."""

    text: str
    metadata: dict = field(default_factory=dict)

    # Metadata fields (every chunk has all of them):
    # - celex: str - CELEX of the act (original id, even when a consolidated text was used)
    # - source_celex: str - the id actually downloaded (consolidated id or the CELEX)
    # - eli: str | None - ELI URI (point-in-time form for consolidated texts)
    # - lang: str - "EN" / "IT"
    # - article: str - "Art. 29", "Recital 45", "Annex I", "Preamble" or ""
    # - paragraph: str | None - numbered paragraph(s) covered when an article is split ("2", "3-4")
    # - title: str | None - article / annex title
    # - framework: str - CSRD, CSDDD, AI_ACT, etc.
    # - url: str | None - EUR-Lex TXT page in the chunk's language
    # - consolidated_as_of: str | None - ISO date of the consolidated text
    # - chunk_index: int - position of the chunk in the document
    # - chunk_type: str - preamble, recital, article, annex, paragraph
    # - article_number / section_title / hierarchy / part / char_count - legacy fields


# ─── Text patterns ─────────────────────────────────────────────────

_ARTICLE_WORDS = r"(?:Article|Articolo|Artikel|Art\.)"
_ARTICLE_NUM = (
    r"(?P<num>\d{1,4})"
    r"(?:\s?(?P<suffix>bis|ter|quater|quinquies|sexies|septies|octies|novies|decies|[a-z]))?"
)
_ARTICLE_HEADING_RE = re.compile(
    rf"^{_ARTICLE_WORDS}\s*{_ARTICLE_NUM}\b\s*(?:[-–—:.]\s*)?(?P<title>.*)$"
)
_RECITAL_RE = re.compile(r"^\((\d{1,3})\)\s+\S")
_PARAGRAPH_RE = re.compile(r"^(\d{1,3})\.\s+\S")
_POINT_RE = re.compile(r"^\(([a-z]{1,2}|[ivxlc]{1,6}|\d{1,3})\)\s+\S")
# A line that is ONLY a paragraph/point marker (EUR-Lex puts markers in their
# own table cell): "1.", "(a)", "(i)", "1.1.", "a)", dashes and bullets.
_MARKER_ONLY_RE = re.compile(
    r"^(?:\((?:\d{1,3}|[a-z]{1,2}|[ivxlc]{1,6})\)|\d{1,3}(?:\.\d{1,3})*\.|[a-z]\)|[ivxlc]{1,6}\)"
    r"|[-–—•●▪■□])$"
)
_SECTION_RE = re.compile(
    r"^(?:CHAPTER|TITLE|SECTION|PART|CAPO|TITOLO|SEZIONE|PARTE|KAPITEL|TITEL|ABSCHNITT|TEIL"
    r"|CHAPITRE|TITRE|PARTIE)\s+(?:[IVXLCDM]+|\d+)[A-Za-z]?\b",
    re.IGNORECASE,
)
_ANNEX_RE = re.compile(
    r"^(?:ANNEX|ALLEGATO|ANHANG|ANNEXE)(?:\s+(?P<num>[IVXLCDM]+|\d+|[A-Z]))?\s*[.:]?$"
)
_ANNEX_SECTION_RE = re.compile(
    r"^(?:Section|Part|Sezione|Parte|Chapter|Capo|SECTION|PART|CHAPTER)\s+[A-Z0-9IVXL]{1,4}\b"
)
_ENACTING_RE = re.compile(
    r"^(?:(?:HAVE|HAS|HANNO|HA)\s+(?:ADOPTED|ADOTTATO)\b|(?:ONT|A)\s+ADOPTÉ|"
    r"(?:HABEN|HAT)\s+FOLGENDE)",
    re.IGNORECASE,
)
_WHEREAS_RE = re.compile(
    r"^(?:Whereas|considerando quanto segue|in Erwägung nachstehender Gründe|"
    r"considérant ce qui suit)\s*:?$",
    re.IGNORECASE,
)
_SENTENCE_PUNCT_RE = re.compile(r"[.;:]")
_OPENING_QUOTES = "‘“'\"«"

# ─── HTML traversal ────────────────────────────────────────────────

_SKIP_TAGS = frozenset(
    {
        "script",
        "style",
        "nav",
        "header",
        "footer",
        "noscript",
        "img",
        "br",
        "hr",
        "col",
        "colgroup",
        "head",
        "title",
        "meta",
        "link",
    }
)
_BLOCK_TAGS = frozenset(
    {
        "p",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ul",
        "ol",
        "table",
        "thead",
        "tbody",
        "tfoot",
        "tr",
        "td",
        "th",
        "section",
        "article",
        "blockquote",
        "pre",
        "dl",
        "dt",
        "dd",
        "main",
        "aside",
        "center",
        "figure",
        "figcaption",
        "caption",
        "body",
        "html",
    }
)
_BLOCK_TAG_LIST = sorted(_BLOCK_TAGS - {"body", "html"})
# OJ page header, footnotes, the closing formula ("Done at ...") and the
# signature block carry no retrievable law.
_SKIP_CLASS_RE = re.compile(r"(?:^|\s)(?:oj-)?(?:hd-[\w-]+|note|footnote|signatory|final)(?:\s|$)")
# Trailing OJ boilerplate lines after the last annex.
_BOILERPLATE_LINE_RE = re.compile(r"^(?:ELI:\s*https?://|ISSN\s+\d{4}-\d{3}[\dXx]\b)")
_HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4"})


@dataclass
class _Line:
    text: str
    classes: str = ""  # lower-cased class attribute of the originating element
    tag: str = ""


@dataclass
class _Unit:
    kind: str  # preamble | recital | article | annex | paragraph
    article: str  # "Art. 5" | "Recital 12" | "Annex I" | "Preamble" | ""
    title: str | None = None
    section: str = ""
    hierarchy: str = ""
    heading: list[str] = field(default_factory=list)  # repeated on every part
    body: list[str] = field(default_factory=list)

    @property
    def body_length(self) -> int:
        return sum(len(line) for line in self.body)


def _classes_of(el: Tag) -> str:
    raw = el.get("class") or []
    if isinstance(raw, str):
        raw = raw.split()
    return " ".join(raw).lower()


def _clean(text: str) -> str:
    """Normalise whitespace and the spacing artefacts of inline-tag joining."""
    t = text.replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r" ?\n ?", "\n", t)
    t = re.sub(r"\s+([,.;:)\]])", r"\1", t)  # "Council ( 4 ) ," -> "Council (4),"
    t = re.sub(r"([(\[])\s+", r"\1", t)
    return t.strip()


def _is_mostly_upper(text: str, threshold: float = 0.8) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= threshold


def _starts_with_marker(text: str) -> bool:
    return bool(_PARAGRAPH_RE.match(text) or _POINT_RE.match(text) or _MARKER_ONLY_RE.match(text))


class EURLexHTMLChunker:
    """
    Chunk EUR-Lex HTML into semantically meaningful pieces.

    Strategy:
    - Linearise the HTML into text lines (one per block / table row), merging
      marker-only cells ("(a)", "1.") into the text they number.
    - Walk the lines with a small state machine (preamble -> recitals ->
      enacting terms -> annexes) that produces one unit per recital, article
      and annex section.
    - Emit one chunk per unit; split units longer than MAX_CHUNK_SIZE at
      paragraph boundaries (each part repeats the heading and records the
      paragraph numbers it covers).
    - Fall back to plain paragraph packing when no structure is recognised
      (uploaded documents).
    """

    MAX_CHUNK_SIZE = 2000
    MIN_CHUNK_SIZE = 100  # fallback paragraph chunks only
    MIN_UNIT_SIZE = 20  # articles / annex sections with less body text than this are noise
    # Annex "sections" with less body text than this are table and glossary rows
    # whose acronym or code was read as a heading ("ODS", "ESRS S2", "AIH 0101").
    # As chunks of 50-200 characters they crowd real articles out of the search
    # results, so they are merged into the neighbouring section of the same annex.
    TINY_ANNEX_SECTION = 120
    DEFAULT_LANG = "EN"

    def __init__(
        self,
        celex: str,
        framework: str,
        lang: str = DEFAULT_LANG,
        source_celex: str | None = None,
        eli_type: str | None = None,
        title: str | None = None,
    ):
        """
        Args:
            celex: identifier of the act. A CELLAR consolidated id
                (``02022L2464-20260318``) is accepted and normalised: ``celex``
                becomes the original act (``32022L2464``) and the given id is
                kept as ``source_celex``. Non-CELEX ids (Normattiva URNs,
                ``DOC_...`` uploads) pass through untouched.
            framework: framework key (CSRD, AI_ACT, ...).
            lang: ISO 639-1 language of the text ("EN", "IT").
            source_celex: the id actually downloaded, when different from
                ``celex`` (the consolidated version).
            eli_type: ELI resource type (``reg_del`` for a delegated
                regulation); inferred from the CELEX when omitted.
            title: title of the act (stored as ``act_title``).
        """
        self.celex = celex_utils.base_celex(celex)
        self.source_celex = source_celex or celex
        self.framework = framework
        self.lang = celex_utils.normalize_lang(lang, self.DEFAULT_LANG)
        self.act_title = title
        self.eli = celex_utils.celex_to_eli(self.source_celex, eli_type)
        self.url = celex_utils.eurlex_txt_url(self.source_celex, self.lang)
        self.consolidated_as_of = celex_utils.consolidated_as_of(self.source_celex)

    # ─── Public API ────────────────────────────────────────────

    def chunk_html(self, html: str) -> list[LegalChunk]:
        """Parse EUR-Lex HTML and return structured chunks in document order."""
        with warnings.catch_warnings():
            # The module-level filter is reset by test runners' warning capture;
            # silence the XHTML advisory at the call site too.
            warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(html or "", "lxml")
        lines = self._linearize(soup)
        units, structured = self._build_units(lines)

        chunks: list[LegalChunk] = []
        if structured:
            units = self._merge_tiny_annex_units(units)
            for unit in units:
                chunks.extend(self._unit_to_chunks(unit))
        else:
            if lines:
                logger.warning(
                    f"No structured content found for {self.celex}, using fallback chunking"
                )
            chunks = self._fallback_paragraph_chunking(lines)

        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
            chunk.metadata["char_count"] = len(chunk.text)

        logger.info(f"Chunked {self.celex} [{self.lang}]: {len(chunks)} chunks created")
        return chunks

    # ─── Linearisation ─────────────────────────────────────────

    def _linearize(self, soup: BeautifulSoup) -> list[_Line]:
        """Flatten the DOM into text lines: one per block element / table row.

        Inline elements are joined with a space (no glued words), blocks become
        separate lines, two-cell layout rows (marker | text) become one line
        and real data rows become ``cell | cell | cell``.
        """
        raw: list[_Line] = []
        root = soup.body if soup.body is not None else soup
        self._walk(root, raw)

        lines: list[_Line] = []
        for line in raw:
            for piece in line.text.split("\n"):
                text = _clean(piece)
                if text and not _BOILERPLATE_LINE_RE.match(text):
                    lines.append(_Line(text, line.classes, line.tag))
        return self._merge_bare_markers(lines)

    def _walk(self, el: Tag, out: list[_Line]) -> None:
        buffer: list[str] = []

        def flush() -> None:
            if buffer:
                out.append(_Line(" ".join(buffer), _classes_of(el), el.name or ""))
                buffer.clear()

        for child in el.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                text = str(child)
                if "\n\n" in text:
                    # Markdown-ish text node: blank lines separate paragraphs,
                    # single newlines are soft wraps.
                    text = re.sub(r"\n[ \t]*\n+", "\n", text)
                    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
                else:
                    text = re.sub(r"\s+", " ", text)
                if text.strip():
                    buffer.append(text.strip())
                continue
            if not isinstance(child, Tag):
                continue
            if child.name in _SKIP_TAGS or _SKIP_CLASS_RE.search(_classes_of(child)):
                continue
            if child.name in _BLOCK_TAGS:
                flush()
                if child.name == "tr":
                    self._emit_row(child, out)
                elif self._has_block_child(child):
                    self._walk(child, out)
                else:
                    text = child.get_text(" ", strip=True)
                    if text:
                        out.append(_Line(text, _classes_of(child), child.name))
            else:
                text = child.get_text(" ", strip=True)
                if text:
                    buffer.append(text)
        flush()

    @staticmethod
    def _has_block_child(el: Tag) -> bool:
        return el.find(_BLOCK_TAG_LIST) is not None

    def _emit_row(self, tr: Tag, out: list[_Line]) -> None:
        cells = [c for c in tr.children if isinstance(c, Tag) and c.name in ("td", "th")]
        if any(self._has_block_child(c) for c in cells):
            # Layout row with nested blocks (points containing sub-points):
            # simple cells become lines (markers are merged afterwards), complex
            # cells are walked recursively.
            for cell in cells:
                if self._has_block_child(cell):
                    self._walk(cell, out)
                else:
                    text = cell.get_text(" ", strip=True)
                    if text:
                        out.append(_Line(text, _classes_of(cell), cell.name))
            return

        texts = [_clean(c.get_text(" ", strip=True)) for c in cells]
        non_empty = [t for t in texts if t]
        if not non_empty:
            return
        if len(non_empty) == 1:
            out.append(_Line(non_empty[0], _classes_of(tr), "tr"))
        elif len(non_empty) == 2 and _MARKER_ONLY_RE.match(non_empty[0]):
            out.append(_Line(f"{non_empty[0]} {non_empty[1]}", _classes_of(tr), "tr"))
        else:
            out.append(_Line(" | ".join(non_empty), _classes_of(tr), "tr-data"))

    @staticmethod
    def _merge_bare_markers(lines: list[_Line]) -> list[_Line]:
        """Glue marker-only lines ("1.", "(a)") to the text line that follows."""
        merged: list[_Line] = []
        pending: list[str] = []
        for line in lines:
            if _MARKER_ONLY_RE.match(line.text):
                pending.append(line.text)
                continue
            if pending:
                line = _Line(" ".join(pending) + " " + line.text, line.classes, line.tag)
                pending = []
            merged.append(line)
        return merged

    # ─── Structure detection ───────────────────────────────────

    @staticmethod
    def _article_heading(line: _Line) -> tuple[str, str | None] | None:
        """(number, inline title) when the line is an article heading, else None."""
        text, classes = line.text, line.classes
        by_class = "ti-art" in classes and "sti-art" not in classes
        m = _ARTICLE_HEADING_RE.match(text)
        if m is None:
            return ("?", text) if by_class else None
        number = m.group("num")
        suffix = m.group("suffix") or ""
        number = f"{number}{suffix}" if len(suffix) == 1 else f"{number} {suffix}".strip()
        title = (m.group("title") or "").strip()
        if not title:
            return number, None
        if by_class:
            return number, title
        if len(text) > 160 or len(title) > 120:
            return None
        if title[0] not in _OPENING_QUOTES and not title[0].isupper():
            return None  # "Article 5 shall apply" - a cross-reference, not a heading
        if title[0] == "(":
            return None  # "Article 5(2) of ..." - a cross-reference
        if ";" in title or ":" in title or ". " in title or title.endswith("."):
            return None
        return number, title

    @staticmethod
    def _looks_like_article_title(line: _Line) -> bool:
        text, classes = line.text, line.classes
        if "sti-art" in classes:
            return True
        if any(k in classes for k in ("ti-art", "ti-section", "grseq", "doc-ti")):
            return False
        if len(text) > 120 or _starts_with_marker(text):
            return False
        if _SENTENCE_PUNCT_RE.search(text):
            return False
        return text[0].isupper() or text[0] in _OPENING_QUOTES

    @staticmethod
    def _section_heading(line: _Line) -> bool:
        text, classes = line.text, line.classes
        if "ti-section-1" in classes:
            return True
        if "ti-section" in classes and "ti-section-2" not in classes:
            return bool(_SECTION_RE.match(text))
        if line.tag in _HEADING_TAGS:
            return True
        return bool(_SECTION_RE.match(text)) and len(text) <= 60

    @staticmethod
    def _looks_like_section_title(line: _Line) -> bool:
        text, classes = line.text, line.classes
        if "ti-section" in classes or "grseq" in classes:
            return True
        if len(text) > 100 or _starts_with_marker(text):
            return False
        if _SENTENCE_PUNCT_RE.search(text):
            return False
        return _is_mostly_upper(text) or text[0].isupper()

    @staticmethod
    def _annex_heading(line: _Line) -> str | None:
        """Annex number ("I", "A", "" for an unnumbered annex) or None."""
        text, classes = line.text, line.classes
        if len(text) > 20:
            return None
        m = _ANNEX_RE.match(text)
        if m:
            return m.group("num") or ""
        if "doc-ti" in classes:
            m = re.match(r"^(?:Annex|Allegato)(?:\s+([IVXLCDM]+|\d+|[A-Z]))?\s*$", text)
            if m:
                return m.group(1) or ""
        return None

    @staticmethod
    def _looks_like_annex_title(line: _Line) -> bool:
        text, classes = line.text, line.classes
        if "doc-ti" in classes:
            return True
        if len(text) > 160 or _starts_with_marker(text):
            return False
        if ";" in text or text.endswith(".") or ". " in text:
            return False
        return text[0].isupper() or text[0] in _OPENING_QUOTES

    @staticmethod
    def _annex_section_heading(line: _Line) -> bool:
        text, classes = line.text, line.classes
        if "grseq" in classes or "ti-section" in classes:
            return True
        if _starts_with_marker(text):
            return False
        if _ANNEX_SECTION_RE.match(text) and len(text) <= 160:
            return True
        return 3 <= len(text) <= 120 and _is_mostly_upper(text) and not re.search(r"[.;]", text)

    # ─── Unit construction ─────────────────────────────────────

    def _build_units(self, lines: list[_Line]) -> tuple[list[_Unit], bool]:
        """Walk the lines and return (units, structured)."""
        units: list[_Unit] = []
        preamble = _Unit("preamble", "Preamble", section="Preamble", hierarchy="Preamble")
        state = "preamble"
        current: _Unit | None = None
        section_heading = ""
        pending_section_title = False
        expect_article_title = False
        annex_label = ""
        annex_title: str | None = None
        expect_annex_title = False

        def close() -> None:
            nonlocal current
            if current is None:
                return
            if current.kind == "recital":
                keep = bool(current.body)
            else:
                keep = current.body_length >= self.MIN_UNIT_SIZE
            if keep:
                units.append(current)
            current = None

        def annex_heading_lines() -> list[str]:
            return [f"{annex_label} - {annex_title}" if annex_title else annex_label]

        for line in lines:
            text = line.text

            # Annex headings start a new annex in every state.
            annex_num = self._annex_heading(line)
            if annex_num is not None:
                close()
                state = "annexes"
                annex_label = f"Annex {annex_num}".strip()
                annex_title = None
                expect_annex_title = True
                current = _Unit("annex", annex_label, hierarchy=annex_label, heading=[annex_label])
                continue

            if state == "annexes":
                assert current is not None
                if expect_annex_title:
                    expect_annex_title = False
                    if self._looks_like_annex_title(line):
                        annex_title = text
                        current.title = text
                        current.heading = annex_heading_lines()
                        continue
                if self._annex_section_heading(line):
                    close()
                    current = _Unit(
                        "annex",
                        annex_label,
                        title=annex_title,
                        section=text,
                        hierarchy=f"{annex_label} > {text}",
                        heading=annex_heading_lines() + [text],
                    )
                    continue
                current.body.append(text)
                continue

            art = self._article_heading(line)
            if art is not None:
                number, inline_title = art
                close()
                state = "articles"
                label = f"Art. {number}"
                current = _Unit(
                    "article",
                    label,
                    title=inline_title,
                    section=section_heading,
                    hierarchy=f"{section_heading} > {label}" if section_heading else label,
                    heading=[text],
                )
                expect_article_title = inline_title is None
                pending_section_title = False
                continue

            if state == "articles":
                if expect_article_title:
                    expect_article_title = False
                    if current is not None and self._looks_like_article_title(line):
                        current.title = text
                        current.heading.append(text)
                        continue
                if self._section_heading(line):
                    close()
                    section_heading = text
                    pending_section_title = True
                    continue
                if pending_section_title and self._looks_like_section_title(line):
                    section_heading = f"{section_heading} - {text}"
                    pending_section_title = False
                    continue
                pending_section_title = False
                if current is not None:
                    current.body.append(text)
                continue

            # preamble / recitals
            if _ENACTING_RE.match(text):
                close()
                state = "articles"
                continue
            recital = _RECITAL_RE.match(text)
            if recital:
                close()
                state = "recitals"
                label = f"Recital {recital.group(1)}"
                current = _Unit(
                    "recital",
                    label,
                    section="Preamble",
                    hierarchy=f"Preamble > {label}",
                    body=[text],
                )
                continue
            if _WHEREAS_RE.match(text):
                state = "recitals"
                continue
            if state == "recitals":
                if current is not None:
                    current.body.append(text)
                continue
            if self._section_heading(line):
                # A chapter heading before any article: enacting terms without recitals.
                state = "articles"
                section_heading = text
                pending_section_title = True
                continue
            preamble.body.append(text)

        close()

        structured = any(u.kind in ("recital", "article", "annex") for u in units)
        if structured and preamble.body_length >= self.MIN_CHUNK_SIZE:
            units.insert(0, preamble)
        return units, structured

    # ─── Chunk emission ────────────────────────────────────────

    def _chunk_metadata(self, unit: _Unit, paragraph: str | None, part: int | None) -> dict:
        meta = {
            "celex": self.celex,
            "source_celex": self.source_celex,
            "eli": self.eli,
            "lang": self.lang,
            "article": unit.article,
            "paragraph": paragraph,
            "title": unit.title,
            "framework": self.framework,
            "url": self.url,
            "consolidated_as_of": self.consolidated_as_of,
            "chunk_index": None,  # assigned once all chunks are known
            "chunk_type": unit.kind,
            "article_number": unit.article,
            "section_title": unit.section,
            "hierarchy": unit.hierarchy,
            "act_title": self.act_title,
        }
        if part is not None:
            meta["part"] = str(part)
        return meta

    @staticmethod
    def _unit_text_length(unit: _Unit) -> int:
        return sum(len(line) + 1 for line in unit.heading) + sum(
            len(line) + 1 for line in unit.body
        )

    def _merge_tiny_annex_units(self, units: list[_Unit]) -> list[_Unit]:
        """Merge annex sections below TINY_ANNEX_SECTION into their neighbours.

        Only consecutive sections of the same annex are merged, and only while
        the merged text still fits one chunk. The merged unit loses its single
        section title (it now spans several); every merged section keeps its
        title as a body line, so the text still says where each part sits.
        """
        merged: list[_Unit] = []
        for unit in units:
            prev = merged[-1] if merged else None
            if (
                prev is not None
                and prev.kind == "annex"
                and unit.kind == "annex"
                and prev.article == unit.article
                and min(prev.body_length, unit.body_length) < self.TINY_ANNEX_SECTION
            ):
                extra = ([unit.section] if unit.section else []) + unit.body
                added = sum(len(line) + 1 for line in extra)
                if self._unit_text_length(prev) + added <= self.MAX_CHUNK_SIZE:
                    if prev.section:
                        if prev.heading and prev.heading[-1] == prev.section:
                            prev.heading = prev.heading[:-1]
                        prev.body.insert(0, prev.section)
                        prev.section = ""
                        prev.hierarchy = prev.article
                    prev.body.extend(extra)
                    continue
            merged.append(unit)
        return merged

    def _unit_to_chunks(self, unit: _Unit) -> list[LegalChunk]:
        heading = "\n".join(unit.heading)
        body = "\n".join(unit.body)
        full = f"{heading}\n{body}".strip() if heading else body.strip()
        if len(full) <= self.MAX_CHUNK_SIZE:
            return [LegalChunk(text=full, metadata=self._chunk_metadata(unit, None, None))]

        limit = max(self.MAX_CHUNK_SIZE - len(heading) - 1, self.MAX_CHUNK_SIZE // 2)
        parts: list[list[str]] = []
        current: list[str] = []
        current_len = 0
        for group in self._paragraph_groups(unit.body):
            group_len = sum(len(line) + 1 for line in group)
            if group_len > limit:
                if current:
                    parts.append(current)
                    current, current_len = [], 0
                parts.extend(self._split_lines(group, limit))
                continue
            if current and current_len + group_len > limit:
                parts.append(current)
                current, current_len = [], 0
            current.extend(group)
            current_len += group_len
        if current:
            parts.append(current)

        chunks: list[LegalChunk] = []
        carry: str | None = None
        for index, part_lines in enumerate(parts, start=1):
            numbers = [m.group(1) for m in map(_PARAGRAPH_RE.match, part_lines) if m]
            if numbers:
                paragraph = (
                    numbers[0] if numbers[0] == numbers[-1] else f"{numbers[0]}-{numbers[-1]}"
                )
                carry = numbers[-1]
            else:
                paragraph = carry
            body_text = "\n".join(part_lines)
            text = f"{heading}\n{body_text}".strip() if heading else body_text
            chunks.append(
                LegalChunk(text=text, metadata=self._chunk_metadata(unit, paragraph, index))
            )
        return chunks

    @staticmethod
    def _paragraph_groups(body: list[str]) -> list[list[str]]:
        """Group lines so that each numbered paragraph (with its points) stays together.

        A new group starts at every top-level numbered paragraph ("2. ...");
        lines before the first number form the first group. Without numbered
        paragraphs every line is its own group.
        """
        if not any(_PARAGRAPH_RE.match(line) for line in body):
            return [[line] for line in body]
        groups: list[list[str]] = []
        for line in body:
            if _PARAGRAPH_RE.match(line) or not groups:
                groups.append([line])
            else:
                groups[-1].append(line)
        return groups

    def _split_lines(self, lines: list[str], limit: int) -> list[list[str]]:
        """Pack lines into pieces of at most ``limit`` chars; hard-split oversize lines."""
        pieces: list[list[str]] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            if len(line) > limit:
                if current:
                    pieces.append(current)
                    current, current_len = [], 0
                pieces.extend([piece] for piece in self._hard_split(line, limit))
                continue
            if current and current_len + len(line) + 1 > limit:
                pieces.append(current)
                current, current_len = [], 0
            current.append(line)
            current_len += len(line) + 1
        if current:
            pieces.append(current)
        return pieces

    def _hard_split(self, text: str, limit: int | None = None) -> list[str]:
        """Hard-split a single long text block that has no paragraph breaks."""
        limit = limit or self.MAX_CHUNK_SIZE
        # Try splitting on sentence boundaries first
        sentences = re.split(r"(?<=[.;])\s+", text)
        parts = []
        current = ""
        for sent in sentences:
            if len(current) + len(sent) > limit and current:
                parts.append(current)
                current = sent
            else:
                current = (current + " " + sent).strip() if current else sent
        if current:
            # If a single segment still exceeds, split at word boundaries
            while len(current) > limit:
                split_at = current.rfind(" ", 0, limit)
                if split_at <= 0:
                    split_at = limit
                parts.append(current[:split_at])
                current = current[split_at:].lstrip()
            if current:
                parts.append(current)
        return parts

    def _fallback_paragraph_chunking(self, lines: list[_Line]) -> list[LegalChunk]:
        """Fallback: pack lines into paragraph chunks when structure is not recognised."""
        unit = _Unit("paragraph", "")
        texts = [line.text for line in lines if len(line.text) >= 20]
        chunks: list[LegalChunk] = []
        for piece in self._split_lines(texts, self.MAX_CHUNK_SIZE):
            text = "\n".join(piece).strip()
            if text:
                chunks.append(
                    LegalChunk(text=text, metadata=self._chunk_metadata(unit, None, None))
                )
        return chunks
