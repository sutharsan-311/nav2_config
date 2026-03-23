"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

import logging
from typing import Any

import rclpy
from rclpy.node import Node
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    """Qt signal bridge for crossing the ROS2-thread / Qt-main-thread boundary.

    All signals are emitted from the ROS2 background thread and delivered
    to GUI slots on the Qt main thread via Qt's queued connection mechanism.
    """

    # Emitted when Nav2 node discovery completes; carries list of node names.
    nodes_discovered = pyqtSignal(list)

    # Emitted when parameters for a node arrive; carries (node_name, param_dict).
    params_received = pyqtSignal(str, dict)

    # Emitted after a set_parameters call; carries (node_name, param_name, success).
    param_set_result = pyqtSignal(str, str, bool)

    # Emitted when the overall ROS2 connection state changes.
    connection_status = pyqtSignal(bool)


class Nav2ConfigNode(Node):
    """ROS2 node that connects to a running Nav2 stack.

    Runs on a background thread via rclpy.spin(). Communicates with the
    Qt GUI exclusively through SignalBridge Qt signals.
    """

    # Known Nav2 node names to discover.
    NAV2_NODE_NAMES: list[str] = [
        '/amcl',
        '/controller_server',
        '/planner_server',
        '/bt_navigator',
        '/local_costmap/local_costmap',
        '/global_costmap/global_costmap',
        '/smoother_server',
        '/velocity_smoother',
        '/behavior_server',
        '/waypoint_follower',
        '/map_server',
    ]

    def __init__(self) -> None:
        super().__init__('nav2_config_node')
        self.signals = SignalBridge()
        self.get_logger().info('Nav2 Config GUI started')
