"""Local LLM router: framework classification, complexity scoring, NER.

Routes queries through the local Qwen 4B model for fast (~50ms) pre-processing
before expensive remote LLM calls. Falls back to keyword-based detection when
the local LLM is unavailable.

Output: RouterResult with frameworks, complexity tier, entities, and source.
"""

import logging
from dataclasses import dataclass, field

from src.agents.local_llm import acall_local_llm
from src.agents.nodes import detect_frameworks_in_query

logger = logging.getLogger(__name__)

_VALID_FRAMEWORKS = {"CSRD", "CSDDD", "AI_ACT", "DORA", "NIS2", "TAXONOMY", "GDPR", "CRA"}
_VALID_COMPLEXITY = {"simple", "medium", "complex"}

_ROUTER_SYSTEM_PROMPT = """\
You are a regulatory intelligence router. Analyze the user query and return JSON only.

Available EU regulatory frameworks:
- CSRD: Corporate Sustainability Reporting Directive
- CSDDD: Corporate Sustainability Due Diligence Directive
- AI_ACT: EU Artificial Intelligence Act
- DORA: Digital Operational Resilience Act
- NIS2: Network and Information Security Directive 2
- TAXONOMY: EU Taxonomy Regulation
- GDPR: General Data Protection Regulation
- CRA: Cyber Resilience Act (products with digital elements)

Complexity tiers:
- "simple": factual lookup, single framework, well-known article reference
- "medium": requires cross-referencing, company-specific analysis, or 2 frameworks
- "complex": multi-framework analysis, novel legal interpretation, gap analysis

Return ONLY valid JSON (no markdown, no explanation):
{
  "frameworks": ["CSRD"],
  "complexity": "simple",
  "entities": {
    "article_refs": ["Art. 19a"],
    "deadlines": ["2025-01-01"],
    "thresholds": ["500 employees"]
  }
}

Rules:
- frameworks: 1 or more from the list above. If unclear, include all likely matches.
- complexity: exactly one of simple/medium/complex.
- entities: extract article references, deadlines, numeric thresholds. Empty arrays if none found.
"""


@dataclass
class RouterResult:
    """Result from the local router."""

    frameworks: list[str] = field(default_factory=list)
    complexity: str = "medium"
    entities: dict = field(
        default_factory=lambda: {
            "article_refs": [],
            "deadlines": [],
            "thresholds": [],
        }
    )
    source: str = "keyword_fallback"


def _keyword_fallback(query: str) -> RouterResult:
    """Fallback to keyword-based framework detection."""
    frameworks = detect_frameworks_in_query(query)
    return RouterResult(
        frameworks=frameworks if frameworks else list(_VALID_FRAMEWORKS),
        complexity="medium",
        source="keyword_fallback",
    )


def _validate_and_sanitize(raw: dict) -> RouterResult:
    """Validate LLM output and sanitize to known values."""
    # Frameworks
    raw_frameworks = raw.get("frameworks", [])
    if not isinstance(raw_frameworks, list):
        raw_frameworks = []
    frameworks = [f for f in raw_frameworks if f in _VALID_FRAMEWORKS]
    if not frameworks:
        frameworks = list(_VALID_FRAMEWORKS)

    # Complexity
    complexity = raw.get("complexity", "medium")
    if complexity not in _VALID_COMPLEXITY:
        complexity = "medium"

    # Entities
    raw_entities = raw.get("entities", {})
    if not isinstance(raw_entities, dict):
        raw_entities = {}
    entities = {
        "article_refs": _safe_str_list(raw_entities.get("article_refs", [])),
        "deadlines": _safe_str_list(raw_entities.get("deadlines", [])),
        "thresholds": _safe_str_list(raw_entities.get("thresholds", [])),
    }

    return RouterResult(
        frameworks=frameworks,
        complexity=complexity,
        entities=entities,
        source="local_llm",
    )


def _safe_str_list(val) -> list[str]:
    """Ensure value is a list of strings."""
    if not isinstance(val, list):
        return []
    return [str(v) for v in val if v is not None]


async def aroute_query(query: str, task_type: str = "qa") -> RouterResult:
    """Route a query through the local LLM or keyword fallback.

    Always returns a valid RouterResult. Never raises.

    For gap_analysis and monitor task types, complexity is forced to
    at least "medium" since these always require deep analysis.
    """
    result = await _try_local_llm(query)
    if result is None:
        result = _keyword_fallback(query)

    # Enforce minimum complexity for analysis-heavy tasks
    if task_type in ("gap_analysis", "monitor") and result.complexity == "simple":
        result.complexity = "medium"

    return result


async def _try_local_llm(query: str) -> RouterResult | None:
    """Attempt local LLM routing. Returns None if unavailable or error."""
    raw = await acall_local_llm(_ROUTER_SYSTEM_PROMPT, query)
    if raw is None:
        return None
    try:
        return _validate_and_sanitize(raw)
    except Exception as e:
        logger.warning("router_validation_failed: %s", e)
        return None
