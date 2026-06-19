"""Tests for the data router (src/api/routers/data.py).

Covers the three endpoints exposed under /api/v1:
- POST /api/v1/crawl           (auth-required, EUR-Lex crawl)
- POST /api/v1/documents/upload (auth-required, requires Qdrant, NLP pipeline)
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
    """HTTP headers with a valid admin Bearer token."""
    token = create_access_token(test_user_id, test_org_id, "admin")
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

    def test_crawl_amendment_check_default_success(self, client, auth_headers):
        """Default (no body fields) is an amendment_check; mock the EUR-Lex client."""
        mock_client = MagicMock()
        mock_client.check_for_new_amendments.return_value = ["amend-1", "amend-2"]
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post("/api/v1/crawl", json={}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["amendments_count"] == 2
        mock_client.check_for_new_amendments.assert_called_once()

    def test_crawl_full_crawl_success(self, client, auth_headers):
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
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["regulations_count"] == 3
        assert sorted(data["data"]["frameworks"]) == ["CSRD", "DORA"]

    def test_crawl_invalid_days_back_too_low(self, client, auth_headers):
        """days_back has ge=1; 0 must be rejected with 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"days_back": 0},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_crawl_invalid_days_back_too_high(self, client, auth_headers):
        """days_back has le=90; 91 must be rejected with 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"days_back": 91},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_crawl_invalid_crawl_type_enum(self, client, auth_headers):
        """crawl_type is an enum; an unknown value is a 422."""
        response = client.post(
            "/api/v1/crawl",
            json={"crawl_type": "delete_everything"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_crawl_client_failure_returns_500(self, client, auth_headers):
        """A crawler exception is caught and surfaced as a sanitized 500."""
        mock_client = MagicMock()
        mock_client.check_for_new_amendments.side_effect = RuntimeError("network down")
        with patch("src.crawler.eurlex.client.EurLexClient", return_value=mock_client):
            response = client.post("/api/v1/crawl", json={}, headers=auth_headers)
        assert response.status_code == 500
        assert "logs" in response.json()["detail"].lower()


# ------------------------------------------------------------------ #
#  POST /api/v1/documents/upload  (auth-required + Qdrant)            #
# ------------------------------------------------------------------ #


class TestUploadEndpoint:
    def test_upload_requires_auth(self, client):
        """No token -> 401 (auth dependency runs even with a valid multipart body)."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.pdf", b"%PDF-1.4 data", "application/pdf")},
        )
        assert response.status_code == 401

    def test_upload_missing_file_is_422(self, client, auth_headers):
        """The file field is required (File(...)); omitting it is a validation error."""
        response = client.post("/api/v1/documents/upload", headers=auth_headers)
        assert response.status_code == 422

    def test_upload_happy_path(self, client, auth_headers):
        """Valid PDF -> pipeline mocked -> 200 with chunk count echoed back."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_document.return_value = {"chunks_indexed": 7}
        with patch("src.pipeline.IngestionPipeline", return_value=mock_pipeline):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("report.pdf", b"%PDF-1.4 hello world", "application/pdf")},
                headers=auth_headers,
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["filename"] == "report.pdf"
        assert data["data"]["chunks_indexed"] == 7
        assert data["data"]["size_bytes"] == len(b"%PDF-1.4 hello world")

    def test_upload_passes_org_id_to_pipeline(self, client, auth_headers, test_org_id):
        """SEC-01: the upload must be tenant-scoped via org_id to process_document."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_document.return_value = {"chunks_indexed": 1}
        with patch("src.pipeline.IngestionPipeline", return_value=mock_pipeline):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("x.pdf", b"%PDF data", "application/pdf")},
                headers=auth_headers,
            )
        assert response.status_code == 200
        _, kwargs = mock_pipeline.process_document.call_args
        assert kwargs["org_id"] == str(test_org_id)

    def test_upload_with_framework_query_param(self, client, auth_headers):
        """A valid framework enum is forwarded to the pipeline and echoed back."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_document.return_value = {"chunks_indexed": 3}
        with patch("src.pipeline.IngestionPipeline", return_value=mock_pipeline):
            response = client.post(
                "/api/v1/documents/upload?framework=CSRD",
                files={"file": ("c.pdf", b"%PDF data", "application/pdf")},
                headers=auth_headers,
            )
        assert response.status_code == 200
        assert response.json()["data"]["framework"] == "CSRD"
        _, kwargs = mock_pipeline.process_document.call_args
        assert kwargs["framework"] == "CSRD"

    def test_upload_invalid_framework_query_param_is_422(self, client, auth_headers):
        """An unknown framework value fails FastAPI enum validation (422)."""
        response = client.post(
            "/api/v1/documents/upload?framework=NOT_A_FRAMEWORK",
            files={"file": ("c.pdf", b"%PDF data", "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_upload_unsupported_extension_is_400(self, client, auth_headers):
        """A .exe upload is rejected by the allowed-extensions check (400)."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("malware.exe", b"MZ\x90\x00", "application/octet-stream")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Unsupported file type" in response.json()["detail"]

    def test_upload_empty_file_is_400(self, client, auth_headers):
        """Zero-byte content is rejected before the pipeline runs (400)."""
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "Empty file" in response.json()["detail"]

    def test_upload_pipeline_failure_returns_500(self, client, auth_headers):
        """A pipeline exception is caught and sanitized into a 500."""
        mock_pipeline = MagicMock()
        mock_pipeline.process_document.side_effect = RuntimeError("OCR exploded")
        with patch("src.pipeline.IngestionPipeline", return_value=mock_pipeline):
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("r.pdf", b"%PDF data", "application/pdf")},
                headers=auth_headers,
            )
        assert response.status_code == 500
        assert "logs" in response.json()["detail"].lower()

    def test_upload_returns_503_when_qdrant_down(self, client, auth_headers):
        """The _require_qdrant guard must 503 before any file processing."""
        from src.api.main import app_state

        original = app_state.qdrant_available
        try:
            app_state.qdrant_available = False
            response = client.post(
                "/api/v1/documents/upload",
                files={"file": ("r.pdf", b"%PDF data", "application/pdf")},
                headers=auth_headers,
            )
            assert response.status_code == 503
        finally:
            app_state.qdrant_available = original


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
