"""Document checks: stored outcomes, watched provisions, their alerts, system state.

Revision ID: 009_document_checks
Revises: 008_invites
Create Date: 2026-11-11

Adds
----
- ``document_checks``: one row per checked document. The document is never
  stored: the row keeps its name, its SHA-256, the dates and the findings.
- ``document_dependencies``: the provisions each checked document relies on,
  with the official text of the day of the check. The scheduled surveillance
  compares them with the text in force and marks the ones that changed.
- ``system_state``: a small key-value table for state that belongs to no
  tenant (the outcome of the nightly corpus freshness check).
- ``users.notify_document_changes`` (bool, NOT NULL, default true): the digest
  email of the surveillance, which every user can turn off.
- ``alerts.document_check_id``: the check an alert of the surveillance is
  about. Such an alert belongs to the organisation of the check and may have
  no client.

Row-Level Security
------------------
``document_checks`` and ``document_dependencies`` are tenant tables and get
what ``clients`` has: ENABLE + FORCE, ``<table>_org_isolation`` on ``org_id``
and ``<table>_org_insert`` for INSERT. A session without an organisation sees
no row: the surveillance sets the organisation it is working on, like every
request does (``src/db/engine.py``).

The two ``alerts`` policies of migration 007 let an alert through only by way
of its client. They are replaced by the same policies with one more way in:
the alert's document check, when it belongs to the organisation. The
downgrade puts the 007 definitions back and deletes the alerts without a
client, which no policy would show any more.

``system_state`` holds nothing of a tenant and has no row-level security,
like ``regulations`` or ``crawl_jobs``.

Idempotent
----------
Every statement can run again on a database that already has its object
(``IF NOT EXISTS``, ``DROP POLICY IF EXISTS`` before ``CREATE POLICY``), so an
interrupted upgrade is simply run again. The statements are built by pure
functions from the inline description of the tables: tests/test_migration_009.py
checks offline that this description is what src/db/models.py declares, and
the CI ``schema`` job runs the migration on PostgreSQL followed by
``alembic check``.
"""

from dataclasses import dataclass

import sqlalchemy as sa

from alembic import op

revision = "009_document_checks"
down_revision = "008_invites"
branch_labels = None
depends_on = None


# ─── Target shape (snapshot of src/db/models.py at this revision) ────────────
# Kept inline on purpose, as in 007: a migration must not import the live
# models, whose future edits would silently change what this revision does.


@dataclass(frozen=True)
class Col:
    """A column: ``type`` is the PostgreSQL DDL type as SQLAlchemy compiles it."""

    name: str
    type: str
    nullable: bool = True
    default: str | None = None  # SQL expression
    primary_key: bool = False
    references: str | None = None  # referenced table (its ``id``)
    ondelete: str | None = None


@dataclass(frozen=True)
class Ix:
    name: str
    table: str
    columns: tuple[str, ...]


UUID = "UUID"
TZ = "TIMESTAMP WITH TIME ZONE"
NOW = "now()"

TABLES: dict[str, tuple[Col, ...]] = {
    "document_checks": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("org_id", UUID, nullable=False, references="organizations", ondelete="CASCADE"),
        Col("client_id", UUID, references="clients", ondelete="CASCADE"),
        Col("created_by", UUID, references="users", ondelete="SET NULL"),
        Col("filename", "VARCHAR(255)", nullable=False),
        Col("document_sha256", "VARCHAR(64)", nullable=False),
        Col("document_date", "DATE"),
        Col("lang", "VARCHAR(8)", nullable=False, default="'IT'"),
        Col("watch", "BOOLEAN", nullable=False, default="true"),
        Col("status", "VARCHAR(20)", nullable=False, default="'a_posto'"),
        Col("needs_review", "BOOLEAN", nullable=False, default="false"),
        Col("counts", "JSONB", nullable=False, default="'{}'::jsonb"),
        Col("findings", "JSONB", nullable=False, default="'[]'::jsonb"),
        Col("checked_at", TZ, nullable=False, default=NOW),
        Col("rechecked_at", TZ),
        Col("review_notified_at", TZ),
    ),
    "document_dependencies": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("check_id", UUID, nullable=False, references="document_checks", ondelete="CASCADE"),
        Col("org_id", UUID, nullable=False, references="organizations", ondelete="CASCADE"),
        Col("position", "INTEGER", nullable=False, default="0"),
        Col("source", "VARCHAR(20)", nullable=False, default="'eurlex'"),
        Col("act", "VARCHAR(300)", nullable=False),
        Col("name", "VARCHAR(300)", nullable=False),
        Col("article", "VARCHAR(100)", nullable=False),
        Col("key", "VARCHAR(100)", nullable=False),
        Col("lang", "VARCHAR(8)", nullable=False, default="'IT'"),
        Col("version", "VARCHAR(300)", nullable=False),
        Col("as_of", "VARCHAR(32)"),
        Col("fingerprint", "VARCHAR(80)", nullable=False),
        Col("official_text", "TEXT", nullable=False),
        Col("cited_as", "JSONB", nullable=False, default="'[]'::jsonb"),
        Col("state", "VARCHAR(20)", nullable=False, default="'current'"),
        Col("changed_at", TZ),
        Col("checked_at", TZ),
        Col("change", "JSONB"),
    ),
    "system_state": (
        Col("key", "VARCHAR(100)", nullable=False, primary_key=True),
        Col("value", "JSONB", nullable=False),
        Col("updated_at", TZ, nullable=False, default=NOW),
    ),
}

