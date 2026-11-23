# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the sim-test harness helpers (no simulation needed)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

import sim.helpers as helpers
from sim.helpers import start_stack, stop_stack, wait_until


@pytest.fixture(autouse=True)
def _no_sweep(monkeypatch):
    """Never pkill a developer's real Gazebo from a unit test."""
    monkeypatch.setattr(helpers, "SWEEP", ())


def test_wait_until_times_out():
    with pytest.raises(TimeoutError, match="the moon"):
        wait_until(lambda: False, timeout=0.3, interval=0.05, what="the moon")


def test_start_stack_retries_once_then_fails(tmp_path: Path):
    log = tmp_path / "sim.log"
    attempts = []

    def ready() -> bool:
        attempts.append(1)
        return False

    with pytest.raises(RuntimeError, match="hello-from-sim"):
        start_stack(
            ["bash", "-c", "echo hello-from-sim; sleep 60"],
            ready=ready, timeout=1.0, retries=1, log_path=log,
        )
    # two launches, each polled at least once
    assert len(attempts) >= 2
    assert "hello-from-sim" in log.read_text()


def test_stop_stack_kills_children(tmp_path: Path):
    proc = subprocess.Popen(
        ["bash", "-c", "sleep 61 & sleep 62 & wait"], start_new_session=True,
    )
    time.sleep(0.5)
    sid = os.getsid(proc.pid)
    stop_stack(proc)
    left = subprocess.run(
        ["pgrep", "-s", str(sid)], capture_output=True, text=True
    ).stdout.split()
    assert left == []
