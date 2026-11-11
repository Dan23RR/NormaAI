"""Model settings and request parameters for the LLM providers.

Regression tests for faults found on 2026-10-24 by running NormaAI against
the live Anthropic API:

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

# The real client is imported here, at collection time, on purpose: other
# tests stub modules with patch.dict("sys.modules", ...), which on exit also
# drops modules first imported inside the block. If torch (pulled in lazily
# through langchain_core and transformers) is dropped that way, importing it
# again fails with "function '_has_torch_function' already has a docstring".
import httpx
import langchain_anthropic  # noqa: F401
import pytest
from langchain_core.messages import AIMessage

from src.agents.llm import (
    CLAUDE_5_MIN_MAX_TOKENS,
    acall_llm,
    anthropic_accepts_temperature,
    anthropic_max_tokens,
    call_llm,
    get_llm,
    message_text,
)
from src.config import Settings
from src.resilience import llm_circuit

# The OpenAI-compatible client (OpenRouter, Mistral) is the optional extra
# "openrouter": in the Docker image, not in a plain `poetry install`. Imported
# at collection time for the reason given above; the tests that need the real
# client are skipped without it.
try:
    import langchain_openai  # noqa: F401
except ImportError:  # pragma: no cover - depends on the installed extras
    langchain_openai = None

needs_openai_client = pytest.mark.skipif(
    langchain_openai is None, reason="langchain-openai (extra 'openrouter') is not installed"
)

_MODEL_ENV = (
    "ANTHROPIC_MODEL",
    "ANTHROPIC_MODEL_ANALYSIS",
    "GEMINI_MODEL",
    "GEMINI_MODEL_ANALYSIS",
    "MISTRAL_MODEL",
    "MISTRAL_MODEL_ANALYSIS",
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
    # Mistral Small 4 by its dated id (docs.mistral.ai, read 2026-11-11).
    assert s.mistral_model_analysis == "mistral-small-2603"


def test_env_example_names_are_read(monkeypatch):
    s = _settings(
        monkeypatch,
        ANTHROPIC_MODEL="claude-haiku-5-5",
        GEMINI_MODEL="gemini-3.8-flash",
        MISTRAL_MODEL="another-mistral-model",
    )
    assert s.anthropic_model_analysis == "claude-haiku-5-5"
    assert s.gemini_model_analysis == "gemini-3.8-flash"
    assert s.mistral_model_analysis == "another-mistral-model"


def test_full_field_names_are_still_read(monkeypatch):
    s = _settings(
        monkeypatch,
        ANTHROPIC_MODEL_ANALYSIS="claude-opus-5-5",
        GEMINI_MODEL_ANALYSIS="gemini-3.5-flash-lite",
        MISTRAL_MODEL_ANALYSIS="a-third-mistral-model",
    )
    assert s.anthropic_model_analysis == "claude-opus-5-5"
    assert s.gemini_model_analysis == "gemini-3.5-flash-lite"
    assert s.mistral_model_analysis == "a-third-mistral-model"


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


# ─── Mistral (OpenAI-compatible endpoint, real client, no network) ───────────

# Request fields of POST /v1/chat/completions in Mistral's API reference
# (docs.mistral.ai/api, read 2026-11-11). `max_completion_tokens`, which
# ChatOpenAI sends for its own `max_tokens`, is not among them.
MISTRAL_REQUEST_FIELDS = {
    "frequency_penalty",
    "guardrails",
    "logprobs",
    "max_tokens",
    "messages",
    "metadata",
    "min_tokens",
    "model",
    "n",
    "parallel_tool_calls",
    "prediction",
    "presence_penalty",
    "prompt_cache_key",
    "prompt_logprobs",
    "prompt_mode",
    "random_seed",
    "reasoning_effort",
    "repetition_penalty",
    "response_format",
    "safe_prompt",
    "service_tier",
    "stop",
    "stream",
    "temperature",
    "tool_choice",
    "tools",
    "top_k",
    "top_logprobs",
    "top_p",
    "top_prompt_logprobs",
}


def _mistral_stub(**overrides) -> SimpleNamespace:
    stub = SimpleNamespace(
        llm_provider="mistral",
        llm_temperature=0.0,
        llm_max_tokens=256,
        llm_timeout_seconds=30,
        mistral_model_analysis="mistral-small-2603",
        mistral_base_url="https://api.eu.mistral.ai/v1",
        mistral_api_key="test-key",
        active_api_key="test-key",
    )
    for name, value in overrides.items():
        setattr(stub, name, value)
    return stub


def _mistral_reply(content) -> dict:
    return {
        "id": "cmpl-1",
        "object": "chat.completion",
        "created": 1,
        "model": "mistral-small-2603",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12},
    }


@pytest.fixture
def mistral_wire(monkeypatch):
    """Answer the client's HTTP request in process and record what it sent."""
    sent: dict = {"reply": _mistral_reply('{"answer": "Yes.", "confidence_score": 0.8}')}

    def handle_request(self, request):
        sent["method"] = request.method
        sent["url"] = str(request.url)
        sent["authorization"] = request.headers.get("authorization")
        sent["headers"] = {name.lower() for name in request.headers}
        sent["body"] = json.loads(request.read())
        return httpx.Response(200, json=sent["reply"])

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
    llm_circuit.reset()
    yield sent
    llm_circuit.reset()


