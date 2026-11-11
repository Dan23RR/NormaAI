"""Tests for the documents router (src/api/routers/documents.py).

Routes under test, all under /api/v1/documents:
- POST   /check                    a file or a text -> 201 with the stored check
- GET    /checks                   list, filters, paging
- GET    /checks/{id}              the full object
- DELETE /checks/{id}              204
- POST   /checks/{id}/recheck      the provisions against the texts in force
- GET    /checks/{id}/report       the HTML report
- GET    /preferences, PATCH /preferences
- GET    /unsubscribe?token=       no login, signed token

Pattern: the bare ``TestClient(app)`` of the other router tests (no lifespan,
rate limiting off), with two differences. The official texts come from a
``FakeSource`` injected through the ``get_text_source`` dependency, and the
router's ``db_manager`` is replaced by tests/documents_support.Database: the
real tables on SQLite in memory, so that filters, paging and above all the
separation between two organisations are what the SQL really does. SQLite has
no row-level security: these tests prove the ``org_id`` filter of every query,
the PostgreSQL policies are checked by the CI ``schema`` job and by hand.
"""

from __future__ import annotations

import hashlib
import io
import sys
import tempfile
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import Alert, DocumentCheck, DocumentDependency, User
from src.document_check import service
from tests.documents_support import (
    AI_ACT,
    ART13,
    ART13_AMENDED,
    CLEAN_DOCUMENT,
    DOCUMENT,
    GDPR,
    Database,
    FakeSource,
    article,
)

BASE = "/api/v1/documents"


@pytest.fixture(autouse=True)
def _restore_module_cache():
    """Evict the app and router modules this file imported (see test_clients_router.py)."""
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
def source():
    return FakeSource()


@pytest.fixture
def app_objects(db, source):
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True),
        patch.dict(
            "sys.modules",
            {
                "src.nlp.embedding.indexer": MagicMock(),
                "src.db.engine": MagicMock(),
            },
        ),
    ):
        mock_settings.return_value = get_settings()

        from src.api.main import app, limiter
        from src.api.routers import documents

        limiter.enabled = False
        app.dependency_overrides[documents.get_text_source] = lambda: source
        with patch.object(documents, "db_manager", db):
            try:
                yield app, limiter, documents
            finally:
                limiter.enabled = False
                app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    return TestClient(app_objects[0])


class Tenant:
    """An organisation with one user and the headers of that user's token."""

    def __init__(self, db: Database, name: str, role: str = "member") -> None:
        self.org_id = db.add_org(name)
        self.user_id = db.add_user(
            self.org_id, f"{uuid.uuid4().hex[:8]}@example.test", role=role, name=name
        )
        token = create_access_token(user_id=self.user_id, org_id=self.org_id, role=role)
        self.headers = {"Authorization": f"Bearer {token}"}

    def user(self, db: Database, role: str) -> dict[str, str]:
        user_id = db.add_user(self.org_id, f"{uuid.uuid4().hex[:8]}@example.test", role=role)
        token = create_access_token(user_id=user_id, org_id=self.org_id, role=role)
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alpha(db):
    return Tenant(db, "Studio Alfa")


@pytest.fixture
def beta(db):
    return Tenant(db, "Studio Beta")


def _check(client, tenant, text=CLEAN_DOCUMENT, **fields):
    payload = {"text": text, "filename": fields.pop("filename", "nota.txt"), **fields}
    return client.post(f"{BASE}/check", json=payload, headers=tenant.headers)


def _upload(client, tenant, name, data, **fields):
    return client.post(
        f"{BASE}/check",
        files={"file": (name, data)},
        data={k: str(v) for k, v in fields.items()},
        headers=tenant.headers,
    )


def _settings(**overrides):
    """The test settings with some limits changed, for ``patch('...get_settings')``."""
    return get_settings().model_copy(update=overrides)


