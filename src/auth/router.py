"""Authentication endpoints: login, register, refresh, logout, me, invites."""

import logging
import re
import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.rate_limit import client_ip_key, limiter, settings_limit
from src.audit import AuditAction, AuditOutcome, audit_log, get_client_ip
from src.auth.dependencies import (
    STAFF_ONLY_DETAIL,
    CurrentUser,
    get_current_user,
    is_staff,
    require_role,
)
from src.auth.invites import (
    INVALID_INVITE_DETAIL,
    INVITE_DEFAULT_EXPIRY_DAYS,
    INVITE_MAX_EXPIRY_DAYS,
    REGISTRATIONS_CLOSED_DETAIL,
    find_redeemable_invite,
    invite_status,
    new_invite,
    redeem_invite,
)
from src.auth.security import (
    TokenPair,
    create_token_pair,
    decode_token,
    hash_password,
    hash_password_async,
    token_blacklist,
    verify_password_async,
)
from src.auth.verification import (
    INVALID_VERIFICATION_TOKEN_DETAIL,
    parse_email_verification_token,
    send_verification_email,
    verify_email_verification_token,
)
from src.config import get_settings
from src.db.engine import RLS_GUC, get_db_session
from src.db.models import Invite, Organization, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])
security_scheme = HTTPBearer(auto_error=False)

# A VALID bcrypt hash, computed once at import, used only on the unknown-email
# login path so verify_password runs in constant time. The previous inline
# literal was an invalid 59-char salt, so bcrypt.checkpw raised ValueError: an
# unknown email returned HTTP 500 while a wrong password returned 401, which
# leaks which emails exist (the user-enumeration attack this guard prevents).
_DUMMY_PASSWORD_HASH = hash_password("normaai-constant-time-dummy")


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=255)
    # Required when a NEW organization is created (open mode, or an org-less
    # invite); ignored when the invite joins an existing organization.
    organization_name: str | None = Field(default=None, min_length=1, max_length=255)
    # Required in invite mode; honoured (and validated) in open mode too.
    invite_code: str | None = Field(default=None, max_length=128)


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
    email_verified: bool


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=512)


class VerifyEmailResponse(BaseModel):
    status: Literal["verified", "already_verified"]
    email: str


class ResendVerificationResponse(BaseModel):
    status: Literal["sent", "already_verified"]
    email: str


class InviteCreateRequest(BaseModel):
    email: EmailStr
    organization_id: uuid.UUID | None = Field(
        default=None,
        description="Organization the invitee joins. Defaults to the caller's; "
        "another organization is staff-only.",
    )
    new_organization: bool = Field(
        default=False,
        description="Staff only: the invitee creates a NEW organization and becomes its admin.",
    )
    role: Literal["member", "viewer", "admin"] = Field(
        default="member", description="Role inside the joined organization."
    )
    expires_in_days: int = Field(
        default=INVITE_DEFAULT_EXPIRY_DAYS, ge=1, le=INVITE_MAX_EXPIRY_DAYS
    )


class InviteResponse(BaseModel):
    id: str
    email: str
    organization_id: str | None
    role: str
    status: Literal["pending", "used", "expired"]
    created_at: datetime | None
    expires_at: datetime
    used_at: datetime | None


class InviteCreatedResponse(InviteResponse):
    code: str = Field(description="Plaintext invite code - shown only in this response.")


def _invite_to_response(invite: Invite) -> dict:
    return {
        "id": str(invite.id),
        "email": invite.email,
        "organization_id": str(invite.org_id) if invite.org_id else None,
        "role": invite.role,
        "status": invite_status(invite),
        "created_at": invite.created_at,
        "expires_at": invite.expires_at,
        "used_at": invite.used_at,
    }


async def _set_rls_org_context(db: AsyncSession, org_id: uuid.UUID) -> None:
    """Set the RLS org context so the subsequent user INSERT passes the
    users_org_insert WITH CHECK under a NON-superuser role + FORCE ROW LEVEL
    SECURITY. No-op under the current superuser app role and skipped on sqlite
    (tests); REQUIRED once DATABASE_URL points at the normaai_app role (see
    scripts/setup_app_role.sql / docs/DEPLOY_READINESS.md)."""
    try:
        is_postgres = db.get_bind().dialect.name == "postgresql"
    except Exception:
        is_postgres = False
    if is_postgres:
        await db.execute(
            text(f"SELECT set_config('{RLS_GUC}', :oid, true)"),
            {"oid": str(org_id)},
        )


