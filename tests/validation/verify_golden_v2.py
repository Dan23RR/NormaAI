"""Re-verify the golden_v2 quotes against the official text (EUR-Lex / CELLAR).

Every ``verification: "fetched"`` record in ``test_cases/golden_v2.jsonl`` carries a
passage copied verbatim from the official text of the cited act. This script
downloads that act from the Publications Office CELLAR endpoint (the same data
EUR-Lex serves; it also works from datacenter IPs), extracts the cited article
and checks that the passage is still there, word for word.

    python -m tests.validation.verify_golden_v2                 # verify the shipped file
    python -m tests.validation.verify_golden_v2 --offline       # cache only, no network
    python -m tests.validation.verify_golden_v2 --cache-dir DIR # reuse downloaded acts

Exit code 0 when every fetched record verifies, 1 otherwise. This is a network
tool and is NOT part of the offline pytest suite (see test_golden_v2_schema.py
for the offline checks). Stdlib only.

Cache layout: ``<cache-dir>/<celex>_<lang3>/body.html`` (one directory per act,
downloaded files are treated as data, never executed).
"""

from __future__ import annotations

import argparse
import html
import json
import pathlib
import re
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request

CELLAR_URL = "http://publications.europa.eu/resource/celex/{celex}"
LANG3 = {"it": "ita", "en": "eng"}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 NormaAI-golden-v2-verifier"
)
DEFAULT_FILE = pathlib.Path(__file__).parent / "test_cases" / "golden_v2.jsonl"
DEFAULT_CACHE = pathlib.Path(tempfile.gettempdir()) / "normaai-eurlex-cache"

# ─── Markup handling ─────────────────────────────────────────────
# Two markups are served by CELLAR: the OJ "oj-*" format for base acts and the
# "norm"/"grid-list" format for consolidated texts (with ▼M / ►M amendment
# markers). Both are reduced to a list of text lines, one per paragraph /
# point, with point markers ("(a)", "a)", "i)") merged into their text.

TAG_RE = re.compile(r"<[^>]+>")
NOTE_RE = re.compile(r'<span class="oj-super oj-note-tag">.*?</span>', re.S)
MODREF_RE = re.compile(r'<p class="modref">.*?</p>', re.S)
FOOTNOTE_RE = re.compile(
    r'\(\s*<a[^>]*>\s*<span class="superscript">\d+</span>\s*</a>\s*\)'
    r'|<span class="superscript">\d+</span>',
    re.S,
)
BLOCK_END_RE = re.compile(r"</(p|div|td|tr|table|li)>")
AMEND_MARK_RE = re.compile(r"[▼►◄]\s*(?:[A-Z]\d*)?\s*")
MARKER_RE = re.compile(
    r"^(\(?[0-9]+( bis| ter| quater)?\)|\(?[a-z]{1,4}( bis| ter| quater)?\)|[—–-]|[0-9]+( bis| ter)?\.)$"
)
ARTICLE_DIV_RE = r'<div class="eli-subdivision" id="art_{art}">'
NEXT_DIV_RE = re.compile(r'<div class="eli-subdivision" id="(art_|anx_|fnp_|sig_|cpt_|sct_|tit_)')


def fetch_act(celex: str, lang: str, cache_dir: pathlib.Path, offline: bool = False) -> str:
    """Return the XHTML of an act (CELEX id, 'it'/'en'), downloading it once."""
    lang3 = LANG3[lang]
    path = cache_dir / f"{celex}_{lang3}" / "body.html"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    if offline:
        raise FileNotFoundError(f"{celex} ({lang3}) not in cache {cache_dir} and --offline set")
    req = urllib.request.Request(
        CELLAR_URL.format(celex=celex),
        headers={
            "Accept": "application/xhtml+xml",
            "Accept-Language": lang3,
            "User-Agent": USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"CELLAR returned HTTP {e.code} for {celex} ({lang3})") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body.decode("utf-8", errors="replace")


def article_block(text: str, article: str) -> str | None:
    """Return the raw markup of one article ('50', '19a', ...) or None."""
    m = re.search(ARTICLE_DIV_RE.format(art=re.escape(article)), text)
    if not m:
        return None
    rest = text[m.end() :]
    nxt = NEXT_DIV_RE.search(rest)
    end = m.end() + nxt.start() if nxt else len(text)
    return text[m.start() : end]


def paragraphs(block: str) -> list[str]:
    """Reduce an article's markup to text lines (paragraphs and points)."""
    s = NOTE_RE.sub("", block)
    s = MODREF_RE.sub("", s)
    s = FOOTNOTE_RE.sub("", s)
    s = re.sub(r"<br\s*/?>", "\n", s)
    s = BLOCK_END_RE.sub("\n", s)
    s = TAG_RE.sub("", s)
    s = html.unescape(s).replace("\xa0", " ")
    lines: list[str] = []
    for raw in s.split("\n"):
        t = re.sub(r"\s+", " ", raw).strip()
        t = AMEND_MARK_RE.sub("", t).strip()
        if t:
            lines.append(t)
    out: list[str] = []
    pending = ""
    for t in lines:
        if MARKER_RE.match(t):
            pending = (pending + " " + t).strip()
            continue
        if pending:
            t = f"{pending} {t}"
            pending = ""
        out.append(t)
    if pending:
        out.append(pending)
    return out


def article_lines(
    celex: str, lang: str, article: str, cache_dir: pathlib.Path, offline: bool = False
) -> list[str]:
    block = article_block(fetch_act(celex, lang, cache_dir, offline), article)
    if block is None:
        raise LookupError(f"Article {article} not found in {celex} ({lang})")
    return paragraphs(block)


# ─── Comparison ──────────────────────────────────────────────────

_QUOTE_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "‚": "'",
        "“": '"',
        "”": '"',
        "„": '"',
        "«": '"',
        "»": '"',
        "–": "-",
        "—": "-",
    }
)