# ─── Access ──────────────────────────────────────────────────────────


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("post", "/check"),
            ("get", "/checks"),
            ("get", f"/checks/{uuid.uuid4()}"),
            ("delete", f"/checks/{uuid.uuid4()}"),
            ("post", f"/checks/{uuid.uuid4()}/recheck"),
            ("get", f"/checks/{uuid.uuid4()}/report"),
            ("get", "/preferences"),
            ("patch", "/preferences"),
        ],
    )
    def test_every_route_wants_a_token(self, client, method, path):
        assert getattr(client, method)(f"{BASE}{path}").status_code == 401
        bad = {"Authorization": "Bearer not-a-token"}
        assert getattr(client, method)(f"{BASE}{path}", headers=bad).status_code == 401

    def test_a_viewer_reads_but_does_not_check_or_delete(self, client, db, alpha):
        created = _check(client, alpha).json()
        viewer = alpha.user(db, "viewer")
        assert client.get(f"{BASE}/checks", headers=viewer).json()["total"] == 1
        assert client.get(f"{BASE}/checks/{created['id']}", headers=viewer).status_code == 200
        assert (
            client.get(f"{BASE}/checks/{created['id']}/report", headers=viewer).status_code == 200
        )
        assert client.get(f"{BASE}/preferences", headers=viewer).status_code == 200
        for response in (
            client.post(f"{BASE}/check", json={"text": CLEAN_DOCUMENT}, headers=viewer),
            client.delete(f"{BASE}/checks/{created['id']}", headers=viewer),
            client.post(f"{BASE}/checks/{created['id']}/recheck", headers=viewer),
        ):
            assert response.status_code == 403
            assert response.json()["detail"] == "Il tuo ruolo consente solo la lettura."
        assert len(db.rows(DocumentCheck)) == 1

    def test_checking_needs_a_verified_email_when_the_deployment_asks_for_it(
        self, client, db, alpha
    ):
        with (
            patch(
                "src.auth.dependencies.get_settings",
                return_value=_settings(require_email_verification=True),
            ),
            patch("src.auth.dependencies._email_verified_in_db", return_value=False),
        ):
            response = _check(client, alpha)
        assert response.status_code == 403
        assert db.rows(DocumentCheck) == []

    def test_preflight_allows_patch(self, client):
        response = client.options(
            f"{BASE}/preferences",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert response.status_code == 200
        assert "PATCH" in response.headers["access-control-allow-methods"]

    def test_routes_are_in_the_openapi_schema(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        for path in (
            "/check",
            "/checks",
            "/checks/{check_id}",
            "/checks/{check_id}/recheck",
            "/checks/{check_id}/report",
            "/preferences",
            "/unsubscribe",
        ):
            assert f"{BASE}{path}" in paths
        assert set(paths[f"{BASE}/unsubscribe"]) == {"get", "post"}
        operation_ids = [
            operation["operationId"]
            for path, operations in paths.items()
            if path.startswith(BASE)
            for operation in operations.values()
        ]
        assert len(operation_ids) == len(set(operation_ids))
        body = paths[f"{BASE}/check"]["post"]["requestBody"]["content"]
        assert set(body) == {"multipart/form-data", "application/json"}


# ─── POST /check ─────────────────────────────────────────────────────


class TestCreate:
    def test_a_pasted_text_gives_the_full_object(self, client, db, alpha):
        response = _check(client, alpha, DOCUMENT, filename="informativa.txt")
        assert response.status_code == 201
        body = response.json()
        assert list(body)[:13] == [
            "id",
            "client_id",
            "filename",
            "document_sha256",
            "document_date",
            "checked_at",
            "lang",
            "watch",
            "status",
            "needs_review",
            "counts",
            "findings",
            "dependencies",
        ]
        assert uuid.UUID(body["id"])
        assert body["client_id"] is None
        assert body["filename"] == "informativa.txt"
        assert body["document_sha256"] == hashlib.sha256(DOCUMENT.encode()).hexdigest()
        assert body["document_date"] is None
        assert body["checked_at"].endswith("Z") and len(body["checked_at"]) == 20
        assert body["lang"] == "IT"
        assert body["watch"] is True
        assert body["status"] == "correggere"
        assert body["needs_review"] is False
        assert body["counts"] == {
            "correggere": 3,
            "controllare": 1,
            "a_posto": 1,
            "non_coperto": 1,
        }
        assert [f["status"]["code"] for f in body["findings"]] == [
            "superata",
            "alterata",
            "inesistente",
            "verificata",
            "non_coperto",
            "atto_mancante",
        ]
        assert [(d["act"], d["key"], d["state"]) for d in body["dependencies"]] == [
            (AI_ACT, "art:4", "current"),
            (AI_ACT, "art:50", "current"),
            (GDPR, "art:13", "current"),
        ]
        assert all("text" not in d for d in body["dependencies"])

    def test_what_is_stored(self, client, db, alpha):
        secret = "Compenso riservato concordato con la cliente Verdi: 9.500 euro."
        text = f"{secret}\n{CLEAN_DOCUMENT}{secret}\n"
        body = _check(client, alpha, text).json()
        (row,) = db.rows(DocumentCheck)
        assert str(row.id) == body["id"]
        assert row.org_id == alpha.org_id and row.created_by == alpha.user_id
        assert row.filename == "nota.txt" and row.status == "a_posto"
        assert row.document_sha256 == hashlib.sha256(text.encode()).hexdigest()
        dependencies = db.rows(DocumentDependency, check_id=row.id)
        assert {d.org_id for d in dependencies} == {alpha.org_id}
        assert [
            (d.position, d.act, d.key) for d in sorted(dependencies, key=lambda d: d.position)
        ] == [
            (0, GDPR, "art:13"),
            (1, AI_ACT, "art:50"),
        ]
        assert dependencies[0].official_text  # the official text, which is public
        # Nothing of the document beyond the lines with a reference.
        kept = repr(row.findings) + repr([(d.cited_as, d.change) for d in dependencies])
        assert "Verdi" not in kept and "9.500" not in kept
        assert all(len(f["context"]) <= 160 for f in row.findings)

    def test_a_text_file(self, client, db, alpha):
        data = CLEAN_DOCUMENT.encode("utf-8")
        response = _upload(client, alpha, "C:\\Documenti\\nota cliente.txt", data)
        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "nota cliente.txt"
        assert body["document_sha256"] == hashlib.sha256(data).hexdigest()
        assert body["counts"]["a_posto"] == 2

    def test_a_text_file_saved_by_an_old_windows_program(self, client, alpha):
        text = "Ai sensi dell'art. 13 del GDPR il titolare «fornisce all'interessato, nel momento in cui i dati personali sono ottenuti, le seguenti informazioni». È così.\n"
        body = _upload(client, alpha, "nota.txt", text.encode("cp1252")).json()
        assert body["findings"][0]["status"]["code"] == "verificata"
        assert (
            "È così" in body["findings"][0]["context"]
            or "ottenuti" in body["findings"][0]["context"]
        )

    def test_a_word_file(self, client, alpha):
        docx = pytest.importorskip("docx")
        document = docx.Document()
        for line in CLEAN_DOCUMENT.strip().split("\n"):
            document.add_paragraph(line)
        buffer = io.BytesIO()
        document.save(buffer)
        response = _upload(client, alpha, "nota.docx", buffer.getvalue())
        assert response.status_code == 201
        body = response.json()
        assert body["filename"] == "nota.docx"
        assert [f["status"]["code"] for f in body["findings"]] == ["verificata", "valido"]
        assert [f["line"] for f in body["findings"]] == [2, 3]

    def test_an_html_file(self, client, alpha):
        html = "<html><body><script>var art = 'art. 99 del GDPR';</script>"
        html += "".join(f"<p>{line}</p>" for line in CLEAN_DOCUMENT.strip().split("\n"))
        html += "</body></html>"
        body = _upload(client, alpha, "nota.html", html.encode("utf-8")).json()
        assert [f["status"]["code"] for f in body["findings"]] == ["verificata", "valido"]

    def _pdf(self, lines):
        canvas_module = pytest.importorskip("reportlab.pdfgen.canvas")
        buffer = io.BytesIO()
        page = canvas_module.Canvas(buffer)
        y = 800
        for line in lines:
            page.drawString(40, y, line)
            y -= 18
        page.save()
        return buffer.getvalue()

    def test_a_pdf_file(self, client, alpha):
        pytest.importorskip("pypdf")
        data = self._pdf(["Nota per il cliente.", "Si applica l'art. 13 del GDPR.", "Fine."])
        response = _upload(client, alpha, "nota.pdf", data)
        assert response.status_code == 201
        finding = response.json()["findings"][0]
        assert finding["raw"] == "art. 13 del GDPR" and finding["status"]["code"] == "valido"

    def test_a_pdf_file_without_pypdf(self, client, alpha):
        # The production image has pypdfium2 (through docling) and not pypdf.
        pytest.importorskip("pypdfium2")
        data = self._pdf(["Nota per il cliente.", "Si applica l'art. 13 del GDPR.", "Fine."])
        with patch.object(service, "_pdf_pages_pypdf", return_value=None):
            response = _upload(client, alpha, "nota.pdf", data)
        assert response.status_code == 201
        assert response.json()["findings"][0]["raw"] == "art. 13 del GDPR"

    def test_a_pdf_when_no_pdf_library_is_installed(self, client, alpha):
        with (
            patch.object(service, "_pdf_pages_pypdf", return_value=None),
            patch.object(service, "_pdf_pages_pdfium", return_value=None),
        ):
            response = _upload(client, alpha, "nota.pdf", b"%PDF-1.4 ...")
        assert response.status_code == 503
        assert "lettura dei PDF non è disponibile" in response.json()["detail"]

    def test_the_upload_stays_in_memory(self, client, alpha, monkeypatch):
        rolled = []
        monkeypatch.setattr(
            tempfile.SpooledTemporaryFile, "rollover", lambda self: rolled.append(1)
        )
        padding = ("Riga senza riferimenti di legge.\n" * 70_000).encode()  # 2.2 MB
        assert len(padding) > 2 * 1024 * 1024
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(document_check_max_chars=5_000_000),
        ):
            response = _upload(client, alpha, "lunga.txt", padding + CLEAN_DOCUMENT.encode())
        assert response.status_code == 201
        assert rolled == []

    def test_document_date_shows_what_changed_after_it(self, client, alpha):
        text = "L'art. 4 dell'AI Act chiede misure per il personale.\n"
        body = _check(client, alpha, text, document_date="2026-03-01").json()
        assert body["document_date"] == "2026-03-01"
        finding = body["findings"][0]
        assert finding["status"]["code"] == "cambiato"
        assert finding["before"]["version_label"] == "testo consolidato al 12/07/2024"
        assert finding["after_text"].startswith("Articolo 4")

    def test_client_watch_and_language(self, client, db, alpha, beta):
        client_id = db.add_client(alpha.org_id)
        body = _check(client, alpha, client_id=str(client_id), watch=False, lang="it").json()
        assert body["client_id"] == str(client_id)
        assert body["watch"] is False and body["lang"] == "IT"
        uploaded = _upload(
            client, alpha, "nota.txt", CLEAN_DOCUMENT.encode(), client_id=client_id, watch="false"
        ).json()
        assert uploaded["client_id"] == str(client_id) and uploaded["watch"] is False

        foreign = db.add_client(beta.org_id, "Cliente di Beta")
        for bad in (str(foreign), str(uuid.uuid4())):
            response = _check(client, alpha, client_id=bad)
            assert response.status_code == 404
            assert response.json()["detail"] == "Cliente non trovato."
        assert _upload(client, alpha, "n.txt", b"art. 13 GDPR", client_id="x").status_code == 404
        assert len(db.rows(DocumentCheck)) == 2

    def test_a_document_without_references(self, client, alpha):
        body = _check(client, alpha, "Buongiorno, in allegato la fattura di ottobre.").json()
        assert body["findings"] == [] and body["dependencies"] == []
        assert body["status"] == "a_posto"
        assert body["counts"] == {"correggere": 0, "controllare": 0, "a_posto": 0, "non_coperto": 0}


class TestCreateRefusals:
    def _detail(self, response, status):
        assert response.status_code == status, response.text
        detail = response.json()["detail"]
        assert isinstance(detail, str) and detail
        return detail

    def test_bad_file_type(self, client, db, alpha):
        for name in ("tabella.xlsx", "foto.png", "senza_estensione"):
            detail = self._detail(_upload(client, alpha, name, b"contenuto"), 415)
            assert detail.startswith("Formato non supportato")
            assert ".docx, .pdf, .html, .txt, .md" in detail
        assert db.rows(DocumentCheck) == []

    def test_file_too_large(self, client, alpha):
        small = _settings(document_check_max_bytes=1024)
        with (
            patch("src.api.routers.documents.get_settings", return_value=small),
            patch("src.document_check.service.get_settings", return_value=small),
        ):
            # Refused while reading, also without a Content-Length to trust.
            detail = self._detail(_upload(client, alpha, "grande.txt", b"x" * 200_000), 413)
            assert detail == "Il file supera il limite di 1 MB."
            just_over = _upload(client, alpha, "grande.txt", b"x" * 1100)
            assert self._detail(just_over, 413) == "Il file supera il limite di 1 MB."
            assert _upload(client, alpha, "ok.txt", b"art. 13 del GDPR").status_code == 201

    def test_default_limit_is_10_mb(self):
        assert get_settings().document_check_max_bytes == 10 * 1024 * 1024
        assert (
            service.file_too_large(10 * 1024 * 1024).detail == "Il file supera il limite di 10 MB."
        )

    def test_text_too_long(self, client, alpha):
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(document_check_max_chars=500),
        ):
            detail = self._detail(_check(client, alpha, CLEAN_DOCUMENT * 5), 413)
        assert detail == (
            "Il testo supera il limite di 500 caratteri: dividi il documento in parti."
        )
        assert "400.000 caratteri" in service.text_too_long(400_000).detail

    def test_too_many_references(self, client, alpha):
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(document_check_max_references=3),
        ):
            detail = self._detail(_check(client, alpha, "Vedi artt. 12-22 del GDPR."), 422)
            assert detail == "Il documento cita più di 3 disposizioni: dividilo in parti."
            assert _check(client, alpha, "Vedi artt. 12-14 del GDPR.").status_code == 201

    def test_empty_and_unreadable_files(self, client, alpha):
        assert self._detail(_upload(client, alpha, "vuoto.txt", b""), 400) == "Il file è vuoto."
        detail = self._detail(_upload(client, alpha, "finto.docx", b"non sono un docx"), 422)
        assert detail.startswith("Non riesco a leggere il file")
        detail = self._detail(_upload(client, alpha, "finto.pdf", b"non sono un pdf"), 422)
        assert detail.startswith("Non riesco a leggere il file")
        assert self._detail(_upload(client, alpha, "spazi.txt", b"  \n \n"), 422).startswith(
            "Nel file non c'è testo da leggere"
        )

    def test_missing_document_and_malformed_requests(self, client, alpha):
        headers = alpha.headers
        missing = "Carica un file oppure incolla il testo del documento."
        assert (
            self._detail(client.post(f"{BASE}/check", json={"text": "  "}, headers=headers), 422)
            == missing
        )
        no_file = client.post(
            f"{BASE}/check", data={"watch": "true"}, files={"x": ("a", b"b")}, headers=headers
        )
        assert no_file.status_code in (422,)
        for response in (
            client.post(f"{BASE}/check", json={"filename": "x.txt"}, headers=headers),
            client.post(f"{BASE}/check", json=["non", "un", "oggetto"], headers=headers),
            client.post(
                f"{BASE}/check",
                content=b"{non json",
                headers={**headers, "Content-Type": "application/json"},
            ),
        ):
            assert self._detail(response, 422).startswith("Richiesta non valida")
        other = client.post(
            f"{BASE}/check", content=b"art. 13", headers={**headers, "Content-Type": "text/plain"}
        )
        assert self._detail(other, 415).startswith("Richiesta non valida")

    def test_bad_date_language_and_watch(self, client, alpha):
        for bad in ("15/03/2026", "2026-13-01", "ieri", "20260315"):
            detail = self._detail(_check(client, alpha, document_date=bad), 422)
            assert detail == "La data del documento non è valida: usa il formato AAAA-MM-GG."
        assert self._detail(_check(client, alpha, lang="FR"), 422) == (
            "Lingua non supportata: usa IT o EN."
        )
        bad_watch = _upload(client, alpha, "n.txt", b"art. 13 del GDPR", watch="forse")
        assert self._detail(bad_watch, 422).startswith("Richiesta non valida")

    def test_storage_limit(self, client, db, alpha, beta):
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(document_checks_max_per_org=2),
        ):
            assert _check(client, alpha).status_code == 201
            assert _check(client, alpha).status_code == 201
            detail = self._detail(_check(client, alpha), 409)
            assert detail == (
                "Hai raggiunto il limite di 2 controlli salvati: elimina quelli che non servono più."
            )
            # The limit is per organisation.
            assert _check(client, beta).status_code == 201
            first = db.rows(DocumentCheck, org_id=alpha.org_id)[0]
            assert (
                client.delete(f"{BASE}/checks/{first.id}", headers=alpha.headers).status_code == 204
            )
            assert _check(client, alpha).status_code == 201

    def test_an_organisation_with_checks_running_waits(self, client, alpha, beta):
        limit = get_settings().document_check_concurrency_per_org
        service._RUNNING[str(alpha.org_id)] = limit
        try:
            response = _check(client, alpha)
            assert self._detail(response, 429).startswith(
                "La tua organizzazione ha già dei controlli"
            )
            assert response.headers["Retry-After"] == "15"
            assert _check(client, beta).status_code == 201
        finally:
            service._RUNNING.pop(str(alpha.org_id), None)

    def test_time_limit(self, client, db, source, alpha):
        original = source.versions

        def slow(celex):
            time.sleep(0.4)
            return original(celex)

        source.versions = slow
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(document_check_timeout_seconds=0.05),
        ):
            response = _check(client, alpha)
        assert self._detail(response, 504).startswith("Il controllo non si è concluso")
        assert db.rows(DocumentCheck) == []
        # The job goes on to its end and only then frees the organisation's place.
        assert service.running_jobs(str(alpha.org_id)) == 1
        deadline = time.time() + 5
        while service.running_jobs(str(alpha.org_id)) and time.time() < deadline:
            time.sleep(0.02)
        assert service.running_jobs(str(alpha.org_id)) == 0

    def test_an_unexpected_failure_says_nothing_of_the_document(
        self, client, db, source, alpha, capsys
    ):
        def broken(celex):
            raise RuntimeError("boom: " + CLEAN_DOCUMENT)

        source.versions = broken
        response = _check(client, alpha)
        assert (
            self._detail(response, 500) == "Errore interno durante il controllo. Riprova più tardi."
        )
        captured = capsys.readouterr()
        assert "Nota per il cliente" not in captured.out + captured.err
        assert db.rows(DocumentCheck) == []
        assert service.running_jobs(str(alpha.org_id)) == 0

    def test_official_texts_not_reachable(self, client, app_objects, alpha):
        app, _limiter, documents = app_objects
        app.dependency_overrides.pop(documents.get_text_source)
        with patch.object(service, "shared_source", side_effect=service.source_unavailable()):
            response = _check(client, alpha)
        assert self._detail(response, 503).startswith("I testi ufficiali non sono raggiungibili")
        assert response.headers["Retry-After"] == "60"

    def test_an_act_cellar_cannot_list_is_a_finding_not_an_error(self, client, source, alpha):
        source.unreachable = {GDPR}
        body = _check(client, alpha).json()
        assert [f["status"]["code"] for f in body["findings"]] == ["non_disponibile", "valido"]
        assert body["status"] == "controllare"

    def test_hourly_limit_of_its_own(self, client, app_objects, alpha, beta):
        _app, limiter, _documents = app_objects
        limiter.enabled = True
        try:
            with patch(
                "src.api.rate_limit.get_settings",
                return_value=_settings(document_check_rate_limit="2/hour"),
            ):
                assert _check(client, alpha).status_code == 201
                assert _check(client, alpha).status_code == 201
                third = _check(client, alpha)
                assert third.status_code == 429
                assert third.json()["detail"].startswith("Troppe richieste")
                assert int(third.headers["Retry-After"]) > 0
                # Per user: another user is not affected.
                assert _check(client, beta).status_code == 201
        finally:
            limiter.enabled = False
        assert get_settings().document_check_rate_limit == "30/hour"


