"""Tests for src/agents/workflow_presets_loader.py.

The loader parses ``workflow_presets.yaml`` at import time and caches the
result in module-level globals (``_PRESETS`` / ``_UI_GROUPING``). To keep the
real shipped presets out of the way of the validation/error tests, the
``restore_module_state`` fixture snapshots the globals + the YAML path before
each test and restores them afterwards, so swapping the path and calling
``reload()`` never leaks into other tests.

No external deps are touched: PyYAML is the only import, file IO goes through a
tmp_path-backed YAML, and structlog logging is a no-op for assertions.
"""

from __future__ import annotations

import textwrap

import pytest

from src.agents import workflow_presets_loader as loader
from src.agents.workflow_presets_loader import WorkflowPreset

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def restore_module_state():
    """Snapshot + restore module-level cache and YAML path around a test."""
    saved_presets = dict(loader._PRESETS)
    saved_grouping = dict(loader._UI_GROUPING)
    saved_path = loader.PRESETS_YAML_PATH
    try:
        yield
    finally:
        loader._PRESETS = saved_presets
        loader._UI_GROUPING = saved_grouping
        loader.PRESETS_YAML_PATH = saved_path


def _write_yaml(tmp_path, body: str):
    p = tmp_path / "workflow_presets.yaml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def _raw_preset(**overrides) -> dict:
    """A minimal valid raw preset dict; override fields per-test."""
    base = {
        "id": "test-preset",
        "name": "Test Preset",
        "icp": "H1",
        "framework": "CSRD",
        "description": "  A description with surrounding whitespace.  ",
        "system_prompt_addendum": "  Do the thing.  ",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# _validate_preset: happy path + field coercion/defaults
# --------------------------------------------------------------------------- #


class TestValidatePreset:
    def test_valid_minimal_preset_returns_dataclass(self):
        preset = loader._validate_preset(_raw_preset())
        assert isinstance(preset, WorkflowPreset)
        assert preset.id == "test-preset"
        assert preset.icp == "H1"
        assert preset.framework == "CSRD"

    def test_description_and_addendum_are_stripped(self):
        preset = loader._validate_preset(_raw_preset())
        assert preset.description == "A description with surrounding whitespace."
        assert preset.system_prompt_addendum == "Do the thing."

    def test_defaults_applied_for_optional_fields(self):
        preset = loader._validate_preset(_raw_preset())
        assert preset.suggested_inputs == []
        assert preset.references_required == []
        assert preset.output_format == "free_text"
        assert preset.max_questions == 5

    def test_optional_fields_passed_through(self):
        preset = loader._validate_preset(
            _raw_preset(
                suggested_inputs=["a", "b"],
                references_required=["EUR-Lex"],
                output_format="structured_json",
                max_questions=3,
            )
        )
        assert preset.suggested_inputs == ["a", "b"]
        assert preset.references_required == ["EUR-Lex"]
        assert preset.output_format == "structured_json"
        assert preset.max_questions == 3

    def test_max_questions_coerced_to_int(self):
        preset = loader._validate_preset(_raw_preset(max_questions="7"))
        assert preset.max_questions == 7
        assert isinstance(preset.max_questions, int)

    def test_suggested_inputs_copied_not_referenced(self):
        raw = _raw_preset(suggested_inputs=["x"])
        preset = loader._validate_preset(raw)
        # list() makes a fresh list; mutating the source must not leak through.
        raw["suggested_inputs"].append("y")
        assert preset.suggested_inputs == ["x"]


# --------------------------------------------------------------------------- #
# _validate_preset: rejection cases (returns None)
# --------------------------------------------------------------------------- #


class TestValidatePresetRejections:
    @pytest.mark.parametrize(
        "missing_field",
        ["id", "name", "icp", "framework", "description", "system_prompt_addendum"],
    )
    def test_missing_required_field_returns_none(self, missing_field):
        raw = _raw_preset()
        del raw[missing_field]
        assert loader._validate_preset(raw) is None

    def test_invalid_icp_returns_none(self):
        assert loader._validate_preset(_raw_preset(icp="H9")) is None

    def test_invalid_framework_returns_none(self):
        assert loader._validate_preset(_raw_preset(framework="NOT_A_FRAMEWORK")) is None

    def test_invalid_output_format_returns_none(self):
        assert loader._validate_preset(_raw_preset(output_format="csv_dump")) is None

    def test_all_valid_frameworks_accepted(self):
        for fw in loader._VALID_FRAMEWORKS:
            preset = loader._validate_preset(_raw_preset(framework=fw))
            assert preset is not None
            assert preset.framework == fw

    def test_all_valid_output_formats_accepted(self):
        for fmt in loader._VALID_OUTPUT_FORMATS:
            preset = loader._validate_preset(_raw_preset(output_format=fmt))
            assert preset is not None
            assert preset.output_format == fmt


# --------------------------------------------------------------------------- #
# _load_yaml + reload via tmp_path-backed file
# --------------------------------------------------------------------------- #


class TestLoadYaml:
    def test_load_existing_yaml(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(
            tmp_path,
            """
            version: 2.5
            presets: []
            ui_grouping:
              H1:
                label: "Officer"
            """,
        )
        data = loader._load_yaml()
        assert data["version"] == 2.5
        assert data["presets"] == []
        assert data["ui_grouping"]["H1"]["label"] == "Officer"

    def test_missing_file_returns_empty_fallback(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = tmp_path / "does_not_exist.yaml"
        data = loader._load_yaml()
        assert data == {"presets": [], "version": "0", "ui_grouping": {}}

    def test_empty_yaml_file_returns_empty_dict(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(tmp_path, "")
        # safe_load("") -> None -> `or {}` -> {}
        assert loader._load_yaml() == {}

    def test_malformed_yaml_returns_fallback(self, tmp_path, restore_module_state):
        # Unbalanced brackets => yaml.YAMLError, caught and turned into fallback.
        loader.PRESETS_YAML_PATH = _write_yaml(tmp_path, "presets: [unclosed\n")
        data = loader._load_yaml()
        assert data == {"presets": [], "version": "0", "ui_grouping": {}}

    def test_load_yaml_when_pyyaml_missing(self, monkeypatch, restore_module_state):
        # Simulate ImportError on `import yaml` inside _load_yaml.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yaml":
                raise ImportError("no pyyaml")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        data = loader._load_yaml()
        assert data == {"presets": [], "version": "0", "ui_grouping": {}}


# --------------------------------------------------------------------------- #
# _build_index + reload behaviour
# --------------------------------------------------------------------------- #


class TestBuildIndexAndReload:
    def test_reload_swaps_in_new_presets(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(
            tmp_path,
            """
            version: 9
            presets:
              - id: only-one
                name: Only One
                icp: H2
                framework: DORA
                description: desc
                system_prompt_addendum: addendum
            ui_grouping:
              H2:
                label: "Legal"
            """,
        )
        loader.reload()
        assert list(loader._PRESETS.keys()) == ["only-one"]
        assert loader.get_preset("only-one").framework == "DORA"
        assert loader.ui_grouping() == {"H2": {"label": "Legal"}}

    def test_build_index_skips_invalid_presets(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(
            tmp_path,
            """
            presets:
              - id: good
                name: Good
                icp: H1
                framework: CSRD
                description: d
                system_prompt_addendum: a
              - id: bad-icp
                name: Bad
                icp: H7
                framework: CSRD
                description: d
                system_prompt_addendum: a
              - id: missing-name
                icp: H1
                framework: CSRD
                description: d
                system_prompt_addendum: a
            """,
        )
        index = loader._build_index()
        assert set(index.keys()) == {"good"}

    def test_build_index_dedupes_repeated_ids_keeping_first(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(
            tmp_path,
            """
            presets:
              - id: dup
                name: First
                icp: H1
                framework: CSRD
                description: d
                system_prompt_addendum: a
              - id: dup
                name: Second
                icp: H2
                framework: DORA
                description: d
                system_prompt_addendum: a
            """,
        )
        index = loader._build_index()
        assert set(index.keys()) == {"dup"}
        # First occurrence wins; the duplicate is dropped.
        assert index["dup"].name == "First"
        assert index["dup"].icp == "H1"

    def test_build_index_empty_when_no_presets_key(self, tmp_path, restore_module_state):
        loader.PRESETS_YAML_PATH = _write_yaml(tmp_path, "version: 1\n")
        assert loader._build_index() == {}


# --------------------------------------------------------------------------- #
# Public getters against a controlled fixture set
# --------------------------------------------------------------------------- #


@pytest.fixture
def controlled_presets(restore_module_state):
    """Replace the cache with a small deterministic set of presets."""
    presets = {
        "h1-csrd": WorkflowPreset(
            id="h1-csrd",
            name="H1 CSRD",
            icp="H1",
            framework="CSRD",
            description="d",
            system_prompt_addendum="a",
        ),
        "h1-gdpr": WorkflowPreset(
            id="h1-gdpr",
            name="H1 GDPR",
            icp="H1",
            framework="GDPR",
            description="d",
            system_prompt_addendum="a",
        ),
        "h3-dora": WorkflowPreset(
            id="h3-dora",
            name="H3 DORA",
            icp="H3",
            framework="DORA",
            description="d",
            system_prompt_addendum="a",
        ),
        "h3-dora-b": WorkflowPreset(
            id="h3-dora-b",
            name="H3 DORA B",
            icp="H3",
            framework="DORA",
            description="d",
            system_prompt_addendum="a",
        ),
    }
    loader._PRESETS = presets
    return presets


class TestPublicGetters:
    def test_list_presets_sorted_by_icp_then_id(self, controlled_presets):
        ids = [p.id for p in loader.list_presets()]
        assert ids == ["h1-csrd", "h1-gdpr", "h3-dora", "h3-dora-b"]

    def test_get_preset_hit(self, controlled_presets):
        p = loader.get_preset("h3-dora")
        assert p is not None
        assert p.framework == "DORA"

    def test_get_preset_unknown_returns_none(self, controlled_presets):
        assert loader.get_preset("nope-not-here") is None

    def test_presets_for_icp_filters_and_sorts(self, controlled_presets):
        ids = [p.id for p in loader.presets_for_icp("H3")]
        assert ids == ["h3-dora", "h3-dora-b"]

    def test_presets_for_icp_invalid_returns_empty(self, controlled_presets):
        assert loader.presets_for_icp("H9") == []

    def test_presets_for_icp_valid_but_unused_returns_empty(self, controlled_presets):
        # H2 is a valid ICP but has no presets in the controlled set.
        assert loader.presets_for_icp("H2") == []

    def test_presets_for_framework_filters(self, controlled_presets):
        ids = [p.id for p in loader.presets_for_framework("DORA")]
        assert ids == ["h3-dora", "h3-dora-b"]

    def test_presets_for_framework_invalid_returns_empty(self, controlled_presets):
        assert loader.presets_for_framework("BOGUS") == []

    def test_presets_for_framework_valid_but_unused_returns_empty(self, controlled_presets):
        # MULTI is valid but absent from the controlled set.
        assert loader.presets_for_framework("MULTI") == []

    def test_stats_counts_by_icp_and_framework(self, controlled_presets):
        s = loader.stats()
        assert s["total"] == 4
        assert s["by_icp"] == {"H1": 2, "H3": 2}
        assert s["by_framework"] == {"CSRD": 1, "GDPR": 1, "DORA": 2}

    def test_ui_grouping_returns_copy(self, controlled_presets):
        loader._UI_GROUPING = {"H1": {"label": "Officer"}}
        grouping = loader.ui_grouping()
        grouping["H1"]["mutated"] = True
        # The shallow copy means the top-level dict is fresh, but mutating a
        # nested dict still hits the original; assert the documented shallow
        # behaviour: a new top-level key does not leak back.
        grouping["NEW"] = {}
        assert "NEW" not in loader._UI_GROUPING


# --------------------------------------------------------------------------- #
# Integration with the real shipped YAML
# --------------------------------------------------------------------------- #


class TestRealShippedPresets:
    def test_real_yaml_loads_eight_presets(self):
        # The shipped workflow_presets.yaml defines 8 presets across H1/H2/H3.
        loader.reload()
        s = loader.stats()
        assert s["total"] == 8
        assert s["by_icp"] == {"H1": 3, "H2": 2, "H3": 3}

    def test_real_known_preset_present_and_typed(self):
        loader.reload()
        p = loader.get_preset("dora-incident-classification")
        assert p is not None
        assert p.icp == "H3"
        assert p.framework == "DORA"
        assert p.output_format == "structured_json"
        assert "EUR-Lex" in p.references_required

    def test_real_ui_grouping_has_all_icps(self):
        loader.reload()
        grouping = loader.ui_grouping()
        assert set(grouping.keys()) == {"H1", "H2", "H3"}
        assert grouping["H1"]["label"]
