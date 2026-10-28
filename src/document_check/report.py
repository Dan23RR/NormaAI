"""The report a consultant reads: one HTML page in Italian, and a plain-text summary.

Findings are grouped by what to do (correct, check, fine, Italian law to check
on Normattiva) and keep the document's order inside each group. An outdated
quote or a provision changed after the document's date shows the provision then
and now, word by word.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from html import escape
from typing import TYPE_CHECKING

from src.document_check.check import GROUPS, Change, DocumentCheck, Finding

if TYPE_CHECKING:
    from src.document_check.official import Version

GROUP_TITLES = {
    "correggere": "Da correggere",
    "controllare": "Da controllare",
    "a_posto": "A posto",
    "non_coperto": "Diritto italiano da controllare su Normattiva",
}
_SUMMARY_LABELS = {
    "correggere": "da correggere",
    "controllare": "da controllare",
    "a_posto": "a posto",
    "non_coperto": "di diritto italiano",
}

_CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #ffffff; color: #1b1f24; font: 16px/1.55 system-ui, -apple-system,
  "Segoe UI", Roboto, sans-serif; }
main { max-width: 880px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 1.6rem; line-height: 1.25; margin: 4px 0 8px; overflow-wrap: anywhere; }
h2 { font-size: 1.15rem; margin: 40px 0 12px; }
h3 { font-size: 1rem; margin: 0; }
.kicker { margin: 0; color: #4b5563; }
.meta { margin: 0; color: #4b5563; }
.summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
  margin-top: 24px; }
.tile { border-radius: 8px; padding: 12px 14px; border: 1px solid #d0d5dd; }
.tile strong { display: block; font-size: 1.6rem; line-height: 1.1; }
.card { border: 1px solid #d0d5dd; border-left-width: 6px; border-radius: 8px; padding: 14px 16px;
  margin: 12px 0; }
.card-head { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: baseline; }
.pill { font-size: .85rem; font-weight: 600; padding: 2px 8px; border-radius: 999px; }
.where { color: #374151; margin: 8px 0; overflow-wrap: anywhere; }
mark { background: #fff1b8; padding: 0 2px; border-radius: 2px; }
blockquote { margin: 8px 0; padding: 6px 12px; border-left: 3px solid #d0d5dd; color: #374151; }
.card ul { margin: 8px 0; padding-left: 20px; }
.official { color: #374151; }
.diff { background: #f8f9fb; border-radius: 6px; padding: 10px 12px; margin: 8px 0;
  overflow-wrap: anywhere; }
.diff p { margin: 4px 0; }
del { background: #fde2e1; color: #7a271a; text-decoration: line-through; }
ins { background: #dcfae6; color: #054f31; text-decoration: none; }
a { color: #1849a9; }
table { width: 100%; border-collapse: collapse; font-size: .95rem; }
th, td { text-align: left; vertical-align: top; padding: 8px 6px; border-bottom: 1px solid #e4e7ec;
  overflow-wrap: anywhere; }
footer { margin-top: 48px; color: #4b5563; font-size: .9rem; }
.correggere { border-color: #b42318; } .correggere .pill, .tile.correggere { background: #fef3f2;
  color: #912018; }
.controllare { border-color: #b54708; } .controllare .pill, .tile.controllare { background: #fffaeb;
  color: #93370d; }
.a_posto { border-color: #067647; } .a_posto .pill, .tile.a_posto { background: #ecfdf3;
  color: #05603a; }
.non_coperto { border-color: #667085; } .non_coperto .pill, .tile.non_coperto { background: #f2f4f7;
  color: #344054; }
@media (max-width: 640px) { .summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media print { a { color: inherit; } .card { break-inside: avoid; } }
"""

_FOOTER = (
    "Il controllo confronta il documento con i testi consolidati di EUR-Lex, che sono "
    "documentazione: fanno fede solo i testi pubblicati nella Gazzetta ufficiale dell'Unione "
    "europea. I riferimenti sono trovati in automatico e uno scritto in modo insolito può sfuggire. "
    "Non è un parere legale."
)


def _italian_date(iso: str | None) -> str:
    if not iso:
        return "non indicata"
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def diff_html(before: str, after: str) -> str:
    """Word-level differences: removed words in <del>, added words in <ins>."""
    a, b = before.split(), after.split()
    parts: list[str] = []
    for op, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            words = a[i1:i2]
            if len(words) > 40:
                words = [*words[:15], "…", *words[-15:]]
            parts.append(escape(" ".join(words)))
            continue
        if op in ("delete", "replace"):
            parts.append(f"<del>{escape(' '.join(a[i1:i2]))}</del>")
        if op in ("insert", "replace"):
            parts.append(f"<ins>{escape(' '.join(b[j1:j2]))}</ins>")
    return " ".join(parts)