# ─── List, detail, delete ────────────────────────────────────────────


class TestListAndDetail:
    def test_list_newest_first_with_paging(self, client, alpha):
        ids = [_check(client, alpha, filename=f"doc{i}.txt").json()["id"] for i in range(3)]
        listing = client.get(f"{BASE}/checks", headers=alpha.headers).json()
        assert listing["total"] == 3
        assert {item["id"] for item in listing["items"]} == set(ids)
        times = [item["checked_at"] for item in listing["items"]]
        assert times == sorted(times, reverse=True)
        for item in listing["items"]:
            assert "findings" not in item and "dependencies" not in item
            assert {"id", "client_id", "filename", "document_sha256", "document_date"} <= set(item)
            assert {"checked_at", "lang", "watch", "status", "needs_review", "counts"} <= set(item)
        first = client.get(f"{BASE}/checks?limit=2", headers=alpha.headers).json()
        rest = client.get(f"{BASE}/checks?limit=2&offset=2", headers=alpha.headers).json()
        assert first["total"] == rest["total"] == 3
        assert len(first["items"]) == 2 and len(rest["items"]) == 1
        assert [i["id"] for i in first["items"] + rest["items"]] == [
            i["id"] for i in listing["items"]
        ]
        assert client.get(f"{BASE}/checks?limit=0", headers=alpha.headers).status_code == 422
        assert client.get(f"{BASE}/checks?limit=500", headers=alpha.headers).status_code == 422

    def test_filter_by_client_and_by_needs_review(self, client, db, source, alpha):
        acme = db.add_client(alpha.org_id, "Acme Srl")
        with_client = _check(client, alpha, client_id=str(acme)).json()["id"]
        without = _check(client, alpha, "Vale l'art. 50, par. 1, dell'AI Act.").json()["id"]

        def ids(query):
            listing = client.get(f"{BASE}/checks{query}", headers=alpha.headers).json()
            assert listing["total"] == len(listing["items"])
            return {item["id"] for item in listing["items"]}

        assert ids(f"?client_id={acme}") == {with_client}
        assert ids(f"?client_id={uuid.uuid4()}") == set()
        assert ids("?needs_review=true") == set()
        assert ids("?needs_review=false") == {with_client, without}

        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        for check_id in (with_client, without):
            assert (
                client.post(f"{BASE}/checks/{check_id}/recheck", headers=alpha.headers).status_code
                == 200
            )
        assert ids("?needs_review=true") == {with_client}
        assert ids("?needs_review=false") == {without}
        assert ids(f"?needs_review=true&client_id={acme}") == {with_client}
        assert client.get(f"{BASE}/checks?client_id=x", headers=alpha.headers).status_code == 422

    def test_detail(self, client, alpha):
        created = _check(client, alpha, DOCUMENT).json()
        fetched = client.get(f"{BASE}/checks/{created['id']}", headers=alpha.headers)
        assert fetched.status_code == 200
        assert fetched.json() == created
        missing = client.get(f"{BASE}/checks/{uuid.uuid4()}", headers=alpha.headers)
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Controllo non trovato."
        assert client.get(f"{BASE}/checks/not-a-uuid", headers=alpha.headers).status_code == 422

    def test_delete(self, client, db, source, alpha):
        keep = _check(client, alpha).json()["id"]
        gone = _check(client, alpha).json()["id"]
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{BASE}/checks/{gone}/recheck", headers=alpha.headers)
        assert len(db.rows(Alert)) == 1

        response = client.delete(f"{BASE}/checks/{gone}", headers=alpha.headers)
        assert response.status_code == 204 and response.content == b""
        assert [str(row.id) for row in db.rows(DocumentCheck)] == [keep]
        assert {str(d.check_id) for d in db.rows(DocumentDependency)} == {keep}
        assert db.rows(Alert) == []
        assert client.get(f"{BASE}/checks/{gone}", headers=alpha.headers).status_code == 404
        again = client.delete(f"{BASE}/checks/{gone}", headers=alpha.headers)
        assert again.status_code == 404

    def test_deleting_a_client_deletes_the_checks_of_its_documents(self, client, db, alpha):
        from src.db.models import Client

        acme = db.add_client(alpha.org_id)
        _check(client, alpha, client_id=str(acme))
        other = _check(client, alpha).json()["id"]
        with db.sync_session() as session:
            session.delete(session.get(Client, acme))
            session.commit()
        assert [str(row.id) for row in db.rows(DocumentCheck)] == [other]
        assert {str(d.check_id) for d in db.rows(DocumentDependency)} == {other}


