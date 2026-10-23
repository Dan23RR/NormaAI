"""Email verification: signed tokens + the transactional email.

Flow:
1. ``make_email_verification_token(user_id, email)`` after registration (or on
   resend) -> a link ``<NORMAAI_PUBLIC_URL>/verify-email?token=...`` mailed via
   Resend (a no-op with a log line when RESEND_API_KEY is unset).
2. ``POST /auth/verify-email`` parses the token, loads the user and checks the
   MAC against the user's CURRENT email, then flips ``users.email_verified``.
   Replays are harmless: once verified there is nothing left to flip, and a
   changed email invalidates every token issued for the old one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import structlog

from src.auth.tokens import make_signed_token, parse_token_subject, verify_signed_token
from src.config import get_settings

logger = structlog.get_logger()

EMAIL_VERIFICATION_PURPOSE = "email-verify"

# UI-facing (Italian) strings.
INVALID_VERIFICATION_TOKEN_DETAIL = "Token di verifica non valido o scaduto."
EMAIL_NOT_VERIFIED_DETAIL = "Conferma l'indirizzo email per usare NormaAI."


def _normalise(email: str) -> str:
    return email.strip().lower()


def make_email_verification_token(
    user_id: uuid.UUID, email: str, *, ttl_hours: int | None = None
) -> str:
    ttl = ttl_hours if ttl_hours is not None else get_settings().email_verification_token_ttl_hours
    expires_at = datetime.now(UTC) + timedelta(hours=ttl)
    return make_signed_token(
        EMAIL_VERIFICATION_PURPOSE, str(user_id), expires_at, binding=_normalise(email)
    )


def parse_email_verification_token(token: str) -> uuid.UUID | None:
    """User id from a well-formed, unexpired token (signature checked later,
    once the user's current email is known)."""
    subject = parse_token_subject(token)
    if subject is None:
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def verify_email_verification_token(token: str, email: str) -> uuid.UUID | None:
    """User id if ``token`` is valid for ``email`` (the user's current address)."""
    subject = verify_signed_token(EMAIL_VERIFICATION_PURPOSE, token, binding=_normalise(email))
    if subject is None:
        return None
    try:
        return uuid.UUID(subject)
    except ValueError:
        return None


def build_verification_url(token: str) -> str:
    base = get_settings().normaai_public_url.rstrip("/")
    return f"{base}/verify-email?token={token}"


def send_verification_email(user_id: uuid.UUID, email: str, name: str) -> tuple[bool, str | None]:
    """Mint a token and send the verification email (sync; call via a
    background task or ``asyncio.to_thread``). Never raises."""
    from src.email_client import send_verification_email as _send

    token = make_email_verification_token(user_id, email)
    try:
        ok, err = _send(
            to_email=email, recipient_name=name, verify_url=build_verification_url(token)
        )
    except Exception as e:  # noqa: BLE001 - email is best-effort
        ok, err = False, f"{type(e).__name__}: {e}"
    if ok:
        logger.info("verification_email_sent", user_id=str(user_id))
    else:
        logger.warning("verification_email_not_sent", user_id=str(user_id), reason=err)
    return ok, err
