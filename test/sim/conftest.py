# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Fixtures for the live-sim tests: headless TurtleBot3 Nav2 + the real tool."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(SRC_ROOT))

from sim.helpers import (  # noqa: E402
    SignalRecorder, start_stack, stop_stack, ros2_param_get, ros2_param_set,
)

SIM_START_TIMEOUT = 120.0
LAUNCH_CMD = [
    "ros2", "launch", "nav2_bringup", "tb3_simulation_launch.py",
    "headless:=True", "use_rviz:=False",
]
SIM_ENV = {"TURTLEBOT3_MODEL": "waffle", "GAZEBO_MODEL_DATABASE_URI": ""}
# Default TurtleBot3 spawn pose in the nav2_bringup world.
START_X, START_Y = -2.0, -0.5

INITIAL_POSE_MSG = (
    "{header: {frame_id: map}, pose: {pose: {position: {x: %s, y: %s}, "
    "orientation: {w: 1.0}}, covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, "
    "0,0,0,0,0,0, 0,0,0,0.07,0,0, 0,0,0,0,0.07,0, 0,0,0,0,0,0.07]}}"
) % (START_X, START_Y)


def _cli(cmd: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _all_lifecycle_active() -> bool:
    names = _cli(["ros2", "lifecycle", "nodes"]).stdout.split()
    if "/bt_navigator" not in names or "/amcl" not in names:
        return False
    return all(
        "active [3]" in _cli(["ros2", "lifecycle", "get", n]).stdout for n in names
    )


def _publish_initial_pose() -> None:
    _cli(["ros2", "topic", "pub", "--once", "/initialpose",
          "geometry_msgs/msg/PoseWithCovarianceStamped", INITIAL_POSE_MSG])


def _amcl_pose_received() -> bool:
    r = _cli(["ros2", "topic", "echo", "--once", "--qos-durability",
              "transient_local", "--qos-reliability", "reliable", "/amcl_pose"], 6)
    return r.returncode == 0 and "pose:" in r.stdout


def _ready() -> bool:
    _publish_initial_pose()  # harmless when already localized
    return _all_lifecycle_active() and _amcl_pose_received()


@pytest.fixture(scope="session")
def sim_stack():
    """Boot headless TurtleBot3 Nav2; yield the sim log path; always tear down."""
    log_dir = Path(os.environ.get("SIM_LOG_DIR", "/tmp/nav2_config_sim"))
    shutil.rmtree(log_dir, ignore_errors=True)
    log_path = log_dir / "sim.log"
    proc = start_stack(
        LAUNCH_CMD, _ready, timeout=SIM_START_TIMEOUT, retries=1,
        log_path=log_path, env=SIM_ENV,
    )
    try:
        yield log_path
    finally:
        stop_stack(proc)


@dataclass
class App:
    node: object
    window: object
    schema: list
    rec: dict = field(default_factory=dict)  # name -> SignalRecorder, connected at startup


@pytest.fixture(scope="session")
def app(sim_stack):
    """The real tool, wired like nav2_config/main.py, running offscreen."""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from PyQt6.QtWidgets import QApplication
    from nav2_config.node import Nav2ConfigNode
    from nav2_config.gui.main_window import MainWindow
    from nav2_config.types.params import load_schema

    rclpy.init()
    node = Nav2ConfigNode()
    schema = load_schema()
    node.set_schema(schema)
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()

    qapp = QApplication.instance() or QApplication([])
    sig = node.signals
    rec = {
        name: SignalRecorder(getattr(sig, name))
        for name in ("topology_updated", "robot_mode_changed",
                     "lifecycle_manager_status", "lifecycle_states_updated")
    }
    window = MainWindow(node, config_file=None)
    window.show()
    try:
        yield App(node, window, schema, rec)
    finally:
        window.close()
        executor.shutdown(timeout_sec=0.0)
        thread.join(timeout=5.0)
        node.destroy_node()
        rclpy.shutdown()
        del qapp


@pytest.fixture
def restore_params():
    """Yield touch(node, name): remember the live value now, restore it at teardown."""
    saved: list[tuple[str, str, str]] = []

    def touch(node: str, name: str) -> None:
        out = ros2_param_get(node, name)  # e.g. "Double value is: 0.26"
        saved.append((node, name, out.split(": ", 1)[-1]))

    yield touch
    for node, name, value in reversed(saved):
        ros2_param_set(node, name, value)