class TestTenantIsolation:
    def test_one_organisation_never_reaches_the_checks_of_another(
        self, client, db, source, alpha, beta
    ):
        mine = _check(client, alpha, DOCUMENT, filename="di-alfa.txt").json()
        theirs = _check(client, beta, CLEAN_DOCUMENT, filename="di-beta.txt").json()

        listing = client.get(f"{BASE}/checks", headers=beta.headers).json()
        assert listing["total"] == 1
        assert [item["id"] for item in listing["items"]] == [theirs["id"]]
        assert "di-alfa.txt" not in str(listing)

        for response in (
            client.get(f"{BASE}/checks/{mine['id']}", headers=beta.headers),
            client.get(f"{BASE}/checks/{mine['id']}/report", headers=beta.headers),
            client.post(f"{BASE}/checks/{mine['id']}/recheck", headers=beta.headers),
            client.delete(f"{BASE}/checks/{mine['id']}", headers=beta.headers),
        ):
            # The same answer as for a check that does not exist.
            assert response.status_code == 404
            assert response.json()["detail"] == "Controllo non trovato."

        # Untouched, and still there for its owner.
        (row,) = db.rows(DocumentCheck, org_id=alpha.org_id)
        assert row.rechecked_at is None
        assert len(db.rows(DocumentDependency, org_id=alpha.org_id)) == 3
        assert client.get(f"{BASE}/checks/{mine['id']}", headers=alpha.headers).json() == mine

    def test_every_session_is_opened_for_the_callers_organisation(self, client, db, alpha, beta):
        created = _check(client, alpha).json()
        client.get(f"{BASE}/checks", headers=beta.headers)
        client.get(f"{BASE}/checks/{created['id']}", headers=alpha.headers)
        client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        client.get(f"{BASE}/preferences", headers=beta.headers)
        client.delete(f"{BASE}/checks/{created['id']}", headers=alpha.headers)
        assert set(db.session_orgs) == {str(alpha.org_id), str(beta.org_id)}
        assert db.session_orgs.count(str(beta.org_id)) == 2

    def test_a_change_alerts_only_the_organisation_of_the_document(
        self, client, db, source, alpha, beta
    ):
        mine = _check(client, alpha).json()
        _check(client, beta)
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{BASE}/checks/{mine['id']}/recheck", headers=alpha.headers)
        (alert,) = db.rows(Alert)
        assert str(alert.document_check_id) == mine["id"]
        assert [r.needs_review for r in db.rows(DocumentCheck, org_id=beta.org_id)] == [False]


