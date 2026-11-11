"""Render frontend/public/og-image.png (1200 x 630) from template.html.

    python frontend/scripts/og-image/render.py [--next-dir <path to a .next folder>]

Needs Playwright for Python with Chromium (``python -m playwright install chromium``).

Fonts. The template asks for Literata and Public Sans, which are not system
fonts. next/font keeps the files the site serves in the build folder, so the
script reads the ``@font-face`` rules of those two families from a ``.next``
folder (``frontend/.next`` by default: any ``next dev`` or ``next build`` fills
it) and embeds them. Without one the image falls back to Georgia and the system
sans, and the script says so: do not commit that result.
"""

from __future__ import annotations

import argparse
import base64
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
FRONTEND = HERE.parents[1]
TEMPLATE = HERE / "template.html"
OUTPUT = FRONTEND / "public" / "og-image.png"
WIDTH, HEIGHT = 1200, 630
FAMILIES = ("Literata", "Public Sans")

_FACE = re.compile(r"@font-face\s*\{[^}]*\}")
_FAMILY = re.compile(r"font-family:\s*[\"']?([^;\"'}]+)[\"']?\s*[;}]")
_URL = re.compile(r"url\(\s*[\"']?([^\"')]+\.woff2)[\"']?\s*\)")


def embedded_font_faces(next_dir: Path) -> str:
    """The @font-face rules of the two families, each font file inlined as a data URL."""
    faces: dict[str, str] = {}
    for css in sorted(next_dir.rglob("*.css")):
        text = css.read_text(encoding="utf-8", errors="ignore")
        if "@font-face" not in text:
            continue
        for face in _FACE.findall(text):
            family = _FAMILY.search(face)
            url = _URL.search(face)
            if not family or not url or family.group(1).strip() not in FAMILIES:
                continue
            font = (css.parent / url.group(1)).resolve()
            if not font.is_file():
                continue
            data = base64.b64encode(font.read_bytes()).decode("ascii")
            faces[face] = face.replace(url.group(0), f'url("data:font/woff2;base64,{data}")')
    return "\n".join(faces.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--next-dir", type=Path, default=FRONTEND / ".next")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    fonts_css = embedded_font_faces(args.next_dir) if args.next_dir.is_dir() else ""

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.goto(TEMPLATE.as_uri())
        if fonts_css:
            page.add_style_tag(content=fonts_css)
        page.evaluate("() => document.fonts.ready")
        loaded = page.evaluate(
            """async () => {
              await Promise.all([document.fonts.load('500 60px Literata'), document.fonts.load('600 34px Literata'),
                                 document.fonts.load('400 18px "Public Sans"'), document.fonts.load('500 24px "Public Sans"')]);
              return [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family.replace(/["']/g, ''));
            }"""
        )
        page.screenshot(
            path=str(args.output), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT}
        )
        browser.close()

    missing = [family for family in FAMILIES if family not in loaded]
    print(f"Saved {args.output} ({args.output.stat().st_size // 1024} KB)")
    if missing:
        print(
            f"WARNING: {', '.join(missing)} not found in {args.next_dir}: the image uses fallback fonts. "
            "Run `next dev` or `next build` once, or pass --next-dir, then render again.",
            file=sys.stderr,
        )
        return 1
    print("Fonts embedded from", args.next_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
