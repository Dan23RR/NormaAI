"""Invite codes for invite-only registration (``settings.registration_mode``).

An invite is a single-use, expiring code bound to an email. Only the SHA-256
of the code is persisted (``Invite.code_hash``); the plaintext is returned
exactly once to whoever created it (admin API response or CLI output).

Redemption is race-safe: ``redeem_invite`` runs a conditional UPDATE
(``WHERE used_at IS NULL``) so two concurrent registrations with the same code
cannot both succeed - under READ COMMITTED the loser's UPDATE re-evaluates the
predicate after the winner commits and matches zero rows.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal

from sqlalchemy import select, update

from src.db.models import Invite

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

INVITE_DEFAULT_EXPIRY_DAYS = 14
INVITE_MAX_EXPIRY_DAYS = 90

# UI-facing (Italian) error strings.
INVALID_INVITE_DETAIL = "Codice di invito non valido o scaduto."
REGISTRATIONS_CLOSED_DETAIL = "Le registrazioni sono chiuse."

InviteStatus = Literal["pending", "used", "expired"]


def generate_invite_code() -> str:
    """Unguessable, URL-safe code (192 bits of entropy)."""
    return secrets.token_urlsafe(24)


def hash_invite_code(code: str) -> str:
    """Storage form of a code: SHA-256 hex of the trimmed plaintext."""
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def new_invite(
    *,
    email: str,
    org_id: uuid.UUID | None,
    role: str = "member",
    created_by: uuid.UUID | None = None,
    expires_in_days: int = INVITE_DEFAULT_EXPIRY_DAYS,
) -> tuple[Invite, str]:
    """Build an (unpersisted) Invite and return it with its plaintext code."""
    code = generate_invite_code()
    invite = Invite(
        id=uuid.uuid4(),
        code_hash=hash_invite_code(code),
        email=email.strip().lower(),
        org_id=org_id,
        role=role,
        created_by=created_by,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    return invite, code


def _as_utc(value: datetime) -> datetime:
    # SQLite (tests) hands back naive datetimes for timezone-aware columns.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def invite_status(invite: Invite, now: datetime | None = None) -> InviteStatus:
    """``used`` wins over ``expired``; ``pending`` = still redeemable."""
    now = now or datetime.now(UTC)
    if invite.used_at is not None:
        return "used"
    if _as_utc(invite.expires_at) <= now:
        return "expired"
    return "pending"


async def find_redeemable_invite(db: AsyncSession, code: str | None) -> Invite | None:
    """Return the invite for ``code`` if it exists, is unused and unexpired."""
    if not code or not code.strip():
        return None
    result = await db.execute(select(Invite).where(Invite.code_hash == hash_invite_code(code)))
    invite = result.scalar_one_or_none()
    if invite is None or invite_status(invite) != "pending":
        return None
    return invite


async def redeem_invite(db: AsyncSession, invite: Invite, user_id: uuid.UUID) -> bool:
    """Mark ``invite`` used by ``user_id``; False if another request won the race.

    The statement is executed (not just flushed later) so the row is updated
    BEFORE the caller switches the RLS org context. ``synchronize_session`` is
    off on purpose: touching the loaded instance would schedule a second UPDATE
    at commit, which an org-scoped session could no longer see for an org-less
    invite.
    """
    result = await db.execute(
        update(Invite)
        .where(Invite.id == invite.id, Invite.used_at.is_(None))
        .values(used_at=datetime.now(UTC), used_by=user_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1
