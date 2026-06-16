"""Client management endpoints: CRUD for multi-tenant client entities."""

import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user
from src.db.engine import db_manager
from src.db.models import Client

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Clients"])

from src.api.rate_limit import limiter

# --- Pydantic Models ---------------------------------------------------------


class ClientCreate(BaseModel):
    """Payload for creating a new client."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Client company name",
        json_schema_extra={"examples": ["Acme Srl"]},
    )
    sector: str | None = Field(
        default=None,
        max_length=100,
        description="Industry sector",
        json_schema_extra={"examples": ["Manufacturing"]},
    )
    employee_count: int | None = Field(
        default=None,
        ge=0,
        description="Number of employees",
        json_schema_extra={"examples": [2500]},
    )
    revenue_eur: int | None = Field(
        default=None,
        ge=0,
        description="Annual revenue in EUR",
        json_schema_extra={"examples": [200000000]},
    )
    jurisdictions: list[str] = Field(
        default_factory=list,
        description="EU country codes",
        json_schema_extra={"examples": [["IT", "DE"]]},
    )
    applicable_frameworks: list[str] = Field(
        default_factory=list,
        description="Tracked regulatory frameworks",
        json_schema_extra={"examples": [["CSRD", "CSDDD"]]},
    )


class ClientUpdate(BaseModel):
    """Payload for updating an existing client. All fields optional."""

    name: str | None = Field(
        default=None, min_length=1, max_length=255, description="Client company name"
    )
    sector: str | None = Field(default=None, max_length=100, description="Industry sector")
    employee_count: int | None = Field(default=None, ge=0, description="Number of employees")
    revenue_eur: int | None = Field(default=None, ge=0, description="Annual revenue in EUR")
    jurisdictions: list[str] | None = Field(default=None, description="EU country codes")
    applicable_frameworks: list[str] | None = Field(
        default=None, description="Tracked regulatory frameworks"
    )


class ClientResponse(BaseModel):
    """Full client representation returned by the API."""

    id: str
    org_id: str
    name: str
    sector: str | None = None
    employee_count: int | None = None
    revenue_eur: int | None = None
    jurisdictions: list[str] = []
    applicable_frameworks: list[str] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# --- Helpers -----------------------------------------------------------------


def _client_to_response(client: Client) -> ClientResponse:
    """Convert an ORM Client instance to a ClientResponse."""
    return ClientResponse(
        id=str(client.id),
        org_id=str(client.org_id),
        name=client.name,
        sector=client.sector,
        employee_count=client.employee_count,
        revenue_eur=client.revenue_eur,
        jurisdictions=client.jurisdictions or [],
        applicable_frameworks=client.applicable_frameworks or [],
        created_at=client.created_at,
        updated_at=client.updated_at,
    )


async def _get_client_or_404(
    session: AsyncSession,
    client_id: uuid.UUID,
    org_id: uuid.UUID,
) -> Client:
    """Fetch a client by ID, enforcing tenant isolation.

    Raises 404 if not found or does not belong to the user's organization.
    This prevents information leakage about clients in other organizations.
    """
    result = await session.execute(
        select(Client).where(Client.id == client_id, Client.org_id == org_id)
    )
    client = result.scalar_one_or_none()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Client not found.",
        )
    return client


# --- Endpoints ---------------------------------------------------------------


@router.get("/clients", response_model=list[ClientResponse])
@limiter.limit("30/minute")
async def list_clients(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **List all clients for the authenticated user's organization.**

    Returns clients filtered by the org_id from the JWT token,
    ordered by creation date (newest first).

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        result = await session.execute(
            select(Client).where(Client.org_id == user.org_id).order_by(Client.created_at.desc())
        )
        clients = result.scalars().all()

    return [_client_to_response(c) for c in clients]


@router.post("/clients", response_model=ClientResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_client(
    request: Request,
    payload: ClientCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Create a new client for the authenticated user's organization.**

    The client is automatically assigned to the user's org_id from the JWT.

    Requires authentication.
    """
    client = Client(
        org_id=user.org_id,
        name=payload.name,
        sector=payload.sector,
        employee_count=payload.employee_count,
        revenue_eur=payload.revenue_eur,
        jurisdictions=payload.jurisdictions,
        applicable_frameworks=payload.applicable_frameworks,
    )

    async with db_manager.session(org_id=str(user.org_id)) as session:
        session.add(client)
        await session.commit()
        await session.refresh(client)

    audit_log(
        AuditAction.CLIENT_CREATED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/clients",
        detail=f"Created client: {client.name}",
        extra={"client_id": str(client.id)},
    )

    logger.info(
        "client_created", client_id=str(client.id), org_id=str(user.org_id), name=client.name
    )
    return _client_to_response(client)


@router.get("/clients/{client_id}", response_model=ClientResponse)
@limiter.limit("30/minute")
async def get_client(
    request: Request,
    client_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Get a single client by ID.**

    The client must belong to the authenticated user's organization.
    Returns 404 if the client is not found or belongs to another org.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        client = await _get_client_or_404(session, client_id, user.org_id)

    return _client_to_response(client)


@router.put("/clients/{client_id}", response_model=ClientResponse)
@limiter.limit("10/minute")
async def update_client(
    request: Request,
    client_id: uuid.UUID,
    payload: ClientUpdate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Update an existing client.**

    Only fields included in the request body are updated.
    The client must belong to the authenticated user's organization.

    Requires authentication.
    """
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided to update.",
        )

    async with db_manager.session(org_id=str(user.org_id)) as session:
        client = await _get_client_or_404(session, client_id, user.org_id)

        for field, value in update_data.items():
            setattr(client, field, value)

        await session.commit()
        await session.refresh(client)

    audit_log(
        AuditAction.CLIENT_UPDATED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/clients/{client_id}",
        detail=f"Updated client: {client.name}",
        extra={"client_id": str(client_id), "updated_fields": list(update_data.keys())},
    )

    logger.info(
        "client_updated",
        client_id=str(client_id),
        org_id=str(user.org_id),
        updated_fields=list(update_data.keys()),
    )
    return _client_to_response(client)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_client(
    request: Request,
    client_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Delete a client.**

    Permanently removes the client and all associated data (assessments, alerts,
    conversations) via the database CASCADE rules.
    The client must belong to the authenticated user's organization.

    Requires authentication.
    """
    async with db_manager.session(org_id=str(user.org_id)) as session:
        client = await _get_client_or_404(session, client_id, user.org_id)
        client_name = client.name

        await session.delete(client)
        await session.commit()

    audit_log(
        AuditAction.CLIENT_DELETED,
        user_id=str(user.user_id),
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/clients/{client_id}",
        detail=f"Deleted client: {client_name}",
        extra={"client_id": str(client_id)},
    )

    logger.info(
        "client_deleted", client_id=str(client_id), org_id=str(user.org_id), name=client_name
    )
