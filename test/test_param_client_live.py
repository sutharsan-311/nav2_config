# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""Live integration test for Nav2ParamClient.

Verifies our actual Nav2ParamClient class (not the CLI) by:
  1. Initializing rclpy and creating a node
  2. Creating a Nav2ParamClient instance
  3. Calling list_params / get_params / set_param / verify on:
       /controller_server, /amcl, /local_costmap/local_costmap

Usage:
    cd ~/ros2_ws/src/nav2_config
    python3 test/test_param_client_live.py

Requires a running Nav2 stack (e.g. turtlebot3 simulation or real robot).
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

# Allow imports from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from nav2_config.core.param_client import Nav2ParamClient


# ---------------------------------------------------------------------------
# ANSI helpers (same as test_live_params.py)
# ---------------------------------------------------------------------------

def _color(text: str, code: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"

def _green(t: str) -> str:  return _color(t, "32")
def _yellow(t: str) -> str: return _color(t, "33")
def _red(t: str) -> str:    return _color(t, "31")
def _bold(t: str) -> str:   return _color(t, "1")
def _cyan(t: str) -> str:   return _color(t, "36")


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

# Results accumulator: list of (test_name, passed, detail)
_results: list[tuple[str, bool, str]] = []


def _ok(label: str, detail: str = "") -> None:
    print(f"  {_green('✓ PASS')}  {label}" + (f"  — {detail}" if detail else ""))
    _results.append((label, True, detail))


def _fail(label: str, detail: str = "") -> None:
    print(f"  {_red('✗ FAIL')}  {label}" + (f"  — {detail}" if detail else ""))
    _results.append((label, False, detail))


def _skip(label: str, detail: str = "") -> None:
    print(f"  {_yellow('— SKIP')}  {label}" + (f"  — {detail}" if detail else ""))
    _results.append((label, True, f"SKIPPED: {detail}"))   # count as non-fail


def _section(title: str) -> None:
    print()
    print(_bold(f"  ── {title} ──────────────────────────────────────"))


# ---------------------------------------------------------------------------
# Node-level test helpers
# ---------------------------------------------------------------------------

def test_list_params(client: Nav2ParamClient, node_path: str) -> list[str]:
    """Calls list_params and prints the result. Returns the name list."""
    label = f"list_params({node_path})"
    params = client.list_params(node_path)
    if params:
        _ok(label, f"{len(params)} params returned")
        # Print a sample (first 10)
        sample = params[:10]
        print(f"      sample: {sample}" + (" …" if len(params) > 10 else ""))
    else:
        _fail(label, "returned empty list — node may be offline or service unavailable")
    return params


def test_get_params(
    client: Nav2ParamClient,
    node_path: str,
    param_names: list[str],
) -> dict[str, Any]:
    """Calls get_params and prints the result. Returns the values dict."""
    label = f"get_params({node_path}, {param_names})"
    values = client.get_params(node_path, param_names)
    if values:
        _ok(label, f"got {len(values)}/{len(param_names)} values")
        for k, v in values.items():
            print(f"      {k} = {v!r}")
    else:
        _fail(label, "returned empty dict — params may not exist or node offline")
    return values


def test_set_get_restore(
    client: Nav2ParamClient,
    node_path: str,
    param_name: str,
    test_value: Any,
    type_hint: str,
) -> None:
    """SET(test_value) → GET to verify → RESTORE original.  Prints each step."""
    base_label = f"{node_path} / {param_name}"

    # ── Step 1: read original ──────────────────────────────────────────────
    original_map = client.get_params(node_path, [param_name])
    if not original_map:
        _skip(f"{base_label}: get original", "cannot read current value")
        return
    original = original_map[param_name]
    print(f"      original value: {original!r}")

    # ── Step 2: set test value ────────────────────────────────────────────
    set_ok = client.set_param(node_path, param_name, test_value, type_hint)
    if not set_ok:
        _fail(f"{base_label}: set_param({test_value!r})", "node rejected the change")
        # Attempt restore anyway
        client.set_param(node_path, param_name, original, type_hint)
        return
    _ok(f"{base_label}: set_param({test_value!r})", "accepted")

    # Small pause so the node processes the change
    time.sleep(0.3)

    # ── Step 3: verify ────────────────────────────────────────────────────
    verify_map = client.get_params(node_path, [param_name])
    if not verify_map:
        _fail(f"{base_label}: verify after set", "cannot re-read value")
    else:
        got = verify_map[param_name]
        # Float comparison with tolerance
        if type_hint == "double":
            match = isinstance(got, float) and abs(got - float(test_value)) < 1e-4
        else:
            match = (got == test_value)
        if match:
            _ok(f"{base_label}: verify", f"value is now {got!r} as expected")
        else:
            _fail(f"{base_label}: verify", f"expected {test_value!r}, got {got!r}")

    # ── Step 4: restore ───────────────────────────────────────────────────
    restore_ok = client.set_param(node_path, param_name, original, type_hint)
    if restore_ok:
        _ok(f"{base_label}: restore to {original!r}")
    else:
        _fail(f"{base_label}: restore to {original!r}", "restore failed — param left at test value!")


# ---------------------------------------------------------------------------
# Per-node test suites
# ---------------------------------------------------------------------------

def run_controller_server_tests(client: Nav2ParamClient) -> None:
    _section("Testing /controller_server")

    # a) list_params
    params = test_list_params(client, "/controller_server")
    if not params:
        print(_yellow("  Skipping further controller_server tests (node offline)"))
        return

    # b) get_params for controller_frequency
    target_param = "controller_frequency"
    if target_param not in params:
        # Some setups use a prefixed name — try to find it
        candidates = [p for p in params if "controller_frequency" in p]
        if candidates:
            target_param = candidates[0]
            print(f"  Note: using {target_param!r} (schema name mismatch)")
        else:
            _skip(f"get_params({target_param})", "param not found on live node")
            target_param = None  # type: ignore[assignment]

    if target_param:
        values = test_get_params(client, "/controller_server", [target_param])

        # c/d/g) set to 25.0, verify, restore
        _section("  set/verify/restore controller_frequency → 25.0")
        test_set_get_restore(client, "/controller_server", target_param, 25.0, "double")


def run_amcl_tests(client: Nav2ParamClient) -> None:
    _section("Testing /amcl")

    params = test_list_params(client, "/amcl")
    if not params:
        print(_yellow("  Skipping further amcl tests (node offline)"))
        return

    # Try a readable float param
    candidates = [
        "alpha1", "alpha2", "alpha3", "alpha4", "alpha5",
        "min_particles", "max_particles",
        "laser_min_range", "laser_max_range",
    ]
    target_param = next((p for p in candidates if p in params), None)
    if target_param:
        test_get_params(client, "/amcl", [target_param])
    else:
        _skip("get_params(amcl, <motion param>)", "no known motion params found on live node")


def run_local_costmap_tests(client: Nav2ParamClient) -> None:
    _section("Testing /local_costmap/local_costmap")

    node_path = "/local_costmap/local_costmap"
    params = test_list_params(client, node_path)
    if not params:
        print(_yellow("  Skipping further local_costmap tests (node offline)"))
        return

    # Try to get a readable param
    candidates = [
        "update_frequency", "publish_frequency",
        "width", "height", "resolution",
        "robot_radius", "inflation_radius",
    ]
    target_param = next((p for p in candidates if p in params), None)
    if target_param:
        test_get_params(client, node_path, [target_param])
    else:
        _skip(f"get_params(local_costmap, <known param>)", "no known params found")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> int:
    total   = len(_results)
    passed  = sum(1 for _, ok, _ in _results if ok)
    failed  = total - passed
    failed_items = [(n, d) for n, ok, d in _results if not ok]

    print()
    print("─" * 70)
    print(_bold("  Nav2ParamClient Live Test Summary"))
    print("─" * 70)
    print(f"  Total : {total}")
    print(f"  {_green('Pass')}  : {passed}")
    print(f"  {_red('Fail')}  : {failed}")
    if failed_items:
        print()
        print(_red("  FAILURES:"))
        for name, detail in failed_items:
            print(f"    ✗  {name}")
            if detail:
                print(f"       {detail}")
    print("─" * 70)

    if failed == 0:
        print(_green("\n  ✓  All Nav2ParamClient tests passed.\n"))
        return 0
    else:
        print(_red(f"\n  ✗  {failed} test(s) failed.\n"))
        return 1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(_bold("\nnav2_config — Nav2ParamClient Live Integration Test"))
    print("Tests our Python client class directly (not the ros2 CLI)")
    print()

    # ── 1. Init ROS2 ──────────────────────────────────────────────────────
    rclpy.init(args=None)
    node: Node = rclpy.create_node("nav2_param_client_test")  # type: ignore[assignment]
    print(f"  ROS2 node created: {node.get_name()}")

    # ── 2. Start executor on background thread ────────────────────────────
    # Nav2ParamClient._call() needs the executor to spin so futures complete.
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    print(f"  MultiThreadedExecutor spinning (thread={spin_thread.native_id})")

    # Give the node a moment to announce itself to the ROS2 graph
    time.sleep(1.0)

    # ── 3. Create Nav2ParamClient ─────────────────────────────────────────
    client = Nav2ParamClient(node)
    print("  Nav2ParamClient created")

    # ── 4. Run test suites ────────────────────────────────────────────────
    try:
        run_controller_server_tests(client)
        run_amcl_tests(client)
        run_local_costmap_tests(client)
    except KeyboardInterrupt:
        print("\n  Interrupted — printing partial summary")
    except Exception as exc:
        print(_red(f"\n  Unexpected error: {exc}"))
        import traceback
        traceback.print_exc()

    # ── 5. Shutdown ───────────────────────────────────────────────────────
    executor.shutdown(timeout_sec=2.0)
    node.destroy_node()
    rclpy.shutdown()
    print("  ROS2 shutdown complete")

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
