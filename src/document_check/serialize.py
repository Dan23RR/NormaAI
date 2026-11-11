"""The JSON of a document check: what the HTTP API returns and what is stored.

``src.document_check.check`` works with dataclasses that hold a document's
references in full. This module turns their outcome into plain JSON and back,
with no database and no network:

- ``findings_to_json`` and ``dependencies_to_json``: the findings of a check and
  the provisions the document depends on, in the shape of the documents API
  (``src/api/routers/documents.py``). A finding keeps at most 160 characters of
  the document around its reference, never the document.
- ``lock_from_json``: the lock ``recheck`` wants, rebuilt from stored
  dependencies.
- ``next_state``: what a later ``recheck`` found for one dependency, and whether
  it is a change nobody was told about yet.
- ``effective_findings``: the stored findings as they stand today, with the
  provisions changed since the check shown as to be corrected.
- ``check_from_json``: a ``DocumentCheck`` rebuilt from stored findings, for the
  HTML report.

A stored finding is the API finding. Besides the fields of the contract it has
``altered_quote``, ``provision.paragraphs``, ``before.version_id``,
``before.as_of`` (the report needs them) and ``dependency``: the provision of
``dependencies`` it relies on, as ``{"source", "act", "key"}``.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from src.document_check.check import GROUPS, Change, DocumentCheck, Finding, Status
from src.document_check.extract import Act, Provision, Reference
from src.document_check.official import ArticleText, Version

# Characters of the document kept around a reference.
CONTEXT_LIMIT = 160

SOURCES = ("eurlex", "normattiva")
STATES = ("current", "changed", "removed", "unavailable")
# ``Change.code`` of src.document_check.check -> state of a dependency.
STATE_BY_CODE = {
    "invariato": "current",
    "cambiato": "changed",
    "soppresso": "removed",
    "non_disponibile": "unavailable",
}
# Worst first. Italian law that could not be checked gives the status only when
# nothing else was found.
_STATUS_ORDER = ("correggere", "controllare", "a_posto")

NO_ACT_NAME = "Atto non indicato"
CHANGED_AFTER_CHECK = {"code": "cambiato", "label": "Cambiato dopo il controllo"}
REMOVED_AFTER_CHECK = {"code": "inesistente", "label": "Non esiste più nel testo vigente"}


# ─── Small helpers ───────────────────────────────────────────────────


def iso_z(moment: datetime | None) -> str | None:
    """``2026-11-11T16:20:00Z``; a datetime without a zone is read as UTC."""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def clip_context(context: str, raw: str, limit: int = CONTEXT_LIMIT) -> str:
    """At most ``limit`` characters of ``context``, with the reference ``raw`` in view.

    ``extract`` gives up to 160 characters on each side of a reference; what is
    stored is one window of ``limit`` characters around it, cut at word
    boundaries and marked with three dots where the line goes on.
    """
    text = " ".join(context.split())
    cut_left = text.startswith("… ")
    cut_right = text.endswith(" …")
    if cut_left:
        text = text[2:]
    if cut_right:
        text = text[:-2]
    if len(text) <= limit and not (cut_left or cut_right):
        return text
    budget = max(limit - 8, 1)  # room for "... " and " ..."
    start, end = 0, min(len(text), budget)
    tokens = raw.split()
    match = re.search(r"\s+".join(map(re.escape, tokens)), text) if tokens else None
    if match is not None and len(text) > budget:
        spare = max(budget - (match.end() - match.start()), 0)
        start = max(0, match.start() - spare // 2)
        end = min(len(text), start + budget)
        start = max(0, end - budget)
        # Whole words, without pushing the reference out of the window.
        if start > 0:
            space = text.find(" ", start, match.start() + 1)
            start = space + 1 if space != -1 else start
        if end < len(text):
            space = text.rfind(" ", max(match.end(), start), end)
            end = space if space != -1 else end
    elif len(text) > budget:
        space = text.rfind(" ", 0, end)
        end = space if space > 0 else end
    left = "... " if start > 0 or cut_left else ""
    right = " ..." if end < len(text) or cut_right else ""
    return f"{left}{text[start:end].strip()}{right}"


def act_source(act: Act) -> str:
    """Where the act's official text comes from: "eurlex" or "normattiva"."""
    explicit = getattr(act, "source", None) or getattr(act, "fonte", None)
    if explicit in SOURCES:
        return str(explicit)
    return "eurlex" if act.eu else "normattiva"


def summarize(findings: list[dict[str, Any]]) -> tuple[str, dict[str, int]]:
    """``(status, counts)``: the worst group present and how many findings each group has."""
    counts = {name: 0 for name in GROUPS}
    for finding in findings:
        group = str(finding.get("group") or "")
        counts[group] = counts.get(group, 0) + 1
    for name in _STATUS_ORDER:
        if counts.get(name):
            return name, counts
    return ("non_coperto" if counts.get("non_coperto") else "a_posto"), counts


