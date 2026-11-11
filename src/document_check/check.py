"""Compare a document's references with the official text in force.

For every reference ``extract`` finds:

1. No act at all, or an act the check does not read (a regional law, a
   ministerial decree, a circular): reported as such. An Italian act is read
   on Normattiva, article by article (see "Italian law" below); the steps that
   follow are those of an EU act.
2. The provision must exist in the version in force (the latest consolidated
   text), and so must each cited paragraph. A provision missing today but
   present in an earlier version was repealed or renumbered.
3. Each quote goes through the production verifier
   (src/agents/citation_verifier.py: same normalisation, same thresholds): in
   the cited provision, then elsewhere in the act, then in the earlier
   versions, newest first. A quote found only in an earlier version is
   outdated, and the report shows the provision then and now. A quote that is
   in no version but differs from the text in force only by a few words (a
   number, a "non") is altered: the report shows the words that differ.
4. When the document's date is known, the provision in force on that date is
   compared with today's: a change means the document rests on the old text.
5. CELLAR does not give every consolidated version as text. The check reads
   the newest version it can. When the unread versions are only the snapshot
   of the act as published, that is the same wording and a note says so; when
   a later consolidated text could not be read, the provision is to be checked
   by hand.

Italian law. Normattiva gives one article per request, as in force on a day,
with the days between which that wording holds. The article must exist and be
in force today, and so must each cited comma; a repealed article is reported
with its last wording. A quote is verified against the article in force today;
failing that against its earlier wordings (the one in force on the document's
date, the ones before today's, the original): found there, it is outdated.
With a document date, a wording that started after that date is compared with
the one in force then. A wording whose last day is already set (a repeal or an
amendment published but not yet in force) is reported too. Only the cited
articles are read, never the whole act.

The worst outcome gives a provision its status. Every provision found in force
becomes a dependency in the lock file (source, version, text, SHA-256 of the
normalised text); ``recheck`` compares a lock file with the texts in force
later and says which provisions changed, so a consultant knows which documents
to redo.
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
    same_article,
    verify_citation,
)
from src.document_check.extract import (
    ACT_NAMES,
    Act,
    Provision,
    Reference,
    detect_language,
    extract_references,
    paragraph_label,
)
from src.document_check.normattiva import (
    IN_FORCE,
    NOT_IN_FORCE,
    PART_SIZE,
    REPEALED,
    ActNotFoundError,
    ArticleNotFoundError,
    ItalianArticle,
    ItalianTextSource,
    ItalianVersion,
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
ALTERED = Status("alterata", "Citazione diversa dal testo ufficiale", "correggere")
NOT_FOUND = Status("non_trovata", "Citazione non trovata", "correggere")
ELSEWHERE = Status("altro_articolo", "Citazione in un altro articolo", "controllare")
UNAVAILABLE = Status("non_disponibile", "Testo ufficiale non raggiungibile", "controllare")
UNREAD = Status("versione_non_letta", "Versione più recente non leggibile", "controllare")
NO_ACT = Status("atto_mancante", "Atto non indicato", "controllare")
VALID = Status("valido", "Riferimento valido", "a_posto")
VERIFIED = Status("verificata", "Citazione verificata", "a_posto")
NOT_COVERED = Status("non_coperto", "Atto che il controllo non legge", "non_coperto")
# Italian law only (Normattiva).
ACT_UNCLEAR = Status("atto_da_controllare", "Estremi dell'atto da controllare", "controllare")
PARTIAL = Status("letto_in_parte", "Articolo letto solo in parte", "controllare")
SCHEDULED = Status(
    "modifica_pubblicata", "Modifica pubblicata, non ancora in vigore", "controllare"
)
RULING = Status("sentenza_in_nota", "Sentenza della Corte costituzionale in nota", "controllare")

# Worst first: a provision keeps the worst outcome of its checks.
_ORDER = (
    OUTDATED,
    CHANGED,
    MISSING,
    ALTERED,
    NOT_FOUND,
    ELSEWHERE,
    UNAVAILABLE,
    UNREAD,
    ACT_UNCLEAR,
    PARTIAL,
    SCHEDULED,
    RULING,
    NO_ACT,
    VALID,
    VERIFIED,
)
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
    # An altered quote: the document's words and how they differ from ``official_quote``.
    altered_quote: str | None = None
    differences: list[dict[str, str]] = field(default_factory=list)

    @property
    def act_name(self) -> str:
        if self.act is None:
            return "Atto non indicato"
        return ACT_NAMES.get(self.act.key, self.act.label)

    @property
    def url(self) -> str | None:
        if self.act is None:
            return None
        if not self.act.eu and self.version is None:
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
        # Close to the text in force but with different words: kept for the
        # end, an earlier version may have the quote word for word.
        near = result if result.differences else None
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
            if near is not None:
                _mark_altered(first, quote, near, provision)
                continue
            first.status = _worse(first.status, NOT_FOUND)
            first.messages.append(
                "La citazione non è nel testo vigente né nelle versioni precedenti: può essere "
                "una parafrasi o un errore."
            )


def _describe_differences(differences: list[dict[str, str]]) -> str:
    parts: list[str] = []
    for difference in differences:
        quoted, official = difference.get("quoted", ""), difference.get("official", "")
        if quoted and official:
            parts.append(f"nel documento «{quoted}», nel testo ufficiale «{official}»")
        elif official:
            parts.append(f"nel documento manca «{official}»")
        elif quoted:
            parts.append(f"nel testo ufficiale non c'è «{quoted}»")
    return "; ".join(parts)


def _mark_altered(
    finding: Finding, quote: str, near: VerificationResult, provision: Provision
) -> None:
    """A quote that differs from the text in force by a few words that matter."""
    finding.status = _worse(finding.status, ALTERED)
    finding.altered_quote = quote
    finding.official_quote = near.near_quote
    finding.differences = list(near.differences or [])
    elsewhere = near.near_article and not same_article(
        parse_article(near.near_article), provision.key
    )
    where = f" (trovato in {near.near_article})" if elsewhere else ""
    finding.messages.append(
        f"La citazione è diversa dal testo vigente{where}: "
        f"{_describe_differences(finding.differences)}."
    )


def _newest_readable(
    versions: list[Version], source: TextSource, lang: str
) -> tuple[int, list[ArticleText]] | None:
    """Index and articles of the newest version whose text the source gives."""
    for index in range(len(versions) - 1, -1, -1):
        try:
            return index, source.articles(versions[index], lang)
        except TextUnavailableError:
            continue
    return None


def _note_unread(findings: list[Finding], read: Version, unread: list[Version]) -> None:
    """Say which newer versions could not be read, and whether that matters."""
    newest = unread[-1]
    if read.as_of is None and all(v.initial for v in unread):
        note = (
            f"CELLAR non dà come testo il {newest.label}, che è l'atto come pubblicato: "
            f"il controllo è fatto sul {read.label}, che ha le stesse parole."
        )
        for finding in findings:
            finding.messages.append(note)
        return
    note = (
        f"Esiste il {newest.label}, che CELLAR non dà come testo in questa lingua: il "
        f"controllo è fatto sul {read.label} e va ripetuto su EUR-Lex."
    )
    for finding in findings:
        finding.status = _worse(finding.status, UNREAD)
        finding.messages.append(note)


def _check_reference(
    ref: Reference, source: TextSource, lang: str, document_date: str | None, today: str
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
        italian: ItalianTextSource | None = getattr(source, "italian", None)
        if italian is not None and act.urn:
            return _check_italian(ref, act, italian, document_date, today)
        reason = act.not_read or "Questa fonte non legge i testi italiani"
        findings = [
            Finding(ref, provision, act, NOT_COVERED, [f"{reason}: da controllare a mano."])
            for provision in ref.provisions
        ]
        findings[0].shows_quotes = True
        return findings

    def unavailable(reason: str) -> list[Finding]:
        out = [
            Finding(ref, provision, act, UNAVAILABLE, [f"{reason}."], lang=lang)
            for provision in ref.provisions
        ]
        out[0].shows_quotes = True
        return out

    try:
        versions = source.versions(act.key)
    except TextUnavailableError as e:
        return unavailable(str(e))
    readable = _newest_readable(versions, source, lang)
    if readable is None:
        return unavailable(f"CELLAR non ha nessun testo di {act.label} in {lang}")
    index, in_force = readable
    # Newer versions that could not be read are set aside: everything below
    # treats the newest readable version as the text in force, and says so.
    unread, versions = versions[index + 1 :], versions[: index + 1]
    findings = [
        _check_provision(ref, provision, act, versions, in_force, source, lang, document_date)
        for provision in ref.provisions
    ]
    findings[0].shows_quotes = True
    _check_quotes(ref, findings, act, versions, in_force, source, lang)
    if unread:
        _note_unread(findings, versions[-1], unread)
    stale = getattr(source, "stale", {}).get(act.key)
    if stale:
        for finding in findings:
            finding.messages.append(
                "Oggi CELLAR non ha dato l'elenco delle versioni: usato quello del "
                f"{_italian_date(stale)}."
            )
    if ref.act_inferred:
        for finding in findings:
            finding.messages.append(f"Atto dedotto dal contesto: {act.label}.")
    return findings


# ─── Italian law (Normattiva) ────────────────────────────────────────

# Earlier wordings of an article read, newest first, to place a quote that is
# not in the text in force.
MAX_EARLIER = 5
# The first article of an act that only approves a text kept in an annex.
_APPROVAL_RE = re.compile(
    r"\b[EÈ]['’]?\s+approvat[oa]\s+(?:l['’]\s?unit[oa]|l['’]\s?allegat[oa]|il)\s+"
    r"(?:testo|codice|regolamento)",
    re.IGNORECASE,
)


# "La Corte Costituzionale, con sentenza 7 aprile - 19 maggio 2022, n. 125 (...), ha
# dichiarato l'illegittimità costituzionale ...": how Normattiva's notes report a ruling.
_RULING_RE = re.compile(
    r"Corte\s+costituzionale,?\s+con\s+sentenza\s+(?P<dates>[^()]{0,80}?)\b(?P<year>\d{4}),?\s*"
    r"n\.\s*(?P<number>\d+)",
    re.IGNORECASE,
)


def _day_after(iso: str) -> str:
    return (date.fromisoformat(iso) + timedelta(days=1)).isoformat()


def _note_rulings(finding: Finding, provision: Provision, now: ItalianArticle) -> None:
    """Flag an article whose notes on Normattiva report a ruling of unconstitutionality.

    Normattiva leaves the wording as it is and reports the ruling under the
    article: a quote can be word for word and still be of a wording the Court
    struck down.
    """
    rulings: list[str] = []
    for note in now.notes.split("\n"):
        if not re.search(r"illegittimit[aà]'?\s+costituzionale", note, re.IGNORECASE):
            continue
        for m in _RULING_RE.finditer(note):
            ruling = f"n. {m.group('number')}/{m.group('year')}"
            if ruling not in rulings:
                rulings.append(ruling)
    if not rulings:
        return
    name = Provision(provision.key).label
    one = len(rulings) == 1
    finding.status = _worse(finding.status, RULING)
    finding.messages.append(
        f"Sotto l'{name} Normattiva riporta {'la sentenza' if one else 'le sentenze'} della Corte "
        f"costituzionale {', '.join(rulings)}, che ne {'dichiara' if one else 'dichiarano'} "
        "l'illegittimità in tutto o in parte: il testo su Normattiva non ne tiene conto, vanno "
        "lette le note."
    )


def _commi(commi: list[str]) -> str:
    """ "il comma 1-bis", "i commi 2, 3"."""
    names = ", ".join(paragraph_label(c) for c in commi)
    return f"il comma {names}" if len(commi) == 1 else f"i commi {names}"


def _verify_in(quote: str, act: Act, article: ArticleText) -> VerificationResult:
    """The production verifier on one article (the only text read of an Italian act)."""
    chunk: dict[str, Any] = {
        "text": article.text,
        "celex": act.key,
        "article": article.label,
        "framework": act.key,
    }
    citation = {"framework": act.key, "reference": article.label, "quote_snippet": quote}
    return verify_citation(citation, [chunk])


def _wording_before(italian: ItalianTextSource, article: ItalianArticle) -> ItalianArticle | None:
    """The wording in force the day before ``article`` started, when there was one."""
    if not article.start:
        return None
    try:
        earlier = italian.article(article.urn, article.key, _day_before(article.start))
    except (LookupError, TextUnavailableError):
        return None
    return earlier if earlier.state == IN_FORCE else None


def _last_wording(italian: ItalianTextSource, repealed: ItalianArticle) -> ItalianArticle | None:
    """The last wording a repealed article had.

    A repeal by decree-law and its confirmation by the converting law are two
    entries on Normattiva: the walk back goes past them.
    """
    current = repealed
    for _ in range(3):
        if not current.start:
            return None
        try:
            earlier = italian.article(current.urn, current.key, _day_before(current.start))
        except (LookupError, TextUnavailableError):
            return None
        if earlier.state == IN_FORCE:
            return earlier
        if earlier.state != REPEALED:
            return None
        current = earlier
    return None


def _changed_commi(
    cited: tuple[str, ...], before: ItalianArticle, after: ItalianArticle
) -> tuple[list[str], list[str]]:
    """Of the cited commi, those that differ between two wordings and those not read.

    A comma differs when its words changed or when only one wording has it. A
    comma of a long article given in part is in neither wording: nothing can be
    said of it.
    """
    changed: list[str] = []
    unread: list[str] = []
    for comma in cited:
        old, new = before.comma_texts.get(comma), after.comma_texts.get(comma)
        if old is None and new is None:
            if after.partial or before.partial:
                unread.append(comma)
        elif old is None or new is None or normalize(old) != normalize(new):
            changed.append(comma)
    return changed, unread


def _earlier_wordings(
    italian: ItalianTextSource, now: ItalianArticle, document_date: str | None
) -> list[ItalianArticle]:
    """Wordings a quote may come from: at the document's date, before today's, the original."""
    found: list[ItalianArticle] = []
    seen = {now.start}

    def add(article: ItalianArticle | None) -> None:
        if article is not None and article.state == IN_FORCE and article.start not in seen:
            seen.add(article.start)
            found.append(article)

    if document_date and now.start and document_date < now.start:
        try:
            add(italian.article(now.urn, now.key, document_date))
        except (LookupError, TextUnavailableError):
            pass
    current = now
    for _ in range(MAX_EARLIER):
        earlier = _wording_before(italian, current)
        if earlier is None:
            break
        add(earlier)
        current = earlier
    try:
        add(italian.original(now.urn, now.key))
    except (LookupError, TextUnavailableError):
        pass
    return found


def _check_commi(finding: Finding, provision: Provision, now: ItalianArticle) -> None:
    """Every cited comma must be in the article in force."""
    label = Provision(provision.key).label
    current = finding.version.label if finding.version else "testo vigente"
    missing = [p for p in provision.paragraphs if p not in now.commi]
    unread: list[str] = []
    if now.partial:
        unread = [p for p in missing if int((re.match(r"\d+", p) or [0])[0]) > PART_SIZE]
        missing = [p for p in missing if p not in unread]
    if unread:
        verb = (
            "non è stato letto e va controllato"
            if len(unread) == 1
            else "non sono stati letti e vanno controllati"
        )
        finding.status = _worse(finding.status, PARTIAL)
        finding.messages.append(
            f"Su Normattiva l'{label} è diviso in più parti e l'API ne dà solo la prima "
            f"(commi da 1 a {PART_SIZE}): {_commi(unread)} {verb} a mano."
        )
    if missing:
        if now.numbered and now.commi:
            first, last = paragraph_label(now.commi[0]), paragraph_label(now.commi[-1])
            have = f"ha i commi da {first} a {last}" if first != last else "ha un solo comma"
        elif len(now.commi) == 1:
            have = "ha un solo comma"
        else:
            have = f"ha {len(now.commi)} commi, non numerati"
        verb = "non esiste" if len(missing) == 1 else "non esistono"
        finding.status = _worse(finding.status, MISSING)
        finding.messages.append(
            f"{_capitalized(_commi(missing))} {verb} nel {current}: l'{label} {have}."
        )
    elif not unread:
        finding.messages.append(
            f"{_capitalized(provision.label)} esiste nel {current} su Normattiva."
        )


def _note_scheduled(
    finding: Finding, provision: Provision, now: ItalianArticle, italian: ItalianTextSource
) -> None:
    """A wording whose last day is set: a repeal or an amendment already published."""
    if not now.end:
        return
    label = Provision(provision.key).label
    start = _day_after(now.end)
    try:
        coming: ItalianArticle | None = italian.article(now.urn, now.key, start)
    except (LookupError, TextUnavailableError):
        coming = None
    if coming is not None and coming.state == REPEALED:
        what = f"l'{label} risulta abrogato. Normattiva riporta: «{coming.repeal_note}»"
    elif coming is None or coming.state != IN_FORCE:
        what = f"l'{label} ha un testo diverso, già pubblicato"
    elif normalize(coming.text) == normalize(now.text):
        return  # the same words: only Normattiva's notes change
    else:
        changed, unread = _changed_commi(provision.paragraphs, now, coming)
        if provision.paragraphs and not changed:
            rest = "; i commi non letti restano da controllare" if unread else ""
            finding.messages.append(
                f"Dal {_italian_date(start)} l'{label} ha un testo diverso, già pubblicato, ma "
                f"non nei commi citati{rest}."
            )
            return
        what = f"l'{label} ha un testo diverso, già pubblicato"
    finding.status = _worse(finding.status, SCHEDULED)
    finding.messages.append(f"Dal {_italian_date(start)} {what}.")


def _compare_italian_with_date(
    finding: Finding,
    provision: Provision,
    now: ItalianArticle,
    italian: ItalianTextSource,
    document_date: str,
) -> None:
    """Say whether the cited article changed between the document's date and today."""
    if not now.start or now.start <= document_date:
        return  # today's wording was already in force on the document's date
    name = _capitalized(Provision(provision.key).label)
    day = _italian_date(document_date)
    try:
        then = italian.article(now.urn, now.key, document_date)
    except (LookupError, TextUnavailableError):
        finding.messages.append("Testo alla data del documento non disponibile.")
        return
    if then.state != IN_FORCE:
        finding.messages.append(
            f"Alla data del documento ({day}) {name} non era in vigore: è entrato in vigore dopo."
        )
        return
    if normalize(then.text) == normalize(now.text):
        if normalize(then.notes) != normalize(now.notes):
            finding.messages.append(
                f"Dopo la data del documento ({day}) Normattiva ha cambiato le note sotto "
                f"l'{Provision(provision.key).label}; il testo è lo stesso."
            )
        return
    changed, unread = _changed_commi(provision.paragraphs, then, now)
    if provision.paragraphs and not changed:
        rest = "; i commi non letti restano da controllare" if unread else ""
        finding.messages.append(
            f"{name} è cambiato dopo la data del documento ({day}), ma non nei commi citati{rest}."
        )
        return
    finding.status = _worse(finding.status, CHANGED)
    finding.before, finding.before_version = then.text, then.version()
    finding.messages.append(
        f"{_capitalized(provision.label)} è cambiato dopo la data del documento ({day}): il "
        f"documento si basa sul {then.version().label}, oggi vale il testo in vigore dal "
        f"{_italian_date(now.start)}."
    )


