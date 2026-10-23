"""Offline tests for alembic/versions/007_reconcile_schema.py.

The migration is state-driven: pure planning functions turn a ``SchemaState``
(a read-only view of the live schema) into DDL statements. That lets this
suite exercise the decision logic without PostgreSQL by feeding it fake
snapshots of the three historical starting states:

* ``converged``  - a database that already matches the ORM: every phase must
  emit nothing (idempotency);
* ``chain_001``  - the Alembic 001..006 shape (old column names, VARCHAR
  lengths, FK options, dead objects, 002 RLS on users/organizations);
* ``init_db``    - the legacy scripts/init_db.sql shape (missing tables, idx_*
  index names, DESC ordering, strict policies).

The real run against PostgreSQL (upgrade + ``alembic check`` on each starting
state) is the CI ``schema`` job in .github/workflows/ci.yml.
"""

from __future__ import annotations

import copy
import importlib.util
import re
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql as pg

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "007_reconcile_schema.py"


@pytest.fixture(scope="module")
def m():
    """The migration module, loaded from its file (the versions dir is not a package)."""
    spec = importlib.util.spec_from_file_location("migration_007_reconcile_schema", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeState:
    """In-memory ``SchemaState`` built from a snapshot ``{table: {...}}``."""

    def __init__(self, tables: dict[str, dict[str, Any]]) -> None:
        self.tables = tables

    def has_table(self, table: str) -> bool:
        return table in self.tables

    def columns(self, table: str) -> dict[str, dict[str, Any]]:
        return self.tables[table]["columns"]

    def indexes(self, table: str) -> list[dict[str, Any]]:
        return self.tables[table].get("indexes", [])

    def unique_constraints(self, table: str) -> list[dict[str, Any]]:
        return self.tables[table].get("uniques", [])

    def foreign_keys(self, table: str) -> list[dict[str, Any]]:
        return self.tables[table].get("fks", [])

    def policies(self, table: str) -> set[str]:
        return set(self.tables[table].get("policies", ()))

    def row_security(self, table: str) -> tuple[bool, bool]:
        return tuple(self.tables[table].get("rls", (False, False)))

    def max_length(self, table: str, column: str) -> int:
        return self.tables[table].get("max_len", {}).get(column, 0)


def converged_snapshot(m) -> dict[str, dict[str, Any]]:
    """A snapshot of a database that already matches the migration's target."""
    tables: dict[str, dict[str, Any]] = {}
    for table, cols in m.TABLES.items():
        tables[table] = {
            "columns": {
                c.name: {
                    "type": c.type,
                    "nullable": False if c.primary_key else c.nullable,
                    "comment": None,
                }
                for c in cols
            },
            "indexes": [
                {"name": ix.name, "columns": list(ix.columns), "unique": ix.unique, "sorted": False}
                for ix in m.INDEXES
                if ix.table == table
            ],
            "uniques": [
                {
                    "name": uq.name or f"{uq.table}_{'_'.join(uq.columns)}_key",
                    "columns": list(uq.columns),
                }
                for uq in m.UNIQUE_CONSTRAINTS
                if uq.table == table
            ],
            "fks": [
                {
                    "name": f"{fk.table}_{fk.column}_fkey",
                    "columns": [fk.column],
                    "ref_table": fk.ref_table,
                    "ref_columns": [fk.ref_column],
                    "ondelete": fk.ondelete,
                }
                for fk in m.FOREIGN_KEYS
                if fk.table == table
            ],
            "policies": set(m.POLICIES.get(table, {})),
            "rls": (True, True) if table in m.RLS_TABLES else (False, False),
        }
    return tables


def apply_structural_effects(m, snap: dict[str, dict[str, Any]], statements: list[str]) -> None:
    """Mirror on the snapshot what a fresh inspector would see after ``statements``.

    The real ``upgrade()`` re-inspects the database before every phase, so a
    table created by ``plan_tables`` is visible to the index/RLS phases and a
    column dropped by ``plan_drops`` is gone for ``plan_comments``. Only the
    structural statements later phases depend on are simulated.
    """
    for stmt in statements:
        if match := re.match(r"CREATE TABLE IF NOT EXISTS (\w+)", stmt):
            table = match.group(1)
            snap[table] = {
                "columns": {
                    c.name: {
                        "type": c.type,
                        "nullable": False if c.primary_key else c.nullable,
                        "comment": None,
                    }
                    for c in m.TABLES[table]
                },
                "indexes": [],
                "uniques": [],
                "fks": [],
                "policies": set(),
                "rls": (False, False),
            }
        elif match := re.match(r"ALTER TABLE (\w+) RENAME COLUMN (\w+) TO (\w+)$", stmt):
            table, old, new = match.groups()
            snap[table]["columns"][new] = snap[table]["columns"].pop(old)
        elif match := re.match(
            r"ALTER TABLE (\w+) ADD COLUMN IF NOT EXISTS (\w+) (.+?)(?: DEFAULT .+?)?( NOT NULL)?$",
            stmt,
        ):
            table, name, ddl_type, not_null = match.groups()
            snap[table]["columns"][name] = {
                "type": ddl_type,
                "nullable": not_null is None,
                "comment": None,
            }
        elif match := re.match(r"ALTER TABLE (\w+) DROP COLUMN IF EXISTS (\w+)$", stmt):
            table, name = match.groups()
            snap[table]["columns"].pop(name, None)
        elif match := re.match(r"DROP TABLE IF EXISTS (\w+)$", stmt):
            snap.pop(match.group(1), None)


def full_plan(m, snap: dict[str, dict[str, Any]]) -> list[str]:
    """Run every phase in order against the (progressively updated) snapshot."""
    plan: list[str] = []
    for phase in m.PHASES:
        statements = phase(FakeState(snap))
        plan.extend(statements)
        apply_structural_effects(m, snap, statements)
    return plan


# ──────────────────────────────────────────────────────────────────────────
#  Module shape
# ──────────────────────────────────────────────────────────────────────────


def test_revision_chain(m):
    assert m.revision == "007_reconcile_schema"
    assert m.down_revision == "006_lead_download_email_tracking"
    assert [p.__name__ for p in m.PHASES][0] == "plan_renames"
    assert [p.__name__ for p in m.PHASES][-1] == "plan_row_level_security"


def test_downgrade_is_a_documented_no_op(m):
    assert m.downgrade() is None
    assert "no-op" in (m.downgrade.__doc__ or "")


def test_spec_mirrors_the_orm_metadata(m):
    """The inline target spec must be a faithful snapshot of src/db/models.py.

    If a model changes, this fails: either the change belongs in a NEW
    migration (and this spec stays a snapshot of 2026-10-23), or the spec was
    mistyped.
    """
    from src.db.models import Base

    # Objects introduced by later migrations are not part of the 007 snapshot.
    later_tables = {"invites"}  # 008_invites
    later_columns = {("users", "email_verified")}  # 008_invites

    dialect = pg.dialect()
    orm_tables = {name: t for name, t in Base.metadata.tables.items() if name not in later_tables}
    assert set(m.TABLES) == set(orm_tables)

    for table_name, table in orm_tables.items():
        orm_columns = [c for c in table.columns if (table_name, c.name) not in later_columns]
        spec_cols = {c.name: c for c in m.TABLES[table_name]}
        assert list(spec_cols) == [c.name for c in orm_columns], table_name
        for col in orm_columns:
            spec = spec_cols[col.name]
            orm_type = m.normalize_type(str(col.type.compile(dialect=dialect)))
            assert spec.type == orm_type, f"{table_name}.{col.name}"
            assert spec.primary_key == bool(col.primary_key), f"{table_name}.{col.name}"
            expected_nullable = False if col.primary_key else bool(col.nullable)
            assert spec.nullable == expected_nullable, f"{table_name}.{col.name}"

        orm_indexes = {
            (ix.name, tuple(c.name for c in ix.columns), bool(ix.unique)) for ix in table.indexes
        }
        spec_indexes = {
            (ix.name, ix.columns, ix.unique) for ix in m.INDEXES if ix.table == table_name
        }
        assert spec_indexes == orm_indexes, table_name

        orm_uniques = {
            tuple(sorted(c.name for c in con.columns))
            for con in table.constraints
            if type(con).__name__ == "UniqueConstraint"
        }
        spec_uniques = {
            tuple(sorted(uq.columns)) for uq in m.UNIQUE_CONSTRAINTS if uq.table == table_name
        }
        assert spec_uniques == orm_uniques, table_name

        orm_fks = {
            (
                tuple(c.name for c in fk.columns),
                fk.elements[0].column.table.name,
                fk.elements[0].column.name,
                fk.ondelete,
            )
            for fk in table.foreign_key_constraints
        }
        spec_fks = {
            ((fk.column,), fk.ref_table, fk.ref_column, fk.ondelete)
            for fk in m.FOREIGN_KEYS
            if fk.table == table_name
        }
        assert spec_fks == orm_fks, table_name


def test_rls_tables_are_the_tenant_scoped_ones(m):
    assert set(m.RLS_TABLES) == {
        "clients",
        "alerts",
        "assessments",
        "conversations",
        "parent_documents",
    }
    assert set(m.RLS_DISABLED_TABLES) == {"users", "organizations"}
    for table, policies in m.POLICIES.items():
        for name, ddl in policies.items():
            assert ddl.startswith(f"CREATE POLICY {name} ON {table} ")
            # The missing_ok form: a no-org session degrades to "no rows", it
            # does not raise like the strict init_db.sql policies did.
            assert "current_setting('app.current_org_id', true)" in ddl


# ──────────────────────────────────────────────────────────────────────────
#  Idempotency: a converged database needs nothing
# ──────────────────────────────────────────────────────────────────────────


def test_converged_database_needs_no_ddl(m):
    state = FakeState(converged_snapshot(m))
    for phase in m.PHASES:
        assert phase(state) == [], phase.__name__


def test_type_normalisation_treats_synonyms_as_equal(m):
    assert m.normalize_type("character varying(255)") == "VARCHAR(255)"
    assert m.normalize_type("FLOAT") == "DOUBLE PRECISION"
    assert m.normalize_type("timestamptz") == "TIMESTAMP WITH TIME ZONE"
    assert m.normalize_type("VARCHAR( 50 )") == "VARCHAR(50)"
    assert m.normalize_type("TEXT[]") == "TEXT[]"


def test_extra_db_defaults_do_not_trigger_ddl(m):
    """Legacy DEFAULT uuid_generate_v4() / DEFAULT now() are not compared."""
    snap = converged_snapshot(m)
    snap["organizations"]["columns"]["id"]["default"] = "uuid_generate_v4()"
    assert full_plan(m, snap) == []


# ──────────────────────────────────────────────────────────────────────────
#  Starting state 1: the Alembic 001..006 chain
# ──────────────────────────────────────────────────────────────────────────


def chain_001_snapshot(m) -> dict[str, dict[str, Any]]:
    snap = converged_snapshot(m)

    org = snap["organizations"]["columns"]
    org["name"]["type"] = "VARCHAR(200)"
    org["slug"]["type"] = "VARCHAR(200)"
    for name in ("plan", "max_clients", "created_at", "updated_at"):
        org[name]["nullable"] = True

    users = snap["users"]["columns"]
    users["hashed_password"]["type"] = "VARCHAR(255)"
    users["name"].update(type="VARCHAR(200)", nullable=True)

    clients = snap["clients"]["columns"]
    clients["name"]["type"] = "VARCHAR(200)"
    clients["jurisdictions"].update(type="VARCHAR[]", nullable=True)

    regs = snap["regulations"]["columns"]
    for name in ("date_in_force", "full_text_url", "last_amended_at", "updated_at"):
        del regs[name]
    regs["title"]["nullable"] = True
    regs["content_hash"] = {
        "type": "VARCHAR(64)",
        "nullable": True,
        "comment": "SHA-256 of raw_html for change detection",
    }
    regs["version_number"] = {"type": "INTEGER", "nullable": True, "comment": None}
    regs["source"]["comment"] = 'Source: "eurlex" or "normattiva"'
    snap["regulations"]["indexes"] = [
        {"name": "idx_regulations_source", "columns": ["source"], "unique": False, "sorted": False},
        {"name": "idx_regulations_urn", "columns": ["urn"], "unique": False, "sorted": False},
    ]

    amend = snap["amendments"]
    amend["columns"]["discovered_at"] = amend["columns"].pop("detected_at")
    del amend["columns"]["summary"]
    amend["columns"]["original_regulation_id"]["nullable"] = False
    amend["fks"][0]["ondelete"] = "CASCADE"

    alerts = snap["alerts"]
    alerts["columns"]["summary"] = alerts["columns"].pop("description")
    alerts["columns"]["client_id"]["nullable"] = False
    alerts["columns"]["severity"]["nullable"] = True
    alerts["columns"]["actions_required"]["type"] = "VARCHAR[]"
    del alerts["columns"]["is_dismissed"]
    alerts["indexes"] = [
        {
            "name": "idx_alerts_client",
            "columns": ["client_id", "created_at"],
            "unique": False,
            "sorted": False,
        }
    ]

    assess = snap["assessments"]
    assess["columns"]["created_at"] = assess["columns"].pop("assessed_at")
    del assess["columns"]["status"]
    del assess["columns"]["assessed_by"]
    assess["fks"] = [fk for fk in assess["fks"] if fk["columns"] != ["assessed_by"]]

    conv = snap["conversations"]
    for fk in conv["fks"]:
        fk["ondelete"] = "SET NULL" if fk["columns"] == ["client_id"] else "CASCADE"
        fk["name"] = f"conversations_{fk['columns'][0]}_fkey"

    snap["crawl_jobs"]["columns"]["status"]["type"] = "VARCHAR(20)"

    snap["revoked_tokens"] = {
        "columns": {"id": {"type": "UUID", "nullable": False, "comment": None}},
        "indexes": [
            {"name": "idx_revoked_tokens_jti", "columns": ["jti"], "unique": False, "sorted": False}
        ],
    }

    # 002: RLS + policies on users/organizations too; no *_insert policies.
    snap["users"].update(rls=(True, True), policies={"users_org_isolation", "users_org_insert"})
    snap["organizations"].update(rls=(True, True), policies={"organizations_self_only"})
    for table in ("clients", "alerts", "assessments", "conversations"):
        snap[table]["policies"] = {f"{table}_org_isolation"}
    return snap


def test_chain_001_state_is_converged(m):
    plan = full_plan(m, chain_001_snapshot(m))

    # 1. renames come first and are plain RENAME COLUMN statements
    assert plan[:3] == [
        "ALTER TABLE amendments RENAME COLUMN discovered_at TO detected_at",
        "ALTER TABLE alerts RENAME COLUMN summary TO description",
        "ALTER TABLE assessments RENAME COLUMN created_at TO assessed_at",
    ]
    # 2. missing columns are added with the ORM default so existing rows stay valid
    assert (
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS is_dismissed BOOLEAN DEFAULT false NOT NULL"
        in plan
    )
    assert "ALTER TABLE amendments ADD COLUMN IF NOT EXISTS summary TEXT" in plan
    # 3. types: widening VARCHAR has no USING cast, array element change does
    assert "ALTER TABLE users ALTER COLUMN hashed_password TYPE VARCHAR(512)" in plan
    assert (
        "ALTER TABLE clients ALTER COLUMN jurisdictions TYPE TEXT[] USING jurisdictions::TEXT[]"
        in plan
    )
    # 4. nullability: backfill then SET NOT NULL; DROP NOT NULL where the ORM is nullable
    i_backfill = plan.index("UPDATE users SET name = '' WHERE name IS NULL")
    i_not_null = plan.index("ALTER TABLE users ALTER COLUMN name SET NOT NULL")
    assert i_backfill < i_not_null
    assert "ALTER TABLE alerts ALTER COLUMN client_id DROP NOT NULL" in plan
    assert "ALTER TABLE amendments ALTER COLUMN original_regulation_id DROP NOT NULL" in plan
    # 5. foreign keys with a different ON DELETE are recreated
    assert "ALTER TABLE amendments DROP CONSTRAINT amendments_original_regulation_id_fkey" in plan
    assert (
        "ALTER TABLE amendments ADD CONSTRAINT amendments_original_regulation_id_fkey "
        "FOREIGN KEY (original_regulation_id) REFERENCES regulations (id)"
    ) in plan
    assert (
        "ALTER TABLE assessments ADD CONSTRAINT assessments_assessed_by_fkey "
        "FOREIGN KEY (assessed_by) REFERENCES users (id)"
    ) in plan
    assert "ALTER TABLE conversations DROP CONSTRAINT conversations_user_id_fkey" in plan
    # 6. indexes the ORM does not declare go, declared ones are created
    assert "DROP INDEX IF EXISTS idx_regulations_source" in plan
    assert "CREATE INDEX IF NOT EXISTS ix_alerts_severity ON alerts (severity)" in plan
    # 7. dead objects
    assert "DROP TABLE IF EXISTS revoked_tokens" in plan
    assert "ALTER TABLE regulations DROP COLUMN IF EXISTS content_hash" in plan
    # 8. comments the ORM does not declare are dropped (alembic check compares them)
    assert "COMMENT ON COLUMN regulations.source IS NULL" in plan
    assert "COMMENT ON COLUMN regulations.content_hash IS NULL" not in plan  # dropped column
    # 9. RLS: off on users/organizations, canonical policies elsewhere
    assert "DROP POLICY IF EXISTS users_org_isolation ON users" in plan
    assert "ALTER TABLE users NO FORCE ROW LEVEL SECURITY" in plan
    assert "ALTER TABLE users DISABLE ROW LEVEL SECURITY" in plan
    assert "DROP POLICY IF EXISTS organizations_self_only ON organizations" in plan
    assert m.POLICIES["alerts"]["alerts_insert"] in plan
    assert m.POLICIES["clients"]["clients_org_isolation"] not in plan  # already there


# ──────────────────────────────────────────────────────────────────────────
#  Starting state 2: the legacy scripts/init_db.sql
# ──────────────────────────────────────────────────────────────────────────


def init_db_snapshot(m) -> dict[str, dict[str, Any]]:
    snap = converged_snapshot(m)
    for table in ("leads", "parent_documents", "citation_verifications"):
        del snap[table]

    regs = snap["regulations"]
    for name in ("source", "urn", "current_text_url", "versions"):
        del regs["columns"][name]
    regs["uniques"] = [uq for uq in regs["uniques"] if uq["columns"] != ["urn"]]
    regs["indexes"] = [
        {"name": "idx_regulations_celex", "columns": ["celex"], "unique": False, "sorted": False},
        {
            "name": "idx_regulations_framework",
            "columns": ["framework"],
            "unique": False,
            "sorted": False,
        },
    ]
    # init_db.sql: every DEFAULT-ed column is nullable (organizations as a sample)
    for name in ("plan", "max_clients", "created_at", "updated_at"):
        snap["organizations"]["columns"][name]["nullable"] = True

    alerts = snap["alerts"]
    alerts["indexes"] = [
        {
            "name": "idx_alerts_client",
            "columns": ["client_id", "created_at"],
            "unique": False,
            "sorted": True,
        },
        {"name": "idx_alerts_severity", "columns": ["severity"], "unique": False, "sorted": False},
    ]

    # Strict policies, no FORCE, conversations enabled with no policy at all,
    # users/organizations untouched (the production state).
    snap["clients"].update(rls=(True, False), policies={"clients_org_policy"})
    snap["alerts"].update(rls=(True, False), policies={"alerts_org_policy"})
    snap["assessments"].update(rls=(True, False), policies={"assessments_org_policy"})
    snap["conversations"].update(rls=(True, False), policies=set())
    snap["users"].update(rls=(False, False), policies=set())
    snap["organizations"].update(rls=(False, False), policies=set())
    return snap


def test_init_db_state_is_converged(m):
    plan = full_plan(m, init_db_snapshot(m))

    created = [s for s in plan if s.startswith("CREATE TABLE IF NOT EXISTS ")]
    assert sorted(s.split()[5] for s in created) == [
        "citation_verifications",
        "leads",
        "parent_documents",
    ]
    leads_ddl = next(s for s in created if "leads" in s)
    assert "id UUID PRIMARY KEY DEFAULT gen_random_uuid()" in leads_ddl
    assert "source VARCHAR(50) DEFAULT 'codex_download' NOT NULL" in leads_ddl

    assert (
        "ALTER TABLE regulations ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'eurlex' NOT NULL"
        in plan
    )
    assert "ALTER TABLE regulations ADD CONSTRAINT regulations_urn_key UNIQUE (urn)" in plan
    assert (
        "ALTER TABLE parent_documents ADD CONSTRAINT uq_parent_docs_celex_article "
        "UNIQUE (celex, article_number)"
    ) in plan
    # the new tables get their foreign keys / indexes / policies in later phases
    assert "CREATE INDEX IF NOT EXISTS ix_leads_email_created ON leads (email, created_at)" in plan
    assert m.POLICIES["parent_documents"]["parent_documents_read_all"] in plan
    assert "ALTER TABLE parent_documents ENABLE ROW LEVEL SECURITY" in plan

    # legacy idx_* names are replaced by the ORM's ix_* names, DESC index rebuilt
    assert "DROP INDEX IF EXISTS idx_regulations_celex" in plan  # unique constraint covers it
    assert "DROP INDEX IF EXISTS idx_regulations_framework" in plan
    assert "CREATE INDEX IF NOT EXISTS ix_regulations_framework ON regulations (framework)" in plan
    i_drop = plan.index("DROP INDEX IF EXISTS idx_alerts_client")
    i_create = plan.index(
        "CREATE INDEX IF NOT EXISTS idx_alerts_client ON alerts (client_id, created_at)"
    )
    assert i_drop < i_create

    # strict policies go, canonical ones come, FORCE everywhere tenant-scoped
    assert "DROP POLICY IF EXISTS clients_org_policy ON clients" in plan
    assert m.POLICIES["clients"]["clients_org_isolation"] in plan
    assert m.POLICIES["conversations"]["conversations_org_isolation"] in plan
    for table in ("clients", "alerts", "assessments", "conversations"):
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in plan
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" not in plan  # already enabled
    # users / organizations were already RLS-free: no policy / RLS statements there
    for table in ("users", "organizations"):
        assert not [
            s
            for s in plan
            if s.endswith(f" ON {table}")
            or s.startswith(f"ALTER TABLE {table} ")
            and "ROW LEVEL" in s
        ]
    # the organizations defaults are backfilled before SET NOT NULL
    assert plan.index("UPDATE organizations SET plan = 'starter' WHERE plan IS NULL") < plan.index(
        "ALTER TABLE organizations ALTER COLUMN plan SET NOT NULL"
    )


# ──────────────────────────────────────────────────────────────────────────
#  Guards
# ──────────────────────────────────────────────────────────────────────────


def test_varchar_narrowing_refuses_to_lose_data(m):
    snap = converged_snapshot(m)
    snap["organizations"]["columns"]["slug"]["type"] = "VARCHAR(200)"
    snap["organizations"]["max_len"] = {"slug": 150}
    with pytest.raises(RuntimeError, match=r"organizations\.slug.*150 characters"):
        m.plan_types(FakeState(snap))


def test_varchar_narrowing_proceeds_when_data_fits(m):
    snap = converged_snapshot(m)
    snap["organizations"]["columns"]["slug"]["type"] = "VARCHAR(200)"
    snap["organizations"]["max_len"] = {"slug": 60}
    assert m.plan_types(FakeState(snap)) == [
        "ALTER TABLE organizations ALTER COLUMN slug TYPE VARCHAR(100)"
    ]


def test_not_null_without_default_is_tightened_without_backfill(m):
    snap = converged_snapshot(m)
    snap["regulations"]["columns"]["celex"]["nullable"] = True
    assert m.plan_nullability(FakeState(snap)) == [
        "ALTER TABLE regulations ALTER COLUMN celex SET NOT NULL"
    ]


def test_missing_table_phases_skip_absent_tables(m):
    """Column/index/RLS phases never touch a table that does not exist yet."""
    snap = converged_snapshot(m)
    del snap["leads"]
    state = FakeState(snap)
    assert m.plan_columns(state) == []
    assert m.plan_indexes(state) == []
    assert m.plan_row_level_security(state) == []
    assert [s.split()[5] for s in m.plan_tables(state)] == ["leads"]


def test_snapshot_helpers_do_not_mutate_the_spec(m):
    """Sanity: the fake snapshots are deep copies, the spec stays frozen."""
    before = copy.deepcopy(m.TABLES)
    chain_001_snapshot(m)
    init_db_snapshot(m)
    assert before == m.TABLES
