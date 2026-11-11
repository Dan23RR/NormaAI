"""Italian law through the documents API and the surveillance.

The Normattiva source (src/document_check/normattiva.py) and the documents API
(src/api/routers/documents.py, src/document_check/{serialize,service,
surveillance}.py) were written apart. These tests push Italian references
through both, with the composite source of production
(``sources.OfficialSources``) made of the two fakes of tests/documents_support:
``POST /check``, storage, ``GET /checks/{id}``, the HTML report, the re-check
and the weekly surveillance with its alert and email. What must hold for an
Italian provision: source ``normattiva``, the URN as act id, the link to
Normattiva, the day of the text read as version, and every Italian outcome with
its group.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from datetime import UTC, date, datetime
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Alert, DocumentCheck, DocumentDependency
from src.document_check import service, surveillance
from src.document_check.check import build_lock, check_text
from src.document_check.sources import OfficialSources
from tests.documents_support import (
    AI_LAW,
    BUDGET,
    GDPR,
    IT_ART13,
    IT_ART13_AMENDED,
    ITALIAN_DOCUMENT,
    PRIVACY,
    WORKERS,
    Database,
    FakeItalian,
    FakeSource,
)

BASE = "/api/v1/documents"
NORMATTIVA = "https://www.normattiva.it/uri-res/N2Ls?"
UNKNOWN_ACT = "urn:nir:stato:legge:2025;999"

# Each Italian reference of ITALIAN_DOCUMENT: (act, status code, group).
ITALIAN_OUTCOMES = [
    (AI_LAW, "verificata", "a_posto"),
    (PRIVACY, "modifica_pubblicata", "controllare"),
    (WORKERS, "sentenza_in_nota", "controllare"),
    (UNKNOWN_ACT, "atto_da_controllare", "controllare"),
    (BUDGET, "letto_in_parte", "controllare"),
]


def _italian(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """Evict the app and router modules this file imported (see test_documents_router.py)."""
    yield
    for name in list(sys.modules):
        if (
            name == "src.api.main"
            or name.startswith("src.api.routers")
            or name == "src.auth.router"
        ):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _no_jobs_left_behind():
    yield
    deadline = time.time() + 5
    while service._RUNNING and time.time() < deadline:
        time.sleep(0.01)
    service._RUNNING.clear()


@pytest.fixture
def db():
    return Database()


@pytest.fixture
def italian():
    return FakeItalian()


@pytest.fixture
def source(italian):
    return OfficialSources(FakeSource(), italian)  # type: ignore[arg-type]


@pytest.fixture
def client(db, source):
    from fastapi.testclient import TestClient

    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        mock_settings.return_value = get_settings()

        from src.api.main import app, limiter
        from src.api.routers import documents

        limiter.enabled = False
        app.dependency_overrides[documents.get_text_source] = lambda: source
        with patch.object(documents, "db_manager", db):
            try:
                yield TestClient(app)
            finally:
                limiter.enabled = False
                app.dependency_overrides.clear()


@pytest.fixture
def headers(db):
    org_id = db.add_org("Studio Alfa")
    user_id = db.add_user(org_id, f"{uuid.uuid4().hex[:8]}@example.test")
    token = create_access_token(user_id=user_id, org_id=org_id, role="member")
    return {"Authorization": f"Bearer {token}"}


def _by_act(items, act):
    found = [item for item in items if item["act"]["id"] == act]
    assert len(found) == 1, [item["act"]["id"] for item in items]
    return found[0]


def _post(client, headers):
    response = client.post(
        f"{BASE}/check",
        json={"text": ITALIAN_DOCUMENT, "filename": "nota.txt", "document_date": "2026-03-15"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# ─── Check, storage, detail, report ──────────────────────────────────


class TestItalianCheck:
    def test_every_italian_outcome_travels_through_the_api(self, client, headers):
        body = _post(client, headers)
        today = body["checked_at"][:10]
        findings = body["findings"]
        assert len(findings) == 6
        for act, code, group in ITALIAN_OUTCOMES:
            finding = _by_act(findings, act)
            assert finding["act"]["source"] == "normattiva"
            assert (finding["status"]["code"], finding["group"]) == (code, group)
            assert finding["url"].startswith(NORMATTIVA + act)
        gdpr = _by_act(findings, GDPR)
        assert gdpr["act"]["source"] == "eurlex" and gdpr["status"]["code"] == "verificata"
        assert body["status"] == "controllare"
        assert body["counts"] == {"correggere": 0, "controllare": 4, "a_posto": 2, "non_coperto": 0}

        # A provision read on Normattiva: the day of the text read is its version.
        verified = _by_act(findings, AI_LAW)
        assert verified["version"] == {
            "id": today,
            "as_of": today,
            "label": f"testo vigente al {_italian(today)}",
        }
        assert verified["url"] == f"{NORMATTIVA}{AI_LAW}~art13!vig={today}"
        assert verified["dependency"] == {"source": "normattiva", "act": AI_LAW, "key": "art:13"}
        assert verified["official_quote"]
        # The act Normattiva does not know has no version and no dependency.
        unknown = _by_act(findings, UNKNOWN_ACT)
        assert unknown["version"] is None and unknown["dependency"] is None
        assert unknown["url"] == NORMATTIVA + UNKNOWN_ACT

        dependencies = {d["act"]: d for d in body["dependencies"]}
        assert set(dependencies) == {AI_LAW, PRIVACY, WORKERS, BUDGET, GDPR}
        for act in (AI_LAW, PRIVACY, WORKERS, BUDGET):
            dependency = dependencies[act]
            assert dependency["source"] == "normattiva" and dependency["state"] == "current"
            assert dependency["version"] == dependency["as_of"] == today
            assert dependency["fingerprint"].startswith("sha256:")
        assert dependencies[AI_LAW]["key"] == "art:13"
        assert dependencies[AI_LAW]["article"] == "Art. 13"
        assert dependencies[GDPR]["source"] == "eurlex"

    def test_storage_and_detail_say_the_same(self, client, db, headers):
        body = _post(client, headers)
        assert client.get(f"{BASE}/checks/{body['id']}", headers=headers).json() == body
        rows = {row.act: row for row in db.rows(DocumentDependency)}
        assert rows[AI_LAW].source == "normattiva" and rows[AI_LAW].official_text == IT_ART13
        (stored,) = db.rows(DocumentCheck)
        assert {f["act"]["id"] for f in stored.findings} >= {AI_LAW, PRIVACY, UNKNOWN_ACT}

    def test_html_report(self, client, headers):
        body = _post(client, headers)
        today = body["checked_at"][:10]
        response = client.get(f"{BASE}/checks/{body['id']}/report", headers=headers)
        assert response.status_code == 200
        html = response.text
        assert "sui testi consolidati di EUR-Lex e sui testi vigenti di Normattiva" in html
        for label in (
            "Modifica pubblicata, non ancora in vigore",
            "Sentenza della Corte costituzionale in nota",
            "Estremi dell&#x27;atto da controllare",
            "Articolo letto solo in parte",
            "Citazione verificata",
        ):
            assert label in html
        assert "Testo vigente su Normattiva" in html
        assert f"{AI_LAW}~art13!vig={today}" in html
        assert "Creative Commons CC BY 4.0" in html


# ─── Re-check ────────────────────────────────────────────────────────


class TestItalianRecheck:
    def test_nothing_changed(self, client, db, headers):
        body = _post(client, headers)
        again = client.post(f"{BASE}/checks/{body['id']}/recheck", headers=headers).json()
        assert again["needs_review"] is False
        assert again["findings"] == body["findings"]
        assert {d["state"] for d in again["dependencies"]} == {"current"}
        assert db.rows(Alert) == []

    def test_a_changed_and_a_repealed_article(self, client, db, headers, italian):
        body = _post(client, headers)
        italian.replace_text(AI_LAW, "art:13", IT_ART13_AMENDED)
        italian.remove(WORKERS, "art:4")
        today = date.today().isoformat()

        again = client.post(f"{BASE}/checks/{body['id']}/recheck", headers=headers).json()

        assert again["needs_review"] is True and again["status"] == "correggere"
        changed = _by_act(again["findings"], AI_LAW)
        assert changed["group"] == "correggere"
        assert changed["status"] == {
            "code": "cambiato_dopo_controllo",
            "label": "Cambiato dopo il controllo",
        }
        assert changed["before"]["text"] == IT_ART13
        assert changed["after_text"] == IT_ART13_AMENDED
        assert changed["version"]["id"] == today
        assert changed["url"] == f"{NORMATTIVA}{AI_LAW}~art13!vig={today}"
        removed = _by_act(again["findings"], WORKERS)
        assert removed["status"]["code"] == "soppresso_dopo_controllo"
        assert removed["group"] == "correggere" and removed["after_text"] is None

        dependencies = {d["act"]: d for d in again["dependencies"]}
        assert dependencies[AI_LAW]["state"] == "changed"
        assert dependencies[AI_LAW]["current_version"] == today
        assert dependencies[AI_LAW]["version"] == body["checked_at"][:10]
        assert dependencies[WORKERS]["state"] == "removed"
        assert dependencies[WORKERS]["message"] == "Art. 4 non c'è più su Normattiva."
        assert dependencies[PRIVACY]["state"] == "current"

        (alert,) = db.rows(Alert)
        assert alert.framework == ""
        assert f"Legge 132/2025, Art. 13 (testo vigente al {_italian(today)})" in alert.description
        assert (
            "Legge 300/1970 (Statuto dei lavoratori), Art. 4 (non c'è più nel testo vigente)"
            in alert.description
        )

        html = client.get(f"{BASE}/checks/{body['id']}/report", headers=headers).text
        assert "Cambiato dopo il controllo" in html and "<ins>prevalentemente</ins>" in html

    def test_normattiva_down_is_not_a_change(self, client, db, headers, italian):
        body = _post(client, headers)

        def down(*_args, **_kwargs):
            from src.document_check.official import TextUnavailableError

            raise TextUnavailableError("Normattiva non ha risposto")

        italian.article = down  # type: ignore[method-assign]
        again = client.post(f"{BASE}/checks/{body['id']}/recheck", headers=headers).json()
        states = {d["act"]: d["state"] for d in again["dependencies"]}
        assert states[AI_LAW] == "unavailable" and states[GDPR] == "current"
        assert again["needs_review"] is False and db.rows(Alert) == []


# ─── The weekly surveillance ─────────────────────────────────────────

CHECKED = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)
API = "https://api.example.test"
APP = "https://app.example.test"


async def test_surveillance_alerts_and_emails_on_an_italian_change(
    db, source, italian, monkeypatch
):
    settings = get_settings().model_copy(
        update={"api_public_url": API, "normaai_public_url": APP, "api_domain": ""}
    )
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    sent: list[dict] = []
    org = db.add_org()
    db.add_user(org, "anna@example.test", name="Anna")
    with (
        patch("src.document_check.service.get_settings", return_value=settings),
        patch("src.document_check.surveillance.get_settings", return_value=settings),
        patch(
            "resend.Emails.send", side_effect=lambda payload: sent.append(payload) or {"id": "1"}
        ),
    ):
        outcome = service.check_document(
            source, filename="nota.txt", text=ITALIAN_DOCUMENT, now=CHECKED
        )
        async with db.session(org_id=str(org)) as session:
            row, _ = await service.store_check(
                session, outcome, org_id=org, user_id=None, client_id=None, watch=True
            )
            await session.commit()
        italian.replace_text(AI_LAW, "art:13", IT_ART13_AMENDED)

        report = await surveillance.run(db.session, source)
        again = await surveillance.run(db.session, source)

    assert report.provisions == 5 and report.unanswered == 0
    assert (report.checks_changed, report.alerts, report.emails_sent) == (1, 1, 1)
    assert (again.alerts, again.emails_sent) == (0, 0)
    (dependency,) = db.rows(DocumentDependency, act=AI_LAW)
    assert dependency.state == "changed" and dependency.source == "normattiva"
    assert dependency.change["version"] == date.today().isoformat()
    assert dependency.change["url"].startswith(NORMATTIVA + AI_LAW)
    (alert,) = db.rows(Alert)
    assert alert.document_check_id == row.id
    expected = f"Legge 132/2025, Art. 13 (testo vigente al {_italian(date.today().isoformat())})"
    assert expected in alert.description
    (email,) = sent
    assert expected in email["text"] and f"{APP}/app/controlla/{row.id}" in email["text"]


# ─── The shared source of the API process ────────────────────────────


def test_the_locked_source_reads_italian_law_under_its_lock(italian):
    locked = service._LockedSource(OfficialSources(FakeSource(), italian))  # type: ignore[arg-type]
    seen: list[bool] = []
    article = italian.article

    def spy(*args):
        # RLock has no public "held" test: another thread must not get it now.
        got = []
        probe = threading.Thread(target=lambda: got.append(locked._lock.acquire(blocking=False)))
        probe.start()
        probe.join()
        if got[0]:
            locked._lock.release()
        seen.append(not got[0])
        return article(*args)

    italian.article = spy  # type: ignore[method-assign]
    check = check_text(ITALIAN_DOCUMENT, locked, document="nota.txt", today="2026-11-11")
    assert {f.status.code for f in check.findings} >= {"verificata", "modifica_pubblicata"}
    assert seen and all(seen)
    assert {entry["fonte"] for entry in build_lock(check)["dipendenze"]} == {"normattiva", "eurlex"}
    assert service._LockedSource(FakeSource()).italian is None
