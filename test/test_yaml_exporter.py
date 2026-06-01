# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Tests for YAML export, focusing on namespace-aware node_path handling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Allow importing from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.core.yaml_exporter import _format_value, _node_path_to_yaml_keys, export_yaml
from nav2_config.types.params import Nav2ParamDef, ParamRange, ParamValue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_param_def(
    node: str,
    param: str,
    type: str = "double",
    default: Any = 1.0,
    *,
    description: str = "test parameter",
    impact: str = "",
    unit: str = "",
) -> Nav2ParamDef:
    return Nav2ParamDef(
        node=node,
        param=param,
        type=type,
        default=default,
        range=None,
        unit=unit,
        description=description,
        impact=impact,
        category="general",
        plugin_specific=False,
        plugin=None,
        hot_reload=True,
        tags=[],
    )


def _make_param_value(
    node: str,
    param: str,
    value: Any,
    *,
    node_path: str = "",
    is_modified: bool = False,
    type: str = "double",
    default: Any = None,
) -> ParamValue:
    if default is None:
        default = value
    defn = _make_param_def(node, param, type=type, default=default)
    return ParamValue(
        definition=defn,
        current_value=value,
        is_modified=is_modified,
        is_live=bool(node_path),
        node_path=node_path,
    )


# ---------------------------------------------------------------------------
# _node_path_to_yaml_keys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("node_path,expected_keys", [
    # Root-namespace regular node
    ("/controller_server", ["controller_server", "ros__parameters"]),
    # Namespaced regular node
    ("/robot1/controller_server", ["robot1", "controller_server", "ros__parameters"]),
    # Self-namespaced costmap in root
    ("/local_costmap/local_costmap", ["local_costmap", "local_costmap", "ros__parameters"]),
    # Self-namespaced costmap with robot namespace
    ("/robot1/local_costmap/local_costmap",
     ["robot1", "local_costmap", "local_costmap", "ros__parameters"]),
    # Deep namespace
    ("/fleet/robot2/planner_server",
     ["fleet", "robot2", "planner_server", "ros__parameters"]),
])
def test_node_path_to_yaml_keys(node_path: str, expected_keys: list[str]) -> None:
    assert _node_path_to_yaml_keys(node_path) == expected_keys


# ---------------------------------------------------------------------------
# export_yaml — node_path controls nesting depth
# ---------------------------------------------------------------------------


def test_export_yaml_root_namespace_node_path() -> None:
    """node_path='/controller_server' produces a top-level key with no extra nesting."""
    pv = _make_param_value(
        "controller_server", "controller_frequency", 20.0,
        node_path="/controller_server",
    )
    yaml_str = export_yaml([pv])

    assert "controller_server:" in yaml_str
    assert "  ros__parameters:" in yaml_str
    assert "    controller_frequency: 20.0" in yaml_str
    # Root namespace means no robot prefix key
    assert "robot1:" not in yaml_str


def test_export_yaml_namespaced_node_path_single_robot() -> None:
    """node_path='/robot1/controller_server' nests under robot1 key."""
    pv = _make_param_value(
        "controller_server", "controller_frequency", 25.0,
        node_path="/robot1/controller_server",
    )
    yaml_str = export_yaml([pv])

    lines = yaml_str.splitlines()
    # robot1: should appear at depth 0
    assert "robot1:" in lines
    # controller_server: should be indented under robot1
    assert "  controller_server:" in lines
    assert "    ros__parameters:" in lines
    assert "      controller_frequency: 25.0" in lines


def test_export_yaml_namespaced_node_path_two_robots() -> None:
    """Two robots each get their own top-level namespace block in the YAML."""
    pv_r1 = _make_param_value(
        "controller_server", "controller_frequency", 20.0,
        node_path="/robot1/controller_server",
    )
    pv_r2 = _make_param_value(
        "controller_server", "controller_frequency", 30.0,
        node_path="/robot2/controller_server",
    )
    yaml_str = export_yaml([pv_r1, pv_r2])

    assert "robot1:" in yaml_str
    assert "robot2:" in yaml_str
    # Both values must appear
    assert "20.0" in yaml_str
    assert "30.0" in yaml_str


