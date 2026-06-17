"""Alert endpoints: CRUD for compliance alerts with org-scoped access."""

import uuid
from datetime import date, datetime
from enum import Enum

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user
from src.db.engine import db_manager
from src.db.models import Alert, Client

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Alerts"])

from src.api.rate_limit import limiter

# --- Enums ----------------------------------------------------------------


class SeverityEnum(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


# Shared across routers - single source of truth (includes CRA).
from src.api.schemas import FrameworkEnum  # noqa: E402

# --- Pydantic Models -----------------------------------------------------


class AlertCreate(BaseModel):
    """Create a new compliance alert."""

    client_id: uuid.UUID = Field(..., description="Client this alert belongs to")
    severity: SeverityEnum = Field(..., description="Alert severity level")
    framework: FrameworkEnum = Field(..., description="Regulatory framework")
    title: str = Field(..., min_length=1, max_length=500, description="Alert title")
    description: str = Field(default="", max_length=5000, description="Detailed description")
    actions_required: list[str] = Field(
        default_factory=list, description="List of required actions"
    )
    regulation_id: uuid.UUID | None = Field(default=None, description="Related regulation ID")
    deadline: date | None = Field(default=None, description="Compliance deadline")


class AlertResponse(BaseModel):
    """Full alert representation."""

    id: uuid.UUID
    client_id: uuid.UUID | None
    regulation_id: uuid.UUID | None
    severity: str
    framework: str
    title: str
    description: str
    actions_required: list[str] | None
    deadline: date | None
    is_read: bool
    is_dismissed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""

    alerts: list[AlertResponse]
    total: int
    limit: int
    offset: int


class SeverityCount(BaseModel):
    """Count per severity level."""

    severity: str
    count: int


class FrameworkCount(BaseModel):
    """Count per framework."""

    framework: str
    count: int


class AlertSummary(BaseModel):
    """Dashboard summary of alerts."""

    total: int
    total_unread: int
    by_severity: list[SeverityCount]
    by_framework: list[FrameworkCount]


# --- Helpers --------------------------------------------------------------


async def _verify_client_org(session, client_id: uuid.UUID, org_id: uuid.UUID) -> Client:
    """Verify that a client belongs to the user's organization.

    Returns the Client row if valid, raises 404 otherwise.
    """
    stmt = select(Client).where(and_(Client.id == client_id, Client.org_id == org_id))
    result = await session.execute(stmt)
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found in your organization.")
    return client


async def _get_alert_for_org(session, alert_id: uuid.UUID, org_id: uuid.UUID) -> Alert:
    """Fetch an alert and verify org ownership via the client join.

    Returns the Alert row if valid, raises 404 otherwise.
    """
    stmt = (
        select(Alert)
        .join(Client, Alert.client_id == Client.id)
        .where(and_(Alert.id == alert_id, Client.org_id == org_id))
    )
    result = await session.execute(stmt)
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert


# --- Endpoints ------------------------------------------------------------


@router.get("/alerts/summary")
@limiter.limit("30/minute")
async def get_alerts_summary(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
) -> AlertSummary:
    """
    **Get alert summary counts for the dashboard.**

    Returns total alerts, unread count, and breakdowns by severity and framework.
    Scoped to the authenticated user's organization.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        base = (
            select(Alert)
            .join(Client, Alert.client_id == Client.id)
            .where(and_(Client.org_id == user.org_id, Alert.is_dismissed is False))
        )

        # Total count
        total_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(total_stmt)).scalar() or 0

        # Unread count
        unread_stmt = select(func.count()).select_from(
            base.where(Alert.is_read is False).subquery()
        )
        total_unread = (await session.execute(unread_stmt)).scalar() or 0

        # By severity
        sev_stmt = (
            select(Alert.severity, func.count().label("count"))
            .join(Client, Alert.client_id == Client.id)
            .where(and_(Client.org_id == user.org_id, Alert.is_dismissed is False))
            .group_by(Alert.severity)
            .order_by(func.count().desc())
        )
        sev_rows = (await session.execute(sev_stmt)).all()
        by_severity = [SeverityCount(severity=row.severity, count=row.count) for row in sev_rows]

        # By framework
        fw_stmt = (
            select(Alert.framework, func.count().label("count"))
            .join(Client, Alert.client_id == Client.id)
            .where(and_(Client.org_id == user.org_id, Alert.is_dismissed is False))
            .group_by(Alert.framework)
            .order_by(func.count().desc())
        )
        fw_rows = (await session.execute(fw_stmt)).all()
        by_framework = [FrameworkCount(framework=row.framework, count=row.count) for row in fw_rows]

    return AlertSummary(
        total=total,
        total_unread=total_unread,
        by_severity=by_severity,
        by_framework=by_framework,
    )


@router.get("/alerts")
@limiter.limit("30/minute")
async def list_alerts(
    request: Request,
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    severity: SeverityEnum | None = None,
    framework: FrameworkEnum | None = None,
    is_read: bool | None = None,
    client_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AlertListResponse:
    """
    **List compliance alerts for your organization.**

    Supports filtering by severity, framework, read status, and client.
    Results are sorted by creation date (newest first).
    Returns the unread count in the `X-Unread-Count` response header.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        # Base query: alerts for the user's org
        base = (
            select(Alert)
            .join(Client, Alert.client_id == Client.id)
            .where(Client.org_id == user.org_id)
        )

        # Apply filters
        if severity is not None:
            base = base.where(Alert.severity == severity.value)
        if framework is not None:
            base = base.where(Alert.framework == framework.value)
        if is_read is not None:
            base = base.where(Alert.is_read == is_read)
        if client_id is not None:
            base = base.where(Alert.client_id == client_id)

        # Total count for pagination
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await session.execute(count_stmt)).scalar() or 0

        # Fetch page, newest first
        data_stmt = base.order_by(Alert.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(data_stmt)).scalars().all()

        # Unread count across the org (not filtered)
        unread_stmt = (
            select(func.count())
            .select_from(Alert)
            .join(Client, Alert.client_id == Client.id)
            .where(and_(Client.org_id == user.org_id, Alert.is_read is False))
        )
        unread_count = (await session.execute(unread_stmt)).scalar() or 0

    response.headers["X-Unread-Count"] = str(unread_count)

    return AlertListResponse(
        alerts=[AlertResponse.model_validate(a) for a in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/alerts/{alert_id}")
@limiter.limit("30/minute")
async def get_alert(
    request: Request,
    alert_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> AlertResponse:
    """
    **Get a single alert by ID.**

    Verifies that the alert belongs to a client in the user's organization.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        alert = await _get_alert_for_org(session, alert_id, user.org_id)

    return AlertResponse.model_validate(alert)


@router.post("/alerts", status_code=201)
@limiter.limit("10/minute")
async def create_alert(
    request: Request,
    payload: AlertCreate,
    user: CurrentUser = Depends(get_current_user),
) -> AlertResponse:
    """
    **Create a new compliance alert.**

    The target client must belong to the user's organization.
    Intended for internal use and monitor agent integration.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        # Verify client belongs to user's org
        await _verify_client_org(session, payload.client_id, user.org_id)

        alert = Alert(
            id=uuid.uuid4(),
            client_id=payload.client_id,
            regulation_id=payload.regulation_id,
            severity=payload.severity.value,
            framework=payload.framework.value,
            title=payload.title,
            description=payload.description,
            actions_required=payload.actions_required if payload.actions_required else None,
            deadline=payload.deadline,
            is_read=False,
            is_dismissed=False,
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)

    audit_log(
        AuditAction.ALERT_CREATED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/alerts/{alert.id}",
        detail=f"{payload.severity.value} alert: {payload.title[:80]}",
        extra={"framework": payload.framework.value, "client_id": str(payload.client_id)},
    )

    return AlertResponse.model_validate(alert)


@router.patch("/alerts/{alert_id}/read")
@limiter.limit("10/minute")
async def mark_alert_read(
    request: Request,
    alert_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> AlertResponse:
    """
    **Mark an alert as read.**

    Requires authentication. The alert must belong to a client in the user's organization.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        alert = await _get_alert_for_org(session, alert_id, user.org_id)
        alert.is_read = True
        await session.commit()
        await session.refresh(alert)

    return AlertResponse.model_validate(alert)


@router.patch("/alerts/{alert_id}/dismiss")
@limiter.limit("10/minute")
async def dismiss_alert(
    request: Request,
    alert_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
) -> AlertResponse:
    """
    **Dismiss an alert.**

    Dismissed alerts are excluded from summary counts and default views.
    Requires authentication. The alert must belong to a client in the user's organization.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        alert = await _get_alert_for_org(session, alert_id, user.org_id)
        alert.is_dismissed = True
        alert.is_read = True
        await session.commit()
        await session.refresh(alert)

    audit_log(
        AuditAction.ALERT_DISMISSED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/alerts/{alert_id}",
        detail=f"Dismissed alert: {alert.title[:80]}",
    )

    return AlertResponse.model_validate(alert)
