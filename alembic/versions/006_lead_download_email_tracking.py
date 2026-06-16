"""Add download + email tracking columns to leads.

Revision ID: 006_lead_download_email_tracking
Revises: 005_add_leads_table
Create Date: 2026-04-28

Adds:
- leads.downloaded_at: timestamp del primo download Codex
- leads.download_count: numero totale download (1 per ogni hit valido /codex/download)
- leads.last_email_sent_at: timestamp ultimo invio email transazionale
- leads.email_error: errore SMTP eventuale (per troubleshooting)
"""
from alembic import op
import sqlalchemy as sa


revision = "006_lead_download_email_tracking"
down_revision = "005_add_leads_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column(
        "download_count", sa.Integer, nullable=False, server_default="0"
    ))
    op.add_column("leads", sa.Column("last_email_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("leads", sa.Column("email_error", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("leads", "email_error")
    op.drop_column("leads", "last_email_sent_at")
    op.drop_column("leads", "download_count")
    op.drop_column("leads", "downloaded_at")
