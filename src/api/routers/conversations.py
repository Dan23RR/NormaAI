"""Conversation endpoints: CRUD for multi-turn Q&A sessions."""

from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from src.audit import AuditAction, audit_log, get_client_ip
from src.auth.dependencies import CurrentUser, get_current_user
from src.conversations import conversation_manager
from src.db.engine import db_manager

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["Conversations"])

from src.api.rate_limit import limiter

# --- Request/Response Models ---------------------------------------------------


class ConversationCreate(BaseModel):
    """Create a new conversation, optionally linked to a client."""

    client_id: UUID | None = Field(
        default=None,
        description="Optional client UUID to associate the conversation with.",
        json_schema_extra={"examples": ["550e8400-e29b-41d4-a716-446655440000"]},
    )


class MessageCreate(BaseModel):
    """Add a message to an existing conversation."""

    role: str = Field(
        ...,
        description="Message role: 'user' or 'assistant'.",
        json_schema_extra={"examples": ["user"]},
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Message content (1-10 000 characters).",
        json_schema_extra={"examples": ["What are the CSRD reporting thresholds?"]},
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata attached to the message (e.g. model, sources).",
    )

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = {"user", "assistant"}
        if v not in allowed:
            raise ValueError(f"role must be one of {allowed}, got '{v}'")
        return v


class MessageResponse(BaseModel):
    """A single message inside a conversation."""

    role: str
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    """Full conversation object returned to the client."""

    id: str
    user_id: str
    client_id: str | None = None
    messages: list[MessageResponse] = Field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None


class ConversationSummary(BaseModel):
    """Lightweight representation used in list responses."""

    id: str
    user_id: str
    client_id: str | None = None
    message_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


# --- Endpoints -----------------------------------------------------------------