@router.post("/register", response_model=TokenPair, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings_limit("auth_rate_limit_register"), key_func=client_ip_key)
async def register(
    payload: RegisterRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new user.

    Behaviour follows ``settings.registration_mode``:

    - ``open``: anyone may register and becomes admin of a NEW organization.
    - ``invite`` (default): a valid invite code is required. An invite tied to
      an organization joins it with the invite's role; an org-less invite
      (staff API / ``scripts/create_invite.py``) creates a new organization
      with role ``admin``.
    - ``closed``: 403.

    In open mode a supplied invite code is still honoured (an org invite joins
    that organization) and an invalid one is rejected rather than ignored.

    The address is verified automatically when it matches the invite's email;
    otherwise a verification email is sent in the background.
    """
    client_ip = get_client_ip(request)

    mode = get_settings().registration_mode
    if mode == "closed":
        audit_log(
            AuditAction.REGISTER,
            AuditOutcome.DENIED,
            ip_address=client_ip,
            detail="Registration closed",
        )
        raise HTTPException(status_code=403, detail=REGISTRATIONS_CLOSED_DETAIL)

    invite: Invite | None = None
    if mode == "invite" or payload.invite_code:
        invite = await find_redeemable_invite(db, payload.invite_code)
        if invite is None:
            audit_log(
                AuditAction.REGISTER,
                AuditOutcome.DENIED,
                ip_address=client_ip,
                detail=f"Invalid or expired invite code for: {payload.email}",
            )
            raise HTTPException(status_code=403, detail=INVALID_INVITE_DETAIL)

    # The user id is generated here so the invite can record it BEFORE the
    # user row exists (see Invite.used_by).
    user_id = uuid.uuid4()

    if invite is not None and invite.org_id is not None:
        # Join the inviting organization with the invited role.
        org_id = invite.org_id
        role = invite.role or "member"
        audit_detail = f"Joined org {org_id} via invite"
    else:
        if not payload.organization_name:
            raise HTTPException(status_code=422, detail="Nome organizzazione obbligatorio.")
        # Create organization with unique slug
        base_slug = (
            re.sub(r"[^a-z0-9]+", "-", payload.organization_name.lower()).strip("-") or "org"
        )
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
        org = Organization(name=payload.organization_name, slug=slug)
        db.add(org)
        await db.flush()
        org_id = org.id
        role = "admin"
        audit_detail = f"New org: {payload.organization_name}"

    # Redeem BEFORE switching the RLS context: an org-less invite is not
    # visible to an org-scoped session. The conditional UPDATE also settles a
    # race between two registrations presenting the same code.
    if invite is not None and not await redeem_invite(db, invite, user_id):
        await db.rollback()
        audit_log(
            AuditAction.REGISTER,
            AuditOutcome.DENIED,
            ip_address=client_ip,
            detail=f"Invite code already used for: {payload.email}",
        )
        raise HTTPException(status_code=403, detail=INVALID_INVITE_DETAIL)

    await _set_rls_org_context(db, org_id)

    # An invite proves control of the invited address: skip verification when
    # the registered email is the one the invite was issued for.
    email_verified = invite is not None and invite.email == payload.email.strip().lower()

    # Create user - rely on DB UNIQUE constraint to prevent race conditions
    user = User(
        id=user_id,
        org_id=org_id,
        email=payload.email,
        name=payload.name,
        hashed_password=await hash_password_async(payload.password),
        role=role,
        email_verified=email_verified,
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
        org_id=str(org_id),
        ip_address=client_ip,
        detail=audit_detail,
    )
    if not user.email_verified:
        # Resend is a blocking HTTP call: run it after the response, off the loop.
        background_tasks.add_task(send_verification_email, user.id, user.email, user.name)
    return create_token_pair(
        user.id, org_id, user.role, email=user.email, email_verified=user.email_verified
    )


@router.post("/login", response_model=TokenPair)
@limiter.limit(settings_limit("auth_rate_limit_login"), key_func=client_ip_key)
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

    # Constant-time comparison: always run bcrypt (against a valid dummy hash on
    # the unknown-email path) so neither timing nor status code reveals whether
    # the email exists. Runs in a worker thread so the slow hash never blocks
    # the event loop.
    password_valid = await verify_password_async(
        payload.password, user.hashed_password if user else _DUMMY_PASSWORD_HASH
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
    return create_token_pair(
        user.id, user.org_id, user.role, email=user.email, email_verified=user.email_verified
    )


@router.post("/refresh", response_model=TokenPair)
@limiter.limit(settings_limit("auth_rate_limit_refresh"), key_func=client_ip_key)
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
    return create_token_pair(
        user.id,
        user.org_id,
        user.role,
        family=token_data.family,
        email=user.email,
        email_verified=user.email_verified,
    )


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
        id=str(u.id),
        email=u.email,
        name=u.name,
        role=u.role,
        organization_name=org.name,
        email_verified=bool(u.email_verified),
    )


# ─── Email verification ──────────────────────────────────────────


@router.post("/verify-email", response_model=VerifyEmailResponse)
@limiter.limit(settings_limit("auth_rate_limit_verification"), key_func=client_ip_key)
async def verify_email(
    request: Request,
    payload: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db_session),
):
    """Confirm an email address with the signed token from the verification link.

    Public: the token is the credential. It is bound to the address it was
    issued for, so changing the email invalidates earlier links; once verified,
    presenting the token again is a harmless ``already_verified``.
    """
    client_ip = get_client_ip(request)

    user: User | None = None
    user_id = parse_email_verification_token(payload.token)
    if user_id is not None:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
    if user is None or verify_email_verification_token(payload.token, user.email) != user.id:
        audit_log(
            AuditAction.EMAIL_VERIFICATION,
            AuditOutcome.FAILURE,
            ip_address=client_ip,
            detail="Invalid or expired verification token",
        )
        raise HTTPException(status_code=400, detail=INVALID_VERIFICATION_TOKEN_DETAIL)

    if user.email_verified:
        return VerifyEmailResponse(status="already_verified", email=user.email)

    user.email_verified = True
    await db.commit()
    audit_log(
        AuditAction.EMAIL_VERIFICATION,
        AuditOutcome.SUCCESS,
        user_id=str(user.id),
        org_id=str(user.org_id),
        ip_address=client_ip,
    )
    return VerifyEmailResponse(status="verified", email=user.email)


@router.post("/resend-verification", response_model=ResendVerificationResponse)
@limiter.limit(settings_limit("auth_rate_limit_verification"), key_func=client_ip_key)
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Send a fresh verification email to the authenticated user's address."""
    result = await db.execute(select(User).where(User.id == user.user_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if row.email_verified:
        return ResendVerificationResponse(status="already_verified", email=row.email)

    background_tasks.add_task(send_verification_email, row.id, row.email, row.name)
    audit_log(
        AuditAction.EMAIL_VERIFICATION_RESEND,
        AuditOutcome.SUCCESS,
        user_id=str(row.id),
        org_id=str(row.org_id),
        ip_address=get_client_ip(request),
    )
    return ResendVerificationResponse(status="sent", email=row.email)


# ─── Invites (admin) ─────────────────────────────────────────────


@router.post("/invites", response_model=InviteCreatedResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("20/hour")
async def create_invite(
    request: Request,
    payload: InviteCreateRequest,
    user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a registration invite (admin only).

    An organization admin invites people into their OWN organization. Only
    NormaAI staff (``settings.staff_emails``) may target another organization
    or mint an org-less invite (``new_organization``), which lets the invitee
    create a new organization as its admin. The plaintext code is returned
    once; only its hash is stored.
    """
    staff = is_staff(user)
    org_id: uuid.UUID | None
    role = payload.role
    if payload.new_organization:
        if not staff:
            raise HTTPException(status_code=403, detail=STAFF_ONLY_DETAIL)
        org_id = None
        role = "admin"  # the invitee founds the organization
    else:
        org_id = payload.organization_id or user.org_id
        if org_id != user.org_id:
            if not staff:
                raise HTTPException(status_code=403, detail=STAFF_ONLY_DETAIL)
            exists = await db.execute(select(Organization.id).where(Organization.id == org_id))
            if exists.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="Organizzazione non trovata.")

    invite, code = new_invite(
        email=payload.email,
        org_id=org_id,
        role=role,
        created_by=user.user_id,
        expires_in_days=payload.expires_in_days,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    audit_log(
        AuditAction.INVITE_CREATED,
        AuditOutcome.SUCCESS,
        user_id=str(user.user_id),
        org_id=str(org_id) if org_id else None,
        ip_address=get_client_ip(request),
        detail=f"Invite for {invite.email} (role={invite.role}, new_org={org_id is None})",
    )
    return {**_invite_to_response(invite), "code": code}


@router.get("/invites", response_model=list[InviteResponse])
@limiter.limit("60/minute")
async def list_invites(
    request: Request,
    user: CurrentUser = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db_session),
):
    """List invites (admin only): the caller's organization, or all for staff."""
    stmt = select(Invite).order_by(Invite.created_at.desc()).limit(200)
    if not is_staff(user):
        stmt = stmt.where(Invite.org_id == user.org_id)
    result = await db.execute(stmt)
    return [_invite_to_response(invite) for invite in result.scalars().all()]