def _highlight(context: str, raw: str) -> str:
    tokens = raw.split()
    if tokens:
        m = re.search(r"\s+".join(map(re.escape, tokens)), context)
        if m:
            return (
                escape(context[: m.start()])
                + f"<mark>{escape(m.group(0))}</mark>"
                + escape(context[m.end() :])
            )
    return escape(context)


def _title(finding: Finding) -> str:
    provision = finding.provision.label if finding.provision else finding.reference.raw
    return f"{finding.act_name}, {provision}"


def _diff_block(before: str, after: str, old: Version | None, new: Version | None) -> str:
    old_label = old.label if old else "testo precedente"
    new_label = new.label if new else "testo vigente"
    return (
        '<div class="diff">'
        f"<p><strong>Differenze tra il {escape(old_label)} e il {escape(new_label)}</strong></p>"
        f"<p>{diff_html(before, after)}</p></div>"
    )


def _card(finding: Finding) -> str:
    ref = finding.reference
    parts = [
        f'<article class="card {finding.status.group}">',
        '<div class="card-head">',
        f'<span class="pill">{escape(finding.status.label)}</span>',
        f"<h3>{escape(_title(finding))}</h3></div>",
        f'<p class="where">Riga {ref.line}: {_highlight(ref.context, ref.raw)}</p>',
    ]
    if finding.shows_quotes:
        for quote in ref.quotes:
            parts.append(f"<blockquote>Nel documento: «{escape(quote)}»</blockquote>")
    parts.append("<ul>" + "".join(f"<li>{escape(m)}</li>" for m in finding.messages) + "</ul>")
    if finding.official_quote:
        parts.append(f'<p class="official">Testo ufficiale: «{escape(finding.official_quote)}»</p>')
    if finding.before and finding.article:
        parts.append(
            _diff_block(
                finding.before, finding.article.text, finding.before_version, finding.version
            )
        )
    if finding.url:
        where = "su Normattiva" if finding.act and not finding.act.eu else "su EUR-Lex"
        parts.append(f'<p><a href="{escape(finding.url)}">Testo vigente {where}</a></p>')
    parts.append("</article>")
    return "".join(parts)


def _fine_table(findings: list[Finding]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{f.reference.line}</td>"
        f"<td>{escape(f.reference.raw)}</td>"
        f"<td>{escape(_title(f))}</td>"
        f"<td>{escape(f.status.label)}</td>"
        "</tr>"
        for f in findings
    )
    return (
        "<table><thead><tr><th>Riga</th><th>Nel documento</th><th>Norma</th><th>Esito</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _italian_table(findings: list[Finding]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{f.reference.line}</td>"
        f"<td>{escape(f.reference.raw)}</td>"
        f"<td>{escape(_title(f))}</td>"
        + (f'<td><a href="{escape(f.url)}">Normattiva</a></td>' if f.url else "<td></td>")
        + "</tr>"
        for f in findings
    )
    return (
        "<table><thead><tr><th>Riga</th><th>Nel documento</th><th>Norma</th><th>Testo</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
    )


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="it"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_CSS}</style></head>"
        f"<body><main>{body}<footer><p>{escape(_FOOTER)}</p></footer></main></body></html>"
    )


