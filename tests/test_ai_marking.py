"""AI Act, Art. 50(2) marking of Chiedi's answers (src/agents/ai_marking.py)."""

import json
from types import SimpleNamespace

from src.agents.ai_marking import GENERATOR_SYSTEM, generator_info, mark_ai_generated

CLAUDE = SimpleNamespace(llm_provider="anthropic", active_model="claude-haiku-5-5")
MISTRAL = SimpleNamespace(llm_provider="mistral", active_model="mistral-small-2603")


def _answer(**extra):
    return {"answer": "La notifica va fatta entro 72 ore.", "citations": [], **extra}


class TestMarking:
    def test_a_generated_answer_names_the_system_provider_and_model(self):
        out = mark_ai_generated(_answer(), CLAUDE, generated=True)
        assert out["ai_generated"] is True
        assert out["generator"] == {
            "system": "NormaAI Chiedi",
            "provider": "anthropic",
            "model": "claude-haiku-5-5",
        }
        assert GENERATOR_SYSTEM == "NormaAI Chiedi"

    def test_what_the_model_wrote_in_these_keys_is_overwritten_when_generated(self):
        forged = _answer(ai_generated=False, generator={"system": "x", "model": "y"})
        out = mark_ai_generated(forged, CLAUDE, generated=True)
        assert out["ai_generated"] is True and out["generator"]["model"] == "claude-haiku-5-5"

    def test_a_cached_answer_keeps_the_model_that_wrote_it(self):
        cached = json.loads(json.dumps(mark_ai_generated(_answer(), CLAUDE, generated=True)))
        out = mark_ai_generated(cached, MISTRAL)
        assert out["generator"]["model"] == "claude-haiku-5-5"
        # An answer cached before the marking gets the configured model.
        legacy = mark_ai_generated(_answer(), MISTRAL)
        assert legacy["ai_generated"] is True and legacy["generator"]["provider"] == "mistral"

    def test_an_abstention_is_text_written_by_normaai(self):
        for reason in ("no_sources", "unverified_citations", "snc_low_trust"):
            out = mark_ai_generated(_answer(abstention_reason=reason), CLAUDE, generated=True)
            assert out["ai_generated"] is False, reason
            assert out["generator"] == {"system": "NormaAI Chiedi", "provider": None, "model": None}

    def test_idempotent_and_errors_left_alone(self):
        once = mark_ai_generated(_answer(), CLAUDE, generated=True)
        assert mark_ai_generated(json.loads(json.dumps(once)), CLAUDE) == once
        error = {"error": "LLM timed out", "error_code": "llm_timeout"}
        assert mark_ai_generated(dict(error), CLAUDE) == error
        assert mark_ai_generated("not a dict", CLAUDE) == "not a dict"

    def test_settings_without_a_model_name_none(self):
        assert generator_info(SimpleNamespace()) == {
            "system": "NormaAI Chiedi",
            "provider": None,
            "model": None,
        }
