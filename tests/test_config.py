"""Tests for configuration management."""

import logging

import pytest

from src.config import LLM_PROVIDERS, Settings, validate_settings_or_exit

_SECRET = "x" * 48  # long enough for the APP_SECRET_KEY check


def _clear_env(monkeypatch) -> None:
    for var in (
        "QDRANT_PORT",
        "QDRANT_HOST",
        "REDIS_URL",
        "DATABASE_URL",
        "LLM_PROVIDER",
        "MISTRAL_API_KEY",
        "MISTRAL_BASE_URL",
        "MISTRAL_MODEL",
        "MISTRAL_MODEL_ANALYSIS",
    ):
        monkeypatch.delenv(var, raising=False)


def _isolated_settings(monkeypatch, **overrides) -> Settings:
    """Settings detached from the developer's .env and shell env.

    Without this, defaults-tests fail on machines whose local .env uses
    the docker-compose.override dev ports (e.g. QDRANT_PORT=6335).
    """
    _clear_env(monkeypatch)
    return Settings(_env_file=None, **overrides)


class TestSettings:
    def test_default_values(self, monkeypatch):
        s = _isolated_settings(monkeypatch, google_api_key="test")
        assert s.llm_provider == "gemini"
        assert s.qdrant_port == 6333
        assert s.embedding_dimension == 768

    def test_corpus_defaults(self, monkeypatch):
        s = _isolated_settings(monkeypatch, google_api_key="test")
        assert s.embedding_model == "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
        assert s.corpus_languages == "EN,IT"
        assert s.corpus_language_list == ["EN", "IT"]
        assert s.eurlex_prefer_consolidated is True

    def test_corpus_language_list_parsing(self):
        assert Settings(corpus_languages=" en, it ,fr,,it").corpus_language_list == [
            "EN",
            "IT",
            "FR",
        ]
        assert Settings(corpus_languages="").corpus_language_list == ["EN"]
        assert Settings(corpus_languages="ita").corpus_language_list == ["IT"]

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

    def test_active_api_key_and_model_mistral(self, monkeypatch):
        s = _isolated_settings(monkeypatch, llm_provider="mistral", mistral_api_key="mkey")
        assert s.active_api_key == "mkey"
        assert s.active_model == "mistral-small-2603"

    def test_mistral_defaults_to_the_eu_regional_endpoint(self, monkeypatch):
        # The reason the provider exists: on the global endpoint Mistral commits
        # to no inference location (comment on the settings).
        s = _isolated_settings(monkeypatch)
        assert s.mistral_base_url == "https://api.eu.mistral.ai/v1"
        assert s.mistral_api_key == ""

    def test_mistral_settings_from_the_environment(self, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("LLM_PROVIDER", "mistral")
        monkeypatch.setenv("MISTRAL_API_KEY", "from-env")
        monkeypatch.setenv("MISTRAL_MODEL", "another-mistral-model")
        monkeypatch.setenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")
        s = Settings(_env_file=None)
        assert (s.llm_provider, s.active_api_key) == ("mistral", "from-env")
        assert s.active_model == "another-mistral-model"
        assert s.mistral_base_url == "https://api.mistral.ai/v1"

    def test_the_default_provider_is_unchanged(self, monkeypatch):
        # Mistral is not measured on the golden set (docs/MODELS.md): it must not
        # become the default by accident.
        assert _isolated_settings(monkeypatch).llm_provider == "gemini"
        assert LLM_PROVIDERS == ("gemini", "anthropic", "openrouter", "mistral")

    def test_snc_trust_layer_is_opt_in(self, monkeypatch):
        # K-1 extra LLM calls per request: never on unless a deploy asks for it.
        monkeypatch.delenv("SNC_ENABLED", raising=False)
        s = _isolated_settings(monkeypatch, google_api_key="test")
        assert s.snc_enabled is False
        assert _isolated_settings(monkeypatch, google_api_key="t", snc_enabled=True).snc_enabled

    def test_citation_verification_defaults_to_flag(self, monkeypatch):
        monkeypatch.delenv("CITATION_VERIFICATION", raising=False)
        assert _isolated_settings(monkeypatch).citation_verification == "flag"

    def test_citation_verification_strict_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CITATION_VERIFICATION", "strict")
        assert _isolated_settings(monkeypatch).citation_verification == "strict"

    def test_citation_verification_rejects_unknown_modes(self, monkeypatch):
        import pytest
        from pydantic import ValidationError

        monkeypatch.setenv("CITATION_VERIFICATION", "lenient")
        with pytest.raises(ValidationError):
            _isolated_settings(monkeypatch)


class TestProviderValidation:
    """What validate_settings_or_exit checks about the LLM provider at startup."""

    def _validate(self, monkeypatch, **overrides) -> Settings:
        settings = _isolated_settings(
            monkeypatch,
            app_env="production",
            app_secret_key=_SECRET,
            cors_origins="https://normaai.org",
            **overrides,
        )
        monkeypatch.setattr("src.config.get_settings", lambda: settings)
        return validate_settings_or_exit()

    def test_mistral_is_accepted_in_production(self, monkeypatch):
        settings = self._validate(monkeypatch, llm_provider="mistral", mistral_api_key="k")
        assert settings.llm_provider == "mistral"

    @pytest.mark.parametrize("provider", LLM_PROVIDERS)
    def test_every_listed_provider_starts(self, monkeypatch, provider):
        keys = {"mistral_api_key": "k"} if provider == "mistral" else {}
        assert self._validate(monkeypatch, llm_provider=provider, **keys).llm_provider == provider

    def test_an_unknown_provider_stops_the_api(self, monkeypatch, caplog):
        with (
            caplog.at_level(logging.ERROR, logger="normaai.config"),
            pytest.raises(SystemExit),
        ):
            self._validate(monkeypatch, llm_provider="mistrall", mistral_api_key="k")
        # The message lists the accepted values, the new one included.
        assert "gemini, anthropic, openrouter, mistral" in caplog.text

    def test_a_missing_mistral_key_stops_production(self, monkeypatch, caplog):
        # Fail fast: choosing Mistral is choosing where questions are processed,
        # and an API up without its key would only answer "llm: down".
        with (
            caplog.at_level(logging.CRITICAL, logger="normaai.config"),
            pytest.raises(SystemExit),
        ):
            self._validate(monkeypatch, llm_provider="mistral")
        assert "MISTRAL_API_KEY is not set" in caplog.text

    def test_a_mistral_url_without_tls_stops_production(self, monkeypatch, caplog):
        with (
            caplog.at_level(logging.CRITICAL, logger="normaai.config"),
            pytest.raises(SystemExit),
        ):
            self._validate(
                monkeypatch,
                llm_provider="mistral",
                mistral_api_key="k",
                mistral_base_url="http://api.eu.mistral.ai/v1",
            )
        assert "MISTRAL_BASE_URL must be an https:// URL" in caplog.text

    def test_a_missing_mistral_key_is_only_a_warning_in_development(self, monkeypatch, caplog):
        settings = _isolated_settings(monkeypatch, llm_provider="mistral", app_env="development")
        monkeypatch.setattr("src.config.get_settings", lambda: settings)
        with caplog.at_level(logging.WARNING, logger="normaai.config"):
            validate_settings_or_exit()
        assert "MISTRAL_API_KEY is not set" in caplog.text

    def test_the_global_endpoint_is_flagged(self, monkeypatch, caplog):
        # Allowed, but Mistral commits to no inference location there.
        with caplog.at_level(logging.WARNING, logger="normaai.config"):
            self._validate(
                monkeypatch,
                llm_provider="mistral",
                mistral_api_key="k",
                mistral_base_url="https://api.mistral.ai/v1",
            )
        assert "not the EU regional endpoint" in caplog.text

    def test_no_warning_when_the_mistral_key_is_set(self, monkeypatch, caplog):
        with caplog.at_level(logging.WARNING, logger="normaai.config"):
            self._validate(monkeypatch, llm_provider="mistral", mistral_api_key="k")
        assert "MISTRAL" not in caplog.text
