# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for namespace-sensitive node discovery functions.

All tests use pre-fetched node lists and mock rclpy.Node so no running ROS2
environment is required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Allow importing from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.core.node_discovery import (
    DiscoveredLifecycleManager,
    DiscoveredNav2Node,
    discover_lifecycle_managers,
    discover_nav2_nodes,
    infer_stack_namespace,
    path_basename,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_node() -> MagicMock:
    """Minimal mock rclpy Node — get_node_names_and_namespaces is never called
    in tests that pass nodes_and_ns directly."""
    return MagicMock()


# ---------------------------------------------------------------------------
# path_basename
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("full_path,expected", [
    # Root-namespace regular node
    ("/controller_server", "controller_server"),
    # Root-namespace self-namespaced costmap
    ("/local_costmap/local_costmap", "local_costmap"),
    # Namespaced regular node
    ("/robot1/planner_server", "planner_server"),
    # Namespaced self-namespaced costmap
    ("/robot1/local_costmap/local_costmap", "local_costmap"),
    # No leading slash (edge case)
    ("controller_server", "controller_server"),
    # Deep namespace
    ("/fleet/robot2/bt_navigator", "bt_navigator"),
    # Trailing slash should be stripped cleanly
    ("/robot1/controller_server/", "controller_server"),
])
def test_path_basename(full_path: str, expected: str) -> None:
    assert path_basename(full_path) == expected


# ---------------------------------------------------------------------------
# infer_stack_namespace — regular nodes
# ---------------------------------------------------------------------------


def test_infer_stack_namespace_root_regular_node() -> None:
    """Root-namespace regular node has stack namespace '/'."""
    assert infer_stack_namespace("/planner_server", "planner_server") == "/"


def test_infer_stack_namespace_namespaced_regular_node() -> None:
    """Single-level namespace is returned as the stack namespace."""
    assert infer_stack_namespace("/robot1/planner_server", "planner_server") == "/robot1"


def test_infer_stack_namespace_deep_namespace_regular_node() -> None:
    """Multi-level namespace is fully preserved."""
    assert infer_stack_namespace("/fleet/robot2/bt_navigator", "bt_navigator") == "/fleet/robot2"


# ---------------------------------------------------------------------------
# infer_stack_namespace — self-namespaced costmap nodes
# ---------------------------------------------------------------------------


def test_infer_stack_namespace_root_local_costmap() -> None:
    """Root-namespace local_costmap strips two trailing components."""
    assert infer_stack_namespace("/local_costmap/local_costmap", "local_costmap") == "/"


def test_infer_stack_namespace_root_global_costmap() -> None:
    """Root-namespace global_costmap strips two trailing components."""
    assert infer_stack_namespace("/global_costmap/global_costmap", "global_costmap") == "/"


def test_infer_stack_namespace_namespaced_local_costmap() -> None:
    """Namespaced local_costmap strips both the node and its self-namespace."""
    result = infer_stack_namespace("/robot1/local_costmap/local_costmap", "local_costmap")
    assert result == "/robot1"


def test_infer_stack_namespace_namespaced_global_costmap() -> None:
    """Namespaced global_costmap strips both the node and its self-namespace."""
    result = infer_stack_namespace("/robot1/global_costmap/global_costmap", "global_costmap")
    assert result == "/robot1"


# ---------------------------------------------------------------------------
# discover_nav2_nodes — basic cases
# ---------------------------------------------------------------------------


def test_discover_nav2_nodes_empty_graph() -> None:
    """Empty node list returns empty dict."""
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=[])
    assert result == {}


def test_discover_nav2_nodes_non_nav2_nodes_ignored() -> None:
    """Nodes whose basenames are not in NAV2_NODE_SPECS are skipped."""
    nodes = [("some_other_node", "/"), ("rviz2", "/"), ("my_custom_node", "/robot1")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)
    assert result == {}


