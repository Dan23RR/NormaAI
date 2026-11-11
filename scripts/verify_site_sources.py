"""Verify the legal sources the site cites against the official texts in force.

Usage (from the repository root, needs network access):

    python scripts/verify_site_sources.py
    python scripts/verify_site_sources.py --only ai-act-113-a dlgs-138-2024-7-1
    python scripts/verify_site_sources.py --date 2026-11-11 --strict

Reads the registry frontend/src/lib/verification/sources.json: one entry for
each provision an Ambito rule or a calendar deadline relies on, with the act
(CELEX for EU acts, URN:NIR for Italian acts), the article and paragraph, the
language and a short literal excerpt of the official text that carries the
date, the threshold or the duty. For each entry the script reads the official
text and checks the excerpt word for word with the production verifier
(src.agents.citation_verifier.verify_citation), then writes
frontend/src/lib/verification/sources.verified.json. The interface shows
"Verificata il <date>" only for the entries that file marks as verified.

Where the texts come from:

- EU acts: CELLAR (Publications Office), through
  src.document_check.official.CellarTextSource: the latest consolidated text
  not later than the check date, or the act as adopted. An act that CELLAR
  serves only in its older HTML format (a 2003 recommendation) is read in that
  format.
- Italian acts: the Normattiva open data API, one article by URN with the text
  in force on the check date. Editorial notes are left out and the marks of
  amended wording ("((" and "))") are removed; the table of an annex is also
  read column by column, top to bottom.
- Documents of an authority (ACN determinations): the PDF at the address on
  the authority's own site.

Outcome of an entry:

- verified: the excerpt is in the cited article, word for word;
- failed: the text was read and the excerpt is not there, or it is in another
  article or paragraph, or the article is not in force from the date the
  registry states;
- unreachable: the text could not be read now. An entry verified by an earlier
  run keeps that verification, with its date, as long as the entry itself has
  not changed.

Exit status: 1 when an entry failed; with --strict, 2 when an entry could not
be read and has no earlier verification; 0 otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.citation_verifier import parse_article, verify_citation  # noqa: E402
from src.crawler.eurlex import celex as celex_utils  # noqa: E402
from src.document_check.official import (  # noqa: E402
    CellarTextSource,
    TextUnavailableError,
)

VERIFICATION_DIR = ROOT / "frontend" / "src" / "lib" / "verification"
REGISTRY = VERIFICATION_DIR / "sources.json"
OUTPUT = VERIFICATION_DIR / "sources.verified.json"
DEFAULT_CACHE = Path.home() / ".cache" / "normaai" / "cellar"

USER_AGENT = "normaai-site-source-check"
NORMATTIVA_API = (
    "https://api.normattiva.it/t/normattiva.api/bff-opendata/v1/api/v1/atto/dettaglio-atto-urn"
)
CELLAR_RESOURCE = "http://publications.europa.eu/resource/celex/{celex}"
ISO639_3 = {"IT": "ita", "EN": "eng"}
# A "document" entry is read only from the site of the authority that issued it.
DOCUMENT_HOSTS = frozenset({"www.acn.gov.it"})
# An article, an act in HTML or a determination in PDF is far below this size.
MAX_BYTES = 25_000_000

KIND_EURLEX = "eurlex"
KIND_NORMATTIVA = "normattiva"
KIND_DOCUMENT = "document"
KINDS = (KIND_EURLEX, KIND_NORMATTIVA, KIND_DOCUMENT)

STATUS_VERIFIED = "verified"
STATUS_FAILED = "failed"
STATUS_UNREACHABLE = "unreachable"

# The verifier matches a citation to chunks by framework key: one neutral key
# for both sides, so an identifier is never mistaken for a framework name.
_FRAMEWORK = "SOURCE"
_NO_END = "99999999"


class UnreachableError(RuntimeError):
    """The official source did not answer (network, timeout, server error)."""


class NotFoundError(RuntimeError):
    """The official source answered and has no such text."""


# ─── Registry ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entry:
    """One provision the site relies on."""

    id: str
    kind: str
    act: str
    article: str
    paragraph: str
    lang: str
    excerpt: str
    annex: int | None = None
    url: str | None = None
    in_force_from: str | None = None

    @property
    def fingerprint(self) -> str:
        """Changes whenever what is checked changes: an old verification then no longer counts."""
        parts = [
            self.kind,
            self.act,
            self.article,
            self.paragraph,
            self.lang,
            self.excerpt,
            str(self.annex or ""),
            self.url or "",
            self.in_force_from or "",
        ]
        return "sha256:" + hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def load_registry(path: Path) -> list[Entry]:
    """The entries of the registry, validated; raises ValueError on a malformed one."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries: list[Entry] = []
    seen: set[str] = set()
    for item in raw.get("sources", []):
        entry = Entry(
            id=str(item.get("id") or "").strip(),
            kind=str(item.get("kind") or "").strip(),
            act=str(item.get("act") or "").strip(),
            article=str(item.get("article") or "").strip(),
            paragraph=str(item.get("paragraph") or "").strip(),
            lang=celex_utils.normalize_lang(item.get("lang"), "IT"),
            excerpt=str(item.get("excerpt") or "").strip(),
            annex=item.get("annex"),
            url=item.get("url"),
            in_force_from=item.get("in_force_from"),
        )
        problem = _entry_problem(entry)
        if problem:
            raise ValueError(f"{entry.id or '(senza id)'}: {problem}")
        if entry.id in seen:
            raise ValueError(f"{entry.id}: id ripetuto")
        seen.add(entry.id)
        entries.append(entry)
    return entries


