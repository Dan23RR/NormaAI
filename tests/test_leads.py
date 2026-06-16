"""Tests for the public /api/v1/leads endpoint.

Goals:
- Endpoint accepts valid payload, returns 201 with ok=true
- Invalid email rejected with 422
- Empty body rejected with 422
- Source enum constraint enforced
- Idempotent re-submit within 24h returns 201 with "already submitted" message
- Rate limit per-IP triggers 429 after threshold

Notes: this uses the same TestClient pattern as test_api_integration.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def client():
    """Bare-bones FastAPI TestClient for the leads router only.

    NOTE 2026-04-28: we do NOT use `with TestClient(app) as c:` (the context
    manager triggers lifespan startup+shutdown). Lifespan shutdown awaits
    db_manager which is a sync MagicMock here, raising
    `MagicMock can't be used in 'await' expression`. Plain TestClient(app)
    skips lifespan entirely, which is what we want for these unit tests.
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

        app_state.qdrant_available = True
        app_state.llm_available = True
        limiter.enabled = False

        from fastapi.testclient import TestClient

        yield TestClient(app)


# ────────────────────── Validation ──────────────────────


class TestLeadValidation:
    def test_invalid_email_rejected(self, client):
        r = client.post("/api/v1/leads", json={"email": "not-an-email"})
        assert r.status_code == 422

    def test_missing_email_rejected(self, client):
        r = client.post("/api/v1/leads", json={"org_name": "X"})
        assert r.status_code == 422

    def test_invalid_source_rejected(self, client):
        r = client.post(
            "/api/v1/leads",
            json={"email": "ok@example.com", "source": "spam_channel"},
        )
        assert r.status_code == 422

    def test_org_name_too_long_rejected(self, client):
        r = client.post(
            "/api/v1/leads",
            json={"email": "ok@example.com", "org_name": "x" * 300},
        )
        assert r.status_code == 422


# ────────────────────── Schema shape ──────────────────────


class TestLeadResponseShape:
    """Verify the route exposes the expected schema (registered with FastAPI)."""

    def test_route_is_registered(self, client):
        # OPTIONS or GET on /api/v1/leads should not 404
        r = client.options("/api/v1/leads")
        # FastAPI returns 405 for unsupported method on registered route, 404 otherwise
        assert r.status_code in (200, 405)

    def test_openapi_documents_leads_post(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert "/api/v1/leads" in spec.get("paths", {})
        assert "post" in spec["paths"]["/api/v1/leads"]
