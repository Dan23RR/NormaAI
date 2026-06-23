"""Conversation persistence for multi-turn Q&A sessions."""

import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages Q&A conversation history in PostgreSQL."""

    async def create_conversation(
        self,
        session: AsyncSession,
        client_id: str | None,
        user_id: str,
    ) -> str:
        """Create a new conversation. Returns conversation_id."""
        conv_id = str(uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO conversations (id, client_id, user_id, messages, created_at, updated_at)
                VALUES (:id, :client_id, :user_id, :messages, :now, :now)
            """),
            {
                "id": conv_id,
                "client_id": client_id,
                "user_id": user_id,
                "messages": json.dumps([]),
                "now": datetime.now(UTC),
            },
        )
        await session.commit()
        return conv_id

    async def add_message(
        self,
        session: AsyncSession,
        conversation_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Add a message to an existing conversation."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if metadata:
            message["metadata"] = metadata

        await session.execute(
            text("""
                UPDATE conversations
                SET messages = messages || :message::jsonb,
                    updated_at = :now
                WHERE CAST(id AS TEXT) = :conv_id
            """),
            {
                "conv_id": conversation_id,
                "message": json.dumps([message]),
                "now": datetime.now(UTC),
            },
        )
        await session.commit()

    async def get_conversation(
        self,
        session: AsyncSession,
        conversation_id: str,
        user_id: str | None = None,
    ) -> dict | None:
        """Get a conversation by ID, optionally filtered by user_id for access control."""
        # Static SQL only - never assemble query strings dynamically.
        # ``:user_id IS NULL`` keeps the no-filter path in the same statement.
        # CAST the UUID columns to text: the bound params are Python strings and
        # PostgreSQL has no implicit ``uuid = text`` operator (asyncpg raises
        # UndefinedFunctionError). CAST(... AS TEXT) is portable across Postgres
        # and the sqlite test backend (``::text`` is not).
        query = text("""
            SELECT id, client_id, user_id, messages, created_at
            FROM conversations
            WHERE CAST(id AS TEXT) = :id
              AND (CAST(:user_id AS TEXT) IS NULL OR CAST(user_id AS TEXT) = :user_id)
        """)
        params: dict = {"id": conversation_id, "user_id": user_id}
        result = await session.execute(query, params)
        row = result.fetchone()
        if not row:
            return None

        return {
            "id": str(row[0]),
            "client_id": str(row[1]) if row[1] else None,
            "user_id": str(row[2]),
            "messages": json.loads(row[3]) if isinstance(row[3], str) else row[3],
            "created_at": row[4].isoformat() if row[4] else None,
        }

    async def get_context_for_qa(
        self,
        session: AsyncSession,
        conversation_id: str,
        max_messages: int = 10,
    ) -> str:
        """Get recent conversation context formatted for the Q&A prompt."""
        conv = await self.get_conversation(session, conversation_id)
        if not conv or not conv["messages"]:
            return ""

        recent = conv["messages"][-max_messages:]
        parts = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"[{role.upper()}]: {content}")

        return "\n".join(parts)


conversation_manager = ConversationManager()
