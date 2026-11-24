"""Offline tests for alembic/versions/011_org_letterheads.py.

The migration creates ``org_letterheads`` with pure, idempotent statements.
Without PostgreSQL this suite checks that:

* the inline description is what src/db/models.py declares (columns in order,
  types as the PostgreSQL dialect compiles them, nullability, the primary key,
  foreign keys with their ON DELETE, no index), so ``alembic check`` finds
  nothing to do after the upgrade;
* it is the head of the chain, right after 010;
* the table gets the row-level security of ``clients``;
* every statement can run twice and the downgrade takes everything back, so
  the CI step that downgrades to 006 and upgrades again finds 007 with nothing
  to do.

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
    return _load("011_org_letterheads.py")


@pytest.fixture(scope="module")
def m007():
    return _load("007_reconcile_schema.py")


def test_revision_chain(m):
    assert m.revision == "011_org_letterheads"
    assert m.down_revision == "010_account_security"
    assert len(m.revision) <= 32  # alembic_version.version_num is VARCHAR(32)


def test_it_is_the_head():
    revisions, parents = set(), set()
    for path in VERSIONS.glob("[0-9][0-9][0-9]_*.py"):
        module = _load(path.name)
        revisions.add(module.revision)
        if module.down_revision:
            parents.add(module.down_revision)
    assert revisions - parents == {"011_org_letterheads"}


def test_the_table_mirrors_the_orm_metadata(m, m007):
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
            # A NOT NULL column the application may leave out needs a default.
            if not spec.nullable and not spec.primary_key and spec.name != "name":
                assert spec.default is not None, where

        orm_fks = {
            (fk.columns[0].name, fk.elements[0].column.table.name, fk.ondelete)
            for fk in table.foreign_key_constraints
        }
        assert all(fk.elements[0].column.name == "id" for fk in table.foreign_key_constraints)
        spec_fks = {(c.name, c.references, c.ondelete) for c in spec_cols if c.references}
        assert spec_fks == orm_fks, table_name
        # No index of its own: the primary key is the only way the table is read.
        assert not table.indexes, table_name


def test_one_letterhead_per_organisation(m):
    from src.db.models import Base

    table = Base.metadata.tables["org_letterheads"]
    assert [c.name for c in table.primary_key.columns] == ["org_id"]
    assert [c.name for c in m.TABLES["org_letterheads"] if c.primary_key] == ["org_id"]


def test_upgrade_statements(m):
    statements = m.upgrade_statements()
    create = statements[0]
    assert create.startswith("CREATE TABLE IF NOT EXISTS org_letterheads (")
    assert "org_id UUID PRIMARY KEY REFERENCES organizations (id) ON DELETE CASCADE," in create
    assert "name VARCHAR(200) NOT NULL," in create
    assert "logo BYTEA," in create
    assert "updated_by UUID REFERENCES users (id) ON DELETE SET NULL," in create
    assert (
        create.rstrip(")")
        .rstrip()
        .endswith("updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL")
    )


def test_upgrade_statements_can_run_twice(m):
    statements = m.upgrade_statements()
    for position, statement in enumerate(statements):
        if statement.startswith("CREATE TABLE"):
            assert statement.startswith("CREATE TABLE IF NOT EXISTS "), statement
        elif statement.startswith("CREATE POLICY"):
            name, table = re.match(r"CREATE POLICY (\w+) ON (\w+) ", statement).groups()
            assert statements[position - 1] == f"DROP POLICY IF EXISTS {name} ON {table}"
        else:
            assert re.fullmatch(
                r"(ALTER TABLE \w+ (ENABLE|FORCE) ROW LEVEL SECURITY|DROP POLICY IF EXISTS \w+ ON \w+)",
                statement,
            ), statement


def test_the_table_gets_the_row_level_security_of_clients(m, m007):
    statements = m.upgrade_statements()
    assert m.RLS_TABLES == ("org_letterheads",)
    assert "ALTER TABLE org_letterheads ENABLE ROW LEVEL SECURITY" in statements
    assert "ALTER TABLE org_letterheads FORCE ROW LEVEL SECURITY" in statements
    for name, ddl in m007.POLICIES["clients"].items():
        expected = ddl.replace("clients", "org_letterheads")
        assert m.POLICIES["org_letterheads"][name.replace("clients", "org_letterheads")] == expected
        assert expected in statements
    # The table before its row-level security.
    assert statements.index("ALTER TABLE org_letterheads ENABLE ROW LEVEL SECURITY") > 0


def test_downgrade_takes_everything_back(m):
    assert m.downgrade_statements() == ["DROP TABLE IF EXISTS org_letterheads"]


def test_after_the_downgrade_007_has_nothing_to_do(m, m007):
    """007 reconciles its own tables: 011 adds none of its objects to them."""
    assert "org_letterheads" not in m007.TABLES
    for statement in m.upgrade_statements():
        assert not any(f" ON {table} " in f"{statement} " for table in m007.TABLES), statement
        assert not any(f"ALTER TABLE {table} " in statement for table in m007.TABLES), statement
