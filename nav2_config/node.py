"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

from __future__ import annotations

import logging
import queue
from typing import Any

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from PyQt6.QtCore import QObject, pyqtSignal

from nav2_config.core.node_discovery import NAV2_NODES, discover_nav2_nodes
from nav2_config.core.param_client import Nav2ParamClient
from nav2_config.core.param_watcher import ParamWatcher
from nav2_config.core.topic_discovery import TopicDiscovery
from nav2_config.core.frame_discovery import FrameDiscovery
from nav2_config.types.params import Nav2ParamDef, ParamValue

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    """Qt signal bridge for crossing the ROS2-thread / Qt-main-thread boundary.

    All signals are emitted from the ROS2 background thread and delivered
    to GUI slots on the Qt main thread via Qt's queued connection mechanism.
    """

    # Emitted when Nav2 node discovery completes; carries {node_path: bool} map.
    nodes_discovered = pyqtSignal(dict)

    # Emitted when parameters for a node arrive; carries (node_name, list[ParamValue]).
    params_received = pyqtSignal(str, list)

    # Emitted after a set_parameters call; carries (node_name, param_name, success).
    param_set_result = pyqtSignal(str, str, bool)

    # Emitted when the overall ROS2 connection state changes.
    connection_status = pyqtSignal(bool)

    # Emitted when an external tool changes a watched param.
    # Carries (node_name, list[tuple[param_name, new_value]]).
    params_externally_changed = pyqtSignal(str, list)

    # Emitted every TOPIC_FRAME_INTERVAL seconds so the GUI can refresh
    # topic and TF frame dropdowns.
    discovery_refreshed = pyqtSignal()


