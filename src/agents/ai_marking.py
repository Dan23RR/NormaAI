"""Machine-readable marking of the text Chiedi generates (AI Act, Art. 50(2)).

NormaAI's Q&A writes text with a language model, so its outputs are marked,
in a machine-readable way, as artificially generated. Every Q&A answer the
API serves carries two fields (POST /api/v1/qa, fresh or from the cache, in
``data``; /api/v1/qa/stream in its final ``done`` event):

- ``ai_generated``: True when the answer text was written by the language
  model; False for an abstention, whose text NormaAI writes itself (no
  passage found, every quote unverified under the strict policy, the SNC
  layer);
- ``generator``: ``{"system": "NormaAI Chiedi", "provider": ..., "model": ...}``,
  the provider and model that wrote the text (None for an abstention).

The provider and model are recorded when the answer is generated
(src.agents.nodes._apply_citation_verification, which also covers the answer
the SNC layer serves), so an answer served from the cache names the model
that wrote it; what the model itself put in these keys is overwritten there.
The Chiedi page shows "Testo generato con un sistema di IA" on every answer
marked so.
"""

from __future__ import annotations

from typing import Any

GENERATOR_SYSTEM = "NormaAI Chiedi"


def generator_info(settings: Any) -> dict[str, str | None]:
    """The system, provider and model that write Chiedi's answers with ``settings``."""
    provider = getattr(settings, "llm_provider", None)
    model = getattr(settings, "active_model", None)
    return {
        "system": GENERATOR_SYSTEM,
        "provider": provider if isinstance(provider, str) and provider else None,
        "model": model if isinstance(model, str) and model else None,
    }


def _recorded(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("system") == GENERATOR_SYSTEM
        and isinstance(value.get("model"), str)
        and bool(value.get("model"))
    )


def mark_ai_generated(result: Any, settings: Any = None, *, generated: bool = False) -> Any:
    """Write ``ai_generated`` and ``generator`` on a Q&A answer (module docstring); idempotent.

    ``generated``: the model has just written this answer with ``settings``,
    so its generator is recorded whatever the result holds. Otherwise a
    generator recorded earlier is kept and a missing one is filled in from
    ``settings`` (the current configuration). Errors are left alone.
    """
    if not isinstance(result, dict) or result.get("error") or result.get("error_code"):
        return result
    if result.get("abstention_reason"):
        result["ai_generated"] = False
        result["generator"] = {"system": GENERATOR_SYSTEM, "provider": None, "model": None}
        return result
    result["ai_generated"] = True
    if generated or not _recorded(result.get("generator")):
        if settings is None:
            from src.config import get_settings

            settings = get_settings()
        result["generator"] = generator_info(settings)
    return result
