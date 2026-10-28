"""Compare a document's references with the official text in force.

For every reference ``extract`` finds:

1. Italian law, or no act at all: reported as such. NormaAI has no Italian
   texts yet, and a reference without an act cannot be checked.
2. The provision must exist in the version in force (the latest consolidated
   text), and so must each cited paragraph. A provision missing today but
   present in an earlier version was repealed or renumbered.
3. Each quote goes through the production verifier
   (src/agents/citation_verifier.py: same normalisation, same thresholds): in
   the cited provision, then elsewhere in the act, then in the earlier
   versions, newest first. A quote found only in an earlier version is
   outdated, and the report shows the provision then and now.
4. When the document's date is known, the provision in force on that date is
   compared with today's: a change means the document rests on the old text.

The worst outcome gives a provision its status. Every provision found in force
becomes a dependency in the lock file (version, text, SHA-256 of the normalised
text); ``recheck`` compares a lock file with the versions in force later and
says which provisions changed, so a consultant knows which documents to redo.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from src.agents.citation_verifier import (
    MIN_QUOTE_CHARS,
    MIN_QUOTE_WORDS,
    VerificationResult,
    normalize,
    parse_article,
    verify_citation,
)
from src.document_check.extract import (
    ACT_NAMES,
    Act,
    Provision,
    Reference,
    detect_language,
    extract_references,
)
from src.document_check.official import (
    ArticleText,
    TextSource,
    TextUnavailableError,
    Version,
    find_article,
)

# ─── Statuses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Status:
    code: str
    label: str
    group: str  # "correggere" | "controllare" | "a_posto" | "non_coperto"


OUTDATED = Status("superata", "Citazione superata", "correggere")
CHANGED = Status("cambiato", "Cambiato dopo la data del documento", "correggere")
MISSING = Status("inesistente", "Non esiste nel testo vigente", "correggere")
NOT_FOUND = Status("non_trovata", "Citazione non trovata", "correggere")
ELSEWHERE = Status("altro_articolo", "Citazione in un altro articolo", "controllare")
UNAVAILABLE = Status("non_disponibile", "Testo ufficiale non raggiungibile", "controllare")
NO_ACT = Status("atto_mancante", "Atto non indicato", "controllare")
VALID = Status("valido", "Riferimento valido", "a_posto")
VERIFIED = Status("verificata", "Citazione verificata", "a_posto")
NOT_COVERED = Status("non_coperto", "Diritto italiano, non ancora coperto", "non_coperto")

# Worst first: a provision keeps the worst outcome of its checks.
_ORDER = (OUTDATED, CHANGED, MISSING, NOT_FOUND, ELSEWHERE, UNAVAILABLE, NO_ACT, VALID, VERIFIED)
GROUPS = ("correggere", "controllare", "a_posto", "non_coperto")


def _worse(a: Status, b: Status) -> Status:
    if a not in _ORDER or b not in _ORDER:
        return a
    return a if _ORDER.index(a) <= _ORDER.index(b) else b


# ─── Results ─────────────────────────────────────────────────────────


@dataclass
class Finding:
    """The outcome for one provision of one reference."""

    reference: Reference
    provision: Provision | None
    act: Act | None
    status: Status
    messages: list[str] = field(default_factory=list)
    lang: str = "IT"
    version: Version | None = None  # the version in force that was checked
    article: ArticleText | None = None  # the provision in force, when found
    official_quote: str | None = None  # the official words a quote matched
    before: str | None = None  # the provision in an earlier version (outdated, changed)
    before_version: Version | None = None
    shows_quotes: bool = False  # the first finding of a reference shows its quotes

    @property
    def act_name(self) -> str:
        if self.act is None:
            return "Atto non indicato"
        return ACT_NAMES.get(self.act.key, self.act.label)

    @property
    def url(self) -> str | None:
        if self.act is None:
            return None
        if not self.act.eu:
            return self.act.normattiva_url
        return self.version.url(self.lang) if self.version else None


@dataclass
class DocumentCheck:
    """The outcome for a whole document."""

    document: str
    checked_on: str
    document_date: str | None
    lang: str
    findings: list[Finding]

    def group(self, name: str) -> list[Finding]:
        return [f for f in self.findings if f.status.group == name]


# ─── Checking ────────────────────────────────────────────────────────


def fingerprint(text: str) -> str:
    """SHA-256 of a provision's normalised text: the same words give the same print."""
    return "sha256:" + hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()


