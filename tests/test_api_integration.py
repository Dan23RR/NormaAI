"""Integration tests for NormaAI API endpoints.

Tests the full HTTP request lifecycle via FastAPI TestClient:
- Authentication enforcement
- Request validation
- Response format
- Error handling
- Rate limiting behavior
- Middleware headers (X-Request-ID, X-Process-Time)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth.security import create_access_token

# ------------------------------------------------------------------ #
#  Fixtures                                                           #
# ------------------------------------------------------------------ #


@pytest.fixture
def test_user_id():
    return uuid.uuid4()


@pytest.fixture
def test_org_id():
    return uuid.uuid4()


@pytest.fixture
def auth_token(test_user_id, test_org_id):
    """Create a valid JWT access token for testing."""
    return create_access_token(test_user_id, test_org_id, "admin")


@pytest.fixture
def auth_headers(auth_token):
    """HTTP headers with valid Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def member_token(test_user_id, test_org_id):
    """Token with member (non-admin) role."""
    return create_access_token(test_user_id, test_org_id, "member")


@pytest.fixture
def member_headers(member_token):
    return {"Authorization": f"Bearer {member_token}"}


@pytest.fixture
def client():
    """FastAPI TestClient with mocked external dependencies.

    The lifespan initializes Qdrant, DB, and LLM checks.  We patch
    ``app_state`` *after* the app is imported so the TestClient runs
    with controlled flags.

    Rate limiting is disabled to prevent cross-test interference.
    """
    # Patch heavy imports that lifespan touches.
    # NOTE 2026-04-28: validate_settings_or_exit is defined in src.config and
    # imported/called by src.api.lifespan (not src.api.main). Patch the
    # callsite where it's actually invoked.
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
        # Return a valid settings object
        from src.config import get_settings

        mock_settings.return_value = get_settings()

        from src.api.main import app, app_state, limiter

        # Disable rate limiting for tests to prevent cross-test 429 errors
        limiter.enabled = False

        with TestClient(app, raise_server_exceptions=False) as c:
            # The lifespan startup has just run and set the real availability
            # flags from the (empty) test environment - no live Qdrant, no LLM
            # key - which makes the intelligence endpoints return 503 via
            # _require_llm()/_require_qdrant() before the mocked handlers are
            # ever reached. Override the flags AFTER startup, not before.
            app_state.qdrant_available = True
            app_state.llm_available = True
            app_state.indexer = MagicMock()
            app_state.indexer.get_collection_stats.return_value = {
                "points_count": 1000,
                "status": "green",
            }

            # Disable Redis cache to prevent cross-test data leakage
            try:
                from src.cache import response_cache

                response_cache._available = False
                response_cache._client = None
            except ImportError:
                pass

            yield c

        # Re-enable rate limiting after tests
        limiter.enabled = True


# ------------------------------------------------------------------ #
#  Health and System Endpoints                                        #
# ------------------------------------------------------------------ #


