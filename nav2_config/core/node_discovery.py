# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Nav2 node discovery: checks which Nav2 nodes are currently running."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass

from rclpy.node import Node


# ---------------------------------------------------------------------------
# Spec dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Nav2NodeSpec:
    """Static descriptor for a known Nav2 node."""

    display_name: str
    self_namespaced: bool = False


@dataclass(frozen=True)
class DiscoveredNav2Node:
    """A Nav2 node found on the live ROS2 graph."""

    full_path: str       # e.g. '/robot1/controller_server'
    basename: str        # e.g. 'controller_server'
    ros_namespace: str   # ROS2 namespace, e.g. '/robot1'
    stack_namespace: str # Stack root, e.g. '/robot1'
    display_name: str    # Human-readable, e.g. 'Controller Server'


@dataclass(frozen=True)
class DiscoveredLifecycleManager:
    """A lifecycle_manager node found on the live ROS2 graph."""

    full_path: str       # e.g. '/lifecycle_manager_navigation'
    basename: str        # e.g. 'lifecycle_manager_navigation'
    ros_namespace: str   # ROS2 namespace, e.g. '/'
    stack_namespace: str # Stack root, e.g. '/'


# ---------------------------------------------------------------------------
# Ordered node spec registry
# ---------------------------------------------------------------------------


NAV2_NODE_SPECS: OrderedDict[str, Nav2NodeSpec] = OrderedDict([
    ("amcl",              Nav2NodeSpec("AMCL")),
    ("controller_server", Nav2NodeSpec("Controller Server")),
    ("planner_server",    Nav2NodeSpec("Planner Server")),
    ("bt_navigator",      Nav2NodeSpec("BT Navigator")),
    ("local_costmap",     Nav2NodeSpec("Local Costmap", self_namespaced=True)),
    ("global_costmap",    Nav2NodeSpec("Global Costmap", self_namespaced=True)),
    ("smoother_server",   Nav2NodeSpec("Smoother Server")),
    ("velocity_smoother", Nav2NodeSpec("Velocity Smoother")),
    ("behavior_server",   Nav2NodeSpec("Behavior Server")),
    ("waypoint_follower", Nav2NodeSpec("Waypoint Follower")),
    ("map_server",        Nav2NodeSpec("Map Server")),
])


# Backward-compat alias: maps root-namespace full path → display name.
# GUI code that iterates NAV2_NODES.items() for (path, display_name) continues to work.
NAV2_NODES: dict[str, str] = {
    (f"/{bn}/{bn}" if spec.self_namespaced else f"/{bn}"): spec.display_name
    for bn, spec in NAV2_NODE_SPECS.items()
}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def path_basename(full_path: str) -> str:
    """Return the last component of a ROS2 node path.

    Examples::
        path_basename("/controller_server")           -> "controller_server"
        path_basename("/local_costmap/local_costmap") -> "local_costmap"
        path_basename("/robot1/planner_server")       -> "planner_server"
    """
    return full_path.rstrip('/').rsplit('/', 1)[-1]


def infer_stack_namespace(full_path: str, basename: str) -> str:
    """Infer the stack namespace (the prefix before node-specific path components).

    Self-namespaced nodes (e.g. ``local_costmap/local_costmap``) have two
    trailing components stripped.  Regular nodes have one stripped.

    Examples::
        infer_stack_namespace("/planner_server", "planner_server")                  -> "/"
        infer_stack_namespace("/robot1/planner_server", "planner_server")           -> "/robot1"
        infer_stack_namespace("/local_costmap/local_costmap", "local_costmap")      -> "/"
        infer_stack_namespace("/robot1/local_costmap/local_costmap", "local_costmap") -> "/robot1"
    """
    path = full_path.rstrip('/')
    # Strip the node name (last component).
    ns = path.rsplit('/', 1)[0] or '/'
    # Self-namespaced nodes carry an extra namespace component equal to the basename.
    spec = NAV2_NODE_SPECS.get(basename)
    if spec and spec.self_namespaced:
        ns = ns.rsplit('/', 1)[0] or '/'
    return ns or '/'


