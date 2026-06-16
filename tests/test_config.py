"""Tests for configuration management."""

from src.config import Settings


def _isolated_settings(monkeypatch, **overrides) -> Settings:
    """Settings detached from the developer's .env and shell env.

    Without this, defaults-tests fail on machines whose local .env uses
    the docker-compose.override dev ports (e.g. QDRANT_PORT=6335).
    """
    for var in ("QDRANT_PORT", "QDRANT_HOST", "REDIS_URL", "DATABASE_URL", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    return Settings(_env_file=None, **overrides)


class TestSettings:
    def test_default_values(self, monkeypatch):
        s = _isolated_settings(monkeypatch, google_api_key="test")
        assert s.llm_provider == "gemini"
        assert s.qdrant_port == 6333
        assert s.embedding_dimension == 768

    def test_active_api_key_gemini(self):
        s = Settings(llm_provider="gemini", google_api_key="gkey")
        assert s.active_api_key == "gkey"

    def test_active_api_key_anthropic(self):
        s = Settings(llm_provider="anthropic", anthropic_api_key="akey")
        assert s.active_api_key == "akey"

    def test_active_model_gemini(self):
        s = Settings(llm_provider="gemini", google_api_key="test")
        assert "gemini" in s.active_model

    def test_active_model_anthropic(self):
        s = Settings(llm_provider="anthropic", anthropic_api_key="test")
        assert "claude" in s.active_model
