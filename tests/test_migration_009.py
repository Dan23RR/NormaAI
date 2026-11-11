"""Offline tests for alembic/versions/009_document_checks.py.

The migration builds its SQL with pure functions from an inline description
of the tables. Without PostgreSQL this suite checks that:

* the description is what src/db/models.py declares (columns in order, types as
  the PostgreSQL dialect compiles them, nullability, foreign keys, indexes), so
  ``alembic check`` finds nothing to do after the upgrade;
* every statement can run twice (``IF NOT EXISTS``, ``DROP POLICY IF EXISTS``
  before ``CREATE POLICY``);
* the two tenant tables get the row-level security of ``clients``, and the
  ``alerts`` policies of 007 come back unchanged on downgrade.

The real run (upgrade, ``alembic check``, downgrade to 006 and up again) is the
CI ``schema`` job in .github/workflows/ci.yml.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql as pg

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(filename: str):
    spec = importlib.util.spec_from_file_location(f"migration_{filename[:3]}", VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def m():
    """The migration module, loaded from its file (the versions dir is not a package)."""
    return _load("009_document_checks.py")


@pytest.fixture(scope="module")
def m007():
    return _load("007_reconcile_schema.py")


def test_revision_chain(m):
    assert m.revision == "009_document_checks"
    assert m.down_revision == "008_invites"
    # alembic_version.version_num is VARCHAR(32)
    assert len(m.revision) <= 32


def test_new_tables_mirror_the_orm_metadata(m, m007):
    from src.db.models import Base

    dialect = pg.dialect()
    for table_name, spec_cols in m.TABLES.items():
        table = Base.metadata.tables[table_name]
        assert [c.name for c in spec_cols] == [c.name for c in table.columns], table_name
        for spec, col in zip(spec_cols, table.columns, strict=True):
            where = f"{table_name}.{col.name}"
            assert spec.type == m007.normalize_type(str(col.type.compile(dialect=dialect))), where
            assert spec.primary_key == bool(col.primary_key), where
            assert spec.nullable == (False if col.primary_key else bool(col.nullable)), where

        orm_fks = {
            (fk.columns[0].name, fk.elements[0].column.table.name, fk.ondelete)
            for fk in table.foreign_key_constraints
        }
        assert all(fk.elements[0].column.name == "id" for fk in table.foreign_key_constraints)
        spec_fks = {(c.name, c.references, c.ondelete) for c in spec_cols if c.references}
        assert spec_fks == orm_fks, table_name

        orm_indexes = {
            (ix.name, tuple(c.name for c in ix.columns), bool(ix.unique)) for ix in table.indexes
        }
        spec_indexes = {(ix.name, ix.columns, False) for ix in m.INDEXES if ix.table == table_name}
        assert spec_indexes == orm_indexes, table_name


def test_added_columns_mirror_the_orm_metadata(m, m007):
    from src.db.models import Base

    dialect = pg.dialect()
    for table_name, spec in m.ADDED_COLUMNS:
        table = Base.metadata.tables[table_name]
        col = table.columns[spec.name]
        where = f"{table_name}.{spec.name}"
        assert spec.type == m007.normalize_type(str(col.type.compile(dialect=dialect))), where
        assert spec.nullable == bool(col.nullable), where
        fks = [fk for fk in table.foreign_key_constraints if fk.columns[0].name == spec.name]
        if spec.references:
            assert len(fks) == 1, where
            assert fks[0].elements[0].column.table.name == spec.references
            assert fks[0].elements[0].column.name == "id"
            assert fks[0].ondelete == spec.ondelete
        else:
            assert fks == [], where
        # A NOT NULL column added to a table with rows needs a default.
        assert spec.nullable or spec.default is not None, where

        orm_indexes = {
            (ix.name, tuple(c.name for c in ix.columns))
            for ix in table.indexes
            if spec.name in [c.name for c in ix.columns]
        }
        spec_indexes = {
            (ix.name, ix.columns)
            for ix in m.INDEXES
            if ix.table == table_name and spec.name in ix.columns
        }
        assert spec_indexes == orm_indexes, where


def test_every_orm_table_has_a_migration(m, m007):
    """A model added without a migration would fail ``alembic check`` in CI: fail here first."""
    from src.db.models import Base

    known = set(m007.TABLES) | {"invites"} | set(m.TABLES)
    assert set(Base.metadata.tables) == known


def test_upgrade_statements_can_run_twice(m):
    statements = m.upgrade_statements()
    for position, statement in enumerate(statements):
        if statement.startswith("CREATE TABLE"):
            assert statement.startswith("CREATE TABLE IF NOT EXISTS "), statement
        elif statement.startswith("CREATE INDEX"):
            assert statement.startswith("CREATE INDEX IF NOT EXISTS "), statement
        elif " ADD COLUMN " in statement:
            assert " ADD COLUMN IF NOT EXISTS " in statement, statement
        elif statement.startswith("CREATE POLICY"):
            name, table = re.match(r"CREATE POLICY (\w+) ON (\w+) ", statement).groups()
            assert statements[position - 1] == f"DROP POLICY IF EXISTS {name} ON {table}"
        else:
            # ENABLE / FORCE are idempotent by nature; nothing else is expected.
            assert re.fullmatch(
                r"(ALTER TABLE \w+ (ENABLE|FORCE) ROW LEVEL SECURITY|DROP POLICY IF EXISTS \w+ ON \w+)",
                statement,
            ), statement


def test_upgrade_order(m):
    statements = m.upgrade_statements()

    def index_of(fragment: str) -> int:
        return next(i for i, s in enumerate(statements) if fragment in s)

    # A table before what references it, columns before their indexes, the
    # table of the alerts' new way in before the policy that reads it.
    assert index_of("CREATE TABLE IF NOT EXISTS document_checks") < index_of(
        "CREATE TABLE IF NOT EXISTS document_dependencies"
    )
    assert index_of("CREATE TABLE IF NOT EXISTS document_checks") < index_of(
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS document_check_id"
    )
    assert index_of("ADD COLUMN IF NOT EXISTS document_check_id") < index_of(
        "CREATE INDEX IF NOT EXISTS ix_alerts_document_check_id"
    )
    assert index_of("ADD COLUMN IF NOT EXISTS document_check_id") < index_of(
        "CREATE POLICY alerts_org_isolation"
    )


def test_column_ddl(m):
    statements = m.upgrade_statements()
    checks = next(
        s for s in statements if s.startswith("CREATE TABLE IF NOT EXISTS document_checks")
    )
    assert "id UUID PRIMARY KEY," in checks
    assert "org_id UUID NOT NULL REFERENCES organizations (id) ON DELETE CASCADE" in checks
    assert "client_id UUID REFERENCES clients (id) ON DELETE CASCADE" in checks
    assert "created_by UUID REFERENCES users (id) ON DELETE SET NULL" in checks
    assert "watch BOOLEAN DEFAULT true NOT NULL" in checks
    assert "findings JSONB DEFAULT '[]'::jsonb NOT NULL" in checks
    assert (
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_document_changes "
        "BOOLEAN DEFAULT true NOT NULL"
    ) in statements
    assert (
        "ALTER TABLE alerts ADD COLUMN IF NOT EXISTS document_check_id UUID "
        "REFERENCES document_checks (id) ON DELETE CASCADE"
    ) in statements
    assert (
        "CREATE INDEX IF NOT EXISTS ix_document_dependencies_provision "
        "ON document_dependencies (source, act, key)"
    ) in statements


def test_tenant_tables_get_the_row_level_security_of_clients(m, m007):
    statements = m.upgrade_statements()
    assert set(m.RLS_TABLES) == {"document_checks", "document_dependencies"}
    for table in m.RLS_TABLES:
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in statements
        assert f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in statements
        for name, ddl in m007.POLICIES["clients"].items():
            expected = ddl.replace("clients", table)
            assert m.POLICIES[table][name.replace("clients", table)] == expected
            assert expected in statements
    # Nothing of a tenant in system_state: no row-level security there.
    assert not [s for s in statements if "system_state" in s and "ROW LEVEL" in s]
    assert not [s for s in statements if s.startswith("CREATE POLICY") and "system_state" in s]


def test_alert_policies_gain_the_document_way_in_and_lose_it_on_downgrade(m, m007):
    old = m007.POLICIES["alerts"]
    assert old == m.ALERT_POLICIES_007
    assert set(m.ALERT_POLICIES) == set(old)
    for name, ddl in m.ALERT_POLICIES.items():
        before = old[name]
        # Same policy, same client condition, plus "or the alert's check is ours".
        client_condition = before[before.index("(") + 1 : -1]
        assert client_condition in ddl
        assert (
            " OR document_check_id IN (SELECT id FROM document_checks WHERE org_id::text = " in ddl
        )
        assert "current_setting('app.current_org_id', true)" in ddl
        assert ddl in m.upgrade_statements()
        assert before in m.downgrade_statements()


def test_downgrade_takes_everything_back(m):
    statements = m.downgrade_statements()
    assert statements[0] == "DELETE FROM alerts WHERE client_id IS NULL"
    for table in m.TABLES:
        assert f"DROP TABLE IF EXISTS {table}" in statements
    for table, col in m.ADDED_COLUMNS:
        assert f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col.name}" in statements
    assert "DROP INDEX IF EXISTS ix_alerts_document_check_id" in statements

    def index_of(statement: str) -> int:
        return statements.index(statement)

    # The column that references document_checks goes before the table, and a
    # table goes after the one that references it.
    assert index_of("ALTER TABLE alerts DROP COLUMN IF EXISTS document_check_id") < index_of(
        "DROP TABLE IF EXISTS document_checks"
    )
    assert index_of("DROP TABLE IF EXISTS document_dependencies") < index_of(
        "DROP TABLE IF EXISTS document_checks"
    )
    for statement in statements[1:]:
        assert " IF EXISTS " in statement or statement.startswith("CREATE POLICY"), statement


def test_after_the_downgrade_007_has_nothing_to_do(m, m007):
    """CI downgrades to 006 and upgrades again: 007 must find its own shape.

    007 drops every index it does not declare on its tables and creates the
    policies missing by name: the downgrade must leave neither an index of
    this revision on ``alerts`` nor a missing ``alerts`` policy.
    """
    statements = m.downgrade_statements()
    own_indexes_on_old_tables = [ix for ix in m.INDEXES if ix.table in m007.TABLES]
    assert [ix.name for ix in own_indexes_on_old_tables] == ["ix_alerts_document_check_id"]
    for ix in own_indexes_on_old_tables:
        assert f"DROP INDEX IF EXISTS {ix.name}" in statements
    recreated = {
        re.match(r"CREATE POLICY (\w+) ON alerts", s).group(1)
        for s in statements
        if s.startswith("CREATE POLICY")
    }
    assert recreated == set(m007.POLICIES["alerts"])
