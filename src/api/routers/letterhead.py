"""The letterhead of the organisation: the heading of the PDFs it hands to its clients.

Routes, all under ``/api/v1/organization``:

- ``GET /letterhead``: ``{"configured", "name", "address", "contact",
  "footer_note", "logo", "updated_at"}``, where ``logo`` is
  ``{"content_type", "size"}`` or null. Without a letterhead ``configured`` is
  false and ``name`` is the organisation's name, which is what the PDFs show.
- ``PUT /letterhead``: the four texts as JSON (``name`` required). The same
  object back.
- ``DELETE /letterhead``: back to the organisation's name alone, logo
  included. 204.
- ``GET /letterhead/logo``: the logo, ``image/png`` or ``image/jpeg``; 404
  without one.
- ``PUT /letterhead/logo``: a PNG or a JPEG of at most 2 MB (multipart, field
  ``file``), checked and encoded again before it is stored
  (``src/reports/letterhead.py``). The letterhead object back; an organisation
  without a letterhead gets one with its name.
- ``DELETE /letterhead/logo``: the letterhead without its logo. The object back.

Access. Reading: any signed-in user of the organisation, since every PDF
carries the letterhead. Writing: the ``admin`` role, with a verified email
address when the deployment asks for one (``require_admin``). Every query
filters on the caller's ``org_id`` and runs in a session with the tenant
context (row-level security). Every change is in the audit log
(``admin.config.changed``), without the texts themselves.

Failures the admin can act on come back as ``{"detail": "<Italian sentence>"}``.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from src.api.rate_limit import limiter
from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user, require_admin
from src.db.engine import db_manager
from src.db.models import OrgLetterhead
from src.reports import letterhead
from src.reports.letterhead import LetterheadError

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/organization", tags=["Organization"])

RESOURCE = "/api/v1/organization/letterhead"
INVALID_TEXTS_DETAIL = (
    "Richiesta non valida: invia i testi della carta intestata come JSON "
    "(name, address, contact, footer_note)."
)
INVALID_LOGO_DETAIL = (
    "Richiesta non valida: invia il logo come file (multipart/form-data, campo file)."
)
MISSING_LOGO_DETAIL = "Scegli un file per il logo."
NO_LOGO_DETAIL = "La carta intestata non ha un logo."
# Room in the request body for the multipart boundaries and headers.
_BODY_OVERHEAD = 16 * 1024
# Longest text accepted before the checks of src/reports/letterhead.py, which
# give the real limits with a sentence the admin understands.
_RAW_MAX_CHARS = 2000


class LetterheadTexts(BaseModel):
    """The JSON of ``PUT /letterhead``."""

    name: str = Field(..., max_length=_RAW_MAX_CHARS, description="Name of the practice")
    address: str | None = Field(
        default=None, max_length=_RAW_MAX_CHARS, description="Up to 3 lines"
    )
    contact: str | None = Field(default=None, max_length=_RAW_MAX_CHARS, description="One line")
    footer_note: str | None = Field(
        default=None, max_length=_RAW_MAX_CHARS, description="One line at the foot of every page"
    )


def _http(error: LetterheadError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _audit(request: Request, user: CurrentUser, detail: str) -> None:
    audit_log(
        AuditAction.CONFIG_CHANGED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=RESOURCE,
        detail=detail,
    )


async def _row_for_writing(session: Any, user: CurrentUser) -> OrgLetterhead:
    """The organisation's letterhead row, a new one with its name when it has none."""
    row = await letterhead.load_row(session, user.org_id)
    if row is None:
        name = await letterhead.organisation_name(session, user.org_id)
        row = OrgLetterhead(
            org_id=user.org_id, name=(name or "Studio")[: letterhead.NAME_MAX_CHARS]
        )
        session.add(row)
    row.updated_by = user.user_id
    row.updated_at = datetime.now(UTC)
    return row


# ─── Texts ───────────────────────────────────────────────────────────