@router.get("/conversations")
@limiter.limit("30/minute")
async def list_conversations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Max conversations to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    user: CurrentUser = Depends(get_current_user),
):
    """
    **List the authenticated user's conversations (paginated).**

    Returns lightweight summaries without full message content.
    Requires authentication.
    """
    user_id = str(user.user_id)

    async with db_manager.session(org_id=str(user.org_id)) as session:
        from sqlalchemy import text

        result = await session.execute(
            text("""
                SELECT id, client_id, user_id, messages, created_at, updated_at
                FROM conversations
                WHERE CAST(user_id AS TEXT) = :user_id
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
            """),
            {"user_id": user_id, "limit": limit, "offset": offset},
        )
        rows = result.fetchall()

    summaries = []
    for row in rows:
        messages_data = row[3]
        if isinstance(messages_data, str):
            import json

            messages_data = json.loads(messages_data)
        msg_count = len(messages_data) if messages_data else 0

        summaries.append(
            ConversationSummary(
                id=str(row[0]),
                client_id=str(row[1]) if row[1] else None,
                user_id=str(row[2]),
                message_count=msg_count,
                created_at=row[4].isoformat() if row[4] else None,
                updated_at=row[5].isoformat() if row[5] else None,
            ).model_dump()
        )

    return {"status": "success", "data": summaries}


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
@limiter.limit("15/minute")
async def create_conversation(
    request: Request,
    payload: ConversationCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Create a new conversation.**

    Optionally link to a client by providing `client_id`.
    Requires authentication.
    """
    user_id = str(user.user_id)
    client_id_str = str(payload.client_id) if payload.client_id else None

    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv_id = await conversation_manager.create_conversation(
            session=session,
            client_id=client_id_str,
            user_id=user_id,
        )

    audit_log(
        AuditAction.CONVERSATION_CREATED,
        user_id=user_id,
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource="/api/v1/conversations",
        detail=f"conversation={conv_id}",
    )

    # Fetch the created conversation to return it
    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conv_id,
            user_id=user_id,
        )

    return {"status": "success", "data": _to_conversation_response(conv)}


@router.get("/conversations/{conversation_id}")
@limiter.limit("30/minute")
async def get_conversation(
    request: Request,
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Get a full conversation with all messages.**

    Returns 404 if the conversation does not exist or does not belong to
    the authenticated user.
    Requires authentication.
    """
    user_id = str(user.user_id)

    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    return {"status": "success", "data": _to_conversation_response(conv)}


@router.post("/conversations/{conversation_id}/messages")
@limiter.limit("15/minute")
async def add_message(
    request: Request,
    conversation_id: str,
    payload: MessageCreate,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Add a message to an existing conversation.**

    The role must be `user` or `assistant`. Returns the updated list
    of messages in the conversation.
    Requires authentication.
    """
    user_id = str(user.user_id)

    # Verify conversation exists and belongs to the user
    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Add the message
    async with db_manager.session(org_id=str(user.org_id)) as session:
        await conversation_manager.add_message(
            session=session,
            conversation_id=conversation_id,
            role=payload.role,
            content=payload.content,
            metadata=payload.metadata,
        )

    # Fetch updated conversation to return current messages
    async with db_manager.session(org_id=str(user.org_id)) as session:
        updated = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    return {"status": "success", "data": _to_conversation_response(updated)}


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("15/minute")
async def delete_conversation(
    request: Request,
    conversation_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Delete a conversation.**

    Returns 204 No Content on success. Returns 404 if the conversation
    does not exist or does not belong to the authenticated user.
    Requires authentication.
    """
    user_id = str(user.user_id)

    # Verify ownership first
    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    # Perform deletion
    async with db_manager.session(org_id=str(user.org_id)) as session:
        from sqlalchemy import text

        await session.execute(
            text(
                "DELETE FROM conversations "
                "WHERE CAST(id AS TEXT) = :id AND CAST(user_id AS TEXT) = :user_id"
            ),
            {"id": conversation_id, "user_id": user_id},
        )
        await session.commit()

    audit_log(
        AuditAction.CONVERSATION_DELETED,
        user_id=user_id,
        org_id=str(user.org_id),
        ip_address=get_client_ip(request),
        resource=f"/api/v1/conversations/{conversation_id}",
        detail=f"conversation={conversation_id}",
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations/{conversation_id}/context")
@limiter.limit("30/minute")
async def get_conversation_context(
    request: Request,
    conversation_id: str,
    max_messages: int = Query(
        default=10, ge=1, le=100, description="Max recent messages to include"
    ),
    user: CurrentUser = Depends(get_current_user),
):
    """
    **Get formatted conversation context for LLM Q&A.**

    Returns the most recent messages formatted as a list of
    `{role, content}` dicts suitable for injecting into an LLM prompt.
    Requires authentication.
    """
    user_id = str(user.user_id)

    # Verify ownership
    async with db_manager.session(org_id=str(user.org_id)) as session:
        conv = await conversation_manager.get_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=user_id,
        )

    if conv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )

    async with db_manager.session(org_id=str(user.org_id)) as session:
        context = await conversation_manager.get_context_for_qa(
            session=session,
            conversation_id=conversation_id,
            max_messages=max_messages,
        )

    return {"status": "success", "data": {"context": context}}


# --- Helpers -------------------------------------------------------------------


def _to_conversation_response(conv: dict | None) -> dict:
    """Convert a raw conversation dict from the manager into a response dict."""
    if conv is None:
        return {}

    raw_messages = conv.get("messages", [])
    messages = [
        MessageResponse(
            role=m.get("role", "user"),
            content=m.get("content", ""),
            timestamp=m.get("timestamp"),
            metadata=m.get("metadata"),
        )
        for m in raw_messages
    ]

    return ConversationResponse(
        id=conv["id"],
        user_id=conv["user_id"],
        client_id=conv.get("client_id"),
        messages=messages,
        created_at=conv.get("created_at"),
        updated_at=conv.get("updated_at"),
    ).model_dump()
