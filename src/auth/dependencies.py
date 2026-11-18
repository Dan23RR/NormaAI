"""FastAPI dependencies for authentication and authorization.

An access token proves who signed in and when; it is not believed on its own.
On every authenticated request ``get_current_user`` reads the account from the
database (kept ``settings.auth_account_cache_seconds`` per process): the user
must still exist, be active and belong to the token's organisation, the token
must not predate ``users.sessions_revoked_at``, and the role, the staff flag
and the verified email used for the request are the ones in the database. A
removed member, a changed role or ended sessions take effect within that delay.
"""

import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.security import TokenPayload, decode_token, issued_before, token_blacklist
from src.config import get_settings

logger = structlog.get_logger(__name__)

security_scheme = HTTPBearer(auto_error=False)

STAFF_ONLY_DETAIL = "Operazione riservata al personale NormaAI."
READ_ONLY_DETAIL = "Il tuo ruolo consente solo la lettura."
ADMIN_ONLY_DETAIL = "Operazione riservata agli amministratori dell'organizzazione."
ACCOUNT_CHECK_UNAVAILABLE_DETAIL = (
    "Non riesco a verificare l'account in questo momento. Riprova tra poco."
)


class CurrentUser:
    """Authenticated user context: the token's identity, the account's live state."""

    def __init__(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        role: str,
        email: str | None = None,
        email_verified: bool | None = None,
        is_staff: bool = False,
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        self.email = email
        self.email_verified = email_verified
        # users.is_staff, read from the database; never from the token.
        self.is_staff = is_staff

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_viewer(self) -> bool:
        return self.role == "viewer"


# ─── The account behind a token ──────────────────────────────────


@dataclass(frozen=True)
class AccountState:
    """What the database says of a user, as far as authorization is concerned."""

    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    is_active: bool
    is_staff: bool
    email: str | None
    email_verified: bool | None
    sessions_revoked_at: datetime | None = None


async def load_account(user_id: uuid.UUID, manager: Any = None) -> AccountState | None:
    """Read the account from the database (None when there is no such user).

    No tenant context: ``users`` has no row-level security, like the login.
    ``manager`` (tests) replaces ``src.db.engine.db_manager``.
    """
    from sqlalchemy import select

    from src.db.engine import db_manager
    from src.db.models import User

    async with (manager or db_manager).session() as session:
        result = await session.execute(
            select(
                User.org_id,
                User.role,
                User.is_active,
                User.is_staff,
                User.email,
                User.email_verified,
                User.sessions_revoked_at,
            ).where(User.id == user_id)
        )
        row = result.one_or_none()
    if row is None:
        return None
    org_id = row.org_id if isinstance(row.org_id, uuid.UUID) else uuid.UUID(str(row.org_id))
    return AccountState(
        user_id=user_id,
        org_id=org_id,
        role=str(row.role or "member"),
        is_active=bool(row.is_active),
        is_staff=bool(row.is_staff),
        email=row.email,
        email_verified=bool(row.email_verified),
        sessions_revoked_at=row.sessions_revoked_at,
    )


class AccountCache:
    """Per-process cache of ``load_account``: a few seconds, bounded in size."""

    MAX_ENTRIES = 10_000

    def __init__(self) -> None:
        self._entries: dict[uuid.UUID, tuple[float, AccountState | None]] = {}

    def get(self, user_id: uuid.UUID) -> tuple[bool, AccountState | None]:
        """(found, account): found is False when nothing fresh is cached."""
        entry = self._entries.get(user_id)
        if entry is None:
            return False, None
        expires, account = entry
        if expires <= time.monotonic():
            self._entries.pop(user_id, None)
            return False, None
        return True, account

    def put(self, user_id: uuid.UUID, account: AccountState | None, ttl: float) -> None:
        if ttl <= 0:
            return
        if len(self._entries) >= self.MAX_ENTRIES:
            now = time.monotonic()
            self._entries = {k: v for k, v in self._entries.items() if v[0] > now}
            if len(self._entries) >= self.MAX_ENTRIES:
                self._entries.clear()
        self._entries[user_id] = (time.monotonic() + ttl, account)

    def evict(self, user_id: uuid.UUID) -> None:
        self._entries.pop(user_id, None)

    def clear(self) -> None:
        self._entries.clear()


account_cache = AccountCache()


def invalidate_account(user_id: uuid.UUID) -> None:
    """Forget what this process read of an account (after changing it)."""
    account_cache.evict(user_id)


async def resolve_account(payload: TokenPayload) -> AccountState | None:
    """The account a token names, from the cache or the database."""
    user_id = uuid.UUID(payload.sub)
    found, account = account_cache.get(user_id)
    if found:
        return account
    account = await load_account(user_id)
    account_cache.put(user_id, account, get_settings().auth_account_cache_seconds)
    return account


def account_from_claims(payload: TokenPayload) -> AccountState:
    """An account built from the token alone: never staff, sessions never ended.

    What ``resolve_account`` would return if the database agreed with the
    token in everything. The test suite uses it for the tokens it mints for
    users that exist in no database (tests/conftest.py).
    """
    return AccountState(
        user_id=uuid.UUID(payload.sub),
        org_id=uuid.UUID(payload.org_id),
        role=payload.role,
        is_active=True,
        is_staff=False,
        email=payload.email,
        email_verified=payload.email_verified,
    )


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def is_staff(user: CurrentUser) -> bool:
    """NormaAI personnel: the users.is_staff flag, on a verified email address.

    The flag is set only by scripts/staff.py. Neither the email address nor
    any claim of the token counts; an unverified address is never staff, so an
    account registered with a staff address that nobody confirmed gets nothing.
    """
    return bool(user.is_staff) and user.email_verified is True


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> CurrentUser:
    """Extract and validate the current user from JWT bearer token.

    Validates:
    1. Token is present and properly formatted
    2. Token signature and expiration are valid
    3. Token type is "access"
    4. Neither the token nor its session has been revoked (Redis blacklist)
    5. The account still exists, is active, belongs to the token's organisation
       and has not ended its sessions after the token was issued (database)
    """
    if credentials is None:
        raise _unauthorized("Authentication required. Provide a Bearer token.")

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise _unauthorized("Invalid or expired token.")

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use an access token.",
        )
    try:
        token_org_id = uuid.UUID(payload.org_id)
        uuid.UUID(payload.sub)
    except ValueError:
        raise _unauthorized("Invalid or expired token.")

    # Check token blacklist (revocation): the token itself and its session.
    if await token_blacklist.is_blacklisted(payload.jti, family=payload.sid):
        raise _unauthorized("Token has been revoked.")

    try:
        account = await resolve_account(payload)
    except Exception as e:  # noqa: BLE001 - fail closed, without believing the token
        logger.warning("account_check_failed", error_type=type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ACCOUNT_CHECK_UNAVAILABLE_DETAIL,
        )

    if account is None or not account.is_active or account.org_id != token_org_id:
        raise _unauthorized("Account not found or deactivated.")
    if issued_before(payload.iat, account.sessions_revoked_at):
        raise _unauthorized("Session ended. Please sign in again.")

    return CurrentUser(
        user_id=account.user_id,
        org_id=account.org_id,
        role=account.role,
        email=account.email,
        email_verified=account.email_verified,
        is_staff=account.is_staff,
    )


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> CurrentUser | None:
    """Like get_current_user but returns None for unauthenticated requests."""
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials)
    except HTTPException as e:
        if e.status_code == status.HTTP_401_UNAUTHORIZED:
            return None
        raise


