"""Honest HTTP error mapping for agent results.

The agent graph never raises: LLM, retrieval and graph failures come back as a
result dict carrying ``error`` (human-readable, English, for logs) and
``error_code`` (machine-readable, see ``ERROR_CODE_STATUS``). Before this module
the routers wrapped such dicts in a ``{"status": "success"}`` envelope with HTTP
200, so the UI showed a green success with an error inside. Here every failure
becomes a real HTTP status with an Italian ``detail`` the UI can display as-is:

- 503: the knowledge base (Qdrant) or the LLM is unavailable (not configured,
       circuit open, overloaded, rate limited)
- 502: the LLM provider failed (rejected credentials, returned an error)
- 504: a timeout (LLM call or whole analysis)
- 500: anything else (internal/graph errors, invalid input)

The upstream English message is never sent to the client: it is logged by the
caller together with the code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# UI-facing details (Italian) for the dependency checks done before the graph runs.
QDRANT_UNAVAILABLE_DETAIL = (
    "La base di conoscenza normativa (Qdrant) non è disponibile. Riprova tra qualche minuto."
)


def llm_not_configured_detail(key_name: str) -> str:
    """Detail for a missing provider API key (keeps the env var name for operators)."""
    return (
        f"Il provider LLM non è configurato sul server ({key_name} mancante). "
        "Contatta l'amministratore."
    )


_DETAIL_LLM_UNAVAILABLE = (
    "Il provider LLM è temporaneamente non disponibile. Riprova tra qualche istante."
)
_DETAIL_INTERNAL = "Errore interno durante l'analisi. Riprova più tardi."

# error_code -> (HTTP status, Italian detail). Codes are produced by
# src.agents.llm._make_error_response, src.agents.nodes.retrieve_node and
# src.agents.graph; keep the three in sync when adding one.
ERROR_CODE_STATUS: dict[str, tuple[int, str]] = {
    "retrieval_unavailable": (503, QDRANT_UNAVAILABLE_DETAIL),
    "llm_not_configured": (
        503,
        "Il provider LLM non è configurato sul server (chiave API mancante). "
        "Contatta l'amministratore.",
    ),
    "llm_circuit_open": (
        503,
        "Il provider LLM è temporaneamente non disponibile dopo errori ripetuti. "
        "Riprova tra un minuto.",
    ),
    "llm_overloaded": (
        503,
        "Il provider LLM è temporaneamente sovraccarico. Riprova tra qualche istante.",
    ),
    "llm_rate_limited": (
        503,
        "Limite di richieste del provider LLM raggiunto. Riprova tra qualche istante.",
    ),
    "llm_timeout": (
        504,
        "Il provider LLM non ha risposto entro il tempo massimo. "
        "Riprova, se possibile con una domanda più semplice.",
    ),
    "graph_timeout": (
        504,
        "L'analisi non è stata completata entro il tempo massimo. Riprova più tardi.",
    ),
    "llm_auth": (
        502,
        "Il provider LLM ha rifiutato le credenziali del server. Contatta l'amministratore.",
    ),
    "llm_provider_error": (
        502,
        "Il provider LLM ha restituito un errore. Riprova più tardi.",
    ),
    "invalid_input": (500, _DETAIL_INTERNAL),
    "graph_error": (500, _DETAIL_INTERNAL),
    "internal_error": (500, _DETAIL_INTERNAL),
}

# Fallback classification for legacy error dicts that carry no error_code
# (same keyword heuristics as src.agents.llm._make_error_response).
_LEGACY_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("timed out", "timeout"), "llm_timeout"),
    (("not configured",), "llm_not_configured"),
    (("circuit",), "llm_circuit_open"),
    (("rate limit", "rate limited", "quota", "429"), "llm_rate_limited"),
    (("overloaded", "503"), "llm_overloaded"),
    (("retrieval failed", "knowledge base"), "retrieval_unavailable"),
    (("api key", "api_key", "auth"), "llm_auth"),
)


@dataclass(frozen=True)
class ResultFailure:
    """A failed agent result, classified for the HTTP layer."""

    status_code: int
    error_code: str
    detail: str  # Italian, safe to show to the end user
    upstream: str  # original English message (logs only)

    @property
    def retryable(self) -> bool:
        """True when a retry may succeed (transient upstream condition)."""
        return self.status_code in (503, 504)


def _legacy_code(message: str) -> str:
    lowered = message.lower()
    for keywords, code in _LEGACY_KEYWORDS:
        if any(kw in lowered for kw in keywords):
            return code
    return "llm_provider_error"


def classify_result(result: Any) -> ResultFailure | None:
    """Return the failure carried by an agent result, or None for a real answer."""
    if not isinstance(result, dict) or "error" not in result:
        return None
    upstream = str(result.get("error") or "")
    code = str(result.get("error_code") or "") or _legacy_code(upstream)
    status, detail = ERROR_CODE_STATUS.get(code, (500, _DETAIL_INTERNAL))
    return ResultFailure(status_code=status, error_code=code, detail=detail, upstream=upstream)


def raise_for_result(result: Any, *, endpoint: str) -> None:
    """Raise an honest HTTPException when ``result`` carries an error."""
    failure = classify_result(result)
    if failure is None:
        return
    logger.warning(
        "agent_result_error",
        extra={
            "endpoint": endpoint,
            "error_code": failure.error_code,
            "status_code": failure.status_code,
            "upstream": failure.upstream,
        },
    )
    raise HTTPException(status_code=failure.status_code, detail=failure.detail)