def normalize(s: str) -> str:
    """Comparison form: NFKC, ASCII quotes/dashes, no amendment markers, single spaces."""
    s = unicodedata.normalize("NFKC", s).translate(_QUOTE_MAP)
    s = AMEND_MARK_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_in_article(quote: str, lines: list[str]) -> bool:
    return normalize(quote) in normalize(" ".join(lines))


def resolve_locator(lines: list[str], loc: dict) -> str:
    """Pick a passage from an article by locator (used when building the set).

    loc: {"para": "5"} | {"startswith": "..."} | {"contains": "..."}, plus optional
    "span" (number of consecutive lines, default 1) and "strip_quotes" (drop
    surrounding quotation marks of text inserted by an amending act).
    """
    norm = [normalize(line) for line in lines]
    idx = -1
    if "para" in loc:
        target = f"{loc['para']}. "
        idx = next((i for i, line in enumerate(norm) if line.startswith(target)), -1)
    elif "startswith" in loc:
        prefix = normalize(loc["startswith"])
        idx = next((i for i, line in enumerate(norm) if line.startswith(prefix)), -1)
    elif "contains" in loc:
        needle = normalize(loc["contains"])
        idx = next((i for i, line in enumerate(norm) if needle in line), -1)
    if idx < 0:
        raise LookupError(f"locator {loc!r} did not match any line")
    span = int(loc.get("span", 1))
    passage = "\n".join(lines[idx : idx + span])
    if loc.get("strip_quotes"):
        passage = passage.strip("‘’'“”\"")
    return passage


# ─── Record verification ─────────────────────────────────────────


def load_records(path: pathlib.Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON ({e})") from e
    return records


def verify_record(rec: dict, cache_dir: pathlib.Path, offline: bool = False) -> tuple[bool, str]:
    exp = rec.get("expected", {})
    if rec.get("verification") != "fetched":
        return True, "skipped (unverified record)"
    if exp.get("abstain"):
        return True, "skipped (abstain record, nothing to quote)"
    quote = exp.get("quote") or ""
    if not quote.strip():
        return False, "fetched record without quote"
    celex = exp.get("quote_celex") or exp.get("celex")
    article = exp.get("quote_article") or exp.get("article")
    if not celex or not article:
        return False, "fetched record without celex/article"
    try:
        lines = article_lines(celex, rec["lang"], str(article), cache_dir, offline)
    except (LookupError, RuntimeError, FileNotFoundError, KeyError) as e:
        return False, str(e)
    if quote_in_article(quote, lines):
        return True, f"verified in {celex} art. {article} ({rec['lang']})"
    return False, f"quote NOT found in {celex} art. {article} ({rec['lang']})"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--file", type=pathlib.Path, default=DEFAULT_FILE)
    parser.add_argument("--cache-dir", type=pathlib.Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--offline", action="store_true", help="never download; fail if an act is not cached"
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    records = load_records(args.file)
    failures = 0
    checked = 0
    for rec in records:
        ok, msg = verify_record(rec, args.cache_dir, args.offline)
        if msg.startswith("skipped"):
            if args.verbose:
                print(f"-  {rec['id']}: {msg}")
            continue
        checked += 1
        if not ok:
            failures += 1
            print(f"!! {rec['id']}: {msg}")
        elif args.verbose:
            print(f"ok {rec['id']}: {msg}")
    print(f"{checked} fetched records checked, {failures} failed, {len(records) - checked} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
