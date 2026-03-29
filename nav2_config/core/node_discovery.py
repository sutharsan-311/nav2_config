# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Nav2 node discovery: checks which Nav2 nodes are currently running."""

from __future__ import annotations

from rclpy.node import Node


# Ordered mapping of ROS2 node paths → human-readable display names.
# Order here determines the display order in the node panel.
NAV2_NODES: dict[str, str] = {
    "/amcl": "AMCL",
    "/controller_server": "Controller Server",
    "/planner_server": "Planner Server",
    "/bt_navigator": "BT Navigator",
    "/local_costmap/local_costmap": "Local Costmap",
    "/global_costmap/global_costmap": "Global Costmap",
    "/smoother_server": "Smoother Server",
    "/velocity_smoother": "Velocity Smoother",
    "/behavior_server": "Behavior Server",
    "/waypoint_follower": "Waypoint Follower",
    "/map_server": "Map Server",
}


def discover_nav2_nodes(
    node: Node,
    nodes_and_ns: list[tuple[str, str]] | None = None,
) -> dict[str, bool]:
    """Discover which Nav2 nodes are currently running.

    Calls ``node.get_node_names_and_namespaces()`` to enumerate all running
    ROS2 nodes, then checks each expected Nav2 node path against the result.

    ROS2 represents a node's location as a (name, namespace) pair:
      - ``/amcl``                       → name='amcl',          namespace='/'
      - ``/local_costmap/local_costmap`` → name='local_costmap', namespace='/local_costmap'

    Args:
        node: The rclpy Node used to call the ROS2 graph API.
        nodes_and_ns: Pre-fetched result of ``node.get_node_names_and_namespaces()``.
            If *None*, the call is made internally.  Pass a cached result to
            avoid a redundant ROS2 graph query on the same tick.

    Returns:
        dict mapping each :data:`NAV2_NODES` key to ``True`` (running) or
        ``False`` (not found).
    """
    if nodes_and_ns is None:
        nodes_and_ns = node.get_node_names_and_namespaces()

    running: set[str] = set()
    for name, ns in nodes_and_ns:
        if ns == '/':
            full_path = '/' + name
        else:
            full_path = ns + '/' + name
        running.add(full_path)

    return {nav_node: (nav_node in running) for nav_node in NAV2_NODES}


#: Known Nav2 lifecycle manager node paths → human-readable scope names.
LIFECYCLE_MANAGERS: dict[str, str] = {
    '/lifecycle_manager_navigation': 'Navigation',
    '/lifecycle_manager_localization': 'Localization',
}


def discover_lifecycle_managers(
    node: Node,
    nodes_and_ns: list[tuple[str, str]] | None = None,
) -> dict[str, bool]:
    """Check which Nav2 lifecycle managers are currently running.

    Args:
        node: The rclpy Node used to call the ROS2 graph API.
        nodes_and_ns: Pre-fetched result of ``node.get_node_names_and_namespaces()``.
            If *None*, the call is made internally.

    Returns:
        dict mapping each :data:`LIFECYCLE_MANAGERS` key to ``True`` (running)
        or ``False`` (not found).
    """
    if nodes_and_ns is None:
        nodes_and_ns = node.get_node_names_and_namespaces()
    running: set[str] = set()
    for name, ns in nodes_and_ns:
        full_path = '/' + name if ns == '/' else ns + '/' + name
        running.add(full_path)
    return {mgr: (mgr in running) for mgr in LIFECYCLE_MANAGERS}