def join_ros_path(namespace: str, relative: str) -> str:
    """Join a ROS2 namespace and a relative node path fragment.

    Examples::
        join_ros_path("/", "amcl")                              -> "/amcl"
        join_ros_path("/robot1", "controller_server")           -> "/robot1/controller_server"
        join_ros_path("/robot1", "local_costmap/local_costmap") -> "/robot1/local_costmap/local_costmap"
    """
    if namespace == '/':
        return '/' + relative
    return namespace.rstrip('/') + '/' + relative


# ---------------------------------------------------------------------------
# Discovery functions
# ---------------------------------------------------------------------------


def discover_nav2_nodes(
    node: Node,
    nodes_and_ns: list[tuple[str, str]] | None = None,
) -> dict[str, DiscoveredNav2Node]:
    """Discover running Nav2 nodes by matching on basename.

    Namespace-agnostic: nodes are found wherever they run (root, ``/robot1/``,
    etc.).  For self-namespaced nodes (costmaps) the namespace is validated to
    end with the basename so that an unrelated node named ``local_costmap`` in
    a non-matching namespace is not mistakenly included.

    When multiple nodes share the same basename (e.g. multi-robot), the first
    one encountered is returned.  Multi-robot support is a later stage.

    Args:
        node: The rclpy Node used to call the ROS2 graph API.
        nodes_and_ns: Pre-fetched result of ``node.get_node_names_and_namespaces()``.
            Pass a cached result to avoid a redundant graph query.

    Returns:
        dict mapping basename → :class:`DiscoveredNav2Node` for each found node.
        Only nodes that are actually running are included (no False entries).
    """
    if nodes_and_ns is None:
        nodes_and_ns = node.get_node_names_and_namespaces()

    result: dict[str, DiscoveredNav2Node] = {}
    for name, ns in nodes_and_ns:
        full_path = '/' + name if ns == '/' else ns + '/' + name
        basename = path_basename(full_path)

        if basename not in NAV2_NODE_SPECS or basename in result:
            continue

        spec = NAV2_NODE_SPECS[basename]
        if spec.self_namespaced:
            # Namespace must end with /<basename> (e.g. /local_costmap or /robot1/local_costmap).
            if not (ns == f'/{basename}' or ns.endswith(f'/{basename}')):
                continue

        result[basename] = DiscoveredNav2Node(
            full_path=full_path,
            basename=basename,
            ros_namespace=ns,
            stack_namespace=infer_stack_namespace(full_path, basename),
            display_name=spec.display_name,
        )

    return result


# ---------------------------------------------------------------------------
# Lifecycle manager discovery
# ---------------------------------------------------------------------------


#: Known Nav2 lifecycle manager node paths → human-readable scope names.
#: Kept for backward compatibility with code that pre-creates LifecycleManagerClient
#: instances for well-known paths.
LIFECYCLE_MANAGERS: dict[str, str] = {
    '/lifecycle_manager_navigation': 'Navigation',
    '/lifecycle_manager_localization': 'Localization',
}


def discover_lifecycle_managers(
    node: Node,
    nodes_and_ns: list[tuple[str, str]] | None = None,
) -> dict[str, DiscoveredLifecycleManager]:
    """Find all running nodes whose basename starts with ``lifecycle_manager``.

    Replaces the old hardcoded-path lookup with dynamic basename matching so
    that custom lifecycle managers (e.g. ``lifecycle_manager_map``) or
    namespaced deployments are found automatically.

    Args:
        node: The rclpy Node used to call the ROS2 graph API.
        nodes_and_ns: Pre-fetched result of ``node.get_node_names_and_namespaces()``.

    Returns:
        dict mapping full_path → :class:`DiscoveredLifecycleManager`.
    """
    if nodes_and_ns is None:
        nodes_and_ns = node.get_node_names_and_namespaces()

    result: dict[str, DiscoveredLifecycleManager] = {}
    for name, ns in nodes_and_ns:
        if not name.startswith('lifecycle_manager'):
            continue
        full_path = '/' + name if ns == '/' else ns + '/' + name
        # Stack namespace is one level above the manager node itself.
        stack_ns = full_path.rsplit('/', 1)[0] or '/'
        result[full_path] = DiscoveredLifecycleManager(
            full_path=full_path,
            basename=name,
            ros_namespace=ns,
            stack_namespace=stack_ns,
        )

    return result
