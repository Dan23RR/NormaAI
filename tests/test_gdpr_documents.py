"""GDPR export and erasure cover the document checks (src/api/routers/gdpr.py).

The routes run their real queries on SQLite (tests/documents_support.Database)
against two organisations with document checks, watched provisions and alerts:
the export gives an organisation all of its own and nothing else, the erasure
deletes all of its own and nothing else.

tests/test_gdpr_router.py keeps covering auth, roles and the confirmation guard
with a scripted session.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Alert, Client, DocumentCheck, DocumentDependency, User
from src.document_check import service
from tests.documents_support import (
    ART13_AMENDED,
    CLEAN_DOCUMENT,
    GDPR,
    Database,
    FakeSource,
    article,
)

CHECKED = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


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

        from src.api.main import app, app_state, limiter
        from src.api.routers import gdpr

        app_state.indexer = MagicMock()
        limiter.enabled = False
        with patch.object(gdpr, "db_manager", db), patch("src.api.app_state.app_state", app_state):
            try:
                yield TestClient(app)
            finally:
                app.dependency_overrides.clear()


def _admin(org_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, org_id=org_id, role="admin")
    return {"Authorization": f"Bearer {token}"}


async def _organisation(db: Database, name: str) -> dict:
    """An organisation with a client, two checks (one of the client) and, after a
    change in the GDPR, the alert of each."""
    org = db.add_org(name)
    user = db.add_user(org, f"admin@{name.lower()}.test", role="admin")
    acme = db.add_client(org, f"Cliente di {name}")
    source = FakeSource()
    checks = []
    for filename, client_id in ((f"{name}-1.txt", None), (f"{name}-2.txt", acme)):
        outcome = service.check_document(
            source, filename=filename, text=CLEAN_DOCUMENT, now=CHECKED
        )
        async with db.session(org_id=str(org)) as session:
            row, _ = await service.store_check(
                session, outcome, org_id=org, user_id=user, client_id=client_id, watch=True
            )
            await session.commit()
            checks.append(row.id)
    source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
    for check_id in checks:
        async with db.session(org_id=str(org)) as session:
            row, dependencies = await service.load_check(session, org, check_id)
            stored = [service.dependency_json(d) for d in dependencies]
            answers = service.recheck_provisions(stored, source)
            await service.apply_recheck(
                session, row, dependencies, [answers.get(service.provision_key(d)) for d in stored]
            )
            await session.commit()
    return {"org": org, "user": user, "client": acme, "checks": checks}


@pytest.fixture
async def world(db):
    return {"alfa": await _organisation(db, "Alfa"), "beta": await _organisation(db, "Beta")}


def test_the_fixture_is_what_the_tests_assume(db, world):
    assert len(db.rows(DocumentCheck)) == 4
    assert len(db.rows(DocumentDependency)) == 8
    assert len(db.rows(Alert)) == 4
    assert {bool(a.client_id) for a in db.rows(Alert)} == {True, False}


def test_export_has_the_checks_their_provisions_and_their_alerts(client, db, world):
    alfa = world["alfa"]
    response = client.get("/api/v1/gdpr/export", headers=_admin(alfa["org"], alfa["user"]))
    assert response.status_code == 200
    data = response.json()

    checks = data["document_checks"]
    assert {c["id"] for c in checks} == {str(i) for i in alfa["checks"]}
    assert {c["filename"] for c in checks} == {"Alfa-1.txt", "Alfa-2.txt"}
    one = next(c for c in checks if c["filename"] == "Alfa-2.txt")
    assert one["org_id"] == str(alfa["org"]) and one["client_id"] == str(alfa["client"])
    assert one["created_by"] == str(alfa["user"])
    assert one["needs_review"] is True and one["watch"] is True
    assert len(one["document_sha256"]) == 64
    assert [f["raw"] for f in one["findings"]] == [
        "art. 13 del GDPR",
        "art. 50, par. 1, dell'AI Act",
    ]

    dependencies = data["document_dependencies"]
    assert len(dependencies) == 4
    assert {d["check_id"] for d in dependencies} == {str(i) for i in alfa["checks"]}
    changed = [d for d in dependencies if d["state"] == "changed"]
    assert len(changed) == 2 and {d["act"] for d in changed} == {GDPR}
    assert changed[0]["cited_as"] == ["art. 13 del GDPR"]
    # Everything of the tenant, not the text of the law.
    assert all("official_text" not in d for d in dependencies)
    assert all("text" not in d["change"] for d in changed)
    assert changed[0]["change"]["version"] == "02016R0679-20270101"

    alerts = data["alerts"]
    assert {a["document_check_id"] for a in alerts} == {str(i) for i in alfa["checks"]}
    assert {a["client_id"] for a in alerts} == {None, str(alfa["client"])}
    assert data["users"][0]["notify_document_changes"] is True

    # Nothing of the other organisation.
    assert "Beta" not in response.text
    for check_id in world["beta"]["checks"]:
        assert str(check_id) not in response.text


def test_erase_deletes_the_checks_their_provisions_and_their_alerts(client, db, world):
    alfa, beta = world["alfa"], world["beta"]
    response = client.post(
        "/api/v1/gdpr/erase",
        json={"confirm_org_id": str(alfa["org"])},
        headers=_admin(alfa["org"], alfa["user"]),
    )
    assert response.status_code == 200
    assert response.json()["deleted"] == {
        "clients": 1,
        "conversations": 0,
        "assessments": 0,
        "alerts": 2,
        "document_checks": 2,
        "document_dependencies": 4,
    }

    assert db.rows(DocumentCheck, org_id=alfa["org"]) == []
    assert db.rows(DocumentDependency, org_id=alfa["org"]) == []
    assert db.rows(Client, org_id=alfa["org"]) == []
    # Users and the organisation stay (account closure is another flow).
    assert len(db.rows(User, org_id=alfa["org"])) == 1

    # The other organisation is untouched.
    assert {r.id for r in db.rows(DocumentCheck)} == set(beta["checks"])
    assert len(db.rows(DocumentDependency, org_id=beta["org"])) == 4
    assert {a.document_check_id for a in db.rows(Alert)} == set(beta["checks"])
    assert len(db.rows(Client, org_id=beta["org"])) == 1

    # A second erasure finds nothing.
    again = client.post(
        "/api/v1/gdpr/erase",
        json={"confirm_org_id": str(alfa["org"])},
        headers=_admin(alfa["org"], alfa["user"]),
    )
    assert again.json()["deleted"] == {
        "clients": 0,
        "conversations": 0,
        "assessments": 0,
        "alerts": 0,
        "document_checks": 0,
        "document_dependencies": 0,
    }
    assert len(db.rows(DocumentCheck)) == 2


def test_erase_with_documents_but_no_clients(client, db):
    org = db.add_org("Solo documenti")
    user = db.add_user(org, "admin@solo.test", role="admin")
    row = DocumentCheck(
        id=uuid.uuid4(),
        org_id=org,
        filename="nota.txt",
        document_sha256="0" * 64,
        lang="IT",
        status="a_posto",
        counts={},
        findings=[],
        checked_at=CHECKED,
    )
    alert = Alert(
        id=uuid.uuid4(),
        document_check_id=row.id,
        severity="HIGH",
        framework="GDPR",
        title="Documento da rivedere: nota.txt",
        description="x",
    )
    with db.sync_session() as session:
        session.add(row)
        session.flush()
        session.add(alert)
        session.commit()
    response = client.post(
        "/api/v1/gdpr/erase", json={"confirm_org_id": str(org)}, headers=_admin(org, user)
    )
    assert response.json()["deleted"]["alerts"] == 1
    assert response.json()["deleted"]["document_checks"] == 1
    assert db.rows(Alert) == [] and db.rows(DocumentCheck) == []
