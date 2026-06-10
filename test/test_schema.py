# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Tests for nav2_params.json schema loading and correctness."""

import json
import os
import sys
from pathlib import Path

import pytest

# Allow importing from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.types.params import Nav2ParamDef, ParamRange, load_schema

SCHEMA_PATH = SRC_ROOT / "nav2_config" / "schema" / "nav2_params.json"
PLUGINS_PATH = SRC_ROOT / "nav2_config" / "schema" / "plugins.json"

VALID_TYPES = {"double", "int", "bool", "string", "string_array", "double_array", "int_array"}
KNOWN_NODES = {
    "controller_server",
    "planner_server",
    "amcl",
    "bt_navigator",
    "local_costmap",
    "global_costmap",
    "smoother_server",
    "velocity_smoother",
    "behavior_server",
    "waypoint_follower",
    "map_server",
    "map_saver",
    "collision_monitor",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def raw_params() -> list[dict]:
    """Load raw JSON before parsing so we can test the JSON itself."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def parsed_params() -> list[Nav2ParamDef]:
    """Load and parse the schema via the public API."""
    # Override ament lookup to use the source tree during testing
    os.environ.setdefault("_NAV2_CONFIG_TEST", "1")
    return load_schema()


@pytest.fixture(scope="module")
def raw_plugins() -> dict:
    with open(PLUGINS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Schema file structure
# ---------------------------------------------------------------------------


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"nav2_params.json not found at {SCHEMA_PATH}"


def test_schema_is_valid_json(raw_params):
    assert isinstance(raw_params, list), "nav2_params.json must be a JSON array"


def test_schema_minimum_param_count(raw_params):
    count = len(raw_params)
    assert count >= 150, f"Expected >= 150 parameters, found {count}"


def test_plugins_file_exists():
    assert PLUGINS_PATH.exists(), f"plugins.json not found at {PLUGINS_PATH}"


# ---------------------------------------------------------------------------
# Per-entry required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_required_fields_present(entry: dict):
    required = {"node", "param", "type", "default", "description"}
    missing = required - entry.keys()
    assert not missing, f"Missing fields {missing} in entry {entry.get('param')}"


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_type_is_valid(entry: dict):
    assert entry["type"] in VALID_TYPES, (
        f"Param '{entry['param']}' has unknown type '{entry['type']}'. "
        f"Valid types: {VALID_TYPES}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_node_is_known(entry: dict):
    assert entry["node"] in KNOWN_NODES, (
        f"Param '{entry['param']}' references unknown node '{entry['node']}'. "
        f"Known nodes: {KNOWN_NODES}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_description_is_non_empty(entry: dict):
    assert entry.get("description", "").strip(), (
        f"Param '{entry['param']}' has an empty description"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_hot_reload_is_bool(entry: dict):
    assert "hot_reload" in entry, f"Param '{entry['param']}' missing hot_reload field"
    assert isinstance(entry["hot_reload"], bool), (
        f"Param '{entry['param']}' hot_reload must be bool, got {type(entry['hot_reload'])}"
    )


# ---------------------------------------------------------------------------
# Default value type matching
# ---------------------------------------------------------------------------


TYPE_PYTHON_MAP = {
    "double": float,
    "int": int,
    "bool": bool,
    "string": str,
    "string_array": list,
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_default_type_matches_declared_type(entry: dict):
    declared = entry["type"]
    default = entry["default"]
    expected_py_type = TYPE_PYTHON_MAP.get(declared)

    if expected_py_type is None:
        return  # Unknown type tested elsewhere

    # JSON numbers: "double" may have an int default (e.g., 20 for 20.0) — accept both
    if declared == "double":
        assert isinstance(default, (int, float)), (
            f"Param '{entry['param']}' declared double but default is {type(default)}"
        )
    else:
        assert isinstance(default, expected_py_type), (
            f"Param '{entry['param']}' declared {declared} but default is {type(default).__name__}"
        )


# ---------------------------------------------------------------------------
# Range consistency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_min_less_than_max(entry: dict):
    raw_range = entry.get("range")
    if not raw_range:
        return
    mn = raw_range.get("min")
    mx = raw_range.get("max")
    if mn is not None and mx is not None:
        assert mn < mx, (
            f"Param '{entry['param']}' has range min ({mn}) >= max ({mx})"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_default_within_range(entry: dict):
    """Default values for numeric params should be within their declared range."""
    raw_range = entry.get("range")
    if not raw_range:
        return
    if entry["type"] not in ("double", "int"):
        return
    mn = raw_range.get("min")
    mx = raw_range.get("max")
    default = entry["default"]
    if mn is not None:
        assert default >= mn, (
            f"Param '{entry['param']}' default {default} < range min {mn}"
        )
    if mx is not None:
        assert default <= mx, (
            f"Param '{entry['param']}' default {default} > range max {mx}"
        )


# ---------------------------------------------------------------------------
# Parsed dataclass tests
# ---------------------------------------------------------------------------


def test_load_schema_returns_list(parsed_params):
    assert isinstance(parsed_params, list)
    assert len(parsed_params) > 0


def test_load_schema_returns_nav2paramdef(parsed_params):
    for p in parsed_params:
        assert isinstance(p, Nav2ParamDef), f"Expected Nav2ParamDef, got {type(p)}"


def test_parsed_param_range_type(parsed_params):
    for p in parsed_params:
        if p.range is not None:
            assert isinstance(p.range, ParamRange), (
                f"Param '{p.param}' range should be ParamRange, got {type(p.range)}"
            )


def test_parsed_param_tags_are_list(parsed_params):
    for p in parsed_params:
        assert isinstance(p.tags, list), f"Param '{p.param}' tags must be a list"


def test_all_nodes_covered(parsed_params):
    """All 11 canonical Nav2 nodes must have at least one parameter."""
    covered = {p.node for p in parsed_params}
    missing = KNOWN_NODES - covered
    assert not missing, f"These Nav2 nodes have no parameters in the schema: {missing}"


def test_node_param_uniqueness(parsed_params):
    """Each (node, param) pair must be unique."""
    seen: set[tuple[str, str]] = set()
    for p in parsed_params:
        key = (p.node, p.param)
        assert key not in seen, f"Duplicate (node, param): {key}"
        seen.add(key)


# ---------------------------------------------------------------------------
# Plugins JSON structure
# ---------------------------------------------------------------------------


def test_plugins_json_top_level_keys(raw_plugins):
    expected_keys = {"planners", "controllers", "costmap_layers", "recovery_behaviors", "smoothers"}
    assert set(raw_plugins.keys()) == expected_keys, (
        f"plugins.json top-level keys mismatch. Got: {set(raw_plugins.keys())}"
    )


def test_plugins_planner_count(raw_plugins):
    assert len(raw_plugins["planners"]) >= 4, "Expected at least 4 global planners"


def test_plugins_controller_count(raw_plugins):
    assert len(raw_plugins["controllers"]) >= 3, "Expected at least 3 controllers"


def test_plugins_layer_count(raw_plugins):
    assert len(raw_plugins["costmap_layers"]) >= 4, "Expected at least 4 costmap layers"


@pytest.mark.parametrize("category", ["planners", "controllers", "costmap_layers", "recovery_behaviors", "smoothers"])
def test_plugin_entries_have_required_fields(raw_plugins, category):
    required = {"name", "plugin_class", "category", "description", "when_to_use"}
    for plugin in raw_plugins[category]:
        missing = required - plugin.keys()
        assert not missing, (
            f"Plugin '{plugin.get('name', '?')}' in {category} missing fields: {missing}"
        )


def test_plugin_classes_are_non_empty(raw_plugins):
    for category, plugins in raw_plugins.items():
        for plugin in plugins:
            assert plugin["plugin_class"].strip(), (
                f"Plugin '{plugin.get('name')}' has empty plugin_class"
            )
