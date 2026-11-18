"""Which invites verify the invitee's email at registration.

Staff (``users.is_staff``) is honoured only on a verified address, so
"verified" must mean that the owner of the mailbox confirmed it. An invite
NormaAI minted (scripts/create_invite.py: no creator; or a staff member)
vouches for its address; an organisation admin's invite does not, since an
admin can invite any address into their own organisation: that invitee gets
the verification link like everyone else. On the real tables (SQLite).
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.auth.invites import new_invite
from src.config import get_settings
from src.db.models import Base, User
from tests.documents_support import Database


@pytest.fixture(autouse=True)
def _restore_module_cache():
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture
def db():
    database = Database()
    Base.metadata.tables["invites"].create(database.engine)
    return database


@pytest.fixture
def client(db):
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        mock_settings.return_value = get_settings()

        from fastapi.testclient import TestClient

        from src.api.main import app, limiter
        from src.auth import router

        async def _session():
            async with db.session() as session:
                yield session

        limiter.enabled = False
        invite_mode = get_settings().model_copy(update={"registration_mode": "invite"})
        app.dependency_overrides[router.get_db_session] = _session
        with (
            patch.object(router, "get_settings", return_value=invite_mode),
            patch.object(router, "send_verification_email") as send,
        ):
            try:
                yield TestClient(app), send
            finally:
                app.dependency_overrides.clear()


def _invite(db, *, org_id, created_by, email="ops@normaai.org") -> str:
    invite, code = new_invite(email=email, org_id=org_id, created_by=created_by)
    with db.sync_session() as session:
        session.add(invite)
        session.commit()
    return code


def _register(client, code, email="ops@normaai.org"):
    body = {
        "email": email,
        "password": "supersecret123",
        "name": "Ops",
        # Needed by an invite that creates an organisation, ignored by one that joins.
        "organization_name": "NormaAI",
        "invite_code": code,
    }
    return client.post("/api/v1/auth/register", json=body)


def _verified(db, email="ops@normaai.org") -> bool:
    return bool(db.rows(User, email=email)[0].email_verified)


def test_an_organisation_admins_invite_does_not_verify_the_address(client, db):
    http, send = client
    org = db.add_org("Studio Rossi")
    admin = db.add_user(org, "admin@rossi.it", role="admin")
    r = _register(http, _invite(db, org_id=org, created_by=admin))
    assert r.status_code == 201, r.text
    assert _verified(db) is False
    send.assert_called_once()  # the link goes out, as for everyone else


def test_an_invite_from_the_command_line_verifies_it(client, db):
    http, send = client
    r = _register(http, _invite(db, org_id=None, created_by=None))
    assert r.status_code == 201, r.text
    assert _verified(db) is True
    send.assert_not_called()


def test_a_staff_members_invite_verifies_it(client, db):
    http, _send = client
    org = db.add_org("NormaAI")
    ops = db.add_user(org, "lead@normaai.org", role="admin", verified=True)
    with db.sync_session() as session:
        session.get(User, ops).is_staff = True
        session.commit()
    r = _register(http, _invite(db, org_id=org, created_by=ops))
    assert r.status_code == 201, r.text
    assert _verified(db) is True


def test_registration_never_makes_anyone_staff(client, db):
    http, _send = client
    _register(http, _invite(db, org_id=None, created_by=None))
    assert db.rows(User, email="ops@normaai.org")[0].is_staff is False


def test_a_different_address_is_never_verified_by_the_invite(client, db):
    http, _send = client
    code = _invite(db, org_id=None, created_by=None, email="someone@normaai.org")
    r = _register(http, code, email="other@normaai.org")
    assert r.status_code == 201, r.text
    assert _verified(db, "other@normaai.org") is False
