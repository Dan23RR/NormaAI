"""Regenerate the Codex PDF from its print source.

Usage (from the repository root or from frontend/; needs network access,
because the web fonts are loaded for the render, not by the published page):

  python frontend/scripts/build_codex_pdf.py

Renders frontend/public/codex.html with headless Chromium (Playwright) to
frontend/public/codex-post-omnibus-2025-2029.pdf, then:

  - reads on which page every chapter starts and, if the index of codex.html
    says otherwise, rewrites the page numbers of the index and renders again;
  - refuses to publish a file that contains a private mailbox (the contact of
    the guide is info@normaai.org) or a page with almost nothing on it;
  - prints the number of pages: the landing page states it
    (landing.codex.kicker in frontend/messages/it.json and en.json).

Options:
  --out PATH    write the PDF somewhere else (the index is still synchronised)
  --no-fonts    do not fail when the web fonts cannot be loaded

Requires the Python packages `playwright` (with a Chromium, or an installed
Edge or Chrome) and `pypdf`.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

PUBLIC = Path(__file__).resolve().parent.parent / "public"
SOURCE = PUBLIC / "codex.html"
OUTPUT = PUBLIC / "codex-post-omnibus-2025-2029.pdf"

# The paper colour of the guide (--paper). Chromium paints the page margins
# with the default background of the page, so it is set to the same tone:
# otherwise every page gets a frame of another colour.
PAPER = {"r": 255, "g": 255, "b": 255, "a": 1}
# The web fonts of the guide (frontend/DESIGN.md: Literata for headings and
# law, Public Sans for the text, Geist Mono for the decision paths) and the
# weights it uses. They are loaded here, for the render only: the published
# codex.html makes no request to a third party.
FONTS_CSS = (
    "https://fonts.googleapis.com/css2"
    "?family=Literata:opsz,wght@7..72,400..600"
    "&family=Public+Sans:wght@400..700"
    "&family=Geist+Mono:wght@400"
    "&display=block"
)
FONTS = {"Literata": (400, 500, 600), "Public Sans": (400, 600, 700), "Geist Mono": (400,)}
PRIVATE_MAILBOX = re.compile(r"@(gmail|googlemail|hotmail|outlook|yahoo|libero|icloud)\.", re.I)
# A page with fewer characters than this is a page break gone wrong.
MIN_CHARS_PER_PAGE = 600

TOC_ENTRY = re.compile(
    r'(<div class="toc-entry" data-target="(?P<target>[\w-]+)">.*?<span class="page-num">)p\. (?P<page>\d+)(</span>)',
    re.S,
)


def plain(text: str) -> str:
    """Text as it can be compared between the HTML source and the PDF."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = text.replace("\u2019", "'").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def chapter_titles(source: str) -> dict[str, str]:
    """Section id -> the title of its chapter heading, without the small label above it."""
    titles: dict[str, str] = {}
    for section in re.finditer(
        r'<section class="page[^"]*" id="(?P<id>[\w-]+)">(?P<body>.*?)</section>', source, re.S
    ):
        heading = re.search(r'<h1 class="chapter">(.*?)</h1>', section.group("body"), re.S)
        if heading:
            title = re.sub(r'<span class="num">.*?</span>', "", heading.group(1), flags=re.S)
            titles[section.group("id")] = plain(title)
    return titles


LOAD_FAMILY = """async ([family, weights]) => {
  const faces = await Promise.all(weights.map((w) => document.fonts.load(w + " 12px '" + family + "'")))
  return faces.every((found) => found.length > 0 && found.every((face) => face.status === "loaded"))
}"""


def load_fonts(page) -> list[str]:  # noqa: ANN001 - a Playwright page
    """Load the web fonts into the page; returns the families that could not be loaded.

    `document.fonts.check` answers true for a family nobody declared, so each
    weight is loaded explicitly and counted.
    """
    try:
        page.add_style_tag(url=FONTS_CSS)
    except Exception:  # noqa: BLE001 - offline: every family is missing
        return list(FONTS)
    missing = [
        family
        for family, weights in FONTS.items()
        if not page.evaluate(LOAD_FAMILY, [family, list(weights)])
    ]
    page.evaluate("document.fonts.ready.then(() => true)")
    return missing


