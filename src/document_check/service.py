"""Run a document check, store its outcome, re-check a stored one.

Between the engine (``check``), the JSON of a check (``serialize``) and the
database. The HTTP router (``src/api/routers/documents.py``) and the scheduled
surveillance (``surveillance``) both go through here, so that a change found by
either is written in the same way.

What happens to a document
--------------------------
The uploaded file is read in memory (``text_from_bytes``) and its text is
handed to the engine. Neither is written to disk, stored or logged. What is
stored is listed in ``src/db/models.py``: the name, the SHA-256, the findings
with at most 160 characters around each reference, and the official text of the
provisions the document cites.

Limits
------
The size of the file, the length of its text and the number of provisions it
cites are capped (``Settings``, "Document check"). The engine reads the official
texts over the network with blocking calls: ``run_job`` runs it in a small
thread pool, away from the event loop, with a time limit and with a cap on the
jobs one organisation has running. A job that outlives its time limit ends by
itself and keeps the organisation's place until then.

Every failure a user can do something about is a ``DocumentCheckError``: an
HTTP status and a sentence in Italian the interface shows as it is.
"""

from __future__ import annotations

import asyncio
import codecs
import hashlib
import io
import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, TypeVar

import structlog
from sqlalchemy import delete, func, select

from src.auth.tokens import make_signed_token, verify_signed_token
from src.config import get_settings
from src.db.models import Alert, Client
from src.db.models import DocumentCheck as CheckRow
from src.db.models import DocumentDependency as DependencyRow
from src.document_check import serialize
from src.document_check.check import GROUPS, Change, build_lock, check_text, recheck
from src.document_check.extract import detect_language, extract_references

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from src.document_check.official import TextSource

logger = structlog.get_logger()

T = TypeVar("T")

TEXT_EXTENSIONS = (".txt", ".md", ".text")
HTML_EXTENSIONS = (".html", ".htm")
# The formats ``extract.load_text`` reads from a path, read here from memory.
SUPPORTED_EXTENSIONS = (*TEXT_EXTENSIONS, *HTML_EXTENSIONS, ".docx", ".pdf")
LANGUAGES = ("IT", "EN")
DEFAULT_FILENAME = "documento.txt"

# A .docx is a zip: refuse one that unpacks to far more than any real document.
_DOCX_MAX_UNPACKED = 200 * 1024 * 1024

UNSUBSCRIBE_PURPOSE = "document-digest-unsubscribe"
_UNSUBSCRIBE_VALIDITY = timedelta(days=5 * 365)


# ─── Errors the user can do something about ──────────────────────────


