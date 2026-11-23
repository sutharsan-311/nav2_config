# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: the tool finds the running Nav2 stack."""

import pytest

from sim.helpers import wait_until

pytestmark = pytest.mark.sim

EXPECTED_NODES = {
    "/controller_server", "/planner_server", "/bt_navigator", "/amcl",
    "/map_server", "/behavior_server",
    "/local_costmap/local_costmap", "/global_costmap/global_costmap",
}


def test_all_nav2_nodes_discovered(app):
    app.node.force_discover()
    def found() -> bool:
        calls = app.rec["topology_updated"].calls
        return bool(calls) and EXPECTED_NODES <= set(calls[-1][0])
    wait_until(found, 60, what="all Nav2 nodes in topology_updated")


def test_lifecycle_manager_discovered(app):
    app.node.force_discover()
    calls = app.rec["lifecycle_manager_status"].wait(1, timeout=60)
    assert any(present for present, _path in calls)


def test_robot_mode_detected(app):
    app.node.force_discover()
    assert app.rec["robot_mode_changed"].wait(1, timeout=60)


def test_topic_and_frame_sources_nonempty(app):
    topics = app.node.topic_discovery
    wait_until(lambda: "/cmd_vel" in topics.get_all_topics(), 30, what="/cmd_vel topic")
    assert "/scan" in topics.get_all_topics()
    frames = app.node.frame_discovery
    try:
        wait_until(lambda: {"map", "base_link"} <= set(frames.get_common_frames()),
                   60, what="map and base_link TF frames")
    except TimeoutError:
        pytest.fail(f"expected map and base_link, tool sees frames: {frames.get_all_frames()}")
