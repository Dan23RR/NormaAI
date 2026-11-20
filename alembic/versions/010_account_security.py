"""Account security: staff flag, password reset link, ended sessions.

Revision ID: 010_account_security
Revises: 009_document_checks
Create Date: 2026-11-18

Adds four columns to ``users``:

- ``is_staff`` (bool, NOT NULL, default false): NormaAI personnel. Set only
  from the command line (``scripts/staff.py grant``), honoured only on a
  verified email. No account is staff after the upgrade: before this revision
  staff was a list of addresses in the settings, matched against the token,
  and those addresses are granted again with the script.
- ``password_reset_token_hash`` (VARCHAR(64)) and ``password_reset_expires_at``
  (timestamptz): the one pending password-reset link of the account, as the
  SHA-256 of its secret, and its expiry.
- ``sessions_revoked_at`` (timestamptz): every token issued up to this instant
  is refused (a password reset or staff ending the sessions sets it).

No index and no row-level security: ``users`` has none by design (migration
007), and these columns are read by primary key.

Idempotent
----------
``ADD COLUMN IF NOT EXISTS`` / ``DROP COLUMN IF EXISTS``, built by pure
functions from the inline description below: tests/test_migration_010.py
checks offline that it is what src/db/models.py declares, and the CI ``schema``
job runs the upgrade on PostgreSQL followed by ``alembic check``, then the
downgrade to 006 and the upgrade again.
"""

from dataclasses import dataclass

import sqlalchemy as sa

from alembic import op

revision = "010_account_security"
down_revision = "009_document_checks"
branch_labels = None
depends_on = None


# ─── Target shape (snapshot of src/db/models.py at this revision) ────────────
# Kept inline on purpose, as in 007 and 009: a migration must not import the
# live models, whose future edits would silently change what this revision does.


@dataclass(frozen=True)
class Col:
    """A column: ``type`` is the PostgreSQL DDL type as SQLAlchemy compiles it."""

    name: str
    type: str
    nullable: bool = True
    default: str | None = None  # SQL expression


TZ = "TIMESTAMP WITH TIME ZONE"

TABLE = "users"
ADDED_COLUMNS: tuple[Col, ...] = (
    Col("is_staff", "BOOLEAN", nullable=False, default="false"),
    Col("password_reset_token_hash", "VARCHAR(64)"),
    Col("password_reset_expires_at", TZ),
    Col("sessions_revoked_at", TZ),
)


# ─── Statements (pure) ───────────────────────────────────────────────────────


def _column_ddl(col: Col) -> str:
    ddl = f"{col.name} {col.type}"
    if col.default is not None:
        ddl += f" DEFAULT {col.default}"
    if not col.nullable:
        ddl += " NOT NULL"
    return ddl


def upgrade_statements() -> list[str]:
    return [f"ALTER TABLE {TABLE} ADD COLUMN IF NOT EXISTS {_column_ddl(c)}" for c in ADDED_COLUMNS]


def downgrade_statements() -> list[str]:
    return [f"ALTER TABLE {TABLE} DROP COLUMN IF EXISTS {c.name}" for c in reversed(ADDED_COLUMNS)]


# ─── Alembic entry points ────────────────────────────────────────────────────


def upgrade() -> None:
    for statement in upgrade_statements():
        op.execute(sa.text(statement))


def downgrade() -> None:
    for statement in downgrade_statements():
        op.execute(sa.text(statement))
