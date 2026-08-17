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
    "docking_server",
    "following_server",
    "loopback_simulator",
    "route_server",
    "keepout_costmap_filter_info_server",
    "speed_costmap_filter_info_server",
    "keepout_filter_mask_server",
    "speed_filter_mask_server",
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


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_impact_is_non_empty(entry: dict):
    """Every param must ship a genuine tuning 'impact' note — it is the schema's core value."""
    assert (entry.get("impact") or "").strip(), (
        f"Param '{entry['param']}' has an empty impact note"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_plugin_specific_is_bool(entry: dict):
    assert isinstance(entry.get("plugin_specific"), bool), (
        f"Param '{entry['param']}' plugin_specific must be bool, "
        f"got {type(entry.get('plugin_specific')).__name__}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_plugin_field_consistency(entry: dict):
    """plugin_specific and plugin must agree: both set or both unset."""
    if entry.get("plugin_specific"):
        assert entry.get("plugin"), (
            f"Param '{entry['param']}' is plugin_specific but has no plugin name"
        )
    else:
        assert not entry.get("plugin"), (
            f"Param '{entry['param']}' names plugin '{entry.get('plugin')}' "
            f"but plugin_specific is false"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_unit_is_string(entry: dict):
    """unit must always be a string ('' for unitless params, never null/absent).

    Nav2ParamDef declares ``unit: str``; a JSON null slips through
    ``data.get("unit", "")`` as None and violates that contract downstream
    (e.g. param_row passes ``defn.unit`` on as a string).
    """
    assert "unit" in entry, f"Param '{entry['param']}' missing unit field (use \"\" for unitless)"
    assert isinstance(entry["unit"], str), (
        f"Param '{entry['param']}' unit must be a string, got {type(entry['unit']).__name__}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_are_non_empty_strings(entry: dict):
    tags = entry.get("tags")
    assert isinstance(tags, list), f"Param '{entry['param']}' tags must be a list"
    for tag in tags:
        assert isinstance(tag, str) and tag.strip(), (
            f"Param '{entry['param']}' has an empty or non-string tag: {tag!r}"
        )


# The closed set of follow-up actions understood by the app. Keep in sync with
# the ``post_set_action`` docstring in nav2_config/types/params.py and the
# dispatch in node.py. A typo here (e.g. "restart_stak") would silently be
# treated as "no action", so the value must come from this vocabulary.
VALID_POST_SET_ACTIONS = {
    None,
    "clear_costmaps",
    "load_map",
    "nomotion_update",
    "restart_stack",
    "restart_node",
    "restart_controller",
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_post_set_action_is_valid(entry: dict):
    """post_set_action must be null or one of the known follow-up actions.

    The value is dispatched by string comparison in node.py; an unrecognised
    string is silently ignored, so the change would appear to take effect while
    its required service call / restart notification never fires.
    """
    action = entry.get("post_set_action")
    assert action in VALID_POST_SET_ACTIONS, (
        f"Param '{entry['param']}' has unknown post_set_action {action!r}; "
        f"expected null or one of {sorted(a for a in VALID_POST_SET_ACTIONS if a)}"
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
    "double_array": list,
    "int_array": list,
}

# Expected Python element type for each array param type. bool is deliberately
# excluded from the numeric arrays even though it subclasses int.
ARRAY_ELEMENT_TYPE = {
    "string_array": (str,),
    "double_array": (int, float),
    "int_array": (int,),
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


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_scalar_default_is_not_bool(entry: dict):
    """A scalar ``int``/``double`` default must not be a JSON boolean.

    ``test_default_type_matches_declared_type`` checks ``isinstance(default, int)``
    for numeric scalars, but ``bool`` subclasses ``int`` so a stray ``true``/``false``
    default slips through — the same trap the array test explicitly guards against
    (see ``test_array_default_elements_match_type``). A bool where a number is
    expected would flow into the slider/numeric set-path as ``0``/``1`` and mis-render
    the param, so reject it here to keep the scalar and array checks symmetric.
    """
    if entry["type"] not in ("int", "double"):
        return
    assert not isinstance(entry["default"], bool), (
        f"Param '{entry['param']}' declared {entry['type']} but default is a bool "
        f"({entry['default']!r}); use a numeric literal"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_array_default_elements_match_type(entry: dict):
    """Array-typed params must default to a list whose elements match the scalar type.

    ``bool`` is rejected for the numeric arrays even though it subclasses ``int``,
    so a stray ``true`` in a ``double_array``/``int_array`` default is caught.
    """
    declared = entry["type"]
    elem_types = ARRAY_ELEMENT_TYPE.get(declared)
    if elem_types is None:
        return
    default = entry["default"]
    assert isinstance(default, list), (
        f"Param '{entry['param']}' declared {declared} but default is "
        f"{type(default).__name__}, not a list"
    )
    numeric = declared in ("double_array", "int_array")
    for i, value in enumerate(default):
        if numeric and isinstance(value, bool):
            raise AssertionError(
                f"Param '{entry['param']}' {declared} default has a bool at index {i}"
            )
        assert isinstance(value, elem_types), (
            f"Param '{entry['param']}' {declared} default has "
            f"{type(value).__name__} at index {i}, expected "
            f"{'/'.join(t.__name__ for t in elem_types)}"
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


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_range_bounds_are_numeric(entry: dict):
    """A numeric range's min/max bounds must themselves be numbers.

    ``ParamRange`` feeds these into the slider widget and into the
    ``min < max`` / default-within-range comparisons above. A stray string
    bound (e.g. ``"0.0"``) would raise a ``TypeError`` at comparison time or
    silently mis-clamp the slider, so bounds must be real numbers. ``bool`` is
    rejected even though it subclasses ``int``.
    """
    raw_range = entry.get("range")
    if not raw_range:
        return
    for key in ("min", "max"):
        value = raw_range.get(key)
        if value is None:
            continue
        assert not isinstance(value, bool) and isinstance(value, (int, float)), (
            f"Param '{entry['param']}' range {key} must be a number, "
            f"got {type(value).__name__} ({value!r})"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_valid_and_contain_default(entry: dict):
    """Discrete ``range.options`` must be a non-empty list of non-empty strings,
    and a string default must be one of those options.

    ``param_select.ParamSelect`` populates a QComboBox from ``range.options``;
    if the schema default is absent from that list the widget opens on a value
    the dropdown cannot represent, so the two must stay in sync.
    """
    raw_range = entry.get("range")
    if not raw_range or "options" not in raw_range:
        return
    options = raw_range["options"]
    assert isinstance(options, list) and options, (
        f"Param '{entry['param']}' range.options must be a non-empty list"
    )
    for opt in options:
        assert isinstance(opt, str) and opt.strip(), (
            f"Param '{entry['param']}' has an empty or non-string option: {opt!r}"
        )
    default = entry.get("default")
    if isinstance(default, str):
        assert default in options, (
            f"Param '{entry['param']}' default {default!r} is not among its "
            f"range.options {options}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_only_on_string_type(entry: dict):
    """``range.options`` may only appear on ``string``-typed params.

    ``param_row._make_input_widget`` dispatches on options *before* the numeric
    slider branch: any param carrying ``range.options`` becomes a ``ParamSelect``
    dropdown (param_row.py), and ``ParamSelect`` emits/returns the raw option
    *string* (its ``value_changed`` signal is typed ``str`` and ``get_value``
    returns ``currentText()``). If a ``double``/``int``/``bool`` param were given
    options it would silently render as a string dropdown whose selections the
    numeric/bool set-path cannot faithfully convert, so options must stay on
    string params only.
    """
    raw_range = entry.get("range")
    if not raw_range or raw_range.get("options") is None:
        return
    assert entry["type"] == "string", (
        f"Param '{entry['param']}' is type '{entry['type']}' but defines "
        f"range.options; discrete options are only supported on string params "
        f"(they render as a string ParamSelect dropdown)"
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
# Category taxonomy consistency
# ---------------------------------------------------------------------------


# Near-duplicate category spellings that fragment the GUI grouping: the param
# panel builds one collapsible section per distinct ``category`` string
# (param_panel.py groups by ``definition.category``), so a singular/plural or
# noun/gerund split of the same concept renders as two separate sections. Map
# each known alias to its canonical form and forbid the alias from reappearing.
CATEGORY_ALIASES = {
    "sensors": "sensor",
    "filtering": "filter",
    "debugging": "debug",
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_category_uses_canonical_spelling(entry: dict):
    """Categories must use the canonical spelling, not a known duplicate alias.

    Two spellings of the same concept (e.g. 'sensor' and 'sensors') split the
    parameter panel into two sections for what is logically one group.
    """
    category = entry.get("category")
    assert category not in CATEGORY_ALIASES, (
        f"Param '{entry['param']}' uses non-canonical category '{category}'; "
        f"use '{CATEGORY_ALIASES.get(category)}' instead"
    )


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
