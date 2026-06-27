"""Add Normattiva and CoVe support.

Revision ID: 004_normattiva_cove
Revises: 003_temporal_metadata
Create Date: 2026-04-09

Adds:
- Multi-source fields to regulations (source, urn, current_text_url, versions)
- New citation_verifications table for CoVe pipeline
- Indexes on source and urn for efficient querying
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "004_normattiva_cove"
down_revision = "003_temporal_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add multi-source fields to regulations ──────────────────────
    op.add_column(
        "regulations",
        sa.Column(
            "source",
            sa.String(20),
            server_default="eurlex",
            comment='Source: "eurlex" or "normattiva"',
        ),
    )
    op.add_column(
        "regulations",
        sa.Column(
            "urn",
            sa.String(200),
            nullable=True,
            unique=True,
            comment="Italian URN identifier (Normattiva)",
        ),
    )
    op.add_column(
        "regulations",
        sa.Column(
            "current_text_url",
            sa.String(500),
            nullable=True,
            comment="URL to the current version of the text",
        ),
    )
    op.add_column(
        "regulations",
        sa.Column(
            "versions",
            pg.JSONB,
            nullable=True,
            comment="Array of {date, status, url} objects tracking all versions",
        ),
    )

    # ── 2. Indexes on new fields ──────────────────────────────────────
    op.create_index("idx_regulations_source", "regulations", ["source"])
    op.create_index("idx_regulations_urn", "regulations", ["urn"])

    # ── 3. Create citation_verifications table ────────────────────────
    op.create_table(
        "citation_verifications",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "reference",
            sa.String(300),
            nullable=False,
            comment="URN, CELEX, or article reference",
        ),
        sa.Column(
            "reference_type",
            sa.String(20),
            nullable=False,
            comment='Type: "urn", "celex", or "article"',
        ),
        sa.Column(
            "verified",
            sa.Boolean,
            server_default="false",
            comment="Whether this reference has been verified",
        ),
        sa.Column(
            "is_current",
            sa.Boolean,
            server_default="true",
            comment="Whether this reference is still current",
        ),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            comment='Source: "normattiva" or "eurlex"',
        ),
        sa.Column(
            "url",
            sa.String(500),
            nullable=True,
            comment="URL where this reference was found",
        ),
        sa.Column(
            "last_checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            comment="Timestamp of last verification check",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            comment="When this record was created",
        ),
    )

    # ── 4. Indexes on citation_verifications ──────────────────────────
    op.create_index("idx_citation_verifications_reference", "citation_verifications", ["reference"])
    op.create_index("idx_citation_verifications_source", "citation_verifications", ["source"])
    op.create_index("idx_citation_verifications_verified", "citation_verifications", ["verified"])


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_citation_verifications_verified")
    op.drop_index("idx_citation_verifications_source")
    op.drop_index("idx_citation_verifications_reference")

    # Drop citation_verifications table
    op.drop_table("citation_verifications")

    # Drop indexes on regulations
    op.drop_index("idx_regulations_urn")
    op.drop_index("idx_regulations_source")

    # Remove multi-source fields from regulations
    op.drop_column("regulations", "versions")
    op.drop_column("regulations", "current_text_url")
    op.drop_column("regulations", "urn")
    op.drop_column("regulations", "source")