@router.get("/letterhead")
@limiter.limit("60/minute")
async def get_letterhead(
    request: Request, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """**The letterhead of your organisation, as the PDFs show it.**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        return letterhead.letterhead_object(await letterhead.load(session, user.org_id))


@router.put("/letterhead")
@limiter.limit("20/minute")
async def put_letterhead(
    request: Request, user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """
    **Set the texts of the letterhead (admins).**

    `name` (one line, at most 200 characters), `address` (at most 3 lines and
    300 characters), `contact` (one line, at most 200) and `footer_note` (one
    line at the foot of every page, at most 300). The logo is not touched.
    """
    try:
        payload = LetterheadTexts.model_validate(await request.json())
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail=INVALID_TEXTS_DETAIL) from None
    try:
        texts = letterhead.clean_texts(
            payload.name, payload.address, payload.contact, payload.footer_note
        )
    except LetterheadError as error:
        raise _http(error) from None
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await _row_for_writing(session, user)
        row.name = texts.name
        row.address = texts.address
        row.contact = texts.contact
        row.footer_note = texts.footer_note
        await session.commit()
        body = letterhead.letterhead_object(letterhead.from_row(row))
    _audit(request, user, "letterhead texts updated")
    return body


@router.delete("/letterhead", status_code=204)
@limiter.limit("20/minute")
async def delete_letterhead(
    request: Request, user: CurrentUser = Depends(require_admin)
) -> Response:
    """**Remove the letterhead, logo included (admins).** The PDFs go back to the organisation's name."""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await letterhead.load_row(session, user.org_id)
        if row is not None:
            await session.delete(row)
            await session.commit()
    _audit(request, user, "letterhead removed")
    return Response(status_code=204)


# ─── Logo ────────────────────────────────────────────────────────────


async def _limited(request: Request, limit: int) -> AsyncGenerator[bytes, None]:
    """The request body, refused as soon as it is longer than ``limit``."""
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > limit:
            raise letterhead.logo_too_large()
        yield chunk


async def _read_logo(request: Request) -> bytes:
    """The file of ``PUT /letterhead/logo``, read in memory with the size limit applied."""
    limit = letterhead.LOGO_MAX_BYTES + _BODY_OVERHEAD
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise letterhead.logo_too_large()
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type != "multipart/form-data":
        raise LetterheadError(415, INVALID_LOGO_DETAIL)
    parser = MultiPartParser(request.headers, _limited(request, limit), max_files=1, max_fields=4)
    # Never spooled to a temporary file on disk: the threshold is above the limit.
    parser.spool_max_size = limit + 1
    try:
        form = await parser.parse()
    except MultiPartException:
        raise LetterheadError(422, INVALID_LOGO_DETAIL) from None
    try:
        upload = form.get("file")
        if not isinstance(upload, UploadFile):
            raise LetterheadError(422, MISSING_LOGO_DETAIL)
        data = await upload.read()
    finally:
        await form.close()
    if len(data) > letterhead.LOGO_MAX_BYTES:
        raise letterhead.logo_too_large()
    return data


@router.get("/letterhead/logo")
@limiter.limit("60/minute")
async def get_logo(request: Request, user: CurrentUser = Depends(get_current_user)) -> Response:
    """**The logo of the letterhead** (`image/png` or `image/jpeg`); 404 without one."""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await letterhead.load_row(session, user.org_id)
        logo, logo_type = (row.logo, row.logo_type) if row is not None else (None, None)
    if not logo or logo_type not in letterhead.LOGO_TYPES.values():
        raise HTTPException(status_code=404, detail=NO_LOGO_DETAIL)
    extension = "png" if logo_type == "image/png" else "jpg"
    return Response(
        content=logo,
        media_type=logo_type,
        headers={
            "Content-Disposition": f'inline; filename="logo.{extension}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'",
        },
    )


@router.put("/letterhead/logo")
@limiter.limit("10/minute")
async def put_logo(request: Request, user: CurrentUser = Depends(require_admin)) -> dict[str, Any]:
    """
    **Upload the logo of the letterhead (admins).**

    A PNG or a JPEG of at most 2 MB, as `multipart/form-data` (field `file`),
    at most 6000 pixels a side. It is stored encoded again, without metadata and
    at most 1000 pixels a side.
    """
    try:
        logo, logo_type = letterhead.normalize_logo(await _read_logo(request))
    except LetterheadError as error:
        raise _http(error) from None
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await _row_for_writing(session, user)
        row.logo = logo
        row.logo_type = logo_type
        await session.commit()
        body = letterhead.letterhead_object(letterhead.from_row(row))
    _audit(request, user, f"letterhead logo updated ({logo_type}, {len(logo)} bytes)")
    return body


@router.delete("/letterhead/logo")
@limiter.limit("20/minute")
async def delete_logo(
    request: Request, user: CurrentUser = Depends(require_admin)
) -> dict[str, Any]:
    """**Remove the logo, keep the texts (admins).**"""
    async with db_manager.session(org_id=str(user.org_id)) as session:
        row = await letterhead.load_row(session, user.org_id)
        if row is not None and row.logo is not None:
            row.logo = None
            row.logo_type = None
            row.updated_by = user.user_id
            row.updated_at = datetime.now(UTC)
            await session.commit()
        body = letterhead.letterhead_object(await letterhead.load(session, user.org_id))
    _audit(request, user, "letterhead logo removed")
    return body
