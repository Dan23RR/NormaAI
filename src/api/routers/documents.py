"""Documents: check the legal references of a document, keep the outcome, watch it.

Routes, all under ``/api/v1/documents``:

- ``POST /check``: a file (multipart, field ``file``) or a text (JSON,
  ``{"text", "filename"}``), with the optional ``client_id``, ``document_date``
  (ISO), ``watch`` (default true) and ``lang`` (IT or EN). Answers 201 with the
  full object. The file is read in memory and not kept; what is stored is its
  name, its SHA-256, the dates, the findings (the reference, at most 160
  characters around it, the quotes, the outcome) and the provisions it cites.
- ``GET /checks?client_id=&needs_review=&limit=&offset=``: ``{"items", "total"}``,
  each item the object without ``findings`` and ``dependencies``.
- ``GET /checks/{id}``: the full object. ``DELETE /checks/{id}``: 204.
- ``POST /checks/{id}/recheck``: the full object after comparing its provisions
  with the texts in force. A provision changed since the check sets
  ``needs_review`` and writes one alert for the document.
- ``GET /checks/{id}/report``: the report as an HTML page.
- ``GET /preferences``, ``PATCH /preferences``: ``{"email_digest": bool}``, the
  email "documenti da rivedere" of the scheduled surveillance, per user.
- ``GET|POST /unsubscribe?token=``: turns that email off from the link in it,
  without a login (signed token; POST is the one-click form of RFC 8058).

Access. Reading: any signed-in user of the organisation. Checking, re-checking
and deleting: not the ``viewer`` role, and a verified email address when the
deployment asks for one. Every query filters on the caller's ``org_id`` and
runs in a session with the tenant context (row-level security).

Limits. The check calls no language model, so it does not count against the LLM
quota: it has its own hourly limit (``DOCUMENT_CHECK_RATE_LIMIT``), a cap on the
checks an organisation keeps and one on those it has running. Failures the user
can act on come back as ``{"detail": "<Italian sentence>"}`` with the status of
``src.document_check.service.DocumentCheckError``.
"""

import json
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from src.api.rate_limit import client_ip_key, limiter, settings_limit
from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user, require_verified_email
from src.config import get_settings
from src.db.engine import db_manager
from src.db.models import User
from src.document_check import serialize, service
from src.document_check.report import render_html
from src.document_check.service import DocumentCheckError

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])

READ_ONLY_DETAIL = "Il tuo ruolo consente solo la lettura."
INVALID_REQUEST_DETAIL = (
    "Richiesta non valida: invia un file (multipart/form-data, campo file) "
    "oppure un testo (application/json, campo text)."
)
INTERNAL_ERROR_DETAIL = "Errore interno durante il controllo. Riprova più tardi."
USER_NOT_FOUND_DETAIL = "Utente non trovato."
# Room in the request body for the multipart boundaries and the other fields.
_BODY_OVERHEAD = 64 * 1024


# ─── Dependencies ────────────────────────────────────────────────────


def _http(error: DocumentCheckError) -> HTTPException:
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
    return HTTPException(status_code=error.status_code, detail=error.detail, headers=headers)


def get_text_source() -> Any:
    """The official texts the checks read: a ``TextSource`` (tests replace it with a fake)."""
    try:
        return service.shared_source()
    except DocumentCheckError as error:
        raise _http(error) from None