def render(source: Path, target: Path, require_fonts: bool) -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = None
        errors = []
        for options in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
            try:
                browser = p.chromium.launch(**options)
                break
            except Exception as error:  # noqa: BLE001 - try the next browser
                errors.append(str(error).splitlines()[0])
        if browser is None:
            raise SystemExit("No Chromium, Edge or Chrome to launch:\n  " + "\n  ".join(errors))
        try:
            page = browser.new_page()
            page.goto(source.as_uri(), wait_until="networkidle")
            page.emulate_media(media="print")
            missing = load_fonts(page)
            if missing:
                message = f"web fonts not loaded: {', '.join(missing)} (no network?)"
                if require_fonts:
                    raise SystemExit(
                        f"{message}. Run again online, or pass --no-fonts to accept fallback fonts."
                    )
                print(f"WARNING: {message}; the PDF uses fallback fonts")
            session = page.context.new_cdp_session(page)
            session.send("Emulation.setDefaultBackgroundColorOverride", {"color": PAPER})
            page.pdf(
                path=str(target), format="A4", print_background=True, prefer_css_page_size=True
            )
        finally:
            browser.close()


def page_texts(pdf: Path) -> list[str]:
    from pypdf import PdfReader

    return [plain(page.extract_text() or "") for page in PdfReader(str(pdf)).pages]


def chapter_pages(source: str, texts: list[str]) -> dict[str, int]:
    """Section id -> 1-based page on which the chapter starts."""
    pages: dict[str, int] = {}
    index_page = next(
        (i for i, text in enumerate(texts) if "cosa trovate in questa guida" in text), 1
    )
    for target, title in chapter_titles(source).items():
        if target == "indice":
            continue
        for number, text in enumerate(texts, start=1):
            # The index names every chapter too: look after it.
            if number - 1 > index_page and title in text:
                pages[target] = number
                break
    return pages


def sync_index(source: str, pages: dict[str, int]) -> tuple[str, list[str]]:
    """The source with the page numbers of the index set to `pages`, and what changed."""
    changes: list[str] = []

    def fix(match: re.Match[str]) -> str:
        target = match.group("target")
        if target not in pages:
            raise SystemExit(f"The index points to '{target}', which was not found in the PDF.")
        if int(match.group("page")) != pages[target]:
            changes.append(f"{target}: p. {match.group('page')} -> p. {pages[target]}")
        return f"{match.group(1)}p. {pages[target]}{match.group(4)}"

    return TOC_ENTRY.sub(fix, source), changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--no-fonts", action="store_true")
    args = parser.parse_args()

    source = SOURCE.read_text(encoding="utf-8")
    if PRIVATE_MAILBOX.search(source):
        raise SystemExit("codex.html contains a private mailbox: use info@normaai.org.")
    if not TOC_ENTRY.search(source):
        raise SystemExit("No index entry found in codex.html (class toc-entry with data-target).")

    render(SOURCE, args.out, require_fonts=not args.no_fonts)
    texts = page_texts(args.out)
    synced, changes = sync_index(source, chapter_pages(source, texts))
    if changes:
        # Same digits in the same place: the layout does not move, one more pass is enough.
        SOURCE.write_text(synced, encoding="utf-8", newline="\n")
        print("Index updated in codex.html: " + "; ".join(changes))
        render(SOURCE, args.out, require_fonts=not args.no_fonts)
        texts = page_texts(args.out)
        _, again = sync_index(synced, chapter_pages(synced, texts))
        if again:
            raise SystemExit(
                "The index still does not match after a second pass: " + "; ".join(again)
            )

    problems = []
    if any(PRIVATE_MAILBOX.search(text) for text in texts):
        problems.append("the PDF contains a private mailbox")
    thin = [n for n, text in enumerate(texts, start=1) if n > 1 and len(text) < MIN_CHARS_PER_PAGE]
    if thin:
        problems.append(f"near-empty page(s): {thin} (check the page breaks)")
    for problem in problems:
        print(f"PROBLEM: {problem}")

    size_kb = args.out.stat().st_size / 1024
    print(f"{args.out.name}: {len(texts)} pages, {size_kb:.0f} KB")
    for target, page in chapter_pages(SOURCE.read_text(encoding="utf-8"), texts).items():
        print(f"  p. {page:>2}  {target}")
    print(
        f"Check that the landing page says {len(texts)} pages (landing.codex.kicker in frontend/messages)."
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
