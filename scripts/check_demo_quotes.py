"""Check that the passages the demo and the site show as official are verbatim in EUR-Lex.

Usage (from the repository root, needs network access):
  python scripts/check_demo_quotes.py

Reads every quote the demo shows as official text:
  - frontend/src/lib/demo/qa-it.ts and qa-en.ts (the answers of "Chiedi"): the
    `quote_snippet` values and the `*_QUOTE` constants, with the `celex` of
    their citation; qa-it.ts is checked against the Italian text, qa-en.ts
    against the English one;
  - frontend/src/lib/law-passages.ts (the passage of the landing page).
Each act is fetched from CELLAR (Publications Office) in the version the demo
declares in frontend/src/lib/demo/acts.ts (`DEMO_ACT_VERSIONS`): the
consolidated text at that date for an amended act, the text published in the
Official Journal otherwise. A passage that an amending act rewrote therefore
fails, even if it was verbatim in the original act.

Whitespace, non-breaking spaces, typographic apostrophes, the consolidation
marks of EUR-Lex and the ordinal of "1° gennaio" (a superscript in the
official HTML) are normalised; nothing else is. Exits with status 1 if any
quote is not verbatim, or if a citation is marked verified without a quote.
Run it after editing demo data: on 2026-10-26 it found 19 paraphrases shown as
verified quotes.
"""

import html
import pathlib
import re
import sys
import urllib.request

LIB = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "src" / "lib"
CELLAR = "http://publications.europa.eu/resource/celex/{celex}"

# (file, CELLAR language) of the demo answers.
QA_FILES = (("demo/qa-it.ts", "ita"), ("demo/qa-en.ts", "eng"))
PASSAGE_LANGUAGES = {"it": "ita", "en": "eng"}

# EUR-Lex consolidation marks: "▼B", "▼M1", "►M1 ... ◄". Editorial, not part of the law.
_CONSOLIDATION_MARKS = re.compile("[\u25bc\u25ba\u25c4](?:\\s*[A-Z]\\d{0,3}\\b)?")
# "1<sup>o</sup> gennaio" in the official HTML, "1° gennaio" in the demo.
_FIRST_OF_MONTH = re.compile("\\b1 ?[o\u00ba\u00b0] (?=[a-z])")


def demo_versions() -> dict[str, str]:
    """CELEX of the basic act -> date of the consolidated text the demo quotes (acts.ts)."""
    source = (LIB / "demo" / "acts.ts").read_text(encoding="utf-8")
    block = re.search(r"DEMO_ACT_VERSIONS[^=]*=\s*\{(.*?)\n\}", source, re.S)
    if not block:
        raise SystemExit("DEMO_ACT_VERSIONS not found in frontend/src/lib/demo/acts.ts")
    return dict(re.findall(r"'(\w+)':\s*'(\d{4}-\d{2}-\d{2})'", block.group(1)))


def text_id(celex: str, versions: dict[str, str]) -> str:
    """The CELLAR id to read: 02024R1689-20260727 for an act with a declared version."""
    as_of = versions.get(celex)
    return f"0{celex[1:]}-{as_of.replace('-', '')}" if as_of else celex


def collect_quotes() -> tuple[list[tuple[str, str, str, str]], list[str]]:
    """((where, celex, language, text) for every quote shown as official, problems)."""
    quotes: list[tuple[str, str, str, str]] = []
    problems: list[str] = []
    for name, language in QA_FILES:
        source = (LIB / name).read_text(encoding="utf-8")
        consts = {
            m.group(1): m.group(3)
            for m in re.finditer(r"const (\w+_QUOTE) =\s+(['\"])(.*?)\2\s*\n", source)
        }
        for m in re.finditer(r"quote_snippet:\s*(?:(['\"])(.*?)\1|(\w+))", source):
            text = m.group(2) if m.group(2) is not None else consts.get(m.group(3), "")
            tail = source[m.end() : m.end() + 600].split("}", 1)[0]
            celex = re.search(r"celex:\s*'(\w+)'", tail)
            verified = re.search(r"verified:\s*true", tail)
            where = f"{name}:{source.count(chr(10), 0, m.start()) + 1}"
            if verified and not (text and celex):
                problems.append(f"VERIFIED WITHOUT QUOTE OR CELEX {where}")
            if text and celex:
                quotes.append((where, celex.group(1), language, text))
    passages = (LIB / "law-passages.ts").read_text(encoding="utf-8")
    for block in re.findall(r"QuotedPassage = \{(.*?)\n\}", passages, re.S):
        celex = re.search(r"celex:\s*'(\w+)'", block)
        lang = re.search(r"lang:\s*'(\w+)'", block)
        language = PASSAGE_LANGUAGES.get(lang.group(1) if lang else "it", "ita")
        for name in ("before", "quote", "after"):
            m = re.search(rf"{name}:\s*\n?\s*'(.*?)'", block)
            if m and celex:
                quotes.append((f"law-passages.ts:{name}", celex.group(1), language, m.group(1)))
    return quotes, problems


def normalise(text: str) -> str:
    text = html.unescape(text)
    # No-break space, narrow no-break space, thin space: how EUR-Lex groups digits.
    for space in ("\u00a0", "\u202f", "\u2009"):
        text = text.replace(space, " ")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = _CONSOLIDATION_MARKS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return _FIRST_OF_MONTH.sub("1\u00b0 ", text)


def official_text(celex: str, language: str, cache: dict[tuple[str, str], str]) -> str:
    key = (celex, language)
    if key not in cache:
        request = urllib.request.Request(
            CELLAR.format(celex=celex),
            headers={
                "Accept": "application/xhtml+xml",
                "Accept-Language": language,
                "User-Agent": "normaai-demo-quote-check",
            },
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", "replace")
        cache[key] = normalise(re.sub(r"<[^>]+>", " ", raw))
    return cache[key]


def main() -> int:
    versions = demo_versions()
    cache: dict[tuple[str, str], str] = {}
    quotes, problems = collect_quotes()
    missing = [
        (where, text_id(celex, versions), language, text)
        for where, celex, language, text in quotes
        if normalise(text) not in official_text(text_id(celex, versions), language, cache)
    ]
    for problem in problems:
        print(problem)
    for where, celex, language, text in missing:
        print(f"NOT VERBATIM {where} [{celex} {language}]: {text[:120]}")
    by_language = {
        language: sum(1 for q in quotes if q[2] == language) for language in ("ita", "eng")
    }
    print(
        f"{len(quotes)} quotes checked ({by_language['ita']} Italian, {by_language['eng']} English) "
        f"against {len(cache)} texts, {len(missing)} not verbatim, {len(problems)} without a quote"
    )
    return 1 if missing or problems else 0


if __name__ == "__main__":
    sys.exit(main())
