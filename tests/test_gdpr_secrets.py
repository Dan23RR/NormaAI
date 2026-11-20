"""The GDPR export gives no secret and no other member's private data.

On the real tables (SQLite, tests/documents_support.Database): an admin's export
has, of every account, only what the members list shows (no password hash, no
password-reset hash, no staff flag), no invite (they carry the hash of their
code), and only the admin's own conversations.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.auth.invites import new_invite
from src.auth.security import create_access_token, hash_password
from src.config import get_settings
from src.db.models import Base, Conversation, Invite, User
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
        from src.api.routers import gdpr

        limiter.enabled = False
        with patch.object(gdpr, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


@pytest.fixture
def studio(db):
    org = db.add_org("Studio Rossi")
    admin = db.add_user(org, "admin@rossi.it", role="admin")
    member = db.add_user(org, "member@rossi.it", role="member")
    with db.sync_session() as session:
        for user_id in (admin, member):
            row = session.get(User, user_id)
            row.hashed_password = hash_password("segretissima-1")
            row.password_reset_token_hash = "f" * 64
            row.password_reset_expires_at = datetime.now(UTC) + timedelta(minutes=30)
            row.is_staff = user_id == admin
        session.add(Conversation(id=uuid.uuid4(), user_id=admin, messages=[{"q": "mia"}]))
        session.add(Conversation(id=uuid.uuid4(), user_id=member, messages=[{"q": "sua"}]))
        invite, code = new_invite(email="nuovo@rossi.it", org_id=org, created_by=admin)
        session.add(invite)
        session.commit()
    return {"org": org, "admin": admin, "member": member, "code": code}


def _export(client, studio) -> dict:
    token = create_access_token(studio["admin"], studio["org"], "admin")
    r = client.get("/api/v1/gdpr/export", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    return r.json()


def test_no_secret_leaves(client, studio):
    data = _export(client, studio)
    text = str(data)
    for secret_field in (
        "hashed_password",
        "password_reset_token_hash",
        "password_reset_expires_at",
        "code_hash",
        "is_staff",
        "sessions_revoked_at",
    ):
        assert secret_field not in text, secret_field
    assert "$2b$" not in text  # no bcrypt hash under any name
    assert "f" * 64 not in text
    assert studio["code"] not in text


def test_accounts_carry_what_the_members_list_shows(client, studio):
    users = {u["email"]: u for u in _export(client, studio)["users"]}
    assert set(users) == {"admin@rossi.it", "member@rossi.it"}
    assert set(users["member@rossi.it"]) == {
        "id",
        "org_id",
        "email",
        "name",
        "role",
        "is_active",
        "email_verified",
        "notify_document_changes",
        "created_at",
    }
    assert users["member@rossi.it"]["org_id"] == str(studio["org"])


def test_invites_are_not_exported(client, db, studio):
    data = _export(client, studio)
    assert "invites" not in data
    assert "nuovo@rossi.it" not in str(data)
    assert db.rows(Invite)[0].code_hash  # still stored, just not exported


def test_conversations_are_the_requesters_own(client, studio):
    conversations = _export(client, studio)["conversations"]
    assert [c["user_id"] for c in conversations] == [str(studio["admin"])]
    assert conversations[0]["messages"] == [{"q": "mia"}]
