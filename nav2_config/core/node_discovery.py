"""Nav2 node discovery: checks which Nav2 nodes are currently running."""

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


def discover_nav2_nodes(node: Node) -> dict[str, bool]:
    """Discover which Nav2 nodes are currently running.

    Calls ``node.get_node_names_and_namespaces()`` to enumerate all running
    ROS2 nodes, then checks each expected Nav2 node path against the result.

    ROS2 represents a node's location as a (name, namespace) pair:
      - ``/amcl``                       → name='amcl',          namespace='/'
      - ``/local_costmap/local_costmap`` → name='local_costmap', namespace='/local_costmap'

    Args:
        node: The rclpy Node used to call the ROS2 graph API.

    Returns:
        dict mapping each :data:`NAV2_NODES` key to ``True`` (running) or
        ``False`` (not found).
    """
    nodes_and_ns = node.get_node_names_and_namespaces()

    running: set[str] = set()
    for name, ns in nodes_and_ns:
        if ns == '/':
            full_path = '/' + name
        else:
            full_path = ns + '/' + name
        running.add(full_path)

    return {nav_node: (nav_node in running) for nav_node in NAV2_NODES}
