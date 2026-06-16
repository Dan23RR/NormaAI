"""Public leads endpoint + Codex download.

POST /api/v1/leads             — capture lead, return signed download_url
GET  /api/v1/codex/download    — verify HMAC token, stream PDF, mark downloaded_at

Public (no JWT required), rate-limited per-IP to mitigate spam.

NOTE 2026-04-28: do NOT add `from __future__ import annotations` here.
FastAPI 0.115 + Pydantic 2.13 has a known forward-ref bug that breaks
OpenAPI schema generation when route body params are annotated as
ForwardRef strings.
"""

import base64
import hashlib
import hmac
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import limiter
from src.audit import get_client_ip
from src.config import get_settings
from src.db.engine import get_db_session
from src.db.models import Lead
from src.email_client import send_codex_email

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Leads"])


# ────────────────────── Constants / paths ──────────────────────

# PDF location on disk (rendered by marketing/generate_pdf_native.py)
_REPO_ROOT = Path(__file__).resolve().parents[3]
CODEX_PDF_PATH = _REPO_ROOT / "marketing" / "codex_post_omnibus_v1.pdf"
CODEX_DOWNLOAD_FILENAME = "NormaAI-Codex-Post-Omnibus-2025-2029.pdf"

# Token TTL (30 giorni dal lead capture)
TOKEN_TTL_DAYS = 30

# Anti-spam window
RATE_LIMIT_WINDOW = timedelta(hours=1)
RATE_LIMIT_MAX_PER_IP = 5


# ────────────────────── Token signing ──────────────────────


def _hmac_secret() -> bytes:
    """HMAC key derived from APP_SECRET_KEY. Distinct domain ('codex-dl')
    so the same APP_SECRET_KEY can be used for JWT etc. without collision."""
    settings = get_settings()
    raw = (settings.app_secret_key + ":codex-dl").encode("utf-8")
    return hashlib.sha256(raw).digest()


