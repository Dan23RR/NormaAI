#!/usr/bin/env python3
"""NormaAI staff and account operations, from the command line only.

Staff (corpus crawl, invites for new organizations) is the ``users.is_staff``
flag: this script is the only thing that sets it. No setting, registration or
token claim does, and the API honours it only on a verified email address.

    python scripts/staff.py list
    python scripts/staff.py grant ops@normaai.org
    python scripts/staff.py revoke ops@normaai.org
    python scripts/staff.py reset-password anna@studio.it [--send]
    python scripts/staff.py end-sessions anna@studio.it

- ``grant`` needs an active account with a verified email address, and names
  the account's organisation: check it is the one you expect.
- ``reset-password`` mints a single-use password-reset link (the one of
  ``POST /auth/password-reset``, valid PASSWORD_RESET_TOKEN_TTL_MINUTES) and
  prints it once, to hand over to the user; ``--send`` also emails it. The
  account's sessions end when the link is used.
- ``end-sessions`` refuses every token issued until now (stolen device,
  departure): the user signs in again.

Reads DATABASE_URL from the environment / .env exactly like the API; on the
server, inside the app container:

    docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm app \\
        python scripts/staff.py grant ops@normaai.org

``users`` has no row-level security, so the app role can run it too. The API
processes see a change within AUTH_ACCOUNT_CACHE_SECONDS.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Make `src` importable when invoked as `python scripts/staff.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from src.audit import AuditAction, AuditOutcome, audit_log  # noqa: E402
from src.auth import password_reset  # noqa: E402
from src.config import get_settings  # noqa: E402
from src.db.models import Organization, User  # noqa: E402


class StaffError(Exception):
    """A request the script refuses; the message is printed and the exit code is 1."""


async def _account(session: Any, email: str) -> User:
    result = await session.execute(select(User).where(User.email == email.strip()))
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise StaffError(f"No account with the email {email.strip()}.")
    return user


async def list_staff(manager: Any) -> list[str]:
    """One line per staff account: email, organization, verified, active."""
    async with manager.session() as session:
        result = await session.execute(
            select(User, Organization.name)
            .join(Organization, User.org_id == Organization.id)
            .where(User.is_staff.is_(True))
            .order_by(User.email)
        )
        lines = []
        for user, org_name in result.all():
            notes = []
            if not user.email_verified:
                notes.append("email NOT verified: not staff until it is")
            if not user.is_active:
                notes.append("deactivated")
            suffix = f" ({'; '.join(notes)})" if notes else ""
            lines.append(f"{user.email}  [{org_name}]{suffix}")
        return lines


async def _organisation_name(session: Any, user: User) -> str:
    result = await session.execute(select(Organization.name).where(Organization.id == user.org_id))
    return str(result.scalar_one_or_none() or user.org_id)


async def grant(manager: Any, email: str) -> str:
    """Make an account staff; the message names its organisation, to check."""
    async with manager.session() as session:
        user = await _account(session, email)
        org_name = await _organisation_name(session, user)
        if not user.is_active:
            raise StaffError(f"{user.email} is deactivated: staff is not granted.")
        if not user.email_verified:
            raise StaffError(
                f"{user.email} has not verified its email address: staff is not granted. "
                "Ask the user to confirm it (or to reset the password, which confirms it)."
            )
        if user.is_staff:
            return f"{user.email} [{org_name}] is already staff."
        user.is_staff = True
        user_id, org_id = user.id, user.org_id
        await session.commit()
    audit_log(
        AuditAction.STAFF_GRANTED,
        AuditOutcome.SUCCESS,
        user_id=str(user_id),
        org_id=str(org_id),
        resource="scripts/staff.py",
        detail=f"Staff granted to {email.strip()}",
    )
    return f"{email.strip()} [{org_name}] is now staff."


async def revoke(manager: Any, email: str) -> str:
    async with manager.session() as session:
        user = await _account(session, email)
        if not user.is_staff:
            return f"{user.email} is not staff."
        user.is_staff = False
        user_id, org_id = user.id, user.org_id
        await session.commit()
    audit_log(
        AuditAction.STAFF_REVOKED,
        AuditOutcome.SUCCESS,
        user_id=str(user_id),
        org_id=str(org_id),
        resource="scripts/staff.py",
        detail=f"Staff revoked from {email.strip()}",
    )
    return f"{email.strip()} is no longer staff."


async def reset_password(manager: Any, email: str, *, send: bool = False) -> tuple[str, str]:
    """Mint a reset link; return (message, link). The link is shown once."""
    async with manager.session() as session:
        user = await _account(session, email)
        if not user.is_active:
            raise StaffError(f"{user.email} is deactivated: no reset link.")
        token = password_reset.issue_link(user)
        user_id, org_id, to_email, name = user.id, user.org_id, user.email, user.name
        await session.commit()
    audit_log(
        AuditAction.PASSWORD_RESET_REQUESTED,
        AuditOutcome.SUCCESS,
        user_id=str(user_id),
        org_id=str(org_id),
        resource="scripts/staff.py",
        detail="Password reset link minted by staff",
    )
    ttl = get_settings().password_reset_token_ttl_minutes
    message = f"Password reset link for {to_email}, valid {ttl} minutes, once:"
    if send:
        sent = await asyncio.to_thread(password_reset.send_reset_email, to_email, name, token)
        message += " (emailed)" if sent else " (NOT emailed: see the log; hand it over yourself)"
    return message, password_reset.build_reset_url(token)


async def end_sessions(manager: Any, email: str) -> str:
    async with manager.session() as session:
        user = await _account(session, email)
        user.sessions_revoked_at = datetime.now(UTC)
        user_id, org_id = user.id, user.org_id
        await session.commit()
    audit_log(
        AuditAction.SESSIONS_ENDED,
        AuditOutcome.SUCCESS,
        user_id=str(user_id),
        org_id=str(org_id),
        resource="scripts/staff.py",
        detail="Every session ended by staff",
    )
    return f"Every session of {email.strip()} is ended: the next request asks to sign in again."


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NormaAI staff and account operations.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List the staff accounts")
    for name, text in (
        ("grant", "Make an account staff (active, verified email)"),
        ("revoke", "Take staff away from an account"),
        ("end-sessions", "Refuse every token issued to an account until now"),
    ):
        commands.add_parser(name, help=text).add_argument("email")
    reset = commands.add_parser("reset-password", help="Mint a single-use password-reset link")
    reset.add_argument("email")
    reset.add_argument("--send", action="store_true", help="Also email the link")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace, manager: Any) -> list[str]:
    """The lines to print for ``args`` (raises StaffError)."""
    if args.command == "list":
        found = await list_staff(manager)
        return found or ["No staff account."]
    if args.command == "grant":
        return [await grant(manager, args.email)]
    if args.command == "revoke":
        return [await revoke(manager, args.email)]
    if args.command == "end-sessions":
        return [await end_sessions(manager, args.email)]
    message, link = await reset_password(manager, args.email, send=args.send)
    return [message, f"  {link}"]


async def _main(args: argparse.Namespace) -> list[str]:
    from src.db.engine import db_manager

    db_manager.init()
    try:
        return await run(args, db_manager)
    finally:
        await db_manager.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        lines = asyncio.run(_main(args))
    except StaffError as error:
        print(str(error), file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
