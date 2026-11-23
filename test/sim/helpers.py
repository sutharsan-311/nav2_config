# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Helpers for the live-sim tests: polling, CLI oracle, signal capture, stack control."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

# Process names killed after a stack stops. Tests that must not touch a
# developer's own Gazebo blank this out.
SWEEP = ("gzserver", "gzclient")


def wait_until(
    cond: Callable[[], bool],
    timeout: float = 30.0,
    interval: float = 0.1,
    what: str = "condition",
) -> None:
    """Poll *cond* until true, pumping Qt events between polls."""
    from PyQt6.QtCore import QCoreApplication

    deadline = time.monotonic() + timeout
    while True:
        app = QCoreApplication.instance()
        if app is not None:
            app.processEvents()
        if cond():
            return
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for {what}")
        time.sleep(interval)


def _run(cmd: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ros2_param_get(node: str, name: str) -> str:
    """Independent oracle: read a param with the ros2 CLI, e.g. 'Double value is: 0.26'."""
    return _run(["ros2", "param", "get", node, name]).stdout.strip()


def ros2_param_set(node: str, name: str, value: str) -> int:
    """Set a param with the ros2 CLI and return its exit code."""
    return _run(["ros2", "param", "set", node, name, value]).returncode


class SignalRecorder:
    """Record every emission of a Qt signal as a tuple of its arguments."""

    def __init__(self, signal) -> None:
        self.calls: list[tuple] = []
        signal.connect(lambda *args: self.calls.append(args))

    def wait(self, n: int = 1, timeout: float = 15.0) -> list[tuple]:
        wait_until(lambda: len(self.calls) >= n, timeout, what=f"{n} signal emission(s)")
        return list(self.calls)


def stop_stack(proc: subprocess.Popen) -> None:
    """SIGINT the stack's process group, then SIGKILL it, then sweep stray sim processes."""
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        pgid = None
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGINT)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    for name in SWEEP:
        subprocess.run(["pkill", "-9", "-x", name], capture_output=True)


def start_stack(
    cmd: list[str],
    ready: Callable[[], bool],
    timeout: float,
    retries: int,
    log_path: Path,
    env: dict | None = None,
) -> subprocess.Popen:
    """Launch *cmd* in its own process group and wait for *ready()*.

    On timeout (or early exit) the group is killed and the launch retried up
    to *retries* more times; then RuntimeError carries the log tail.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **(env or {})}
    for attempt in range(retries + 1):
        with open(log_path, "ab") as log:
            log.write(f"\n=== launch attempt {attempt + 1} ===\n".encode())
            log.flush()
            proc = subprocess.Popen(
                cmd, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True, env=full_env,
            )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and proc.poll() is None:
            try:
                if ready():
                    return proc
            except Exception:
                pass
            time.sleep(0.5)
        stop_stack(proc)
    tail = "\n".join(log_path.read_text(errors="replace").splitlines()[-40:])
    raise RuntimeError(
        f"stack did not become ready after {retries + 1} attempt(s):\n{tail}"
    )


def select_node(app, node_path: str, param: str | None = None, timeout: float = 30.0):
    """Select *node_path* in the window as a user would; wait for freshly built rows.

    Re-selecting the same node rebuilds the row widgets (progressively), and results are
    routed to the new rows, so a test must never keep a row from before the rebuild.
    With *param*, also wait until that param's row exists and return it.
    """
    bare = node_path.rstrip("/").rsplit("/", 1)[-1]
    old_rows = list(app.window._param_panel._all_rows)
    app.window._on_node_selected(node_path)

    def fresh_rows() -> list:
        return [r for r in app.window._param_panel._all_rows
                if all(r is not o for o in old_rows)]

    def loaded() -> bool:
        params = app.window._current_params
        fresh = fresh_rows()
        return (bool(params) and params[0].definition.node == bare
                and bool(fresh) and fresh[0]._param_value.definition.node == bare)

    wait_until(loaded, timeout, what=f"params and fresh rows of {node_path} loaded in the window")
    if param is None:
        return None

    def find():
        return next((r for r in fresh_rows() if r._param_value.definition.param == param), None)

    wait_until(lambda: find() is not None, timeout, what=f"row for {param} built")
    return find()


def navigate(nav, x: float, y: float, yaw: float = 0.0, timeout: float = 120.0) -> bool:
    """Send a NavigateToPose goal in the map frame; True only if Nav2 reports SUCCEEDED."""
    import math
    from geometry_msgs.msg import PoseStamped
    from nav2_simple_commander.robot_navigator import TaskResult
    from PyQt6.QtCore import QCoreApplication

    pose = PoseStamped()
    pose.header.frame_id = "map"  # stamp left at 0 = "latest transform"
    pose.pose.position.x, pose.pose.position.y = x, y
    pose.pose.orientation.z, pose.pose.orientation.w = math.sin(yaw / 2), math.cos(yaw / 2)
    nav.goToPose(pose)
    deadline = time.monotonic() + timeout
    while not nav.isTaskComplete():  # spins the navigator node ~0.1 s per call
        QCoreApplication.processEvents()
        if time.monotonic() > deadline:
            nav.cancelTask()
            return False
    return nav.getResult() == TaskResult.SUCCEEDED


class PeakSpeed:
    """Track the peak |linear x| seen on /odom while the context is open."""

    def __init__(self, node) -> None:
        self._node = node
        self.peak = 0.0

    def __enter__(self) -> "PeakSpeed":
        from nav_msgs.msg import Odometry

        def cb(msg) -> None:
            self.peak = max(self.peak, abs(msg.twist.twist.linear.x))

        self._sub = self._node.create_subscription(Odometry, "/odom", cb, 10)
        return self

    def __exit__(self, *exc) -> None:
        self._node.destroy_subscription(self._sub)


def lifecycle_states() -> dict[str, str]:
    """{node: state} for every lifecycle node, read with the ros2 CLI (an independent oracle)."""
    from concurrent.futures import ThreadPoolExecutor

    names = _run(["ros2", "lifecycle", "nodes"], timeout=30).stdout.split()

    def state(name: str) -> str:
        try:
            out = _run(["ros2", "lifecycle", "get", name], timeout=10).stdout.strip()
        except subprocess.TimeoutExpired:
            return "unreachable"          # a node that does not answer is a state, not a crash
        return out.split()[0] if out else "unknown"   # e.g. "active [3]"

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(names, pool.map(state, names)))


INITIAL_POSE_MSG = (
    "{header: {frame_id: map}, pose: {pose: {position: {x: -2.0, y: -0.5}, "
    "orientation: {w: 1.0}}, covariance: [0.25,0,0,0,0,0, 0,0.25,0,0,0,0, "
    "0,0,0,0,0,0, 0,0,0,0.07,0,0, 0,0,0,0,0.07,0, 0,0,0,0,0,0.07]}}"
)


def publish_initial_pose() -> None:
    """Tell AMCL where the TurtleBot3 spawned (the nav2_bringup world's start pose)."""
    _run(["ros2", "topic", "pub", "--once", "/initialpose",
          "geometry_msgs/msg/PoseWithCovarianceStamped", INITIAL_POSE_MSG], timeout=15)


def amcl_pose_received() -> bool:
    r = _run(["ros2", "topic", "echo", "--once", "--qos-durability", "transient_local",
              "--qos-reliability", "reliable", "/amcl_pose"], timeout=6)
    return r.returncode == 0 and "pose:" in r.stdout
