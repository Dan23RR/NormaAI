"""FastAPI dependencies for authentication and authorization."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.security import decode_token, token_blacklist
from src.config import get_settings

logger = structlog.get_logger(__name__)

security_scheme = HTTPBearer(auto_error=False)

STAFF_ONLY_DETAIL = "Operazione riservata al personale NormaAI."


class CurrentUser:
    """Authenticated user context extracted from JWT."""

    def __init__(
        self,
        user_id: uuid.UUID,
        org_id: uuid.UUID,
        role: str,
        email: str | None = None,
        email_verified: bool | None = None,
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        # From the access token's claims; None on legacy tokens.
        self.email = email
        self.email_verified = email_verified

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_viewer(self) -> bool:
        return self.role == "viewer"


def is_staff(user: CurrentUser) -> bool:
    """NormaAI personnel = the token's email claim is in settings.staff_emails.

    Fail-closed: a token without an email claim (minted before the claim
    existed) is never staff - a fresh login fixes that.
    """
    return get_settings().is_staff_email(user.email)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> CurrentUser:
    """Extract and validate the current user from JWT bearer token.

    Validates:
    1. Token is present and properly formatted
    2. Token signature and expiration are valid
    3. Token type is "access"
    4. Token has not been revoked (blacklist check via Redis)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Use an access token.",
        )

    # Check token blacklist (revocation)
    if await token_blacklist.is_blacklisted(payload.jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        user_id=uuid.UUID(payload.sub),
        org_id=uuid.UUID(payload.org_id),
        role=payload.role,
        email=payload.email,
        email_verified=payload.email_verified,
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

    Fast path: the ``email_verified`` claim of the access token. A token minted
    BEFORE the user verified says False, so fall back to the database rather
    than forcing a re-login right after clicking the link. Fail closed on any
    error (treat as unverified).
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


async def require_staff(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Dependency: the caller must be NormaAI staff (settings.staff_emails).

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