class DocumentCheckError(Exception):
    """An HTTP status, a machine-readable code and a sentence in Italian."""

    def __init__(
        self, status_code: int, code: str, detail: str, *, retry_after: int | None = None
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


def _thousands(number: int) -> str:
    return f"{number:,}".replace(",", ".")


def file_too_large(limit_bytes: int) -> DocumentCheckError:
    megabytes = max(1, round(limit_bytes / (1024 * 1024)))
    return DocumentCheckError(413, "file_too_large", f"Il file supera il limite di {megabytes} MB.")


def unsupported_type(extension: str) -> DocumentCheckError:
    shown = extension or "senza estensione"
    return DocumentCheckError(
        415,
        "unsupported_type",
        f"Formato non supportato ({shown}). Formati accettati: .docx, .pdf, .html, .txt, .md.",
    )


def text_too_long(limit: int) -> DocumentCheckError:
    return DocumentCheckError(
        413,
        "text_too_long",
        f"Il testo supera il limite di {_thousands(limit)} caratteri: "
        "dividi il documento in parti.",
    )


def too_many_references(limit: int) -> DocumentCheckError:
    return DocumentCheckError(
        422,
        "too_many_references",
        f"Il documento cita più di {limit} disposizioni: dividilo in parti.",
    )


def storage_full(limit: int) -> DocumentCheckError:
    return DocumentCheckError(
        409,
        "storage_full",
        f"Hai raggiunto il limite di {_thousands(limit)} controlli salvati: "
        "elimina quelli che non servono più.",
    )


def empty_file() -> DocumentCheckError:
    return DocumentCheckError(400, "empty_file", "Il file è vuoto.")


def missing_document() -> DocumentCheckError:
    return DocumentCheckError(
        422, "missing_document", "Carica un file oppure incolla il testo del documento."
    )


def unreadable_file() -> DocumentCheckError:
    return DocumentCheckError(
        422,
        "unreadable_file",
        "Non riesco a leggere il file: è danneggiato o non è del formato indicato dal nome.",
    )


def password_protected() -> DocumentCheckError:
    return DocumentCheckError(
        422,
        "password_protected",
        "Il PDF è protetto da password: caricane una copia senza protezione.",
    )


def no_text() -> DocumentCheckError:
    return DocumentCheckError(
        422,
        "no_text",
        "Nel file non c'è testo da leggere. Un PDF fatto di immagini va prima convertito in testo.",
    )


def pdf_not_supported() -> DocumentCheckError:
    return DocumentCheckError(
        503,
        "pdf_not_supported",
        "Su questo server la lettura dei PDF non è disponibile: "
        "carica il documento in .docx o .txt.",
    )


def invalid_date() -> DocumentCheckError:
    return DocumentCheckError(
        422, "invalid_date", "La data del documento non è valida: usa il formato AAAA-MM-GG."
    )


def invalid_language() -> DocumentCheckError:
    return DocumentCheckError(422, "invalid_language", "Lingua non supportata: usa IT o EN.")


def client_not_found() -> DocumentCheckError:
    return DocumentCheckError(404, "client_not_found", "Cliente non trovato.")


def check_not_found() -> DocumentCheckError:
    return DocumentCheckError(404, "check_not_found", "Controllo non trovato.")


def busy() -> DocumentCheckError:
    return DocumentCheckError(
        429,
        "busy",
        "La tua organizzazione ha già dei controlli in corso. Riprova tra poco.",
        retry_after=15,
    )


def timed_out() -> DocumentCheckError:
    return DocumentCheckError(
        504,
        "timeout",
        "Il controllo non si è concluso entro il tempo massimo. I testi ufficiali già "
        "scaricati restano pronti: riprova tra poco.",
        retry_after=30,
    )


def source_unavailable() -> DocumentCheckError:
    return DocumentCheckError(
        503,
        "source_unavailable",
        "I testi ufficiali non sono raggiungibili in questo momento. Riprova tra qualche minuto.",
        retry_after=60,
    )


# ─── The request: name, date, language ───────────────────────────────


def clean_filename(name: str | None) -> str:
    """The file's own name: no folders, no control characters, at most 255 characters."""
    base = re.split(r"[\\/]", name or "")[-1]
    base = "".join(ch for ch in base if ch.isprintable()).strip()
    if not base:
        return DEFAULT_FILENAME
    if len(base) > 255:
        stem, dot, suffix = base.rpartition(".")
        base = f"{stem[: 254 - len(suffix)]}.{suffix}" if dot and len(suffix) <= 10 else base[:255]
    return base


def extension_of(filename: str) -> str:
    _, dot, suffix = filename.rpartition(".")
    return f".{suffix.lower()}" if dot and suffix else ""


def parse_document_date(value: Any) -> date | None:
    """``YYYY-MM-DD`` or nothing; anything else is the user's mistake."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value.strip()):
        raise invalid_date()
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise invalid_date() from None


def parse_language(value: Any) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    code = str(value).strip().upper()
    if code not in LANGUAGES:
        raise invalid_language()
    return code


# ─── The file, in memory ─────────────────────────────────────────────


def _clean_text(text: str) -> str:
    """Text PostgreSQL can store and the engine reads line by line."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    # Lone surrogates (a badly decoded PDF) cannot be written as UTF-8.
    return text.encode("utf-8", "ignore").decode("utf-8")


def _decode(data: bytes) -> str:
    if data.startswith(codecs.BOM_UTF8):
        return data[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace")
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # Notes saved by older Windows programs: accented letters would
        # otherwise be lost and every quote with one would look altered.
        return data.decode("cp1252", errors="replace")


def _html_text(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n"))


def _docx_text(data: bytes) -> str:
    import docx

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            unpacked = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        raise unreadable_file() from None
    if unpacked > _DOCX_MAX_UNPACKED:
        raise unreadable_file()
    try:
        document = docx.Document(io.BytesIO(data))
        parts = [paragraph.text for paragraph in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                parts.append(" | ".join(cell.text for cell in row.cells))
    except DocumentCheckError:
        raise
    except Exception:  # noqa: BLE001 - whatever the parser raises, the file is not a readable .docx
        raise unreadable_file() from None
    return "\n".join(parts)


def _pdf_pages_pypdf(data: bytes, max_chars: int) -> list[str] | None:
    """The text of each page with pypdf, or None when pypdf is not installed."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                opened = bool(reader.decrypt(""))
            except Exception:  # noqa: BLE001 - e.g. a cipher this install cannot open
                opened = False
            if not opened:
                raise password_protected()
        pages: list[str] = []
        total = 0
        for page in reader.pages:
            pages.append(page.extract_text() or "")
            total += len(pages[-1])
            if total > max_chars:
                break
    except DocumentCheckError:
        raise
    except Exception:  # noqa: BLE001 - whatever the parser raises, the file is not a readable PDF
        raise unreadable_file() from None
    return pages


def _pdf_pages_pdfium(data: bytes, max_chars: int) -> list[str] | None:
    """The same with pypdfium2, which the production image has (through docling)."""
    try:
        import pypdfium2
    except ImportError:
        return None
    try:
        document = pypdfium2.PdfDocument(data)
    except Exception as e:  # noqa: BLE001
        if "password" in str(e).lower():
            raise password_protected() from None
        raise unreadable_file() from None
    pages: list[str] = []
    total = 0
    try:
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            pages.append(text_page.get_text_range() or "")
            text_page.close()
            page.close()
            total += len(pages[-1])
            if total > max_chars:
                break
    except Exception:  # noqa: BLE001
        raise unreadable_file() from None
    finally:
        document.close()
    return pages


def _pdf_text(data: bytes, max_chars: int) -> str:
    pages = _pdf_pages_pypdf(data, max_chars)
    if pages is None:
        pages = _pdf_pages_pdfium(data, max_chars)
    if pages is None:
        raise pdf_not_supported()
    raw = "\n".join(pages).replace("\r\n", "\n").replace("\r", "\n")
    # PDF lines break mid-sentence: rejoin hyphenated words and wrapped lines
    # (the same two steps as extract.load_text).
    raw = re.sub(r"(\w)-\n(\w)", r"\1\2", raw)
    return re.sub(r"(?<![.:;])\n(?!\n)", " ", raw)


def text_from_bytes(filename: str, data: bytes, *, max_chars: int | None = None) -> str:
    """Plain text of an uploaded .txt, .md, .html, .docx or .pdf, read in memory."""
    limit = max_chars if max_chars is not None else get_settings().document_check_max_chars
    suffix = extension_of(filename)
    if suffix not in SUPPORTED_EXTENSIONS:
        raise unsupported_type(suffix)
    if not data:
        raise empty_file()
    if suffix in TEXT_EXTENSIONS:
        text = _decode(data)
    elif suffix in HTML_EXTENSIONS:
        text = _html_text(data)
    elif suffix == ".docx":
        text = _docx_text(data)
    else:
        text = _pdf_text(data, limit)
    return _clean_text(text)


# ─── The check itself (blocking: run it through ``run_job``) ─────────


@dataclass(repr=False)
class CheckOutcome:
    """What a check produced, ready to be stored: the outcome, not the document."""

    filename: str
    document_sha256: str
    document_date: date | None
    lang: str
    checked_at: datetime
    status: str
    counts: dict[str, int]
    findings: list[dict[str, Any]] = field(default_factory=list)
    dependencies: list[dict[str, Any]] = field(default_factory=list)

    def __repr__(self) -> str:
        # Findings quote the document: they stay out of logs and error reports.
        return f"<check outcome: {self.status}, {len(self.findings)} findings>"


def check_document(
    source: TextSource,
    *,
    filename: str,
    data: bytes | None = None,
    text: str | None = None,
    document_date: date | None = None,
    lang: str | None = None,
    now: datetime | None = None,
) -> CheckOutcome:
    """Check an uploaded file (``data``) or a pasted text against the official texts.

    Blocking: it parses the file and reads the official texts over the network.
    """
    settings = get_settings()
    now = now or datetime.now(UTC)
    if data is not None:
        content = text_from_bytes(filename, data, max_chars=settings.document_check_max_chars)
        digest = hashlib.sha256(data).hexdigest()
    elif text is not None:
        content = _clean_text(text)
        digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()
    else:
        raise missing_document()
    if not content.strip():
        raise no_text() if data is not None else missing_document()
    if len(content) > settings.document_check_max_chars:
        raise text_too_long(settings.document_check_max_chars)
    cited = sum(len(reference.provisions) or 1 for reference in extract_references(content))
    if cited > settings.document_check_max_references:
        raise too_many_references(settings.document_check_max_references)

    language = lang or detect_language(content)
    check = check_text(
        content,
        source,
        document=filename,
        lang=language,
        document_date=document_date.isoformat() if document_date else None,
        today=now.date().isoformat(),
    )
    lock = build_lock(check)
    findings = serialize.findings_to_json(check, lock)
    status, counts = serialize.summarize(findings)
    return CheckOutcome(
        filename=filename,
        document_sha256=digest,
        document_date=document_date,
        lang=check.lang,
        checked_at=now,
        status=status,
        counts=counts,
        findings=findings,
        dependencies=serialize.dependencies_to_json(lock),
    )


ProvisionKey = tuple[str, str, str, str, str, str]


def provision_key(dependency: dict[str, Any]) -> ProvisionKey:
    """What a re-check compares: a provision in a language, and the wording it had.

    Two documents that cite the same article checked on the same version share
    the key, whoever they belong to: the official text is read once for both.
    """
    return (
        str(dependency.get("source") or "eurlex"),
        str(dependency.get("act") or ""),
        str(dependency.get("key") or ""),
        str(dependency.get("lang") or "IT"),
        str(dependency.get("version") or ""),
        str(dependency.get("fingerprint") or ""),
    )


def _entry_key(entry: dict[str, Any]) -> ProvisionKey:
    return (
        str(entry.get("fonte") or "eurlex"),
        str(entry.get("atto") or ""),
        str(entry.get("chiave") or ""),
        str(entry.get("lingua") or "IT"),
        str(entry.get("versione") or ""),
        str(entry.get("impronta") or ""),
    )


def recheck_provisions(
    dependencies: list[dict[str, Any]], source: TextSource
) -> dict[ProvisionKey, Change]:
    """Ask ``recheck`` once for each distinct provision among ``dependencies``.

    Blocking. Nothing of a document goes into the lock (no name, no reference as
    written): the provisions of several organisations can be asked together.
    The answer for a stored dependency is ``answers.get(provision_key(it))``;
    a provision ``recheck`` did not answer for is simply missing.
    """
    distinct: dict[ProvisionKey, dict[str, Any]] = {}
    for dependency in dependencies:
        distinct.setdefault(provision_key(dependency), dependency)
    lock = serialize.lock_from_json(list(distinct.values()), with_document=False)
    answers: dict[ProvisionKey, Change] = {}
    for change in recheck(lock, source):
        answers[_entry_key(change.entry)] = change
    return answers


# ─── Threads, time limit, one organisation at a time ─────────────────

_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()
_RUNNING: dict[str, int] = {}
_RUNNING_LOCK = threading.Lock()


def _executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            workers = max(1, get_settings().document_check_workers)
            _EXECUTOR = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="document-check")
        return _EXECUTOR


def running_jobs(org_id: str) -> int:
    """Checks and re-checks of ``org_id`` running in this process."""
    with _RUNNING_LOCK:
        return _RUNNING.get(org_id, 0)


async def run_job(org_id: str, job: Callable[[], T]) -> T:
    """Run blocking ``job`` in the document-check threads, for ``org_id``.

    429 when the organisation already has its share of jobs running, 504 when
    the job does not end within the time limit. A thread cannot be stopped: a
    job past its limit goes on to the end (the texts it downloads stay in the
    cache) and only then gives its place back.
    """
    settings = get_settings()
    limit = max(1, settings.document_check_concurrency_per_org)
    with _RUNNING_LOCK:
        if _RUNNING.get(org_id, 0) >= limit:
            raise busy()
        _RUNNING[org_id] = _RUNNING.get(org_id, 0) + 1

    def release(_done: Any = None) -> None:
        with _RUNNING_LOCK:
            left = _RUNNING.get(org_id, 1) - 1
            if left > 0:
                _RUNNING[org_id] = left
            else:
                _RUNNING.pop(org_id, None)

    try:
        future = _executor().submit(job)
    except BaseException:
        release()
        raise
    future.add_done_callback(release)
    try:
        return await asyncio.wait_for(
            asyncio.shield(asyncio.wrap_future(future)),
            timeout=settings.document_check_timeout_seconds,
        )
    except TimeoutError:
        logger.warning("document_check_timeout", org_id=org_id)
        raise timed_out() from None


# ─── The official texts ──────────────────────────────────────────────


class _LockedSource:
    """One text source for the threads of a process: one call at a time.

    A source keeps what it downloaded and parsed in plain dictionaries and
    files; two checks reading the same act at once must not trip on each other.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._lock = threading.RLock()

    def versions(self, celex: str) -> Any:
        with self._lock:
            return self._inner.versions(celex)

    def articles(self, version: Any, lang: str) -> Any:
        with self._lock:
            return self._inner.articles(version, lang)

    @property
    def italian(self) -> Any:
        """The Italian side of the source (``sources.OfficialSources``), under the same lock."""
        inner = getattr(self._inner, "italian", None)
        return None if inner is None else _LockedItalian(inner, self._lock)

    def __getattr__(self, name: str) -> Any:
        # Whatever else the engine reads from a source (``stale``).
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)


class _LockedItalian:
    """``ItalianTextSource`` of a ``_LockedSource``: Normattiva's cache is shared too."""

    def __init__(self, inner: Any, lock: Any) -> None:
        self._inner = inner
        self._lock = lock

    def article(self, act_urn: str, key: str, on: str) -> Any:
        with self._lock:
            return self._inner.article(act_urn, key, on)

    def original(self, act_urn: str, key: str) -> Any:
        with self._lock:
            return self._inner.original(act_urn, key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        return getattr(self._inner, name)


_SOURCE: tuple[float, Any] | None = None
_SOURCE_LOCK = threading.Lock()


def shared_source() -> TextSource:
    """The text source of this process (``sources.default_source``), renewed now and then.

    Keeping it for a while saves parsing the same act at every check; renewing
    it lets a text CELLAR could not give a moment ago be asked again.
    """
    global _SOURCE
    ttl = get_settings().document_check_source_ttl_seconds
    with _SOURCE_LOCK:
        now = time.monotonic()
        if _SOURCE is None or now - _SOURCE[0] > ttl:
            try:
                from src.document_check.sources import default_source

                _SOURCE = (now, _LockedSource(default_source()))
            except Exception as e:  # noqa: BLE001 - e.g. the cache folder cannot be written
                logger.error(
                    "document_check_source_unavailable",
                    error=f"{type(e).__name__}: {e}",
                    hint="set NORMAAI_TEXT_CACHE to a folder the API can write to",
                )
                raise source_unavailable() from e
        source: TextSource = _SOURCE[1]
        return source


# ─── Stored checks ───────────────────────────────────────────────────


def dependency_json(row: DependencyRow) -> dict[str, Any]:
    """A stored dependency as ``serialize`` reads it."""
    return {
        "source": row.source,
        "act": row.act,
        "name": row.name,
        "article": row.article,
        "key": row.key,
        "lang": row.lang,
        "version": row.version,
        "as_of": row.as_of,
        "fingerprint": row.fingerprint,
        "text": row.official_text,
        "cited_as": list(row.cited_as or []),
        "state": row.state,
        "changed_at": row.changed_at,
        "checked_at": row.checked_at,
        "change": row.change,
    }


def _counts(value: Any) -> dict[str, int]:
    stored = value if isinstance(value, dict) else {}
    return {name: int(stored.get(name) or 0) for name in GROUPS}


def check_object(row: CheckRow, dependencies: list[DependencyRow] | None = None) -> dict[str, Any]:
    """The check as the API returns it: the summary, or the full object with ``dependencies``."""
    out: dict[str, Any] = {
        "id": str(row.id),
        "client_id": str(row.client_id) if row.client_id else None,
        "filename": row.filename,
        "document_sha256": row.document_sha256,
        "document_date": row.document_date.isoformat() if row.document_date else None,
        "checked_at": serialize.iso_z(row.checked_at),
        "lang": row.lang,
        "watch": bool(row.watch),
        "status": row.status,
        "needs_review": bool(row.needs_review),
        "counts": _counts(row.counts),
    }
    if dependencies is not None:
        stored = [dependency_json(dependency) for dependency in dependencies]
        out["findings"] = serialize.effective_findings(list(row.findings or []), stored)
        out["dependencies"] = [serialize.dependency_public(dependency) for dependency in stored]
    out["rechecked_at"] = serialize.iso_z(row.rechecked_at)
    return out


async def client_in_org(session: AsyncSession, org_id: uuid.UUID, client_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(Client.id).where(Client.id == client_id, Client.org_id == org_id)
    )
    return result.scalar_one_or_none() is not None


async def count_checks(session: AsyncSession, org_id: uuid.UUID) -> int:
    result = await session.execute(
        select(func.count()).select_from(CheckRow).where(CheckRow.org_id == org_id)
    )
    return int(result.scalar() or 0)


async def ensure_room(session: AsyncSession, org_id: uuid.UUID) -> None:
    """409 when the organisation already keeps as many checks as it may."""
    limit = get_settings().document_checks_max_per_org
    if limit > 0 and await count_checks(session, org_id) >= limit:
        raise storage_full(limit)


def _short(value: Any, length: int) -> str:
    return str(value or "")[:length]


async def store_check(
    session: AsyncSession,
    outcome: CheckOutcome,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    client_id: uuid.UUID | None,
    watch: bool,
) -> tuple[CheckRow, list[DependencyRow]]:
    """Add the check and its dependencies to the session (the caller commits)."""
    row = CheckRow(
        id=uuid.uuid4(),
        org_id=org_id,
        client_id=client_id,
        created_by=user_id,
        filename=_short(outcome.filename, 255) or DEFAULT_FILENAME,
        document_sha256=outcome.document_sha256,
        document_date=outcome.document_date,
        lang=_short(outcome.lang, 8) or "IT",
        watch=watch,
        status=outcome.status,
        needs_review=False,
        counts=dict(outcome.counts),
        findings=list(outcome.findings),
        checked_at=outcome.checked_at,
    )
    dependencies = [
        DependencyRow(
            id=uuid.uuid4(),
            check_id=row.id,
            org_id=org_id,
            position=position,
            source=_short(item["source"], 20) or "eurlex",
            act=_short(item["act"], 300),
            name=_short(item["name"], 300),
            article=_short(item["article"], 100),
            key=_short(item["key"], 100),
            lang=_short(item.get("lang"), 8) or row.lang,
            version=_short(item["version"], 300),
            as_of=_short(item.get("as_of"), 32) or None,
            fingerprint=_short(item["fingerprint"], 80),
            official_text=str(item.get("text") or ""),
            cited_as=list(item.get("cited_as") or []),
            state="current",
            checked_at=outcome.checked_at,
        )
        for position, item in enumerate(outcome.dependencies)
    ]
    session.add(row)
    await session.flush()
    session.add_all(dependencies)
    await session.flush()
    return row, dependencies


async def load_check(
    session: AsyncSession, org_id: uuid.UUID, check_id: uuid.UUID
) -> tuple[CheckRow, list[DependencyRow]] | None:
    """The check of ``org_id`` with its dependencies; None when it is not theirs."""
    result = await session.execute(
        select(CheckRow).where(CheckRow.id == check_id, CheckRow.org_id == org_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return row, await load_dependencies(session, org_id, [row.id])


async def load_dependencies(
    session: AsyncSession, org_id: uuid.UUID, check_ids: list[uuid.UUID]
) -> list[DependencyRow]:
    if not check_ids:
        return []
    result = await session.execute(
        select(DependencyRow)
        .where(DependencyRow.org_id == org_id, DependencyRow.check_id.in_(check_ids))
        .order_by(DependencyRow.check_id, DependencyRow.position, DependencyRow.id)
    )
    return list(result.scalars().all())


async def list_checks(
    session: AsyncSession,
    org_id: uuid.UUID,
    *,
    client_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CheckRow], int]:
    """A page of the organisation's checks, newest first, and how many match in all."""
    conditions = [CheckRow.org_id == org_id]
    if client_id is not None:
        conditions.append(CheckRow.client_id == client_id)
    if needs_review is not None:
        conditions.append(CheckRow.needs_review.is_(needs_review))
    total = (
        await session.execute(select(func.count()).select_from(CheckRow).where(*conditions))
    ).scalar() or 0
    result = await session.execute(
        select(CheckRow)
        .where(*conditions)
        .order_by(CheckRow.checked_at.desc(), CheckRow.id)
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all()), int(total)


async def delete_check(session: AsyncSession, row: CheckRow) -> None:
    """Delete a check with its dependencies and its alerts (the caller commits).

    PostgreSQL would cascade from the check; the three deletes say it in the
    application too, so nothing depends on the database doing it.
    """
    await session.execute(delete(Alert).where(Alert.document_check_id == row.id))
    await session.execute(
        delete(DependencyRow).where(
            DependencyRow.check_id == row.id, DependencyRow.org_id == row.org_id
        )
    )
    await session.execute(
        delete(CheckRow).where(CheckRow.id == row.id, CheckRow.org_id == row.org_id)
    )


# ─── A re-check on a stored check ────────────────────────────────────


def apply_changes(
    row: CheckRow,
    dependencies: list[DependencyRow],
    changes: list[Change | None],
    now: datetime,
) -> list[DependencyRow]:
    """Write what a re-check found; return the provisions changed for the first time.

    ``changes`` answers ``dependencies`` one for one. The check's status and
    counts follow the findings as they stand now, and ``needs_review`` is set
    while a provision the document cites is not the one of the day of the check.
    """
    fresh: list[DependencyRow] = []
    for dependency, change in zip(dependencies, changes, strict=True):
        if change is None:
            continue
        update = serialize.next_state(dependency_json(dependency), change, now)
        dependency.state = update.state
        dependency.changed_at = update.changed_at
        dependency.change = update.change
        if update.verified:
            dependency.checked_at = now
        if update.is_new:
            fresh.append(dependency)
    stored = [dependency_json(dependency) for dependency in dependencies]
    status, counts = serialize.summarize(
        serialize.effective_findings(list(row.findings or []), stored)
    )
    row.status = status
    row.counts = counts
    row.needs_review = any(d.state in ("changed", "removed") for d in dependencies)
    row.rechecked_at = now
    if fresh:
        # A change nobody was told about: the next digest email includes it.
        row.review_notified_at = None
    return fresh


def changed_provisions(dependencies: list[DependencyRow]) -> list[str]:
    """ "GDPR, Art. 33 (testo consolidato al 04/05/2026)" for each provision no longer the same."""
    out: list[str] = []
    for dependency in dependencies:
        if dependency.state not in ("changed", "removed"):
            continue
        change = dependency.change if isinstance(dependency.change, dict) else {}
        if dependency.state == "removed":
            detail = "non c'è più nel testo vigente"
        else:
            detail = str(change.get("label") or "testo vigente")
        out.append(f"{dependency.name}, {dependency.article} ({detail})")
    return out


ALERT_SEVERITY = "HIGH"
ALERT_ACTIONS = [
    "Apri il controllo e confronta il testo citato con quello vigente.",
    "Aggiorna il documento e caricalo di nuovo per un controllo completo.",
]


def _alert_framework(dependencies: list[DependencyRow]) -> str:
    """The framework of the first changed act NormaAI tracks ("GDPR"), or ""."""
    from src.crawler.eurlex.client import get_tracked_act

    for dependency in dependencies:
        if dependency.state in ("changed", "removed") and dependency.source == "eurlex":
            act = get_tracked_act(dependency.act)
            if act is not None:
                return str(act.framework)
    return ""


def _alert_text(row: CheckRow, dependencies: list[DependencyRow]) -> tuple[str, str]:
    provisions = changed_provisions(dependencies)
    title = f"Documento da rivedere: {row.filename}"[:500]
    if len(provisions) == 1:
        opening = "Dopo il controllo è cambiata una disposizione citata nel documento"
    else:
        opening = (
            f"Dopo il controllo sono cambiate {len(provisions)} disposizioni citate nel documento"
        )
    return title, f"{opening}: {'; '.join(provisions)}."


async def write_review_alert(
    session: AsyncSession, row: CheckRow, dependencies: list[DependencyRow]
) -> Alert:
    """The one alert of a document whose provisions changed (the caller commits).

    A document has at most one alert that is not dismissed: when another of its
    provisions changes, that alert is brought up to date and marked unread.
    """
    title, description = _alert_text(row, dependencies)
    result = await session.execute(
        select(Alert)
        .where(Alert.document_check_id == row.id, Alert.is_dismissed.is_(False))
        .order_by(Alert.created_at.desc())
        .limit(1)
    )
    alert = result.scalar_one_or_none()
    if alert is None:
        alert = Alert(
            id=uuid.uuid4(),
            client_id=row.client_id,
            document_check_id=row.id,
            severity=ALERT_SEVERITY,
            is_dismissed=False,
        )
        session.add(alert)
    alert.framework = _alert_framework(dependencies)
    alert.title = title
    alert.description = description
    alert.actions_required = list(ALERT_ACTIONS)
    alert.is_read = False
    return alert


async def apply_recheck(
    session: AsyncSession,
    row: CheckRow,
    dependencies: list[DependencyRow],
    changes: list[Change | None],
    now: datetime | None = None,
) -> list[DependencyRow]:
    """``apply_changes`` plus the alert when something changed for the first time."""
    fresh = apply_changes(row, dependencies, changes, now or datetime.now(UTC))
    if fresh:
        await write_review_alert(session, row, dependencies)
    return fresh


# ─── The unsubscribe link of the digest email ────────────────────────


def make_unsubscribe_token(user_id: uuid.UUID) -> str:
    """A signed token that turns the digest email off for ``user_id``, without a login."""
    return make_signed_token(
        UNSUBSCRIBE_PURPOSE, str(user_id), datetime.now(UTC) + _UNSUBSCRIBE_VALIDITY
    )


def read_unsubscribe_token(token: str) -> uuid.UUID | None:
    subject = verify_signed_token(UNSUBSCRIBE_PURPOSE, token or "")
    if subject is None:
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def unsubscribe_url(user_id: uuid.UUID) -> str | None:
    """The link for the email, or None when the public address of the API is not configured."""
    base = get_settings().api_base_url
    if not base:
        return None
    return f"{base}/api/v1/documents/unsubscribe?token={make_unsubscribe_token(user_id)}"
