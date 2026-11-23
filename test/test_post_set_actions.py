# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Post-set action tests: namespace-aware service path resolution (mock-based).

The live-stack versions of these checks are in test/sim/test_actions_history.py.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


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
