"""
Response Parser for NormaAI API.

Transforms real API HTTP responses into the format expected by
the metrics engine (extract_findings_from_output).

The real API wraps responses as:
    {
        "status": "success",
        "data": { ... actual payload ... },
        "metadata": { ... }
    }

This module unwraps them and normalizes the structure for
comparison with expected findings.
"""

import logging
import re

logger = logging.getLogger(__name__)


def parse_api_response(
    api_response: dict,
    task_type: str,
) -> dict:
    """
    Parse a full NormaAI API response into the flat format
    expected by metrics.extract_findings_from_output().

    Args:
        api_response: Raw HTTP JSON response from the API
        task_type: "gap_analysis", "qa", or "monitor"

    Returns:
        Normalized dict with findings in the format metrics.py expects
    """
    if not isinstance(api_response, dict):
        logger.warning(f"Unexpected response type: {type(api_response)}")
        return {"error": "Invalid response format"}

    # Check for API-level errors
    status = api_response.get("status", "")
    if status == "error":
        return {
            "error": api_response.get("detail", api_response.get("message", "Unknown error")),
        }

    # Unwrap the data envelope
    data = api_response.get("data", api_response)
    metadata = api_response.get("metadata", {})

    # Dispatch to task-specific parser
    if task_type == "gap_analysis":
        return _parse_gap_analysis(data, metadata)
    elif task_type == "qa":
        return _parse_qa(data, metadata)
    elif task_type == "monitor":
        return _parse_monitor(data, metadata)
    else:
        logger.warning(f"Unknown task type: {task_type}")
        return data


def _parse_gap_analysis(data: dict, metadata: dict) -> dict:
    """
    Parse gap analysis response.

    API returns:
        {
            "framework": "GDPR",
            "assessment_date": "2026-02-27",
            "overall_score": 72.5,
            "status_summary": { "compliant": 8, ... },
            "requirements": [
                {
                    "requirement_id": "GDPR-Art13-2a",
                    "description": "...",
                    "article_reference": "Art. 13(2)(a)",
                    "status": "NON_COMPLIANT",
                    "evidence": "...",
                    "gap_description": "...",
                    "remediation_effort": "2-3 days",
                    "priority": "P1",
                    "notes": "..."
                }
            ],
            "top_recommendations": [...],
            "confidence_score": 0.85
        }

    Metrics engine expects:
        {
            "requirements": [
                { "article": "Art. 13(2)(a)", "status": "NON_COMPLIANT", "description": "...", "severity": "..." }
            ],
            "confidence_score": 0.85
        }
    """
    requirements = data.get("requirements", [])
    normalized = []

    for req in requirements:
        if not isinstance(req, dict):
            continue

        status = str(req.get("status", "")).upper().replace("-", "_")

        # Extract article reference — try multiple field names
        article = (
            req.get("article_reference")
            or req.get("article")
            or req.get("requirement_id")
            or "unknown"
        )

        # Normalize article format: "GDPR-Art13-2a" → "Art. 13(2)(a)" (keep as-is if already proper)
        article = _normalize_article_ref(article)

        # Map priority to severity
        severity = _priority_to_severity(req.get("priority", "P2"))

        normalized.append(
            {
                "article": article,
                "status": status,
                "description": req.get("gap_description") or req.get("description", ""),
                "severity": severity,
                "evidence": req.get("evidence", ""),
                "remediation_effort": req.get("remediation_effort", ""),
            }
        )

    return {
        "requirements": normalized,
        "compliance_score": data.get("overall_score", 0),
        "confidence_score": data.get("confidence_score", 0.0),
        "framework": data.get("framework", ""),
        "assessment_date": data.get("assessment_date", ""),
        "status_summary": data.get("status_summary", {}),
        "top_recommendations": data.get("top_recommendations", []),
        "requires_expert_review": data.get("requires_expert_review", False),
    }


def _parse_qa(data: dict, metadata: dict) -> dict:
    """
    Parse Q&A response.

    API returns:
        {
            "answer": "...",
            "citations": [
                { "framework": "GDPR", "reference": "Art. 13(2)(a)", "quote_snippet": "..." }
            ],
            "confidence_score": 0.9,
            "requires_expert_review": false,
            "related_frameworks": ["GDPR"],
            "caveats": [...]
        }

    Metrics engine expects:
        {
            "citations": [
                { "article": "Art. 13(2)(a)", "text": "..." }
            ],
            "confidence_score": 0.9
        }
    """
    citations = data.get("citations", [])
    normalized = []

    for cit in citations:
        if not isinstance(cit, dict):
            continue

        article = (
            cit.get("reference") or cit.get("article") or cit.get("article_reference") or "unknown"
        )
        article = _normalize_article_ref(article)

        normalized.append(
            {
                "article": article,
                "text": cit.get("quote_snippet", cit.get("text", "")),
                "framework": cit.get("framework", ""),
            }
        )

    return {
        "answer": data.get("answer", ""),
        "citations": normalized,
        "confidence_score": data.get("confidence_score", 0.0),
        "requires_expert_review": data.get("requires_expert_review", False),
        "related_frameworks": data.get("related_frameworks", []),
        "caveats": data.get("caveats", []),
    }