# ─── Re-check ────────────────────────────────────────────────────────


class TestRecheck:
    def test_nothing_changed(self, client, db, source, alpha):
        created = _check(client, alpha).json()
        source.asked_versions.clear()
        response = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        assert response.status_code == 200
        body = response.json()
        assert body["needs_review"] is False and body["status"] == "a_posto"
        assert body["rechecked_at"] is not None
        assert body["findings"] == created["findings"]
        assert [d["state"] for d in body["dependencies"]] == ["current", "current"]
        assert all(d["checked_at"] for d in body["dependencies"])
        assert sorted(source.asked_versions) == sorted([GDPR, AI_ACT])
        assert db.rows(Alert) == []

    def test_a_changed_provision_marks_the_check_and_writes_one_alert(
        self, client, db, source, alpha
    ):
        created = _check(client, alpha).json()
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        body = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()

        assert body["needs_review"] is True
        assert body["status"] == "correggere"
        assert body["counts"] == {"correggere": 1, "controllare": 0, "a_posto": 1, "non_coperto": 0}
        changed = body["findings"][0]
        assert changed["status"] == {"code": "cambiato", "label": "Cambiato dopo il controllo"}
        assert changed["before"]["text"] == ART13 and changed["after_text"] == ART13_AMENDED
        assert changed["version"]["id"] == "02016R0679-20270101"
        gdpr, ai_act = body["dependencies"]
        assert gdpr["state"] == "changed" and gdpr["changed_at"].endswith("Z")
        assert gdpr["version"] == "02016R0679-20160504"  # the text of the day of the check
        assert gdpr["current_version"] == "02016R0679-20270101"
        assert gdpr["message"] == "Art. 13 è cambiato nel testo consolidato al 01/01/2027."
        assert ai_act["state"] == "current" and ai_act["changed_at"] is None

        (alert,) = db.rows(Alert)
        assert str(alert.document_check_id) == created["id"]
        assert alert.client_id is None
        assert alert.severity == "HIGH" and alert.framework == "GDPR"
        assert alert.title == "Documento da rivedere: nota.txt"
        assert alert.description == (
            "Dopo il controllo è cambiata una disposizione citata nel documento: "
            "GDPR, Art. 13 (testo consolidato al 01/01/2027)."
        )
        assert alert.actions_required == service.ALERT_ACTIONS
        assert alert.is_read is False and alert.is_dismissed is False

        # The detail and the list say the same.
        assert client.get(f"{BASE}/checks/{created['id']}", headers=alpha.headers).json() == body
        listed = client.get(f"{BASE}/checks", headers=alpha.headers).json()["items"][0]
        assert listed["needs_review"] is True and listed["status"] == "correggere"

    def test_checking_again_does_not_write_a_second_alert(self, client, db, source, alpha):
        created = _check(client, alpha).json()
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        first = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        (alert,) = db.rows(Alert)
        with db.sync_session() as session:
            session.get(Alert, alert.id).is_read = True
            session.commit()
        second = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        assert second["dependencies"][0]["changed_at"] == first["dependencies"][0]["changed_at"]
        (same,) = db.rows(Alert)
        assert same.id == alert.id and same.is_read is True

        # Another provision of the same document changes: the alert is brought
        # up to date and unread again, still one.
        source.publish(
            AI_ACT,
            "2027-02-01",
            [article("Art. 4", "Articolo 4\nNuovo."), article("Art. 50", "Articolo 50\n1. Nuovo.")],
        )
        third = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        assert [d["state"] for d in third["dependencies"]] == ["changed", "changed"]
        (updated,) = db.rows(Alert)
        assert updated.id == alert.id and updated.is_read is False
        assert updated.description.startswith(
            "Dopo il controllo sono cambiate 2 disposizioni citate nel documento: GDPR, Art. 13"
        )
        assert "AI Act, Art. 50 (testo consolidato al 01/02/2027)" in updated.description

    def test_a_dismissed_alert_is_not_reopened_for_the_same_change(self, client, db, source, alpha):
        created = _check(client, alpha).json()
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        (alert,) = db.rows(Alert)
        with db.sync_session() as session:
            session.get(Alert, alert.id).is_dismissed = True
            session.commit()
        client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        assert [a.id for a in db.rows(Alert)] == [alert.id]

    def test_a_removed_provision(self, client, db, source, alpha):
        created = _check(client, alpha).json()
        source.publish(GDPR, "2027-01-01", [article("Art. 12", "Articolo 12\nAltro.")])
        body = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        assert body["dependencies"][0]["state"] == "removed"
        assert body["findings"][0]["status"]["code"] == "inesistente"
        assert body["needs_review"] is True
        (alert,) = db.rows(Alert)
        assert "GDPR, Art. 13 (non c'è più nel testo vigente)" in alert.description

    def test_unreachable_texts_do_not_raise_an_alarm(self, client, db, source, alpha):
        created = _check(client, alpha).json()
        source.unreachable = {GDPR}
        body = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        gdpr, ai_act = body["dependencies"]
        assert gdpr["state"] == "unavailable" and ai_act["state"] == "current"
        assert gdpr["message"]
        assert body["needs_review"] is False and body["status"] == "a_posto"
        assert db.rows(Alert) == []
        source.unreachable = set()
        again = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        assert [d["state"] for d in again["dependencies"]] == ["current", "current"]

    def test_the_alert_of_a_clients_document_names_the_client(self, client, db, source, alpha):
        acme = db.add_client(alpha.org_id)
        created = _check(client, alpha, client_id=str(acme)).json()
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        (alert,) = db.rows(Alert)
        assert alert.client_id == acme and str(alert.document_check_id) == created["id"]

    def test_a_check_without_provisions(self, client, source, alpha):
        created = _check(client, alpha, "Resta fermo l'art. 13 del d.lgs. 196/2003.").json()
        source.asked_versions.clear()
        body = client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers).json()
        assert body["dependencies"] == [] and body["rechecked_at"] is not None
        assert source.asked_versions == []