def test_discover_nav2_nodes_root_namespace_regular_node() -> None:
    """A regular Nav2 node in the root namespace is discovered correctly."""
    nodes = [("controller_server", "/")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert "/controller_server" in result
    node = result["/controller_server"]
    assert isinstance(node, DiscoveredNav2Node)
    assert node.full_path == "/controller_server"
    assert node.basename == "controller_server"
    assert node.ros_namespace == "/"
    assert node.stack_namespace == "/"
    assert node.display_name == "Controller Server"


def test_discover_nav2_nodes_namespaced_single_node() -> None:
    """A namespaced regular node is discovered with the correct stack namespace."""
    nodes = [("controller_server", "/robot1")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert "/robot1/controller_server" in result
    node = result["/robot1/controller_server"]
    assert node.full_path == "/robot1/controller_server"
    assert node.basename == "controller_server"
    assert node.ros_namespace == "/robot1"
    assert node.stack_namespace == "/robot1"


# ---------------------------------------------------------------------------
# discover_nav2_nodes — self-namespaced costmap nodes
# ---------------------------------------------------------------------------


def test_discover_nav2_nodes_root_local_costmap() -> None:
    """local_costmap in root namespace: ROS reports name=local_costmap, ns=/local_costmap."""
    nodes = [("local_costmap", "/local_costmap")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert "/local_costmap/local_costmap" in result
    node = result["/local_costmap/local_costmap"]
    assert node.basename == "local_costmap"
    assert node.stack_namespace == "/"
    assert node.display_name == "Local Costmap"


def test_discover_nav2_nodes_namespaced_local_costmap() -> None:
    """Namespaced local_costmap is discovered and its stack namespace is inferred correctly."""
    nodes = [("local_costmap", "/robot1/local_costmap")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert "/robot1/local_costmap/local_costmap" in result
    node = result["/robot1/local_costmap/local_costmap"]
    assert node.stack_namespace == "/robot1"


def test_discover_nav2_nodes_costmap_wrong_namespace_excluded() -> None:
    """A node named local_costmap whose ROS namespace does not end with /local_costmap
    is NOT included — it could be an unrelated node with the same basename."""
    nodes = [("local_costmap", "/some_other_ns")]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)
    assert result == {}


# ---------------------------------------------------------------------------
# discover_nav2_nodes — multi-robot (same basenames, different namespaces)
# ---------------------------------------------------------------------------


def test_discover_nav2_nodes_multi_robot_regular_nodes() -> None:
    """Two robots with the same node basenames are both discovered under separate paths."""
    nodes = [
        ("controller_server", "/robot1"),
        ("controller_server", "/robot2"),
        ("planner_server", "/robot1"),
        ("planner_server", "/robot2"),
    ]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert len(result) == 4
    assert "/robot1/controller_server" in result
    assert "/robot2/controller_server" in result
    assert "/robot1/planner_server" in result
    assert "/robot2/planner_server" in result

    r1_ctrl = result["/robot1/controller_server"]
    r2_ctrl = result["/robot2/controller_server"]
    assert r1_ctrl.stack_namespace == "/robot1"
    assert r2_ctrl.stack_namespace == "/robot2"


def test_discover_nav2_nodes_multi_robot_costmaps() -> None:
    """Two robots each with local_costmap are both discovered correctly."""
    nodes = [
        ("local_costmap", "/robot1/local_costmap"),
        ("local_costmap", "/robot2/local_costmap"),
    ]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert len(result) == 2
    assert "/robot1/local_costmap/local_costmap" in result
    assert "/robot2/local_costmap/local_costmap" in result

    assert result["/robot1/local_costmap/local_costmap"].stack_namespace == "/robot1"
    assert result["/robot2/local_costmap/local_costmap"].stack_namespace == "/robot2"


def test_discover_nav2_nodes_mixed_root_and_namespaced() -> None:
    """Nodes from multiple stacks (root + namespaced) coexist without conflict."""
    nodes = [
        ("controller_server", "/"),          # root stack
        ("controller_server", "/robot1"),     # /robot1 stack
        ("planner_server", "/"),
    ]
    result = discover_nav2_nodes(_mock_node(), nodes_and_ns=nodes)

    assert len(result) == 3
    assert "/controller_server" in result
    assert "/robot1/controller_server" in result
    assert "/planner_server" in result


# ---------------------------------------------------------------------------
# discover_nav2_nodes — nodes_and_ns fetched from the mock node
# ---------------------------------------------------------------------------


def test_discover_nav2_nodes_uses_node_when_no_list_provided() -> None:
    """When nodes_and_ns is None, get_node_names_and_namespaces() is called on the node."""
    mock = _mock_node()
    mock.get_node_names_and_namespaces.return_value = [("amcl", "/")]

    result = discover_nav2_nodes(mock)  # no nodes_and_ns kwarg

    mock.get_node_names_and_namespaces.assert_called_once()
    assert "/amcl" in result


# ---------------------------------------------------------------------------
# discover_lifecycle_managers
# ---------------------------------------------------------------------------


def test_discover_lifecycle_managers_empty() -> None:
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=[])
    assert result == {}


def test_discover_lifecycle_managers_root_namespace() -> None:
    """A root-namespace lifecycle manager is found and stack_namespace is '/'."""
    nodes = [("lifecycle_manager_navigation", "/")]
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=nodes)

    assert "/lifecycle_manager_navigation" in result
    mgr = result["/lifecycle_manager_navigation"]
    assert isinstance(mgr, DiscoveredLifecycleManager)
    assert mgr.full_path == "/lifecycle_manager_navigation"
    assert mgr.basename == "lifecycle_manager_navigation"
    assert mgr.ros_namespace == "/"
    assert mgr.stack_namespace == "/"


def test_discover_lifecycle_managers_namespaced() -> None:
    """A namespaced lifecycle manager has the correct stack namespace."""
    nodes = [("lifecycle_manager_navigation", "/robot1")]
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=nodes)

    assert "/robot1/lifecycle_manager_navigation" in result
    mgr = result["/robot1/lifecycle_manager_navigation"]
    assert mgr.full_path == "/robot1/lifecycle_manager_navigation"
    assert mgr.ros_namespace == "/robot1"
    assert mgr.stack_namespace == "/robot1"


