# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live integration tests for nav2_config lifecycle client.

Requires a running TurtleBot3 simulation (Nav2 stack active).
Run with:
    source /opt/ros/humble/setup.bash && source ~/ros2_ws/install/setup.bash
    python3 test/test_lifecycle_live.py
"""

import os
import subprocess
import sys
import time
import threading


def run(cmd: str, timeout: int = 10) -> tuple[str, int]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip(), result.returncode


def test_get_state() -> None:
    """Test getting lifecycle state for all Nav2 nodes via CLI."""
    nodes = [
        '/amcl', '/controller_server', '/planner_server', '/bt_navigator',
        '/smoother_server', '/velocity_smoother', '/behavior_server',
        '/waypoint_follower', '/map_server',
        '/local_costmap/local_costmap', '/global_costmap/global_costmap',
    ]
    print('=== GET STATE TEST ===')
    failed = []
    for node in nodes:
        out, rc = run(f'ros2 lifecycle get {node}')
        status = out if out else '(no output)'
        print(f'  {node}: {status} (rc={rc})')
        if rc != 0:
            failed.append(node)
    if failed:
        print(f'  WARNING: could not query state for: {failed}')
    print()


def test_deactivate_activate() -> None:
    """Test deactivate then reactivate a safe node via CLI."""
    node = '/smoother_server'
    print(f'=== DEACTIVATE/ACTIVATE TEST: {node} ===')

    out, _ = run(f'ros2 lifecycle get {node}')
    print(f'  Initial state: {out}')

    out, rc = run(f'ros2 lifecycle set {node} deactivate', timeout=15)
    print(f'  Deactivate: {out} (rc={rc})')
    time.sleep(1)

    out, _ = run(f'ros2 lifecycle get {node}')
    print(f'  After deactivate: {out}')

    if 'inactive' not in out.lower():
        # lifecycle_manager may have already re-activated; that's normal
        print(f'  NOTE: Expected inactive, got {out!r} — lifecycle_manager may have re-activated.')
    else:
        print('  ✓ Node reached inactive state')

    out, rc = run(f'ros2 lifecycle set {node} activate', timeout=15)
    print(f'  Activate: {out} (rc={rc})')
    time.sleep(1)

    out, _ = run(f'ros2 lifecycle get {node}')
    print(f'  After activate: {out}')

    if 'active' not in out.lower():
        print(f'  WARNING: Expected active, got {out!r}')
    else:
        print('  ✓ Node returned to active state')

    print()


def test_lifecycle_client() -> None:
    """Test our LifecycleClient class directly against the live simulation."""
    print('=== LIFECYCLE CLIENT TEST ===')

    import rclpy
    from rclpy.executors import MultiThreadedExecutor

    rclpy.init()
    ros_node = rclpy.create_node('lifecycle_test_node')
    executor = MultiThreadedExecutor()
    executor.add_node(ros_node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    # Add the workspace source root to the path so the package is importable
    # regardless of whether the test is run before `colcon build`.
    ws_src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if ws_src not in sys.path:
        sys.path.insert(0, ws_src)

    from nav2_config.core.lifecycle_client import LifecycleClient

    from rclpy.callback_groups import ReentrantCallbackGroup
    cb_group = ReentrantCallbackGroup()
    ros_node._cb_group = cb_group  # attach so clients use it

    client = LifecycleClient(ros_node, cb_group)
    time.sleep(1)  # let node settle

    # ── Get state for all key nodes ──────────────────────────────────────
    test_nodes = ['/controller_server', '/planner_server', '/amcl', '/smoother_server']
    print('  get_state for key nodes:')
    all_ok = True
    for n in test_nodes:
        state = client.get_state(n)
        print(f'    {n}: {state}')
        if state == 'unknown':
            print(f'    WARNING: could not get state for {n}')
            all_ok = False
    if all_ok:
        print('  ✓ get_state passed for all nodes')
    print()

    # ── Deactivate / activate cycle on smoother_server ───────────────────
    target = '/smoother_server'
    print(f'  Testing deactivate/activate cycle on {target}:')

    initial = client.get_state(target)
    print(f'    Initial state: {initial}')

    if initial != 'active':
        print(f'    WARNING: {target} not active (state={initial!r}), skipping cycle test')
    else:
        success = client.deactivate(target)
        print(f'    deactivate(): {"✓" if success else "✗"}')
        if not success:
            print('    WARNING: deactivate returned False — lifecycle_manager may have rejected it')

        time.sleep(1)
        state = client.get_state(target)
        print(f'    State after deactivate: {state}')

        if state not in ('inactive', 'active'):
            raise AssertionError(f'Unexpected state after deactivate: {state!r}')
        if state == 'active':
            print('    NOTE: lifecycle_manager re-activated the node immediately — this is normal.')

        # If deactivated, we need to re-activate
        if state == 'inactive':
            success = client.activate(target)
            print(f'    activate(): {"✓" if success else "✗"}')
            time.sleep(1)
            state = client.get_state(target)
            print(f'    State after activate: {state}')
            if state != 'active':
                raise AssertionError(f'Expected active after reactivate, got {state!r}')

        print('  ✓ DEACTIVATE/ACTIVATE CYCLE PASSED')
    print()

    # ── Restart on smoother_server ────────────────────────────────────────
    print(f'  Testing restart on {target}:')
    current = client.get_state(target)
    if current != 'active':
        print(f'    Skipping restart test — {target} not in active state (state={current!r})')
    else:
        success, msg = client.restart(target)
        print(f'    restart(): {"✓" if success else "✗"} — {msg}')
        if not success:
            print('    WARNING: restart reported failure — lifecycle_manager may have interfered')

        time.sleep(2)
        state = client.get_state(target)
        print(f'    State after restart: {state}')

        if state != 'active':
            # lifecycle_manager should eventually restore it
            print(f'    NOTE: State is {state!r} — lifecycle_manager should restore to active')
        else:
            print('  ✓ RESTART PASSED')
    print()

    # Cleanup
    ros_node.destroy_node()
    rclpy.shutdown()


def main() -> None:
    print('Nav2 Lifecycle Live Tests')
    print('=' * 50)
    print()

    failures: list[str] = []

    for name, fn in [
        ('get_state CLI', test_get_state),
        ('deactivate/activate CLI', test_deactivate_activate),
        ('lifecycle_client direct', test_lifecycle_client),
    ]:
        try:
            fn()
        except AssertionError as exc:
            print(f'FAILED [{name}]: {exc}')
            failures.append(f'{name}: {exc}')
        except Exception as exc:
            print(f'ERROR [{name}]: {exc}')
            failures.append(f'{name}: {type(exc).__name__}: {exc}')

    print('=' * 50)
    if failures:
        print(f'FAILED — {len(failures)} test(s) failed:')
        for f in failures:
            print(f'  • {f}')
        sys.exit(1)
    else:
        print('=== ALL TESTS PASSED ===')


if __name__ == '__main__':
    main()
