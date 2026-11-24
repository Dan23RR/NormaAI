"""Members of an organisation (src/auth/members.py, /api/v1/auth/members).

Through the API, on the real tables (SQLite, tests/documents_support.Database),
with the live account check (``live_account``):

- only an admin lists, changes and removes members, and only of their own
  organisation (another organisation's member is a 404, like a missing one);
- the last active admin can be neither demoted nor removed (409);
- a removed member's token stops working, and a changed role applies to the
  member's next request;
- removing a member deletes the account and its own conversations, while the
  checks and assessments it created stay with the organisation.

The real PostgreSQL run, under row-level security, is tests/test_accounts_postgres.py.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.auth import dependencies as deps
from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Assessment, Client, Conversation, DocumentCheck, User
from tests.documents_support import Database

pytestmark = pytest.mark.live_account


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
def db(monkeypatch):
    database = Database()
    real = deps.load_account

    async def _load(user_id, manager=None):
        return await real(user_id, manager=database)

    monkeypatch.setattr(deps, "load_account", _load)
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
        from src.api.routers import clients
        from src.auth import router

        limiter.enabled = False
        with patch.object(router, "db_manager", db), patch.object(clients, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


def _headers(user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id, org_id, role)}"}


@pytest.fixture
def studio(db):
    """Studio Rossi: two admins (one deactivated), a member, a viewer; and Beta with one admin."""
    org = db.add_org("Studio Rossi")
    other = db.add_org("Beta")
    return {
        "org": org,
        "admin": db.add_user(org, "admin@rossi.it", role="admin"),
        "old_admin": db.add_user(org, "old@rossi.it", role="admin", active=False),
        "member": db.add_user(org, "member@rossi.it", role="member"),
        "viewer": db.add_user(org, "viewer@rossi.it", role="viewer"),
        "other": other,
        "other_admin": db.add_user(other, "admin@beta.it", role="admin"),
    }


def _as(studio, name: str) -> dict[str, str]:
    org = studio["other"] if name == "other_admin" else studio["org"]
    role = {"member": "member", "viewer": "viewer"}.get(name, "admin")
    return _headers(studio[name], org, role)


class TestList:
    def test_an_admin_sees_the_members_of_the_own_organisation(self, client, studio):
        r = client.get("/api/v1/auth/members", headers=_as(studio, "admin"))
        assert r.status_code == 200
        emails = {m["email"] for m in r.json()}
        assert emails == {"admin@rossi.it", "old@rossi.it", "member@rossi.it", "viewer@rossi.it"}
        one = next(m for m in r.json() if m["email"] == "viewer@rossi.it")
        assert one["role"] == "viewer" and one["is_active"] is True
        assert set(one) == {
            "id",
            "email",
            "name",
            "role",
            "is_active",
            "email_verified",
            "created_at",
        }

    @pytest.mark.parametrize("who", ["member", "viewer"])
    def test_only_admins(self, client, studio, who):
        r = client.get("/api/v1/auth/members", headers=_as(studio, who))
        assert r.status_code == 403
        assert r.json()["detail"] == deps.ADMIN_ONLY_DETAIL


class TestChangeRole:
    def test_an_admin_changes_a_role_and_it_applies_at_once(self, client, db, studio):
        url = f"/api/v1/auth/members/{studio['member']}"
        r = client.patch(url, json={"role": "viewer"}, headers=_as(studio, "admin"))
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"
        assert db.rows(User, id=studio["member"])[0].role == "viewer"
        # The member's token still says "member": the next write is refused.
        r = client.post("/api/v1/clients", json={"name": "Acme"}, headers=_as(studio, "member"))
        assert r.status_code == 403
        assert r.json()["detail"] == deps.READ_ONLY_DETAIL

    def test_the_last_active_admin_cannot_be_demoted(self, client, db, studio):
        url = f"/api/v1/auth/members/{studio['admin']}"
        r = client.patch(url, json={"role": "member"}, headers=_as(studio, "admin"))
        assert r.status_code == 409
        assert "almeno un amministratore attivo" in r.json()["detail"]
        assert db.rows(User, id=studio["admin"])[0].role == "admin"

    def test_with_another_admin_an_admin_can_step_down(self, client, db, studio):
        client.patch(
            f"/api/v1/auth/members/{studio['member']}",
            json={"role": "admin"},
            headers=_as(studio, "admin"),
        )
        r = client.patch(
            f"/api/v1/auth/members/{studio['admin']}",
            json={"role": "member"},
            headers=_as(studio, "admin"),
        )
        assert r.status_code == 200
        assert db.rows(User, id=studio["admin"])[0].role == "member"

    def test_a_member_of_another_organisation_is_not_found(self, client, db, studio):
        r = client.patch(
            f"/api/v1/auth/members/{studio['other_admin']}",
            json={"role": "viewer"},
            headers=_as(studio, "admin"),
        )
        assert r.status_code == 404
        assert db.rows(User, id=studio["other_admin"])[0].role == "admin"

    def test_an_unknown_role_is_422(self, client, studio):
        r = client.patch(
            f"/api/v1/auth/members/{studio['member']}",
            json={"role": "owner"},
            headers=_as(studio, "admin"),
        )
        assert r.status_code == 422

    def test_only_admins(self, client, db, studio):
        r = client.patch(
            f"/api/v1/auth/members/{studio['viewer']}",
            json={"role": "admin"},
            headers=_as(studio, "member"),
        )
        assert r.status_code == 403
        assert db.rows(User, id=studio["viewer"])[0].role == "viewer"


class TestRemove:
    def test_an_admin_removes_a_member_and_its_token_stops_working(self, client, db, studio):
        member = studio["member"]
        org = studio["org"]
        with db.sync_session() as session:
            client_row = Client(id=uuid.uuid4(), org_id=org, name="Acme")
            session.add(client_row)
            session.flush()
            session.add(Conversation(id=uuid.uuid4(), user_id=member, messages=[]))
            session.add(Conversation(id=uuid.uuid4(), user_id=studio["admin"], messages=[]))
            session.add(
                Assessment(
                    id=uuid.uuid4(), client_id=client_row.id, framework="GDPR", assessed_by=member
                )
            )
            session.add(
                DocumentCheck(
                    id=uuid.uuid4(),
                    org_id=org,
                    created_by=member,
                    filename="nota.txt",
                    document_sha256="0" * 64,
                    checked_at=datetime.now(UTC),
                )
            )
            session.commit()
        member_headers = _as(studio, "member")
        assert client.get("/api/v1/clients", headers=member_headers).status_code == 200

        r = client.delete(f"/api/v1/auth/members/{member}", headers=_as(studio, "admin"))
        assert r.status_code == 204
        assert db.rows(User, id=member) == []
        assert db.rows(Conversation, user_id=member) == []
        assert len(db.rows(Conversation, user_id=studio["admin"])) == 1  # nobody else's
        assert db.rows(Assessment)[0].assessed_by is None  # the assessment stays
        assert db.rows(DocumentCheck)[0].created_by is None  # the check stays
        assert client.get("/api/v1/clients", headers=member_headers).status_code == 401

    def test_the_last_active_admin_cannot_be_removed(self, client, db, studio):
        r = client.delete(f"/api/v1/auth/members/{studio['admin']}", headers=_as(studio, "admin"))
        assert r.status_code == 409
        assert db.rows(User, id=studio["admin"])

    def test_a_deactivated_admin_does_not_count(self, client, db, studio):
        """old@rossi.it is an admin but deactivated: removing it is allowed, and it
        does not let the only active admin go."""
        r = client.delete(
            f"/api/v1/auth/members/{studio['old_admin']}", headers=_as(studio, "admin")
        )
        assert r.status_code == 204
        r = client.delete(f"/api/v1/auth/members/{studio['admin']}", headers=_as(studio, "admin"))
        assert r.status_code == 409

    def test_a_member_of_another_organisation_is_not_found(self, client, db, studio):
        r = client.delete(
            f"/api/v1/auth/members/{studio['other_admin']}", headers=_as(studio, "admin")
        )
        assert r.status_code == 404
        assert db.rows(User, id=studio["other_admin"])

    @pytest.mark.parametrize("who", ["member", "viewer"])
    def test_only_admins(self, client, db, studio, who):
        r = client.delete(f"/api/v1/auth/members/{studio['viewer']}", headers=_as(studio, who))
        assert r.status_code == 403
        assert db.rows(User, id=studio["viewer"])

    def test_every_change_runs_in_the_organisation_context(self, client, db, studio):
        db.session_orgs.clear()
        client.delete(f"/api/v1/auth/members/{studio['viewer']}", headers=_as(studio, "admin"))
        client.patch(
            f"/api/v1/auth/members/{studio['member']}",
            json={"role": "viewer"},
            headers=_as(studio, "admin"),
        )
        client.get("/api/v1/auth/members", headers=_as(studio, "admin"))
        # The account check reads users without a tenant (no RLS there); the
        # member routes open their sessions with the caller's organisation.
        assert str(studio["org"]) in db.session_orgs
        assert set(db.session_orgs) <= {None, str(studio["org"])}
