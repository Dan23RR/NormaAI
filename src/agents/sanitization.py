"""Input sanitization for prompt injection prevention.

Extracted from graph.py for single-responsibility.
"""

import logging
import re

logger = logging.getLogger(__name__)


def sanitize_input(text: str, max_length: int = 5000) -> str:
    """Sanitize user input to prevent prompt injection attacks."""
    if not isinstance(text, str):
        return str(text)[:max_length]

    text = text[:max_length]

    injection_patterns = [
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        r"(?i)ignore\s+all\s+instructions",
        r"(?i)disregard\s+(all\s+)?(above|previous)",
        r"(?i)system\s+prompt",
        r"(?i)you\s+are\s+now",
        r"(?i)new\s+instructions\s*:",
        r"(?i)forget\s+(all\s+)?(previous|your)\s+(instructions|rules)",
        r"(?i)override\s+(all\s+)?(previous|your)\s+(instructions|rules)",
        r"(?i)act\s+as\s+(a\s+)?different",
        r"(?i)pretend\s+(to\s+be|you\s+are)",
    ]

    for pattern in injection_patterns:
        match = re.search(pattern, text)
        if match:
            logger.warning("prompt_injection_blocked: pattern=%s", match.group()[:50])
            text = re.sub(pattern, "[BLOCKED]", text)

    return text


def sanitize_profile(profile: dict) -> dict:
    """Sanitize company profile fields to prevent injection and enforce types."""
    if not isinstance(profile, dict):
        return {}

    sanitized = {}

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
