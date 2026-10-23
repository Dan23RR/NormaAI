#!/usr/bin/env python3
"""Create a registration invite from the command line (bootstrap the first admin).

In invite mode (the default, REGISTRATION_MODE=invite) nobody can register
without a code and only an existing admin can mint one through the API - so
the very first admin is invited from here, on the server:

    python scripts/create_invite.py --email founder@acme.com
    python scripts/create_invite.py --email cfo@acme.com --org-id <uuid> --role member --days 7

Without --org-id the invitee creates a NEW organization and becomes its admin;
with --org-id they join that organization with --role (default: member).

Reads DATABASE_URL from the environment / .env exactly like the API. The code
is printed ONCE - only its SHA-256 is stored. Run as the same DB role the app
uses (the migration-008 RLS policies allow a session without org context).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Make `src` importable when invoked as `python scripts/create_invite.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import select  # noqa: E402

from src.auth.invites import (  # noqa: E402
    INVITE_DEFAULT_EXPIRY_DAYS,
    INVITE_MAX_EXPIRY_DAYS,
    new_invite,
)
from src.db.engine import db_manager  # noqa: E402
from src.db.models import Organization  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a NormaAI registration invite.")
    parser.add_argument("--email", required=True, help="Invitee email (bound to the code)")
    parser.add_argument(
        "--org-id",
        default=None,
        help="Existing organization UUID to join; omit to let the invitee create a new one",
    )
    parser.add_argument(
        "--role",
        default="member",
        choices=("member", "viewer", "admin"),
        help="Role inside the joined organization (ignored without --org-id: always admin)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=INVITE_DEFAULT_EXPIRY_DAYS,
        help=f"Validity in days (1-{INVITE_MAX_EXPIRY_DAYS}, default {INVITE_DEFAULT_EXPIRY_DAYS})",
    )
    args = parser.parse_args(argv)
    if not 1 <= args.days <= INVITE_MAX_EXPIRY_DAYS:
        parser.error(f"--days must be between 1 and {INVITE_MAX_EXPIRY_DAYS}")
    return args


async def create(email: str, org_id: uuid.UUID | None, role: str, days: int) -> tuple[str, str]:
    """Persist the invite; return (invite_id, plaintext_code)."""
    db_manager.init()
    try:
        async with db_manager.session() as db:
            if org_id is not None:
                found = await db.execute(select(Organization.id).where(Organization.id == org_id))
                if found.scalar_one_or_none() is None:
                    raise SystemExit(f"Organization {org_id} not found.")
            invite, code = new_invite(
                email=email,
                org_id=org_id,
                role=role if org_id is not None else "admin",
                created_by=None,
                expires_in_days=days,
            )
            db.add(invite)
            await db.commit()
            return str(invite.id), code
    finally:
        await db_manager.close()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    org_id = uuid.UUID(args.org_id) if args.org_id else None
    invite_id, code = asyncio.run(create(args.email, org_id, args.role, args.days))
    target = (
        f"join organization {org_id} as {args.role}"
        if org_id
        else "create a new organization (admin)"
    )
    print(
        f"Invite {invite_id} for {args.email.strip().lower()} - {target}, valid {args.days} days."
    )
    print("Invite code (shown once, store it safely):")
    print(f"  {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
