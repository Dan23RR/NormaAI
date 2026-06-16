"""Extend leads with outbound outreach fields + add outreach_events table.

Revision ID: 007_extend_leads_for_outreach
Revises: 006_lead_download_email_tracking
Create Date: 2026-05-08

Adds:
- leads.icp_hypothesis (H1/H2/H3 enum) — Wave 2 cluster assignment
- leads.outreach_status (granular outbound lifecycle, parallel to legacy `status`)
- leads.email_verified (bool) — verifier check before sending
- leads.source_channel (registroimprese|linkedin_free|cnf_albo|ivass|banca_italia|inbound|manual)
- leads.enrichment_data (jsonb) — sector, size, decision_maker_role, etc.
- leads.personalization_hook (text) — 1 verified fact for email opener
- leads.last_outreach_at (timestamptz)
- leads.first_name, last_name, role_title — split from generic `org_name`/`role`
- New `outreach_events` table — append-only log of every send + reply
- View bizdev_pipeline_kpi — for weekly-digest agent
- View bizdev_reply_rate_by_hypothesis — for decision gate G+21

Postgres-only (uses jsonb, CHECK constraints for enum-like, partial indexes).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "007_extend_leads_for_outreach"
down_revision = "006_lead_download_email_tracking"
branch_labels = None
depends_on = None


# Enum-like value sets (CHECK constraints, not pg ENUM types — more portable)
ICP_HYPOTHESIS_VALUES = ("H1", "H2", "H3")
OUTREACH_STATUS_VALUES = (
    "target",          # identified but not yet qualified
    "qualified",       # email verified + hook ready
    "sent",            # cold email sent
    "replied_positive",
    "replied_cold",
    "replied_objection",
    "replied_unsubscribe",
    "booked",          # call in calendar
    "lost",            # no reply after 2 follow-ups OR explicit no
    "excluded",        # out of ICP, do not pursue
)
SOURCE_CHANNEL_VALUES = (
    "inbound",          # legacy: came in via Codex form
    "registroimprese",  # H1
    "linkedin_free",    # H1/H2/H3
    "cnf_albo",         # H2
    "ivass",            # H3
    "banca_italia",     # H3
    "manual",           # founder added by hand
)
EVENT_CHANNEL_VALUES = ("email", "linkedin_dm", "phone", "other")
EVENT_DIRECTION_VALUES = ("outbound", "inbound")
REPLY_STATUS_VALUES = (
    "none",
    "positive",
    "cold",
    "objection",
    "unsubscribe",
    "out_of_office",
    "bounce",
)


def upgrade() -> None:
    # ── 1. Extend leads table ──────────────────────────────────────────
    op.add_column("leads", sa.Column("icp_hypothesis", sa.String(8), nullable=True))
    op.add_column(
        "leads",
        sa.Column(
            "outreach_status",
            sa.String(32),
            nullable=False,
            server_default="target",
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "email_verified",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "source_channel",
            sa.String(32),
            nullable=False,
            server_default="inbound",
        ),
    )
    op.add_column(
        "leads",
        sa.Column(
            "enrichment_data",
            pg.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("leads", sa.Column("personalization_hook", sa.Text, nullable=True))
    op.add_column(
        "leads",
        sa.Column("last_outreach_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("leads", sa.Column("first_name", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("last_name", sa.String(100), nullable=True))
    op.add_column("leads", sa.Column("role_title", sa.String(150), nullable=True))

    # CHECK constraints
    op.create_check_constraint(
        "ck_leads_icp_hypothesis",
        "leads",
        f"icp_hypothesis IS NULL OR icp_hypothesis IN {ICP_HYPOTHESIS_VALUES}",
    )
    op.create_check_constraint(
        "ck_leads_outreach_status",
        "leads",
        f"outreach_status IN {OUTREACH_STATUS_VALUES}",
    )
    op.create_check_constraint(
        "ck_leads_source_channel",
        "leads",
        f"source_channel IN {SOURCE_CHANNEL_VALUES}",
    )

    # Indexes for agent queries
    op.create_index(
        "ix_leads_hypothesis_status",
        "leads",
        ["icp_hypothesis", "outreach_status"],
        postgresql_where=sa.text("icp_hypothesis IS NOT NULL"),
    )
    op.create_index(
        "ix_leads_outreach_qualified",
        "leads",
        ["last_outreach_at"],
        postgresql_where=sa.text("outreach_status = 'qualified'"),
    )

    # ── 2. outreach_events table ───────────────────────────────────────
    op.create_table(
        "outreach_events",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("direction", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body_draft", sa.Text, nullable=True),
        sa.Column("body_sent", sa.Text, nullable=True),
        sa.Column(
            "draft_approved",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="True after Daniel approves a draft for sending",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reply_body", sa.Text, nullable=True),
        sa.Column(
            "reply_status",
            sa.String(20),
            nullable=False,
            server_default="none",
        ),
        sa.Column("sentiment", sa.Float, nullable=True, comment="-1.0 to 1.0"),
        sa.Column("objection_cluster", sa.String(64), nullable=True),
        sa.Column(
            "thread_id",
            sa.String(255),
            nullable=True,
            comment="IMAP thread id for grouping replies",
        ),
        sa.Column(
            "raw_message_id",
            sa.String(255),
            nullable=True,
            comment="RFC 5322 Message-ID for dedup",
        ),
        sa.Column(
            "idempotency_key",
            sa.String(64),
            nullable=True,
            comment="hash(lead_id+subject+date) to prevent duplicate sends",
        ),
        sa.Column("provider_meta", pg.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_check_constraint(
        "ck_outreach_events_channel",
        "outreach_events",
        f"channel IN {EVENT_CHANNEL_VALUES}",
    )
    op.create_check_constraint(
        "ck_outreach_events_direction",
        "outreach_events",
        f"direction IN {EVENT_DIRECTION_VALUES}",
    )
    op.create_check_constraint(
        "ck_outreach_events_reply_status",
        "outreach_events",
        f"reply_status IN {REPLY_STATUS_VALUES}",
    )
    op.create_index(
        "ix_outreach_events_lead",
        "outreach_events",
        ["lead_id", "created_at"],
    )
    op.create_index(
        "ix_outreach_events_sent_at",
        "outreach_events",
        ["sent_at"],
        postgresql_where=sa.text("sent_at IS NOT NULL"),
    )
    op.create_index(
        "ix_outreach_events_replied",
        "outreach_events",
        ["replied_at", "reply_status"],
        postgresql_where=sa.text("replied_at IS NOT NULL"),
    )
    op.create_index(
        "uq_outreach_events_idempotency",
        "outreach_events",
        ["idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ── 3. Reporting views (postgres-only) ─────────────────────────────
    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_pipeline_kpi AS
        SELECT
            icp_hypothesis,
            outreach_status,
            count(*)            AS lead_count,
            count(*) FILTER (WHERE email_verified)        AS verified_count,
            count(*) FILTER (WHERE last_outreach_at IS NOT NULL) AS contacted_count,
            max(last_outreach_at) AS last_activity_at
        FROM leads
        WHERE icp_hypothesis IS NOT NULL
        GROUP BY icp_hypothesis, outreach_status;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_reply_rate_by_hypothesis AS
        SELECT
            l.icp_hypothesis,
            count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) AS sent,
            count(DISTINCT oe.id) FILTER (WHERE oe.opened_at IS NOT NULL) AS opened,
            count(DISTINCT oe.id) FILTER (WHERE oe.clicked_at IS NOT NULL) AS clicked,
            count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive') AS replied_positive,
            count(DISTINCT oe.id) FILTER (WHERE oe.reply_status IN ('cold', 'objection', 'positive')) AS replied_total,
            ROUND(
                100.0 * count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive')
                / NULLIF(count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL), 0),
                2
            ) AS reply_rate_positive_pct,
            ROUND(
                100.0 * count(DISTINCT oe.id) FILTER (WHERE oe.opened_at IS NOT NULL)
                / NULLIF(count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL), 0),
                2
            ) AS open_rate_pct
        FROM leads l
        LEFT JOIN outreach_events oe ON oe.lead_id = l.id AND oe.direction = 'outbound'
        WHERE l.icp_hypothesis IS NOT NULL
        GROUP BY l.icp_hypothesis;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_weekly_activity AS
        SELECT
            date_trunc('week', oe.sent_at) AS week_start,
            l.icp_hypothesis,
            count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) AS emails_sent,
            count(DISTINCT oe.id) FILTER (WHERE oe.replied_at IS NOT NULL) AS replies_received,
            count(DISTINCT l.id) FILTER (WHERE l.outreach_status = 'qualified') AS prospects_qualified
        FROM outreach_events oe
        JOIN leads l ON l.id = oe.lead_id
        WHERE oe.sent_at >= now() - interval '90 days'
        GROUP BY date_trunc('week', oe.sent_at), l.icp_hypothesis
        ORDER BY week_start DESC, l.icp_hypothesis;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS bizdev_weekly_activity;")
    op.execute("DROP VIEW IF EXISTS bizdev_reply_rate_by_hypothesis;")
    op.execute("DROP VIEW IF EXISTS bizdev_pipeline_kpi;")

    op.drop_index("uq_outreach_events_idempotency", table_name="outreach_events")
    op.drop_index("ix_outreach_events_replied", table_name="outreach_events")
    op.drop_index("ix_outreach_events_sent_at", table_name="outreach_events")
    op.drop_index("ix_outreach_events_lead", table_name="outreach_events")
    op.drop_table("outreach_events")

    op.drop_index("ix_leads_outreach_qualified", table_name="leads")
    op.drop_index("ix_leads_hypothesis_status", table_name="leads")
    op.drop_constraint("ck_leads_source_channel", "leads", type_="check")
    op.drop_constraint("ck_leads_outreach_status", "leads", type_="check")
    op.drop_constraint("ck_leads_icp_hypothesis", "leads", type_="check")

    for col in (
        "role_title",
        "last_name",
        "first_name",
        "last_outreach_at",
        "personalization_hook",
        "enrichment_data",
        "source_channel",
        "email_verified",
        "outreach_status",
        "icp_hypothesis",
    ):
        op.drop_column("leads", col)