class Nav2ConfigNode(Node):
    """ROS2 node that connects to a running Nav2 stack.

    Runs on a background thread via rclpy.spin(). Communicates with the
    Qt GUI exclusively through SignalBridge Qt signals.

    Parameter operations (fetch / set) are requested by the GUI by calling
    :meth:`request_fetch_params` or :meth:`request_set_param`.  These methods
    place work items on an internal queue which is drained on the next ROS2
    timer tick, keeping all service calls on the ROS2 thread.
    """

    #: Seconds between automatic discovery polls.
    DISCOVERY_INTERVAL: float = 3.0
    #: Seconds between parameter polls for external-change detection.
    POLL_INTERVAL: float = 2.0
    #: Seconds between topic/frame discovery refreshes for GUI dropdowns.
    TOPIC_FRAME_INTERVAL: float = 5.0

    def __init__(self, schema: list[Nav2ParamDef] | None = None) -> None:
        super().__init__('nav2_config_node')
        self.signals = SignalBridge()

        #: Loaded parameter schema (all nodes).  Set after construction when
        #: the schema file has been read, or pass directly for testing.
        self._schema: list[Nav2ParamDef] = schema or []

        # Reentrant callback group so that timer callbacks can block waiting
        # for service futures without starving the service response callbacks.
        # With the default MutuallyExclusiveCallbackGroup the timer would hold
        # the group lock while blocking, and the service client could never fire.
        self._cb_group = ReentrantCallbackGroup()

        #: Parameter service client.
        self._param_client = Nav2ParamClient(self, self._cb_group)

        #: Thread-safe queue for GUI → ROS2 parameter operation requests.
        #: Each item is a tuple: ("fetch", node_name) or ("set", node_name, param_name, value, type_hint).
        self._request_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        #: Watches the selected node for external parameter changes.
        self._watcher = ParamWatcher()

        #: Topic discovery helper — wraps get_topic_names_and_types().
        self.topic_discovery = TopicDiscovery(self)

        #: TF frame discovery helper — wraps tf2_ros Buffer.
        self.frame_discovery = FrameDiscovery(self)

        # None sentinel means "first tick — always emit".
        self._prev_discovered: set[str] | None = None

        # ROS2 timers share the same reentrant group so that service calls
        # issued inside these callbacks can complete concurrently.
        self.create_timer(self.DISCOVERY_INTERVAL, self._on_timer_tick,
                          callback_group=self._cb_group)
        self.create_timer(self.POLL_INTERVAL, self._on_poll_tick,
                          callback_group=self._cb_group)
        self.create_timer(self.TOPIC_FRAME_INTERVAL, self._on_topic_frame_tick,
                          callback_group=self._cb_group)

        self.get_logger().info('Nav2 Config GUI started')

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def set_schema(self, schema: list[Nav2ParamDef]) -> None:
        """Replace the loaded schema.  Safe to call before spinning starts."""
        self._schema = schema

    # ------------------------------------------------------------------
    # GUI-facing request methods (safe to call from any thread)
    # ------------------------------------------------------------------

    def request_fetch_params(self, node_name: str) -> None:
        """Ask the ROS2 thread to fetch all parameters for *node_name*.

        Non-blocking.  When the fetch completes, ``signals.params_received``
        is emitted with ``(node_name, list[ParamValue])``.

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.
        """
        self._request_queue.put(("fetch", node_name))

    def request_set_param(
        self,
        node_name: str,
        param_name: str,
        value: Any,
        type_hint: str = "",
    ) -> None:
        """Ask the ROS2 thread to set a parameter on *node_name*.

        Non-blocking.  When the call completes, ``signals.param_set_result``
        is emitted with ``(node_name, param_name, success)``.

        Args:
            node_name: Full ROS2 node path.
            param_name: Parameter name.
            value: New value (Python native type).
            type_hint: Schema type string to encode the value correctly.
        """
        self._request_queue.put(("set", node_name, param_name, value, type_hint))

    def watch_node(self, node_name: str) -> None:
        """Start polling *node_name* for external parameter changes.

        Safe to call from any thread.  The watcher fires on the ROS2 poll
        timer and emits ``signals.params_externally_changed`` if values differ.

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.
        """
        self._watcher.watch(node_name)

    def unwatch_node(self) -> None:
        """Stop polling for external parameter changes."""
        self._watcher.unwatch()

    # ------------------------------------------------------------------
    # ROS2 timer callbacks
    # ------------------------------------------------------------------

    def _on_timer_tick(self) -> None:
        """Called by the ROS2 timer on the spin thread every DISCOVERY_INTERVAL.

        Performs node discovery, then drains any pending parameter requests
        from the GUI.
        """
        self._on_discovery_tick()
        self._drain_request_queue()

    def _on_topic_frame_tick(self) -> None:
        """5-second timer callback: signal the GUI to refresh topic/frame dropdowns."""
        self.signals.discovery_refreshed.emit()

    def _on_poll_tick(self) -> None:
        """2-second timer callback: drain request queue, then re-fetch watched node params."""
        self._drain_request_queue()
        watched = self._watcher.watched_node
        if not watched:
            return
        try:
            fresh = self._param_client.get_all_nav2_params(watched, self._schema)
        except Exception:
            return  # Node may have gone offline — silently skip this tick.
        changed = self._watcher.diff(fresh)
        if changed:
            self.signals.params_externally_changed.emit(watched, changed)
            self.get_logger().info(
                f"External param changes on {watched}: {', '.join(f'{n}={v}' for n, v in changed)}"
            )

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
            self.get_logger().info(f"Nav2 node appeared: {path} ({NAV2_NODES.get(path, path)})")
        for path in self._prev_discovered - discovered:
            self.get_logger().info(f"Nav2 node lost: {path} ({NAV2_NODES.get(path, path)})")

        self._prev_discovered = discovered
        self.signals.nodes_discovered.emit(status)

    def force_discover(self) -> None:
        """Trigger one immediate discovery pass (e.g. from Refresh button).

        Safe to call from any thread; discovery result is emitted via signal.
        """
        self._on_discovery_tick()

    # ------------------------------------------------------------------
    # Parameter request processing (ROS2 thread only)
    # ------------------------------------------------------------------

    def _drain_request_queue(self) -> None:
        """Process all pending GUI parameter requests from the queue."""
        while not self._request_queue.empty():
            try:
                item = self._request_queue.get_nowait()
            except queue.Empty:
                break
            self._handle_request(item)

    def _handle_request(self, item: tuple) -> None:
        """Dispatch a single request tuple to the appropriate handler."""
        op = item[0]
        if op == "fetch":
            _, node_name = item
            self._fetch_params_for_node(node_name)
        elif op == "set":
            _, node_name, param_name, value, type_hint = item
            self._set_param(node_name, param_name, value, type_hint)
        else:
            logger.warning("Unknown request op: %r", op)

    def _fetch_params_for_node(self, node_name: str) -> None:
        """Fetch all schema-defined params for *node_name* and emit the result.

        Called on the ROS2 thread.  Emits ``signals.params_received``.
        """
        param_values: list[ParamValue] = self._param_client.get_all_nav2_params(
            node_name, self._schema
        )
        # Update watcher baseline so poll doesn't flag these values as external changes.
        if self._watcher.watched_node == node_name:
            self._watcher.set_baseline(param_values)
        self.signals.params_received.emit(node_name, param_values)
        self.get_logger().debug(f"Fetched {len(param_values)} params for {node_name}")

    def _set_param(
        self,
        node_name: str,
        param_name: str,
        value: Any,
        type_hint: str,
    ) -> None:
        """Set a single parameter and emit the result signal.

        Called on the ROS2 thread.  Emits ``signals.param_set_result``.
        """
        success = self._param_client.set_param(node_name, param_name, value, type_hint)
        self.signals.param_set_result.emit(node_name, param_name, success)
        if success:
            self.get_logger().info(f"Set {node_name}/{param_name} = {value!r}")
        else:
            self.get_logger().warning(f"Failed to set {node_name}/{param_name}")
