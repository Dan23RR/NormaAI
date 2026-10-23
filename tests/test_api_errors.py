"""Tests for src/api/errors.py - the honest HTTP mapping of agent result errors.

The agent graph returns failures as dicts (``error`` + ``error_code``); the
routers must turn them into real HTTP statuses with an Italian ``detail``:

  503  knowledge base / LLM unavailable (not configured, circuit open,
       overloaded, rate limited, retrieval down)
  502  the LLM provider failed (auth rejected, provider error)
  504  timeouts (LLM call or whole analysis)
  500  everything else (internal/graph errors, invalid input)
"""

import pytest
from fastapi import HTTPException

from src.api.errors import (
    ERROR_CODE_STATUS,
    QDRANT_UNAVAILABLE_DETAIL,
    ResultFailure,
    classify_result,
    llm_not_configured_detail,
    raise_for_result,
)


class TestMappingTable:
    @pytest.mark.parametrize(
        "code, status",
        [
            ("retrieval_unavailable", 503),
            ("llm_not_configured", 503),
            ("llm_circuit_open", 503),
            ("llm_overloaded", 503),
            ("llm_rate_limited", 503),
            ("llm_timeout", 504),
            ("graph_timeout", 504),
            ("llm_auth", 502),
            ("llm_provider_error", 502),
            ("invalid_input", 500),
            ("graph_error", 500),
            ("internal_error", 500),
        ],
    )
    def test_code_to_status(self, code, status):
        assert ERROR_CODE_STATUS[code][0] == status

    def test_details_are_italian_and_non_empty(self):
        for _code, (_status, detail) in ERROR_CODE_STATUS.items():
            assert detail
            # Every detail tells the user what to do in Italian.
            assert any(w in detail for w in ("Riprova", "Contatta", "amministratore"))

    def test_dependency_check_details_keep_operator_hints(self):
        # Operators grep logs/UI for the service name and the env var name.
        assert "Qdrant" in QDRANT_UNAVAILABLE_DETAIL
        assert "GOOGLE_API_KEY" in llm_not_configured_detail("GOOGLE_API_KEY")


class TestClassifyResult:
    def test_real_answer_is_not_a_failure(self):
        assert classify_result({"answer": "x", "confidence_score": 0.9}) is None
        assert classify_result("not a dict") is None
        assert classify_result(None) is None

    def test_coded_error_is_classified_by_code(self):
        failure = classify_result(
            {"error": "LLM timed out after 120s", "error_code": "llm_timeout"}
        )
        assert isinstance(failure, ResultFailure)
        assert failure.status_code == 504
        assert failure.error_code == "llm_timeout"
        assert failure.upstream == "LLM timed out after 120s"
        assert failure.retryable is True

    def test_unknown_code_falls_back_to_500(self):
        failure = classify_result({"error": "weird", "error_code": "something_new"})
        assert failure.status_code == 500
        assert failure.retryable is False

    @pytest.mark.parametrize(
        "message, code, status",
        [
            ("LLM timed out after 120s. Try a simpler query.", "llm_timeout", 504),
            ("GOOGLE_API_KEY not configured. Add it to your .env file.", "llm_not_configured", 503),
            ("LLM service is temporarily unavailable (circuit open)", "llm_circuit_open", 503),
            ("Rate limited by gemini API. Wait a moment and retry.", "llm_rate_limited", 503),
            ("gemini is temporarily overloaded. Retry in 30 seconds.", "llm_overloaded", 503),
            ("Knowledge base retrieval failed: qdrant down", "retrieval_unavailable", 503),
            ("Invalid API key for gemini. Check your .env file.", "llm_auth", 502),
            ("LLM error (gemini): kaboom", "llm_provider_error", 502),
        ],
    )
    def test_legacy_error_without_code_uses_keyword_fallback(self, message, code, status):
        failure = classify_result({"error": message})
        assert failure.error_code == code
        assert failure.status_code == status


class TestRaiseForResult:
    def test_noop_on_success(self):
        raise_for_result({"answer": "fine"}, endpoint="qa")  # must not raise

    def test_raises_http_exception_with_italian_detail(self):
        with pytest.raises(HTTPException) as exc:
            raise_for_result(
                {"error": "LLM error (gemini): stack trace here", "error_code": "llm_auth"},
                endpoint="qa",
            )
        assert exc.value.status_code == 502
        assert "credenziali" in exc.value.detail
        # The upstream message is logged, never shown to the client.
        assert "stack trace" not in exc.value.detail
