"""Password reset: single-use, short-lived links, stored only as a hash.

Flow:
1. ``POST /auth/password-reset {"email"}`` answers the same whether or not the
   address has an account, and does the work after the answer
   (``request_reset``): for an active account it mints a token, stores its
   SHA-256 and expiry on the user (``users.password_reset_token_hash`` and
   ``password_reset_expires_at``: one pending link per account, a new request
   replaces it) and mails ``<NORMAAI_PUBLIC_URL>/reset-password?token=...``
   through Resend (without RESEND_API_KEY nothing leaves and the log says so).
   Within ``RESEND_COOLDOWN`` of a link, no other is sent: the form cannot be
   used to flood someone's inbox.
2. ``POST /auth/password-reset/confirm {"token", "password"}`` (``confirm_reset``)
   sets the new password with a conditional UPDATE, so a link works once even
   when two requests race. It clears the link, confirms the email address (the
   link proves it is read by its owner) and sets ``users.sessions_revoked_at``:
   every session opened before ends (access tokens at the next request,
   refresh tokens at the next refresh).

Staff can mint the same link from the command line, for someone whose email
does not arrive: ``python scripts/staff.py reset-password <email>``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select, update

from src.config import get_settings
from src.db.models import User

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

# UI-facing (Italian) strings.
INVALID_RESET_TOKEN_DETAIL = (
    "Il link per reimpostare la password non è valido o è scaduto. "
    "Chiedine uno nuovo dalla pagina di accesso."
)


def reset_requested_detail(ttl_minutes: int) -> str:
    """The one answer of the request, whatever the address."""
    return (
        "Se l'indirizzo corrisponde a un account attivo, riceverai un'email con il link "
        f"per scegliere una nuova password. Il link vale {ttl_minutes} minuti e una sola volta."
    )


# A second link for the same account is not sent within this delay.
RESEND_COOLDOWN = timedelta(minutes=5)


def _as_utc(value: datetime) -> datetime:
    # SQLite (tests) hands back naive datetimes for timezone-aware columns.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def hash_secret(secret: str) -> str:
    """Storage form of a link's secret: SHA-256 hex."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def make_token(user_id: uuid.UUID) -> tuple[str, str]:
    """(token for the link, hash to store). 256 random bits; the id is only a locator."""
    secret = secrets.token_urlsafe(32)
    return f"{user_id}.{secret}", hash_secret(secret)


def parse_token(token: str) -> tuple[uuid.UUID, str] | None:
    """(user id, secret) of a well-formed token, else None."""
    user_part, _, secret = (token or "").strip().partition(".")
    if not secret:
        return None
    try:
        return uuid.UUID(user_part), secret
    except ValueError:
        return None


def build_reset_url(token: str) -> str:
    base = get_settings().normaai_public_url.rstrip("/")
    return f"{base}/reset-password?token={token}"


def _ttl() -> timedelta:
    return timedelta(minutes=get_settings().password_reset_token_ttl_minutes)


def recently_sent(user: User, now: datetime) -> bool:
    """True when a link for ``user`` went out less than ``RESEND_COOLDOWN`` ago."""
    if not user.password_reset_token_hash or user.password_reset_expires_at is None:
        return False
    issued_at = _as_utc(user.password_reset_expires_at) - _ttl()
    return now - issued_at < RESEND_COOLDOWN


def issue_link(user: User, now: datetime | None = None) -> str:
    """Give ``user`` a new pending link (replacing any other); return its token.

    The caller commits the session.
    """
    now = now or datetime.now(UTC)
    token, digest = make_token(user.id)
    user.password_reset_token_hash = digest
    user.password_reset_expires_at = now + _ttl()
    return token


def send_reset_email(email: str, name: str, token: str) -> bool:
    """Mail the link (sync: call off the event loop). Never raises."""
    from src.email_client import send_password_reset_email

    try:
        ok, err = send_password_reset_email(
            to_email=email,
            recipient_name=name,
            reset_url=build_reset_url(token),
            ttl_minutes=get_settings().password_reset_token_ttl_minutes,
        )
    except Exception as e:  # noqa: BLE001 - email is best-effort
        ok, err = False, type(e).__name__
    if not ok:
        logger.warning("password_reset_email_not_sent", reason=err)
    return ok


async def request_reset(email: str, *, manager: Any = None) -> bool:
    """Background half of ``POST /auth/password-reset``: True when a link was sent.

    Looks the address up exactly as the login does. Nothing happens for an
    unknown or deactivated account, or within the cooldown of the last link.
    """
    from src.db.engine import db_manager

    manager = manager or db_manager
    now = datetime.now(UTC)
    async with manager.session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            logger.info("password_reset_no_account")
            return False
        if recently_sent(user, now):
            logger.info("password_reset_cooldown", user_id=str(user.id))
            return False
        token = issue_link(user, now)
        user_id, to_email, name = user.id, user.email, user.name
        await session.commit()
    sent = await asyncio.to_thread(send_reset_email, to_email, name, token)
    logger.info("password_reset_link_issued", user_id=str(user_id), emailed=sent)
    return sent


async def confirm_reset(
    session: AsyncSession, token: str, password: str, now: datetime | None = None
) -> User | None:
    """Set the password of the link's account; None when the link is not valid.

    Valid: well formed, of an active account, its hash is the pending one and it
    has not expired. The password is hashed (bcrypt, off the event loop) only
    for a valid link. The UPDATE repeats those conditions, so of two requests
    with the same link only one changes the password. The caller commits.
    """
    from src.auth.security import hash_password_async

    parsed = parse_token(token)
    if parsed is None:
        return None
    user_id, secret = parsed
    now = now or datetime.now(UTC)
    result = await session.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not user.password_reset_token_hash
        or user.password_reset_expires_at is None
        or _as_utc(user.password_reset_expires_at) <= now
    ):
        return None
    digest = hash_secret(secret)
    if not hmac.compare_digest(digest, user.password_reset_token_hash):
        return None
    password_hash = await hash_password_async(password)
    changed = await session.execute(
        update(User)
        .where(
            User.id == user_id,
            User.password_reset_token_hash == digest,
            User.password_reset_expires_at > now,
        )
        .values(
            hashed_password=password_hash,
            password_reset_token_hash=None,
            password_reset_expires_at=None,
            sessions_revoked_at=now,
            email_verified=True,
        )
        .execution_options(synchronize_session=False)
    )
    if getattr(changed, "rowcount", 0) != 1:
        return None
    return user