def _italian_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def _readable_at(
    versions: list[Version], day: str, source: TextSource, lang: str
) -> tuple[Version, list[ArticleText]] | None:
    """The newest version in force on ``day`` whose text CELLAR gives.

    A consolidated text without an XHTML manifestation falls back to the one
    before it, down to the act as adopted.
    """
    candidates = [v for v in versions if v.as_of is None or v.as_of <= day]
    for version in reversed(candidates):
        try:
            return version, source.articles(version, lang)
        except TextUnavailableError:
            continue
    return None


_PARAGRAPH_START = re.compile(r"(?m)^[ \t]*(\d{1,3})\.[ \t]+")


def paragraph_text(text: str, number: str) -> str | None:
    """Numbered paragraph ``number`` of an article, up to the next numbered paragraph."""
    starts = list(_PARAGRAPH_START.finditer(text))
    for i, m in enumerate(starts):
        if m.group(1) == number:
            end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
            return text[m.start() : end].strip()
    return None


def _day_before(iso: str) -> str:
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


def _specific_enough(quote: str) -> bool:
    text = normalize(quote)
    return len(text) >= MIN_QUOTE_CHARS and len(text.split()) >= MIN_QUOTE_WORDS


def _verify(
    quote: str, provision: Provision, act: Act, version: Version, articles: list[ArticleText]
) -> VerificationResult:
    chunks: list[dict[str, Any]] = [
        {
            "text": a.text,
            "celex": act.key,
            "source_celex": version.celex,
            "article": a.label,
            "framework": act.key,
        }
        for a in articles
    ]
    return verify_citation(
        {"framework": act.key, "reference": provision.label, "quote_snippet": quote}, chunks
    )


def _capitalized(label: str) -> str:
    return label[:1].upper() + label[1:]


def _check_provision(
    ref: Reference,
    provision: Provision,
    act: Act,
    versions: list[Version],
    in_force: list[ArticleText],
    source: TextSource,
    lang: str,
    document_date: str | None,
) -> Finding:
    current = versions[-1]
    finding = Finding(ref, provision, act, VALID, lang=lang, version=current)
    name = _capitalized(Provision(provision.key).label)
    article = find_article(in_force, provision.key)
    if article is None:
        finding.status = MISSING
        for version in reversed(versions[:-1]):
            try:
                earlier = find_article(source.articles(version, lang), provision.key)
            except TextUnavailableError:
                continue
            if earlier is not None:
                finding.before, finding.before_version = earlier.text, version
                finding.messages.append(
                    f"{name} non c'è nel {current.label}; c'era nel {version.label}: "
                    "è stato abrogato o rinumerato."
                )
                break
        else:
            finding.messages.append(f"{name} non esiste nel {current.label} ({act.label}).")
        return finding

    finding.article = article
    missing = [p for p in provision.paragraphs if p not in article.paragraphs]
    if not article.paragraphs:
        # An article without numbered paragraphs is its own paragraph 1.
        missing = [p for p in missing if p != "1"]
    if missing:
        finding.status = MISSING
        have = (
            f"ha i paragrafi da {article.paragraphs[0]} a {article.paragraphs[-1]}"
            if article.paragraphs
            else "non ha paragrafi numerati"
        )
        word = "Il paragrafo" if len(missing) == 1 else "I paragrafi"
        verb = "non esiste" if len(missing) == 1 else "non esistono"
        finding.messages.append(
            f"{word} {', '.join(missing)} {verb} nel {current.label}: "
            f"l'{Provision(provision.key).label} {have}."
        )
    else:
        finding.messages.append(f"{_capitalized(provision.label)} esiste nel {current.label}.")

    if document_date and not missing:
        _compare_with_date(finding, provision, article, versions, source, lang, document_date)
    return finding


