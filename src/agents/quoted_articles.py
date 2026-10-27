"""Cite an amended article from the consolidated text, else as the amending act quotes it.

An amending act quotes whole articles of the act it amends ("the following
Article is inserted: «Article 4a ...»"). The chunker labels such a passage with
the amending act's own article and records the quoted one (``quoted_article``,
``amended_celex``; src/nlp/chunking/legal_chunker.py). Retrieved passages of
that kind are cited, by Daniel's decision of 2026-10-27:

C. From the consolidated text, when the corpus holds the amended act and its
   article has the passage's wording: the passage is replaced by the chunk of
   that article that contains it, so the answer quotes and cites the law as it
   stands. The amending act stays on the chunk (``amended_by_celex``,
   ``amended_by_article``) for the prompt label.
B. As the amending act quotes it, otherwise (consolidated text missing or
   worded differently): the passage is cut where the quotation ends and is
   presented and verified as the amended act's article (``citation_celex``,
   ``citation_article``); the amending act is where its wording was found.
   Only the first part of a quoted unit: it starts with the quoted article for
   sure, while a later part may already hold the next amendments.
A. Unchanged otherwise: a later part without the consolidated wording, or a
   part that starts with an amending instruction ("(4) Article 11 is amended
   as follows:") or with another quotation.

The consolidated text must contain the passage's own words before it replaces
it, so an answer never quotes a consolidated version older than the amendment.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from src.agents.citation_verifier import base_celex, normalize

ArticleLookup = Callable[[str, str, str | None], list[dict[str, Any]]]

# The probe: the start of the longest line of the quoted text, which must appear
# in the consolidated article. Shorter lines are too generic to prove the wording.
PROBE_CHARS = 160
MIN_PROBE_CHARS = 60

_OPENING_QUOTES = "‘“'\"«"
# The line that closes the quotation: "... shall apply.’;", "... applicazione.»;".
_CLOSING_LINE_RE = re.compile(r"[’”'\"»][;.,]?\s*$")
# A point that amends ("(4) Article 11 is amended as follows:", "(a) paragraph 1 is
# replaced by the following:", "1) è inserito l'articolo seguente:").
_INSTRUCTION_RE = re.compile(
    r"^\(?[0-9a-z]{1,3}\)\s.*\b(?:amended|replaced|inserted|added|deleted"
    r"|modificat\w*|sostituit\w*|inserit\w*|aggiunt\w*|soppress\w*)\b",
    re.IGNORECASE,
)


def _wording(text: str) -> str:
    """Normalized text without quote marks, which only the quotation carries."""
    return re.sub(r"[\"']", "", normalize(text))


def quoted_span(chunk: dict[str, Any]) -> list[str]:
    """The lines of the quoted article in a chunk, after its heading line.

    From the first body line to the line that closes the quotation; empty when
    the body starts with an amending instruction or with another quotation.
    """
    body = (chunk.get("text") or "").split("\n")[1:]
    if not body or body[0][:1] in _OPENING_QUOTES or _INSTRUCTION_RE.match(body[0]):
        return []
    span = []
    for line in body:
        if _INSTRUCTION_RE.match(line):
            break
        span.append(line)
        if _CLOSING_LINE_RE.search(line):
            break
    return span


def _probe(span: list[str]) -> str | None:
    longest = max((_wording(line) for line in span), key=len, default="")
    return longest[:PROBE_CHARS] if len(longest) >= MIN_PROBE_CHARS else None


def resolve_quoted_articles(
    chunks: list[dict[str, Any]], article_chunks: ArticleLookup
) -> list[dict[str, Any]]:
    """Apply C, then B, then A (module docstring) to the retrieved chunks, in order.

    ``article_chunks(celex, article, lang)`` returns the chunks of an article
    (HybridIndexer.article_chunks). Chunks of other acts pass through untouched;
    a consolidated chunk already retrieved is not added twice.
    """
    present = {c.get("id") for c in chunks if c.get("id") is not None}
    lookups: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
    provenance: dict[Any, dict[str, Any]] = {}
    resolved: list[dict[str, Any]] = []
    for chunk in chunks:
        quoted, amended = chunk.get("quoted_article"), chunk.get("amended_celex")
        span = quoted_span(chunk) if quoted and amended else []
        if not span:
            resolved.append(chunk)  # not an amending passage, or A
            continue
        amending = {
            "amended_by_celex": base_celex(chunk),
            "amended_by_article": chunk.get("article"),
        }
        key = (amended, quoted, chunk.get("lang"))
        if key not in lookups:
            lookups[key] = article_chunks(*key)
        probe = _probe(span)
        match = next(
            (c for c in lookups[key] if probe and probe in _wording(c.get("text") or "")),
            None,
        )
        if match is not None:  # C
            provenance.setdefault(match.get("id"), amending)
            if match.get("id") not in present:
                present.add(match.get("id"))
                resolved.append({**match, "score": chunk.get("score")})
            continue
        if chunk.get("part") not in (None, "1", 1):
            resolved.append(chunk)  # A
            continue
        heading = (chunk.get("text") or "").split("\n", 1)[0]
        resolved.append(  # B
            {
                **chunk,
                "text": "\n".join([heading, *span]),
                "citation_celex": amended,
                "citation_article": quoted,
            }
        )
    return [{**c, **provenance[c.get("id")]} if c.get("id") in provenance else c for c in resolved]
