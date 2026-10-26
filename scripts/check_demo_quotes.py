"""Check that the passages the demo and the site show as official are verbatim in EUR-Lex.

Usage (from the repository root, needs network access):
  python scripts/check_demo_quotes.py

Reads every quote in frontend/src/lib/mock-data.ts (quote_snippet values and the
*_QUOTE constants, with the celex of their citation) and the passage in
frontend/src/lib/law-passages.ts, fetches each act's Italian text from CELLAR
(Publications Office) and reports the quotes that are not found word for word.
Whitespace, non-breaking spaces and typographic apostrophes are normalised.
Exits with status 1 if any quote is not verbatim. Run it after editing demo data:
on 2026-10-26 it found 19 paraphrases shown as verified quotes.
"""

import html
import pathlib
import re
import sys
import urllib.request

LIB = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"
CELLAR = "http://publications.europa.eu/resource/celex/{celex}"


def collect_quotes() -> list[tuple[str, str, str]]:
    """(where, celex, text) for every quote shown as official text."""
    mock = (LIB / "mock-data.ts").read_text(encoding="utf-8")
    passages = (LIB / "law-passages.ts").read_text(encoding="utf-8")
    consts = {
        m.group(1): m.group(3)
        for m in re.finditer(r"const (\w+_QUOTE) =\s+(['\"])(.*?)\2\s*\n", mock)
    }
    quotes = []
    for m in re.finditer(r"quote_snippet:\s*(?:(['\"])(.*?)\1|(\w+))", mock):
        text = m.group(2) if m.group(2) is not None else consts.get(m.group(3), "")
        tail = mock[m.end() : m.end() + 400].split("}", 1)[0]
        celex = re.search(r"celex:\s*'(\w+)'", tail)
        if text and celex:
            line = mock.count("\n", 0, m.start()) + 1
            quotes.append((f"mock-data.ts:{line}", celex.group(1), text))
    celex = re.search(r"celex:\s*'(\w+)'", passages)
    for name in ("before", "quote", "after"):
        m = re.search(rf"{name}:\s*\n?\s*'(.*?)'", passages)
        if m and celex:
            quotes.append((f"law-passages.ts:{name}", celex.group(1), m.group(1)))
    return quotes


def normalise(text: str) -> str:
    text = html.unescape(text)
    for space in (" ", " ", " "):
        text = text.replace(space, " ")
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip()


def official_text(celex: str, cache: dict[str, str]) -> str:
    if celex not in cache:
        request = urllib.request.Request(
            CELLAR.format(celex=celex),
            headers={
                "Accept": "application/xhtml+xml",
                "Accept-Language": "ita",
                "User-Agent": "normaai-demo-quote-check",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", "replace")
        cache[celex] = normalise(re.sub(r"<[^>]+>", " ", raw))
    return cache[celex]


def main() -> int:
    cache: dict[str, str] = {}
    quotes = collect_quotes()
    missing = [
        (where, celex, text)
        for where, celex, text in quotes
        if normalise(text) not in official_text(celex, cache)
    ]
    for where, celex, text in missing:
        print(f"NOT VERBATIM {where} [{celex}]: {text[:120]}")
    print(f"{len(quotes)} quotes checked against {len(cache)} acts, {len(missing)} not verbatim")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
