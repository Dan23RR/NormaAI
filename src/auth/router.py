"""Authentication endpoints: login, register, refresh, logout, me."""

import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import AuditAction, AuditOutcome, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user
from src.auth.security import (
    TokenPair,
    create_token_pair,
    decode_token,
    hash_password,
    token_blacklist,
    verify_password,
)
from src.db.engine import get_db_session
from src.db.models import Organization, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security_scheme = HTTPBearer(auto_error=False)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    organization_name: str = Field(..., min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    organization_name: str


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new user and organization."""
    client_ip = get_client_ip(request)

    # Create organization with unique slug
    base_slug = re.sub(r"[^a-z0-9]+", "-", payload.organization_name.lower()).strip("-") or "org"
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
    org = Organization(name=payload.organization_name, slug=slug)
    db.add(org)
    await db.flush()

    # Create user - rely on DB UNIQUE constraint to prevent race conditions
    user = User(
        org_id=org.id,
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
        role="admin",
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        audit_log(
            AuditAction.REGISTER,
            AuditOutcome.FAILURE,
            ip_address=client_ip,
            detail=f"Duplicate email: {payload.email}",
        )
        raise HTTPException(status_code=409, detail="Email already registered.")
    await db.refresh(user)

    audit_log(
        AuditAction.REGISTER,
        AuditOutcome.SUCCESS,
        user_id=str(user.id),
        org_id=str(org.id),
        ip_address=client_ip,
        detail=f"New org: {payload.organization_name}",
    )
    return create_token_pair(user.id, org.id, user.role)


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Authenticate and receive a token pair."""
    client_ip = get_client_ip(request)

    # Brute-force protection: check lockout before attempting authentication
    from src.auth.brute_force import brute_force

    lockout_msg = await brute_force.check_and_increment(payload.email, client_ip)
    if lockout_msg:
        audit_log(
            AuditAction.LOGIN_FAILURE,
            AuditOutcome.DENIED,
            ip_address=client_ip,
            detail=f"Brute-force lockout for: {payload.email}",
        )
        raise HTTPException(status_code=429, detail=lockout_msg)

    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    # Constant-time comparison: always compute bcrypt to prevent user enumeration timing attacks
    _dummy_hash = "$2b$12$LJ3m4ks5K5k7k8k9k0k1k2k3k4k5k6k7k8k9k0k1k2k3k4k5k6k7"
    password_valid = verify_password(
        payload.password, user.hashed_password if user else _dummy_hash
    )

    if not user or not password_valid:
        audit_log(
            AuditAction.LOGIN_FAILURE,
            AuditOutcome.FAILURE,
            ip_address=client_ip,
            detail=f"Failed login attempt for: {payload.email}",
        )
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not user.is_active:
        audit_log(
            AuditAction.LOGIN_FAILURE,
            AuditOutcome.DENIED,
            user_id=str(user.id),
            ip_address=client_ip,
            detail="Account deactivated",
        )
        raise HTTPException(status_code=403, detail="Account is deactivated.")

    # Reset brute-force counter on successful login
    await brute_force.reset(payload.email)

    audit_log(
        AuditAction.LOGIN_SUCCESS,
        AuditOutcome.SUCCESS,
        user_id=str(user.id),
        org_id=str(user.org_id),
        ip_address=client_ip,
    )
    return create_token_pair(user.id, user.org_id, user.role)


@router.post("/refresh", response_model=TokenPair)
async def refresh_token(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Refresh an access token using a refresh token.

    Implements refresh token rotation:
    - The old refresh token is blacklisted
    - A new token pair is issued with the same family
    - If a blacklisted refresh token is reused, the entire family is revoked
    """
    client_ip = get_client_ip(request)

    try:
        token_data = decode_token(payload.refresh_token)
    except ValueError:
        audit_log(
            AuditAction.TOKEN_REFRESH,
            AuditOutcome.FAILURE,
            ip_address=client_ip,
            detail="Invalid or expired refresh token",
        )
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    if token_data.type != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type. Provide a refresh token.")

    # Check if this specific token was already used (replay attack detection)
    if await token_blacklist.is_blacklisted(token_data.jti, family=token_data.family):
        # Token reuse detected - compromise! Blacklist the entire family
        if token_data.family:
            await token_blacklist.blacklist_token_family(token_data.family)
        audit_log(
            AuditAction.TOKEN_REUSE_DETECTED,
            AuditOutcome.DENIED,
            user_id=token_data.sub,
            ip_address=client_ip,
            detail="Refresh token reuse - family revoked",
        )
        raise HTTPException(
            status_code=401,
            detail="Token has been revoked. Please log in again.",
        )

    # Verify user still exists and is active
    result = await db.execute(select(User).where(User.id == uuid.UUID(token_data.sub)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or deactivated.")

    # Blacklist the old refresh token (rotation)
    await token_blacklist.blacklist_token(token_data.jti, token_data.exp)

    audit_log(
        AuditAction.TOKEN_REFRESH,
        AuditOutcome.SUCCESS,
        user_id=str(user.id),
        org_id=str(user.org_id),
        ip_address=client_ip,
    )

    # Issue new pair with same family
    return create_token_pair(user.id, user.org_id, user.role, family=token_data.family)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
):
    """Logout by blacklisting the current access token.

    The client should also discard the refresh token.
    For full session termination, call with the access token.
    """
    client_ip = get_client_ip(request)

    if credentials is None:
        raise HTTPException(status_code=401, detail="No token provided.")

    try:
        token_data = decode_token(credentials.credentials)
    except ValueError:
        # Token is already invalid, nothing to revoke
        return

    # Blacklist the token
    await token_blacklist.blacklist_token(token_data.jti, token_data.exp)

    # If it's an access token and we know the family, blacklist the family too
    if token_data.family:
        await token_blacklist.blacklist_token_family(token_data.family)

    audit_log(
        AuditAction.LOGOUT, AuditOutcome.SUCCESS, user_id=token_data.sub, ip_address=client_ip
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Get the current authenticated user's profile."""
    result = await db.execute(
        select(User, Organization)
        .join(Organization, User.org_id == Organization.id)
        .where(User.id == user.user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    u, org = row
    return UserResponse(
        id=str(u.id), email=u.email, name=u.name, role=u.role, organization_name=org.name
    )
