"""Initial schema migration.

Revision ID: 001_initial
Revises:
Create Date: 2026-02-28
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Organizations
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(200), unique=True, nullable=False),
        sa.Column("plan", sa.String(50), server_default="starter"),
        sa.Column("max_clients", sa.Integer, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Clients (monitored companies)
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("sector", sa.String(100)),
        sa.Column("employee_count", sa.Integer),
        sa.Column("revenue_eur", sa.BigInteger),
        sa.Column("jurisdictions", postgresql.ARRAY(sa.String)),
        sa.Column("applicable_frameworks", postgresql.ARRAY(sa.String)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Regulations
    op.create_table(
        "regulations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("celex", sa.String(50), unique=True, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("framework", sa.String(50)),
        sa.Column("doc_type", sa.String(50)),
        sa.Column("date_document", sa.Date),
        sa.Column("is_in_force", sa.Boolean),
        sa.Column("raw_html", sa.Text),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Amendments
    op.create_table(
        "amendments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("original_regulation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("regulations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amending_celex", sa.String(50), nullable=False),
        sa.Column("amending_title", sa.Text),
        sa.Column("amendment_date", sa.Date),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Alerts
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("regulation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("regulations.id")),
        sa.Column("severity", sa.String(20)),
        sa.Column("framework", sa.String(50)),
        sa.Column("title", sa.String(500)),
        sa.Column("summary", sa.Text),
        sa.Column("actions_required", postgresql.ARRAY(sa.String)),
        sa.Column("deadline", sa.Date),
        sa.Column("is_read", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_alerts_client", "alerts", ["client_id", "created_at"])

    # Assessments (gap analysis results)
    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("overall_score", sa.Float),
        sa.Column("gaps", postgresql.JSONB),
        sa.Column("recommendations", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_assessments_client", "assessments", ["client_id", "framework"])

    # Conversations (Q&A history)
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="SET NULL")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("messages", postgresql.JSONB, server_default="'[]'::jsonb"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Crawl jobs
    op.create_table(
        "crawl_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("regulations_processed", sa.Integer, server_default="0"),
        sa.Column("amendments_found", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # Refresh token blacklist (for token revocation)
    op.create_table(
        "revoked_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("jti", sa.String(255), unique=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_revoked_tokens_jti", "revoked_tokens", ["jti"])


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_table("crawl_jobs")
    op.drop_table("conversations")
    op.drop_table("assessments")
    op.drop_table("alerts")
    op.drop_table("amendments")
    op.drop_table("regulations")
    op.drop_table("clients")
    op.drop_table("users")
    op.drop_table("organizations")
