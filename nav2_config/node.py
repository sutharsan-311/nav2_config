"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

import logging

import rclpy
from rclpy.node import Node
from PyQt6.QtCore import QObject, pyqtSignal

from nav2_config.core.node_discovery import NAV2_NODES, discover_nav2_nodes

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    """Qt signal bridge for crossing the ROS2-thread / Qt-main-thread boundary.

    All signals are emitted from the ROS2 background thread and delivered
    to GUI slots on the Qt main thread via Qt's queued connection mechanism.
    """

    # Emitted when Nav2 node discovery completes; carries {node_path: bool} map.
    nodes_discovered = pyqtSignal(dict)

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

    #: Seconds between automatic discovery polls.
    DISCOVERY_INTERVAL: float = 3.0

    def __init__(self) -> None:
        super().__init__('nav2_config_node')
        self.signals = SignalBridge()

        # None sentinel means "first tick — always emit".
        self._prev_discovered: set[str] | None = None

        # ROS2 timer fires on the spin thread every DISCOVERY_INTERVAL seconds.
        self.create_timer(self.DISCOVERY_INTERVAL, self._on_discovery_tick)

        self.get_logger().info('Nav2 Config GUI started')

    # ------------------------------------------------------------------
    # Node discovery
    # ------------------------------------------------------------------

    def _on_discovery_tick(self) -> None:
        """Periodic callback: discover Nav2 nodes and emit signal on change."""
        status = discover_nav2_nodes(self)
        if status is None:
            # discover_nav2_nodes not yet implemented — skip.
            return

        discovered = {path for path, found in status.items() if found}

        if self._prev_discovered is None:
            # First tick: always emit so the GUI shows initial state.
            self._prev_discovered = discovered
            self.signals.nodes_discovered.emit(status)
            return

        if discovered == self._prev_discovered:
            return  # No change — skip the emit.

        # Log appeared / lost nodes.
        for path in discovered - self._prev_discovered:
            self.get_logger().info('Nav2 node appeared: %s (%s)', path, NAV2_NODES.get(path, path))
        for path in self._prev_discovered - discovered:
            self.get_logger().info('Nav2 node lost: %s (%s)', path, NAV2_NODES.get(path, path))

        self._prev_discovered = discovered
        self.signals.nodes_discovered.emit(status)

    def force_discover(self) -> None:
        """Trigger one immediate discovery pass (e.g. from Refresh button).

        Safe to call from any thread; discovery result is emitted via signal.
        """
        self._on_discovery_tick()