def _entry_problem(entry: Entry) -> str | None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", entry.id):
        return "id mancante o non in minuscolo con trattini"
    if entry.kind not in KINDS:
        return f"kind deve essere uno di {', '.join(KINDS)}"
    if not entry.excerpt:
        return "excerpt mancante"
    if parse_article(entry.article) is None:
        return "article non riconosciuto (per esempio 'Art. 50', 'Allegato I')"
    if entry.kind == KIND_EURLEX and celex_utils.parse_celex(entry.act) is None:
        return "act deve essere un numero CELEX"
    if entry.kind == KIND_NORMATTIVA and not entry.act.startswith("urn:nir:"):
        return "act deve essere un URN:NIR"
    if entry.kind == KIND_DOCUMENT:
        if not entry.url or urlsplit(entry.url).scheme != "https":
            return "url https mancante"
        if urlsplit(entry.url).hostname not in DOCUMENT_HOSTS:
            return "url fuori dai siti delle autorità ammessi"
    if entry.in_force_from:
        if entry.kind != KIND_NORMATTIVA:
            return "in_force_from vale solo per gli atti letti su Normattiva"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.in_force_from):
            return "in_force_from deve essere AAAA-MM-GG"
    if entry.annex is not None and (
        entry.kind != KIND_NORMATTIVA or not str(entry.annex).isdigit()
    ):
        return "annex (numero dell'allegato) vale solo per gli atti letti su Normattiva"
    return None


# ─── Reading the official texts ──────────────────────────────────────


@dataclass(frozen=True)
class Reading:
    """The official text read for an entry, split by article."""

    version: str
    version_label: str
    articles: list[tuple[str, str]]  # (label, text): "Art. 50", "Annex III", "" for a preamble
    url: str | None = None
    consolidated_as_of: str | None = None
    in_force_from: str | None = None
    in_force_to: str | None = None


def http_request(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
    attempts: int = 4,
    pause: float = 3.0,
) -> bytes:
    """GET (or POST when ``data`` is given) with retries on timeouts and 5xx answers."""
    last = "nessun tentativo"
    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            data=data,
            method="POST" if data is not None else "GET",
            headers={"User-Agent": USER_AGENT, **(headers or {})},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise NotFoundError(f"risposta oltre {MAX_BYTES} byte: non è il testo atteso")
            return body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200].replace("\n", " ")
            if e.code < 500:
                raise NotFoundError(f"HTTP {e.code}: {body}") from e
            last = f"HTTP {e.code}: {body}"
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt + 1 < attempts:
            time.sleep(pause * (attempt + 1))
    raise UnreachableError(last)


_ARTICLE_HEADING = re.compile(r"(?im)^[ \t]*articolo[ \t]+(\d{1,4})[ \t]*$")


