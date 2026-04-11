# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Post-set action tests: namespace-aware service path resolution (mock-based) +
integration tests against live TurtleBot3 sim (skipped without live Nav2 stack)."""

import os
import subprocess
import time
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run(cmd, timeout=30):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def restore(cmd, timeout=30):
    """Run a cleanup/restore command; silently ignore failures."""
    try:
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Mock-based unit tests: namespace-aware service path resolution
# No live Nav2 stack required.
# ---------------------------------------------------------------------------

class TestNamespaceServicePathResolution:
    """Verify that Nav2ServiceCaller resolves service paths using the correct
    namespace prefix derived from the node_path argument."""

    def _make_caller(self):
        """Return a Nav2ServiceCaller with a fully-mocked rclpy node."""
        mock_node = MagicMock()
        mock_node.get_logger.return_value = MagicMock()
        mock_cb_group = MagicMock()

        # create_client returns a mock client that always reports service available
        mock_client = MagicMock()
        mock_client.wait_for_service.return_value = True

        # call_async returns a future; add_done_callback fires immediately with result
        def _call_async_side_effect(request):
            fut = MagicMock()
            fut.result.return_value = MagicMock()  # non-None = success

            def _add_done_cb(cb):
                cb(fut)

            fut.add_done_callback.side_effect = _add_done_cb
            return fut

        mock_client.call_async.side_effect = _call_async_side_effect
        mock_node.create_client.return_value = mock_client

        from nav2_config.core.service_caller import Nav2ServiceCaller
        sc = Nav2ServiceCaller(mock_node, mock_cb_group)
        return sc, mock_node, mock_client

    # ------------------------------------------------------------------
    # clear_costmaps: root namespace
    # ------------------------------------------------------------------

    def test_clear_costmaps_root_namespace_service_paths(self):
        """clear_costmaps('/controller_server') resolves to root-namespace paths."""
        sc, mock_node, _ = self._make_caller()

        try:
            sc.clear_costmaps("/controller_server")
        except Exception:
            pass  # we only care about which services were created

        created_names = [
            call.args[1] if len(call.args) >= 2 else call.kwargs.get("srv_name", "")
            for call in mock_node.create_client.call_args_list
        ]
        # Root namespace: no /robot1/ prefix
        assert any("/global_costmap/clear_entirely_global_costmap" == n for n in created_names), \
            f"Expected root-namespace global costmap service, got: {created_names}"
        assert any("/local_costmap/clear_entirely_local_costmap" == n for n in created_names), \
            f"Expected root-namespace local costmap service, got: {created_names}"

    # ------------------------------------------------------------------
    # clear_costmaps: /robot1 namespace
    # ------------------------------------------------------------------

    def test_clear_costmaps_robot1_namespace_service_paths(self):
        """clear_costmaps('/robot1/controller_server') resolves paths under /robot1/."""
        sc, mock_node, _ = self._make_caller()

        try:
            sc.clear_costmaps("/robot1/controller_server")
        except Exception:
            pass

        created_names = [
            call.args[1] if len(call.args) >= 2 else call.kwargs.get("srv_name", "")
            for call in mock_node.create_client.call_args_list
        ]
        assert any("/robot1/global_costmap/clear_entirely_global_costmap" == n for n in created_names), \
            f"Expected /robot1/-prefixed global costmap service, got: {created_names}"
        assert any("/robot1/local_costmap/clear_entirely_local_costmap" == n for n in created_names), \
            f"Expected /robot1/-prefixed local costmap service, got: {created_names}"

    # ------------------------------------------------------------------
    # nomotion_update: root namespace
    # ------------------------------------------------------------------

    def test_nomotion_update_root_namespace_service_path(self):
        """nomotion_update('/amcl') resolves to /request_nomotion_update."""
        sc, mock_node, _ = self._make_caller()

        try:
            sc.nomotion_update("/amcl")
        except Exception:
            pass

        created_names = [
            call.args[1] if len(call.args) >= 2 else call.kwargs.get("srv_name", "")
            for call in mock_node.create_client.call_args_list
        ]
        assert any("/request_nomotion_update" == n for n in created_names), \
            f"Expected /request_nomotion_update, got: {created_names}"
        # Must NOT have a robot namespace prefix
        assert not any(n.startswith("/robot") for n in created_names), \
            f"Root-namespace call should not have /robotN prefix: {created_names}"

    # ------------------------------------------------------------------
    # nomotion_update: /robot1 namespace
    # ------------------------------------------------------------------

    def test_nomotion_update_robot1_namespace_service_path(self):
        """nomotion_update('/robot1/amcl') resolves to /robot1/request_nomotion_update."""
        sc, mock_node, _ = self._make_caller()

        try:
            sc.nomotion_update("/robot1/amcl")
        except Exception:
            pass

        created_names = [
            call.args[1] if len(call.args) >= 2 else call.kwargs.get("srv_name", "")
            for call in mock_node.create_client.call_args_list
        ]
        assert any("/robot1/request_nomotion_update" == n for n in created_names), \
            f"Expected /robot1/request_nomotion_update, got: {created_names}"

    # ------------------------------------------------------------------
    # clear_costmaps: /robot2 namespace (different robot)
    # ------------------------------------------------------------------

    def test_clear_costmaps_robot2_namespace_service_paths(self):
        """clear_costmaps('/robot2/planner_server') resolves paths under /robot2/."""
        sc, mock_node, _ = self._make_caller()

        try:
            sc.clear_costmaps("/robot2/planner_server")
        except Exception:
            pass

        created_names = [
            call.args[1] if len(call.args) >= 2 else call.kwargs.get("srv_name", "")
            for call in mock_node.create_client.call_args_list
        ]
        assert any("/robot2/" in n for n in created_names), \
            f"Expected /robot2/-prefixed services, got: {created_names}"
        assert not any("/robot1/" in n for n in created_names), \
            f"robot2 call must not touch robot1 services: {created_names}"


# ---------------------------------------------------------------------------
# Mock-based unit test: schema entry post_set_action lookup
# No live Nav2 stack required.
# ---------------------------------------------------------------------------

class TestFindSchemaEntry:
    """Verify _find_schema_entry returns the correct post_set_action values
    from the schema for known Nav2 nodes/params."""

    def _make_schema_node(self):
        from nav2_config.types.params import load_schema
        from nav2_config.node import Nav2ConfigNode
        schema = load_schema()
        obj = Nav2ConfigNode.__new__(Nav2ConfigNode)
        obj._schema = schema
        return obj

    def test_inflation_radius_post_set_action(self):
        obj = self._make_schema_node()
        entry = obj._find_schema_entry(
            "/local_costmap/local_costmap",
            "inflation_layer.inflation_radius",
        )
        assert entry is not None, "_find_schema_entry returned None for inflation_radius"
        assert entry.post_set_action == "clear_costmaps", \
            f"Expected 'clear_costmaps', got {entry.post_set_action!r}"

    def test_amcl_max_particles_post_set_action(self):
        obj = self._make_schema_node()
        entry = obj._find_schema_entry("/amcl", "max_particles")
        assert entry is not None, "_find_schema_entry returned None for amcl/max_particles"
        assert entry.post_set_action == "nomotion_update", \
            f"Expected 'nomotion_update', got {entry.post_set_action!r}"

    def test_controller_frequency_no_post_set_action(self):
        obj = self._make_schema_node()
        entry = obj._find_schema_entry("/controller_server", "controller_frequency")
        assert entry is not None, "_find_schema_entry returned None for controller_frequency"
        assert entry.post_set_action is None, \
            f"Expected None post_set_action, got {entry.post_set_action!r}"


# ---------------------------------------------------------------------------
# CLI-level integration tests — require a live Nav2 stack
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires live Nav2 stack")
def test_clear_costmaps():
    """Test: change inflation_radius → costmaps auto-clear."""
    print("=== TEST: clear_costmaps (inflation_radius) ===")

    node = '/local_costmap/local_costmap'
    param = 'inflation_layer.inflation_radius'

    out, _, _ = run(f"ros2 param get {node} {param}")
    print(f"  Original: {out}")

    out, err, rc = run(f"ros2 param set {node} {param} 0.8")
    print(f"  Set to 0.8: {out} (rc={rc})")
    assert rc == 0, f"param set failed: {err}"

    out, err, rc = run(
        "ros2 service call /local_costmap/clear_entirely_local_costmap "
        "nav2_msgs/srv/ClearEntireCostmap '{}'"
    )
    print(f"  Clear local costmap: rc={rc}")
    assert rc == 0, f"clear local costmap failed: {err}"

    out, err, rc = run(
        "ros2 service call /global_costmap/clear_entirely_global_costmap "
        "nav2_msgs/srv/ClearEntireCostmap '{}'"
    )
    print(f"  Clear global costmap: rc={rc}")
    assert rc == 0, f"clear global costmap failed: {err}"

    out, _, _ = run(f"ros2 param get {node} {param}")
    print(f"  Verify: {out}")
    assert "0.8" in out, f"param value not updated: {out}"

    restore(f"ros2 param set {node} {param} 0.55")
    restore("ros2 service call /local_costmap/clear_entirely_local_costmap nav2_msgs/srv/ClearEntireCostmap '{}'")
    restore("ros2 service call /global_costmap/clear_entirely_global_costmap nav2_msgs/srv/ClearEntireCostmap '{}'")
    print("  Restored to 0.55 ✓")
    print()


@pytest.mark.skip(reason="requires live Nav2 stack")
def test_clear_costmaps_cost_scaling():
    """Test: change cost_scaling_factor → costmaps auto-clear."""
    print("=== TEST: clear_costmaps (cost_scaling_factor) ===")

    node = '/local_costmap/local_costmap'
    param = 'inflation_layer.cost_scaling_factor'

    out, _, _ = run(f"ros2 param get {node} {param}")
    print(f"  Original: {out}")

    out, err, rc = run(f"ros2 param set {node} {param} 5.0")
    print(f"  Set to 5.0: {out} (rc={rc})")
    assert rc == 0, f"param set failed: {err}"

    out, err, rc = run(
        "ros2 service call /local_costmap/clear_entirely_local_costmap "
        "nav2_msgs/srv/ClearEntireCostmap '{}'"
    )
    print(f"  Clear costmap: rc={rc}")
    assert rc == 0, f"clear costmap failed: {err}"

    out, _, _ = run(f"ros2 param get {node} {param}")
    print(f"  Verify: {out}")
    assert "5.0" in out, f"param value not updated: {out}"

    restore(f"ros2 param set {node} {param} 3.0")
    restore("ros2 service call /local_costmap/clear_entirely_local_costmap nav2_msgs/srv/ClearEntireCostmap '{}'")
    print("  Restored ✓")
    print()


@pytest.mark.skip(reason="requires live Nav2 stack")
def test_load_map():
    """Test: load_map service fires with a valid map file."""
    print("=== TEST: load_map (yaml_filename) ===")

    out, _, _ = run("ls /opt/ros/humble/share/nav2_bringup/maps/")
    print(f"  Available maps: {out}")

    out, _, _ = run("ros2 param get /map_server yaml_filename")
    print(f"  Current map: {out}")

    map_path = '/opt/ros/humble/share/nav2_bringup/maps/turtlebot3_world.yaml'
    out, err, rc = run(
        f"ros2 service call /map_server/load_map nav2_msgs/srv/LoadMap "
        f"\"{{map_url: '{map_path}'}}\"",
        timeout=45,
    )
    print(f"  load_map result (rc={rc}): {out[:200]}")
    assert rc == 0, f"load_map CLI call failed: {err}"
    # CLI response uses repr format: result=0
    assert "result=0" in out, f"load_map returned non-zero result: {out[:400]}"

    print()


@pytest.mark.skip(reason="requires live Nav2 stack")
def test_nomotion_update():
    """Test: change AMCL param → nomotion_update fires."""
    print("=== TEST: nomotion_update (AMCL max_particles) ===")

    out, _, _ = run("ros2 param get /amcl max_particles")
    print(f"  Original: {out}")

    out, err, rc = run("ros2 param set /amcl max_particles 3000")
    print(f"  Set to 3000: {out} (rc={rc})")
    assert rc == 0, f"param set failed: {err}"

    out, err, rc = run("ros2 service call /request_nomotion_update std_srvs/srv/Empty '{}'")
    print(f"  nomotion_update: rc={rc}")
    assert rc == 0, f"nomotion_update failed: {err}"

    out, _, _ = run("ros2 param get /amcl max_particles")
    print(f"  Verify: {out}")
    assert "3000" in out, f"param value not updated: {out}"

    restore("ros2 param set /amcl max_particles 2000")
    print("  Restored to 2000 ✓")
    print()


@pytest.mark.skip(reason="requires live Nav2 stack")
def test_nomotion_alpha():
    """Test: change AMCL alpha1 → nomotion_update fires."""
    print("=== TEST: nomotion_update (AMCL alpha1) ===")

    out, _, _ = run("ros2 param get /amcl alpha1")
    print(f"  Original: {out}")

    out, err, rc = run("ros2 param set /amcl alpha1 0.3")
    print(f"  Set to 0.3: {out} (rc={rc})")
    assert rc == 0, f"param set failed: {err}"

    out, err, rc = run("ros2 service call /request_nomotion_update std_srvs/srv/Empty '{}'")
    print(f"  nomotion_update: rc={rc}")
    assert rc == 0, f"nomotion_update failed: {err}"

    out, _, _ = run("ros2 param get /amcl alpha1")
    print(f"  Verify: {out}")
    assert "0.3" in out, f"param value not updated: {out}"

    restore("ros2 param set /amcl alpha1 0.2")
    print("  Restored to 0.2 ✓")
    print()


@pytest.mark.skip(reason="requires live Nav2 stack")
def test_no_action_needed():
    """Test: change controller_frequency → no service needed, immediate effect."""
    print("=== TEST: no action (controller_frequency) ===")

    out, _, _ = run("ros2 param get /controller_server controller_frequency")
    print(f"  Original: {out}")

    out, err, rc = run("ros2 param set /controller_server controller_frequency 25.0")
    print(f"  Set to 25.0: {out} (rc={rc})")
    assert rc == 0, f"param set failed: {err}"

    out, _, _ = run("ros2 param get /controller_server controller_frequency")
    print(f"  Verify: {out}")
    assert "25.0" in out, f"param value not updated: {out}"

    restore("ros2 param set /controller_server controller_frequency 20.0")
    print("  Restored to 20.0 ✓")
    print()


# ---------------------------------------------------------------------------
# Python code integration test — requires live Nav2 stack
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires live Nav2 stack")
def test_nav2_param_client_with_actions():
    """Test the full flow through Nav2ParamClient + Nav2ServiceCaller."""
    print("=== TEST: Full flow via nav2_config code ===")

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.callback_groups import ReentrantCallbackGroup
    import threading

    rclpy.init()
    node = rclpy.create_node('post_action_test_node')
    cb_group = ReentrantCallbackGroup()
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()
    time.sleep(1.0)

    from nav2_config.core.param_client import Nav2ParamClient
    from nav2_config.core.service_caller import Nav2ServiceCaller

    pc = Nav2ParamClient(node, cb_group)
    sc = Nav2ServiceCaller(node, cb_group)
    time.sleep(0.5)

    # ------------------------------------------------------------------
    # Test 1: Set inflation_radius + clear_costmaps
    # ------------------------------------------------------------------
    print("\n  Test 1: inflation_radius + clear_costmaps")
    original = pc.get_params('/local_costmap/local_costmap', ['inflation_layer.inflation_radius'])
    print(f"    Original: {original}")

    success, reason = pc.set_param(
        '/local_costmap/local_costmap', 'inflation_layer.inflation_radius', 0.8, 'double'
    )
    print(f"    Set to 0.8: {'OK' if success else f'FAIL ({reason})'}")
    assert success, f"set_param failed: {reason}"

    clear_ok = sc.clear_costmaps("/local_costmap/local_costmap")
    print(f"    Clear costmaps: {'OK' if clear_ok else 'FAIL'}")
    assert clear_ok, "clear_costmaps() returned False"

    verify = pc.get_params('/local_costmap/local_costmap', ['inflation_layer.inflation_radius'])
    print(f"    Verify: {verify}")
    assert abs(verify.get('inflation_layer.inflation_radius', 0) - 0.8) < 0.001, \
        f"inflation_radius not updated: {verify}"

    pc.set_param('/local_costmap/local_costmap', 'inflation_layer.inflation_radius', 0.55, 'double')
    sc.clear_costmaps("/local_costmap/local_costmap")
    print("    Restored ✓")

    # ------------------------------------------------------------------
    # Test 2: Set max_particles + nomotion_update
    # ------------------------------------------------------------------
    print("\n  Test 2: max_particles + nomotion_update")
    success, reason = pc.set_param('/amcl', 'max_particles', 3000, 'int')
    print(f"    Set to 3000: {'OK' if success else f'FAIL ({reason})'}")
    assert success, f"set_param failed: {reason}"

    nomotion_ok = sc.nomotion_update("/amcl")
    print(f"    Nomotion update: {'OK' if nomotion_ok else 'FAIL'}")
    assert nomotion_ok, "nomotion_update() returned False"

    verify = pc.get_params('/amcl', ['max_particles'])
    print(f"    Verify: {verify}")
    assert verify.get('max_particles') == 3000, f"max_particles not updated: {verify}"

    pc.set_param('/amcl', 'max_particles', 2000, 'int')
    print("    Restored ✓")

    # ------------------------------------------------------------------
    # Test 3: load_map
    # ------------------------------------------------------------------
    print("\n  Test 3: load_map")
    map_path = '/opt/ros/humble/share/nav2_bringup/maps/turtlebot3_world.yaml'
    sc.CALL_TIMEOUT = 20.0  # load_map can take a moment
    map_ok, code = sc.load_map(map_path, "/map_server")
    print(f"    Load map: {'OK' if map_ok else 'FAIL'} (code={code})")
    assert map_ok, f"load_map() returned False with code {code}"

    node.destroy_node()
    rclpy.shutdown()
    print()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("Nav2 Post-Set Action Tests\n")
    print("=" * 60)
    print("Phase 1: CLI-level service tests")
    print("=" * 60)
    failures = []

    for fn in [
        test_clear_costmaps,
        test_clear_costmaps_cost_scaling,
        test_load_map,
        test_nomotion_update,
        test_nomotion_alpha,
        test_no_action_needed,
    ]:
        try:
            fn()
        except AssertionError as e:
            print(f"  FAIL: {e}\n")
            failures.append((fn.__name__, str(e)))
        except Exception as e:
            print(f"  ERROR: {e}\n")
            failures.append((fn.__name__, str(e)))

    print("=" * 60)
    print("Phase 2: Python code integration tests")
    print("=" * 60)
    try:
        test_nav2_param_client_with_actions()
    except AssertionError as e:
        print(f"  FAIL: {e}\n")
        failures.append(('test_nav2_param_client_with_actions', str(e)))
    except Exception as e:
        import traceback
        traceback.print_exc()
        failures.append(('test_nav2_param_client_with_actions', str(e)))

    print("=" * 60)
    if failures:
        print(f"FAILED {len(failures)} test(s):")
        for name, reason in failures:
            print(f"  - {name}: {reason}")
        sys.exit(1)
    else:
        print("=== ALL TESTS PASSED ===")