# ─── Report ──────────────────────────────────────────────────────────


class TestReport:
    def test_html_report(self, client, source, alpha):
        created = _check(client, alpha, DOCUMENT, filename="informativa <1>.txt").json()
        response = client.get(f"{BASE}/checks/{created['id']}/report", headers=alpha.headers)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "private, no-store"
        html = response.text
        assert "informativa &lt;1&gt;.txt" in html and "<1>" not in html
        for fragment in (
            "Citazione superata",
            "Citazione diversa dal testo ufficiale",
            "Da correggere",
        ):
            assert fragment in html
        assert "check_document.py" not in html  # no command-line instructions in the app's report

    def test_the_report_follows_the_last_recheck(self, client, source, alpha):
        created = _check(client, alpha).json()
        before = client.get(f"{BASE}/checks/{created['id']}/report", headers=alpha.headers).text
        assert "Cambiato dopo il controllo" not in before
        source.publish(GDPR, "2027-01-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{BASE}/checks/{created['id']}/recheck", headers=alpha.headers)
        after = client.get(f"{BASE}/checks/{created['id']}/report", headers=alpha.headers).text
        assert "Cambiato dopo il controllo" in after
        assert "<ins>almeno</ins>" in after
        assert (
            "Differenze tra il testo consolidato al 04/05/2016 e il testo consolidato al 01/01/2027"
            in after
        )


