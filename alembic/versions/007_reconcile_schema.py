"""Reconcile the three historical schema definitions into the ORM shape.

Revision ID: 007_reconcile_schema
Revises: 006_lead_download_email_tracking
Create Date: 2026-10-23

Background
----------
Until this revision the schema was defined in three places that had drifted
apart:

* the ORM (``src/db/models.py``) - what the application actually reads/writes;
* the Alembic chain 001..006 - older column names/types/nullability, an extra
  ``revoked_tokens`` table and four temporal columns on ``regulations`` that no
  code path ever wrote;
* ``scripts/init_db.sql`` - mounted into ``/docker-entrypoint-initdb.d`` by
  docker-compose, so every container-created database was born from it. On such
  a database ``alembic upgrade head`` failed with "relation already exists" and
  the documented workaround was ``alembic stamp head``, which silently skipped
  the tables only the migrations create (``parent_documents``, ``leads``,
  ``citation_verifications``), the 002 Row-Level-Security policies and every
  later column.

From this revision on the ORM is the single source of truth: ``alembic upgrade
head`` builds the schema and CI runs ``alembic check`` against it, so any drift
between models and migrations fails the build (``scripts/init_db.sql`` now only
creates extensions).

How it works
------------
The migration is state-driven and idempotent. It inspects the live database in
successive phases and only emits the DDL needed to reach the ORM shape, so it
works on a database created from 001..006, on one created from the legacy
``init_db.sql`` and stamped, and it is a no-op on a database that already
matches. The planning functions are pure (``SchemaState -> list[str]``) so the
offline test-suite can exercise them against fake snapshots of each starting
state; the CI ``schema`` job runs the real thing against PostgreSQL.

Phases, in order:

1. ``plan_renames``       - 001 column names: ``amendments.discovered_at`` ->
   ``detected_at``, ``alerts.summary`` -> ``description``,
   ``assessments.created_at`` -> ``assessed_at``.
2. ``plan_tables``        - create the missing tables.
3. ``plan_columns``       - add the missing columns (with the ORM defaults so
   existing rows stay valid).
4. ``plan_types``         - align column types (VARCHAR lengths, ``varchar[]``
   -> ``text[]``). Narrowing a VARCHAR is refused with a clear error if a
   stored value would not fit - PostgreSQL would otherwise fail opaquely.
5. ``plan_nullability``   - align NOT NULL, backfilling NULLs with the ORM
   defaults first.
6. ``plan_unique_constraints`` / ``plan_foreign_keys`` - add missing unique
   constraints; recreate foreign keys whose ON DELETE option differs
   (``alembic check`` compares it).
7. ``plan_indexes``       - drop indexes the ORM does not declare (the legacy
   ``idx_*`` names, the redundant 004 indexes, ``idx_alerts_client`` with its
   ``DESC`` ordering) and create the declared ones.
8. ``plan_drops``         - drop ``revoked_tokens`` (token revocation is the
   Redis blacklist in ``src/auth/security.py``; nothing ever wrote this table)
   and the 003 temporal columns on ``regulations`` (that metadata lives in the
   Qdrant payload, see ``src/pipeline.py`` / ``src/nlp/embedding/indexer.py``).
9. ``plan_comments``      - drop the column comments carried by 003/004/005:
   the ORM declares none and ``alembic check`` compares comments.
10. ``plan_row_level_security`` - see below.

Row-Level Security
------------------
Tenant-scoped tables (``clients``, ``alerts``, ``assessments``,
``conversations``) get ENABLE + FORCE and the canonical policies (the 002
names plus the INSERT policies ``scripts/setup_app_role.sql`` used to add);
the strict ``init_db.sql`` policies (``<table>_org_policy``, which raise when
the GUC is unset) are dropped. ``parent_documents`` keeps the 003 policies.

``users`` and ``organizations`` deliberately have NO row-level security. The
production app must connect as the non-superuser ``normaai_app`` role
(``src/api/lifespan.py`` refuses to start otherwise) and the authentication
paths - login, token refresh, ``/auth/me`` and the first half of register -
look rows up on a session with no org context; the 002 policies on these two
tables would return zero rows there and lock everybody out. This was already
the documented stance of ``scripts/setup_app_role.sql`` and the state of the
production database; the migration makes it explicit and consistent. The
``leads``, ``citation_verifications``, ``regulations``, ``amendments`` and
``crawl_jobs`` tables are global and keep no RLS, as before.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

from alembic import op

revision = "007_reconcile_schema"
down_revision = "006_lead_download_email_tracking"
branch_labels = None
depends_on = None

# Child of the "alembic" logger configured in alembic.ini (INFO), so operators
# see every statement this migration decides to run.
log = logging.getLogger("alembic.reconcile")


# ─── Target shape (snapshot of src/db/models.py at this revision) ────────────
# Kept inline on purpose: a migration must not import the live models, whose
# future edits would silently change what this revision does.


@dataclass(frozen=True)
class Col:
    """A column of the target schema.

    ``type`` is the PostgreSQL DDL type exactly as SQLAlchemy compiles and
    reflects it. ``default`` is a SQL expression used as DEFAULT when the
    column is created and as the backfill value when NULLs must be removed.
    """

    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


@dataclass(frozen=True)
class FK:
    table: str
    column: str
    ref_table: str
    ref_column: str = "id"
    ondelete: str | None = None


@dataclass(frozen=True)
class Ix:
    name: str
    table: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True)
class Uq:
    table: str
    columns: tuple[str, ...]
    name: str | None = None  # None -> PostgreSQL convention <table>_<column>_key


UUID = "UUID"
TZ = "TIMESTAMP WITH TIME ZONE"
NOW = "now()"

TABLES: dict[str, tuple[Col, ...]] = {
    "organizations": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("name", "VARCHAR(255)", nullable=False),
        Col("slug", "VARCHAR(100)", nullable=False),
        Col("plan", "VARCHAR(50)", nullable=False, default="'starter'"),
        Col("max_clients", "INTEGER", nullable=False, default="5"),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("updated_at", TZ, nullable=False, default=NOW),
    ),
    "users": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("org_id", UUID, nullable=False),
        Col("email", "VARCHAR(255)", nullable=False),
        Col("name", "VARCHAR(255)", nullable=False, default="''"),
        Col("hashed_password", "VARCHAR(512)", nullable=False, default="''"),
        Col("role", "VARCHAR(50)", nullable=False, default="'member'"),
        Col("is_active", "BOOLEAN", nullable=False, default="true"),
        Col("created_at", TZ, nullable=False, default=NOW),
    ),
    "clients": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("org_id", UUID, nullable=False),
        Col("name", "VARCHAR(255)", nullable=False),
        Col("sector", "VARCHAR(100)"),
        Col("employee_count", "INTEGER"),
        Col("revenue_eur", "BIGINT"),
        Col("jurisdictions", "TEXT[]", nullable=False, default="'{}'::text[]"),
        Col("applicable_frameworks", "TEXT[]", nullable=False, default="'{}'::text[]"),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("updated_at", TZ, nullable=False, default=NOW),
    ),
    "regulations": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("celex", "VARCHAR(50)", nullable=False),
        Col("title", "TEXT", nullable=False, default="''"),
        Col("framework", "VARCHAR(50)", nullable=False, default="''"),
        Col("doc_type", "VARCHAR(50)"),
        Col("date_document", "DATE"),
        Col("date_in_force", "DATE"),
        Col("is_in_force", "BOOLEAN", nullable=False, default="true"),
        Col("full_text_url", "TEXT"),
        Col("raw_html", "TEXT"),
        Col("last_crawled_at", TZ),
        Col("last_amended_at", TZ),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("updated_at", TZ, nullable=False, default=NOW),
        Col("source", "VARCHAR(20)", nullable=False, default="'eurlex'"),
        Col("urn", "VARCHAR(200)"),
        Col("current_text_url", "VARCHAR(500)"),
        Col("versions", "JSONB"),
    ),
    "amendments": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("original_regulation_id", UUID),
        Col("amending_celex", "VARCHAR(50)", nullable=False),
        Col("amending_title", "TEXT"),
        Col("amendment_date", "DATE"),
        Col("summary", "TEXT"),
        Col("detected_at", TZ, nullable=False, default=NOW),
    ),
    "alerts": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("client_id", UUID),
        Col("regulation_id", UUID),
        Col("severity", "VARCHAR(20)", nullable=False, default="'info'"),
        Col("framework", "VARCHAR(50)", nullable=False, default="''"),
        Col("title", "VARCHAR(500)", nullable=False, default="''"),
        Col("description", "TEXT", nullable=False, default="''"),
        Col("actions_required", "TEXT[]"),
        Col("deadline", "DATE"),
        Col("is_read", "BOOLEAN", nullable=False, default="false"),
        Col("is_dismissed", "BOOLEAN", nullable=False, default="false"),
        Col("created_at", TZ, nullable=False, default=NOW),
    ),
    "assessments": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("client_id", UUID, nullable=False),
        Col("framework", "VARCHAR(50)", nullable=False),
        Col("overall_score", "DOUBLE PRECISION"),
        Col("status", "VARCHAR(50)", nullable=False, default="'in_progress'"),
        Col("gaps", "JSONB", nullable=False, default="'{}'::jsonb"),
        Col("recommendations", "JSONB", nullable=False, default="'{}'::jsonb"),
        Col("assessed_at", TZ, nullable=False, default=NOW),
        Col("assessed_by", UUID),
    ),
    "conversations": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("client_id", UUID),
        Col("user_id", UUID, nullable=False),
        Col("messages", "JSONB", nullable=False, default="'[]'::jsonb"),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("updated_at", TZ, nullable=False, default=NOW),
    ),
    "crawl_jobs": (
        Col("id", UUID, nullable=False, primary_key=True),
        Col("job_type", "VARCHAR(50)", nullable=False),
        Col("status", "VARCHAR(50)", nullable=False, default="'pending'"),
        Col("regulations_processed", "INTEGER", nullable=False, default="0"),
        Col("amendments_found", "INTEGER", nullable=False, default="0"),
        Col("error_message", "TEXT"),
        Col("started_at", TZ),
        Col("completed_at", TZ),
        Col("created_at", TZ, nullable=False, default=NOW),
    ),
    "citation_verifications": (
        Col("id", UUID, nullable=False, primary_key=True, default="gen_random_uuid()"),
        Col("reference", "VARCHAR(300)", nullable=False),
        Col("reference_type", "VARCHAR(20)", nullable=False),
        Col("verified", "BOOLEAN", nullable=False, default="false"),
        Col("is_current", "BOOLEAN", nullable=False, default="true"),
        Col("source", "VARCHAR(20)", nullable=False),
        Col("url", "VARCHAR(500)"),
        Col("last_checked_at", TZ, nullable=False, default=NOW),
        Col("created_at", TZ, nullable=False, default=NOW),
    ),
    "leads": (
        Col("id", UUID, nullable=False, primary_key=True, default="gen_random_uuid()"),
        Col("email", "VARCHAR(255)", nullable=False),
        Col("org_name", "VARCHAR(255)"),
        Col("role", "VARCHAR(100)"),
        Col("source", "VARCHAR(50)", nullable=False, default="'codex_download'"),
        Col("ip_address", "VARCHAR(45)"),
        Col("user_agent", "VARCHAR(500)"),
        Col("referer", "VARCHAR(500)"),
        Col("status", "VARCHAR(50)", nullable=False, default="'new'"),
        Col("notes", "TEXT"),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("downloaded_at", TZ),
        Col("download_count", "INTEGER", nullable=False, default="0"),
        Col("last_email_sent_at", TZ),
        Col("email_error", "TEXT"),
    ),
    "parent_documents": (
        Col("id", UUID, nullable=False, primary_key=True, default="gen_random_uuid()"),
        Col("celex", "VARCHAR(20)", nullable=False),
        Col("framework", "VARCHAR(50)", nullable=False),
        Col("article_number", "VARCHAR(50)"),
        Col("section_title", "VARCHAR(500)"),
        Col("full_text", "TEXT", nullable=False),
        Col("content_hash", "VARCHAR(64)", nullable=False),
        Col("chunk_ids", "TEXT[]"),
        Col("created_at", TZ, nullable=False, default=NOW),
        Col("updated_at", TZ, nullable=False, default=NOW),
    ),
}

COLUMN_RENAMES: tuple[tuple[str, str, str], ...] = (
    ("amendments", "discovered_at", "detected_at"),
    ("alerts", "summary", "description"),
    ("assessments", "created_at", "assessed_at"),
)

FOREIGN_KEYS: tuple[FK, ...] = (
    FK("users", "org_id", "organizations", ondelete="CASCADE"),
    FK("clients", "org_id", "organizations", ondelete="CASCADE"),
    FK("amendments", "original_regulation_id", "regulations"),
    FK("alerts", "client_id", "clients", ondelete="CASCADE"),
    FK("alerts", "regulation_id", "regulations"),
    FK("assessments", "client_id", "clients", ondelete="CASCADE"),
    FK("assessments", "assessed_by", "users"),
    FK("conversations", "client_id", "clients"),
    FK("conversations", "user_id", "users"),
)

UNIQUE_CONSTRAINTS: tuple[Uq, ...] = (
    Uq("organizations", ("slug",)),
    Uq("users", ("email",)),
    Uq("regulations", ("celex",)),
    Uq("regulations", ("urn",)),
    Uq("parent_documents", ("celex", "article_number"), name="uq_parent_docs_celex_article"),
)

INDEXES: tuple[Ix, ...] = (
    Ix("ix_regulations_framework", "regulations", ("framework",)),
    Ix("ix_alerts_severity", "alerts", ("severity",)),
    Ix("idx_alerts_client", "alerts", ("client_id", "created_at")),
    Ix("idx_assessments_client", "assessments", ("client_id", "framework")),
    Ix("ix_leads_email", "leads", ("email",)),
    Ix("ix_leads_created_at", "leads", ("created_at",)),
    Ix("ix_leads_email_created", "leads", ("email", "created_at")),
    Ix("idx_parent_docs_celex", "parent_documents", ("celex",)),
    Ix("idx_parent_docs_framework", "parent_documents", ("framework",)),
    Ix("idx_parent_docs_article", "parent_documents", ("celex", "article_number")),
)

DEAD_TABLES: tuple[str, ...] = ("revoked_tokens",)
DEAD_COLUMNS: dict[str, tuple[str, ...]] = {
    "regulations": ("content_hash", "superseded_by", "effective_date", "version_number"),
}

# ─── Row-Level Security ──────────────────────────────────────────────────────

_ORG_GUC = "current_setting('app.current_org_id', true)"
_CLIENT_IN_ORG = f"client_id IN (SELECT id FROM clients WHERE org_id::text = {_ORG_GUC})"
_USER_IN_ORG = f"user_id IN (SELECT id FROM users WHERE org_id::text = {_ORG_GUC})"
_GUC_IS_SET = f"({_ORG_GUC} IS NOT NULL AND {_ORG_GUC} <> '')"

# table -> {policy name: CREATE POLICY statement}. Idempotency is by name: a
# policy that exists is left alone, a missing one is created.
POLICIES: dict[str, dict[str, str]] = {
    "clients": {
        "clients_org_isolation": (
            f"CREATE POLICY clients_org_isolation ON clients USING (org_id::text = {_ORG_GUC})"
        ),
        "clients_org_insert": (
            "CREATE POLICY clients_org_insert ON clients FOR INSERT "
            f"WITH CHECK (org_id::text = {_ORG_GUC})"
        ),
    },
    "alerts": {
        "alerts_org_isolation": (
            f"CREATE POLICY alerts_org_isolation ON alerts USING ({_CLIENT_IN_ORG})"
        ),
        "alerts_insert": (
            f"CREATE POLICY alerts_insert ON alerts FOR INSERT WITH CHECK ({_CLIENT_IN_ORG})"
        ),
    },
    "assessments": {
        "assessments_org_isolation": (
            f"CREATE POLICY assessments_org_isolation ON assessments USING ({_CLIENT_IN_ORG})"
        ),
        "assessments_insert": (
            "CREATE POLICY assessments_insert ON assessments FOR INSERT "
            f"WITH CHECK ({_CLIENT_IN_ORG})"
        ),
    },
    "conversations": {
        "conversations_org_isolation": (
            f"CREATE POLICY conversations_org_isolation ON conversations USING ({_USER_IN_ORG})"
        ),
        "conversations_insert": (
            "CREATE POLICY conversations_insert ON conversations FOR INSERT "
            f"WITH CHECK ({_USER_IN_ORG})"
        ),
    },
    "parent_documents": {
        "parent_documents_read_all": (
            "CREATE POLICY parent_documents_read_all ON parent_documents FOR SELECT "
            f"USING {_GUC_IS_SET}"
        ),
        "parent_documents_write": (
            "CREATE POLICY parent_documents_write ON parent_documents FOR ALL "
            f"USING {_GUC_IS_SET} WITH CHECK {_GUC_IS_SET}"
        ),
    },
}

# Tables that must have RLS enabled + forced (the keys of POLICIES).
RLS_TABLES: tuple[str, ...] = tuple(POLICIES)

# Tables where RLS must be OFF (see the module docstring).
RLS_DISABLED_TABLES: tuple[str, ...] = ("users", "organizations")

# Policies from init_db.sql / 002 / setup_app_role.sql that are superseded.
LEGACY_POLICIES: dict[str, tuple[str, ...]] = {
    "clients": ("clients_org_policy",),
    "alerts": ("alerts_org_policy",),
    "assessments": ("assessments_org_policy",),
    "conversations": ("conversations_org_policy",),
    "users": ("users_org_isolation", "users_org_insert"),
    "organizations": ("organizations_self_only", "organizations_insert"),
}


# ─── Schema state abstraction ────────────────────────────────────────────────


class SchemaState(Protocol):
    """Read-only view of the live schema consumed by the planning functions."""

    def has_table(self, table: str) -> bool: ...

    def columns(self, table: str) -> dict[str, dict[str, Any]]:
        """``{name: {"type": ddl, "nullable": bool, "comment": str | None}}``."""
        ...

    def indexes(self, table: str) -> list[dict[str, Any]]:
        """Non-constraint indexes: ``{"name", "columns", "unique", "sorted"}``."""
        ...

    def unique_constraints(self, table: str) -> list[dict[str, Any]]:
        """``{"name", "columns"}`` per unique constraint."""
        ...

    def foreign_keys(self, table: str) -> list[dict[str, Any]]:
        """``{"name", "columns", "ref_table", "ref_columns", "ondelete"}`` per FK."""
        ...

    def policies(self, table: str) -> set[str]:
        """Names of the row-level-security policies defined on the table."""
        ...

    def row_security(self, table: str) -> tuple[bool, bool]:
        """``(enabled, forced)`` row-level-security flags of the table."""
        ...

    def max_length(self, table: str, column: str) -> int:
        """Length of the longest stored value (0 when the table is empty)."""
        ...


_TYPE_SYNONYMS = {
    "CHARACTER VARYING": "VARCHAR",
    "FLOAT": "DOUBLE PRECISION",
    "TIMESTAMPTZ": TZ,
    "TIMESTAMP WITH TIME ZONE": TZ,
    "INT": "INTEGER",
    "INT4": "INTEGER",
    "INT8": "BIGINT",
    "BOOL": "BOOLEAN",
}


def normalize_type(ddl: str) -> str:
    """Canonical spelling of a PostgreSQL type so reflected and target compare."""
    text = " ".join(ddl.upper().split())
    text = re.sub(r"\s*\(\s*(\d+)\s*\)", r"(\1)", text)
    base, length = _split_length(text)
    base = _TYPE_SYNONYMS.get(base, base)
    return f"{base}({length})" if length is not None else base


def _split_length(ddl: str) -> tuple[str, int | None]:
    match = re.fullmatch(r"(.+?)\((\d+)\)", ddl)
    if match is None:
        return ddl, None
    return match.group(1), int(match.group(2))


class LiveState:
    """``SchemaState`` backed by a SQLAlchemy connection (PostgreSQL)."""

    def __init__(self, connection: sa.engine.Connection) -> None:
        self._conn = connection
        self._inspector = sa.inspect(connection)
        self._dialect = pg.dialect()

    def has_table(self, table: str) -> bool:
        return self._inspector.has_table(table)

    def columns(self, table: str) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for col in self._inspector.get_columns(table):
            out[col["name"]] = {
                "type": normalize_type(str(col["type"].compile(dialect=self._dialect))),
                "nullable": bool(col.get("nullable", True)),
                "comment": col.get("comment"),
            }
        return out

    def indexes(self, table: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for ix in self._inspector.get_indexes(table):
            name = ix.get("name")
            # Indexes that back a UNIQUE/PRIMARY KEY constraint belong to the
            # constraint, not to this phase.
            if not name or ix.get("duplicates_constraint") or name.endswith("_pkey"):
                continue
            out.append(
                {
                    "name": name,
                    "columns": [c for c in ix.get("column_names", []) if c is not None],
                    "unique": bool(ix.get("unique")),
                    "sorted": bool(ix.get("column_sorting")),
                }
            )
        return out

    def unique_constraints(self, table: str) -> list[dict[str, Any]]:
        return [
            {"name": uq["name"], "columns": list(uq["column_names"])}
            for uq in self._inspector.get_unique_constraints(table)
        ]

    def foreign_keys(self, table: str) -> list[dict[str, Any]]:
        return [
            {
                "name": fk["name"],
                "columns": list(fk["constrained_columns"]),
                "ref_table": fk["referred_table"],
                "ref_columns": list(fk["referred_columns"]),
                "ondelete": (fk.get("options") or {}).get("ondelete"),
            }
            for fk in self._inspector.get_foreign_keys(table)
        ]

    def policies(self, table: str) -> set[str]:
        rows = self._conn.execute(
            sa.text(
                "SELECT policyname FROM pg_policies "
                "WHERE schemaname = current_schema() AND tablename = :t"
            ),
            {"t": table},
        )
        return {row[0] for row in rows}

    def row_security(self, table: str) -> tuple[bool, bool]:
        row = self._conn.execute(
            sa.text(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = current_schema() AND c.relname = :t"
            ),
            {"t": table},
        ).first()
        if row is None:
            return (False, False)
        return (bool(row[0]), bool(row[1]))

    def max_length(self, table: str, column: str) -> int:
        value = self._conn.execute(
            sa.text(f"SELECT COALESCE(MAX(LENGTH({column})), 0) FROM {table}")
        ).scalar()
        return int(value or 0)


# ─── Planning phases (pure: SchemaState -> DDL statements) ───────────────────


def plan_renames(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table, old, new in COLUMN_RENAMES:
        if not state.has_table(table):
            continue
        cols = state.columns(table)
        if old in cols and new not in cols:
            out.append(f"ALTER TABLE {table} RENAME COLUMN {old} TO {new}")
    return out


def _column_ddl(col: Col) -> str:
    ddl = f"{col.name} {col.type}"
    if col.primary_key:
        ddl += " PRIMARY KEY"
    if col.default is not None:
        ddl += f" DEFAULT {col.default}"
    if not col.nullable and not col.primary_key:
        ddl += " NOT NULL"
    return ddl


def plan_tables(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        if state.has_table(table):
            continue
        body = ",\n    ".join(_column_ddl(c) for c in cols)
        out.append(f"CREATE TABLE IF NOT EXISTS {table} (\n    {body}\n)")
    return out


def plan_columns(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        if not state.has_table(table):
            continue
        existing = state.columns(table)
        for col in cols:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col.name} {col.type}"
            if col.default is not None:
                ddl += f" DEFAULT {col.default}"
                if not col.nullable:
                    ddl += " NOT NULL"
            # A NOT NULL column without a default is added nullable here and
            # tightened by plan_nullability, which fails loudly if rows exist.
            out.append(ddl)
    return out


def _check_varchar_narrowing(state: SchemaState, table: str, col: Col, current: str) -> None:
    cur_base, cur_len = _split_length(current)
    new_base, new_len = _split_length(col.type)
    if cur_base != "VARCHAR" or new_base != "VARCHAR" or cur_len is None or new_len is None:
        return
    if new_len >= cur_len:
        return
    longest = state.max_length(table, col.name)
    if longest > new_len:
        raise RuntimeError(
            f"Cannot narrow {table}.{col.name} from VARCHAR({cur_len}) to VARCHAR({new_len}): "
            f"a stored value is {longest} characters long. Shorten the data, then re-run "
            "`alembic upgrade head`."
        )


def plan_types(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        if not state.has_table(table):
            continue
        existing = state.columns(table)
        for col in cols:
            info = existing.get(col.name)
            if info is None:
                continue
            current = normalize_type(info["type"])
            if current == col.type:
                continue
            _check_varchar_narrowing(state, table, col, current)
            ddl = f"ALTER TABLE {table} ALTER COLUMN {col.name} TYPE {col.type}"
            # Only cast when the base type changes (varchar[] -> text[]). A
            # USING cast between VARCHAR lengths would silently truncate data.
            if _split_length(current)[0] != _split_length(col.type)[0]:
                ddl += f" USING {col.name}::{col.type}"
            out.append(ddl)
    return out


def plan_nullability(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table, cols in TABLES.items():
        if not state.has_table(table):
            continue
        existing = state.columns(table)
        for col in cols:
            info = existing.get(col.name)
            if info is None or col.primary_key:
                continue
            if info["nullable"] and not col.nullable:
                if col.default is not None:
                    out.append(
                        f"UPDATE {table} SET {col.name} = {col.default} WHERE {col.name} IS NULL"
                    )
                out.append(f"ALTER TABLE {table} ALTER COLUMN {col.name} SET NOT NULL")
            elif not info["nullable"] and col.nullable:
                out.append(f"ALTER TABLE {table} ALTER COLUMN {col.name} DROP NOT NULL")
    return out


def plan_unique_constraints(state: SchemaState) -> list[str]:
    out: list[str] = []
    for uq in UNIQUE_CONSTRAINTS:
        if not state.has_table(uq.table):
            continue
        wanted = sorted(uq.columns)
        if any(sorted(c["columns"]) == wanted for c in state.unique_constraints(uq.table)):
            continue
        name = uq.name or f"{uq.table}_{'_'.join(uq.columns)}_key"
        out.append(f"ALTER TABLE {uq.table} ADD CONSTRAINT {name} UNIQUE ({', '.join(uq.columns)})")
    return out


def _norm_ondelete(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.upper()
    return None if value == "NO ACTION" else value


def plan_foreign_keys(state: SchemaState) -> list[str]:
    out: list[str] = []
    for fk in FOREIGN_KEYS:
        if not state.has_table(fk.table):
            continue
        same_target = [
            c
            for c in state.foreign_keys(fk.table)
            if c["columns"] == [fk.column]
            and c["ref_table"] == fk.ref_table
            and c["ref_columns"] == [fk.ref_column]
        ]
        if any(_norm_ondelete(c["ondelete"]) == _norm_ondelete(fk.ondelete) for c in same_target):
            continue
        for c in same_target:  # same columns, different ON DELETE: recreate
            out.append(f"ALTER TABLE {fk.table} DROP CONSTRAINT {c['name']}")
        ddl = (
            f"ALTER TABLE {fk.table} ADD CONSTRAINT {fk.table}_{fk.column}_fkey "
            f"FOREIGN KEY ({fk.column}) REFERENCES {fk.ref_table} ({fk.ref_column})"
        )
        if fk.ondelete:
            ddl += f" ON DELETE {fk.ondelete}"
        out.append(ddl)
    return out


def _index_matches(ix: Ix, reflected: dict[str, Any]) -> bool:
    return (
        list(ix.columns) == list(reflected["columns"])
        and bool(ix.unique) == bool(reflected["unique"])
        and not reflected.get("sorted")
    )


def plan_indexes(state: SchemaState) -> list[str]:
    out: list[str] = []
    wanted_by_table: dict[str, dict[str, Ix]] = {}
    for ix in INDEXES:
        wanted_by_table.setdefault(ix.table, {})[ix.name] = ix
    for table in TABLES:
        if not state.has_table(table):
            continue
        wanted = wanted_by_table.get(table, {})
        satisfied: set[str] = set()
        for reflected in state.indexes(table):
            ix = wanted.get(reflected["name"])
            if ix is not None and _index_matches(ix, reflected):
                satisfied.add(ix.name)
                continue
            # Not declared by the ORM, or declared with a different definition
            # (e.g. the legacy ``created_at DESC`` ordering): rebuild.
            out.append(f"DROP INDEX IF EXISTS {reflected['name']}")
        for name, ix in wanted.items():
            if name in satisfied:
                continue
            unique = "UNIQUE " if ix.unique else ""
            out.append(
                f"CREATE {unique}INDEX IF NOT EXISTS {name} ON {table} ({', '.join(ix.columns)})"
            )
    return out


def plan_drops(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table in DEAD_TABLES:
        if state.has_table(table):
            out.append(f"DROP TABLE IF EXISTS {table}")
    for table, cols in DEAD_COLUMNS.items():
        if not state.has_table(table):
            continue
        existing = state.columns(table)
        for name in cols:
            if name in existing:
                out.append(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {name}")
    return out


def plan_comments(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table in TABLES:
        if not state.has_table(table):
            continue
        for name, info in state.columns(table).items():
            if info.get("comment"):
                out.append(f"COMMENT ON COLUMN {table}.{name} IS NULL")
    return out


def plan_row_level_security(state: SchemaState) -> list[str]:
    out: list[str] = []
    for table in RLS_DISABLED_TABLES:
        if not state.has_table(table):
            continue
        present = state.policies(table)
        for name in LEGACY_POLICIES.get(table, ()):
            if name in present:
                out.append(f"DROP POLICY IF EXISTS {name} ON {table}")
        enabled, forced = state.row_security(table)
        if forced:
            out.append(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        if enabled:
            out.append(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    for table in RLS_TABLES:
        if not state.has_table(table):
            continue
        present = state.policies(table)
        for name in LEGACY_POLICIES.get(table, ()):
            if name in present:
                out.append(f"DROP POLICY IF EXISTS {name} ON {table}")
        for name, ddl in POLICIES[table].items():
            if name not in present:
                out.append(ddl)
        enabled, forced = state.row_security(table)
        if not enabled:
            out.append(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        if not forced:
            out.append(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    return out


PHASES = (
    plan_renames,
    plan_tables,
    plan_columns,
    plan_types,
    plan_nullability,
    plan_unique_constraints,
    plan_foreign_keys,
    plan_indexes,
    plan_drops,
    plan_comments,
    plan_row_level_security,
)


# ─── Alembic entry points ────────────────────────────────────────────────────


def upgrade() -> None:
    connection = op.get_bind()
    for phase in PHASES:
        # A fresh inspector per phase: each phase must see what the previous
        # ones changed (SQLAlchemy caches reflection per Inspector instance).
        for statement in phase(LiveState(connection)):
            log.info("%s: %s", phase.__name__, statement.splitlines()[0])
            op.execute(sa.text(statement))


def downgrade() -> None:
    """Intentionally a no-op.

    This revision does not add a feature that can be taken back: it converges
    three divergent starting states onto the ORM shape, and the ORM at
    revision 006 was already this shape (the application never ran against
    the 001..006 column names). Reverting would mean choosing one of the
    legacy states to restore, which is not meaningful; the schema is left as
    it is and ``alembic_version`` simply moves back to 006.
    """
