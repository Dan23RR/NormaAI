"""Model settings and request parameters for the LLM providers.

Regression tests for three faults found on 2026-10-24 by running NormaAI
against the live Anthropic API:

* the default Anthropic model id (claude-sonnet-4-5-20250514) did not exist,
  and the default Gemini model (gemini-2.5-flash-preview-05-20) had been shut
  down by Google on 2025-11-18;
* the GEMINI_MODEL / ANTHROPIC_MODEL names used in .env.example were ignored,
  because the settings fields are *_MODEL_ANALYSIS;
* Claude 5 models reject `temperature` (HTTP 400), and NormaAI always sent it;
* Claude 5 replies are a list of content blocks (signed reasoning, then text),
  and reading ``.content`` as a string put the whole list in the answer, so
  JSON parsing failed and every citation was lost.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.llm import (
    CLAUDE_5_MIN_MAX_TOKENS,
    acall_llm,
    anthropic_accepts_temperature,
    anthropic_max_tokens,
    get_llm,
    message_text,
)
from src.config import Settings
from src.resilience import llm_circuit

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


_REASONING = {"type": "thinking", "thinking": "Check Article 50.", "signature": "c2lnbmF0dXJl"}


def test_message_text_keeps_only_the_text_blocks():
    reply = AIMessage(content=[_REASONING, {"type": "text", "text": '{"answer": "Yes"}'}])
    assert message_text(reply) == '{"answer": "Yes"}'


def test_message_text_plain_string_and_string_lists():
    assert message_text(AIMessage(content="plain")) == "plain"
    assert message_text(AIMessage(content=["a", "b"])) == "ab"


async def test_acall_llm_parses_the_answer_after_a_reasoning_block():
    llm_circuit.reset()
    reply = AIMessage(
        content=[
            _REASONING,
            {
                "type": "text",
                "text": '{"answer": "Yes, from 2 August 2026.", "confidence_score": 0.8}',
            },
        ]
    )
    fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=reply))
    settings = SimpleNamespace(llm_provider="anthropic", active_api_key="k")
    with (
        patch("src.config.get_settings", return_value=settings),
        patch("src.agents.llm.get_llm", return_value=fake_llm),
    ):
        result = await acall_llm("system", "question")
    assert result["answer"] == "Yes, from 2 August 2026."
    assert "signature" not in json.dumps(result)


@pytest.mark.parametrize(
    ("model", "configured", "expected"),
    [
        ("claude-haiku-5-5", 4096, CLAUDE_5_MIN_MAX_TOKENS),
        ("claude-sonnet-5-5", 32000, 32000),
        ("claude-sonnet-4-5-20250929", 4096, 4096),
        ("unknown-model", 4096, CLAUDE_5_MIN_MAX_TOKENS),
    ],
)
def test_anthropic_max_tokens_leaves_room_for_adaptive_thinking(model, configured, expected):
    assert anthropic_max_tokens(model, configured) == expected


def test_get_llm_raises_max_tokens_for_claude_5():
    from langchain_core.messages import HumanMessage

    with patch("src.config.get_settings", return_value=_anthropic_stub("claude-haiku-5-5")):
        llm = get_llm()
    assert llm._get_request_payload([HumanMessage("hi")])["max_tokens"] == CLAUDE_5_MIN_MAX_TOKENS