async def require_editor(user: CurrentUser = Depends(require_verified_email)) -> CurrentUser:
    """Who may check, re-check and delete: everyone but the read-only ``viewer`` role."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail=READ_ONLY_DETAIL)
    return user


# ─── The request of POST /check ──────────────────────────────────────


class CheckTextRequest(BaseModel):
    """The JSON form of ``POST /check``: a pasted text instead of a file."""

    text: str = Field(..., description="The text of the document")
    filename: str | None = Field(default=None, max_length=255, description="A name for it")
    client_id: uuid.UUID | None = Field(default=None, description="The client it belongs to")
    document_date: str | None = Field(default=None, description="Date of the document, ISO")
    watch: bool = Field(default=True, description="Re-check it when the law changes")
    lang: str | None = Field(default=None, description="IT or EN (detected when missing)")


@dataclass(repr=False)
class _CheckRequest:
    """What ``POST /check`` asked for. Its ``repr`` shows nothing of the document."""

    filename: str
    data: bytes | None = None
    text: str | None = None
    client_id: uuid.UUID | None = None
    document_date: date | None = None
    watch: bool = True
    lang: str | None = None
    size: int = field(default=0)

    def __repr__(self) -> str:
        return f"<document of {self.size} bytes>"


_CHECK_OPENAPI: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "client_id": {"type": "string", "format": "uuid"},
                        "document_date": {"type": "string", "format": "date"},
                        "watch": {"type": "boolean", "default": True},
                        "lang": {"type": "string", "enum": ["IT", "EN"]},
                    },
                }
            },
            "application/json": {"schema": CheckTextRequest.model_json_schema()},
        },
    }
}


def _invalid_request() -> DocumentCheckError:
    return DocumentCheckError(422, "invalid_request", INVALID_REQUEST_DETAIL)


def _as_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "on", "yes", "si", "sì"):
        return True
    if text in ("false", "0", "off", "no"):
        return False
    raise _invalid_request()


def _as_client_id(value: Any) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value).strip())
    except ValueError:
        raise service.client_not_found() from None


async def _limited(request: Request, limit: int, max_bytes: int) -> AsyncIterator[bytes]:
    """The request body, refused as soon as it is longer than ``limit``."""
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise service.file_too_large(max_bytes)
        yield chunk


async def _read_multipart(request: Request, limit: int, max_bytes: int) -> _CheckRequest:
    parser = MultiPartParser(
        request.headers, _limited(request, limit, max_bytes), max_files=1, max_fields=8
    )
    # Starlette moves an upload larger than ``spool_max_size`` (1 MB) to a
    # temporary file on disk. A document sent here is never written to disk:
    # the threshold goes above the largest body this route accepts.
    parser.spool_max_size = limit + 1
    try:
        form = await parser.parse()
    except MultiPartException:
        raise _invalid_request() from None
    try:
        upload = form.get("file")
        text = form.get("text")
        fields = {name: form.get(name) for name in ("client_id", "document_date", "watch", "lang")}
        if isinstance(upload, UploadFile):
            data = await upload.read()
            if len(data) > max_bytes:
                raise service.file_too_large(max_bytes)
            if not data:
                raise service.empty_file()
            filename = service.clean_filename(upload.filename)
            parsed = _CheckRequest(filename=filename, data=data, size=len(data))
        elif isinstance(text, str) and text.strip():
            filename_field = form.get("filename")
            filename = service.clean_filename(
                filename_field if isinstance(filename_field, str) else None
            )
            parsed = _CheckRequest(filename=filename, text=text, size=len(text.encode("utf-8")))
        else:
            raise service.missing_document()
    finally:
        await form.close()
    parsed.client_id = _as_client_id(fields["client_id"])
    parsed.document_date = service.parse_document_date(fields["document_date"])
    parsed.watch = _as_bool(fields["watch"], default=True)
    parsed.lang = service.parse_language(fields["lang"])
    return parsed


async def _read_json(request: Request, limit: int, max_bytes: int) -> _CheckRequest:
    raw = b"".join([chunk async for chunk in _limited(request, limit, max_bytes)])
    try:
        payload = CheckTextRequest.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise _invalid_request() from None
    if not payload.text.strip():
        raise service.missing_document()
    return _CheckRequest(
        filename=service.clean_filename(payload.filename),
        text=payload.text,
        client_id=payload.client_id,
        document_date=service.parse_document_date(payload.document_date),
        watch=payload.watch,
        lang=service.parse_language(payload.lang),
        size=len(payload.text.encode("utf-8")),
    )


async def _read_check_request(request: Request) -> _CheckRequest:
    """Parse ``POST /check`` in memory, with the size limit applied while reading."""
    max_bytes = get_settings().document_check_max_bytes
    limit = max_bytes + _BODY_OVERHEAD
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise service.file_too_large(max_bytes)
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    try:
        if content_type == "multipart/form-data":
            parsed = await _read_multipart(request, limit, max_bytes)
        elif content_type == "application/json":
            parsed = await _read_json(request, limit, max_bytes)
        else:
            raise DocumentCheckError(415, "invalid_request", INVALID_REQUEST_DETAIL)
    except DocumentCheckError:
        raise
    except Exception as e:  # noqa: BLE001
        # Never the message: it may quote the body.
        logger.error("document_request_unreadable", error_type=type(e).__name__)
        raise _invalid_request() from None
    if parsed.data is not None and service.extension_of(parsed.filename) not in (
        service.SUPPORTED_EXTENSIONS
    ):
        raise service.unsupported_type(service.extension_of(parsed.filename))
    return parsed


async def _run(org_id: uuid.UUID, job: Callable[[], Any]) -> Any:
    """``service.run_job`` with every unexpected failure turned into a clean 500.

    The exception of a failed check is not re-raised and its message is not
    logged: both could carry text of the document.
    """
    try:
        return await service.run_job(str(org_id), job)
    except DocumentCheckError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("document_check_failed", org_id=str(org_id), error_type=type(e).__name__)
        raise DocumentCheckError(500, "internal_error", INTERNAL_ERROR_DETAIL) from None


# ─── Checks ──────────────────────────────────────────────────────────


@router.post("/check", status_code=201, openapi_extra=_CHECK_OPENAPI)
@limiter.limit(settings_limit("document_check_rate_limit"))
async def create_check(
    request: Request,
    user: CurrentUser = Depends(require_editor),
    source: Any = Depends(get_text_source),
) -> dict[str, Any]:
    """
    **Check the legal references of a document against the official texts in force.**

    Send the document as `multipart/form-data` (field `file`: .docx, .pdf, .html,
    .txt or .md, at most 10 MB) or as JSON (`{"text": "...", "filename": "nota.txt"}`).
    Optional: `client_id`, `document_date` (YYYY-MM-DD: what changed after that
    date is reported), `watch` (default true: the provisions cited are
    re-checked on schedule) and `lang` (IT or EN).

    The file is read in memory and not kept. The answer is the stored check,
    with one finding per provision cited and the provisions it depends on.
    """
    org_id = user.org_id
    try:
        upload = await _read_check_request(request)
        async with db_manager.session(org_id=str(org_id)) as session:
            if upload.client_id is not None and not await service.client_in_org(
                session, org_id, upload.client_id
            ):
                raise service.client_not_found()
            await service.ensure_room(session, org_id)
        outcome = await _run(
            org_id,
            lambda: service.check_document(
                source,
                filename=upload.filename,
                data=upload.data,
                text=upload.text,
                document_date=upload.document_date,
                lang=upload.lang,
            ),
        )
        async with db_manager.session(org_id=str(org_id)) as session:
            row, dependencies = await service.store_check(
                session,
                outcome,
                org_id=org_id,
                user_id=user.user_id,
                client_id=upload.client_id,
                watch=upload.watch,
            )
            await session.commit()
            body = service.check_object(row, dependencies)
    except DocumentCheckError as error:
        raise _http(error) from None

    audit_log(
        AuditAction.DOCUMENT_UPLOAD,
        user_id=str(user.user_id),
        org_id=str(org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/documents/check",
        detail=f"document check ({upload.size} bytes, {len(body['findings'])} findings)",
        extra={"check_id": body["id"], "status": body["status"]},
    )
    return body


@router.get("/checks")
@limiter.limit("30/minute")
async def list_checks(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    client_id: uuid.UUID | None = None,
    needs_review: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """
    **The organisation's document checks, newest first.**

    `client_id` keeps the checks of one client, `needs_review=true` those with a
    cited provision that changed since the check. Each item is the check without
    `findings` and `dependencies`; `total` counts every check that matches.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        rows, total = await service.list_checks(
            session,
            user.org_id,
            client_id=client_id,
            needs_review=needs_review,
            limit=limit,
            offset=offset,
        )
        items = [service.check_object(row) for row in rows]
    return {"items": items, "total": total}


