"""Suppression list table + KPI views v2 for Wave 2 decision gate G+21.

Revision ID: 008_suppression_list_and_kpi_views
Revises: 007_extend_leads_for_outreach
Create Date: 2026-05-15

Adds:
- suppression_list table — email/domain blocked for outreach (unsubscribe, bounce, manual)
- View bizdev_decision_gate_g21 — KPI per icp_hypothesis con threshold ≥5% per decision
- View bizdev_funnel_per_hypothesis — funnel target→qualified→sent→opened→clicked→replied→booked
- View bizdev_daily_activity — per-day activity tracker (cron Friday digest)
- Function suppress_email() — single-call suppression with reason audit
- Trigger on outreach_events to auto-suppress on unsubscribe/bounce
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg


revision = "008_suppression_list_and_kpi_views"
down_revision = "007_extend_leads_for_outreach"
branch_labels = None
depends_on = None


SUPPRESSION_REASON_VALUES = (
    "unsubscribe",      # explicit reply STOP / unsubscribe request
    "bounce",           # hard bounce from Resend webhook
    "complaint",        # spam complaint
    "manual",           # founder marked manually
    "gdpr_request",     # right to be forgotten
)


def upgrade() -> None:
    # ── 1. suppression_list table ──────────────────────────────────────
    op.create_table(
        "suppression_list",
        sa.Column(
            "id",
            pg.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "domain",
            sa.String(255),
            nullable=True,
            comment="Optional: suppress entire domain (e.g. competitor company)",
        ),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column(
            "source_event_id",
            pg.UUID(as_uuid=True),
            nullable=True,
            comment="FK to outreach_events.id if triggered by reply (no FK constraint for soft-link)",
        ),
        sa.Column(
            "notes",
            sa.Text,
            nullable=True,
            comment="Optional context (e.g. full reply body for unsubscribe)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="NULL = forever. Otherwise timestamp to re-eligibility (e.g. 24mo for cold)",
        ),
    )
    op.create_check_constraint(
        "ck_suppression_list_reason",
        "suppression_list",
        f"reason IN {SUPPRESSION_REASON_VALUES}",
    )
    op.create_index(
        "ix_suppression_list_email",
        "suppression_list",
        ["email"],
    )
    op.create_index(
        "ix_suppression_list_domain",
        "suppression_list",
        ["domain"],
        postgresql_where=sa.text("domain IS NOT NULL"),
    )

    # ── 2. Helper function to check suppression ────────────────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION is_suppressed(check_email TEXT) RETURNS BOOLEAN AS $$
        BEGIN
            RETURN EXISTS (
                SELECT 1 FROM suppression_list
                WHERE (lower(email) = lower(check_email)
                       OR (domain IS NOT NULL AND lower(check_email) LIKE '%@' || lower(domain)))
                  AND (expires_at IS NULL OR expires_at > now())
            );
        END;
        $$ LANGUAGE plpgsql STABLE;
        """
    )

    # ── 3. Decision gate G+21 view — the money view ────────────────────
    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_decision_gate_g21 AS
        SELECT
            l.icp_hypothesis,
            count(DISTINCT l.id) FILTER (WHERE l.outreach_status = 'qualified') AS qualified,
            count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) AS sent,
            count(DISTINCT oe.id) FILTER (WHERE oe.opened_at IS NOT NULL) AS opened,
            count(DISTINCT oe.id) FILTER (WHERE oe.clicked_at IS NOT NULL) AS clicked,
            count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive') AS replied_positive,
            count(DISTINCT oe.id) FILTER (WHERE oe.reply_status IN ('cold', 'objection')) AS replied_negative,
            count(DISTINCT l.id) FILTER (WHERE l.outreach_status = 'booked') AS booked,

            ROUND(
                100.0 * count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive')
                / NULLIF(count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL), 0),
                2
            ) AS reply_rate_positive_pct,

            CASE
                WHEN count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) < 8 THEN 'CAMPIONE_TROPPO_BASSO'
                WHEN ROUND(
                    100.0 * count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive')
                    / NULLIF(count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL), 0),
                    2
                ) >= 5.0 THEN 'GO_DOUBLE_DOWN'
                WHEN ROUND(
                    100.0 * count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive')
                    / NULLIF(count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL), 0),
                    2
                ) >= 2.0 THEN 'MONITORARE_+7g'
                ELSE 'KILL_HYPOTHESIS'
            END AS verdict_g21
        FROM leads l
        LEFT JOIN outreach_events oe ON oe.lead_id = l.id AND oe.direction = 'outbound'
        WHERE l.icp_hypothesis IS NOT NULL
        GROUP BY l.icp_hypothesis
        ORDER BY l.icp_hypothesis;
        """
    )

    # ── 4. Funnel view (drop-off analysis per hypothesis) ──────────────
    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_funnel_per_hypothesis AS
        WITH funnel_stages AS (
            SELECT
                l.icp_hypothesis AS hyp,
                count(DISTINCT l.id) AS s1_target,
                count(DISTINCT l.id) FILTER (
                    WHERE l.outreach_status IN ('qualified','sent','replied_positive','replied_cold','replied_objection','booked','lost')
                ) AS s2_qualified,
                count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) AS s3_sent,
                count(DISTINCT oe.id) FILTER (WHERE oe.opened_at IS NOT NULL) AS s4_opened,
                count(DISTINCT oe.id) FILTER (WHERE oe.clicked_at IS NOT NULL) AS s5_clicked,
                count(DISTINCT oe.id) FILTER (WHERE oe.reply_status = 'positive') AS s6_replied_positive,
                count(DISTINCT l.id) FILTER (WHERE l.outreach_status = 'booked') AS s7_booked
            FROM leads l
            LEFT JOIN outreach_events oe ON oe.lead_id = l.id AND oe.direction = 'outbound'
            WHERE l.icp_hypothesis IS NOT NULL
            GROUP BY l.icp_hypothesis
        )
        SELECT
            hyp,
            s1_target, s2_qualified, s3_sent, s4_opened, s5_clicked, s6_replied_positive, s7_booked,
            ROUND(100.0 * s2_qualified / NULLIF(s1_target, 0), 1) AS pct_target_to_qualified,
            ROUND(100.0 * s3_sent / NULLIF(s2_qualified, 0), 1) AS pct_qualified_to_sent,
            ROUND(100.0 * s4_opened / NULLIF(s3_sent, 0), 1) AS pct_sent_to_opened,
            ROUND(100.0 * s5_clicked / NULLIF(s4_opened, 0), 1) AS pct_opened_to_clicked,
            ROUND(100.0 * s6_replied_positive / NULLIF(s3_sent, 0), 1) AS pct_sent_to_positive,
            ROUND(100.0 * s7_booked / NULLIF(s6_replied_positive, 0), 1) AS pct_positive_to_booked
        FROM funnel_stages;
        """
    )

    # ── 5. Daily activity (per cron Friday digest) ─────────────────────
    op.execute(
        """
        CREATE OR REPLACE VIEW bizdev_daily_activity AS
        SELECT
            (oe.sent_at AT TIME ZONE 'Europe/Rome')::date AS activity_date,
            l.icp_hypothesis,
            count(DISTINCT oe.id) FILTER (WHERE oe.sent_at IS NOT NULL) AS sent,
            count(DISTINCT oe.id) FILTER (WHERE oe.opened_at IS NOT NULL) AS opened,
            count(DISTINCT oe.id) FILTER (WHERE oe.clicked_at IS NOT NULL) AS clicked,
            count(DISTINCT oe.id) FILTER (WHERE oe.replied_at IS NOT NULL) AS replied
        FROM outreach_events oe
        JOIN leads l ON l.id = oe.lead_id
        WHERE oe.sent_at >= now() - interval '30 days'
        GROUP BY (oe.sent_at AT TIME ZONE 'Europe/Rome')::date, l.icp_hypothesis
        ORDER BY activity_date DESC, l.icp_hypothesis;
        """
    )

    # ── 6. Trigger: auto-suppress on unsubscribe / bounce ──────────────
    op.execute(
        """
        CREATE OR REPLACE FUNCTION auto_suppress_on_event() RETURNS TRIGGER AS $$
        DECLARE
            target_email TEXT;
        BEGIN
            IF NEW.reply_status IN ('unsubscribe', 'bounce') THEN
                SELECT lower(email) INTO target_email FROM leads WHERE id = NEW.lead_id;
                IF target_email IS NOT NULL THEN
                    INSERT INTO suppression_list (email, reason, source_event_id)
                    VALUES (target_email, NEW.reply_status, NEW.id)
                    ON CONFLICT (email) DO NOTHING;
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER trg_auto_suppress_on_event
        AFTER INSERT OR UPDATE OF reply_status ON outreach_events
        FOR EACH ROW
        WHEN (NEW.reply_status IN ('unsubscribe', 'bounce'))
        EXECUTE FUNCTION auto_suppress_on_event();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_auto_suppress_on_event ON outreach_events;")
    op.execute("DROP FUNCTION IF EXISTS auto_suppress_on_event();")
    op.execute("DROP VIEW IF EXISTS bizdev_daily_activity;")
    op.execute("DROP VIEW IF EXISTS bizdev_funnel_per_hypothesis;")
    op.execute("DROP VIEW IF EXISTS bizdev_decision_gate_g21;")
    op.execute("DROP FUNCTION IF EXISTS is_suppressed(TEXT);")

    op.drop_index("ix_suppression_list_domain", table_name="suppression_list")
    op.drop_index("ix_suppression_list_email", table_name="suppression_list")
    op.drop_table("suppression_list")