def _compare_with_date(
    finding: Finding,
    provision: Provision,
    article: ArticleText,
    versions: list[Version],
    source: TextSource,
    lang: str,
    document_date: str,
) -> None:
    """Say whether the cited provision changed between the document's date and today."""
    current = versions[-1]
    name = _capitalized(Provision(provision.key).label)
    day = _italian_date(document_date)
    readable = _readable_at(versions, document_date, source, lang)
    if readable is None:
        finding.messages.append("Testo alla data del documento non disponibile.")
        return
    then, articles = readable
    if then.celex == current.celex:
        return
    old = find_article(articles, provision.key)
    if old is None:
        finding.messages.append(
            f"Alla data del documento ({day}) {name} non c'era ancora: è stato inserito dopo."
        )
        return
    if normalize(old.text) == normalize(article.text):
        return
    cited = [p for p in provision.paragraphs if article.paragraphs]
    changed = [
        p
        for p in cited
        if normalize(paragraph_text(old.text, p) or "")
        != normalize(paragraph_text(article.text, p) or "")
    ]
    if cited and not changed:
        finding.messages.append(
            f"{name} è cambiato dopo la data del documento ({day}), ma non nella parte citata."
        )
        return
    finding.status = _worse(finding.status, CHANGED)
    finding.before, finding.before_version = old.text, then
    finding.messages.append(
        f"{_capitalized(provision.label)} è cambiato dopo la data del documento ({day}): il "
        f"documento si basa sul {then.label}, oggi vale il {current.label}."
    )


def _check_quotes(
    ref: Reference,
    findings: list[Finding],
    act: Act,
    versions: list[Version],
    in_force: list[ArticleText],
    source: TextSource,
    lang: str,
) -> None:
    current = versions[-1]
    first = findings[0]
    for quote in ref.quotes:
        if not _specific_enough(quote):
            first.messages.append("Citazione troppo breve per una verifica parola per parola.")
            continue
        exact: tuple[Finding, VerificationResult] | None = None
        for f in findings:
            if f.provision is None:
                continue
            r = _verify(quote, f.provision, act, current, in_force)
            if r.verified and r.level == "article":
                exact = (f, r)
                break
        if exact is not None:
            finding, result = exact
            if finding.status is VALID:
                finding.status = VERIFIED
            finding.official_quote = result.official_quote
            finding.messages.append(
                "La citazione è nel testo vigente, parola per parola."
                if result.match == "exact"
                else "La citazione è nel testo vigente, con piccole differenze di punteggiatura."
            )
            continue
        provision = first.provision or Provision("art:0")
        result = _verify(quote, provision, act, current, in_force)
        if result.verified:
            first.status = _worse(first.status, ELSEWHERE)
            first.official_quote = result.official_quote
            where = result.article or "un'altra parte dell'atto"
            first.messages.append(
                f"La citazione è nel testo vigente, ma in {where}, non nella disposizione citata."
            )
            continue
        # The quote stopped matching at the oldest newer version that lacks it.
        newer_without = current
        for version in reversed(versions[:-1]):
            try:
                articles = source.articles(version, lang)
            except TextUnavailableError:
                continue
            old = _verify(quote, provision, act, version, articles)
            if not old.verified:
                newer_without = version
                continue
            key = parse_article(old.article) or provision.key
            then = find_article(articles, key)
            now = find_article(in_force, key)
            first.status = _worse(first.status, OUTDATED)
            first.before, first.before_version = (then.text if then else None), version
            if first.article is None and now is not None:
                first.article = now
            until = _day_before(newer_without.as_of) if newer_without.as_of else None
            period = f", in vigore fino al {_italian_date(until)}" if until else ""
            first.messages.append(
                f"La citazione corrisponde al {version.label}{period}, non al testo vigente: "
                "la disposizione è cambiata."
            )
            break
        else:
            first.status = _worse(first.status, NOT_FOUND)
            first.messages.append(
                "La citazione non è nel testo vigente né nelle versioni precedenti: può essere "
                "una parafrasi o un errore."
            )


