# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: lifecycle control. Named zz_ so it runs last: it disturbs the whole stack.

Order matters inside this file: pause/resume, then the risky direct transition (which
can break the lifecycle_manager bond), then a stack restart to recover, then proof that
navigation still works.
"""

import pytest

from sim.helpers import (
    SignalRecorder, amcl_pose_received, lifecycle_states, navigate,
    publish_initial_pose, wait_until,
)

pytestmark = pytest.mark.sim

DEACTIVATE, ACTIVATE = 4, 3          # lifecycle_msgs/Transition ids
GOAL_A = (-0.5, 0.5)                 # same free cell as test_navigation.py
EXPECTED_MANAGED = [
    "/amcl", "/map_server", "/behavior_server", "/bt_navigator", "/controller_server",
    "/planner_server", "/smoother_server", "/velocity_smoother", "/waypoint_follower",
]


def _managed(app) -> list[str]:
    """Lifecycle nodes that a lifecycle_manager controls, per the tool's own mapping."""
    app.node.force_discover()
    wait_until(lambda: app.node.get_manager_for_node("/planner_server"), 30,
               what="tool to map nodes to their lifecycle_manager")
    names = sorted(p for p in lifecycle_states() if app.node.get_manager_for_node(p))
    # The costmaps are children of controller/planner server, not managed directly.
    assert names == sorted(EXPECTED_MANAGED), f"managed nodes: {names}"
    return names


def _wait_all(names: list[str], state: str, timeout: float) -> None:
    def done() -> bool:
        states = lifecycle_states()
        return all(states.get(n) == state for n in names)
    try:
        wait_until(done, timeout, interval=2.0, what=f"all {len(names)} managed nodes {state}")
    except TimeoutError as exc:
        raise TimeoutError(f"{exc}; states now: {lifecycle_states()}") from None


def test_pause_then_resume_stack(app):
    managed = _managed(app)
    app.node.request_lifecycle_pause_stack()
    _wait_all(managed, "inactive", 90)
    wait_until(lambda: all(app.node.get_lifecycle_state(n) == "inactive" for n in managed),
               30, what="the tool to show every managed node inactive")

    app.node.request_lifecycle_resume_stack()
    _wait_all(managed, "active", 120)
    wait_until(lambda: all(app.node.get_lifecycle_state(n) == "active" for n in managed),
               30, what="the tool to show every managed node active")


def test_expert_mode_direct_transition(app):
    """Expert mode lets a node be deactivated directly, bypassing the lifecycle_manager.

    That breaks the manager's bond and can bring the whole stack down (the tool warns about
    this), so we only assert that the transition runs and the node leaves `active`; the next
    test restarts the stack.
    """
    node = "/planner_server"
    app.window._expert_mode_warned = True   # skip the one-time modal warning (unanswerable offscreen)
    app.window._on_expert_mode_toggled(True)
    assert app.window._expert_mode is True

    results = SignalRecorder(app.node.signals.lifecycle_change_result)
    app.node.request_lifecycle_change(node, DEACTIVATE)
    wait_until(lambda: any(c[0] == node for c in results.calls), 30, what="deactivate result")
    assert next(c for c in results.calls if c[0] == node)[1] is True
    try:
        wait_until(lambda: lifecycle_states().get(node) != "active", 30, interval=1.0,
                   what=f"{node} to leave active")
    except TimeoutError as exc:
        raise TimeoutError(f"{exc}; states now: {lifecycle_states()}") from None
    app.window._on_expert_mode_toggled(False)
    assert app.window._expert_mode is False


def test_restart_stack(app):
    managed = _managed(app)
    app.node.request_lifecycle_restart_stack("/")
    _wait_all(managed, "active", 150)


def test_navigation_works_after_lifecycle_changes(app, nav):
    # A restart resets AMCL, so localize again the way the harness did at startup.
    wait_until(lambda: (publish_initial_pose(), amcl_pose_received())[1], 90, interval=2.0,
               what="AMCL to localize after the restart")
    assert navigate(nav, *GOAL_A), f"robot could not navigate after lifecycle changes: {nav.getResult()}"
