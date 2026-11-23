# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: post-set actions, restart suggestions, history and undo."""

import re

import pytest

from sim.helpers import SignalRecorder, ros2_param_get, select_node, wait_until

pytestmark = pytest.mark.sim

MAP_YAML = "/opt/ros/humble/share/nav2_bringup/maps/turtlebot3_world.yaml"


def _set_and_wait_action(app, node, name, value, hint, action):
    rec = SignalRecorder(app.node.signals.post_action_result)
    app.node.request_set_param(node, name, value, hint)
    wait_until(lambda: any(c[1] == action for c in rec.calls), 30,
               what=f"post_action_result {action}")
    return next(c for c in rec.calls if c[1] == action)


def test_clear_costmaps_action(app, restore_params):
    node, name = "/local_costmap/local_costmap", "inflation_layer.inflation_radius"
    restore_params(node, name)
    param, action, ok, _msg = _set_and_wait_action(app, node, name, 0.5, "double", "clear_costmaps")
    assert ok is True
    assert param == name


def test_nomotion_update_action(app, restore_params):
    restore_params("/amcl", "alpha1")
    _p, _a, ok, _m = _set_and_wait_action(app, "/amcl", "alpha1", 0.25, "double", "nomotion_update")
    assert ok is True


def test_load_map_action(app, restore_params):
    restore_params("/map_server", "yaml_filename")
    rec = SignalRecorder(app.node.signals.load_map_result)
    app.node.request_set_param("/map_server", "yaml_filename", MAP_YAML, "string")
    wait_until(lambda: rec.calls, 30, what="load_map_result")
    assert rec.calls[-1][0] is True, rec.calls[-1]


def test_restart_stack_action_suggests_restart(app, restore_params):
    node, name = "/controller_server", "progress_checker_plugin"
    restore_params(node, name)
    rec = SignalRecorder(app.node.signals.restart_suggested)
    app.node.request_set_param(node, name, "progress_checker", "string")
    wait_until(lambda: rec.calls, 30, what="restart_suggested")
    assert rec.calls[-1] == (node, name)


@pytest.mark.xfail(strict=True, raises=TimeoutError, reason=(
    "restart_node / restart_controller post_set_actions are not dispatched in "
    "node._after_param_set (see docs/dev-notes.md)"))
@pytest.mark.parametrize("node,bare,param", [
    ("/behavior_server", "behavior_server", "local_costmap_topic"),         # restart_node
    ("/controller_server", "controller_server", "follow_path.model_dt"),    # restart_controller
])
def test_restart_actions_known_bug(app, node, bare, param):
    # These params do not exist on a Humble stack, so call the dispatcher directly.
    entry = next(d for d in app.schema if d.node == bare and d.param == param)
    assert entry.post_set_action in ("restart_node", "restart_controller")
    rec = SignalRecorder(app.node.signals.restart_suggested)
    app.node._after_param_set(node, param, "x", entry)
    wait_until(lambda: rec.calls, 3, what="restart_suggested")


def test_history_records_and_undo(app, restore_params):
    node, name = "/controller_server", "FollowPath.max_vel_x"
    restore_params(node, name)
    original = float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group())
    select_node(app, node)
    history = app.window._history
    before = len(history.get_history())

    app.window._on_param_set_requested(node, name, 0.18)
    wait_until(lambda: len(history.get_history()) > before
               and history.get_history()[-1].status == "applied", 30,
               what="history entry applied")
    entry = history.get_history()[-1]
    assert (entry.ref.node_path, entry.ref.param_name) == (node, name)
    assert entry.old_value == pytest.approx(original)
    assert entry.new_value == pytest.approx(0.18)
    assert float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group()) == pytest.approx(0.18)

    app.window._on_undo_requested(entry.entry_id)
    wait_until(lambda: float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group())
               == pytest.approx(original), 30, what="live value restored by undo")