def make_download_token(lead_id: uuid.UUID, expires_at: datetime) -> str:
    """Build url-safe token: <lead_id>.<exp_unix>.<hmac>"""
    exp_unix = int(expires_at.timestamp())
    payload = f"{lead_id}.{exp_unix}".encode("ascii")
    sig = hmac.new(_hmac_secret(), payload, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode("ascii")
    return f"{payload.decode('ascii')}.{sig_b64}"


def verify_download_token(token: str) -> uuid.UUID | None:
    """Return the lead_id if token is valid + not expired, else None."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        lead_id_str, exp_str, sig_b64 = parts
        lead_id = uuid.UUID(lead_id_str)
        exp_unix = int(exp_str)
    except (ValueError, TypeError):
        return None
    # Expiry
    if exp_unix < int(datetime.now(UTC).timestamp()):
        return None
    # Signature
    payload = f"{lead_id_str}.{exp_str}".encode("ascii")
    expected_sig = hmac.new(_hmac_secret(), payload, hashlib.sha256).digest()
    expected_b64 = base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(expected_b64, sig_b64):
        return None
    return lead_id


def _build_download_url(lead_id: uuid.UUID) -> tuple[str, str]:
    """Return (relative_url, absolute_url) for the codex download token."""
    expires = datetime.now(UTC) + timedelta(days=TOKEN_TTL_DAYS)
    token = make_download_token(lead_id, expires)
    rel = f"/api/v1/codex/download?t={token}"
    base = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    return rel, f"{base}{rel}"


# ────────────────────── Schemas ──────────────────────


class LeadCreate(BaseModel):
    email: EmailStr = Field(..., description="Business email")
    org_name: str | None = Field(None, max_length=255)
    role: str | None = Field(None, max_length=100)
    source: str = Field(
        default="codex_download",
        pattern=r"^(codex_download|demo_request|newsletter)$",
    )


class LeadResponse(BaseModel):
    ok: bool = True
    message: str = "Richiesta registrata. Riceverai il Codex entro pochi secondi."
    download_url: str | None = Field(
        None,
        description="Relative URL to download the Codex (signed, expires in 30 days)",
    )


# ────────────────────── DB helpers ──────────────────────


async def _ip_recent_count(db: AsyncSession, ip: str) -> int:
    if not ip:
        return 0
    cutoff = datetime.now(UTC) - RATE_LIMIT_WINDOW
    stmt = select(func.count(Lead.id)).where(Lead.ip_address == ip).where(Lead.created_at >= cutoff)
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def _find_recent_lead_by_email(db: AsyncSession, email: str) -> Lead | None:
    """Return the most recent Lead for this email created in last 24h, or None."""
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    stmt = (
        select(Lead)
        .where(Lead.email == email)
        .where(Lead.created_at >= cutoff)
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ────────────────────── Routes ──────────────────────


@router.post(
    "/leads",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a public lead and receive a signed Codex download URL",
)
@limiter.limit("10/hour")
async def create_lead(
    request: Request,
    payload: LeadCreate,
    db: AsyncSession = Depends(get_db_session),
) -> LeadResponse:
    ip = get_client_ip(request) or ""
    user_agent = request.headers.get("user-agent", "")[:500]
    referer = request.headers.get("referer", "")[:500]

    # 1. DB-level rate limit
    recent = await _ip_recent_count(db, ip)
    if recent >= RATE_LIMIT_MAX_PER_IP:
        logger.warning("lead_rate_limit_hit", ip=ip, recent_count=recent, email=payload.email)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Troppe richieste da questo indirizzo. Riprova più tardi.",
        )

    # 2. Idempotent UX — return same download_url if email already registered in last 24h
    existing = await _find_recent_lead_by_email(db, payload.email)
    if existing is not None:
        logger.info("lead_duplicate_within_24h", email=payload.email, source=payload.source)
        rel, _abs = _build_download_url(existing.id)
        return LeadResponse(
            ok=True,
            message="Hai già richiesto il Codex di recente — ecco di nuovo il link.",
            download_url=rel,
        )

    # 3. Persist
    lead = Lead(
        email=payload.email,
        org_name=payload.org_name,
        role=payload.role,
        source=payload.source,
        ip_address=ip,
        user_agent=user_agent,
        referer=referer,
        status="new",
    )
    db.add(lead)
    await db.commit()
    await db.refresh(lead)

    # 4. Build download URL
    rel_url, abs_url = _build_download_url(lead.id)

    # 5. Send email (best-effort: log if SMTP not configured, never block response)
    sent_ok, err = send_codex_email(
        to_email=payload.email,
        recipient_name=(payload.org_name or "").split()[0] if payload.org_name else "",
        download_url=abs_url,
    )
    now = datetime.now(UTC)
    update_fields: dict = {}
    if sent_ok:
        update_fields["last_email_sent_at"] = now
    elif err and err != "smtp_not_configured":
        update_fields["email_error"] = err
    if update_fields:
        await db.execute(update(Lead).where(Lead.id == lead.id).values(**update_fields))
        await db.commit()

    logger.info(
        "lead_captured",
        lead_id=str(lead.id),
        email=payload.email,
        org_name=payload.org_name,
        source=payload.source,
        ip=ip,
        email_sent=sent_ok,
        email_error=err if not sent_ok else None,
    )

    return LeadResponse(
        ok=True,
        message="Richiesta registrata. Ti abbiamo inviato il Codex via email."
        if sent_ok
        else "Richiesta registrata. Scarica il Codex con il link qui sotto.",
        download_url=rel_url,
    )


@router.get(
    "/codex/download",
    summary="Download the Codex PDF (signed token required)",
    response_class=FileResponse,
)
@limiter.limit("30/hour")
async def codex_download(
    request: Request,
    t: str,  # token query param
    db: AsyncSession = Depends(get_db_session),
):
    if not CODEX_PDF_PATH.exists():
        logger.error("codex_pdf_missing", path=str(CODEX_PDF_PATH))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Codex temporaneamente non disponibile. Scrivi a info@normaai.org.",
        )

    lead_id = verify_download_token(t)
    if lead_id is None:
        logger.warning("codex_download_invalid_token", token_prefix=t[:20] if t else "")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Link non valido o scaduto. Richiedi un nuovo link su normaai.it.",
        )

    # Fetch lead, mark download (best-effort; allow download even if lead row missing)
    stmt = select(Lead).where(Lead.id == lead_id)
    result = await db.execute(stmt)
    lead = result.scalar_one_or_none()
    if lead is None:
        logger.warning("codex_download_lead_missing", lead_id=str(lead_id))
        # Still serve the PDF: token was valid; lead may have been GDPR-deleted.
    else:
        now = datetime.now(UTC)
        await db.execute(
            update(Lead)
            .where(Lead.id == lead.id)
            .values(
                downloaded_at=lead.downloaded_at or now,
                download_count=Lead.download_count + 1,
            )
        )
        await db.commit()
        logger.info(
            "codex_download_served",
            lead_id=str(lead_id),
            email=lead.email,
            download_count=lead.download_count + 1,
        )

    return FileResponse(
        path=str(CODEX_PDF_PATH),
        media_type="application/pdf",
        filename=CODEX_DOWNLOAD_FILENAME,
    )
