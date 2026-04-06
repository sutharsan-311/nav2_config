# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

from __future__ import annotations

import logging
import queue
from typing import Any

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rcl_interfaces.msg import ParameterType
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
from nav2_config.core.service_caller import Nav2ServiceCaller
from nav2_config.core.topic_discovery import TopicDiscovery
from nav2_config.core.frame_discovery import FrameDiscovery
from nav2_config.types.params import Nav2ParamDef, ParamValue

logger = logging.getLogger(__name__)

#: Parameter name substrings that are infrastructure / not useful to show in the GUI.
_PARAM_FILTER_SUBSTRINGS = ('qos_overrides', 'use_sim_time', 'bond_disable_heartbeat')


def _dot_prefix_category(name: str) -> str:
    """Return a grouping category based on the dot-prefix of a parameter name.

    Examples::
        "controller_frequency"         -> "Base Parameters"
        "FollowPath.max_vel_x"         -> "FollowPath"
        "FollowPath.GoalAlign.weight"  -> "FollowPath.GoalAlign"
    """
    parts = name.split('.')
    if len(parts) <= 1:
        return 'Base Parameters'
    return '.'.join(parts[:-1])


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

    # Emitted after a /map_server/load_map service call completes.
    # Carries (success, message).
    load_map_result = pyqtSignal(bool, str)

    # Emitted after a post-set service action completes (clear_costmaps, nomotion_update).
    # Carries (param_name, action, success, detail_message).
    post_action_result = pyqtSignal(str, str, bool, str)

    # Emitted when a restart_stack param is successfully set.
    # Carries (node_name, param_name).
    restart_suggested = pyqtSignal(str, str)


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

        #: Service caller for post-param-set follow-up actions.
        self._service_caller = Nav2ServiceCaller(self, self._cb_group)

        #: Lifecycle service client (direct per-node transitions).
        self._lifecycle_client = LifecycleClient(self, self._cb_group)

        #: lifecycle_manager service clients keyed by manager node path.
        #: Pre-created for all known managers; availability checked at call time.
        self._lifecycle_manager_clients: dict[str, LifecycleManagerClient] = {
            path: LifecycleManagerClient(self, path, self._cb_group)
            for path in LIFECYCLE_MANAGERS
        }

        #: All currently-running lifecycle_manager node paths.
        self._active_lifecycle_managers: set[str] = set()

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

    def request_load_map(self, map_url: str) -> None:
        """Ask the ROS2 thread to call /map_server/load_map with *map_url*.

        Non-blocking.  Result is emitted via ``signals.load_map_result``.

        Args:
            map_url: Absolute path to the map YAML file to load.
        """
        self._request_queue.put(('load_map', map_url))

    def request_nav2_stack_restart(self) -> None:
        """Ask the ROS2 thread to restart all Nav2 nodes via lifecycle_manager.

        Uses ``/lifecycle_manager_navigation/manage_nodes`` (RESET + STARTUP)
        so that lifecycle_manager's bond monitoring is not triggered.
        Falls back to direct restart if lifecycle_manager is not detected.

        Progress is emitted via ``signals.lifecycle_progress``.
        Result is emitted via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_manager_restart',))

    def get_lifecycle_state(self, node_name: str) -> str:
        """Return the last-polled lifecycle state for *node_name*.

        Safe to call from the Qt thread — reads only the cached dict, no ROS2
        service calls.  Returns ``'unknown'`` if the node has not been polled yet.
        """
        return self._lifecycle_states.get(node_name, 'unknown')

    def request_lifecycle_pause_stack(self) -> None:
        """Ask the ROS2 thread to pause all Nav2 nodes via lifecycle_manager.

        Sends the PAUSE command to lifecycle_manager, which deactivates all
        managed nodes without cleanup.  Nodes land in ``inactive`` state and
        can be resumed cheaply via ``request_nav2_stack_restart()``.

        Requires lifecycle_manager to be running.  If it is absent the request
        silently emits a failure via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_manager_pause',))

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
            fresh = self._build_param_values(watched)
        except Exception:
            return  # Node may have gone offline — silently skip this tick.
        if not any(pv.is_live for pv in fresh):
            return  # All params are schema defaults — node is offline, skip diff.
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
        """Periodic callback: discover Nav2 nodes, emit signal every tick, poll lifecycle."""
        nodes_and_ns = self.get_node_names_and_namespaces()
        status = discover_nav2_nodes(self, nodes_and_ns)

        discovered = {path for path, found in status.items() if found}

        # Log appeared / lost nodes relative to previous tick.
        if self._prev_discovered is not None:
            for path in discovered - self._prev_discovered:
                self.get_logger().info(
                    f"Nav2 node appeared: {path} ({NAV2_NODES.get(path, path)})"
                )
            for path in self._prev_discovered - discovered:
                self.get_logger().info(
                    f"Nav2 node lost: {path} ({NAV2_NODES.get(path, path)})"
                )
        self._prev_discovered = discovered

        # Always emit — the GUI must always receive fresh discovery data.
        self.signals.nodes_discovered.emit(status)

        # Detect which lifecycle_manager (if any) is running (reuse cached graph data).
        self._update_lifecycle_manager_status(nodes_and_ns)

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

        Safe to call from any thread; the work executes on the ROS2 thread via
        the request queue and result is emitted via signal.
        """
        self._request_queue.put(('discover',))

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
        elif op == 'lifecycle_manager_pause':
            self._do_lifecycle_manager_pause()
        elif op == 'lifecycle_shutdown':
            _, node_name = item
            self._do_lifecycle_shutdown(node_name)
        elif op == 'load_map':
            _, map_url = item
            self._do_load_map(map_url)
        elif op == 'discover':
            self._on_discovery_tick()
        else:
            logger.warning('Unknown request op: %r', op)

    def _fetch_params_for_node(self, node_name: str) -> None:
        """Fetch all live params for *node_name*, merging with schema where available.

        Called on the ROS2 thread.  Emits ``signals.params_received``.
        """
        param_values = self._build_param_values(node_name)
        # Update watcher baseline so poll doesn't flag these values as external changes.
        if self._watcher.watched_node == node_name:
            self._watcher.set_baseline(param_values)
        self.signals.params_received.emit(node_name, param_values)
        self.get_logger().debug(f"Fetched {len(param_values)} params for {node_name}")

    def _build_param_values(self, node_name: str) -> list[ParamValue]:
        """Build the full ParamValue list for *node_name*.

        1. Lists all live parameters from the running node.
        2. Filters out infrastructure params (qos_overrides etc.).
        3. Fetches all live values in one RPC call.
        4. For each param: uses schema metadata if available, otherwise synthesises
           a minimal Nav2ParamDef from the live type and a dot-prefix category.

        Falls back to schema-only params (with ``is_live=False``) when the node
        is not reachable (i.e. ``list_params`` returns an empty list).
        """
        bare_node = node_name.rstrip('/').rsplit('/', 1)[-1]

        live_names = [
            n for n in self._param_client.list_params(node_name)
            if not any(f in n for f in _PARAM_FILTER_SUBSTRINGS)
        ]

        if not live_names:
            # Node offline — fall back to schema defaults so the panel isn't empty.
            return self._param_client.get_all_nav2_params(node_name, self._schema)

        live_typed = self._param_client.get_params(node_name, live_names)

        results: list[ParamValue] = []
        for name in live_names:
            schema_entry = self._find_schema_entry(node_name, name)
            entry = live_typed.get(name)
            value, ros2_type = entry if entry is not None else (None, None)

            if schema_entry:
                results.append(ParamValue(
                    definition=schema_entry,
                    current_value=value if value is not None else schema_entry.default,
                    is_modified=False,
                    is_live=(value is not None),
                ))
            else:
                param_type = self._detect_type(value, ros2_type)
                category = _dot_prefix_category(name)
                defn = Nav2ParamDef(
                    node=bare_node,
                    param=name,
                    ros2_name=name,
                    type=param_type,
                    default=value,
                    range=None,
                    unit='',
                    description='',
                    impact='',
                    category=category,
                    plugin_specific=('.' in name),
                    plugin=name.split('.')[0] if '.' in name else None,
                    hot_reload=True,
                    post_set_action=None,
                    tags=[],
                )
                results.append(ParamValue(
                    definition=defn,
                    current_value=value,
                    is_modified=False,
                    is_live=True,
                ))

        return results

    _ROS2_TYPE_MAP: dict[int, str] = {
        ParameterType.PARAMETER_BOOL:          'bool',
        ParameterType.PARAMETER_INTEGER:       'int',
        ParameterType.PARAMETER_DOUBLE:        'double',
        ParameterType.PARAMETER_STRING:        'string',
        ParameterType.PARAMETER_BOOL_ARRAY:    'bool_array',
        ParameterType.PARAMETER_INTEGER_ARRAY: 'int_array',
        ParameterType.PARAMETER_DOUBLE_ARRAY:  'double_array',
        ParameterType.PARAMETER_STRING_ARRAY:  'string_array',
    }

    @staticmethod
    def _detect_type(value: object, ros2_type: int | None = None) -> str:
        """Infer a schema type string from a Python value returned by ROS2.

        Uses the authoritative ROS2 ParameterType when available (live params).
        Falls back to Python type inference for schema-only paths, with a
        special case: a string of comma-separated numbers is treated as
        double_array (handles params loaded from YAML as a quoted list).
        """
        if ros2_type is not None and ros2_type in Nav2ConfigNode._ROS2_TYPE_MAP:
            return Nav2ConfigNode._ROS2_TYPE_MAP[ros2_type]

        if isinstance(value, bool):
            return 'bool'
        if isinstance(value, int):
            return 'int'
        if isinstance(value, float):
            return 'double'
        if isinstance(value, list):
            if value and all(isinstance(v, bool) for v in value):
                return 'bool_array'
            if value and all(isinstance(v, int) for v in value):
                return 'int_array'
            if value and all(isinstance(v, float) for v in value):
                return 'double_array'
            return 'string_array'
        if isinstance(value, str):
            parts = [s.strip() for s in value.split(',')]
            if len(parts) > 1:
                try:
                    [float(p) for p in parts]
                    return 'double_array'
                except ValueError:
                    pass
        return 'string'

    def _set_param(
        self,
        node_name: str,
        param_name: str,
        value: Any,
        type_hint: str,
    ) -> None:
        """Set a single parameter and emit the result signal.

        Called on the ROS2 thread.  Emits ``signals.param_set_result``.
        On success, runs any post-set service action defined in the schema.
        """
        self.get_logger().info(f"Setting {node_name}/{param_name} → {value}")
        success, reason = self._param_client.set_param(node_name, param_name, value, type_hint)
        self.signals.param_set_result.emit(node_name, param_name, success)
        if success:
            self.get_logger().info(f"✓ Set {node_name}/{param_name} = {value}")
            schema_entry = self._find_schema_entry(node_name, param_name)
            self._after_param_set(node_name, param_name, value, schema_entry)
        else:
            self.get_logger().error(f"✗ Failed to set {node_name}/{param_name} = {value}: {reason}")

    def _find_schema_entry(self, node_name: str, param_name: str) -> Nav2ParamDef | None:
        """Return the schema entry for *param_name* on *node_name*, or None.

        Matches on both ``param`` and ``ros2_name`` fields.
        """
        # Use the last path segment so "/local_costmap/local_costmap" → "local_costmap"
        bare_node = node_name.rstrip('/').rsplit('/', 1)[-1]
        for entry in self._schema:
            if entry.node == bare_node and (
                entry.param == param_name or entry.ros2_name == param_name
            ):
                return entry
        return None

    def _after_param_set(
        self,
        node_name: str,
        param_name: str,
        value: Any,
        schema_entry: Nav2ParamDef | None,
    ) -> None:
        """Run any follow-up service action defined by the schema entry.

        Called on the ROS2 thread immediately after a successful param set.
        Emits ``signals.post_action_result`` or ``signals.restart_suggested``
        as appropriate.

        Args:
            node_name: Full ROS2 node path.
            param_name: Parameter name that was just set.
            value: The new value that was set.
            schema_entry: Schema definition for this parameter (may be None).
        """
        action = schema_entry.post_set_action if schema_entry else None

        if action == 'clear_costmaps':
            success = self._service_caller.clear_costmaps()
            if success:
                self.get_logger().info(
                    f"Costmaps cleared after setting {param_name}"
                )
                self.signals.post_action_result.emit(
                    param_name, 'clear_costmaps', True, 'costmaps cleared'
                )
            else:
                self.get_logger().warning(
                    f"Failed to clear costmaps after setting {param_name}"
                )
                self.signals.post_action_result.emit(
                    param_name, 'clear_costmaps', False, 'costmap clear failed'
                )

        elif action == 'load_map':
            map_url = str(value)
            success, code = self._service_caller.load_map(map_url)
            if success:
                self.get_logger().info(f"Map reloaded: {map_url}")
                self.signals.load_map_result.emit(True, f'Map loaded: {map_url}')
            else:
                _code_msgs = {
                    1: 'map file not found',
                    2: 'invalid map',
                    3: 'load_map service unavailable',
                }
                detail = _code_msgs.get(code, f'result code {code}')
                self.get_logger().error(f"Failed to load map: {map_url} ({detail})")
                self.signals.load_map_result.emit(False, f'Failed to load map: {detail}')

        elif action == 'nomotion_update':
            success = self._service_caller.nomotion_update()
            if success:
                self.get_logger().info(
                    f"AMCL nomotion update triggered after setting {param_name}"
                )
                self.signals.post_action_result.emit(
                    param_name, 'nomotion_update', True, 'AMCL updated'
                )
            else:
                self.get_logger().warning(
                    f"Failed to trigger AMCL nomotion update after setting {param_name}"
                )
                self.signals.post_action_result.emit(
                    param_name, 'nomotion_update', False, 'AMCL update failed'
                )

        elif action == 'restart_stack':
            # Don't auto-restart — show notification to user.
            self.signals.restart_suggested.emit(node_name, param_name)

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

    def _update_lifecycle_manager_status(
        self,
        nodes_and_ns: list[tuple[str, str]] | None = None,
    ) -> None:
        """Detect all running lifecycle_managers; emit signal on change."""
        mgr_status = discover_lifecycle_managers(self, nodes_and_ns)
        active = {p for p, running in mgr_status.items() if running}
        if active != self._active_lifecycle_managers:
            self._active_lifecycle_managers = active
            present = bool(active)
            primary = next(iter(sorted(active))) if active else ''
            self.signals.lifecycle_manager_status.emit(present, primary)
            if active:
                self.get_logger().info(
                    f'lifecycle_managers detected: {sorted(active)}'
                )
            else:
                self.get_logger().info(
                    'lifecycle_manager not found — direct lifecycle transitions enabled'
                )

    def _do_lifecycle_manager_restart(self) -> None:
        """Restart all Nav2 nodes via all active lifecycle_managers.

        If no lifecycle_manager is detected, falls back to the direct
        per-node restart sequence.  Emits ``lifecycle_progress`` and
        a single aggregated ``lifecycle_change_result``.
        """
        if not self._active_lifecycle_managers:
            self.get_logger().warning(
                'request_nav2_stack_restart: no lifecycle_manager detected, '
                'falling back to direct per-node restart'
            )
            self._do_lifecycle_restart_all()
            return

        all_ok = True
        result_lines: list[str] = []
        for mgr_path in sorted(self._active_lifecycle_managers):
            client = self._lifecycle_manager_clients[mgr_path]

            def _progress(step: str, _mgr: str = mgr_path) -> None:
                self.signals.lifecycle_progress.emit(_mgr, step)

            ok, msg = client.restart_stack(progress_cb=_progress)
            all_ok = all_ok and ok
            result_lines.append(f'{mgr_path.lstrip("/")} → {msg}')
            self.get_logger().info(f'lifecycle_manager restart via {mgr_path}: {msg}')

        self.signals.lifecycle_change_result.emit('', all_ok, '; '.join(result_lines))

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

    def _do_lifecycle_manager_pause(self) -> None:
        """Pause all Nav2 nodes via all active lifecycle_managers.

        Deactivates all managed nodes without cleanup — they land in
        ``inactive`` state.  If no lifecycle_manager is detected, emits a
        failure result so the GUI can report it without crashing.
        """
        if not self._active_lifecycle_managers:
            self.get_logger().warning(
                'request_lifecycle_pause_stack: no lifecycle_manager detected — cannot pause'
            )
            self.signals.lifecycle_change_result.emit(
                '', False, 'Pause failed: lifecycle_manager not found'
            )
            return

        all_ok = True
        for mgr_path in sorted(self._active_lifecycle_managers):
            ok = self._lifecycle_manager_clients[mgr_path].pause()
            all_ok = all_ok and ok
            self.get_logger().info(
                f'lifecycle_manager pause via {mgr_path}: {"ok" if ok else "failed"}'
            )

        msg = 'Stack paused (nodes inactive)' if all_ok else 'Pause failed'
        self.signals.lifecycle_change_result.emit('', all_ok, msg)

        # Re-poll states so the GUI reflects inactive immediately.
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

    def _do_load_map(self, map_url: str) -> None:
        """Call /map_server/load_map to reload the map without restarting Nav2.

        Called on the ROS2 thread.  Emits ``signals.load_map_result``.

        Args:
            map_url: Absolute path to the map YAML file to load.
        """
        from nav2_msgs.srv import LoadMap

        if not hasattr(self, '_load_map_client'):
            self._load_map_client = self.create_client(
                LoadMap, '/map_server/load_map', callback_group=self._cb_group
            )

        if not self._load_map_client.wait_for_service(timeout_sec=2.0):
            msg = 'load_map service not available on /map_server'
            self.get_logger().warning(msg)
            self.signals.load_map_result.emit(False, msg)
            return

        import threading
        req = LoadMap.Request()
        req.map_url = map_url
        future = self._load_map_client.call_async(req)

        done_event = threading.Event()
        result_holder: list[Any] = [None]

        def _on_done(fut: Any) -> None:
            result_holder[0] = fut.result()
            done_event.set()

        future.add_done_callback(_on_done)

        if not done_event.wait(timeout=10.0):
            msg = 'load_map service call timed out'
            self.get_logger().warning(msg)
            self.signals.load_map_result.emit(False, msg)
            return

        response = result_holder[0]
        # LoadMap response: result field is a uint8 (0 = success)
        success = (response is not None and response.result == 0)
        if success:
            msg = f'Map loaded: {map_url}'
            self.get_logger().info(msg)
        else:
            result_code = response.result if response is not None else -1
            msg = f'load_map failed (result={result_code})'
            self.get_logger().warning(msg)
        self.signals.load_map_result.emit(success, msg)
