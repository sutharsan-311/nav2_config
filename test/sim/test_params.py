# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: parameter reads and writes through the real tool."""

from pathlib import Path

import pytest

from sim.helpers import SignalRecorder, ros2_param_get, ros2_param_set, wait_until

pytestmark = pytest.mark.sim

# rcl_interfaces/ParameterType values
ROS_TYPE = {
    "bool": 1, "int": 2, "double": 3, "string": 4,
    "int_array": 7, "double_array": 8, "string_array": 9,
}


def _allowlist() -> set[tuple[str, str]]:
    path = Path(__file__).with_name("schema_absent.txt")
    pairs = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            node, param = line.split(None, 1)
            pairs.add((node, param.strip()))
    return pairs


def test_live_schema_matches_nav2(app):
    """Every schema param on a running node exists live with the schema's type.

    Plugin-specific params may be absent (that plugin isn't loaded); anything
    else absent must be listed in schema_absent.txt.
    """
    from nav2_config.core.param_client import Nav2ParamClient

    app.node.force_discover()
    wait_until(lambda: app.rec["topology_updated"].calls, 60, what="topology")
    client = Nav2ParamClient(app.node)
    allowed = _allowlist()
    problems: list[str] = []
    checked = 0
    for path in sorted(app.rec["topology_updated"].calls[-1][0]):
        bare = path.rstrip("/").rsplit("/", 1)[-1]
        defs = [d for d in app.schema if d.node == bare]
        if not defs:
            continue
        live_names = set(client.list_params(path))
        live = client.get_params(path, [d.ros2_name for d in defs if d.ros2_name in live_names])
        for d in defs:
            if d.ros2_name not in live:
                if not d.plugin_specific and (bare, d.ros2_name) not in allowed:
                    problems.append(f"{bare} {d.ros2_name}: in schema, absent live")
                continue
            checked += 1
            live_type = live[d.ros2_name][1]
            if live_type != ROS_TYPE[d.type]:
                problems.append(
                    f"{bare} {d.ros2_name}: schema {d.type}, live ROS type {live_type}"
                )
    assert checked > 100, f"only {checked} params checked, discovery looks broken"
    assert not problems, f"{len(problems)} schema/live mismatches:\n" + "\n".join(problems)


def _set_via_tool(app, node: str, name: str, value, type_hint: str) -> bool:
    rec = SignalRecorder(app.node.signals.param_set_result)
    app.node.request_set_param(node, name, value, type_hint)
    wait_until(lambda: any(c[:2] == (node, name) for c in rec.calls), 30,
               what=f"param_set_result for {node} {name}")
    return next(c[2] for c in rec.calls if c[:2] == (node, name))


@pytest.mark.parametrize("node,name,value,hint,expect", [
    ("/controller_server", "FollowPath.max_vel_x", 0.31, "double", "0.31"),
    ("/amcl", "max_particles", 1234, "int", "1234"),
    ("/amcl", "always_reset_initial_pose", True, "bool", "True"),
    ("/amcl", "base_frame_id", "base_footprint", "string", "base_footprint"),
    ("/velocity_smoother", "max_velocity", [0.25, 0.0, 1.0], "double_array", "0.25"),
    ("/bt_navigator", "plugin_lib_names", [], "string_array", "[]"),
], ids=["double", "int", "bool", "string", "double_array", "empty_string_array"])
def test_set_roundtrip(app, restore_params, node, name, value, hint, expect):
    restore_params(node, name)
    assert _set_via_tool(app, node, name, value, hint) is True
    assert expect in ros2_param_get(node, name)


@pytest.mark.parametrize("node,name,value,hint", [
    ("/amcl", "max_particles", "not-an-int", "int"),      # wrong type
    ("/amcl", "no_such_param", 1, "int"),                  # undeclared param
    ("/no_such_node", "anything", 1, "int"),               # node does not exist
], ids=["wrong_type", "undeclared_param", "missing_node"])
def test_set_invalid_fails_cleanly(app, node, name, value, hint):
    assert _set_via_tool(app, node, name, value, hint) is False


def test_external_change_detected(app, restore_params):
    node, name = "/controller_server", "FollowPath.max_vel_x"
    restore_params(node, name)
    rec = SignalRecorder(app.node.signals.params_externally_changed)
    app.node.watch_node(node)
    # The first 2 s poll only establishes the baseline; changes after it are reported.
    wait_until(lambda: app.node._watcher._baseline, 30, what="watcher baseline")
    assert ros2_param_set(node, name, "0.22") == 0
    wait_until(lambda: any(c[0] == node for c in rec.calls), 30,
               what="params_externally_changed")
    app.node.unwatch_node()
    names = [item[0] for c in rec.calls for item in c[1]]
    assert name in names
