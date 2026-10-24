"""Model settings and request parameters for the LLM providers.

Regression tests for three faults found on 2026-10-24 by running NormaAI
against the live Anthropic API:

* the default Anthropic model id (claude-sonnet-4-5-20250514) did not exist,
  and the default Gemini model (gemini-2.5-flash-preview-05-20) had been shut
  down by Google on 2025-11-18;
* the GEMINI_MODEL / ANTHROPIC_MODEL names used in .env.example were ignored,
  because the settings fields are *_MODEL_ANALYSIS;
* Claude 5 models reject `temperature` (HTTP 400), and NormaAI always sent it.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.agents.llm import anthropic_accepts_temperature, get_llm
from src.config import Settings

_MODEL_ENV = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_MODEL_ANALYSIS",
    "GEMINI_MODEL",
    "GEMINI_MODEL_ANALYSIS",
)


def _settings(monkeypatch, **env) -> Settings:
    """Settings detached from the developer's .env, with only ``env`` set."""
    for var in _MODEL_ENV:
        monkeypatch.delenv(var, raising=False)
    for var, value in env.items():
        monkeypatch.setenv(var, value)
    return Settings(_env_file=None)


@pytest.mark.parametrize(
    ("model", "accepted"),
    [
        ("claude-sonnet-4-5-20250929", True),
        ("claude-opus-4-8", True),
        ("claude-haiku-4-5-20251001", True),
        ("claude-3-5-sonnet-20241022", True),
        ("claude-haiku-5-5", False),
        ("claude-sonnet-5-5", False),
        ("claude-opus-5-5", False),
        ("claude-sonnet-5", False),
        ("claude-fable-5-1", False),
        ("", False),
        ("gpt-4o", False),
    ],
)
def test_anthropic_accepts_temperature(model, accepted):
    assert anthropic_accepts_temperature(model) is accepted


def test_default_models_are_current(monkeypatch):
    s = _settings(monkeypatch)
    assert s.anthropic_model_analysis == "claude-sonnet-5-5"
    assert s.gemini_model_analysis == "gemini-3.6-flash"


def test_env_example_names_are_read(monkeypatch):
    s = _settings(monkeypatch, ANTHROPIC_MODEL="claude-haiku-5-5", GEMINI_MODEL="gemini-3.8-flash")
    assert s.anthropic_model_analysis == "claude-haiku-5-5"
    assert s.gemini_model_analysis == "gemini-3.8-flash"


def test_full_field_names_are_still_read(monkeypatch):
    s = _settings(
        monkeypatch,
        ANTHROPIC_MODEL_ANALYSIS="claude-opus-5-5",
        GEMINI_MODEL_ANALYSIS="gemini-3.5-flash-lite",
    )
    assert s.anthropic_model_analysis == "claude-opus-5-5"
    assert s.gemini_model_analysis == "gemini-3.5-flash-lite"


def test_settings_still_accept_field_names_as_arguments(monkeypatch):
    for var in _MODEL_ENV:
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None, anthropic_model_analysis="claude-haiku-5-5")
    assert s.anthropic_model_analysis == "claude-haiku-5-5"


def _anthropic_stub(model: str) -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider="anthropic",
        llm_temperature=0.0,
        llm_max_tokens=256,
        llm_timeout_seconds=30,
        anthropic_model_analysis=model,
        anthropic_api_key="test-key",
    )


@pytest.mark.parametrize(
    ("model", "expected_temperature"),
    [("claude-haiku-5-5", None), ("claude-sonnet-4-5-20250929", 0.0)],
)
def test_get_llm_sends_temperature_only_where_accepted(model, expected_temperature):
    from langchain_core.messages import HumanMessage

    with patch("src.config.get_settings", return_value=_anthropic_stub(model)):
        llm = get_llm()
    payload = llm._get_request_payload([HumanMessage("hi")])
    assert payload["model"] == model
    if expected_temperature is None:
        assert "temperature" not in payload
    else:
        assert payload["temperature"] == expected_temperature
