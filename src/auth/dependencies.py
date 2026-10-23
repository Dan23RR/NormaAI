"""FastAPI dependencies for authentication and authorization."""

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.security import decode_token, token_blacklist
from src.config import get_settings

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
    ):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        # From the access token's ``email`` claim; None on legacy tokens.
        self.email = email

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