@router.get("/checks/{check_id}")
@limiter.limit("60/minute")
async def get_check(
    request: Request,
    check_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """**One check, with its findings and the provisions it depends on.**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        loaded = await service.load_check(session, user.org_id, check_id)
        if loaded is None:
            raise _http(service.check_not_found())
        return service.check_object(*loaded)


@router.get("/checks/{check_id}/report", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def get_check_report(
    request: Request,
    check_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> HTMLResponse:
    """**The report of a check as a self-contained HTML page (Italian).**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        loaded = await service.load_check(session, user.org_id, check_id)
        if loaded is None:
            raise _http(service.check_not_found())
        row, _ = loaded
        body = service.check_object(*loaded)
    checked_on = (body["checked_at"] or "")[:10]
    check = serialize.check_from_json(
        body["findings"],
        document=row.filename,
        checked_on=checked_on,
        document_date=body["document_date"],
        lang=row.lang,
    )
    return HTMLResponse(
        render_html(check),
        headers={
            # A page built from a tenant's document: no scripts, no embedding, no cache.
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'"
            ),
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/checks/{check_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_check(
    request: Request,
    check_id: uuid.UUID,
    user: CurrentUser = Depends(require_editor),
) -> Response:
    """**Delete a check, the provisions watched for it and its alerts.**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        loaded = await service.load_check(session, user.org_id, check_id)
        if loaded is None:
            raise _http(service.check_not_found())
        await service.delete_check(session, loaded[0])
        await session.commit()

    audit_log(
        AuditAction.DATA_ERASURE,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/documents/checks/{check_id}",
        detail="document check deleted",
        extra={"check_id": str(check_id)},
    )
    return Response(status_code=204)


@router.post("/checks/{check_id}/recheck")
@limiter.limit(settings_limit("document_check_rate_limit"))
async def recheck_check(
    request: Request,
    check_id: uuid.UUID,
    user: CurrentUser = Depends(require_editor),
    source: Any = Depends(get_text_source),
) -> dict[str, Any]:
    """
    **Compare the provisions of a stored check with the texts in force now.**

    The document is not needed (and not kept): what is compared is the official
    text of each provision on the day of the check. A provision that changed or
    disappeared sets `needs_review`, moves its findings under "correggere" with
    the text then and now, and writes one alert for the document.
    """
    org_id = user.org_id
    try:
        async with db_manager.session(org_id=str(org_id)) as session:
            loaded = await service.load_check(session, org_id, check_id)
            if loaded is None:
                raise service.check_not_found()
            stored = [service.dependency_json(dependency) for dependency in loaded[1]]
        answers = (
            await _run(org_id, lambda: service.recheck_provisions(stored, source)) if stored else {}
        )
        async with db_manager.session(org_id=str(org_id)) as session:
            loaded = await service.load_check(session, org_id, check_id)
            if loaded is None:
                raise service.check_not_found()
            row, dependencies = loaded
            changes = [
                answers.get(service.provision_key(service.dependency_json(dependency)))
                for dependency in dependencies
            ]
            fresh = await service.apply_recheck(session, row, dependencies, changes)
            await session.commit()
            body = service.check_object(row, dependencies)
    except DocumentCheckError as error:
        raise _http(error) from None

    logger.info(
        "document_check_rechecked",
        check_id=str(check_id),
        org_id=str(org_id),
        provisions=len(stored),
        newly_changed=len(fresh),
    )
    return body


# ─── Email preferences ───────────────────────────────────────────────


class Preferences(BaseModel):
    """Whether the user gets the digest email of the document surveillance."""

    email_digest: bool


async def _load_user(session: Any, user: CurrentUser) -> User:
    result = await session.execute(
        select(User).where(User.id == user.user_id, User.org_id == user.org_id)
    )
    row: User | None = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=USER_NOT_FOUND_DETAIL)
    return row


@router.get("/preferences")
@limiter.limit("60/minute")
async def get_preferences(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> Preferences:
    """**Whether you receive the email "documenti da rivedere".**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await _load_user(session, user)
        return Preferences(email_digest=bool(row.notify_document_changes))


@router.patch("/preferences")
@limiter.limit("20/minute")
async def update_preferences(
    request: Request,
    payload: Preferences,
    user: CurrentUser = Depends(get_current_user),
) -> Preferences:
    """**Turn the email "documenti da rivedere" on or off for yourself.**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await _load_user(session, user)
        row.notify_document_changes = payload.email_digest
        await session.commit()
    return Preferences(email_digest=payload.email_digest)


_UNSUBSCRIBE_PAGE = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{title} - NormaAI</title>
<style>
body {{ margin: 0; background: #ffffff; color: #0C1B33;
  font: 16px/1.55 "Public Sans", system-ui, -apple-system, "Segoe UI", sans-serif; }}
main {{ max-width: 560px; margin: 0 auto; padding: 64px 20px; }}
h1 {{ font: 600 1.6rem/1.25 Literata, Georgia, serif; margin: 0 0 12px; }}
p {{ margin: 0 0 12px; }}
a {{ color: #0A3A9C; }}
a:focus-visible {{ outline: 3px solid #0A3A9C; outline-offset: 2px; }}
</style></head>
<body><main><h1>{title}</h1><p>{text}</p>
<p><a href="{app_url}">Apri NormaAI</a></p></main></body></html>"""


def _unsubscribe_page(title: str, text: str, status_code: int) -> HTMLResponse:
    app_url = get_settings().normaai_public_url.rstrip("/") + "/app/controlla"
    return HTMLResponse(
        _UNSUBSCRIBE_PAGE.format(title=title, text=text, app_url=app_url),
        status_code=status_code,
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.api_route("/unsubscribe", methods=["GET", "POST"], response_class=HTMLResponse)
@limiter.limit("30/hour", key_func=client_ip_key)
async def unsubscribe(request: Request, token: str = Query(default="", max_length=400)):
    """
    **Turn the email "documenti da rivedere" off from the link in the email.**

    No login: the token in the link is signed and names the user. POST is the
    one-click form mail programs use (`List-Unsubscribe-Post`).
    """
    user_id = service.read_unsubscribe_token(token)
    if user_id is None:
        return _unsubscribe_page(
            "Link non valido",
            "Questo link non è valido o è scaduto. Puoi disattivare l'email dalle "
            "impostazioni di NormaAI.",
            400,
        )
    async with db_manager.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        row = result.scalar_one_or_none()
        if row is not None and row.notify_document_changes:
            row.notify_document_changes = False
            await session.commit()
    logger.info("document_digest_unsubscribed", user_id=str(user_id))
    return _unsubscribe_page(
        "Email disattivata",
        "Non riceverai più l'email con i documenti da rivedere. Gli avvisi restano in "
        "NormaAI, dove puoi anche riattivarla.",
        200,
    )