def test_export_yaml_namespaced_costmap_nesting() -> None:
    """node_path='/robot1/local_costmap/local_costmap' produces three-level nesting."""
    pv = _make_param_value(
        "local_costmap", "update_frequency", 5.0,
        node_path="/robot1/local_costmap/local_costmap",
        type="double",
    )
    yaml_str = export_yaml([pv])

    lines = yaml_str.splitlines()
    assert "robot1:" in lines
    assert "  local_costmap:" in lines
    assert "    local_costmap:" in lines
    assert "      ros__parameters:" in lines
    assert "        update_frequency: 5.0" in lines


# ---------------------------------------------------------------------------
# export_yaml — fallback to definition.node when node_path is empty
# ---------------------------------------------------------------------------


def test_export_yaml_falls_back_to_definition_node_when_no_node_path() -> None:
    """When node_path is '' the exporter uses /definition.node as the YAML key."""
    pv = _make_param_value(
        "planner_server", "planner_frequency", 1.0,
        node_path="",  # no path set
    )
    yaml_str = export_yaml([pv])

    assert "planner_server:" in yaml_str
    assert "  ros__parameters:" in yaml_str
    assert "    planner_frequency: 1.0" in yaml_str


def test_export_yaml_mixed_node_path_and_no_node_path() -> None:
    """Params with node_path set and those without coexist in the same export."""
    pv_with_path = _make_param_value(
        "controller_server", "controller_frequency", 20.0,
        node_path="/robot1/controller_server",
    )
    pv_without_path = _make_param_value(
        "planner_server", "planner_frequency", 1.0,
        node_path="",
    )
    yaml_str = export_yaml([pv_with_path, pv_without_path])

    assert "robot1:" in yaml_str
    assert "controller_server:" in yaml_str
    assert "planner_server:" in yaml_str
    assert "controller_frequency: 20.0" in yaml_str
    assert "planner_frequency: 1.0" in yaml_str


# ---------------------------------------------------------------------------
# export_yaml — value formatting
# ---------------------------------------------------------------------------


def test_export_yaml_bool_formatted_as_lowercase() -> None:
    pv = _make_param_value(
        "controller_server", "use_sim_time", True,
        node_path="/controller_server", type="bool", default=False,
    )
    yaml_str = export_yaml([pv])
    assert "use_sim_time: true" in yaml_str


def test_export_yaml_string_value() -> None:
    pv = _make_param_value(
        "controller_server", "robot_base_frame", "base_link",
        node_path="/controller_server", type="string", default="base_link",
    )
    yaml_str = export_yaml([pv])
    assert "robot_base_frame: base_link" in yaml_str


def test_export_yaml_list_value() -> None:
    pv = _make_param_value(
        "controller_server", "goal_checker_plugins", ["general_goal_checker"],
        node_path="/controller_server", type="string_array",
        default=["general_goal_checker"],
    )
    yaml_str = export_yaml([pv])
    assert "goal_checker_plugins: [general_goal_checker]" in yaml_str


# ---------------------------------------------------------------------------
# export_yaml — pending marker
# ---------------------------------------------------------------------------


def test_export_yaml_pending_marker_added() -> None:
    """Parameters in pending_params get an inline '# (pending)' comment."""
    pv = _make_param_value(
        "controller_server", "controller_frequency", 25.0,
        node_path="/controller_server",
    )
    yaml_str = export_yaml([pv], pending_params={"controller_frequency"})
    assert "# (pending)" in yaml_str


def test_export_yaml_pending_marker_not_added_when_not_pending() -> None:
    pv = _make_param_value(
        "controller_server", "controller_frequency", 25.0,
        node_path="/controller_server",
    )
    yaml_str = export_yaml([pv], pending_params=set())
    assert "# (pending)" not in yaml_str


# ---------------------------------------------------------------------------
# export_yaml — empty param list
# ---------------------------------------------------------------------------


def test_export_yaml_empty_params() -> None:
    """Empty param list produces a valid (but empty) YAML with a comment."""
    yaml_str = export_yaml([])
    assert "# Generated by nav2_config" in yaml_str
    assert "(no parameters to export)" in yaml_str


# ---------------------------------------------------------------------------
# export_yaml — header contains ROS version
# ---------------------------------------------------------------------------


def test_export_yaml_header_contains_ros_version() -> None:
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    yaml_str = export_yaml([pv], ros_version="jazzy")
    assert "# ROS2 jazzy" in yaml_str


