"""Tests for the letterhead routes and for the PDF of a check that reads them.

Routes under test:
- GET, PUT, DELETE /api/v1/organization/letterhead           the texts
- GET, PUT, DELETE /api/v1/organization/letterhead/logo      the logo
- GET /api/v1/documents/checks/{id}/report.pdf               the PDF of a check

Same pattern as tests/test_documents_router.py: the bare ``TestClient(app)``
(no lifespan, rate limiting off), the official texts from a ``FakeSource`` and
the routers' ``db_manager`` replaced by tests/documents_support.Database, the
real tables on SQLite in memory. SQLite has no row-level security: these tests
prove the ``org_id`` filter of every query; the PostgreSQL policies of
migration 011 are checked by tests/test_migration_011.py and the CI ``schema``
job.
"""

from __future__ import annotations

import io
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from pypdf import PdfReader

from src.auth.dependencies import ADMIN_ONLY_DETAIL
from src.auth.security import create_access_token
from src.config import get_settings
from src.db.models import OrgLetterhead
from tests.documents_support import ART13_AMENDED, DOCUMENT, GDPR, Database, FakeSource, article

BASE = "/api/v1/organization/letterhead"
DOCS = "/api/v1/documents"
_ROUTERS = ("src.api.routers.documents", "src.api.routers.letterhead")


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


def _forget_stale_route_limits() -> None:
    """Drop the limits an earlier import of the two routers left on the shared limiter."""
    from src.api.rate_limit import limiter

    for module in _ROUTERS:
        if module in sys.modules:
            continue
        for registry in (limiter._dynamic_route_limits, limiter._route_limits):
            for name in [n for n in registry if n.startswith(f"{module}.")]:
                del registry[name]


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
            {"src.nlp.embedding.indexer": MagicMock(), "src.db.engine": MagicMock()},
        ),
    ):
        mock_settings.return_value = get_settings()
        _forget_stale_route_limits()
        from src.api.main import app, limiter
        from src.api.routers import documents
        from src.api.routers import letterhead as letterhead_router

        limiter.enabled = False
        app.dependency_overrides[documents.get_text_source] = lambda: source
        with (
            patch.object(documents, "db_manager", db),
            patch.object(letterhead_router, "db_manager", db),
        ):
            try:
                yield app, documents, letterhead_router
            finally:
                app.dependency_overrides.clear()


@pytest.fixture
def client(app_objects):
    from fastapi.testclient import TestClient

    return TestClient(app_objects[0])


class Tenant:
    """An organisation with an admin and the headers of the admin's token."""

    def __init__(self, db: Database, name: str) -> None:
        self.org_id = db.add_org(name)
        self.admin_id = db.add_user(
            self.org_id, f"{uuid.uuid4().hex[:8]}@example.test", role="admin"
        )
        self.headers = self._headers(self.admin_id, "admin")

    def _headers(self, user_id: uuid.UUID, role: str) -> dict[str, str]:
        token = create_access_token(user_id=user_id, org_id=self.org_id, role=role)
        return {"Authorization": f"Bearer {token}"}

    def user(self, db: Database, role: str) -> dict[str, str]:
        user_id = db.add_user(self.org_id, f"{uuid.uuid4().hex[:8]}@example.test", role=role)
        return self._headers(user_id, role)


@pytest.fixture
def alpha(db):
    return Tenant(db, "Studio Alfa")


@pytest.fixture
def beta(db):
    return Tenant(db, "Studio Beta")


TEXTS = {
    "name": "Studio Legale Alfa",
    "address": "Via Roma 1\n20121 Milano",
    "contact": "tel. 02 1234567 · info@alfa.example",
    "footer_note": "Riservato al cliente.",
}