def _parse_monitor(data: dict, metadata: dict) -> dict:
    """
    Parse monitor (regulatory change) response.

    API returns:
        {
            "applicability": "YES",
            "urgency": "HIGH",
            "impact_summary": "...",
            "required_actions": [
                "Action 1 with effort (5 days)"
            ],
            "deadline": "...",
            "cross_framework_impacts": [...],
            "confidence_score": 0.8,
            "citations": ["GDPR, Art. 13(2)(a) — ..."]
        }

    Metrics engine expects:
        {
            "required_actions": [
                { "article": "Art. ...", "description": "..." }
            ],
            "confidence_score": 0.8
        }
    """
    raw_actions = data.get("required_actions", [])
    raw_citations = data.get("citations", [])
    normalized = []

    # Try to extract articles from citations and match with actions
    citation_articles = _extract_articles_from_citations(raw_citations)

    for i, action in enumerate(raw_actions):
        if isinstance(action, dict):
            article = (
                action.get("article")
                or action.get("regulation")
                or (citation_articles[i] if i < len(citation_articles) else "unknown")
            )
            description = action.get("description", action.get("action", ""))
        elif isinstance(action, str):
            # Plain string action — try to extract article reference
            article = _extract_article_from_text(action) or (
                citation_articles[i] if i < len(citation_articles) else "unknown"
            )
            description = action
        else:
            continue

        article = _normalize_article_ref(article)
        normalized.append(
            {
                "article": article,
                "description": description,
                "urgency": data.get("urgency", "medium"),
            }
        )

    return {
        "required_actions": normalized,
        "applicability": data.get("applicability", ""),
        "urgency": data.get("urgency", ""),
        "impact_summary": data.get("impact_summary", ""),
        "deadline": data.get("deadline", ""),
        "cross_framework_impacts": data.get("cross_framework_impacts", []),
        "confidence_score": data.get("confidence_score", 0.0),
        "requires_expert_review": data.get("requires_expert_review", False),
    }


# ─── Helper Functions ─────────────────────────────────────────────


def _normalize_article_ref(ref: str) -> str:
    """
    Normalize article reference to a consistent format.
    Keeps 'Art. X(Y)(Z)' format if already present.
    Converts 'GDPR-Art13-2a' to 'Art. 13(2)(a)'.
    """
    if not ref or ref == "unknown":
        return ref

    # Already in good format: "Art. 13(2)(a)"
    if re.match(r"Art\.\s*\d+", ref):
        return ref

    # Already in good format: "ESRS E1-6"
    if re.match(r"ESRS\s+\w+", ref, re.IGNORECASE):
        return ref

    # Try to extract from requirement_id format: "GDPR-Art13-2a"
    m = re.match(r"(?:\w+-)?Art\.?(\d+)(?:[-_](\d+))?(?:[-_](\w+))?", ref, re.IGNORECASE)
    if m:
        article = f"Art. {m.group(1)}"
        if m.group(2):
            article += f"({m.group(2)})"
        if m.group(3):
            article += f"({m.group(3)})"
        return article

    return ref


def _priority_to_severity(priority: str) -> str:
    """Map API priority to validation severity."""
    mapping = {
        "P1": "critical",
        "P2": "major",
        "P3": "minor",
        "P4": "observation",
    }
    return mapping.get(priority.upper() if priority else "P2", "major")


def _extract_article_from_text(text: str) -> str | None:
    """Extract first article reference from free text."""
    patterns = [
        r"Art\.?\s*(\d+(?:\(\d+\)(?:\([a-z]\))?)?)",
        r"Article\s+(\d+(?:\(\d+\)(?:\([a-z]\))?)?)",
        r"ESRS\s+(\w+-?\d+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return f"Art. {m.group(1)}" if "ESRS" not in pattern else f"ESRS {m.group(1)}"
    return None


def _extract_articles_from_citations(citations: list) -> list[str]:
    """Extract article references from monitor citation strings."""
    articles = []
    for cit in citations:
        if isinstance(cit, str):
            article = _extract_article_from_text(cit)
            if article:
                articles.append(article)
        elif isinstance(cit, dict):
            articles.append(cit.get("reference", cit.get("article", "unknown")))
    return articles
