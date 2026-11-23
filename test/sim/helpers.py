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