def _read_italian(
    finding: Finding,
    provision: Provision,
    act: Act,
    italian: ItalianTextSource,
    document_date: str | None,
    today: str,
) -> ItalianArticle | None:
    """Check one article on Normattiva; the wording a quote is to be compared with, if any."""
    name = _capitalized(Provision(provision.key).label)
    if not provision.key.startswith("art:"):
        finding.status = NOT_COVERED
        finding.messages.append(
            "Degli atti italiani il controllo legge gli articoli, non gli allegati: da "
            "controllare a mano."
        )
        return None
    try:
        now = italian.article(act.urn or "", provision.key, today)
    except ActNotFoundError:
        finding.status = ACT_UNCLEAR
        finding.messages.append(
            f"Normattiva non trova {act.label}: il numero, l'anno o il tipo dell'atto "
            "potrebbero essere sbagliati."
        )
        return None
    except ArticleNotFoundError:
        finding.status = MISSING
        finding.messages.append(
            f"{name} non esiste: {act.label} non ha questo articolo su Normattiva (testo "
            f"vigente al {_italian_date(today)})."
        )
        return None
    except TextUnavailableError as e:
        finding.status = UNAVAILABLE
        finding.messages.append(f"{_capitalized(str(e))}.")
        return None

    finding.version = now.version(current=True)
    if now.stale:
        finding.messages.append(
            f"Oggi Normattiva non ha risposto: usato il testo letto il {_italian_date(now.asked)}."
        )
    if act.date and now.act_date and act.date != now.act_date:
        finding.status = _worse(finding.status, ACT_UNCLEAR)
        finding.messages.append(
            f"Nel documento l'atto è datato {_italian_date(act.date)}; su Normattiva è "
            f"«{now.act_title}»: controlla gli estremi."
        )

    if now.state == REPEALED:
        since = f" dal {_italian_date(now.start)}" if now.start else ""
        finding.status = MISSING
        finding.messages.append(
            f"{name}, {act.label}, risulta abrogato{since}. Normattiva riporta: "
            f"«{now.repeal_note}»."
        )
        last = _last_wording(italian, now)
        if last is not None:
            finding.before, finding.before_version = last.text, last.version()
        return last
    if now.state == NOT_IN_FORCE:
        when = f": entra in vigore il {_italian_date(_day_after(now.end))}" if now.end else ""
        finding.status = MISSING
        finding.messages.append(
            f"{name}, {act.label}, non è in vigore al {_italian_date(today)}{when}."
        )
        return None

    finding.article = now.article
    _check_commi(finding, provision, now)
    if provision.key == "art:1" and _APPROVAL_RE.search(now.text):
        finding.status = _worse(finding.status, PARTIAL)
        finding.messages.append(
            "Normattiva dà qui l'articolo 1 dell'atto di approvazione: se il documento intende "
            "l'articolo 1 del testo approvato, in allegato, va controllato a mano."
        )
    _note_scheduled(finding, provision, now, italian)
    _note_rulings(finding, provision, now)
    if document_date:
        _compare_italian_with_date(finding, provision, now, italian, document_date)
    return now