def _png(size=(300, 100), fmt="PNG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (10, 58, 156)).save(out, fmt)
    return out.getvalue()


def _put_logo(client, tenant_headers, data: bytes, name: str = "logo.png"):
    return client.put(f"{BASE}/logo", files={"file": (name, data)}, headers=tenant_headers)


# ─── Access ──────────────────────────────────────────────────────────


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", BASE),
            ("put", BASE),
            ("delete", BASE),
            ("get", f"{BASE}/logo"),
            ("put", f"{BASE}/logo"),
            ("delete", f"{BASE}/logo"),
            ("get", f"{DOCS}/checks/{uuid.uuid4()}/report.pdf"),
        ],
    )
    def test_every_route_wants_a_token(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401
        bad = {"Authorization": "Bearer not-a-token"}
        assert getattr(client, method)(path, headers=bad).status_code == 401

    @pytest.mark.parametrize("role", ["member", "viewer"])
    def test_members_and_viewers_read_but_do_not_write(self, client, db, alpha, role):
        headers = alpha.user(db, role)
        assert client.get(BASE, headers=headers).status_code == 200
        for response in (
            client.put(BASE, json=TEXTS, headers=headers),
            client.delete(BASE, headers=headers),
            _put_logo(client, headers, _png()),
            client.delete(f"{BASE}/logo", headers=headers),
        ):
            assert response.status_code == 403
            assert response.json()["detail"] == ADMIN_ONLY_DETAIL
        assert db.rows(OrgLetterhead) == []

    def test_writing_needs_a_verified_email_when_the_deployment_asks_for_it(
        self, client, db, alpha
    ):
        settings = get_settings().model_copy(update={"require_email_verification": True})
        with (
            patch("src.auth.dependencies.get_settings", return_value=settings),
            patch("src.auth.dependencies._email_verified_in_db", return_value=False),
        ):
            assert client.put(BASE, json=TEXTS, headers=alpha.headers).status_code == 403
            assert _put_logo(client, alpha.headers, _png()).status_code == 403
        assert db.rows(OrgLetterhead) == []

    def test_routes_are_in_the_openapi_schema(self, client):
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths[BASE]) == {"get", "put", "delete"}
        assert set(paths[f"{BASE}/logo"]) == {"get", "put", "delete"}
        assert "get" in paths[f"{DOCS}/checks/{{check_id}}/report.pdf"]


# ─── Texts ───────────────────────────────────────────────────────────


