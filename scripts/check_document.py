"""Check a document's legal references against the official EU texts in force.

Prototype of "controlla un documento" (src/document_check). From the
repository root:

    python scripts/check_document.py informativa.docx
    python scripts/check_document.py policy_ia.pdf --data 2026-03-01
    python scripts/check_document.py --ricontrolla informativa.norma-lock.json

The first run writes, next to the document, an HTML report and a lock file
(the provisions the document cites, with today's text). --ricontrolla compares
a lock file with the texts in force and writes a report of what changed. Texts
come from CELLAR (Publications Office of the EU) and are cached in
~/.cache/normaai/cellar; the first check of an act downloads it (about 5 s).

Formats: .docx, .pdf, .html, .txt, .md.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.document_check.check import build_lock, check_text, recheck  # noqa: E402
from src.document_check.extract import load_text  # noqa: E402
from src.document_check.official import CellarTextSource  # noqa: E402
from src.document_check.report import (  # noqa: E402
    render_html,
    render_recheck_html,
    summary_lines,
)

DEFAULT_CACHE = Path.home() / ".cache" / "normaai" / "cellar"
LOCK_SUFFIX = ".norma-lock.json"


def _beside(path: Path, suffix: str) -> Path:
    name = path.name[: -len(LOCK_SUFFIX)] if path.name.endswith(LOCK_SUFFIX) else path.stem
    return path.with_name(name + suffix)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Controlla i riferimenti di legge di un documento sui testi UE in vigore."
    )
    parser.add_argument("documento", nargs="?", type=Path, help="il documento da controllare")
    parser.add_argument(
        "--data", help="data del documento (AAAA-MM-GG): segnala cosa è cambiato dopo"
    )
    parser.add_argument(
        "--lingua", choices=["it", "en"], help="lingua dei testi ufficiali (di solito si capisce)"
    )
    parser.add_argument("--report", type=Path, help="file HTML del report")
    parser.add_argument("--lock", type=Path, help="file delle disposizioni citate")
    parser.add_argument(
        "--ricontrolla", type=Path, metavar="LOCK", help="ricontrolla un file delle disposizioni"
    )
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="cartella dei testi")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    source = CellarTextSource(args.cache)
    today = date.today().isoformat()

    if args.ricontrolla:
        lock = json.loads(args.ricontrolla.read_text(encoding="utf-8"))
        changes = recheck(lock, source)
        report = args.report or _beside(args.ricontrolla, ".ricontrollo.html")
        report.write_text(render_recheck_html(lock, changes, today), encoding="utf-8")
        for change in changes:
            entry = change.entry
            print(f"- {entry['nome']}, {entry['articolo']}: {change.code}")
        print(f"Report: {report}")
        return 0

    if args.documento is None:
        parser.error("indica un documento, oppure --ricontrolla con un file delle disposizioni")
    if args.data:
        try:
            date.fromisoformat(args.data)
        except ValueError:
            parser.error("--data vuole una data AAAA-MM-GG, per esempio 2026-03-01")

    text = load_text(args.documento)
    check = check_text(
        text,
        source,
        document=args.documento.name,
        lang=args.lingua,
        document_date=args.data,
        today=today,
    )
    report = args.report or _beside(args.documento, ".controllo.html")
    lock_path = args.lock or _beside(args.documento, LOCK_SUFFIX)
    lock_path.write_text(
        json.dumps(build_lock(check), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report.write_text(render_html(check, lock_path.name), encoding="utf-8")
    print("\n".join(summary_lines(check)))
    print(f"Report: {report}")
    print(f"Disposizioni citate: {lock_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
