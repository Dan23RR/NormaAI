"""Official texts of EU acts by version, from CELLAR, cached on disk.

``check`` asks for the versions of an act and for the articles of one version.
The versions are the act as adopted (``32024R1689``) followed by its CELLAR
consolidated texts, oldest first (``02024R1689-20260727``: the AI Act as
consolidated on 27 July 2026). A text is downloaded once per version and
language and kept in ``cache_dir``; the list of versions is asked again after a
day, so a new consolidated text is seen the next day.

Articles are rebuilt from the chunks of src/nlp/chunking/legal_chunker.py, the
same parsing the corpus uses, so a provision found here is labelled as the
assistant labels it. EUR-Lex consolidated texts are documentation: only the
Official Journal is authentic, and the report says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from src.agents.citation_verifier import parse_article, same_article
from src.crawler.eurlex import celex as celex_utils
from src.crawler.eurlex.client import EurLexClient, get_tracked_act
from src.nlp.chunking.legal_chunker import EURLexHTMLChunker

if TYPE_CHECKING:
    from pathlib import Path

    from src.nlp.chunking.legal_chunker import LegalChunk

_PARAGRAPH_RE = re.compile(r"(?m)^[ \t]*(\d{1,3})\.[ \t]+\S")
# EUR-Lex consolidation marks: "▼B" (basic act), "▼M1" (first amending act), "▼C1"
# (corrigendum), "►M1 ... ◄" around inserted words. Editorial, not part of the law.
_CONSOLIDATION_MARKS = re.compile(r"[▼►◄](?:\s*[A-Z]\d{0,3}\b)?")


class TextUnavailableError(RuntimeError):
    """CELLAR could not give the text (offline, no text in this language, endpoint error)."""


@dataclass(frozen=True)
class Version:
    """One version of an act: the act as adopted or a consolidated text."""

    celex: str  # "32024R1689" or "02024R1689-20260727"
    as_of: str | None  # ISO date of a consolidated text; None for the act as adopted

    @property
    def label(self) -> str:
        if self.as_of is None:
            return "testo originale"
        return f"testo consolidato al {_italian_date(self.as_of)}"

    def url(self, lang: str) -> str:
        return celex_utils.eurlex_txt_url(self.celex, celex_utils.normalize_lang(lang, "IT"))


@dataclass(frozen=True)
class ArticleText:
    """The text of one article, recital or annex in one version."""

    key: str  # parse_article key: "art:4", "recital:47", "annex:III"
    label: str  # the chunker's label: "Art. 4", "Recital 47", "Annex III"
    text: str
    paragraphs: tuple[str, ...]  # numbered paragraphs, in order ("1", "2", ...)


class TextSource(Protocol):
    """Where ``check`` reads the official texts (CELLAR, or a fake in tests)."""

    def versions(self, celex: str) -> list[Version]: ...

    def articles(self, version: Version, lang: str) -> list[ArticleText]: ...


def _italian_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def find_article(articles: list[ArticleText], key: str) -> ArticleText | None:
    """The article with this key ("art:19a" also finds "Art. 19 bis")."""
    return next((a for a in articles if same_article(a.key, key)), None)


def assemble_articles(chunks: list[LegalChunk]) -> list[ArticleText]:
    """One ArticleText per article, recital and annex, from the chunker's output.

    A long article is split into chunks that each repeat its heading lines
    ("Articolo 50", its title); the repeats are dropped so the rebuilt text is
    the same however a version happens to be split. Consolidation marks
    ("▼M1") are removed: they would break quotes and change the fingerprint of
    a provision whose words did not change.
    """
    groups: dict[str, list[str]] = {}
    for chunk in chunks:
        label = str(chunk.metadata.get("article") or "").strip()
        if label and parse_article(label) is not None:
            groups.setdefault(label, []).append(chunk.text)
    articles: list[ArticleText] = []
    for label, texts in groups.items():
        first = texts[0].split("\n")
        lines = list(first)
        for text in texts[1:]:
            part = text.split("\n")
            i = 0
            while i < min(len(part), len(first)) and part[i].strip() == first[i].strip():
                i += 1
            lines.extend(part[i:])
        body = _CONSOLIDATION_MARKS.sub("", "\n".join(lines))
        body = re.sub(r"[ \t]+(?=\n)|(?<=\n)[ \t]+", "", body)
        body = re.sub(r"[ \t]{2,}", " ", body)
        body = re.sub(r"\n{2,}", "\n", body).strip()
        paragraphs = tuple(dict.fromkeys(_PARAGRAPH_RE.findall(body)))
        key = parse_article(label)
        if key is not None:
            articles.append(ArticleText(key, label, body, paragraphs))
    return articles


class CellarTextSource:
    """Official texts from CELLAR, with an on-disk cache."""

    VERSIONS_TTL = timedelta(days=1)
    # Some consolidated versions have no XHTML text in CELLAR (02024R1689-20240712 in
    # Italian, 404): remembered for a week instead of asked again on every check.
    MISSING_TTL = timedelta(days=7)

    def __init__(self, cache_dir: Path, client: EurLexClient | None = None) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = client or EurLexClient(request_delay=0.5)
        self._articles: dict[tuple[str, str], list[ArticleText]] = {}
        self._unavailable: dict[tuple[str, str], str] = {}

    def versions(self, celex: str) -> list[Version]:
        base = celex_utils.base_celex(celex)
        path = self.cache_dir / f"{base}.versions.json"
        ids: list[str] | None = None
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            asked = datetime.fromisoformat(cached["asked_at"])
            if datetime.now(UTC) - asked < self.VERSIONS_TTL:
                ids = list(cached["ids"])
        if ids is None:
            try:
                ids = self._client.list_consolidated_celex(base)
            except Exception as e:
                raise TextUnavailableError(f"elenco delle versioni di {base} non disponibile: {e}")
            path.write_text(
                json.dumps({"asked_at": datetime.now(UTC).isoformat(), "ids": ids}),
                encoding="utf-8",
            )
        return [Version(base, None)] + [Version(i, celex_utils.consolidated_as_of(i)) for i in ids]

    def articles(self, version: Version, lang: str) -> list[ArticleText]:
        lang = celex_utils.normalize_lang(lang, "IT")
        memo = (version.celex, lang)
        if memo in self._unavailable:
            raise TextUnavailableError(self._unavailable[memo])
        if memo not in self._articles:
            try:
                html = self._html(version.celex, lang)
            except TextUnavailableError as e:
                self._unavailable[memo] = str(e)
                raise
            act = get_tracked_act(version.celex)
            chunker = EURLexHTMLChunker(
                version.celex,
                act.framework if act else "OTHER",
                lang,
                eli_type=act.eli_type if act else None,
            )
            self._articles[memo] = assemble_articles(chunker.chunk_html(html))
        return self._articles[memo]

    def _html(self, celex: str, lang: str) -> str:
        path = self.cache_dir / f"{celex}.{lang}.xhtml"
        if path.exists():
            return path.read_text(encoding="utf-8")
        missing = self.cache_dir / f"{celex}.{lang}.missing"
        no_text = f"CELLAR non ha il testo di {celex} in {lang}"
        if missing.exists():
            marked = datetime.fromtimestamp(missing.stat().st_mtime, UTC)
            if datetime.now(UTC) - marked < self.MISSING_TTL:
                raise TextUnavailableError(no_text)
        try:
            html = self._client.download_full_text_html(celex, lang)
        except Exception as e:
            raise TextUnavailableError(f"testo di {celex} non disponibile: {e}")
        if not html:
            missing.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")
            raise TextUnavailableError(no_text)
        path.write_text(html, encoding="utf-8")
        return html
