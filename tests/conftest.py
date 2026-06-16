"""Shared test fixtures for NormaAI."""

import os
import uuid
from unittest.mock import MagicMock

import pytest

from src.auth.security import create_access_token

# Set test environment before any imports
os.environ["APP_ENV"] = "testing"
os.environ["LLM_PROVIDER"] = "gemini"
os.environ["GOOGLE_API_KEY"] = "test-key-not-real"
os.environ["APP_SECRET_KEY"] = "test-secret-key-for-jwt-tokens-minimum-64-characters-long-abcdef"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///test.db"


@pytest.fixture
def sample_company_profile():
    return {
        "name": "Acme Srl",
        "sector": "Manufacturing",
        "employee_count": 2500,
        "revenue_eur": 200_000_000,
        "jurisdictions": ["IT", "DE"],
        "applicable_frameworks": ["CSRD", "CSDDD"],
        "existing_documents": "Annual sustainability report 2024",
    }


@pytest.fixture
def sample_qa_response():
    return {
        "answer": "Companies with over 1,000 employees must report under CSRD [CSRD, Art. 19a(1)].",
        "citations": [
            {
                "framework": "CSRD",
                "reference": "Art. 19a(1)",
                "quote_snippet": "Large undertakings shall include...",
            }
        ],
        "confidence_score": 0.9,
        "requires_expert_review": False,
        "related_frameworks": ["CSDDD"],
        "caveats": [],
    }


@pytest.fixture
def sample_gap_response():
    return {
        "framework": "CSRD",
        "overall_score": 45.0,
        "status_summary": {
            "compliant": 2,
            "partially_compliant": 3,
            "non_compliant": 5,
            "not_applicable": 1,
            "in_evolution": 1,
        },
        "requirements": [],
        "top_recommendations": ["Establish double materiality assessment process"],
        "confidence_score": 0.85,
        "requires_expert_review": False,
    }


@pytest.fixture
def mock_llm_response():
    """Mock LLM that returns a valid JSON response."""
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(
        content='{"answer": "Test answer", "confidence_score": 0.9, "citations": [], "requires_expert_review": false}'
    )
    return mock


@pytest.fixture
def auth_headers():
    """Generate valid JWT auth headers for testing."""
    token = create_access_token(
        user_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}
