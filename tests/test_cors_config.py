"""CORS must never combine a wildcard origin with credentialed requests in prod.

``main.py`` registers CORSMiddleware with ``allow_credentials=True``; a ``*``
origin under that is a credential-leak footgun. Defense in depth:
``cors_origin_list`` fails closed (empties the list) and
``validate_settings_or_exit`` fails fast at startup. TIER 1 (pure config; no
DB/network).
"""

from __future__ import annotations

import pytest

from src.config import Settings, validate_settings_or_exit

_SECRET = "x" * 48  # >= 32 chars so the secret check passes and CORS is reached


def _settings(**overrides) -> Settings:
    base = {"app_secret_key": _SECRET, "google_api_key": "k", "llm_provider": "gemini"}
    base.update(overrides)
    return Settings(**base)


def test_wildcard_origin_emptied_in_production():
    s = _settings(app_env="production", cors_origins="*")
    assert s.cors_origin_list == []  # fail closed: no origin allowed


def test_explicit_origins_kept_in_production():
    s = _settings(
        app_env="production",
        cors_origins="https://normaai.org,https://app.normaai.org",
    )
    assert s.cors_origin_list == ["https://normaai.org", "https://app.normaai.org"]


def test_wildcard_allowed_in_dev():
    s = _settings(app_env="development", cors_origins="*")
    assert s.cors_origin_list == ["*"]  # dev convenience only, never reached in prod


def test_validate_exits_on_wildcard_in_production(monkeypatch):
    s = _settings(app_env="production", cors_origins="*")
    monkeypatch.setattr("src.config.get_settings", lambda: s)
    with pytest.raises(SystemExit):
        validate_settings_or_exit()


def test_validate_passes_with_explicit_origins_in_production(monkeypatch):
    s = _settings(app_env="production", cors_origins="https://normaai.org")
    monkeypatch.setattr("src.config.get_settings", lambda: s)
    # Other prod gates satisfied (valid provider+key, secret >= 32) -> no exit.
    assert validate_settings_or_exit() is s
