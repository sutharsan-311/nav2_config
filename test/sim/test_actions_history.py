# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: post-set actions, restart suggestions, history and undo."""

import re

import pytest

from nav2_config.types.history import ChangeSource
from sim.helpers import SignalRecorder, ros2_param_get, ros2_param_set, select_node, wait_until

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
    live_sets = lambda: [e for e in history.get_history()  # noqa: E731
                         if e.source is ChangeSource.LIVE_SET and e.ref.param_name == name]
    before = len(live_sets())

    app.window._on_param_set_requested(node, name, 0.18)
    wait_until(lambda: len(live_sets()) > before and live_sets()[-1].status == "applied", 30,
               what="history entry applied")
    entry = live_sets()[-1]
    assert (entry.ref.node_path, entry.ref.param_name) == (node, name)
    assert entry.type_hint == "double", entry
    assert isinstance(entry.old_value, float), repr(entry.old_value)
    assert entry.old_value == pytest.approx(original)
    assert entry.new_value == pytest.approx(0.18)
    assert float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group()) == pytest.approx(0.18)

    app.window._on_undo_requested(entry.entry_id)
    wait_until(lambda: float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group())
               == pytest.approx(original), 30, what="live value restored by undo")


def test_undo_of_external_change_restores_live_value(app, restore_params):
    """Undo on a History row for a change made outside the tool must work for any type."""
    node, name = "/controller_server", "FollowPath.max_vel_x"
    restore_params(node, name)
    original = float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group())
    select_node(app, node)
    history = app.window._history
    external = lambda: [e for e in history.get_history()  # noqa: E731
                        if e.source is ChangeSource.EXTERNAL_CHANGE and e.ref.param_name == name
                        and e.new_value == pytest.approx(0.22)]
    # Re-arm the watcher (clears its baseline); the next 2 s poll re-establishes it and
    # only changes made after that are reported.
    app.node.watch_node(node)
    wait_until(lambda: name in app.node._watcher._baseline, 30, what="watcher baseline")
    assert ros2_param_set(node, name, "0.22") == 0
    try:
        wait_until(lambda: external(), 30, what="external change recorded in history")
    except TimeoutError:
        recent = [(e.source.name, e.ref.param_name, e.new_value, e.status)
                  for e in history.get_history()[-5:]]
        pytest.fail(f"no external entry; watched={app.node._watcher.watched_node!r} "
                    f"baseline_has_param={name in app.node._watcher._baseline} recent={recent}")

    app.window._on_undo_requested(external()[-1].entry_id)
    wait_until(lambda: float(re.search(r"[-\d.]+$", ros2_param_get(node, name)).group())
               == pytest.approx(original), 30, what="live value restored by undo of external change")