@needs_openai_client
def test_mistral_request_payload_names_the_limit_max_tokens():
    from langchain_core.messages import HumanMessage

    with patch("src.config.get_settings", return_value=_mistral_stub()):
        llm = get_llm()
    payload = llm._get_request_payload([HumanMessage("hi")])
    assert payload["model"] == "mistral-small-2603"
    assert payload["temperature"] == 0.0
    assert payload["extra_body"] == {"max_tokens": 256}
    assert "max_completion_tokens" not in payload
    assert "max_tokens" not in payload


@needs_openai_client
def test_mistral_request_on_the_wire(mistral_wire):
    with patch("src.config.get_settings", return_value=_mistral_stub()):
        result = call_llm("system prompt", "question")

    assert result == {"answer": "Yes.", "confidence_score": 0.8}
    assert mistral_wire["method"] == "POST"
    # The EU regional endpoint, and the key only as a bearer token.
    assert mistral_wire["url"] == "https://api.eu.mistral.ai/v1/chat/completions"
    assert mistral_wire["authorization"] == "Bearer test-key"
    # No OpenRouter attribution headers on a request to Mistral.
    assert not {"http-referer", "x-title"} & mistral_wire["headers"]
    body = mistral_wire["body"]
    assert set(body) <= MISTRAL_REQUEST_FIELDS
    assert body["model"] == "mistral-small-2603"
    assert body["max_tokens"] == 256
    assert body["temperature"] == 0.0
    assert body["stream"] is False
    assert body["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "question"},
    ]


@needs_openai_client
def test_mistral_base_url_setting_reaches_the_client(mistral_wire):
    stub = _mistral_stub(mistral_base_url="https://api.mistral.ai/v1")
    with patch("src.config.get_settings", return_value=stub):
        call_llm("system prompt", "question")
    assert mistral_wire["url"] == "https://api.mistral.ai/v1/chat/completions"


@needs_openai_client
@pytest.mark.filterwarnings("ignore:Pydantic serializer warnings")
def test_mistral_reply_with_a_reasoning_chunk_is_parsed(mistral_wire):
    # With reasoning on, Mistral returns the content as a list of chunks: a
    # "thinking" one (itself a list of text chunks), then the text.
    mistral_wire["reply"] = _mistral_reply(
        [
            {"type": "thinking", "thinking": [{"type": "text", "text": "Check Article 50."}]},
            {"type": "text", "text": '{"answer": "Yes, from 2 August 2026.", "citations": []}'},
        ]
    )
    with patch("src.config.get_settings", return_value=_mistral_stub()):
        result = call_llm("system prompt", "question")
    assert result == {"answer": "Yes, from 2 August 2026.", "citations": []}
    assert "Check Article 50." not in json.dumps(result)


def test_message_text_drops_a_mistral_thinking_chunk():
    reply = AIMessage(
        content=[
            {"type": "thinking", "thinking": [{"type": "text", "text": "Check Article 50."}]},
            {"type": "text", "text": '{"answer": "Yes"}'},
        ]
    )
    assert message_text(reply) == '{"answer": "Yes"}'