# ─── A check to JSON ─────────────────────────────────────────────────


def _lock_entries(lock: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry for entry in lock.get("dipendenze", []) if isinstance(entry, dict)]


def _entry_of(finding: Finding, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The lock entry a finding relies on.

    ``build_lock`` makes one entry per act and article and lists in
    ``riferimenti`` the references that rely on it. The act is matched by its
    id or by its name, so that an act the lock identifies in another way than
    the finding does (an Italian act by its URN) is still found.
    """
    article = finding.article
    if article is None or finding.act is None:
        return None
    same_provision = [
        entry
        for entry in entries
        if entry.get("chiave") == article.key
        and finding.reference.raw in (entry.get("riferimenti") or [])
    ]
    for entry in same_provision:
        if entry.get("atto") == finding.act.key or entry.get("nome") == finding.act_name:
            return entry
    return same_provision[0] if len(same_provision) == 1 else None


def _finding_json(finding: Finding, number: int, entry: dict[str, Any] | None) -> dict[str, Any]:
    ref = finding.reference
    act = finding.act
    provision = finding.provision
    version = finding.version
    before: dict[str, Any] | None = None
    if finding.before:
        earlier = finding.before_version
        before = {
            "version_label": earlier.label if earlier else "testo precedente",
            "version_id": earlier.celex if earlier else None,
            "as_of": earlier.as_of if earlier else None,
            "text": finding.before,
        }
    return {
        "id": f"f{number}",
        "group": finding.status.group,
        "status": {"code": finding.status.code, "label": finding.status.label},
        "line": ref.line,
        "raw": ref.raw,
        "context": clip_context(ref.context, ref.raw),
        "act": {
            "source": act_source(act) if act else None,
            "id": act.key if act else None,
            "name": finding.act_name,
            "label": act.label if act else finding.act_name,
        },
        "provision": {
            "key": provision.key if provision else None,
            "label": provision.label if provision else ref.raw,
            "paragraphs": list(provision.paragraphs) if provision else [],
        },
        "version": (
            {"id": version.celex, "as_of": version.as_of, "label": version.label}
            if version
            else None
        ),
        "url": finding.url,
        "messages": [str(message) for message in finding.messages],
        "quotes": list(ref.quotes) if finding.shows_quotes else [],
        "official_quote": finding.official_quote,
        "altered_quote": finding.altered_quote,
        "differences": [dict(difference) for difference in finding.differences],
        "before": before,
        "after_text": finding.article.text if finding.before and finding.article else None,
        "dependency": (
            {
                "source": str(entry.get("fonte") or "eurlex"),
                "act": str(entry["atto"]),
                "key": str(entry["chiave"]),
            }
            if entry
            else None
        ),
    }


def findings_to_json(check: DocumentCheck, lock: dict[str, Any]) -> list[dict[str, Any]]:
    """The findings of ``check``, in the document's order, as the API returns them."""
    entries = _lock_entries(lock)
    return [
        _finding_json(finding, number, _entry_of(finding, entries))
        for number, finding in enumerate(check.findings, start=1)
    ]


def dependencies_to_json(lock: dict[str, Any]) -> list[dict[str, Any]]:
    """The provisions of a lock as stored dependencies, all in state ``current``."""
    default_lang = str(lock.get("lingua") or "IT")
    return [
        {
            "source": str(entry.get("fonte") or "eurlex"),
            "act": str(entry["atto"]),
            "name": str(entry.get("nome") or entry["atto"]),
            "article": str(entry.get("articolo") or entry["chiave"]),
            "key": str(entry["chiave"]),
            "lang": str(entry.get("lingua") or default_lang),
            "version": str(entry.get("versione") or ""),
            "as_of": entry.get("consolidato_al"),
            "fingerprint": str(entry.get("impronta") or ""),
            "text": str(entry.get("testo") or ""),
            "cited_as": [str(raw) for raw in entry.get("riferimenti") or []],
            "state": "current",
            "changed_at": None,
            "checked_at": None,
            "change": None,
        }
        for entry in _lock_entries(lock)
    ]


def dependency_public(dependency: dict[str, Any]) -> dict[str, Any]:
    """A stored dependency as the API returns it: no official text, dates as ISO strings."""
    change = dependency.get("change") or {}
    return {
        "source": dependency["source"],
        "act": dependency["act"],
        "name": dependency["name"],
        "article": dependency["article"],
        "key": dependency["key"],
        "version": dependency["version"],
        "as_of": dependency.get("as_of"),
        "fingerprint": dependency["fingerprint"],
        "state": dependency.get("state") or "current",
        "changed_at": iso_z(dependency.get("changed_at")),
        "lang": dependency.get("lang"),
        "cited_as": list(dependency.get("cited_as") or []),
        "checked_at": iso_z(dependency.get("checked_at")),
        "message": change.get("message"),
        "current_version": change.get("version"),
        "current_as_of": change.get("as_of"),
    }


# ─── Stored JSON back to what the engine wants ───────────────────────


def lock_from_json(
    dependencies: list[dict[str, Any]],
    *,
    document: str = "",
    checked_on: str | None = None,
    document_date: str | None = None,
    lang: str = "IT",
    with_document: bool = True,
) -> dict[str, Any]:
    """The lock ``recheck`` reads, rebuilt from stored dependencies.

    ``with_document=False`` leaves out everything that comes from the document
    (its name, how it cites each provision): the surveillance re-checks the
    provisions of many organisations in one lock.
    """
    return {
        "documento": document if with_document else "",
        "controllato_il": checked_on,
        "data_documento": document_date if with_document else None,
        "lingua": lang,
        "dipendenze": [
            {
                "fonte": dependency["source"],
                "atto": dependency["act"],
                "nome": dependency["name"],
                "versione": dependency["version"],
                "consolidato_al": dependency.get("as_of"),
                "articolo": dependency["article"],
                "chiave": dependency["key"],
                "lingua": dependency.get("lang") or lang,
                "impronta": dependency["fingerprint"],
                "testo": dependency.get("text") or "",
                "riferimenti": (list(dependency.get("cited_as") or []) if with_document else []),
            }
            for dependency in dependencies
        ],
    }


@dataclass(frozen=True)
class DependencyUpdate:
    """What a re-check means for one stored dependency."""

    state: str
    changed_at: datetime | None
    change: dict[str, Any] | None
    # The official text could be read (so ``checked_at`` moves).
    verified: bool
    # A change nobody was told about yet: it deserves an alert.
    is_new: bool


def _version_url(version: Any, lang: str) -> str | None:
    url = getattr(version, "url", None)
    if not callable(url):
        return None
    try:
        return url(lang)
    except Exception:  # noqa: BLE001 - a link is a convenience, never a reason to fail
        return None


def next_state(dependency: dict[str, Any], change: Change, now: datetime) -> DependencyUpdate:
    """The state of ``dependency`` after ``recheck`` answered ``change``.

    The provision as it was on the day of the check stays the term of
    comparison: a changed provision is "changed" at every later re-check. It is
    new only the first time its present wording is seen, so running the
    re-check twice tells nobody twice.
    """
    state = STATE_BY_CODE.get(change.code, "unavailable")
    previous = str(dependency.get("state") or "current")
    seen = dependency.get("change") or {}
    if state == "current":
        return DependencyUpdate("current", None, None, verified=True, is_new=False)
    if state == "unavailable":
        if previous in ("changed", "removed"):
            # Not reachable today: what was found before still stands.
            return DependencyUpdate(
                previous, dependency.get("changed_at"), seen or None, False, False
            )
        return DependencyUpdate(
            "unavailable", None, {"message": change.message}, verified=False, is_new=False
        )
    digest = hashlib.sha256(f"{change.code}\n{change.after or ''}".encode()).hexdigest()
    is_new = previous != state or seen.get("digest") != digest
    version = change.version
    observed = {
        "version": getattr(version, "celex", None),
        "as_of": getattr(version, "as_of", None),
        "label": getattr(version, "label", None),
        "url": _version_url(version, str(dependency.get("lang") or "IT")),
        "text": change.after,
        "message": change.message,
        "digest": digest,
    }
    changed_at = now if is_new else (dependency.get("changed_at") or now)
    return DependencyUpdate(state, changed_at, observed, verified=True, is_new=is_new)


def _overlay(finding: dict[str, Any], dependency: dict[str, Any]) -> None:
    change = dependency.get("change") or {}
    message = change.get("message")
    if message and message not in finding["messages"]:
        finding["messages"].append(message)
    if finding.get("group") == "correggere":
        # Already to be corrected: it keeps its own outcome and comparison.
        return
    checked = finding.get("version") or {}
    finding["group"] = "correggere"
    finding["before"] = {
        "version_label": checked.get("label") or "testo del controllo",
        "version_id": dependency.get("version"),
        "as_of": dependency.get("as_of"),
        "text": dependency.get("text") or "",
    }
    if dependency.get("state") == "removed":
        finding["status"] = dict(REMOVED_AFTER_CHECK)
        finding["after_text"] = None
    else:
        finding["status"] = dict(CHANGED_AFTER_CHECK)
        finding["after_text"] = change.get("text")
    if change.get("version"):
        finding["version"] = {
            "id": change["version"],
            "as_of": change.get("as_of"),
            "label": change.get("label"),
        }
    if change.get("url"):
        finding["url"] = change["url"]


def effective_findings(
    findings: list[dict[str, Any]], dependencies: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The stored findings as they stand after the last re-check (copies).

    A finding whose provision changed or disappeared since the check goes
    under "correggere", with the provision as it was and as it is.
    """
    moved = {
        (dependency["source"], dependency["act"], dependency["key"]): dependency
        for dependency in dependencies
        if dependency.get("state") in ("changed", "removed")
    }
    out: list[dict[str, Any]] = []
    for stored in findings:
        finding = copy.deepcopy(stored)
        link = finding.get("dependency")
        if isinstance(link, dict):
            dependency = moved.get((link.get("source"), link.get("act"), link.get("key")))
            if dependency is not None:
                _overlay(finding, dependency)
        out.append(finding)
    return out


# ─── Stored findings back to a DocumentCheck (the HTML report) ───────
# The report reads labels and links through properties that the engine computes
# from an act's id or a version's date. A stored finding already has them as
# they were shown on the day of the check: these subclasses give those back
# instead of computing them again.


@dataclass(frozen=True)
class _StoredAct(Act):
    stored_source: str = "eurlex"

    @property
    def eu(self) -> bool:
        return self.stored_source != "normattiva"


@dataclass(frozen=True)
class _StoredProvision(Provision):
    stored_label: str = ""

    @property
    def label(self) -> str:
        return self.stored_label or super().label


@dataclass(frozen=True)
class _StoredVersion(Version):
    stored_label: str = ""

    @property
    def label(self) -> str:
        return self.stored_label or super().label


@dataclass
class _StoredFinding(Finding):
    stored_url: str | None = None
    stored_act_name: str = ""

    @property
    def act_name(self) -> str:
        return self.stored_act_name or super().act_name

    @property
    def url(self) -> str | None:
        return self.stored_url


def _stored_version(item: dict[str, Any] | None) -> Version | None:
    if not item or not item.get("id"):
        return None
    return _StoredVersion(
        str(item["id"]), item.get("as_of"), stored_label=str(item.get("label") or "")
    )


def _finding_from_json(item: dict[str, Any], lang: str) -> Finding:
    act_json = item.get("act") or {}
    provision_json = item.get("provision") or {}
    status_json = item.get("status") or {}
    before_json = item.get("before") or {}
    act: Act | None = None
    if act_json.get("id"):
        act = _StoredAct(
            str(act_json["id"]),
            str(act_json.get("label") or act_json.get("name") or act_json["id"]),
            stored_source=str(act_json.get("source") or "eurlex"),
        )
    provision: Provision | None = None
    if provision_json.get("key"):
        provision = _StoredProvision(
            str(provision_json["key"]),
            tuple(str(p) for p in provision_json.get("paragraphs") or ()),
            stored_label=str(provision_json.get("label") or ""),
        )
    quotes = [str(quote) for quote in item.get("quotes") or []]
    reference = Reference(
        start=0,
        end=0,
        provisions=[provision] if provision else [],
        act=act,
        quotes=quotes,
        raw=str(item.get("raw") or ""),
        line=int(item.get("line") or 0),
        context=str(item.get("context") or ""),
    )
    after_text = item.get("after_text")
    article: ArticleText | None = None
    if after_text and provision is not None:
        article = ArticleText(provision.key, provision.label, str(after_text), ())
    before_version: Version | None = None
    if before_json.get("text"):
        before_version = _StoredVersion(
            str(before_json.get("version_id") or ""),
            before_json.get("as_of"),
            stored_label=str(before_json.get("version_label") or ""),
        )
    return _StoredFinding(
        reference=reference,
        provision=provision,
        act=act,
        status=Status(
            str(status_json.get("code") or ""),
            str(status_json.get("label") or ""),
            str(item.get("group") or "controllare"),
        ),
        messages=[str(message) for message in item.get("messages") or []],
        lang=lang,
        version=_stored_version(item.get("version")),
        article=article,
        official_quote=item.get("official_quote"),
        before=before_json.get("text") or None,
        before_version=before_version,
        shows_quotes=bool(quotes),
        altered_quote=item.get("altered_quote"),
        differences=[dict(d) for d in item.get("differences") or [] if isinstance(d, dict)],
        stored_url=item.get("url"),
        stored_act_name=str(act_json.get("name") or NO_ACT_NAME),
    )


def check_from_json(
    findings: list[dict[str, Any]],
    *,
    document: str,
    checked_on: str,
    document_date: str | None,
    lang: str,
) -> DocumentCheck:
    """A ``DocumentCheck`` with the stored findings, for ``report.render_html``."""
    return DocumentCheck(
        document=document,
        checked_on=checked_on,
        document_date=document_date,
        lang=lang,
        findings=[_finding_from_json(item, lang) for item in findings],
    )
