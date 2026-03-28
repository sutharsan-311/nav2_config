"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

from __future__ import annotations

import logging
import queue
from typing import Any

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from PyQt6.QtCore import QObject, pyqtSignal

from nav2_config.core.lifecycle_client import LifecycleClient, LifecycleManagerClient, NAV2_RESTART_ORDER
from nav2_config.core.node_discovery import (
    NAV2_NODES,
    LIFECYCLE_MANAGERS,
    discover_nav2_nodes,
    discover_lifecycle_managers,
)
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

    # Emitted when lifecycle states are polled; carries {node_path: state_label}.
    lifecycle_states_updated = pyqtSignal(dict)

    # Emitted after a single-node lifecycle transition or restart completes.
    # Carries (node_path, success, message).
    lifecycle_change_result = pyqtSignal(str, bool, str)

    # Emitted during a restart sequence to report progress.
    # Carries (node_path, step_description).
    lifecycle_progress = pyqtSignal(str, str)

    # Emitted when lifecycle_manager presence changes.
    # Carries (is_present, manager_node_path).  manager_node_path is '' when not present.
    lifecycle_manager_status = pyqtSignal(bool, str)


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

        #: Lifecycle service client (direct per-node transitions).
        self._lifecycle_client = LifecycleClient(self, self._cb_group)

        #: lifecycle_manager service clients keyed by manager node path.
        #: Pre-created for all known managers; availability checked at call time.
        self._lifecycle_manager_clients: dict[str, LifecycleManagerClient] = {
            path: LifecycleManagerClient(self, path, self._cb_group)
            for path in LIFECYCLE_MANAGERS
        }

        #: Currently-detected lifecycle_manager node path, or None if not running.
        self._lifecycle_manager_node: str | None = None

        #: Thread-safe queue for GUI → ROS2 parameter operation requests.
        #: Each item is a tuple: ("fetch", node_name) or ("set", ...) or lifecycle ops.
        self._request_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        #: Watches the selected node for external parameter changes.
        self._watcher = ParamWatcher()

        #: Topic discovery helper — wraps get_topic_names_and_types().
        self.topic_discovery = TopicDiscovery(self)

        #: TF frame discovery helper — wraps tf2_ros Buffer.
        self.frame_discovery = FrameDiscovery(self)

        # None sentinel means "first tick — always emit".
        self._prev_discovered: set[str] | None = None

        #: Latest known lifecycle states per node path.
        self._lifecycle_states: dict[str, str] = {}

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

    def request_lifecycle_change(self, node_name: str, transition_id: int) -> None:
        """Ask the ROS2 thread to trigger a single lifecycle transition.

        Non-blocking.  Result is emitted via ``signals.lifecycle_change_result``.

        Args:
            node_name: Full ROS2 node path, e.g. ``'/controller_server'``.
            transition_id: A ``lifecycle_msgs.msg.Transition.TRANSITION_*`` constant.
        """
        self._request_queue.put(('lifecycle_change', node_name, transition_id))

    def request_lifecycle_restart(self, node_name: str) -> None:
        """Ask the ROS2 thread to run the full restart sequence for *node_name*.

        Sequence: deactivate → cleanup → configure → activate.
        Progress is emitted via ``signals.lifecycle_progress``.
        Final result is emitted via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_restart', node_name))

    def request_lifecycle_restart_all(self) -> None:
        """Ask the ROS2 thread to restart all discovered Nav2 nodes in order.

        Progress is emitted via ``signals.lifecycle_progress``.
        Per-node results are emitted via ``signals.lifecycle_change_result``.
        Updated states are emitted via ``signals.lifecycle_states_updated`` on completion.
        """
        self._request_queue.put(('lifecycle_restart_all',))

    def request_lifecycle_shutdown(self, node_name: str) -> None:
        """Ask the ROS2 thread to shut down *node_name*.

        Picks the appropriate shutdown transition based on current state.
        Result is emitted via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_shutdown', node_name))

    def request_nav2_stack_restart(self) -> None:
        """Ask the ROS2 thread to restart all Nav2 nodes via lifecycle_manager.

        Uses ``/lifecycle_manager_navigation/manage_nodes`` (RESET + STARTUP)
        so that lifecycle_manager's bond monitoring is not triggered.
        Falls back to direct restart if lifecycle_manager is not detected.

        Progress is emitted via ``signals.lifecycle_progress``.
        Result is emitted via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_manager_restart',))

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
        """Periodic callback: discover Nav2 nodes, emit signal on change, poll lifecycle."""
        status = discover_nav2_nodes(self)
        if status is None:
            # discover_nav2_nodes not yet implemented — skip.
            return

        discovered = {path for path, found in status.items() if found}

        if self._prev_discovered is None:
            # First tick: always emit so the GUI shows initial state.
            self._prev_discovered = discovered
            self.signals.nodes_discovered.emit(status)
        elif discovered != self._prev_discovered:
            # Log appeared / lost nodes.
            for path in discovered - self._prev_discovered:
                self.get_logger().info(
                    f"Nav2 node appeared: {path} ({NAV2_NODES.get(path, path)})"
                )
            for path in self._prev_discovered - discovered:
                self.get_logger().info(
                    f"Nav2 node lost: {path} ({NAV2_NODES.get(path, path)})"
                )
            self._prev_discovered = discovered
            self.signals.nodes_discovered.emit(status)

        # Detect which lifecycle_manager (if any) is running.
        self._update_lifecycle_manager_status()

        # Poll lifecycle state for all discovered nodes and emit if changed.
        self._poll_lifecycle_states(discovered)

    def _poll_lifecycle_states(self, discovered: set[str]) -> None:
        """Query lifecycle state for all *discovered* nodes; emit if any changed."""
        new_states: dict[str, str] = {}
        for path in discovered:
            state = self._lifecycle_client.get_state(
                path, availability_timeout=0.3
            )
            new_states[path] = state

        if new_states != {k: v for k, v in self._lifecycle_states.items() if k in discovered}:
            self._lifecycle_states.update(new_states)
            self.signals.lifecycle_states_updated.emit(dict(new_states))

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
        if op == 'fetch':
            _, node_name = item
            self._fetch_params_for_node(node_name)
        elif op == 'set':
            _, node_name, param_name, value, type_hint = item
            self._set_param(node_name, param_name, value, type_hint)
        elif op == 'lifecycle_change':
            _, node_name, transition_id = item
            self._do_lifecycle_change(node_name, transition_id)
        elif op == 'lifecycle_restart':
            _, node_name = item
            self._do_lifecycle_restart(node_name)
        elif op == 'lifecycle_restart_all':
            self._do_lifecycle_restart_all()
        elif op == 'lifecycle_manager_restart':
            self._do_lifecycle_manager_restart()
        elif op == 'lifecycle_shutdown':
            _, node_name = item
            self._do_lifecycle_shutdown(node_name)
        else:
            logger.warning('Unknown request op: %r', op)

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

    # ------------------------------------------------------------------
    # Lifecycle request handlers (ROS2 thread only)
    # ------------------------------------------------------------------

    def _do_lifecycle_change(self, node_name: str, transition_id: int) -> None:
        """Execute a single lifecycle transition and emit the result.

        Called on the ROS2 thread.  Emits ``signals.lifecycle_change_result``
        and updates ``signals.lifecycle_states_updated`` with the new state.
        """
        success = self._lifecycle_client.change_state(node_name, transition_id)
        from lifecycle_msgs.msg import Transition as _T
        _names = {
            _T.TRANSITION_CONFIGURE: 'Configure',
            _T.TRANSITION_CLEANUP: 'Cleanup',
            _T.TRANSITION_ACTIVATE: 'Activate',
            _T.TRANSITION_DEACTIVATE: 'Deactivate',
            _T.TRANSITION_ACTIVE_SHUTDOWN: 'Shutdown',
            _T.TRANSITION_INACTIVE_SHUTDOWN: 'Shutdown',
            _T.TRANSITION_UNCONFIGURED_SHUTDOWN: 'Shutdown',
        }
        op_name = _names.get(transition_id, f'Transition {transition_id}')
        msg = f'{op_name} succeeded' if success else f'{op_name} failed'
        self.signals.lifecycle_change_result.emit(node_name, success, msg)
        self.get_logger().info(f'{op_name} {node_name}: {"OK" if success else "FAILED"}')

        # Refresh lifecycle state for this node.
        state = self._lifecycle_client.get_state(node_name, availability_timeout=0.5)
        self._lifecycle_states[node_name] = state
        self.signals.lifecycle_states_updated.emit({node_name: state})

    def _do_lifecycle_shutdown(self, node_name: str) -> None:
        """Execute the appropriate shutdown transition and emit the result."""
        success = self._lifecycle_client.shutdown(node_name)
        msg = 'Shutdown succeeded' if success else 'Shutdown failed'
        self.signals.lifecycle_change_result.emit(node_name, success, msg)
        self.get_logger().info(f'Shutdown {node_name}: {"OK" if success else "FAILED"}')

        state = self._lifecycle_client.get_state(node_name, availability_timeout=0.5)
        self._lifecycle_states[node_name] = state
        self.signals.lifecycle_states_updated.emit({node_name: state})

    def _do_lifecycle_restart(self, node_name: str) -> None:
        """Run the full restart sequence and emit progress + result signals."""
        def _progress(step: str) -> None:
            self.signals.lifecycle_progress.emit(node_name, step)

        success, msg = self._lifecycle_client.restart(node_name, progress_cb=_progress)
        self.signals.lifecycle_change_result.emit(node_name, success, msg)
        self.get_logger().info(f'Restart {node_name}: {msg}')

        state = self._lifecycle_client.get_state(node_name, availability_timeout=0.5)
        self._lifecycle_states[node_name] = state
        self.signals.lifecycle_states_updated.emit({node_name: state})

    def _update_lifecycle_manager_status(self) -> None:
        """Detect whether a lifecycle_manager is running; emit signal on change."""
        mgr_status = discover_lifecycle_managers(self)
        # Use the first running manager found (navigation takes priority).
        active = next((p for p in LIFECYCLE_MANAGERS if mgr_status.get(p)), None)
        if active != self._lifecycle_manager_node:
            self._lifecycle_manager_node = active
            self.signals.lifecycle_manager_status.emit(
                active is not None,
                active or '',
            )
            if active:
                self.get_logger().info(
                    f'lifecycle_manager detected: {active} — using managed lifecycle operations'
                )
            else:
                self.get_logger().info(
                    'lifecycle_manager not found — direct lifecycle transitions enabled'
                )

    def _do_lifecycle_manager_restart(self) -> None:
        """Restart all Nav2 nodes via lifecycle_manager's manage_nodes service.

        If lifecycle_manager is not detected, falls back to the direct
        per-node restart sequence.  Emits ``lifecycle_progress`` and
        ``lifecycle_change_result``.
        """
        mgr_path = self._lifecycle_manager_node
        if mgr_path is None:
            self.get_logger().warning(
                'request_nav2_stack_restart: no lifecycle_manager detected, '
                'falling back to direct per-node restart'
            )
            self._do_lifecycle_restart_all()
            return

        client = self._lifecycle_manager_clients[mgr_path]

        def _progress(step: str) -> None:
            self.signals.lifecycle_progress.emit(mgr_path, step)

        success, msg = client.restart_stack(progress_cb=_progress)
        self.signals.lifecycle_change_result.emit(mgr_path, success, msg)
        self.get_logger().info(f'lifecycle_manager restart via {mgr_path}: {msg}')

        # Re-poll all lifecycle states after the restart completes.
        discovered = self._prev_discovered or set()
        new_states: dict[str, str] = {}
        for path in discovered:
            new_states[path] = self._lifecycle_client.get_state(
                path, availability_timeout=0.5
            )
        self._lifecycle_states.update(new_states)
        if new_states:
            self.signals.lifecycle_states_updated.emit(new_states)

    def _do_lifecycle_restart_all(self) -> None:
        """Restart all discovered Nav2 nodes in lifecycle order.

        Emits ``lifecycle_progress`` per step, ``lifecycle_change_result`` per
        node, and ``lifecycle_states_updated`` when finished.
        """
        discovered = self._prev_discovered or set()

        def _progress(node_name: str, step: str) -> None:
            self.signals.lifecycle_progress.emit(node_name, step)

        results = self._lifecycle_client.restart_all_nav2(
            discovered, progress_cb=_progress
        )

        for node_name, (success, msg) in results.items():
            self.signals.lifecycle_change_result.emit(node_name, success, msg)
            self.get_logger().info(f'restart_all {node_name}: {msg}')

        # Re-poll all lifecycle states.
        new_states: dict[str, str] = {}
        for path in discovered:
            new_states[path] = self._lifecycle_client.get_state(
                path, availability_timeout=0.5
            )
        self._lifecycle_states.update(new_states)
        if new_states:
            self.signals.lifecycle_states_updated.emit(new_states)
