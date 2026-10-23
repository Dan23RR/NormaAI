"""Invites table (invite-only registration) + users.email_verified.

Revision ID: 008_invites
Revises: 006_lead_download_email_tracking
Create Date: 2026-10-23

NOTE: numbered 008 on purpose - a sibling branch adds 007; the chain is
reconciled at merge time (down_revision then becomes that 007 revision).

Adds:
- invites: single-use, expiring registration codes (SHA-256 of the code is
  stored, never the plaintext). org_id NULL = the invitee creates a new
  organization as admin; set = joins that organization with `role`.
- users.email_verified (bool, NOT NULL, default false). Accounts that exist at
  migration time are grandfathered as verified: they were onboarded by hand and
  must not be locked out the day REQUIRE_EMAIL_VERIFICATION is switched on.

RLS on invites follows migration 002 (ENABLE + FORCE, org isolation on
org_id) plus one extra policy for the NO-org session used by the public auth
path (/auth/register redeems a code before any user exists, and staff/CLI
create org-less invites). Mirrors `organizations_insert WITH CHECK (true)` in
scripts/setup_app_role.sql: on a session without an org context the rows are
reachable only through their unguessable code hash at the application level.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "008_invites"
down_revision = "006_lead_download_email_tracking"
branch_labels = None
depends_on = None

_NO_ORG_CONTEXT = "coalesce(current_setting('app.current_org_id', true), '') = ''"
_ORG_MATCH = "org_id::text = current_setting('app.current_org_id', true)"


def upgrade() -> None:
    op.create_table(
        "invites",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column(
            "org_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
            comment="NULL = invitee creates a new organization (as admin)",
        ),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column(
            "created_by",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "used_by",
            pg.UUID(as_uuid=True),
            nullable=True,
            comment="Registered user id; no FK (flushed before the user row exists)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_invites_email", "invites", ["email"])
    op.create_index("ix_invites_org_id", "invites", ["org_id"])

    # Row-Level Security (same shape as migration 002 for org-scoped tables).
    op.execute("ALTER TABLE invites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invites FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY invites_org_isolation ON invites USING ({_ORG_MATCH})")
    op.execute(f"CREATE POLICY invites_org_insert ON invites FOR INSERT WITH CHECK ({_ORG_MATCH})")
    # Public auth path / staff / CLI: a session WITHOUT an org context.
    op.execute(
        "CREATE POLICY invites_no_org_context ON invites "
        f"USING ({_NO_ORG_CONTEXT}) WITH CHECK ({_NO_ORG_CONTEXT})"
    )

    # users.email_verified
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Grandfather pre-existing accounts (see module docstring).
    op.execute("UPDATE users SET email_verified = true")


def downgrade() -> None:
    op.drop_column("users", "email_verified")
    for policy in ("invites_no_org_context", "invites_org_insert", "invites_org_isolation"):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON invites")
    op.drop_index("ix_invites_org_id", table_name="invites")
    op.drop_index("ix_invites_email", table_name="invites")
    op.drop_table("invites")
