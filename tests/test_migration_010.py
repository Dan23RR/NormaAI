"""Offline tests for alembic/versions/010_account_security.py.

The migration adds four columns to ``users`` with pure, idempotent statements.
Without PostgreSQL this suite checks that:

* the inline description is what src/db/models.py declares (types as the
  PostgreSQL dialect compiles them, nullability, no foreign key, no index), so
  ``alembic check`` finds nothing to do after the upgrade;
* every column of ``users`` is accounted for by 007, 008, 009 or 010;
* the upgrade can run twice and the downgrade takes everything back, so the
  CI step that downgrades to 006 and upgrades again finds 007 with nothing to do.

The real run (upgrade, ``alembic check``, downgrade to 006 and up again) is the
CI ``schema`` job in .github/workflows/ci.yml.
"""

from __future__ import annotations

import importlib.util
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
    return _load("010_account_security.py")


@pytest.fixture(scope="module")
def m007():
    return _load("007_reconcile_schema.py")


def test_revision_chain(m):
    assert m.revision == "010_account_security"
    assert m.down_revision == "009_document_checks"
    assert len(m.revision) <= 32  # alembic_version.version_num is VARCHAR(32)


def test_it_is_the_head():
    revisions, parents = set(), set()
    for path in VERSIONS.glob("[0-9][0-9][0-9]_*.py"):
        module = _load(path.name)
        revisions.add(module.revision)
        if module.down_revision:
            parents.add(module.down_revision)
    assert revisions - parents == {"010_account_security"}


def test_added_columns_mirror_the_orm_metadata(m, m007):
    from src.db.models import Base

    table = Base.metadata.tables[m.TABLE]
    dialect = pg.dialect()
    for spec in m.ADDED_COLUMNS:
        col = table.columns[spec.name]
        where = f"{m.TABLE}.{spec.name}"
        assert spec.type == m007.normalize_type(str(col.type.compile(dialect=dialect))), where
        assert spec.nullable == bool(col.nullable), where
        # A NOT NULL column added to a table with rows needs a default.
        assert spec.nullable or spec.default is not None, where
        assert not [fk for fk in table.foreign_key_constraints if fk.columns[0].name == spec.name]
        assert not [ix for ix in table.indexes if spec.name in [c.name for c in ix.columns]]


def test_every_users_column_has_a_migration(m, m007):
    from src.db.models import Base

    m009 = _load("009_document_checks.py")
    known = {c.name for c in m007.TABLES["users"]}
    known.add("email_verified")  # 008_invites
    known |= {c.name for table, c in m009.ADDED_COLUMNS if table == "users"}
    known |= {c.name for c in m.ADDED_COLUMNS}
    assert {c.name for c in Base.metadata.tables["users"].columns} == known


def test_upgrade_statements(m):
    assert m.upgrade_statements() == [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_staff BOOLEAN DEFAULT false NOT NULL",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token_hash VARCHAR(64)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires_at "
        "TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS sessions_revoked_at TIMESTAMP WITH TIME ZONE",
    ]


def test_downgrade_takes_everything_back(m):
    statements = m.downgrade_statements()
    assert statements == [
        f"ALTER TABLE users DROP COLUMN IF EXISTS {c.name}" for c in reversed(m.ADDED_COLUMNS)
    ]


def test_nobody_is_staff_after_the_upgrade(m):
    """No backfill: staff is granted again with scripts/staff.py, never by the migration."""
    statements = " ".join(m.upgrade_statements()).upper()
    assert "UPDATE" not in statements
    assert "DEFAULT FALSE" in statements


def test_after_the_downgrade_007_has_nothing_to_do(m, m007):
    """007 drops indexes it does not declare on its tables: 010 adds none."""
    assert not [s for s in m.upgrade_statements() if "INDEX" in s or "POLICY" in s]
    assert all(s.startswith("ALTER TABLE users ") for s in m.upgrade_statements())
    assert "users" in m007.RLS_DISABLED_TABLES  # no row-level security to keep in step