def _check_italian_quotes(
    ref: Reference,
    findings: list[Finding],
    readings: list[ItalianArticle | None],
    act: Act,
    italian: ItalianTextSource,
    document_date: str | None,
) -> None:
    """Each quote against the cited articles: today's wording, then the earlier ones."""
    read = [(f, r) for f, r in zip(findings, readings, strict=True) if r is not None]
    in_force = [(f, r) for f, r in read if f.article is not None]
    first = findings[0]
    for quote in ref.quotes:
        if not _specific_enough(quote):
            first.messages.append("Citazione troppo breve per una verifica parola per parola.")
            continue
        if not read:
            first.messages.append("Citazione non controllata: l'articolo citato non è stato letto.")
            continue
        near: tuple[Finding, VerificationResult] | None = None
        done = False
        for finding, now in in_force:
            result = _verify_in(quote, act, now.article)
            if result.verified:
                if finding.status is VALID:
                    finding.status = VERIFIED
                finding.official_quote = result.official_quote
                finding.messages.append(
                    "La citazione è nel testo vigente, parola per parola."
                    if result.match == "exact"
                    else "La citazione è nel testo vigente, con piccole differenze di punteggiatura."
                )
                done = True
                break
            if result.differences and near is None:
                near = (finding, result)
        if done:
            continue
        # A repealed article: the quote can only be of its last wording.
        for finding, last in read:
            if finding.article is None and _verify_in(quote, act, last.article).verified:
                finding.messages.append(
                    f"La citazione corrisponde al {last.version().label}, l'ultimo prima "
                    "dell'abrogazione."
                )
                done = True
                break
        if done:
            continue
        for finding, now in in_force:
            for old in _earlier_wordings(italian, now, document_date):
                if not _verify_in(quote, act, old.article).verified:
                    continue
                finding.status = _worse(finding.status, OUTDATED)
                finding.before, finding.before_version = old.text, old.version()
                finding.messages.append(
                    f"La citazione corrisponde al {old.version().label}, non al testo vigente: "
                    "la disposizione è cambiata."
                )
                done = True
                break
            if done:
                break
        if done:
            continue
        if near is not None:
            finding, result = near
            finding.status = _worse(finding.status, ALTERED)
            finding.altered_quote = quote
            finding.official_quote = result.near_quote
            finding.differences = list(result.differences or [])
            finding.messages.append(
                "La citazione è diversa dal testo vigente: "
                f"{_describe_differences(finding.differences)}."
            )
        elif any(now.partial for _, now in in_force):
            first.status = _worse(first.status, PARTIAL)
            first.messages.append(
                f"La citazione non è nei primi {PART_SIZE} commi dell'articolo, i soli che l'API "
                "di Normattiva dà: va controllata a mano."
            )
        elif in_force:
            first.status = _worse(first.status, NOT_FOUND)
            first.messages.append(
                "La citazione non è nell'articolo citato, né nel testo vigente né nelle versioni "
                "precedenti: può essere una parafrasi, un errore o il testo di un altro articolo "
                "(degli atti italiani il controllo legge solo gli articoli citati)."
            )
        else:
            first.messages.append(
                "La citazione non corrisponde all'ultimo testo in vigore dell'articolo abrogato."
            )