class TestHealthEndpoints:
    def test_health_check_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_stats_public_access(self, client):
        """Stats endpoint should work without auth (basic info only)."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert data["status"] in ("healthy", "degraded")

    def test_stats_contains_qdrant_info(self, client):
        response = client.get("/api/v1/stats")
        data = response.json()
        assert "qdrant_available" in data
        assert "qdrant" in data

    def test_stats_contains_llm_info(self, client, auth_headers):
        """LLM provider/model are only exposed to authenticated admin users."""
        response = client.get("/api/v1/stats", headers=auth_headers)
        data = response.json()
        assert "llm_provider" in data
        assert "llm_model" in data

    def test_landing_page_returns_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "NormaAI" in response.text


# ------------------------------------------------------------------ #
#  Authentication Tests                                               #
# ------------------------------------------------------------------ #


class TestAuthentication:
    def test_protected_endpoint_requires_auth(self, client):
        """Intelligence endpoints should reject unauthenticated requests."""
        response = client.post("/api/v1/qa", json={"question": "What is CSRD?"})
        assert response.status_code == 401

    def test_protected_endpoint_rejects_invalid_token(self, client):
        response = client.post(
            "/api/v1/qa",
            json={"question": "What is CSRD?"},
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert response.status_code == 401

    def test_protected_endpoint_rejects_empty_bearer(self, client):
        response = client.post(
            "/api/v1/qa",
            json={"question": "What is CSRD?"},
            headers={"Authorization": "Bearer "},
        )
        # FastAPI HTTPBearer rejects empty token
        assert response.status_code in (401, 403)

    def test_gap_analysis_requires_auth(self, client):
        response = client.post(
            "/api/v1/gap-analysis",
            json={
                "framework": "CSRD",
                "company_profile": {"name": "Test"},
            },
        )
        assert response.status_code == 401

    def test_monitor_requires_auth(self, client):
        response = client.post(
            "/api/v1/monitor",
            json={
                "regulation_change": "Omnibus I raised CSRD thresholds",
                "company_profile": {"name": "Test"},
            },
        )
        assert response.status_code == 401

    def test_crawl_requires_auth(self, client):
        response = client.post("/api/v1/crawl", json={})
        assert response.status_code == 401

    def test_metrics_requires_admin_role(self, client, member_headers):
        """Metrics endpoint should reject non-admin users."""
        response = client.get("/api/v1/metrics", headers=member_headers)
        assert response.status_code == 403

    def test_metrics_allows_admin(self, client, auth_headers):
        response = client.get("/api/v1/metrics", headers=auth_headers)
        assert response.status_code == 200


# ------------------------------------------------------------------ #
#  Intelligence Endpoint Tests                                        #
# ------------------------------------------------------------------ #


class TestQAEndpoint:
    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_qa_success(self, mock_qa, client, auth_headers):
        mock_qa.return_value = {
            "answer": "CSRD requires sustainability reporting.",
            "citations": [{"framework": "CSRD", "reference": "Art. 19a"}],
            "confidence_score": 0.92,
        }
        response = client.post(
            "/api/v1/qa",
            json={"question": "What is the CSRD reporting deadline?"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "data" in data
        assert "metadata" in data

    def test_qa_validates_question_length(self, client, auth_headers):
        """Questions shorter than 5 chars should be rejected (Pydantic min_length=5)."""
        response = client.post(
            "/api/v1/qa",
            json={"question": "Hi"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_qa_validates_missing_question(self, client, auth_headers):
        """Missing required 'question' field should fail validation."""
        response = client.post(
            "/api/v1/qa",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_qa_with_company_profile(self, mock_qa, client, auth_headers):
        """Should accept a valid company profile alongside the question."""
        mock_qa.return_value = {
            "answer": "Based on your profile, yes.",
            "confidence_score": 0.9,
            "citations": [],
        }
        response = client.post(
            "/api/v1/qa",
            json={
                "question": "Am I subject to CSRD?",
                "company_profile": {
                    "name": "Test Srl",
                    "sector": "Manufacturing",
                    "employee_count": 2500,
                    "revenue_eur": 200000000,
                    "jurisdictions": ["IT"],
                    "applicable_frameworks": ["CSRD"],
                },
            },
            headers=auth_headers,
        )
        assert response.status_code == 200

    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_qa_with_language_parameter(self, mock_qa, client, auth_headers):
        mock_qa.return_value = {"answer": "Risposta in italiano.", "confidence_score": 0.85}
        response = client.post(
            "/api/v1/qa",
            json={"question": "Cosa dice il CSRD?", "language": "it"},
            headers=auth_headers,
        )
        assert response.status_code == 200


_VERIFIED_CITATION = {
    "framework": "GDPR",
    "reference": "Art. 17(1)",
    "quote_snippet": "ha il diritto di ottenere la cancellazione",
    "grounded": True,
    "verified": True,
    "match": "exact",
    "level": "article",
    "chunk_id": "pt-gdpr-17",
    "celex": "32016R0679",
    "article": "Art. 17",
    "paragraph": "1",
    "lang": "IT",
    "consolidated_as_of": None,
    "url": "https://eur-lex.europa.eu/legal-content/IT/TXT/?uri=CELEX:32016R0679",
    "official_quote": "ha il diritto di ottenere dal titolare la cancellazione",
}


class TestQACitationVerificationContract:
    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_enriched_citations_and_counters_in_data(self, mock_qa, client, auth_headers):
        mock_qa.return_value = {
            "answer": "Sì [GDPR, Art. 17(1)].",
            "citations": [dict(_VERIFIED_CITATION)],
            "verified_citations": 1,
            "citations_total": 1,
            "confidence_score": 0.9,
            "requires_expert_review": False,
        }
        response = client.post(
            "/api/v1/qa",
            json={"question": "Posso chiedere la cancellazione?", "language": "it"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["citations"] == [_VERIFIED_CITATION]
        assert (data["verified_citations"], data["citations_total"]) == (1, 1)
        assert data["requires_expert_review"] is False
        # The request language reaches the pipeline (caveat/abstention language).
        assert mock_qa.await_args.kwargs["language"] == "it"

    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_unverified_citations_are_flagged_at_delivery(self, mock_qa, client, auth_headers):
        mock_qa.return_value = {
            "answer": "Sì.",
            "citations": [{"framework": "GDPR", "reference": "Art. 17", "quote_snippet": "x"}],
            "confidence_score": 0.9,
            "requires_expert_review": False,
        }
        response = client.post(
            "/api/v1/qa",
            json={"question": "Can I ask for erasure?", "language": "en"},
            headers=auth_headers,
        )
        data = response.json()["data"]
        assert (data["verified_citations"], data["citations_total"]) == (0, 1)
        assert data["requires_expert_review"] is True
        assert data["confidence_score"] == 0.6
        assert data["caveats"] == [
            "None of the cited passages was found verbatim in the corpus texts: "
            "check the sources before using this answer."
        ]

    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_cached_answer_follows_the_current_policy(self, mock_qa, client, auth_headers):
        # Cached while the deploy ran in "flag" mode; served after the switch to
        # "strict": the cached path re-applies the policy -> abstention.
        from src.config import get_settings

        cached = {
            "answer": "Risposta non verificata.",
            "citations": [{"framework": "GDPR", "verified": False}],
            "verified_citations": 0,
            "citations_total": 1,
            "confidence_score": 0.6,
            "requires_expert_review": True,
            "caveats": [
                "Nessuno dei passaggi citati è stato ritrovato testualmente nei testi del "
                "corpus: verifica le fonti prima di usarla."
            ],
        }
        strict = get_settings().model_copy(update={"citation_verification": "strict"})
        with (
            patch("src.cache.response_cache.get", new=AsyncMock(return_value=cached)),
            patch("src.api.routers.intelligence.get_settings", return_value=strict),
        ):
            response = client.post(
                "/api/v1/qa",
                json={"question": "Posso chiedere la cancellazione?", "language": "it"},
                headers=auth_headers,
            )
        assert response.status_code == 200
        body = response.json()
        assert body["metadata"]["cached"] is True
        assert body["data"]["abstention_reason"] == "unverified_citations"
        assert body["data"]["citations"] == []
        assert (body["data"]["verified_citations"], body["data"]["citations_total"]) == (0, 1)
        mock_qa.assert_not_awaited()


class TestGapAnalysisEndpoint:
    @patch("src.agents.graph.arun_gap_analysis", new_callable=AsyncMock)
    def test_gap_analysis_success(self, mock_gap, client, auth_headers):
        mock_gap.return_value = {
            "framework": "CSRD",
            "overall_score": 42.5,
            "requirements": [],
            "confidence_score": 0.88,
        }
        response = client.post(
            "/api/v1/gap-analysis",
            json={
                "framework": "CSRD",
                "company_profile": {
                    "name": "Test Srl",
                    "sector": "Manufacturing",
                    "employee_count": 2500,
                },
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "success"

    def test_gap_analysis_invalid_framework(self, client, auth_headers):
        """Should reject unknown framework names (enum validation)."""
        response = client.post(
            "/api/v1/gap-analysis",
            json={
                "framework": "INVALID_FRAMEWORK",
                "company_profile": {"name": "Test Srl"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    def test_gap_analysis_missing_company_profile(self, client, auth_headers):
        """company_profile is required."""
        response = client.post(
            "/api/v1/gap-analysis",
            json={"framework": "CSRD"},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @patch("src.agents.graph.arun_gap_analysis", new_callable=AsyncMock)
    def test_gap_analysis_all_valid_frameworks(self, mock_gap, client, auth_headers):
        """All 7 supported frameworks should be accepted."""
        mock_gap.return_value = {"overall_score": 50.0, "confidence_score": 0.9}
        for fw in ["CSRD", "CSDDD", "AI_ACT", "DORA", "NIS2", "TAXONOMY", "GDPR"]:
            response = client.post(
                "/api/v1/gap-analysis",
                json={
                    "framework": fw,
                    "company_profile": {"name": "Test"},
                },
                headers=auth_headers,
            )
            assert response.status_code == 200, f"Framework {fw} should be accepted"


class TestMonitorEndpoint:
    @patch("src.agents.graph.arun_monitor_check", new_callable=AsyncMock)
    def test_monitor_success(self, mock_monitor, client, auth_headers):
        mock_monitor.return_value = {
            "applicability": "YES",
            "urgency": "HIGH",
            "impact_summary": "Significant impact on reporting obligations",
            "confidence_score": 0.85,
        }
        response = client.post(
            "/api/v1/monitor",
            json={
                "regulation_change": "CSRD threshold raised from 250 to 1000 employees by Omnibus I",
                "company_profile": {"name": "Test Srl", "employee_count": 800},
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_monitor_validates_change_length(self, client, auth_headers):
        """regulation_change shorter than 10 chars should be rejected (min_length=10)."""
        response = client.post(
            "/api/v1/monitor",
            json={
                "regulation_change": "Short",
                "company_profile": {"name": "Test"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 422


# ------------------------------------------------------------------ #
#  Data Endpoints                                                     #
# ------------------------------------------------------------------ #


class TestDataEndpoints:
    def test_processors_is_public(self, client):
        """Processor status endpoint should not require auth."""
        response = client.get("/api/v1/processors")
        assert response.status_code == 200


# ------------------------------------------------------------------ #
#  Error Handling                                                     #
# ------------------------------------------------------------------ #


class TestErrorHandling:
    @patch("src.agents.graph.arun_qa", new_callable=AsyncMock)
    def test_llm_error_returns_500(self, mock_qa, client, auth_headers):
        """When the LLM raises an exception, the endpoint should return 500."""
        mock_qa.side_effect = Exception("LLM timeout")
        response = client.post(
            "/api/v1/qa",
            json={"question": "What is CSRD compliance?"},
            headers=auth_headers,
        )
        assert response.status_code == 500
        # Italian detail for the UI, no raw exception text.
        assert "Errore interno" in response.json()["detail"]

    @pytest.mark.parametrize(
        "error_code, status, snippet",
        [
            ("llm_timeout", 504, "tempo massimo"),
            ("llm_circuit_open", 503, "non disponibile"),
            ("llm_not_configured", 503, "non è configurato"),
            ("retrieval_unavailable", 503, "Qdrant"),
            ("llm_rate_limited", 503, "Limite di richieste"),
            ("llm_auth", 502, "credenziali"),
            ("llm_provider_error", 502, "errore"),
            ("graph_error", 500, "Errore interno"),
        ],
    )
    def test_agent_error_dict_is_an_honest_http_error(
        self, client, auth_headers, error_code, status, snippet
    ):
        """An error payload from the graph must NOT come back as HTTP 200 with
        ``status: success``: it is mapped to 503/502/504/500 with an Italian
        ``detail`` and the upstream English text is not leaked."""
        error_result = {
            "error": "LLM error (gemini): upstream stack trace",
            "error_code": error_code,
            "confidence_score": 0.0,
            "requires_expert_review": True,
        }
        with patch("src.agents.graph.arun_qa", new=AsyncMock(return_value=error_result)):
            response = client.post(
                "/api/v1/qa",
                json={"question": "What is CSRD compliance?"},
                headers=auth_headers,
            )
        assert response.status_code == status
        body = response.json()
        assert "status" not in body  # no success envelope
        assert snippet.lower() in body["detail"].lower()
        assert "stack trace" not in body["detail"]

    def test_gap_analysis_and_monitor_error_dicts_are_honest_too(self, client, auth_headers):
        error_result = {"error": "LLM timed out after 120s", "error_code": "llm_timeout"}
        with patch("src.agents.graph.arun_gap_analysis", new=AsyncMock(return_value=error_result)):
            r = client.post(
                "/api/v1/gap-analysis",
                json={"framework": "CSRD", "company_profile": {"name": "Test"}},
                headers=auth_headers,
            )
        assert r.status_code == 504

        with patch("src.agents.graph.arun_monitor_check", new=AsyncMock(return_value=error_result)):
            r = client.post(
                "/api/v1/monitor",
                json={
                    "regulation_change": "Major regulatory change affecting all sectors",
                    "company_profile": {"name": "Test"},
                },
                headers=auth_headers,
            )
        assert r.status_code == 504

    def test_legacy_error_dict_without_code_is_not_a_200(self, client, auth_headers):
        with patch(
            "src.agents.graph.arun_qa",
            new=AsyncMock(return_value={"error": "Rate limited by gemini API."}),
        ):
            r = client.post(
                "/api/v1/qa",
                json={"question": "What is CSRD compliance?"},
                headers=auth_headers,
            )
        assert r.status_code == 503

    @patch("src.agents.graph.arun_gap_analysis", new_callable=AsyncMock)
    def test_gap_analysis_error_returns_500(self, mock_gap, client, auth_headers):
        mock_gap.side_effect = RuntimeError("Vector DB down")
        response = client.post(
            "/api/v1/gap-analysis",
            json={
                "framework": "CSRD",
                "company_profile": {"name": "Test"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 500

    @patch("src.agents.graph.arun_monitor_check", new_callable=AsyncMock)
    def test_monitor_error_returns_500(self, mock_monitor, client, auth_headers):
        mock_monitor.side_effect = Exception("Unexpected failure")
        response = client.post(
            "/api/v1/monitor",
            json={
                "regulation_change": "Major regulatory change affecting all sectors",
                "company_profile": {"name": "Test"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 500


# ------------------------------------------------------------------ #
#  Middleware Headers                                                  #
# ------------------------------------------------------------------ #


class TestMiddleware:
    def test_request_id_header_present(self, client):
        """Every response should include an X-Request-ID header."""
        response = client.get("/health")
        assert "X-Request-ID" in response.headers

    def test_request_id_is_uuid(self, client):
        response = client.get("/health")
        rid = response.headers.get("X-Request-ID", "")
        # Should be a valid UUID
        uuid.UUID(rid)  # raises ValueError if not valid

    def test_process_time_header_present(self, client):
        """Every response should include an X-Process-Time header."""
        response = client.get("/health")
        assert "X-Process-Time" in response.headers

    def test_process_time_is_numeric(self, client):
        response = client.get("/health")
        pt = response.headers.get("X-Process-Time", "")
        # format is "0.001s"
        assert pt.endswith("s")
        float(pt[:-1])  # should not raise


# ------------------------------------------------------------------ #
#  Service Unavailability (503)                                       #
# ------------------------------------------------------------------ #


class TestServiceDegradation:
    def test_qa_returns_503_when_qdrant_down(self, client, auth_headers):
        """When Qdrant is unavailable, intelligence endpoints should return 503."""
        from src.api.main import app_state

        original = app_state.qdrant_available
        try:
            app_state.qdrant_available = False
            response = client.post(
                "/api/v1/qa",
                json={"question": "What is CSRD compliance?"},
                headers=auth_headers,
            )
            assert response.status_code == 503
            assert "Qdrant" in response.json()["detail"]
            assert "Riprova" in response.json()["detail"]
        finally:
            app_state.qdrant_available = original

    def test_qa_returns_503_when_llm_down(self, client, auth_headers):
        """When LLM key is missing, intelligence endpoints should return 503."""
        from src.api.main import app_state

        original = app_state.llm_available
        try:
            app_state.llm_available = False
            response = client.post(
                "/api/v1/qa",
                json={"question": "What is CSRD compliance?"},
                headers=auth_headers,
            )
            assert response.status_code == 503
            assert "GOOGLE_API_KEY" in response.json()["detail"]
            assert "non è configurato" in response.json()["detail"]
        finally:
            app_state.llm_available = original

    def test_stats_shows_degraded_when_services_down(self, client):
        from src.api.main import app_state

        orig_q = app_state.qdrant_available
        orig_l = app_state.llm_available
        try:
            app_state.qdrant_available = False
            app_state.llm_available = False
            response = client.get("/api/v1/stats")
            assert response.status_code == 200
            assert response.json()["status"] == "degraded"
        finally:
            app_state.qdrant_available = orig_q
            app_state.llm_available = orig_l


# ------------------------------------------------------------------ #
#  Request Metrics                                                    #
# ------------------------------------------------------------------ #


class TestMetricsEndpoint:
    def test_metrics_returns_request_counts(self, client, auth_headers):
        """Admin metrics endpoint should return structured data."""
        # Make a few requests first to populate metrics
        client.get("/health")
        client.get("/api/v1/stats")

        response = client.get("/api/v1/metrics", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "error_count" in data
        assert "endpoints" in data