# ─── Preferences and unsubscribe ─────────────────────────────────────


class TestPreferences:
    def test_get_and_patch(self, client, db, alpha):
        other = db.add_user(alpha.org_id, "collega@example.test")
        assert client.get(f"{BASE}/preferences", headers=alpha.headers).json() == {
            "email_digest": True
        }
        response = client.patch(
            f"{BASE}/preferences", json={"email_digest": False}, headers=alpha.headers
        )
        assert response.status_code == 200 and response.json() == {"email_digest": False}
        assert client.get(f"{BASE}/preferences", headers=alpha.headers).json() == {
            "email_digest": False
        }
        with db.sync_session() as session:
            assert session.get(User, alpha.user_id).notify_document_changes is False
            assert session.get(User, other).notify_document_changes is True
        client.patch(f"{BASE}/preferences", json={"email_digest": True}, headers=alpha.headers)
        assert client.get(f"{BASE}/preferences", headers=alpha.headers).json() == {
            "email_digest": True
        }

    def test_patch_validation(self, client, alpha):
        for bad in ({}, {"email_digest": "forse"}, {"email_digest": None}):
            assert (
                client.patch(f"{BASE}/preferences", json=bad, headers=alpha.headers).status_code
                == 422
            )

    def test_a_token_of_a_deleted_user(self, client, db, alpha):
        ghost = create_access_token(user_id=uuid.uuid4(), org_id=alpha.org_id, role="member")
        response = client.get(f"{BASE}/preferences", headers={"Authorization": f"Bearer {ghost}"})
        assert response.status_code == 404


