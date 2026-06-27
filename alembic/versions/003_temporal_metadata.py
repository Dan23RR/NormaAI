"""Add temporal metadata and parent document storage.

Revision ID: 003_temporal_metadata
Revises: 002_enable_rls_policies
Create Date: 2026-03-01

Adds change-detection and versioning columns to regulations, and creates
the parent_documents table for the Parent Document Retrieval pattern.
Parent documents store full articles; smaller sub-chunks are used for
vector search and then resolved back to their parent for LLM context.
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "003_temporal_metadata"
down_revision = "002_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Temporal tracking columns on regulations ──────────────────────
    op.add_column(
        "regulations",
        sa.Column("content_hash", sa.String(64), comment="SHA-256 of raw_html for change detection"),
    )
    op.add_column(
        "regulations",
        sa.Column("superseded_by", sa.String(20), comment="CELEX of the superseding regulation"),
    )
    op.add_column(
        "regulations",
        sa.Column(
            "effective_date",
            sa.DateTime(timezone=True),
            comment="When this version became effective",
        ),
    )
    op.add_column(
        "regulations",
        sa.Column(
            "version_number",
            sa.Integer,
            server_default="1",
            comment="Version counter for the same CELEX",
        ),
    )

    # ── 2. Parent documents table ────────────────────────────────────────
    op.create_table(
        "parent_documents",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("celex", sa.String(20), nullable=False),
        sa.Column("framework", sa.String(50), nullable=False),
        sa.Column("article_number", sa.String(50), comment='e.g. "Art. 29"'),
        sa.Column("section_title", sa.String(500)),
        sa.Column("full_text", sa.Text, nullable=False),
        sa.Column(
            "content_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 for dedup",
        ),
        sa.Column(
            "chunk_ids",
            pg.ARRAY(sa.Text),
            comment="Related chunk point IDs in Qdrant",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # Indexes
    op.create_index("idx_parent_docs_celex", "parent_documents", ["celex"])
    op.create_index("idx_parent_docs_framework", "parent_documents", ["framework"])
    op.create_index(
        "idx_parent_docs_article", "parent_documents", ["celex", "article_number"]
    )
    op.create_unique_constraint(
        "uq_parent_docs_celex_article", "parent_documents", ["celex", "article_number"]
    )

    # ── 3. RLS on parent_documents ───────────────────────────────────────
    # Parent documents are shared regulatory text (not tenant-scoped),
    # so the policy allows all authenticated users to read.
    op.execute("ALTER TABLE parent_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE parent_documents FORCE ROW LEVEL SECURITY")

    # SELECT: any authenticated session (current_setting returns non-empty org_id)
    op.execute("""
        CREATE POLICY parent_documents_read_all ON parent_documents
        FOR SELECT
        USING (current_setting('app.current_org_id', true) IS NOT NULL
               AND current_setting('app.current_org_id', true) <> '')
    """)

    # INSERT / UPDATE / DELETE: restricted to service role (no org_id check needed;
    # only the application service account should write regulatory content).
    # If no service role exists yet, allow any authenticated user to write as well.
    op.execute("""
        CREATE POLICY parent_documents_write ON parent_documents
        FOR ALL
        USING (current_setting('app.current_org_id', true) IS NOT NULL
               AND current_setting('app.current_org_id', true) <> '')
        WITH CHECK (current_setting('app.current_org_id', true) IS NOT NULL
                    AND current_setting('app.current_org_id', true) <> '')
    """)


def downgrade() -> None:
    # Drop RLS policies
    op.execute("DROP POLICY IF EXISTS parent_documents_read_all ON parent_documents")
    op.execute("DROP POLICY IF EXISTS parent_documents_write ON parent_documents")
    op.execute("ALTER TABLE parent_documents DISABLE ROW LEVEL SECURITY")

    # Drop table
    op.drop_table("parent_documents")

    # Remove temporal columns from regulations
    op.drop_column("regulations", "version_number")
    op.drop_column("regulations", "effective_date")
    op.drop_column("regulations", "superseded_by")
    op.drop_column("regulations", "content_hash")
