"""Prompt-injection telemetry for user-supplied text.

WHAT THIS IS (and what it is NOT)
---------------------------------
This module is an *observable tripwire*, not a security barrier.

It scans free-text user input (queries, company-profile fields) for the common
imperative/jailbreak phrasings used in prompt-injection attempts -- in BOTH
English and Italian, since NormaAI is an Italian-first product -- and emits a
structured ``prompt_injection_detected`` log event so attempts are observable.

It deliberately does NOT rewrite or redact the input. An earlier version
replaced matches with ``[BLOCKED]``; that silently corrupted legitimate Italian
compliance questions (e.g. "le regole precedenti", "supera i limiti") and gave
false confidence. A regex denylist is trivially bypassable (obfuscation,
encoding, novel phrasings, other languages), so it can only ever be telemetry.

The REAL defenses against prompt injection in this codebase are structural:
strict system/user message separation (untrusted text never lands in the system
prompt), output grounding against retrieved chunks, and Chain-of-Verification
(CoVe) citation validation. This layer exists to *measure*, not to protect.

Design constraints: dependency-free (stdlib ``re``), fast (patterns compiled
once at import), low telemetry-noise on Italian compliance prose.
"""

from __future__ import annotations

import re

try:  # structlog is the project-wide logging standard; fall back to stdlib.
    import structlog

    logger = structlog.get_logger("normaai.sanitization")
    _STRUCTLOG = True
except Exception:  # pragma: no cover - structlog is a hard dependency in prod
    import logging

    logger = logging.getLogger(__name__)
    _STRUCTLOG = False


# ── Injection denylist ───────────────────────────────────────────────────────
# Each entry is (label, pattern). The label is a stable identifier emitted in
# telemetry so detections can be grouped/alerted on without leaking attacker
# text. Patterns are case-insensitive and Unicode-aware, with bounded
# quantifiers (no ReDoS), and require the injection-specific collocation so
# benign Italian compliance words ("sistema", "regole precedenti", "supera i
# limiti", "istruzioni operative") do NOT match. See tests/test_sanitization.py.
_INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    # ── English ──────────────────────────────────────────────────────────
    ("en.ignore_previous", r"ignore\s+(all\s+)?previous\s+instructions"),
    ("en.ignore_all", r"ignore\s+all\s+instructions"),
    ("en.disregard_above", r"disregard\s+(all\s+|the\s+)?(above|previous)"),
    ("en.system_prompt", r"system\s+prompt"),
    ("en.you_are_now", r"you\s+are\s+now"),
    ("en.new_instructions", r"new\s+instructions\s*:"),
    ("en.forget", r"forget\s+(all\s+)?(previous|your)\s+(instructions|rules)"),
    ("en.override", r"override\s+(all\s+)?(previous|your)\s+(instructions|rules)"),
    ("en.act_as", r"act\s+as\s+(a\s+)?(different|an?\s+)"),
    ("en.pretend", r"pretend\s+(to\s+be|you\s+are)"),
    ("en.bypass", r"bypass\s+(your\s+|the\s+|all\s+)?(restrictions|rules|safety|filters)"),
    # ── Italian ──────────────────────────────────────────────────────────
    (
        "it.ignora_istruzioni",
        r"ignor[ai]\s+(tutte\s+le\s+|le\s+|ogni\s+|qualsiasi\s+)?(istruzion[ei]|prompt)",
    ),
    (
        "it.dimentica",
        r"dimentic[ah]\s+(tutte\s+le\s+|le\s+|ogni\s+|quelle\s+|i\s+)?(istruzion[ei]|regol[ae]|comand[oi]|prompt)",
    ),
    (
        "it.non_tenere_conto",
        r"non\s+tenere\s+conto\s+(di\s+|del\w*\s+|delle\s+)?(istruzion[ei]|prompt)",
    ),
    (
        "it.non_seguire",
        r"non\s+seguire\s+(le\s+|piu'?\s+|più\s+)?(istruzion[ei]|indicazion[ei]|prompt)",
    ),
    # Injection-specific: "istruzioni/comandi/direttive precedenti" (NOT the
    # benign compliance collocation "regole/esercizi precedenti").
    ("it.istruzioni_precedenti", r"(istruzion[ei]|comand[oi]|direttiv[ae])\s+precedent[ei]"),
    ("it.prompt_di_sistema", r"(prompt|istruzion[ei])\s+(di\s+|del\s+)sistema"),
    # Reveal the SYSTEM prompt/instructions specifically (not "mostrami le
    # istruzioni operative").
    (
        "it.rivela_prompt",
        r"(rivel\w+|mostr\w+|dimm[ei]|dammi|elenca|stamp\w+)\s+.{0,20}(prompt\s+(di\s+|del\s+)?sistema|istruzioni\s+(di\s+|del\s+)?sistema|tue\s+istruzioni|prompt\s+iniziale|system\s+prompt)",
    ),
    ("it.sei_ora", r"(sei\s+ora|adesso\s+sei|da\s+ora\s+(in\s+poi\s+)?sei|ora\s+sei)\b"),
    ("it.agisci_come", r"(agisci|comportat[ei])\s+come\b"),
    ("it.fingi_di_essere", r"(fing[ei]|fai\s+finta)\s+(di\s+)?(essere|esser)\b"),
    ("it.impersona", r"\bimpersona\s+(un|il|la|l'|i\s|gli\s)"),
    ("it.nuove_istruzioni", r"nuov[ei]\s+(istruzion[ei]|regol[ae]|comand[oi]|direttiv[ae])\s*:"),
    # Override requires a possessive ("le tue / i tuoi") so benign "annulla le
    # restrizioni doganali" does NOT match.
    (
        "it.sovrascrivi",
        r"(sovrascriv\w+|disattiv\w+|ignor\w+|annull\w+)\s+(le\s+tue|i\s+tuoi|tutte\s+le\s+tue|ogni\s+tua)\s+(istruzion[ei]|regol[ae]|restrizion[ei]|limit\w+|direttiv[ae])",
    ),
    # Bypass WITHOUT the over-broad "super\\w+" (which matched benign "superare").
    (
        "it.bypassa",
        r"(bypass\w+|aggir\w+|elud\w+|scavalc\w+)\s+(?:(?:le|i|gli|tutte|tutti|ogni|qualsiasi|tue|tuoi|tua|tuo)\s+){0,3}(restrizion[ei]|regol[ae]|limit\w+|protezion[ei]|sicurezz[ae]|controll[oi]|filtr[oi])",
    ),
    ("it.senza_restrizioni", r"senza\s+(restrizion[ei]|censur[ae]|filtr[oi]|limitazion[ei])"),
    (
        "it.come_se_non",
        r"come\s+se\s+non\s+(avessi|ci\s+fossero|esistessero)\s+\w*\s*(regol[ae]|limit\w+|restrizion[ei])",
    ),
)

