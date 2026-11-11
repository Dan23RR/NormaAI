"""Italian acts, article by article, from the Normattiva open data API, cached on disk.

Normattiva (Istituto Poligrafico e Zecca dello Stato) publishes Italian
legislation "in multivigenza": every article keeps each wording it has had,
with the days between which that wording was in force. Since 2026 its open
data API serves one article per request, addressed by URN:NIR, as it was in
force on a given day:

    POST {API_BASE}/bff-opendata/v1/api/v1/atto/dettaglio-atto-urn
    {"urn": "urn:nir:stato:decreto.legislativo:2003;196~art2ter!vig=2026-11-11"}

(specification: https://dati.normattiva.it/assets/come_fare_per/API_Normattiva_OpenData.pdf,
revision 10 of 10 March 2026; no key; licence CC BY 4.0). The answer is the
article as HTML plus the first and last day of that wording
(``articoloDataInizioVigenza`` / ``articoloDataFineVigenza``).

This is why Italian law is read through an article-level interface
(``ItalianTextSource``) and not through the ``versions`` / ``articles`` pair of
``official.TextSource``: an Italian act has no list of consolidated versions,
each article has its own timeline, and a whole code is far too large to
download in order to check one article.

What the API does, as observed on 11 November 2026:

- Without ``!vig=`` it answers with the LAST wording, which may not be in force
  yet (art. 51 of d.P.R. 917/1986 came back as repealed from 1 January 2027).
  The text in force on a day is always asked with ``!vig=<day>``.
- A suffix it does not know is dropped in silence: ``~art24xyz`` answers with
  art. 24. The article that comes back is therefore compared with the one asked.
- An article that never existed: HTTP 404. An act it cannot resolve: HTTP 400
  (code 1003) or 404 "atto non trovato". A repealed article: HTTP 200 with
  "ARTICOLO ABROGATO DAL ..." in place of the text. An article not yet in force
  on the day asked: HTTP 200 with "NON ANCORA ESISTENTE O VIGENTE".
- A very long article (art. 1 of a budget law) is served in parts of 100 commi
  and only the first part can be asked by URN.
- Rulings of the Constitutional Court do not change the text: they are in the
  "AGGIORNAMENTO" notes under the article, which are kept apart from the text.

Normattiva's texts are not official: the Gazzetta Ufficiale prevails, and the
report says so.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import httpx
from bs4 import BeautifulSoup
from bs4.element import Comment, NavigableString, Tag

from src.document_check.extract import latin_ordinal
from src.document_check.official import ArticleText, TextUnavailableError, Version

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

API_BASE = "https://api.normattiva.it/t/normattiva.api"
ARTICLE_ENDPOINT = "/bff-opendata/v1/api/v1/atto/dettaglio-atto-urn"
SITE_RESOLVER = "https://www.normattiva.it/uri-res/N2Ls?"
USER_AGENT = "NormaAI/0.1 (document check)"

IN_FORCE = "vigente"
REPEALED = "abrogato"
NOT_IN_FORCE = "non_vigente"  # asked for a day on which the article was not in force yet

# Long articles come in parts of this many commi; only the first can be asked.
PART_SIZE = 100


class ActNotFoundError(LookupError):
    """Normattiva does not have an act with this type, year and number."""


class ArticleNotFoundError(LookupError):
    """The act is on Normattiva, the article is not (and never was)."""


# ─── URNs ────────────────────────────────────────────────────────────

_ARTICLE_KEY_RE = re.compile(r"^art:(\d{1,4})([a-z]*)$")
# The URN of an annex of an act ends with its number: "...:1942-03-16;262:2".
_ANNEX_RE = re.compile(r";\d+:\d+$")
# The same inserted article is written in more than one way: Normattiva labels
# as "2-quindecies" the article the law calls "2-quinquiesdecies".
_SUFFIX_FORMS: dict[int, tuple[str, ...]] = {
    9: ("novies", "nonies"),
    15: ("quinquiesdecies", "quindecies"),
    16: ("sexiesdecies", "sedecies"),
    18: ("octiesdecies", "duodevicies"),
    19: ("noviesdecies", "undevicies"),
}


def article_tokens(key: str) -> list[str]:
    """URN tokens to try for an article key: "art:2ter" gives ["art2ter"].

    More than one when the suffix has two spellings. Empty for a key that is
    not an article of an Italian act (a recital, an annex, "art:19a").
    """
    m = _ARTICLE_KEY_RE.match(key)
    if not m:
        return []
    number, suffix = m.group(1), m.group(2)
    if not suffix:
        return [f"art{number}"]
    ordinal = latin_ordinal(suffix)
    if ordinal is None:
        return []
    forms = [suffix, *(f for f in _SUFFIX_FORMS.get(ordinal, ()) if f != suffix)]
    return [f"art{number}{form}" for form in forms]


def article_url(act_urn: str, key: str, on: str | None = None, original: bool = False) -> str:
    """Page of an article on normattiva.it, as in force on ``on`` (or as first published)."""
    tokens = article_tokens(key)
    urn = f"{act_urn}~{tokens[0]}" if tokens else act_urn
    if original:
        urn += "@originale"
    elif on:
        urn += f"!vig={on}"
    return SITE_RESOLVER + urn


def _iso(value: Any) -> str | None:
    """ "20211208" gives "2021-12-08"; "0" and "99999999" (no limit) give None."""
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{8}", text) or text == "99999999":
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:])).isoformat()
    except ValueError:
        return None


def _italian_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


# ─── What a reading gives ────────────────────────────────────────────


@dataclass(frozen=True)
class ItalianVersion(Version):
    """One wording of one article: ``celex`` and ``as_of`` hold the day it was read for."""

    urn: str = ""  # the act
    key: str = ""  # the article, "art:2ter"
    start: str | None = None  # first day in force (ISO); None when Normattiva gives none
    end: str | None = None  # last day in force (ISO); None while no end is set
    current: bool = False  # read as the text in force on the day of the check
    original: bool = False  # the article as first published

    @property
    def label(self) -> str:
        if self.original:
            return "testo originale"
        if self.current and self.as_of:
            return f"testo vigente al {_italian_date(self.as_of)}"
        if self.start and self.end:
            return f"testo in vigore dal {_italian_date(self.start)} al {_italian_date(self.end)}"
        if self.end:
            return f"testo in vigore fino al {_italian_date(self.end)}"
        if self.start:
            return f"testo in vigore dal {_italian_date(self.start)}"
        return f"testo vigente al {_italian_date(self.as_of)}" if self.as_of else "testo vigente"

    def url(self, lang: str = "IT") -> str:
        return article_url(self.urn, self.key, self.as_of, self.original)


@dataclass(frozen=True)
class ItalianArticle:
    """One article of an Italian act as Normattiva gave it for one day."""

    urn: str  # the act: "urn:nir:stato:decreto.legislativo:2003;196"
    key: str  # "art:2ter"
    label: str  # "Art. 2-ter"
    text: str  # label, heading and commi, one per line, without editorial marks
    commi: tuple[str, ...]  # "1", "1bis", "2"; counted when the commi carry no number
    numbered: bool  # the commi carry their number in the text
    state: str  # IN_FORCE | REPEALED | NOT_IN_FORCE
    asked: str  # the day asked for (ISO); "" for the original text
    start: str | None = None
    end: str | None = None
    original: bool = False
    act_title: str = ""  # "DECRETO LEGISLATIVO 30 giugno 2003, n. 196"
    act_subject: str = ""  # what the act is about, as Normattiva titles it
    act_date: str | None = None  # ISO date of the act
    notes: str = ""  # Normattiva's update notes under the article (not part of the text)
    partial: bool = False  # only the first PART_SIZE commi of a longer article
    read_on: str = ""  # ISO day the API gave this answer
    stale: bool = False  # the API did not answer: an older answer from the cache
    comma_texts: dict[str, str] = field(default_factory=dict, compare=False, hash=False)

    @property
    def article(self) -> ArticleText:
        return ArticleText(self.key, self.label, self.text, self.commi)

    def version(self, current: bool = False) -> ItalianVersion:
        day = self.asked or None
        return ItalianVersion(
            celex=day or "originale",
            as_of=day,
            urn=self.urn,
            key=self.key,
            start=self.start,
            end=self.end,
            current=current,
            original=self.original,
        )

    @property
    def repeal_note(self) -> str:
        """ "ARTICOLO ABROGATO DAL D.LGS. 10 AGOSTO 2018, N. 101" for a repealed article."""
        return " ".join(self.text.split("\n")[1:]).strip().rstrip(".")


class ItalianTextSource(Protocol):
    """Where ``check`` reads Italian articles (Normattiva, or a fake in tests).

    Both methods raise ActNotFoundError, ArticleNotFoundError or
    TextUnavailableError.
    """

    def article(self, act_urn: str, key: str, on: str) -> ItalianArticle: ...

    def original(self, act_urn: str, key: str) -> ItalianArticle: ...


# ─── From the API's HTML to the text of an article ───────────────────

_BLOCK_TAGS = frozenset("div p h1 h2 h3 h4 h5 li ul ol table tr section article".split())
_NOTE_BLOCKS = ("art_aggiornamento-akn", "note-akn")
_HEADING_BLOCKS = ("article-heading-akn", "article-pre-comma-text-akn")
_LABEL_RE = re.compile(
    r"^art(?:icolo)?\.?\s*(\d{1,4})(?:\s*[-\s]\s*([a-z]+(?:\s+[a-z]+)?))?\s*\.?$", re.IGNORECASE
)
# "((49))": a pointer to an update note. "((...))": words removed by the last amendment.
_NOTE_POINTER_RE = re.compile(r"\(\(\s*\d{1,4}\s*\)\)")
_OMISSION_RE = re.compile(r"\(\(\s*\.{3}\s*\)\)")
_LONE_POINTERS_RE = re.compile(r"^(?:\(\s*\d{1,4}\s*\)\s*)+$")
_EDITORIAL_WORD_RE = re.compile(r"ABROGAT|SOPPRESS")
_LIST_ITEM_RE = re.compile(
    r"^(?:\(?\d{1,3}(?:[-\s]?[a-z]+)?[).°]|[a-z]{1,2}(?:[-\s][a-z]+)?\)|-\s)"
)
_LATIN_WORDS = r"[a-z]+(?:\s(?:semel|bis|ter|quater|quinquies|sexies|septies|octies|novies))?"
_COMMA_NUMBER = rf"(\d{{1,4}}(?:\.\d{{1,2}})?)(?:\s?-\s?({_LATIN_WORDS}))?"
_COMMA_START_RE = re.compile(rf"^{_COMMA_NUMBER}\.(?:\s|$)")
_COMMA_MARK_RE = re.compile(rf"^{_COMMA_NUMBER}\.?$")
_MARKER_RE = re.compile(
    r"^(\d{1,4}(?:\.\d{1,2})?(?:\s?-\s?[a-z]+)?\.\s+|[a-z0-9]{1,3}(?:-[a-z]+)?\)\s+)"
)
_PLACEHOLDER = "NON ANCORA ESISTENTE O VIGENTE"


def _has_lowercase(text: str) -> bool:
    return any(ch.islower() for ch in text)


def _has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _raw_lines(node: Tag) -> list[str]:
    """The text under ``node``, one string per line of the page.

    Lines break at <br> and around block elements; the line breaks of the HTML
    source are only spaces. Normattiva marks changed words with
    ``<div class="ins-akn">``, a block element used in the middle of a
    sentence: it is read as inline.
    """
    parts: list[str] = []

    def walk(parent: Tag) -> None:
        for child in parent.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                parts.append(re.sub(r"\s+", " ", str(child)))
            elif isinstance(child, Tag):
                name = child.name.lower()
                if name == "br":
                    parts.append("\n")
                elif name in ("script", "style"):
                    continue
                elif name in ("td", "th"):
                    walk(child)
                    parts.append(" ")
                else:
                    classes = child.get("class") or []
                    block = name in _BLOCK_TAGS and "ins-akn" not in classes
                    if block:
                        parts.append("\n")
                    walk(child)
                    if block:
                        parts.append("\n")

    walk(node)
    return "".join(parts).replace("\xa0", " ").split("\n")


def _drop_inline_editorial(line: str) -> str:
    """Remove an editorial note that sits inside a line of law.

    "PERIODO SOPPRESSO DAL D.L. 8 OTTOBRE 2021, N. 139" in the middle of a
    comma is Normattiva telling what is no longer there: it is not the law's
    wording and would break a quote that runs across it. A comma or a letter
    that holds nothing but such a note ("1. COMMA ABROGATO DAL ...") keeps it,
    it is all there is to read.
    """
    if not _EDITORIAL_WORD_RE.search(line):
        return line
    m = _MARKER_RE.match(line)
    marker, body = (m.group(1), line[m.end() :]) if m else ("", line)
    tokens = body.split(" ")
    keep = [True] * len(tokens)
    i = 0
    while i < len(tokens):
        if not _EDITORIAL_WORD_RE.search(tokens[i]) or _has_lowercase(tokens[i]):
            i += 1
            continue
        first = last = i
        while first > 0 and not _has_lowercase(tokens[first - 1]):
            first -= 1
        while last + 1 < len(tokens) and not _has_lowercase(tokens[last + 1]):
            last += 1
        # The note starts at a word: a number or a full stop before it is the law's.
        while first < i and not _has_letters(tokens[first]):
            first += 1
        for j in range(first, last + 1):
            keep[j] = False
        i = last + 1
    rest = " ".join(t for t, k in zip(tokens, keep, strict=True) if k)
    return marker + rest if _has_letters(rest) else line


def _clean_line(line: str, pointers: frozenset[str] = frozenset()) -> str:
    """One line of law without Normattiva's editorial marks.

    ``pointers`` are the numbers of the update notes under the article: "(119)"
    in the text points to "AGGIORNAMENTO (119)" and is not the law's.
    """
    line = _NOTE_POINTER_RE.sub(" ", line)
    line = _OMISSION_RE.sub(" ", line)
    line = line.replace("((", " ").replace("))", " ")
    if pointers:
        line = re.sub(
            r"\(\s*(\d{1,4})\s*\)", lambda m: " " if m.group(1) in pointers else m.group(0), line
        )
    line = re.sub(r"\s+", " ", line).strip()
    if _LONE_POINTERS_RE.match(line) or not any(ch.isalnum() for ch in line):
        return ""
    line = _drop_inline_editorial(line)
    line = re.sub(r"\s+([.,;:])", r"\1", line)
    line = re.sub(r"\(\s+", "(", line)
    line = re.sub(r"\s+\)", ")", line)
    line = re.sub(r"(?<!\.)\.\.(?!\.)", ".", line)
    return line.strip()


def _lines(node: Tag, pointers: frozenset[str] = frozenset()) -> list[str]:
    return [line for line in (_clean_line(raw, pointers) for raw in _raw_lines(node)) if line]


def _comma_id(number: str, suffix: str | None) -> str:
    return number + re.sub(r"[\s-]", "", (suffix or "").lower())


def _base(comma: str) -> str:
    """The number a comma hangs from: "1bis" and "1" give "1", "3.2" gives "3"."""
    m = re.match(r"\d+", comma)
    return m.group(0) if m else ""


def _label_parts(label: str) -> tuple[str, str] | None:
    """ "Art. 2-ter" gives ("2", "ter"); None when the text is not an article heading."""
    m = _LABEL_RE.match(label.strip())
    if not m:
        return None
    return m.group(1), re.sub(r"\s+", "", (m.group(2) or "").lower())


def _same_parts(a: tuple[str, str] | None, b: tuple[str, str] | None) -> bool:
    """Two (number, suffix) pairs for one article: "quindecies" is "quinquiesdecies"."""
    if a is None or b is None or int(a[0]) != int(b[0]):
        return False
    if a[1] == b[1]:
        return True
    first, second = latin_ordinal(a[1]), latin_ordinal(b[1])
    return bool(a[1] and b[1]) and first is not None and first == second


def same_article_number(key: str, label: str) -> bool:
    """True when ``label`` ("Art. 2-quindecies") names the article of ``key``."""
    asked = _ARTICLE_KEY_RE.match(key)
    if asked is None:
        return False
    return _same_parts((asked.group(1), asked.group(2)), _label_parts(label))


@dataclass
class ParsedArticle:
    """What one API answer says about an article."""

    label: str  # "Art. 2-ter"; "" when the answer has no recognisable heading
    lines: list[str]  # heading and commi, without the label
    commi: tuple[str, ...]
    numbered: bool
    comma_texts: dict[str, str]
    state: str
    notes: str
    partial: bool


def parse_article_html(html: str) -> ParsedArticle:
    """Label, text lines, commi and state of the article in an API answer."""
    soup = BeautifulSoup(html or "", "html.parser")
    found = soup.find(class_="bodyTesto")
    body: Tag = found if isinstance(found, Tag) else soup
    notes: list[str] = []
    pointers: set[str] = set()
    for block in body.find_all(class_=list(_NOTE_BLOCKS)):
        note = " ".join(_lines(block))
        notes.append(note)
        pointers.update(re.findall(r"AGGIORNAMENTO \((\d{1,4})\)", note))
        block.decompose()
    marked = frozenset(pointers)
    repealed_mark = body.find(class_="art_abrogato-akn") is not None
    marks = [
        re.sub(r"\s+", " ", span.get_text()).strip()
        for span in body.find_all(class_="comma-num-akn")
    ]

    label = ""
    heading_lines: list[str] = []
    number = body.find(class_="article-num-akn")
    if isinstance(number, Tag):
        label = re.sub(r"\s+", " ", number.get_text()).strip()
        # What comes before the number is the preamble of the act (article 1 only).
        node: Tag | None = number
        while node is not None and node is not body:
            for sibling in list(node.previous_siblings):
                sibling.extract()
            node = node.parent
        number.decompose()
        for block in body.find_all(class_=list(_HEADING_BLOCKS)):
            heading_lines.extend(_lines(block, marked))
            block.decompose()
        lines = _lines(body, marked)
    else:
        # An article of an annex (the codes): the text opens with "Art. 2043."
        lines = _lines(body, marked)
        if lines and _label_parts(lines[0]) is not None:
            label, lines = lines[0], lines[1:]
    parts = _label_parts(label)
    if parts is not None:
        label = f"Art. {parts[0]}" + (f"-{parts[1]}" if parts[1] else "")
        # The article's own number inside the text: what precedes it is the
        # preamble of the act, given as plain text with some first articles
        # (a repealed article just repeats its number there).
        own = [i for i, line in enumerate(lines) if _same_parts(_label_parts(line), parts)]
        if own:
            lines = lines[own[-1] + 1 :]

    text = " ".join(lines)
    if _PLACEHOLDER in text:
        state = NOT_IN_FORCE
    elif repealed_mark or (bool(lines) and not _has_lowercase(text) and "ABROGAT" in text):
        state = REPEALED
    else:
        state = IN_FORCE

    starts: list[tuple[int, str]] = []
    numbered = False
    if state == IN_FORCE:
        starts = _numbered_commi(lines, marks)
        numbered = bool(starts)
        if numbered:
            # Lines before the first comma are the heading of the article.
            first = starts[0][0]
            heading_lines, lines = [*heading_lines, *lines[:first]], lines[first:]
            starts = [(index - first, comma) for index, comma in starts]
        else:
            if (
                not heading_lines
                and len(lines) > 1
                and lines[0].startswith("(")
                and lines[0].rstrip(".").endswith(")")
            ):
                heading_lines, lines = [lines[0]], lines[1:]  # the heading of a code article
            starts = _counted_commi(lines)
    comma_texts: dict[str, str] = {}
    for position, (index, comma) in enumerate(starts):
        stop = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        comma_texts.setdefault(comma, "\n".join(lines[index:stop]))
    plain = [int(comma) for comma in comma_texts if comma.isdigit()]
    return ParsedArticle(
        label=label,
        lines=[*heading_lines, *lines],
        commi=tuple(comma_texts),
        numbered=numbered,
        comma_texts=comma_texts,
        state=state,
        notes="\n".join(n for n in notes if n),
        partial=numbered
        and bool(plain)
        and max(plain) >= PART_SIZE
        and max(plain) % PART_SIZE == 0,
    )


def _numbered_commi(lines: list[str], marks: list[str]) -> list[tuple[int, str]]:
    """Line and id of each comma of an article whose commi carry a number.

    Normattiva marks the number of a comma; a comma inserted later ("1-bis.",
    "3.1.") may have it only in the text, right after the comma it follows. A
    line that merely starts with a number, inside a quoted amendment
    ("516. Le amministrazioni ..."), is neither. Where nothing is marked (an
    article given as plain text) the numbers count when they run 1, 2, 3.
    Empty when the commi carry no number.
    """
    pending: list[str] = []
    for mark in marks:
        m = _COMMA_MARK_RE.match(mark)
        if m:
            pending.append(_comma_id(m.group(1), m.group(2)))
    marked = set(pending)
    starts: list[tuple[int, str]] = []
    last = ""
    for index, line in enumerate(lines):
        m = _COMMA_START_RE.match(line)
        if not m:
            continue
        comma = _comma_id(m.group(1), m.group(2))
        if comma in pending:
            del pending[: pending.index(comma) + 1]
        elif comma in marked:
            continue
        elif comma.isdigit():
            if marked or int(comma) != (int(_base(last)) + 1 if last else 1):
                continue
        elif not last or _base(comma) != _base(last):
            continue
        starts.append((index, comma))
        last = comma
    return starts


def _counted_commi(lines: list[str]) -> list[tuple[int, str]]:
    """Commi without numbers: every paragraph that is not an item of a list is one."""
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if starts and _LIST_ITEM_RE.match(line):
            continue
        starts.append((index, str(len(starts) + 1)))
    return starts


# ─── HTTP client ─────────────────────────────────────────────────────


class NormattivaClient:
    """The one call the document check needs: an article by URN.

    One request at a time, a pause between requests, a couple of retries on a
    network error or a 5xx, a timeout on every call.
    """

    def __init__(
        self,
        base_url: str = API_BASE,
        timeout: float = 20.0,
        retries: int = 2,
        delay: float = 0.4,
        http: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.retries = retries
        self.delay = delay
        self._http = http or httpx.Client(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        self._last = 0.0
        self.requests = 0

    def close(self) -> None:
        self._http.close()

    def _pause(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def article(self, urn: str) -> dict[str, Any]:
        """The API's ``atto`` object for an article URN (with ``!vig=`` or ``@originale``)."""
        url = self.base_url + ARTICLE_ENDPOINT
        problem = "nessuna risposta"
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(self.delay * 2 * attempt)
            self._pause()
            self.requests += 1
            try:
                response = self._http.post(url, json={"urn": urn})
            except httpx.HTTPError as e:
                problem = f"errore di rete ({type(e).__name__})"
                continue
            if response.status_code == 429 or response.status_code >= 500:
                problem = f"HTTP {response.status_code}"
                continue
            return self._read(urn, response)
        raise TextUnavailableError(f"Normattiva non ha risposto per {urn}: {problem}")

    @staticmethod
    def _read(urn: str, response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
        if response.status_code == 400:
            raise ActNotFoundError(message or "atto non trovato")
        if response.status_code == 404:
            if "atto non trovato" in message.lower():
                raise ActNotFoundError(message)
            raise ArticleNotFoundError(message or "articolo non trovato")
        if response.status_code != 200 or not isinstance(payload, dict):
            raise TextUnavailableError(
                f"risposta inattesa di Normattiva per {urn}: HTTP {response.status_code}"
            )
        data = payload.get("data")
        act = data.get("atto") if isinstance(data, dict) else None
        if isinstance(act, dict) and act.get("articoloHtml"):
            return act
        candidates = data.get("lista") if isinstance(data, dict) else None
        if isinstance(candidates, list) and candidates:
            return _one_act(urn, [c for c in candidates if isinstance(c, dict)])
        raise TextUnavailableError(f"risposta di Normattiva senza testo per {urn}")


def _one_act(urn: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """The act among several answers, when they are one act published twice.

    The specification shows a law and its republication with notes in a later
    Gazzetta: same type, date and number. The first publication carries the
    text that is kept up to date. Different acts are never chosen between.
    """
    titles = {str(c.get("titolo") or "") for c in candidates}
    if len(titles) != 1 or not all(c.get("articoloHtml") for c in candidates):
        names = "; ".join(sorted(t for t in titles if t)) or "più atti"
        raise TextUnavailableError(f"Normattiva dà più atti per {urn}: {names}")

    def published(c: dict[str, Any]) -> tuple[int, int, int]:
        return (int(c.get("annoGU") or 0), int(c.get("meseGU") or 0), int(c.get("giornoGU") or 0))

    return min(candidates, key=published)


# ─── Text source with a cache ────────────────────────────────────────


def _plain(fragment: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(fragment or "", "html.parser").get_text()).strip()


def _now() -> str:
    return datetime.now(UTC).isoformat()


class NormattivaTextSource:
    """Italian articles from Normattiva, with an on-disk cache.

    One JSON file per article holds the answers already received, each with
    the days between which that wording is in force. A day inside a wording
    that has ended is served from the cache for a month; a wording that is
    still in force is asked again after a day, so an amendment is seen the
    next day. When the API does not answer, an older answer is used and marked
    ``stale``: the report says which day it is from.
    """

    OPEN_TTL = timedelta(days=1)
    CLOSED_TTL = timedelta(days=30)
    MISSING_TTL = timedelta(days=1)

    def __init__(self, cache_dir: Path, client: NormattivaClient | None = None) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = client or NormattivaClient()
        self._files: dict[str, dict[str, Any]] = {}
        self._no_act: dict[str, str] = {}

    # The cache ----------------------------------------------------------

    def _path(self, act_urn: str, key: str) -> Path:
        name = re.sub(r"[^a-z0-9.]+", "_", f"{act_urn.removeprefix('urn:nir:')}_{key}".lower())
        return self.cache_dir / f"{name.strip('_')}.json"

    def _load(self, act_urn: str, key: str) -> dict[str, Any]:
        path = self._path(act_urn, key)
        memo = self._files.get(path.name)
        if memo is not None:
            return memo
        data: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, dict):
                data = loaded
        data.setdefault("urn", act_urn)
        data.setdefault("key", key)
        if not isinstance(data.get("answers"), list):
            data["answers"] = []
        self._files[path.name] = data
        return data

    def _save(self, act_urn: str, key: str) -> None:
        path = self._path(act_urn, key)
        try:
            path.write_text(
                json.dumps(self._files[path.name], ensure_ascii=False), encoding="utf-8"
            )
        except OSError:
            pass  # a cache that cannot be written only costs a request next time

    @staticmethod
    def _age(entry: dict[str, Any]) -> timedelta:
        try:
            fetched = datetime.fromisoformat(str(entry.get("fetched_at")))
        except ValueError:
            return timedelta.max
        return datetime.now(UTC) - fetched

    @staticmethod
    def _covering(answers: list[dict[str, Any]], on: str) -> Iterator[dict[str, Any]]:
        """Cached answers whose wording is in force on ``on``, newest answer first."""
        for entry in sorted(answers, key=lambda e: str(e.get("fetched_at")), reverse=True):
            act = entry.get("atto") or {}
            start = _iso(act.get("articoloDataInizioVigenza"))
            end = _iso(act.get("articoloDataFineVigenza"))
            if (start is None or start <= on) and (end is None or on <= end):
                yield entry

    def _fresh(self, entry: dict[str, Any]) -> bool:
        end = _iso((entry.get("atto") or {}).get("articoloDataFineVigenza"))
        closed = end is not None and end < date.today().isoformat()
        return self._age(entry) < (self.CLOSED_TTL if closed else self.OPEN_TTL)

    def _remember_missing(self, act_urn: str, key: str, slot: str, error: LookupError) -> None:
        self._load(act_urn, key)[slot] = {
            "fetched_at": _now(),
            "message": str(error),
            "act": isinstance(error, ActNotFoundError),
        }
        self._save(act_urn, key)

    def _raise_if_missing(self, data: dict[str, Any], slot: str) -> None:
        marked = data.get(slot)
        if isinstance(marked, dict) and self._age(marked) < self.MISSING_TTL:
            if marked.get("act"):
                raise ActNotFoundError(str(marked.get("message") or ""))
            raise ArticleNotFoundError(str(marked.get("message") or ""))

    # Asking -------------------------------------------------------------

    def _ask(self, act_urn: str, key: str, qualifier: str) -> dict[str, Any]:
        """The API's answer for the article, with the URN that gave it under "urn".

        An act that approves a text keeps that text in an annex (the 1942 law on
        bankruptcy is annex 1 of royal decree 267): an article the act itself
        does not have is looked for in its first two annexes before it is said
        not to exist.
        """
        if act_urn in self._no_act:
            raise ActNotFoundError(self._no_act[act_urn])
        try:
            return {**self._ask_in(act_urn, key, qualifier), "urn": act_urn}
        except ActNotFoundError as e:
            self._no_act[act_urn] = str(e)
            raise
        except ArticleNotFoundError:
            if _ANNEX_RE.search(act_urn):
                raise
            for annex in ("1", "2"):
                try:
                    found = self._ask_in(f"{act_urn}:{annex}", key, qualifier)
                except (ActNotFoundError, ArticleNotFoundError):
                    continue
                return {**found, "urn": f"{act_urn}:{annex}"}
            raise

    def _ask_in(self, act_urn: str, key: str, qualifier: str) -> dict[str, Any]:
        """The answer for an article of this very URN, checked to be the article asked for."""
        tokens = article_tokens(key)
        if not tokens:
            raise ArticleNotFoundError(f"{key} non è un articolo di un atto italiano")
        error: LookupError | None = None
        for token in tokens:
            try:
                act = self._client.article(f"{act_urn}~{token}{qualifier}")
            except ArticleNotFoundError as e:
                error = e
                continue
            label = parse_article_html(str(act.get("articoloHtml") or "")).label
            if same_article_number(key, label) or (not label and key == "art:1"):
                return act
            if not label:
                raise TextUnavailableError(
                    f"non riconosco l'articolo nella risposta di Normattiva per {act_urn}~{token}"
                )
            # A suffix the API does not know is dropped: it answered with another article.
            error = ArticleNotFoundError(f"Normattiva ha risposto con {label}")
        raise error or ArticleNotFoundError(key)

    def article(self, act_urn: str, key: str, on: str) -> ItalianArticle:
        """The article as in force on ``on`` (ISO day)."""
        data = self._load(act_urn, key)
        for entry in self._covering(data["answers"], on):
            if self._fresh(entry):
                return self._build(act_urn, key, entry, on)
        self._raise_if_missing(data, "missing")
        try:
            act = self._ask(act_urn, key, f"!vig={on}")
        except (ActNotFoundError, ArticleNotFoundError) as e:
            self._remember_missing(act_urn, key, "missing", e)
            raise
        except TextUnavailableError:
            older = next(self._covering(data["answers"], on), None)
            if older is None:
                raise
            # An old answer speaks for the day it was given, not for today.
            read_on = str(older.get("fetched_at") or "")[:10]
            asked = read_on if read_on and read_on < on else on
            return replace(self._build(act_urn, key, older, asked), stale=True)
        entry = {"fetched_at": _now(), "atto": act}
        start = act.get("articoloDataInizioVigenza")
        data["answers"] = [
            e
            for e in data["answers"]
            if (e.get("atto") or {}).get("articoloDataInizioVigenza") != start
        ]
        data["answers"].append(entry)
        data.pop("missing", None)
        self._save(act_urn, key)
        return self._build(act_urn, key, entry, on)

    def original(self, act_urn: str, key: str) -> ItalianArticle:
        """The article as first published; ArticleNotFoundError when it was inserted later."""
        data = self._load(act_urn, key)
        entry = data.get("original")
        if isinstance(entry, dict) and self._age(entry) < self.CLOSED_TTL:
            return self._build(act_urn, key, entry, "", original=True)
        self._raise_if_missing(data, "original_missing")
        try:
            act = self._ask(act_urn, key, "@originale")
        except (ActNotFoundError, ArticleNotFoundError) as e:
            self._remember_missing(act_urn, key, "original_missing", e)
            raise
        except TextUnavailableError:
            if isinstance(entry, dict):
                return replace(self._build(act_urn, key, entry, "", original=True), stale=True)
            raise
        entry = {"fetched_at": _now(), "atto": act}
        data["original"] = entry
        self._save(act_urn, key)
        return self._build(act_urn, key, entry, "", original=True)

    @staticmethod
    def _build(
        act_urn: str, key: str, entry: dict[str, Any], asked: str, original: bool = False
    ) -> ItalianArticle:
        act = entry.get("atto") or {}
        parsed = parse_article_html(str(act.get("articoloHtml") or ""))
        label = parsed.label or "Art. " + key.partition(":")[2]
        act_date: str | None
        try:
            act_date = date(
                int(act.get("annoProvvedimento") or 0),
                int(act.get("meseProvvedimento") or 0),
                int(act.get("giornoProvvedimento") or 0),
            ).isoformat()
        except (TypeError, ValueError):
            act_date = None
        subject = re.sub(
            r"\s*\(\d{2,3}[A-Z]\d{4,5}\)\s*$", "", _plain(str(act.get("sottoTitolo") or ""))
        )
        return ItalianArticle(
            urn=str(act.get("urn") or act_urn),
            key=key,
            label=label,
            text="\n".join([label, *parsed.lines]),
            commi=parsed.commi,
            numbered=parsed.numbered,
            state=parsed.state,
            asked=asked,
            start=_iso(act.get("articoloDataInizioVigenza")),
            end=_iso(act.get("articoloDataFineVigenza")),
            original=original,
            act_title=re.sub(r"\s+", " ", str(act.get("titolo") or "")).strip(),
            act_subject=subject,
            act_date=act_date,
            notes=parsed.notes,
            partial=parsed.partial,
            read_on=str(entry.get("fetched_at") or "")[:10],
            comma_texts=parsed.comma_texts,
        )
