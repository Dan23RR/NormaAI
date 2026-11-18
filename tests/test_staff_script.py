"""scripts/staff.py: the only way to make someone staff, and the account operations.

On the real tables (SQLite, tests/documents_support.Database): ``grant`` needs
an active account with a verified email; ``revoke`` takes the flag away;
``list`` shows who is staff; ``end-sessions`` sets ``sessions_revoked_at``;
the command line exits 1 with a message on a refusal.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.db.models import User
from tests.documents_support import Database

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "staff.py"


@pytest.fixture(scope="module")
def staff():
    spec = importlib.util.spec_from_file_location("staff_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db():
    return Database()


@pytest.fixture
def people(db):
    org = db.add_org("NormaAI")
    return {
        "ops": db.add_user(org, "ops@normaai.org", verified=True),
        "unverified": db.add_user(org, "new@normaai.org", verified=False),
        "gone": db.add_user(org, "gone@normaai.org", active=False),
    }


def _row(db, user_id) -> User:
    return db.rows(User, id=user_id)[0]


async def test_grant_and_revoke(staff, db, people):
    assert await staff.grant(db, "ops@normaai.org") == "ops@normaai.org is now staff."
    assert _row(db, people["ops"]).is_staff is True
    assert await staff.grant(db, "ops@normaai.org") == "ops@normaai.org is already staff."
    assert await staff.list_staff(db) == ["ops@normaai.org  [NormaAI]"]
    assert await staff.revoke(db, "ops@normaai.org") == "ops@normaai.org is no longer staff."
    assert _row(db, people["ops"]).is_staff is False
    assert await staff.list_staff(db) == []


async def test_grant_refuses_an_unverified_or_deactivated_account(staff, db, people):
    with pytest.raises(staff.StaffError, match="has not verified its email"):
        await staff.grant(db, "new@normaai.org")
    with pytest.raises(staff.StaffError, match="deactivated"):
        await staff.grant(db, "gone@normaai.org")
    with pytest.raises(staff.StaffError, match="No account"):
        await staff.grant(db, "nobody@normaai.org")
    assert not any(u.is_staff for u in db.rows(User))


async def test_list_flags_a_staff_account_that_lost_its_verification(staff, db, people):
    await staff.grant(db, "ops@normaai.org")
    with db.sync_session() as session:
        session.get(User, people["ops"]).email_verified = False
        session.commit()
    assert await staff.list_staff(db) == [
        "ops@normaai.org  [NormaAI] (email NOT verified: not staff until it is)"
    ]


async def test_end_sessions(staff, db, people):
    before = datetime.now(UTC) - timedelta(seconds=1)
    message = await staff.end_sessions(db, "ops@normaai.org")
    assert "ended" in message
    revoked = _row(db, people["ops"]).sessions_revoked_at
    assert revoked is not None and revoked.replace(tzinfo=UTC) >= before


async def test_run_dispatches_the_commands(staff, db, people):
    args = staff._parse_args(["grant", "ops@normaai.org"])
    assert await staff.run(args, db) == ["ops@normaai.org is now staff."]
    assert await staff.run(staff._parse_args(["list"]), db) == ["ops@normaai.org  [NormaAI]"]
    lines = await staff.run(staff._parse_args(["reset-password", "ops@normaai.org"]), db)
    assert lines[0].startswith("Password reset link for ops@normaai.org")
    assert "/reset-password?token=" in lines[1]


def test_main_exits_1_with_the_message_on_a_refusal(staff, monkeypatch, capsys):
    async def _refuse(args):
        raise staff.StaffError("No account with the email x@y.it.")

    monkeypatch.setattr(staff, "_main", _refuse)
    assert staff.main(["grant", "x@y.it"]) == 1
    assert "No account with the email x@y.it." in capsys.readouterr().err


def test_a_command_is_required(staff):
    with pytest.raises(SystemExit):
        staff._parse_args([])