def render_html(check: DocumentCheck, lock_name: str | None = None) -> str:
    """The report of a document check."""
    groups = {name: check.group(name) for name in GROUPS}
    tiles = "".join(
        f'<div class="tile {name}"><strong>{len(groups[name])}</strong>'
        f"<span>{_SUMMARY_LABELS[name]}</span></div>"
        for name in GROUPS
    )
    body = [
        '<header><p class="kicker">NormaAI, controllo del documento</p>',
        f"<h1>{escape(check.document or 'Documento')}</h1>",
        f'<p class="meta">Controllato il {_italian_date(check.checked_on)} sui testi consolidati '
        f"di EUR-Lex. Data del documento: {_italian_date(check.document_date)}.</p></header>",
        f'<section class="summary" aria-label="Riepilogo">{tiles}</section>',
    ]
    if not check.findings:
        body.append("<p>Nel documento non ho trovato riferimenti ad articoli di legge.</p>")
    for name in ("correggere", "controllare"):
        if groups[name]:
            body.append(f"<section><h2>{GROUP_TITLES[name]}</h2>")
            body.extend(_card(f) for f in groups[name])
            body.append("</section>")
    if groups["a_posto"]:
        body.append(f"<section><h2>{GROUP_TITLES['a_posto']}</h2>{_fine_table(groups['a_posto'])}")
        body.append("</section>")
    if groups["non_coperto"]:
        body.append(
            f"<section><h2>{GROUP_TITLES['non_coperto']}</h2>"
            "<p>NormaAI non ha ancora i testi italiani: questi riferimenti vanno controllati a mano."
            f"</p>{_italian_table(groups['non_coperto'])}</section>"
        )
    if lock_name:
        watched = len({(f.act.key, f.article.key) for f in check.findings if f.act and f.article})
        body.append(
            "<section><h2>Sorveglianza</h2>"
            f"<p>{watched} disposizioni registrate nel file <code>{escape(lock_name)}</code>, con il "
            "testo di oggi. Per sapere più avanti quali sono cambiate: "
            f"<code>python scripts/check_document.py --ricontrolla {escape(lock_name)}</code>.</p>"
            "</section>"
        )
    return _page(f"Controllo: {check.document}", "".join(body))


_CHANGE_TITLES = {
    "cambiato": "Cambiato",
    "soppresso": "Non c'è più",
    "non_disponibile": "Non controllato",
    "invariato": "Invariato",
}
_CHANGE_GROUPS = {
    "cambiato": "correggere",
    "soppresso": "correggere",
    "non_disponibile": "controllare",
    "invariato": "a_posto",
}


def render_recheck_html(lock: dict[str, object], changes: list[Change], today: str) -> str:
    """The report of a re-check: which provisions of a document changed since its lock file."""
    document = str(lock.get("documento") or "Documento")
    first_check = _italian_date(str(lock.get("controllato_il") or "") or None)
    counts = {code: sum(c.code == code for c in changes) for code in _CHANGE_TITLES}
    tiles = "".join(
        f'<div class="tile {_CHANGE_GROUPS[code]}"><strong>{counts[code]}</strong>'
        f"<span>{_CHANGE_TITLES[code].lower()}</span></div>"
        for code in _CHANGE_TITLES
    )
    body = [
        '<header><p class="kicker">NormaAI, ricontrollo delle disposizioni citate</p>',
        f"<h1>{escape(document)}</h1>",
        f'<p class="meta">Primo controllo il {first_check}; ricontrollo il {_italian_date(today)}.'
        "</p></header>",
        f'<section class="summary" aria-label="Riepilogo">{tiles}</section>',
    ]
    for change in changes:
        entry = change.entry
        group = _CHANGE_GROUPS[change.code]
        refs = "; ".join(str(r) for r in entry.get("riferimenti", []))
        parts = [
            f'<article class="card {group}"><div class="card-head">',
            f'<span class="pill">{escape(_CHANGE_TITLES[change.code])}</span>',
            f"<h3>{escape(str(entry.get('nome')))}, {escape(str(entry.get('articolo')))}</h3></div>",
            f'<p class="where">Nel documento: {escape(refs)}</p>',
            f"<ul><li>{escape(change.message)}</li></ul>",
        ]
        if change.before and change.after:
            old_label = f"testo del {first_check}"
            parts.append(
                '<div class="diff">'
                f"<p><strong>Differenze tra il {escape(old_label)} e il "
                f"{escape(change.version.label if change.version else 'testo vigente')}</strong></p>"
                f"<p>{diff_html(change.before, change.after)}</p></div>"
            )
        if change.version:
            parts.append(
                f'<p><a href="{escape(change.version.url(str(entry.get("lingua") or "IT")))}">'
                "Testo vigente su EUR-Lex</a></p>"
            )
        parts.append("</article>")
        body.append("".join(parts))
    return _page(f"Ricontrollo: {document}", "".join(body))


def summary_lines(check: DocumentCheck) -> list[str]:
    """A short plain-text summary for the terminal."""
    counts = {name: len(check.group(name)) for name in GROUPS}
    lines = [
        f"Controllo di {check.document or 'documento'} ({_italian_date(check.checked_on)}): "
        f"{len(check.findings)} disposizioni citate.",
        ", ".join(f"{counts[n]} {_SUMMARY_LABELS[n]}" for n in GROUPS) + ".",
    ]
    for f in check.findings:
        if f.status.group in ("correggere", "controllare"):
            lines.append(f"- riga {f.reference.line}, {_title(f)}: {f.status.label}")
    return lines