_COMPILED: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (label, re.compile(pattern, re.IGNORECASE | re.UNICODE))
    for label, pattern in _INJECTION_PATTERNS
)


def detect_injection(text: str) -> list[str]:
    """Return the labels of every injection pattern that matches ``text``.

    Pure function: no mutation, no logging. Empty list means no known pattern
    matched (which does NOT imply the text is safe -- see module docstring).
    """
    if not isinstance(text, str) or not text:
        return []
    return [label for label, rx in _COMPILED if rx.search(text)]


def _log_detection(labels: list[str]) -> None:
    if _STRUCTLOG:
        logger.warning(
            "prompt_injection_detected",
            pattern_count=len(labels),
            patterns=labels,
            note="telemetry only; not a barrier (see sanitization.py)",
        )
    else:  # pragma: no cover
        logger.warning("prompt_injection_detected patterns=%s", labels)


def sanitize_input(text: str, max_length: int = 5000) -> str:
    """Length-cap user input and emit telemetry on injection patterns.

    Returns the (truncated) input UNCHANGED -- detection is observed, not
    enforced here. The real defenses are structural (system/user separation,
    output grounding, CoVe). See the module docstring.
    """
    if not isinstance(text, str):
        return str(text)[:max_length]
    text = text[:max_length]
    labels = detect_injection(text)
    if labels:
        _log_detection(labels)
    return text


def sanitize_profile(profile: dict) -> dict:
    """Sanitize company-profile fields: length-cap + type-enforce + telemetry."""
    if not isinstance(profile, dict):
        return {}

    sanitized: dict = {}

    str_fields = ["name", "sector", "existing_documents"]
    for field in str_fields:
        if field in profile:
            sanitized[field] = sanitize_input(str(profile[field]), max_length=1000)

    int_fields = ["employee_count", "revenue_eur"]
    for field in int_fields:
        if field in profile:
            try:
                sanitized[field] = int(profile[field])
            except (ValueError, TypeError):
                sanitized[field] = 0

    list_fields = ["jurisdictions", "applicable_frameworks"]
    for field in list_fields:
        if field in profile and isinstance(profile[field], list):
            sanitized[field] = [sanitize_input(str(v), 50) for v in profile[field][:20]]

    return sanitized