def split_articles(text: str) -> list[tuple[str, str]]:
    """A plain text cut at its "Articolo N" heading lines: [("Art. N", text), ...].

    What comes before the first heading is returned with an empty label. Used
    for the texts that do not come already split by article (a PDF, an old
    HTML act).
    """
    parts: list[tuple[str, str]] = []
    last = 0
    label = ""
    for match in _ARTICLE_HEADING.finditer(text):
        chunk = text[last : match.start()].strip()
        if chunk:
            parts.append((label, chunk))
        label = f"Art. {match.group(1)}"
        last = match.start()
    tail = text[last:].strip()
    if tail:
        parts.append((label, tail))
    return parts


_NEWLINE = chr(10)


class _HtmlText(HTMLParser):
    """Text of an HTML fragment: one line per block, inline tags dropped without a space.

    Elements whose class starts with one of ``skip_classes`` are left out with
    everything inside them. Inside elements whose class starts with one of
    ``mark_classes`` the Normattiva marks of amended wording, "((" and "))",
    are removed: they are editorial, not part of the provision.
    """

    _BLOCK = frozenset(
        {"div", "p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr", "table", "title"}
    )
    _VOID = frozenset({"br", "hr", "img", "input", "meta", "link", "col", "area", "base"})
    _SILENT = frozenset({"script", "style", "head"})

    def __init__(
        self, skip_classes: tuple[str, ...] = (), mark_classes: tuple[str, ...] = ()
    ) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_classes = skip_classes
        self._mark_classes = mark_classes
        self._open: list[tuple[str, str]] = []  # (tag, "skip" | "mark" | "")
        self._parts: list[str] = []

    def _inside(self, flag: str) -> bool:
        return any(f == flag for _, f in self._open)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        flag = ""
        if tag in self._SILENT or any(c.startswith(self._skip_classes) for c in classes):
            flag = "skip"
        elif any(c.startswith(self._mark_classes) for c in classes):
            flag = "mark"
        skipping = self._inside("skip") or flag == "skip"
        if tag not in self._VOID:
            self._open.append((tag, flag))
        if not skipping and tag in self._BLOCK:
            self._parts.append(_NEWLINE)

    def handle_endtag(self, tag: str) -> None:
        # Close up to the matching open tag, as a browser does; a stray end tag is ignored.
        for index in range(len(self._open) - 1, -1, -1):
            if self._open[index][0] == tag:
                skipping = self._inside("skip")
                del self._open[index:]
                if not skipping and tag in self._BLOCK:
                    self._parts.append(_NEWLINE)
                return

    def handle_data(self, data: str) -> None:
        if self._inside("skip"):
            return
        if self._inside("mark"):
            data = data.replace("((", "").replace("))", "")
        self._parts.append(data)

    def lines(self) -> list[str]:
        out = []
        for line in "".join(self._parts).splitlines():
            line = " ".join(line.split())
            if line:
                out.append(line)
        return out


def html_lines(
    fragment: str, skip_classes: tuple[str, ...] = (), mark_classes: tuple[str, ...] = ()
) -> list[str]:
    parser = _HtmlText(skip_classes, mark_classes)
    parser.feed(fragment)
    parser.close()
    return parser.lines()


_TABLE_RULE = re.compile(r"[+=\-|\s]+")