def _check_italian(
    ref: Reference,
    act: Act,
    italian: ItalianTextSource,
    document_date: str | None,
    today: str,
) -> list[Finding]:
    """The findings of a reference to an Italian act, read on Normattiva."""
    findings: list[Finding] = []
    readings: list[ItalianArticle | None] = []
    for provision in ref.provisions:
        finding = Finding(ref, provision, act, VALID)
        readings.append(_read_italian(finding, provision, act, italian, document_date, today))
        findings.append(finding)
    findings[0].shows_quotes = True
    _check_italian_quotes(ref, findings, readings, act, italian, document_date)
    for finding, reading in zip(findings, readings, strict=True):
        if reading is not None and reading.act_title:
            finding.messages.append(f"Atto letto su Normattiva: {reading.act_title}.")
        if ref.act_inferred:
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
    today = today or date.today().isoformat()
    findings: list[Finding] = []
    for ref in extract_references(text):
        findings.extend(_check_reference(ref, source, lang, document_date, today))
    return DocumentCheck(
        document=document,
        checked_on=today,
        document_date=document_date,
        lang=lang,
        findings=findings,
    )


# ─── Lock file and re-check ──────────────────────────────────────────


def build_lock(check: DocumentCheck) -> dict[str, Any]:
    """The provisions a document depends on, as found in force on the day of the check."""
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for f in check.findings:
        if f.article is None or f.version is None or f.act is None:
            continue
        # An Italian article is identified by the URN that gave it (the annex included).
        urn = f.version.urn if isinstance(f.version, ItalianVersion) else None
        if not f.act.eu and not urn:
            continue
        key = (f.act.key, f.article.key)
        entry = entries.get(key)
        if entry is None:
            entries[key] = {
                "fonte": f.act.source,
                "atto": urn or f.act.key,
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


def _recheck_italian(entry: dict[str, Any], italian: ItalianTextSource | None) -> Change:
    """What happened to an article read on Normattiva since its lock entry was written."""
    name = str(entry.get("articolo") or "L'articolo")
    if italian is None:
        return Change(entry, "non_disponibile", "Questa fonte non legge i testi italiani.")
    today = date.today().isoformat()
    try:
        now = italian.article(str(entry.get("atto") or ""), str(entry.get("chiave") or ""), today)
    except ArticleNotFoundError:
        message = f"{name} non c'è più su Normattiva."
        return Change(entry, "soppresso", message, None, entry.get("testo"))
    except ActNotFoundError:
        return Change(entry, "non_disponibile", "Normattiva non trova più l'atto.")
    except TextUnavailableError as e:
        return Change(entry, "non_disponibile", f"{_capitalized(str(e))}.")
    if now.stale:
        message = (
            "Oggi Normattiva non ha risposto: l'ultimo testo letto è del "
            f"{_italian_date(now.asked)}."
        )
        return Change(entry, "non_disponibile", message)
    version = now.version(current=True)
    since = f" dal {_italian_date(now.start)}" if now.start else ""
    if now.state != IN_FORCE:
        note = f" Normattiva riporta: «{now.repeal_note}»." if now.state == REPEALED else ""
        message = f"{name} non è più in vigore{since}.{note}"
        return Change(entry, "soppresso", message, version, entry.get("testo"))
    if fingerprint(now.text) != entry.get("impronta"):
        message = f"{name} è cambiato: il testo vigente è in vigore{since}."
        return Change(entry, "cambiato", message, version, entry.get("testo"), now.text)
    message = f"{name} è uguale nel {version.label}."
    if now.end:
        message += (
            f" Dal {_italian_date(_day_after(now.end))} è pubblicata una modifica non ancora "
            "in vigore."
        )
    return Change(entry, "invariato", message, version)


def recheck(lock: dict[str, Any], source: TextSource) -> list[Change]:
    """Compare a lock file's provisions with the texts in force now.

    An entry without ``fonte`` comes from a lock file written before Italian
    law was read: it is an EU provision.
    """
    changes: list[Change] = []
    for entry in lock.get("dipendenze", []):
        if entry.get("fonte") == "normattiva":
            changes.append(_recheck_italian(entry, getattr(source, "italian", None)))
            continue
        lang = str(entry.get("lingua") or "IT")
        try:
            versions = source.versions(entry["atto"])
            current = versions[-1]
            if current.celex == entry["versione"]:
                changes.append(
                    Change(entry, "invariato", f"Nessuna versione nuova dopo il {current.label}.")
                )
                continue
            readable = _newest_readable(versions, source, lang)
            if readable is None:
                raise TextUnavailableError(f"CELLAR non ha nessun testo di {entry['atto']}")
            index, articles = readable
            current, unread = versions[index], versions[index + 1 :]
            # A newer version that cannot be read is harmless only when it is
            # the snapshot of the act as published, read here as the original.
            if unread and not (current.as_of is None and all(v.initial for v in unread)):
                raise TextUnavailableError(
                    f"esiste il {unread[-1].label}, che CELLAR non dà come testo: "
                    "da controllare su EUR-Lex"
                )
            if current.celex == entry["versione"]:
                changes.append(
                    Change(entry, "invariato", f"Nessuna versione nuova dopo il {current.label}.")
                )
                continue
            article = find_article(articles, entry["chiave"])
        except TextUnavailableError as e:
            changes.append(Change(entry, "non_disponibile", f"{str(e)[:1].upper()}{str(e)[1:]}."))
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
