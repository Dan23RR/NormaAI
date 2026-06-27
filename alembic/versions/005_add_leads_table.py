"""Add leads table for public lead capture (Codex download, demo requests).

Revision ID: 005_add_leads_table
Revises: 004_normattiva_cove
Create Date: 2026-04-28

Adds:
- leads table with anti-spam fields (ip, user_agent, referer)
- Indexes on email and (email, created_at) for rate-limit queries
- Lifecycle tracking (status, notes) for CRM-light workflow
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "005_add_leads_table"
down_revision = "004_normattiva_cove"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("org_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column(
            "source",
            sa.String(50),
            nullable=False,
            server_default="codex_download",
            comment="Channel: codex_download | demo_request | newsletter",
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("referer", sa.String(500), nullable=True),
        sa.Column(
            "status",
            sa.String(50),
            nullable=False,
            server_default="new",
            comment="Lifecycle: new | contacted | qualified | converted | lost",
        ),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_email_created", "leads", ["email", "created_at"])
    op.create_index("ix_leads_created_at", "leads", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_leads_created_at", table_name="leads")
    op.drop_index("ix_leads_email_created", table_name="leads")
    op.drop_index("ix_leads_email", table_name="leads")
    op.drop_table("leads")
