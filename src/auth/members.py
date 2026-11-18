"""Members of an organisation: list them, change a role, remove one (admins only).

The organisation always keeps an active admin: the last one can be neither
demoted nor removed. Changes to the members of one organisation take a lock on
its row first (``SELECT ... FOR UPDATE`` on PostgreSQL), so two admins demoting
each other at the same moment cannot leave it without one.

Every query filters on the caller's organisation and runs in a session with its
tenant context (``db_manager.session(org_id=...)``): ``users`` has no
row-level security, the member's conversations and the assessments do.

Removing a member deletes the account and the member's own conversations (only
they could read them); clients, checks, reports and invites stay with the
organisation, with the member's name removed from them (``created_by`` and
``assessed_by`` become empty).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from sqlalchemy import delete, func, select, update

from src.db.models import Assessment, Conversation, Organization, User

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

Role = Literal["admin", "member", "viewer"]
ROLES: tuple[Role, ...] = ("admin", "member", "viewer")

# UI-facing (Italian) strings.
MEMBER_NOT_FOUND_DETAIL = "Membro non trovato."
LAST_ADMIN_DETAIL = (
    "L'organizzazione deve avere almeno un amministratore attivo: "
    "nomina prima un altro amministratore."
)


class MemberError(Exception):
    """A change the API refuses, with its HTTP status and Italian detail."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def list_members(session: AsyncSession, org_id: uuid.UUID) -> list[User]:
    """The organisation's accounts, oldest first."""
    result = await session.execute(
        select(User).where(User.org_id == org_id).order_by(User.created_at, User.email)
    )
    return list(result.scalars().all())


async def _lock_organisation(session: AsyncSession, org_id: uuid.UUID) -> None:
    await session.execute(
        select(Organization.id).where(Organization.id == org_id).with_for_update()
    )


async def _member(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
    result = await session.execute(select(User).where(User.id == user_id, User.org_id == org_id))
    user: User | None = result.scalar_one_or_none()
    if user is None:
        raise MemberError(404, MEMBER_NOT_FOUND_DETAIL)
    return user


async def _is_last_active_admin(session: AsyncSession, user: User) -> bool:
    if user.role != "admin" or not user.is_active:
        return False
    others = await session.execute(
        select(func.count())
        .select_from(User)
        .where(
            User.org_id == user.org_id,
            User.id != user.id,
            User.role == "admin",
            User.is_active.is_(True),
        )
    )
    return int(others.scalar() or 0) == 0


async def change_role(
    session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, role: Role
) -> tuple[User, str]:
    """Give a member ``role``; return (the member, the previous role). The caller commits."""
    if role not in ROLES:
        raise MemberError(422, "Ruolo non valido.")
    await _lock_organisation(session, org_id)
    user = await _member(session, org_id, user_id)
    previous = user.role
    if previous == role:
        return user, previous
    if role != "admin" and await _is_last_active_admin(session, user):
        raise MemberError(409, LAST_ADMIN_DETAIL)
    user.role = role
    return user, previous


async def remove_member(session: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> User:
    """Delete a member's account and own conversations; return the (deleted) member.

    The caller commits.
    """
    await _lock_organisation(session, org_id)
    user = await _member(session, org_id, user_id)
    if await _is_last_active_admin(session, user):
        raise MemberError(409, LAST_ADMIN_DETAIL)
    await session.execute(delete(Conversation).where(Conversation.user_id == user.id))
    await session.execute(
        update(Assessment)
        .where(Assessment.assessed_by == user.id)
        .values(assessed_by=None)
        .execution_options(synchronize_session=False)
    )
    # document_checks.created_by and invites.created_by: ON DELETE SET NULL.
    await session.execute(
        delete(User)
        .where(User.id == user.id, User.org_id == org_id)
        .execution_options(synchronize_session=False)
    )
    return user
