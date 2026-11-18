"""The read-only ``viewer`` role reads, and changes nothing.

Clients: creating and editing need a non-viewer role (``require_editor``);
deleting, which takes the client's checks, assessments and alerts with it,
needs ``admin`` (``require_admin``). Alerts: creating one, marking it read and
dismissing it (state every member sees) need a non-viewer role. Reading stays
open to every role. On the real tables (SQLite, tests/documents_support.Database).
"""

from __future__ import annotations

import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.auth.dependencies import ADMIN_ONLY_DETAIL, READ_ONLY_DETAIL
from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Alert, Client
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
    return Database()


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
        from src.api.routers import alerts, clients

        limiter.enabled = False
        with patch.object(clients, "db_manager", db), patch.object(alerts, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


@pytest.fixture
def org(db):
    org_id = db.add_org()
    client_id = db.add_client(org_id, "Acme Srl")
    with db.sync_session() as session:
        alert = Alert(
            id=uuid.uuid4(),
            client_id=client_id,
            severity="HIGH",
            framework="GDPR",
            title="Nuova versione",
            description="",
        )
        session.add(alert)
        session.commit()
    return {"id": org_id, "client": client_id, "alert": alert.id}


def _as(org, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(uuid.uuid4(), org['id'], role)}"}


class TestClients:
    def test_a_viewer_reads_but_cannot_create_edit_or_delete(self, client, db, org):
        viewer = _as(org, "viewer")
        assert client.get("/api/v1/clients", headers=viewer).status_code == 200
        assert client.get(f"/api/v1/clients/{org['client']}", headers=viewer).status_code == 200

        r = client.post("/api/v1/clients", json={"name": "Nuovo"}, headers=viewer)
        assert r.status_code == 403
        assert r.json()["detail"] == READ_ONLY_DETAIL
        r = client.put(f"/api/v1/clients/{org['client']}", json={"name": "X"}, headers=viewer)
        assert r.status_code == 403
        r = client.delete(f"/api/v1/clients/{org['client']}", headers=viewer)
        assert r.status_code == 403
        assert [c.name for c in db.rows(Client)] == ["Acme Srl"]

    def test_a_member_creates_and_edits_but_does_not_delete(self, client, db, org):
        member = _as(org, "member")
        assert (
            client.post("/api/v1/clients", json={"name": "Nuovo"}, headers=member).status_code
            == 201
        )
        r = client.put(f"/api/v1/clients/{org['client']}", json={"sector": "Moda"}, headers=member)
        assert r.status_code == 200
        r = client.delete(f"/api/v1/clients/{org['client']}", headers=member)
        assert r.status_code == 403
        assert r.json()["detail"] == ADMIN_ONLY_DETAIL
        assert len(db.rows(Client, id=org["client"])) == 1

    def test_an_admin_deletes(self, client, db, org):
        r = client.delete(f"/api/v1/clients/{org['client']}", headers=_as(org, "admin"))
        assert r.status_code == 204
        assert db.rows(Client, id=org["client"]) == []


class TestAlerts:
    def test_a_viewer_reads_but_cannot_create_mark_read_or_dismiss(self, client, db, org):
        viewer = _as(org, "viewer")
        assert client.get("/api/v1/alerts", headers=viewer).status_code == 200
        body = {
            "client_id": str(org["client"]),
            "severity": "LOW",
            "framework": "GDPR",
            "title": "Prova",
        }
        assert client.post("/api/v1/alerts", json=body, headers=viewer).status_code == 403
        r = client.patch(f"/api/v1/alerts/{org['alert']}/read", headers=viewer)
        assert r.status_code == 403
        assert r.json()["detail"] == READ_ONLY_DETAIL
        assert (
            client.patch(f"/api/v1/alerts/{org['alert']}/dismiss", headers=viewer).status_code
            == 403
        )
        alert = db.rows(Alert, id=org["alert"])[0]
        assert alert.is_read is False and alert.is_dismissed is False
        assert len(db.rows(Alert)) == 1

    def test_a_member_marks_read_and_dismisses(self, client, db, org):
        member = _as(org, "member")
        assert (
            client.patch(f"/api/v1/alerts/{org['alert']}/read", headers=member).status_code == 200
        )
        assert (
            client.patch(f"/api/v1/alerts/{org['alert']}/dismiss", headers=member).status_code
            == 200
        )
        assert db.rows(Alert, id=org["alert"])[0].is_dismissed is True


def test_require_editor_is_still_importable_from_the_documents_router():
    from src.api.routers import documents
    from src.auth import dependencies

    assert documents.require_editor is dependencies.require_editor
    assert documents.READ_ONLY_DETAIL == dependencies.READ_ONLY_DETAIL
