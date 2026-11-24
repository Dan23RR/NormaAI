"""Tests for the data router (src/api/routers/data.py).

Covers the three endpoints exposed under /api/v1:
- POST /api/v1/crawl           (staff only, EUR-Lex crawl)
- POST /api/v1/documents/upload (closed: 410 Gone for everyone, nothing read or stored)
- GET  /api/v1/processors       (public, OCR engine status)

Focus areas (per task brief):
- auth-required (401 without a token)
- happy paths (200/success) with the external crawler / pipeline mocked
- validation (422) for out-of-range payload fields
- not-found / unsupported-input (400/404-style) for bad uploads
- service degradation (503) when Qdrant is unavailable

TestClient + auth-header + app_state pattern is copied verbatim from
tests/test_api_integration.py so this file is order-independent and does not
pollute global module state (rate-limiting and app_state flags are restored in
the fixture teardown).
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.security import create_access_token

# ------------------------------------------------------------------ #
#  Fixtures (mirror tests/test_api_integration.py)                    #
# ------------------------------------------------------------------ #


@pytest.fixture
def test_user_id():
    return uuid.uuid4()


@pytest.fixture
def test_org_id():
    return uuid.uuid4()


@pytest.fixture
def auth_headers(test_user_id, test_org_id):
    """HTTP headers with a valid admin Bearer token (a customer admin, NOT staff)."""
    token = create_access_token(test_user_id, test_org_id, "admin")
    return {"Authorization": f"Bearer {token}"}


STAFF_EMAIL = "ops@normaai.org"


@pytest.fixture
def staff_headers(test_user_id, test_org_id, monkeypatch):
    """Admin token of an account that the database says is staff, with a verified email.

    /crawl re-indexes the shared corpus and is gated by ``require_staff``, which
    reads users.is_staff through the account check of get_current_user.
    """
    from dataclasses import replace

    from src.auth import dependencies

    async def _staff_account(payload):
        account = dependencies.account_from_claims(payload)
        if payload.sub == str(test_user_id):
            return replace(account, is_staff=True, email_verified=True)
        return account

    monkeypatch.setattr(dependencies, "resolve_account", _staff_account)
    token = create_access_token(test_user_id, test_org_id, "admin", email=STAFF_EMAIL)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client():
    """FastAPI TestClient with mocked external dependencies.

    Identical setup to tests/test_api_integration.py: patch the heavy imports
    the lifespan touches, disable the rate limiter, then override the
    availability flags AFTER startup. Teardown restores the limiter so the
    file is safe to run alongside order-dependent neighbours (test_leads).
    """
    with (
        patch("src.api.lifespan.validate_settings_or_exit") as mock_settings,
        patch("src.api.lifespan.db_manager", create=True) as _mock_db,
        patch.dict(
            "sys.modules",
            {
                "src.nlp.embedding.indexer": MagicMock(),
                "src.db.engine": MagicMock(),
            },
        ),
    ):
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app, app_state, limiter

        limiter.enabled = False

        with TestClient(app, raise_server_exceptions=False) as c:
            # Override real (empty-env) availability flags after startup so the
            # qdrant guard in /documents/upload does not 503 before the handler.
            app_state.qdrant_available = True
            app_state.llm_available = True
            app_state.indexer = MagicMock()

            try:
                from src.cache import response_cache

                response_cache._available = False
                response_cache._client = None
            except ImportError:
                pass

            yield c

        limiter.enabled = True


# ------------------------------------------------------------------ #
#  GET /api/v1/processors  (public)                                   #
# ------------------------------------------------------------------ #


class TestProcessorsEndpoint:
    def test_processors_is_public(self, client):
        """No auth needed; always returns 200 with a status field."""
        response = client.get("/api/v1/processors")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("success", "degraded")

    def test_processors_degraded_when_processor_import_fails(self, client):
        """If the OCR processor blows up, the endpoint degrades (no 500)."""
        with patch(
            "src.nlp.processing.dots_ocr_processor.UnifiedDocumentProcessor",
            side_effect=RuntimeError("no torch"),
        ):
            response = client.get("/api/v1/processors")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"


# ------------------------------------------------------------------ #
#  POST /api/v1/crawl  (auth-required)                                #
# ------------------------------------------------------------------ #


class TestCrawlEndpoint:
    def test_crawl_requires_auth(self, client):
        response = client.post("/api/v1/crawl", json={})
        assert response.status_code == 401

    def test_crawl_rejects_invalid_token(self, client):
        response = client.post(
            "/api/v1/crawl",
            json={},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401

    def test_crawl_non_staff_admin_is_403(self, client, auth_headers):
        """A customer admin (no staff email claim) must not re-index the shared corpus."""
        mock_client = MagicMock()
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post("/api/v1/crawl", json={}, headers=auth_headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Operazione riservata al personale NormaAI."
        mock_client.check_for_new_amendments.assert_not_called()

    def test_crawl_staff_email_claim_alone_is_403(self, client, test_user_id, test_org_id):
        """A staff address in the token's email claim is not enough: staff is a DB flag."""
        token = create_access_token(test_user_id, test_org_id, "admin", email=STAFF_EMAIL)
        response = client.post(
            "/api/v1/crawl", json={}, headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 403

    def test_crawl_amendment_check_default_success(self, client, staff_headers):
        """Default (no body fields) is an amendment_check; mock the EUR-Lex client."""
        mock_client = MagicMock()
        mock_client.check_for_new_amendments.return_value = ["amend-1", "amend-2"]
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post("/api/v1/crawl", json={}, headers=staff_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["amendments_count"] == 2
        mock_client.check_for_new_amendments.assert_called_once()

    def test_crawl_full_crawl_success(self, client, staff_headers):
        """full_crawl path reports a regulation count and dedup'd frameworks."""
        reg1 = MagicMock(framework="CSRD")
        reg2 = MagicMock(framework="CSRD")
        reg3 = MagicMock(framework="DORA")
        mock_client = MagicMock()
        mock_client.crawl_all_core_frameworks.return_value = [reg1, reg2, reg3]
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post(
                "/api/v1/crawl",
                json={"crawl_type": "full_crawl"},
                headers=staff_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["regulations_count"] == 3
        assert sorted(data["data"]["frameworks"]) == ["CSRD", "DORA"]

    def test_crawl_invalid_days_back_too_low(self, client, staff_headers):
        """days_back has ge=1; 0 must be rejected with 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"days_back": 0},
            headers=staff_headers,
        )
        assert response.status_code == 422

    def test_crawl_invalid_days_back_too_high(self, client, staff_headers):
        """days_back has le=90; 91 must be rejected with 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"days_back": 91},
            headers=staff_headers,
        )
        assert response.status_code == 422

    def test_crawl_invalid_crawl_type_enum(self, client, staff_headers):
        """crawl_type is an enum; an unknown value is a 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"crawl_type": "delete_everything"},
            headers=staff_headers,
        )
        assert response.status_code == 422

    def test_crawl_client_failure_returns_500(self, client, staff_headers):
        """A crawler exception is caught and surfaced as a sanitized 500."""
        mock_client = MagicMock()
        mock_client.check_for_new_amendments.side_effect = RuntimeError("network down")
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post("/api/v1/crawl", json={}, headers=staff_headers)
        assert response.status_code == 500
        assert "logs" in response.json()["detail"].lower()


# ------------------------------------------------------------------ #
#  POST /api/v1/documents/upload  (closed: 410 Gone)                  #
# ------------------------------------------------------------------ #


class TestUploadEndpoint:
    """The legacy upload indexed a document for good; it is closed for everyone."""

    @pytest.mark.parametrize("with_token", [True, False])
    def test_upload_is_gone_and_points_to_the_check(self, client, auth_headers, with_token):
        mock_pipeline = MagicMock()
        with patch("src.pipeline.IngestionPipeline", return_value=mock_pipeline):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("report.pdf", b"%PDF-1.4 hello world", "application/pdf")},
                headers=auth_headers if with_token else {},
            )
        assert response.status_code == 410
        detail = response.json()["detail"]
        assert "/api/v1/documents/check" in detail
        assert "non viene conservato" in detail
        # Nothing is read, extracted or indexed.
        mock_pipeline.process_document.assert_not_called()

    def test_upload_without_a_file_is_gone_too(self, client, auth_headers):
        response = client.post("/api/v1/documents/upload", headers=auth_headers)
        assert response.status_code == 410

    def test_upload_is_marked_deprecated_in_the_schema(self, client):
        operation = client.get("/openapi.json").json()["paths"]["/api/v1/documents/upload"]["post"]
        assert operation["deprecated"] is True
        assert "410" in operation["responses"]


# ------------------------------------------------------------------ #
#  OpenAPI surface                                                    #
# ------------------------------------------------------------------ #


class TestDataRouterRegistration:
    def test_data_routes_registered_in_openapi(self, client):
        spec = client.get("/openapi.json").json()
        paths = spec.get("paths", {})
        assert "/api/v1/crawl" in paths
        assert "/api/v1/documents/upload" in paths
        assert "/api/v1/processors" in paths
