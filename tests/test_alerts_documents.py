"""The alerts router and the alerts of a document (src/api/routers/alerts.py).

The document surveillance writes an alert that points to a document check and
may have no client. Before, an alert was reachable only through its client: the
list joined ``clients`` and such an alert never showed. These tests run the
router's real queries on SQLite (tests/documents_support.Database) and check
that an organisation sees the alerts of its clients and of its documents, and
nothing of another organisation.

tests/test_alerts_router.py keeps covering the routes with a scripted session.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Alert, DocumentCheck
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
        from src.api.routers import alerts

        limiter.enabled = False
        with patch.object(alerts, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


def _headers(org_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=uuid.uuid4(), org_id=org_id, role="member")
    return {"Authorization": f"Bearer {token}"}


def _add_check(db: Database, org_id: uuid.UUID, client_id: uuid.UUID | None = None) -> uuid.UUID:
    row = DocumentCheck(
        id=uuid.uuid4(),
        org_id=org_id,
        client_id=client_id,
        filename="nota.docx",
        document_sha256="0" * 64,
        lang="IT",
        status="correggere",
        needs_review=True,
        counts={},
        findings=[],
        checked_at=datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
    )
    with db.sync_session() as session:
        session.add(row)
        session.commit()
    return row.id


def _add_alert(db: Database, title: str, **fields) -> uuid.UUID:
    alert = Alert(
        id=uuid.uuid4(),
        severity=fields.pop("severity", "HIGH"),
        framework=fields.pop("framework", "GDPR"),
        title=title,
        description="Dopo il controllo è cambiata una disposizione citata nel documento.",
        is_read=False,
        is_dismissed=False,
        **fields,
    )
    with db.sync_session() as session:
        session.add(alert)
        session.commit()
    return alert.id


@pytest.fixture
def world(db):
    """Two organisations: A has a client alert, a document alert without a client and
    a document alert of a client's document; B has one document alert."""
    org_a, org_b = db.add_org("Alfa"), db.add_org("Beta")
    client_a = db.add_client(org_a, "Acme Srl")
    check_a = _add_check(db, org_a)
    check_a_client = _add_check(db, org_a, client_a)
    check_b = _add_check(db, org_b)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "client_a": client_a,
        "check_a": check_a,
        "by_client": _add_alert(db, "Avviso del cliente", client_id=client_a, severity="LOW"),
        "by_document": _add_alert(
            db,
            "Documento da rivedere: nota.docx",
            document_check_id=check_a,
            actions_required=["Apri il controllo."],
        ),
        "by_both": _add_alert(
            db, "Documento del cliente", client_id=client_a, document_check_id=check_a_client
        ),
        "of_b": _add_alert(db, "Documento di Beta", document_check_id=check_b),
    }


def test_the_list_has_the_alerts_of_clients_and_of_documents(client, world):
    response = client.get("/api/v1/alerts?limit=50&offset=0", headers=_headers(world["org_a"]))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert {a["id"] for a in body["alerts"]} == {
        str(world["by_client"]),
        str(world["by_document"]),
        str(world["by_both"]),
    }
    assert response.headers["X-Unread-Count"] == "3"
    by_id = {a["id"]: a for a in body["alerts"]}
    document = by_id[str(world["by_document"])]
    assert document["document_check_id"] == str(world["check_a"])
    assert document["client_id"] is None
    assert document["actions_required"] == ["Apri il controllo."]
    assert by_id[str(world["by_client"])]["document_check_id"] is None
    assert by_id[str(world["by_both"])]["client_id"] == str(world["client_a"])


def test_another_organisation_sees_only_its_own(client, world):
    body = client.get("/api/v1/alerts", headers=_headers(world["org_b"])).json()
    assert [a["id"] for a in body["alerts"]] == [str(world["of_b"])]
    assert body["total"] == 1
    stranger = client.get("/api/v1/alerts", headers=_headers(uuid.uuid4())).json()
    assert stranger["alerts"] == [] and stranger["total"] == 0


def test_filters_still_apply(client, world):
    headers = _headers(world["org_a"])
    by_client = client.get(f"/api/v1/alerts?client_id={world['client_a']}", headers=headers).json()
    assert {a["id"] for a in by_client["alerts"]} == {
        str(world["by_client"]),
        str(world["by_both"]),
    }
    low = client.get("/api/v1/alerts?severity=LOW", headers=headers).json()
    assert [a["id"] for a in low["alerts"]] == [str(world["by_client"])]


def test_summary_counts_them(client, world):
    summary = client.get("/api/v1/alerts/summary", headers=_headers(world["org_a"])).json()
    assert summary["total"] == 3 and summary["total_unread"] == 3
    assert {row["severity"]: row["count"] for row in summary["by_severity"]} == {
        "HIGH": 2,
        "LOW": 1,
    }
    assert summary["by_framework"] == [{"framework": "GDPR", "count": 3}]
    other = client.get("/api/v1/alerts/summary", headers=_headers(world["org_b"])).json()
    assert other["total"] == 1


def test_get_read_and_dismiss_a_document_alert(client, db, world):
    headers = _headers(world["org_a"])
    alert_id = world["by_document"]
    assert client.get(f"/api/v1/alerts/{alert_id}", headers=headers).status_code == 200
    read = client.patch(f"/api/v1/alerts/{alert_id}/read", headers=headers)
    assert read.status_code == 200 and read.json()["is_read"] is True
    dismissed = client.patch(f"/api/v1/alerts/{alert_id}/dismiss", headers=headers)
    assert dismissed.status_code == 200 and dismissed.json()["is_dismissed"] is True
    summary = client.get("/api/v1/alerts/summary", headers=headers).json()
    assert summary["total"] == 2
    (row,) = db.rows(Alert, id=alert_id)
    assert row.is_read and row.is_dismissed


def test_the_alert_of_another_organisation_is_not_found(client, db, world):
    headers = _headers(world["org_a"])
    foreign = world["of_b"]
    assert client.get(f"/api/v1/alerts/{foreign}", headers=headers).status_code == 404
    assert client.patch(f"/api/v1/alerts/{foreign}/read", headers=headers).status_code == 404
    assert client.patch(f"/api/v1/alerts/{foreign}/dismiss", headers=headers).status_code == 404
    (row,) = db.rows(Alert, id=foreign)
    assert not row.is_read and not row.is_dismissed