class TestUnsubscribe:
    def _flag(self, db, user_id):
        with db.sync_session() as session:
            return session.get(User, user_id).notify_document_changes

    def test_the_link_turns_the_email_off_without_a_login(self, client, db, alpha):
        token = service.make_unsubscribe_token(alpha.user_id)
        response = client.get(f"{BASE}/unsubscribe", params={"token": token})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Email disattivata" in response.text
        assert self._flag(db, alpha.user_id) is False
        # A session without a tenant: users are not tenant-scoped.
        assert db.session_orgs[-1] is None
        # Opening the link again changes nothing.
        assert client.get(f"{BASE}/unsubscribe", params={"token": token}).status_code == 200
        assert self._flag(db, alpha.user_id) is False

    def test_one_click_post(self, client, db, alpha):
        token = service.make_unsubscribe_token(alpha.user_id)
        response = client.post(
            f"{BASE}/unsubscribe", params={"token": token}, data={"List-Unsubscribe": "One-Click"}
        )
        assert response.status_code == 200
        assert self._flag(db, alpha.user_id) is False

    def test_only_the_user_of_the_token(self, client, db, alpha, beta):
        client.get(
            f"{BASE}/unsubscribe", params={"token": service.make_unsubscribe_token(alpha.user_id)}
        )
        assert self._flag(db, beta.user_id) is True

    def test_invalid_tokens(self, client, db, alpha):
        from datetime import UTC, datetime, timedelta

        from src.auth.tokens import make_signed_token
        from src.auth.verification import make_email_verification_token

        good = service.make_unsubscribe_token(alpha.user_id)
        forged = good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")
        other_user = good.replace(str(alpha.user_id), str(uuid.uuid4()))
        other_purpose = make_email_verification_token(alpha.user_id, "a@example.test")
        expired = make_signed_token(
            service.UNSUBSCRIBE_PURPOSE, str(alpha.user_id), datetime.now(UTC) - timedelta(days=1)
        )
        for token in ("", "abc", forged, other_user, other_purpose, expired):
            response = client.get(f"{BASE}/unsubscribe", params={"token": token})
            assert response.status_code == 400, token
            assert "Link non valido" in response.text
        assert self._flag(db, alpha.user_id) is True

    def test_the_link_points_to_the_api(self):
        user_id = uuid.uuid4()
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(api_public_url="", api_domain=""),
        ):
            assert service.unsubscribe_url(user_id) is None
        with patch(
            "src.document_check.service.get_settings",
            return_value=_settings(api_public_url="", api_domain="api.example.test"),
        ):
            url = service.unsubscribe_url(user_id)
        assert url.startswith("https://api.example.test/api/v1/documents/unsubscribe?token=")
        assert service.read_unsubscribe_token(url.split("token=")[1]) == user_id
        assert _settings(api_public_url="https://api.normaai.example/").api_base_url == (
            "https://api.normaai.example"
        )