def table_columns(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split the lines of a typeset annex into running text and table columns.

    The annexes of an Italian decree are 80-column text with tables drawn in
    characters ("| Settore | Sottosettore | Tipologia |"). A cell wraps over
    several lines, so a phrase is never on one line. Returns the lines outside
    the tables and, for each column, its cells joined top to bottom.
    """
    plain: list[str] = []
    columns: dict[int, list[str]] = {}
    for line in lines:
        if _TABLE_RULE.fullmatch(line):
            continue
        if line.startswith("|") and line.endswith("|") and len(line) > 2:
            for index, cell in enumerate(line[1:-1].split("|")):
                cell = cell.strip()
                if cell and not _TABLE_RULE.fullmatch(cell):
                    columns.setdefault(index, []).append(cell)
            continue
        plain.append(line)
    return plain, [" ".join(columns[i]) for i in sorted(columns)]


# Normattiva classes: the editorial notes under an article and the notes of
# later amendments are not the text of the provision; "ins-akn" wraps the
# wording an amending act inserted, between "((" and "))".
_NORMATTIVA_SKIP = ("note-akn", "art_aggiornamento")
_NORMATTIVA_MARKS = ("ins-akn",)


def normattiva_text(article_html: str) -> str:
    """Plain text of the ``articoloHtml`` the Normattiva API returns for one article."""
    plain, columns = table_columns(html_lines(article_html, _NORMATTIVA_SKIP, _NORMATTIVA_MARKS))
    return _NEWLINE.join([*plain, *columns])


def normattiva_urn(entry: Entry, on: str) -> str:
    """URN of the article of an entry, in the version in force on ``on`` (AAAA-MM-GG)."""
    urn = entry.act
    if entry.annex is not None:
        return f"{urn}:{int(entry.annex)}~art1!vig={on}"
    key = parse_article(entry.article) or ""
    number = key.partition(":")[2]
    return f"{urn}~art{number}!vig={on}"


def normattiva_page(entry: Entry) -> str:
    """Address of the provision on normattiva.it, for the reader."""
    key = parse_article(entry.article) or ""
    suffix = "" if entry.annex is not None else f"~art{key.partition(':')[2]}"
    return f"https://www.normattiva.it/uri-res/N2Ls?{entry.act}{suffix}"


def _iso_day(compact: Any) -> str | None:
    text = str(compact or "")
    if re.fullmatch(r"\d{8}", text) and text != _NO_END and text != "00000000":
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return None


def read_normattiva(entry: Entry, on: str) -> Reading:
    """One article of an Italian act from the Normattiva open data API.

    Private helper: the document-check stream is building the full Normattiva
    source, which will replace this function.
    """
    urn = normattiva_urn(entry, on)
    body = http_request(
        NORMATTIVA_API,
        data=json.dumps({"urn": urn}).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        attempts=5,
        pause=4.0,
    )
    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise UnreachableError(f"risposta non JSON da Normattiva: {e}") from e
    data = payload.get("data") if isinstance(payload, dict) else None
    act = data.get("atto") if isinstance(data, dict) else None
    if not isinstance(act, dict) or not act.get("articoloHtml"):
        raise NotFoundError(f"Normattiva non ha un solo atto per {urn}")
    label = entry.article if entry.annex is not None else _article_label(entry.article)
    return Reading(
        version=f"vigente al {on}",
        version_label=f"testo vigente al {on} (Normattiva)",
        articles=[(label, normattiva_text(str(act["articoloHtml"])))],
        url=normattiva_page(entry),
        in_force_from=_iso_day(act.get("articoloDataInizioVigenza")),
        in_force_to=_iso_day(act.get("articoloDataFineVigenza")),
    )


def _article_label(reference: str) -> str:
    """ "Art. 1-bis" for any spelling of the reference: the label a chunk is matched by."""
    key = parse_article(reference) or ""
    kind, _, number = key.partition(":")
    return f"Art. {number}" if kind == "art" else reference


def read_eurlex(entry: Entry, on: str, source: CellarTextSource) -> Reading:
    """The articles of an EU act in its latest text not later than ``on``."""
    base = celex_utils.base_celex(entry.act)
    try:
        versions = source.versions(base)
    except TextUnavailableError as e:
        raise UnreachableError(str(e)) from e
    usable = [v for v in versions if v.as_of is None or v.as_of <= on]
    problems: list[str] = []
    # Newest consolidated text first, the act as adopted last.
    for version in sorted(usable, key=lambda v: v.as_of or "", reverse=True):
        try:
            articles = source.articles(version, entry.lang)
        except TextUnavailableError as e:
            problems.append(str(e))
            continue
        return Reading(
            version=version.celex,
            version_label=version.label,
            articles=[(a.label, a.text) for a in articles],
            url=version.url(entry.lang),
            consolidated_as_of=version.as_of,
        )
    return _read_cellar_html(base, entry.lang, problems)


def _read_cellar_html(celex: str, lang: str, problems: list[str]) -> Reading:
    """An act CELLAR serves only as plain HTML (no XHTML text), cut at its article headings."""
    try:
        body = http_request(
            CELLAR_RESOURCE.format(celex=celex),
            headers={"Accept": "text/html", "Accept-Language": ISO639_3.get(lang, "ita")},
            timeout=60.0,
        )
    except NotFoundError as e:
        raise UnreachableError("; ".join([*problems, str(e)])) from e
    text = "\n".join(html_lines(body.decode("utf-8", "replace")))
    if not text.strip():
        raise UnreachableError("; ".join([*problems, f"testo HTML di {celex} vuoto"]))
    return Reading(
        version=celex,
        version_label="testo originale (formato HTML)",
        articles=split_articles(text),
        url=celex_utils.eurlex_txt_url(celex, lang),
    )


def pdf_text(data: bytes) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(data)).pages)


def read_document(entry: Entry) -> Reading:
    """A document published by an authority on its own site (PDF)."""
    try:
        data = http_request(str(entry.url), headers={"Accept": "application/pdf"}, timeout=60.0)
    except NotFoundError as e:
        raise UnreachableError(str(e)) from e
    if not data.startswith(b"%PDF"):
        raise UnreachableError("l'indirizzo non restituisce un PDF")
    try:
        text = pdf_text(data)
    except Exception as e:  # a damaged or protected file: nothing was read
        raise UnreachableError(f"PDF non leggibile: {e}") from e
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return Reading(
        version="sha256:" + hashlib.sha256(data).hexdigest(),
        version_label="documento pubblicato dall'autorità",
        articles=split_articles("\n".join(line for line in lines if line)),
        url=entry.url,
    )


# ─── Checking one entry ──────────────────────────────────────────────


def check_reading(entry: Entry, reading: Reading) -> dict[str, Any]:
    """Outcome fields for an entry whose official text was read: verified or failed."""
    chunks = [
        {
            "id": f"{reading.version}:{label or 'testo'}:{index}",
            "text": text,
            "framework": _FRAMEWORK,
            "article": label,
            "lang": entry.lang,
        }
        for index, (label, text) in enumerate(reading.articles)
    ]
    citation = {
        "framework": _FRAMEWORK,
        "reference": _article_label(entry.article),
        "quote_snippet": entry.excerpt,
    }
    result = verify_citation(citation, chunks)
    fields: dict[str, Any] = {
        "version": reading.version,
        "version_label": reading.version_label,
        "consolidated_as_of": reading.consolidated_as_of,
        "in_force_from": reading.in_force_from,
        "url": reading.url,
        "official_quote": None,
        "detail": None,
    }

    def failed(detail: str) -> dict[str, Any]:
        return {**fields, "status": STATUS_FAILED, "detail": detail}

    if not result.verified:
        return failed("il passaggio non è nel testo ufficiale letto")
    if result.match != "exact":
        return failed("il passaggio non coincide parola per parola con il testo ufficiale")
    if result.level != "article":
        where = result.article or "un'altra parte dell'atto"
        return failed(f"il passaggio è in {where}, non nell'articolo indicato")
    if entry.paragraph.isdigit() and result.paragraph and result.paragraph != entry.paragraph:
        return failed(f"il passaggio è al paragrafo {result.paragraph}, non al {entry.paragraph}")
    if entry.in_force_from:
        if reading.in_force_from != entry.in_force_from:
            found = reading.in_force_from or "non indicata"
            return failed(
                f"vigenza dell'articolo dal {found}, il registro indica {entry.in_force_from}"
            )
        if reading.in_force_to:
            return failed(f"l'articolo non è più vigente dal {reading.in_force_to}")
    return {**fields, "status": STATUS_VERIFIED, "official_quote": result.official_quote}


class Reader:
    """Reads the official text of an entry; each article or document once per run."""

    def __init__(self, source: CellarTextSource, on: str) -> None:
        self.source = source
        self.on = on
        self.requests = 0  # texts asked to Normattiva or to an authority's site
        self._memo: dict[tuple[str, ...], Reading | Exception] = {}

    def read(self, entry: Entry) -> Reading:
        if entry.kind == KIND_EURLEX:
            return read_eurlex(entry, self.on, self.source)  # cached by CellarTextSource
        if entry.kind == KIND_NORMATTIVA:
            key: tuple[str, ...] = (entry.kind, normattiva_urn(entry, self.on))
        else:
            key = (entry.kind, str(entry.url))
        if key not in self._memo:
            if self.requests and entry.kind == KIND_NORMATTIVA:
                time.sleep(1.0)  # the open data API answers 500 to a burst of requests
            self.requests += 1
            try:
                if entry.kind == KIND_NORMATTIVA:
                    self._memo[key] = read_normattiva(entry, self.on)
                else:
                    self._memo[key] = read_document(entry)
            except (UnreachableError, NotFoundError) as e:
                self._memo[key] = e
        found = self._memo[key]
        if isinstance(found, Exception):
            raise found
        return found


def check_entry(entry: Entry, reader: Reader) -> dict[str, Any]:
    """Read the official text of an entry and check its excerpt."""
    try:
        reading = reader.read(entry)
    except UnreachableError as e:
        return {"status": STATUS_UNREACHABLE, "detail": f"fonte non raggiungibile: {e}"}
    except NotFoundError as e:
        return {"status": STATUS_FAILED, "detail": f"testo non trovato nella fonte ufficiale: {e}"}
    return check_reading(entry, reading)


def build_record(
    entry: Entry, outcome: dict[str, Any], on: str, previous: dict[str, Any] | None
) -> dict[str, Any]:
    """The record written for an entry, keeping an earlier verification through an outage."""
    status = outcome["status"]
    kept = (
        status == STATUS_UNREACHABLE
        and previous is not None
        and previous.get("status") == STATUS_VERIFIED
        and previous.get("fingerprint") == entry.fingerprint
    )
    if kept and previous is not None:
        return {**previous, "checked_on": on, "detail": outcome.get("detail")}
    return {
        "id": entry.id,
        "status": status,
        "verified_on": on if status == STATUS_VERIFIED else None,
        "checked_on": on,
        "version": outcome.get("version"),
        "version_label": outcome.get("version_label"),
        "consolidated_as_of": outcome.get("consolidated_as_of"),
        "in_force_from": outcome.get("in_force_from"),
        "official_quote": outcome.get("official_quote"),
        "url": outcome.get("url"),
        "detail": outcome.get("detail"),
        "fingerprint": entry.fingerprint,
    }


def load_previous(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    records = data.get("sources") if isinstance(data, dict) else None
    return {str(r["id"]): r for r in records or [] if isinstance(r, dict) and r.get("id")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Controlla sulle fonti ufficiali i passaggi di legge citati dal sito."
    )
    parser.add_argument("--registry", type=Path, default=REGISTRY, help="registro delle fonti")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="file degli esiti")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="cartella dei testi UE")
    parser.add_argument("--date", help="data del controllo (AAAA-MM-GG), oggi se assente")
    parser.add_argument("--only", nargs="+", metavar="ID", help="controlla solo queste voci")
    parser.add_argument(
        "--strict", action="store_true", help="esce con 2 se una fonte non è raggiungibile"
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    on = args.date or date.today().isoformat()
    try:
        date.fromisoformat(on)
    except ValueError:
        parser.error("--date vuole una data AAAA-MM-GG, per esempio 2026-11-11")

    entries = load_registry(args.registry)
    wanted = set(args.only or [])
    unknown = wanted - {e.id for e in entries}
    if unknown:
        parser.error(f"voci non presenti nel registro: {', '.join(sorted(unknown))}")

    previous = load_previous(args.output)
    reader = Reader(CellarTextSource(args.cache), on)
    records: list[dict[str, Any]] = []
    counts = {STATUS_VERIFIED: 0, STATUS_FAILED: 0, STATUS_UNREACHABLE: 0}
    kept = 0
    for entry in entries:
        earlier = previous.get(entry.id)
        if wanted and entry.id not in wanted:
            if earlier is not None and earlier.get("fingerprint") == entry.fingerprint:
                records.append(earlier)
            continue
        outcome = check_entry(entry, reader)
        record = build_record(entry, outcome, on, earlier)
        records.append(record)
        counts[outcome["status"]] += 1
        note = outcome.get("detail") or outcome.get("version_label") or ""
        if outcome["status"] == STATUS_UNREACHABLE and record["status"] == STATUS_VERIFIED:
            kept += 1
            note = f"{note}; resta la verifica del {record['verified_on']}"
        print(f"{outcome['status']:<11} {entry.id}: {note}")

    args.output.write_text(
        json.dumps(
            {"generated_on": on, "tool": "scripts/verify_site_sources.py", "sources": records},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    checked = sum(counts.values())
    print(
        f"{checked} voci controllate il {on}: {counts[STATUS_VERIFIED]} verificate, "
        f"{counts[STATUS_FAILED]} non confermate, {counts[STATUS_UNREACHABLE]} non raggiungibili"
        + (f" ({kept} con verifica precedente mantenuta)" if kept else "")
    )
    print(f"Esiti: {args.output}")
    if counts[STATUS_FAILED]:
        return 1
    if args.strict and counts[STATUS_UNREACHABLE] > kept:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
