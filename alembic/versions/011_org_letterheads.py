"""Letterheads: what heads the PDFs an organisation hands to its clients.

Revision ID: 011_org_letterheads
Revises: 010_account_security
Create Date: 2026-11-24

Adds
----
- ``org_letterheads``: one row per organisation (the primary key is
  ``org_id``) with the name of the practice, its address, a line of contacts,
  an optional note for the foot of every page and the logo (a PNG or a JPEG,
  checked and encoded again by ``src/reports/letterhead.py``, in ``logo`` with
  its media type in ``logo_type``). Without a row the PDFs carry the name of
  the organisation only. ``updated_by`` is the admin who last changed it.

Row-Level Security
------------------
A tenant table, so it gets what ``clients`` has: ENABLE + FORCE,
``org_letterheads_org_isolation`` on ``org_id`` and ``org_letterheads_org_insert``
for INSERT. A session without an organisation sees no row.

Idempotent
----------
``CREATE TABLE IF NOT EXISTS`` and ``DROP POLICY IF EXISTS`` before every
``CREATE POLICY``, built by pure functions from the inline description below:
tests/test_migration_011.py checks offline that it is what src/db/models.py
declares, and the CI ``schema`` job runs the upgrade on PostgreSQL followed by
``alembic check``, then the downgrade to 006 and the upgrade again.
"""

from dataclasses import dataclass

import sqlalchemy as sa

from alembic import op

revision = "011_org_letterheads"
down_revision = "010_account_security"
branch_labels = None
depends_on = None


# ─── Target shape (snapshot of src/db/models.py at this revision) ────────────
# Kept inline on purpose, as in 007, 009 and 010: a migration must not import
# the live models, whose future edits would silently change what it does.


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


UUID = "UUID"
TZ = "TIMESTAMP WITH TIME ZONE"

TABLES: dict[str, tuple[Col, ...]] = {
    "org_letterheads": (
        Col(
            "org_id",
            UUID,
            nullable=False,
            primary_key=True,
            references="organizations",
            ondelete="CASCADE",
        ),
        Col("name", "VARCHAR(200)", nullable=False),
        Col("address", "VARCHAR(300)"),
        Col("contact", "VARCHAR(200)"),
        Col("footer_note", "VARCHAR(300)"),
        Col("logo", "BYTEA"),
        Col("logo_type", "VARCHAR(20)"),
        Col("updated_by", UUID, references="users", ondelete="SET NULL"),
        Col("updated_at", TZ, nullable=False, default="now()"),
    ),
}

# ─── Row-Level Security ──────────────────────────────────────────────────────

_ORG_MATCH = "org_id::text = current_setting('app.current_org_id', true)"

# Tenant tables of this revision: the policies of ``clients``.
RLS_TABLES: tuple[str, ...] = ("org_letterheads",)

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


def upgrade_statements() -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        body = ",\n    ".join(_column_ddl(c) for c in cols)
        out.append(f"CREATE TABLE IF NOT EXISTS {table} (\n    {body}\n)")
    for table in RLS_TABLES:
        out.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        out.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for name, ddl in POLICIES[table].items():
            out.append(f"DROP POLICY IF EXISTS {name} ON {table}")
            out.append(ddl)
    return out


def downgrade_statements() -> list[str]:
    # A table takes its policies with it.
    return [f"DROP TABLE IF EXISTS {table}" for table in reversed(TABLES)]


# ─── Alembic entry points ────────────────────────────────────────────────────


def upgrade() -> None:
    for statement in upgrade_statements():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in downgrade_statements():
        op.execute(sa.text(statement))