class TestTexts:
    def test_without_a_letterhead_the_name_of_the_organisation(self, client, alpha):
        assert client.get(BASE, headers=alpha.headers).json() == {
            "configured": False,
            "name": "Studio Alfa",
            "address": None,
            "contact": None,
            "footer_note": None,
            "logo": None,
            "updated_at": None,
        }

    def test_put_and_get(self, client, db, alpha):
        response = client.put(BASE, json=TEXTS, headers=alpha.headers)
        assert response.status_code == 200
        body = response.json()
        assert body["configured"] is True
        assert {k: body[k] for k in TEXTS} == TEXTS
        assert body["logo"] is None and body["updated_at"]
        assert client.get(BASE, headers=alpha.headers).json() == body
        (row,) = db.rows(OrgLetterhead)
        assert row.org_id == alpha.org_id and row.updated_by == alpha.admin_id

    def test_texts_are_cleaned(self, client, alpha):
        body = client.put(
            BASE,
            json={
                "name": "  Studio\nAlfa ",
                "address": "Via Roma 1\n\n\n Milano ",
                "contact": "  ",
            },
            headers=alpha.headers,
        ).json()
        assert body["name"] == "Studio Alfa"
        assert body["address"] == "Via Roma 1\nMilano"
        assert body["contact"] is None and body["footer_note"] is None

    def test_put_again_replaces_the_texts_and_keeps_the_logo(self, client, alpha):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        _put_logo(client, alpha.headers, _png())
        body = client.put(
            BASE, json={"name": "Studio Alfa e Associati"}, headers=alpha.headers
        ).json()
        assert body["name"] == "Studio Alfa e Associati"
        assert body["address"] is None and body["footer_note"] is None
        assert body["logo"]["content_type"] == "image/png"

    @pytest.mark.parametrize(
        ("payload", "detail"),
        [
            ({"name": " "}, "Scrivi il nome dello studio."),
            (
                {"name": "Studio", "address": "a\nb\nc\nd"},
                "L'indirizzo può avere al massimo 3 righe.",
            ),
            ({"name": "x" * 201}, "Il nome dello studio può avere al massimo 200 caratteri."),
        ],
    )
    def test_refused_texts(self, client, db, alpha, payload, detail):
        response = client.put(BASE, json=payload, headers=alpha.headers)
        assert response.status_code == 422
        assert response.json()["detail"] == detail
        assert db.rows(OrgLetterhead) == []

    @pytest.mark.parametrize(
        "content",
        ["not json", "[1, 2]", '{"address": "senza nome"}', '{"name": "' + "x" * 2001 + '"}'],
    )
    def test_requests_that_are_not_the_texts(self, client, alpha, content):
        from src.api.routers.letterhead import INVALID_TEXTS_DETAIL

        response = client.put(
            BASE, content=content, headers={**alpha.headers, "Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert response.json()["detail"] == INVALID_TEXTS_DETAIL

    def test_delete_goes_back_to_the_name_of_the_organisation(self, client, db, alpha):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        _put_logo(client, alpha.headers, _png())
        assert client.delete(BASE, headers=alpha.headers).status_code == 204
        assert db.rows(OrgLetterhead) == []
        body = client.get(BASE, headers=alpha.headers).json()
        assert body["configured"] is False and body["name"] == "Studio Alfa"
        assert client.get(f"{BASE}/logo", headers=alpha.headers).status_code == 404
        assert client.delete(BASE, headers=alpha.headers).status_code == 204  # nothing left: fine

    def test_every_change_is_in_the_audit_log_without_the_texts(self, client, alpha):
        with patch("src.api.routers.letterhead.audit_log") as audit:
            client.put(BASE, json=TEXTS, headers=alpha.headers)
            _put_logo(client, alpha.headers, _png())
            client.delete(f"{BASE}/logo", headers=alpha.headers)
            client.delete(BASE, headers=alpha.headers)
        details = [call.kwargs["detail"] for call in audit.call_args_list]
        assert details[0] == "letterhead texts updated"
        assert details[1].startswith("letterhead logo updated (image/png, ")
        assert details[2:] == ["letterhead logo removed", "letterhead removed"]
        for call in audit.call_args_list:
            assert call.args[0].value == "admin.config.changed"
            assert call.kwargs["org_id"] == str(alpha.org_id)
            assert "Studio Legale Alfa" not in str(call)


# ─── Logo ────────────────────────────────────────────────────────────


class TestLogo:
    def test_upload_and_read(self, client, alpha):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        response = _put_logo(client, alpha.headers, _png())
        assert response.status_code == 200
        logo = response.json()["logo"]
        assert logo["content_type"] == "image/png" and logo["size"] > 0
        image = client.get(f"{BASE}/logo", headers=alpha.headers)
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.headers["cache-control"] == "private, no-store"
        assert image.headers["x-content-type-options"] == "nosniff"
        assert len(image.content) == logo["size"]
        with Image.open(io.BytesIO(image.content)) as stored:
            assert stored.format == "PNG" and stored.size == (300, 100)

    def test_a_logo_without_a_letterhead_gives_one_with_the_name_of_the_organisation(
        self, client, db, alpha
    ):
        body = _put_logo(client, alpha.headers, _png(fmt="JPEG"), "logo.jpg").json()
        assert body["configured"] is True and body["name"] == "Studio Alfa"
        assert body["logo"]["content_type"] == "image/jpeg"
        (row,) = db.rows(OrgLetterhead)
        assert row.logo_type == "image/jpeg" and row.updated_by == alpha.admin_id

    def test_delete_the_logo_keeps_the_texts(self, client, alpha):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        _put_logo(client, alpha.headers, _png())
        body = client.delete(f"{BASE}/logo", headers=alpha.headers).json()
        assert body["logo"] is None and body["name"] == TEXTS["name"] and body["configured"]
        assert client.get(f"{BASE}/logo", headers=alpha.headers).status_code == 404

    def test_no_logo_is_404(self, client, alpha):
        response = client.get(f"{BASE}/logo", headers=alpha.headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "La carta intestata non ha un logo."

    def test_refused_files(self, client, db, alpha):
        gif = _put_logo(client, alpha.headers, _png(fmt="GIF"), "logo.gif")
        assert gif.status_code == 415
        assert gif.json()["detail"] == "Il logo deve essere un'immagine PNG o JPEG."
        named_png = _put_logo(client, alpha.headers, b"GIF89a fake", "logo.png")
        assert named_png.status_code == 415
        empty = _put_logo(client, alpha.headers, b"")
        assert empty.status_code == 422 and empty.json()["detail"] == "Il file del logo è vuoto."
        heavy = _put_logo(client, alpha.headers, b"\x89PNG" + b"0" * (3 * 1024 * 1024))
        assert heavy.status_code == 413
        assert heavy.json()["detail"] == "Il logo supera 2 MB: usa un file più leggero."
        assert db.rows(OrgLetterhead) == []

    def test_requests_that_are_not_a_file(self, client, alpha):
        from src.api.routers.letterhead import INVALID_LOGO_DETAIL, MISSING_LOGO_DETAIL

        as_json = client.put(f"{BASE}/logo", json={"file": "x"}, headers=alpha.headers)
        assert as_json.status_code == 415 and as_json.json()["detail"] == INVALID_LOGO_DETAIL
        no_file = client.put(
            f"{BASE}/logo", data={"other": "x"}, files={"x": ("a", b"b")}, headers=alpha.headers
        )
        assert no_file.status_code == 422 and no_file.json()["detail"] == MISSING_LOGO_DETAIL

    def test_a_declared_length_too_large_is_refused_before_reading(self, client, alpha):
        response = client.put(
            f"{BASE}/logo",
            content=b"x",
            headers={
                **alpha.headers,
                "Content-Type": "multipart/form-data; boundary=x",
                "Content-Length": str(3 * 1024 * 1024),
            },
        )
        assert response.status_code == 413


# ─── Organisations ───────────────────────────────────────────────────


class TestIsolation:
    def test_each_organisation_sees_and_changes_its_own(self, client, db, alpha, beta):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        _put_logo(client, alpha.headers, _png())
        db.session_orgs.clear()

        beta_view = client.get(BASE, headers=beta.headers).json()
        assert beta_view["configured"] is False and beta_view["name"] == "Studio Beta"
        assert client.get(f"{BASE}/logo", headers=beta.headers).status_code == 404
        client.put(BASE, json={"name": "Studio Beta Srl"}, headers=beta.headers)
        assert client.delete(f"{BASE}/logo", headers=beta.headers).json()["logo"] is None
        assert client.delete(BASE, headers=beta.headers).status_code == 204

        alpha_view = client.get(BASE, headers=alpha.headers).json()
        assert alpha_view["name"] == TEXTS["name"] and alpha_view["logo"] is not None
        assert {str(org) for org in db.session_orgs} == {str(alpha.org_id), str(beta.org_id)}
        assert [row.org_id for row in db.rows(OrgLetterhead)] == [alpha.org_id]


# ─── The PDF of a check ──────────────────────────────────────────────


def _check(client, tenant_headers, text=DOCUMENT, filename="Informativa «clienti».docx"):
    response = client.post(
        f"{DOCS}/check", json={"text": text, "filename": filename}, headers=tenant_headers
    )
    assert response.status_code == 201
    return response.json()


def _text(data: bytes) -> str:
    return " ".join(
        " ".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages).split()
    )


class TestPdf:
    def test_the_pdf_of_a_check_with_the_letterhead(self, client, db, alpha):
        client.put(BASE, json=TEXTS, headers=alpha.headers)
        _put_logo(client, alpha.headers, _png())
        created = _check(client, alpha.headers)
        reader_headers = alpha.user(db, "viewer")  # anyone of the organisation downloads it
        response = client.get(f"{DOCS}/checks/{created['id']}/report.pdf", headers=reader_headers)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["cache-control"] == "private, no-store"
        assert response.headers["content-disposition"] == (
            'attachment; filename="Informativa _clienti_.controllo.pdf"; '
            "filename*=UTF-8''Informativa%20%C2%ABclienti%C2%BB.controllo.pdf"
        )
        reader = PdfReader(io.BytesIO(response.content))
        assert len(reader.pages[0].images) == 1
        text = _text(response.content)
        assert text.startswith(
            "Studio Legale Alfa Via Roma 1 20121 Milano tel. 02 1234567 · info@alfa.example"
        )
        for fragment in (
            "Informativa «clienti».docx",
            "Da correggere",
            "Citazione superata",
            "Atti che il controllo non legge",
            "Riservato al cliente.",
            "Controllo eseguito con NormaAI",
        ):
            assert fragment in text
        assert reader.metadata["/Author"] == "Studio Legale Alfa"

    def test_without_a_letterhead_the_name_of_the_organisation(self, client, alpha):
        created = _check(client, alpha.headers)
        response = client.get(f"{DOCS}/checks/{created['id']}/report.pdf", headers=alpha.headers)
        assert _text(response.content).startswith("Studio Alfa Controllo dei riferimenti normativi")

    def test_the_pdf_of_another_organisation_is_not_found(self, client, alpha, beta):
        created = _check(client, alpha.headers)
        response = client.get(f"{DOCS}/checks/{created['id']}/report.pdf", headers=beta.headers)
        assert response.status_code == 404
        missing = client.get(f"{DOCS}/checks/{uuid.uuid4()}/report.pdf", headers=alpha.headers)
        assert missing.status_code == 404

    def test_the_pdf_follows_the_last_recheck(self, client, source, alpha):
        created = _check(client, alpha.headers, "Ai sensi dell'art. 13 del GDPR.", "nota.txt")
        source.publish(GDPR, "2026-11-01", [article("Art. 13", ART13_AMENDED)])
        client.post(f"{DOCS}/checks/{created['id']}/recheck", headers=alpha.headers)
        text = _text(
            client.get(f"{DOCS}/checks/{created['id']}/report.pdf", headers=alpha.headers).content
        )
        assert "Cambiato dopo il controllo" in text
        assert "Norme citate ricontrollate il" in text
        assert (
            "Differenze tra il testo consolidato al 04/05/2016 e il testo consolidato al 01/11/2026"
            in text
        )

    def test_the_download_is_in_the_audit_log(self, client, alpha):
        created = _check(client, alpha.headers)
        with patch("src.api.routers.documents.audit_log") as audit:
            client.get(f"{DOCS}/checks/{created['id']}/report.pdf", headers=alpha.headers)
        (call,) = audit.call_args_list
        assert call.args[0].value == "data.export"
        assert call.kwargs["extra"] == {"check_id": created["id"]}

    def test_a_failure_is_a_clean_500_without_the_document(self, client, alpha):
        created = _check(client, alpha.headers)
        with (
            patch("src.api.routers.documents.render_pdf", side_effect=ValueError("testo segreto")),
            patch("src.api.routers.documents.logger") as log,
        ):
            response = client.get(
                f"{DOCS}/checks/{created['id']}/report.pdf", headers=alpha.headers
            )
        assert response.status_code == 500
        assert (
            response.json()["detail"] == "Errore interno durante il controllo. Riprova più tardi."
        )
        assert "testo segreto" not in str(log.mock_calls)

    def test_no_llm_quota_is_spent(self, client, alpha):
        created = _check(client, alpha.headers)
        with patch("src.quotas.llm_quota.consume") as consume:
            response = client.get(
                f"{DOCS}/checks/{created['id']}/report.pdf", headers=alpha.headers
            )
        assert response.status_code == 200
        consume.assert_not_called()