def test_discover_lifecycle_managers_custom_name() -> None:
    """Custom lifecycle manager names that start with 'lifecycle_manager' are matched."""
    nodes = [("lifecycle_manager_map", "/")]
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=nodes)
    assert "/lifecycle_manager_map" in result


def test_discover_lifecycle_managers_multiple_stacks() -> None:
    """All lifecycle managers across multiple robot namespaces are discovered."""
    nodes = [
        ("lifecycle_manager_navigation", "/robot1"),
        ("lifecycle_manager_navigation", "/robot2"),
        ("lifecycle_manager_localization", "/robot1"),
    ]
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=nodes)

    assert len(result) == 3
    assert "/robot1/lifecycle_manager_navigation" in result
    assert "/robot2/lifecycle_manager_navigation" in result
    assert "/robot1/lifecycle_manager_localization" in result


def test_discover_lifecycle_managers_non_lifecycle_nodes_excluded() -> None:
    """Nodes not starting with 'lifecycle_manager' are not included."""
    nodes = [
        ("controller_server", "/"),
        ("lifecycle_manager_navigation", "/"),
        ("my_node", "/robot1"),
    ]
    result = discover_lifecycle_managers(_mock_node(), nodes_and_ns=nodes)
    assert len(result) == 1
    assert "/lifecycle_manager_navigation" in result


def test_discover_lifecycle_managers_calls_node_when_no_list() -> None:
    """When nodes_and_ns is None, get_node_names_and_namespaces() is called."""
    mock = _mock_node()
    mock.get_node_names_and_namespaces.return_value = [("lifecycle_manager_navigation", "/")]

    result = discover_lifecycle_managers(mock)

    mock.get_node_names_and_namespaces.assert_called_once()
    assert "/lifecycle_manager_navigation" in result
