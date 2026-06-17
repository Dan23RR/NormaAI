"""Loader for workflow_presets.yaml - pattern inspired by Mike OSS workflows.

Loads the YAML on import, validates schema, exposes typed getters.
Cached at module level (mutate `_PRESETS` only in tests).

Usage:
    from src.agents.workflow_presets_loader import (
        list_presets, get_preset, presets_for_icp, presets_for_framework
    )

    h3_dora = presets_for_icp("H3")
    incident = get_preset("dora-incident-classification")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()


PRESETS_YAML_PATH = Path(__file__).parent / "workflow_presets.yaml"


@dataclass
class WorkflowPreset:
    """One workflow preset (e.g. 'DORA self-assessment for small entity')."""

    id: str
    name: str
    icp: str  # "H1" | "H2" | "H3"
    framework: str  # "CSRD" | "DORA" | ... | "MULTI"
    description: str
    system_prompt_addendum: str
    suggested_inputs: list[str] = field(default_factory=list)
    output_format: str = "free_text"
    max_questions: int = 5
    references_required: list[str] = field(default_factory=list)


_VALID_ICPS = {"H1", "H2", "H3"}
_VALID_FRAMEWORKS = {
    "CSRD",
    "CSDDD",
    "AI_Act",
    "DORA",
    "NIS2",
    "EU_Taxonomy",
    "GDPR",
    "CRA",
    "MULTI",
}
_VALID_OUTPUT_FORMATS = {
    "free_text",
    "structured_json",
    "gap_analysis",
    "self_assessment",
}


def _load_yaml() -> dict:
    """Read the YAML file. PyYAML is the dependency."""
    try:
        import yaml  # type: ignore
    except ImportError:
        logger.error("pyyaml_not_installed", remediation="poetry add pyyaml")
        return {"presets": [], "version": "0", "ui_grouping": {}}

    if not PRESETS_YAML_PATH.exists():
        logger.warning("workflow_presets_yaml_missing", path=str(PRESETS_YAML_PATH))
        return {"presets": [], "version": "0", "ui_grouping": {}}

    try:
        with PRESETS_YAML_PATH.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except yaml.YAMLError as e:
        logger.error("workflow_presets_yaml_parse_failed", error=str(e))
        return {"presets": [], "version": "0", "ui_grouping": {}}

    return data


def _validate_preset(raw: dict) -> WorkflowPreset | None:
    """Validate a raw preset dict and return a WorkflowPreset, or None on error."""
    required = ("id", "name", "icp", "framework", "description", "system_prompt_addendum")
    missing = [k for k in required if k not in raw]
    if missing:
        logger.warning("preset_missing_fields", id=raw.get("id"), missing=missing)
        return None

    if raw["icp"] not in _VALID_ICPS:
        logger.warning("preset_invalid_icp", id=raw["id"], icp=raw["icp"])
        return None

    if raw["framework"] not in _VALID_FRAMEWORKS:
        logger.warning("preset_invalid_framework", id=raw["id"], framework=raw["framework"])
        return None

    output_format = raw.get("output_format", "free_text")
    if output_format not in _VALID_OUTPUT_FORMATS:
        logger.warning("preset_invalid_output_format", id=raw["id"], output_format=output_format)
        return None

    return WorkflowPreset(
        id=raw["id"],
        name=raw["name"],
        icp=raw["icp"],
        framework=raw["framework"],
        description=raw["description"].strip(),
        system_prompt_addendum=raw["system_prompt_addendum"].strip(),
        suggested_inputs=list(raw.get("suggested_inputs", [])),
        output_format=output_format,
        max_questions=int(raw.get("max_questions", 5)),
        references_required=list(raw.get("references_required", [])),
    )


def _build_index() -> dict[str, WorkflowPreset]:
    """Parse YAML, validate, return id→preset dict."""
    data = _load_yaml()
    index: dict[str, WorkflowPreset] = {}
    for raw in data.get("presets", []):
        preset = _validate_preset(raw)
        if preset is None:
            continue
        if preset.id in index:
            logger.warning("preset_duplicate_id", id=preset.id)
            continue
        index[preset.id] = preset
    logger.info("workflow_presets_loaded", count=len(index), version=data.get("version"))
    return index


# Module-level cache. Reset only via reload() in tests.
_PRESETS: dict[str, WorkflowPreset] = _build_index()
_UI_GROUPING: dict[str, dict] = _load_yaml().get("ui_grouping", {})


def reload() -> None:
    """Re-parse the YAML (useful in tests + dev with hot reload)."""
    global _PRESETS, _UI_GROUPING
    _PRESETS = _build_index()
    _UI_GROUPING = _load_yaml().get("ui_grouping", {})


def list_presets() -> list[WorkflowPreset]:
    """All presets, sorted by ICP then id."""
    return sorted(_PRESETS.values(), key=lambda p: (p.icp, p.id))


def get_preset(preset_id: str) -> WorkflowPreset | None:
    """Look up a preset by id. Returns None if not found."""
    return _PRESETS.get(preset_id)


def presets_for_icp(icp: str) -> list[WorkflowPreset]:
    """All presets for a given ICP (H1/H2/H3), sorted by id."""
    if icp not in _VALID_ICPS:
        return []
    return sorted(
        (p for p in _PRESETS.values() if p.icp == icp),
        key=lambda p: p.id,
    )


def presets_for_framework(framework: str) -> list[WorkflowPreset]:
    """All presets that target a specific framework (or MULTI)."""
    if framework not in _VALID_FRAMEWORKS:
        return []
    return sorted(
        (p for p in _PRESETS.values() if p.framework == framework),
        key=lambda p: (p.icp, p.id),
    )


def ui_grouping() -> dict[str, dict]:
    """UI metadata for grouping presets (label, color, icon per ICP)."""
    return dict(_UI_GROUPING)


def stats() -> dict:
    """Quick stats for telemetry / health endpoint."""
    by_icp: dict[str, int] = {}
    by_framework: dict[str, int] = {}
    for p in _PRESETS.values():
        by_icp[p.icp] = by_icp.get(p.icp, 0) + 1
        by_framework[p.framework] = by_framework.get(p.framework, 0) + 1
    return {
        "total": len(_PRESETS),
        "by_icp": by_icp,
        "by_framework": by_framework,
    }