async def _email_verified_in_db(user: CurrentUser) -> bool:
    """Authoritative check for tokens minted before the user verified."""
    from sqlalchemy import select

    from src.db.engine import db_manager
    from src.db.models import User

    async with db_manager.session(org_id=str(user.org_id)) as session:
        result = await session.execute(select(User.email_verified).where(User.id == user.user_id))
        return bool(result.scalar_one_or_none())


async def require_verified_email(
    user: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """Dependency: like ``get_current_user`` but, when
    ``settings.require_email_verification`` is on, the user must have confirmed
    their email address (403 otherwise).

    Fast path: ``email_verified`` of the account (the database, read by
    ``get_current_user``). When that says False, the database is asked once
    more, so that a link clicked a moment ago counts before the account cache
    expires. Fail closed on any error (treat as unverified).
    """
    if not get_settings().require_email_verification or user.email_verified is True:
        return user
    try:
        verified = await _email_verified_in_db(user)
    except Exception as e:  # noqa: BLE001 - fail closed
        logger.warning("email_verification_check_failed", error=str(e))
        verified = False
    if not verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conferma l'indirizzo email per usare NormaAI.",
        )
    user.email_verified = True
    return user


async def require_editor(user: CurrentUser = Depends(require_verified_email)) -> CurrentUser:
    """Who may change the organisation's data: everyone but the read-only ``viewer``.

    Also needs a verified email address when the deployment asks for one.
    """
    if user.is_viewer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=READ_ONLY_DETAIL)
    return user


async def require_admin(user: CurrentUser = Depends(require_verified_email)) -> CurrentUser:
    """Who may delete what others rely on and manage the members: the ``admin`` role.

    Also needs a verified email address when the deployment asks for one.
    """
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ADMIN_ONLY_DETAIL)
    return user


async def require_staff(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: the caller must be NormaAI staff (``is_staff``).

    Guards operations that touch the SHARED regulatory corpus (crawl /
    re-index) or create new tenants, which no customer admin should run.
    """
    if not is_staff(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=STAFF_ONLY_DETAIL)
    return user


def require_role(*allowed_roles: str) -> Callable[..., Awaitable[CurrentUser]]:
    """Dependency factory: require the user to have one of the specified roles."""

    async def _check_role(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(allowed_roles)}",
            )
        return user

    return _check_role