# Columns added to tables of earlier revisions.
ADDED_COLUMNS: tuple[tuple[str, Col], ...] = (
    ("users", Col("notify_document_changes", "BOOLEAN", nullable=False, default="true")),
    ("alerts", Col("document_check_id", UUID, references="document_checks", ondelete="CASCADE")),
)

INDEXES: tuple[Ix, ...] = (
    Ix("ix_document_checks_org_checked", "document_checks", ("org_id", "checked_at")),
    Ix("ix_document_checks_client_id", "document_checks", ("client_id",)),
    Ix("ix_document_dependencies_provision", "document_dependencies", ("source", "act", "key")),
    Ix("ix_document_dependencies_check_id", "document_dependencies", ("check_id",)),
    Ix("ix_document_dependencies_org_id", "document_dependencies", ("org_id",)),
    Ix("ix_alerts_document_check_id", "alerts", ("document_check_id",)),
)

# ─── Row-Level Security ──────────────────────────────────────────────────────

_ORG_GUC = "current_setting('app.current_org_id', true)"
_ORG_MATCH = f"org_id::text = {_ORG_GUC}"
_CLIENT_IN_ORG = f"client_id IN (SELECT id FROM clients WHERE org_id::text = {_ORG_GUC})"
_CHECK_IN_ORG = (
    f"document_check_id IN (SELECT id FROM document_checks WHERE org_id::text = {_ORG_GUC})"
)
_ALERT_IN_ORG = f"{_CLIENT_IN_ORG} OR {_CHECK_IN_ORG}"

# Tenant tables of this revision: the policies of ``clients``.
RLS_TABLES: tuple[str, ...] = ("document_checks", "document_dependencies")

# table -> {policy name: CREATE POLICY statement}.
POLICIES: dict[str, dict[str, str]] = {
    table: {
        f"{table}_org_isolation": (
            f"CREATE POLICY {table}_org_isolation ON {table} USING ({_ORG_MATCH})"
        ),
        f"{table}_org_insert": (
            f"CREATE POLICY {table}_org_insert ON {table} FOR INSERT WITH CHECK ({_ORG_MATCH})"
        ),
    }
    for table in RLS_TABLES
}

# The ``alerts`` policies, by name: as this revision leaves them and as 007 made them.
ALERT_POLICIES: dict[str, str] = {
    "alerts_org_isolation": f"CREATE POLICY alerts_org_isolation ON alerts USING ({_ALERT_IN_ORG})",
    "alerts_insert": (
        f"CREATE POLICY alerts_insert ON alerts FOR INSERT WITH CHECK ({_ALERT_IN_ORG})"
    ),
}
ALERT_POLICIES_007: dict[str, str] = {
    "alerts_org_isolation": (
        f"CREATE POLICY alerts_org_isolation ON alerts USING ({_CLIENT_IN_ORG})"
    ),
    "alerts_insert": (
        f"CREATE POLICY alerts_insert ON alerts FOR INSERT WITH CHECK ({_CLIENT_IN_ORG})"
    ),
}

# Under the 007 policies an alert is reachable only through its client: the
# alerts of documents without a client would stay in the table where no tenant
# (and no GDPR erasure) can see them. The downgrade deletes them.
_DELETE_UNREACHABLE_ALERTS = "DELETE FROM alerts WHERE client_id IS NULL"


# ─── Statements (pure) ───────────────────────────────────────────────────────


def _column_ddl(col: Col) -> str:
    ddl = f"{col.name} {col.type}"
    if col.primary_key:
        ddl += " PRIMARY KEY"
    if col.default is not None:
        ddl += f" DEFAULT {col.default}"
    if not col.nullable and not col.primary_key:
        ddl += " NOT NULL"
    if col.references:
        ddl += f" REFERENCES {col.references} (id)"
        if col.ondelete:
            ddl += f" ON DELETE {col.ondelete}"
    return ddl


def _replace_policies(table: str, policies: dict[str, str]) -> list[str]:
    out: list[str] = []
    for name, ddl in policies.items():
        out.append(f"DROP POLICY IF EXISTS {name} ON {table}")
        out.append(ddl)
    return out


def upgrade_statements() -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        body = ",\n    ".join(_column_ddl(c) for c in cols)
        out.append(f"CREATE TABLE IF NOT EXISTS {table} (\n    {body}\n)")
    for table, col in ADDED_COLUMNS:
        out.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {_column_ddl(col)}")
    for ix in INDEXES:
        out.append(f"CREATE INDEX IF NOT EXISTS {ix.name} ON {ix.table} ({', '.join(ix.columns)})")
    for table in RLS_TABLES:
        out.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        out.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        out.extend(_replace_policies(table, POLICIES[table]))
    out.extend(_replace_policies("alerts", ALERT_POLICIES))
    return out


def downgrade_statements() -> list[str]:
    out: list[str] = [_DELETE_UNREACHABLE_ALERTS]
    out.extend(_replace_policies("alerts", ALERT_POLICIES_007))
    for ix in INDEXES:
        if ix.table not in TABLES:
            out.append(f"DROP INDEX IF EXISTS {ix.name}")
    for table, col in reversed(ADDED_COLUMNS):
        out.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col.name}")
    # Children first; a table takes its indexes and policies with it.
    for table in reversed(TABLES):
        out.append(f"DROP TABLE IF EXISTS {table}")
    return out


# ─── Alembic entry points ────────────────────────────────────────────────────


def upgrade() -> None:
    for statement in upgrade_statements():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in downgrade_statements():
        op.execute(sa.text(statement))
