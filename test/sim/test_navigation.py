# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: the robot really navigates, and a param changed through the tool changes it."""

import pytest

from sim.helpers import PeakSpeed, SignalRecorder, navigate, wait_until

pytestmark = pytest.mark.sim

# Two free cells in the nav2_bringup TurtleBot3 world, 0.5+ m clear of obstacles, ~2.25 m apart.
# The tests alternate between them. Not the spawn cell (-2.0, -0.5): Nav2's planner
# refuses to plan to it, even with tolerance, so it cannot be a goal.
GOAL_A = (-0.5, 0.5)
GOAL_B = (-0.5, -1.75)
NODE, PARAM = "/controller_server", "FollowPath.max_vel_x"


def _set_via_tool(app, value: float) -> None:
    rec = SignalRecorder(app.node.signals.param_set_result)
    app.node.request_set_param(NODE, PARAM, value, "double")
    wait_until(lambda: any(c[:2] == (NODE, PARAM) for c in rec.calls), 30, what="param set")
    assert next(c[2] for c in rec.calls if c[:2] == (NODE, PARAM)) is True


def test_goal_succeeds_and_returns(app, nav):
    assert navigate(nav, *GOAL_A), f"robot did not reach A: {nav.getResult()}"
    assert navigate(nav, *GOAL_B), f"robot did not reach B: {nav.getResult()}"
    assert navigate(nav, *GOAL_A), f"robot did not come back to A: {nav.getResult()}"


def test_max_vel_x_changes_robot_speed(app, nav, restore_params):
    restore_params(NODE, PARAM)
    # Fast leg first, slow leg last: Nav2's planner repeatedly failed to plan the leg that
    # *followed* a 0.10 m/s run (cause not isolated, sim-side), so every leg here starts
    # from a normal-speed arrival, as in test_goal_succeeds_and_returns.
    _set_via_tool(app, 0.26)
    with PeakSpeed(app.node) as fast:
        assert navigate(nav, *GOAL_B), f"fast run failed: {nav.getResult()}"
    _set_via_tool(app, 0.10)
    with PeakSpeed(app.node) as slow:
        assert navigate(nav, *GOAL_A), f"slow run failed: {nav.getResult()}"
    # Gazebo odometry overshoots the commanded limit (measured 0.123 and 0.151 m/s peaks at a
    # 0.10 limit), so allow ~80% headroom; the fast run must still be clearly faster.
    assert slow.peak <= 0.18, f"max_vel_x=0.10 but robot reached {slow.peak:.3f} m/s"
    assert fast.peak > 0.20, f"max_vel_x=0.26 but robot only reached {fast.peak:.3f} m/s"
    assert fast.peak > 1.5 * slow.peak, f"slow {slow.peak:.3f} vs fast {fast.peak:.3f} m/s"