# ---------------------------------------------------------------------------
# export_yaml — plugin_filter excludes plugin-specific params
# ---------------------------------------------------------------------------


def test_export_yaml_plugin_filter_excludes_other_plugins() -> None:
    """plugin_filter keeps only matching plugin params and non-plugin-specific params."""
    defn_generic = _make_param_def("controller_server", "controller_frequency")
    defn_dwb = Nav2ParamDef(
        node="controller_server",
        param="xy_goal_tolerance",
        type="double",
        default=0.25,
        range=None,
        unit="",
        description="DWB goal tolerance",
        impact="",
        category="general",
        plugin_specific=True,
        plugin="DWB",
        hot_reload=True,
        tags=[],
    )
    defn_teb = Nav2ParamDef(
        node="controller_server",
        param="max_vel_x",
        type="double",
        default=0.5,
        range=None,
        unit="",
        description="TEB max velocity",
        impact="",
        category="general",
        plugin_specific=True,
        plugin="TEB",
        hot_reload=True,
        tags=[],
    )
    params = [
        ParamValue(definition=defn_generic, current_value=20.0),
        ParamValue(definition=defn_dwb, current_value=0.25),
        ParamValue(definition=defn_teb, current_value=0.5),
    ]
    yaml_str = export_yaml(params, plugin_filter="DWB")

    assert "controller_frequency" in yaml_str   # non-plugin-specific: always included
    assert "xy_goal_tolerance" in yaml_str       # DWB plugin: included
    assert "max_vel_x" not in yaml_str           # TEB plugin: excluded


# ---------------------------------------------------------------------------
# _format_value — unit tests for the scalar/sequence formatter
# ---------------------------------------------------------------------------


def test_format_value_bool_true() -> None:
    """Python True formats as lowercase 'true', not 'True'."""
    assert _format_value(True) == "true"


def test_format_value_bool_false() -> None:
    """Python False formats as lowercase 'false'."""
    assert _format_value(False) == "false"


def test_format_value_int() -> None:
    """Integer values are rendered without a decimal point."""
    assert _format_value(42) == "42"


def test_format_value_float_with_decimal() -> None:
    """A float with a fractional part keeps its decimal notation."""
    assert _format_value(3.14) == "3.14"


def test_format_value_float_whole_number() -> None:
    """A float equal to a whole number retains the '.0' suffix so YAML
    parsers do not misinterpret it as an integer."""
    assert _format_value(20.0) == "20.0"


def test_format_value_plain_string_unquoted() -> None:
    """A plain identifier string is returned without quotes."""
    assert _format_value("base_link") == "base_link"


def test_format_value_empty_string_quoted() -> None:
    """An empty string is represented as two double-quotes so YAML parsers
    see an explicit empty string rather than a null."""
    assert _format_value("") == '""'


def test_format_value_string_with_colon_quoted() -> None:
    """A string containing ':' must be quoted to avoid YAML mapping syntax."""
    result = _format_value("key: value")
    assert result.startswith('"') and result.endswith('"')
    assert "key: value" in result


def test_format_value_string_starting_with_tilde_quoted() -> None:
    """A string starting with '~' must be quoted because bare '~' is YAML null."""
    result = _format_value("~foo")
    assert result.startswith('"')


def test_format_value_string_starting_with_dash_quoted() -> None:
    """A string starting with '-' must be quoted to avoid YAML block-sequence
    indicator ambiguity."""
    result = _format_value("-my-topic")
    assert result.startswith('"')


def test_format_value_empty_list() -> None:
    """An empty list produces the inline YAML form '[]'."""
    assert _format_value([]) == "[]"


def test_format_value_list_of_strings() -> None:
    """A list of plain strings is rendered as an inline YAML flow sequence."""
    assert _format_value(["a", "b", "c"]) == "[a, b, c]"


def test_format_value_nested_list_of_floats() -> None:
    """Each element of a float list is formatted with the same float rules."""
    result = _format_value([1.0, 2.5])
    assert result == "[1.0, 2.5]"


def test_format_value_list_of_bools() -> None:
    """Boolean elements inside a list use lowercase true/false."""
    assert _format_value([True, False]) == "[true, false]"