def _check_reference(
    ref: Reference, source: TextSource, lang: str, document_date: str | None
) -> list[Finding]:
    act = ref.act
    if act is None:
        return [
            Finding(
                ref,
                None,
                None,
                NO_ACT,
                ["Il documento non dice di quale atto è questo riferimento."],
                lang=lang,
                shows_quotes=True,
            )
        ]
    if not act.eu:
        findings = [
            Finding(
                ref,
                provision,
                act,
                NOT_COVERED,
                ["NormaAI non ha ancora i testi italiani: da controllare su Normattiva."],
                lang=lang,
            )
            for provision in ref.provisions
        ]
        findings[0].shows_quotes = True
        return findings
    try:
        versions = source.versions(act.key)
        in_force = source.articles(versions[-1], lang)
    except TextUnavailableError as e:
        findings = [
            Finding(ref, provision, act, UNAVAILABLE, [f"{e}."], lang=lang)
            for provision in ref.provisions
        ]
        findings[0].shows_quotes = True
        return findings
    findings = [
        _check_provision(ref, provision, act, versions, in_force, source, lang, document_date)
        for provision in ref.provisions
    ]
    findings[0].shows_quotes = True
    _check_quotes(ref, findings, act, versions, in_force, source, lang)
    if ref.act_inferred:
        for finding in findings:
            finding.messages.append(f"Atto dedotto dal contesto: {act.label}.")
    return findings


def check_text(
    text: str,
    source: TextSource,
    *,
    document: str = "",
    lang: str | None = None,
    document_date: str | None = None,
    today: str | None = None,
) -> DocumentCheck:
    """Check every reference in ``text``; ``document_date`` is ISO (YYYY-MM-DD) or None."""
    lang = (lang or detect_language(text)).upper()
    findings: list[Finding] = []
    for ref in extract_references(text):
        findings.extend(_check_reference(ref, source, lang, document_date))
    return DocumentCheck(
        document=document,
        checked_on=today or date.today().isoformat(),
        document_date=document_date,
        lang=lang,
        findings=findings,
    )


# ─── Lock file and re-check ──────────────────────────────────────────


def build_lock(check: DocumentCheck) -> dict[str, Any]:
    """The provisions a document depends on, as found in force on the day of the check."""
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for f in check.findings:
        if f.article is None or f.version is None or f.act is None or not f.act.eu:
            continue
        key = (f.act.key, f.article.key)
        entry = entries.get(key)
        if entry is None:
            entries[key] = {
                "atto": f.act.key,
                "nome": f.act_name,
                "versione": f.version.celex,
                "consolidato_al": f.version.as_of,
                "articolo": f.article.label,
                "chiave": f.article.key,
                "lingua": f.lang,
                "impronta": fingerprint(f.article.text),
                "testo": f.article.text,
                "riferimenti": [f.reference.raw],
            }
        elif f.reference.raw not in entry["riferimenti"]:
            entry["riferimenti"].append(f.reference.raw)
    return {
        "documento": check.document,
        "controllato_il": check.checked_on,
        "data_documento": check.document_date,
        "lingua": check.lang,
        "dipendenze": list(entries.values()),
    }


@dataclass
class Change:
    """What happened to one dependency of a lock file since it was written."""

    entry: dict[str, Any]
    code: str  # "invariato" | "cambiato" | "soppresso" | "non_disponibile"
    message: str
    version: Version | None = None
    before: str | None = None
    after: str | None = None


def recheck(lock: dict[str, Any], source: TextSource) -> list[Change]:
    """Compare a lock file's provisions with the versions in force now."""
    changes: list[Change] = []
    for entry in lock.get("dipendenze", []):
        lang = str(entry.get("lingua") or "IT")
        try:
            versions = source.versions(entry["atto"])
            current = versions[-1]
            if current.celex == entry["versione"]:
                changes.append(
                    Change(entry, "invariato", f"Nessuna versione nuova dopo il {current.label}.")
                )
                continue
            article = find_article(source.articles(current, lang), entry["chiave"])
        except TextUnavailableError as e:
            changes.append(Change(entry, "non_disponibile", f"{e}."))
            continue
        if article is None:
            changes.append(
                Change(
                    entry,
                    "soppresso",
                    f"{entry['articolo']} non c'è più nel {current.label}.",
                    current,
                    entry.get("testo"),
                )
            )
        elif fingerprint(article.text) != entry["impronta"]:
            changes.append(
                Change(
                    entry,
                    "cambiato",
                    f"{entry['articolo']} è cambiato nel {current.label}.",
                    current,
                    entry.get("testo"),
                    article.text,
                )
            )
        else:
            changes.append(
                Change(
                    entry,
                    "invariato",
                    f"C'è il {current.label}, ma {entry['articolo']} è uguale.",
                    current,
                )
            )
    return changes
