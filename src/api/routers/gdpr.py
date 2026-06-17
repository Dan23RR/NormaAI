"""GDPR data-subject rights for a tenant organization.

- Export (Art. 15 access / Art. 20 portability): a full JSON dump of the org's
  data, admin-only.
- Erasure (Art. 17 right to be forgotten): deletes the org's tenant content
  (clients, conversations, assessments, alerts) from the database AND the org's
  uploaded chunks from the vector store. Confirmation-gated and audit-logged.
  The shared regulatory corpus is never touched. Users and the Organization
  record are kept (account closure is a separate flow) so the admin can still
  operate / re-onboard.

Ironic-but-true: a GDPR product MUST be able to do this. It previously could not.
"""

import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, inspect, select

from src.api.rate_limit import limiter
from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, require_role
from src.db.engine import db_manager
from src.db.models import Alert, Assessment, Client, Conversation, User

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/gdpr", tags=["GDPR"])


def _row_to_dict(obj) -> dict:
    """Serialize an ORM row to a JSON-able dict (FastAPI encodes datetime/UUID)."""
    out: dict = {}
    for col in inspect(obj).mapper.column_attrs:
        value = getattr(obj, col.key)
        out[col.key] = str(value) if isinstance(value, uuid.UUID) else value
    return out


class ErasureRequest(BaseModel):
    confirm_org_id: str = Field(
        ..., description="Must equal your organization id - confirms the destructive action."
    )


@router.get("/export")
@limiter.limit("3/hour")
async def export_org_data(
    request: Request,
    user: CurrentUser = Depends(require_role("admin")),
) -> dict:
    """Export all of the authenticated organization's data (admin only)."""
    org_id = str(user.org_id)
    async with db_manager.session(org_id=org_id) as session:
        users = (
            (await session.execute(select(User).where(User.org_id == user.org_id))).scalars().all()
        )
        clients = (
            (await session.execute(select(Client).where(Client.org_id == user.org_id)))
            .scalars()
            .all()
        )
        client_ids = [c.id for c in clients]
        user_ids = [u.id for u in users]

        conversations = (
            (await session.execute(select(Conversation).where(Conversation.user_id.in_(user_ids))))
            .scalars()
            .all()
            if user_ids
            else []
        )
        assessments = (
            (await session.execute(select(Assessment).where(Assessment.client_id.in_(client_ids))))
            .scalars()
            .all()
            if client_ids
            else []
        )
        alerts = (
            (await session.execute(select(Alert).where(Alert.client_id.in_(client_ids))))
            .scalars()
            .all()
            if client_ids
            else []
        )

    audit_log(
        AuditAction.DATA_EXPORT,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/gdpr/export",
        detail=f"GDPR export: {len(users)} users, {len(clients)} clients",
    )

    return {
        "org_id": org_id,
        "exported_at": datetime.now(UTC).isoformat(),
        "users": [_row_to_dict(u) for u in users],
        "clients": [_row_to_dict(c) for c in clients],
        "conversations": [_row_to_dict(c) for c in conversations],
        "assessments": [_row_to_dict(a) for a in assessments],
        "alerts": [_row_to_dict(a) for a in alerts],
    }


@router.post("/erase")
@limiter.limit("2/hour")
async def erase_org_data(
    request: Request,
    payload: ErasureRequest,
    user: CurrentUser = Depends(require_role("admin")),
) -> dict:
    """Erase the org's tenant content (DB + vector store). Confirmation-gated."""
    org_id = str(user.org_id)
    if payload.confirm_org_id != org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="confirm_org_id does not match your organization.",
        )

    deleted = {"clients": 0, "conversations": 0, "assessments": 0, "alerts": 0}
    async with db_manager.session(org_id=org_id) as session:
        client_ids = (
            (await session.execute(select(Client.id).where(Client.org_id == user.org_id)))
            .scalars()
            .all()
        )
        user_ids = (
            (await session.execute(select(User.id).where(User.org_id == user.org_id)))
            .scalars()
            .all()
        )
        if client_ids:
            r = await session.execute(
                delete(Assessment).where(Assessment.client_id.in_(client_ids))
            )
            deleted["assessments"] = r.rowcount or 0
            r = await session.execute(delete(Alert).where(Alert.client_id.in_(client_ids)))
            deleted["alerts"] = r.rowcount or 0
        if user_ids:
            r = await session.execute(
                delete(Conversation).where(Conversation.user_id.in_(user_ids))
            )
            deleted["conversations"] = r.rowcount or 0
        r = await session.execute(delete(Client).where(Client.org_id == user.org_id))
        deleted["clients"] = r.rowcount or 0
        await session.commit()

    # Erase the org's uploaded chunks from the vector store (best-effort).
    try:
        from src.api.app_state import app_state

        if app_state.indexer is not None:
            app_state.indexer.delete_org_chunks(org_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("gdpr_qdrant_erase_failed", org_id=org_id, error=str(e))

    audit_log(
        AuditAction.DATA_ERASURE,
        user_id=str(user.user_id),
        org_id=org_id,
        ip_address=get_client_ip(request),
        resource="/api/v1/gdpr/erase",
        detail=f"GDPR erasure: {deleted}",
    )

    return {"status": "erased", "org_id": org_id, "deleted": deleted}
