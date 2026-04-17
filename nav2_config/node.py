# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ROS2 node for nav2_config: discovers Nav2 nodes and manages parameter I/O."""

from __future__ import annotations

import copy
import dataclasses
import logging
import queue
import threading
import time
from typing import Any

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node
from rcl_interfaces.msg import ParameterType
from PyQt6.QtCore import QObject, pyqtSignal

from nav2_config.core.lifecycle_client import LifecycleClient, LifecycleManagerClient
from nav2_config.core.node_discovery import (
    NAV2_NODE_SPECS,
    discover_nav2_nodes,
    discover_lifecycle_managers,
    infer_stack_namespace,
    join_ros_path,
    path_basename,
)
from nav2_config.core.param_client import Nav2ParamClient
from nav2_config.core.param_watcher import ParamWatcher
from nav2_config.core.robot_mode_detector import RobotMode, RobotModeDetector
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

    # Emitted every discovery tick with the full topology.
    # first arg: dict[str, DiscoveredNav2Node] keyed by full_path
    # second arg: dict[str, DiscoveredLifecycleManager] keyed by full_path
    topology_updated = pyqtSignal(dict, dict)

    # Emitted when the detected robot mode changes.
    # Carries a RobotMode enum value (object type so PyQt6 accepts the enum).
    robot_mode_changed = pyqtSignal(object)

    # Emitted during AMCL pose preservation around a restart.
    # Carries a human-readable status string for the status bar.
    amcl_pose_status = pyqtSignal(str)


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
        #: Created lazily as managers are discovered; avoids binding to hardcoded paths.
        self._lifecycle_manager_clients: dict[str, LifecycleManagerClient] = {}

        #: All currently-running lifecycle_manager node paths.
        self._active_lifecycle_managers: set[str] = set()

        #: Guards mutations to _lifecycle_manager_clients and _active_lifecycle_managers.
        self._lifecycle_lock = threading.Lock()

        #: Maps node_path → manager_path for each node managed by a lifecycle_manager.
        self._node_to_manager: dict[str, str] = {}

        #: Maps manager_path → set of node paths it manages.
        self._manager_to_nodes: dict[str, set[str]] = {}

        #: Thread-safe queue for GUI → ROS2 parameter operation requests.
        #: Each item is a tuple: ("fetch", node_name) or ("set", ...) or lifecycle ops.
        self._request_queue: queue.SimpleQueue[tuple] = queue.SimpleQueue()

        #: Watches the selected node for external parameter changes.
        self._watcher = ParamWatcher()

        #: Topic discovery helper — wraps get_topic_names_and_types().
        self.topic_discovery = TopicDiscovery(self)

        #: TF frame discovery helper — wraps tf2_ros Buffer.
        self.frame_discovery = FrameDiscovery(self)

        #: Simulation-vs-real-robot detector.
        self._robot_mode_detector = RobotModeDetector(self, self._param_client)

        #: Most recently emitted robot mode.
        self._current_robot_mode: RobotMode = RobotMode.UNKNOWN

        # None sentinel means "first tick — always emit".
        self._prev_discovered: set[str] | None = None

        #: Latest known lifecycle states per node path.
        self._lifecycle_states: dict[str, str] = {}

        #: Latest discovered lifecycle managers; keyed by full_path.
        self._discovered_managers: dict = {}

        # None sentinel means "first tick — always emit".
        self._prev_topology_key: tuple | None = None

        #: monotonic timestamp of the last lifecycle poll per node path.
        self._last_confirmed_poll: dict[str, float] = {}

        #: number of ticks each manager has been seen (keyed by full_path).
        self._manager_first_seen: dict[str, int] = {}

        #: increments every _poll_lifecycle_states call; used for even/odd throttle.
        self._poll_tick_count: int = 0

        #: Cached publishers for /initialpose topics, keyed by topic name.
        #: Created lazily in _publish_initial_pose; one publisher per AMCL namespace.
        self._initialpose_pubs: dict[str, object] = {}

        #: Per-node cache of filtered parameter name lists.
        #: Populated on the first successful list_params call for a node and reused
        #: on subsequent poll ticks to avoid redundant list_parameters RPCs.
        #: Invalidated (entry removed) when the node disappears from the topology.
        self._param_names_cache: dict[str, list[str]] = {}

        #: full_path of the node currently selected in the GUI (always polled).
        self._selected_node_path: str | None = None

        # ROS2 timers share the same reentrant group so that service calls
        # issued inside these callbacks can complete concurrently.
        self.create_timer(self.DISCOVERY_INTERVAL, self._on_timer_tick,
                          callback_group=self._cb_group)
        self.create_timer(self.POLL_INTERVAL, self._on_poll_tick,
                          callback_group=self._cb_group)
        self.create_timer(self.TOPIC_FRAME_INTERVAL, self._on_topic_frame_tick,
                          callback_group=self._cb_group)
        self.create_timer(5.0, self._on_robot_mode_tick,
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
        self._selected_node_path = node_name
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

    def update_watcher_baseline_entry(self, param_name: str, value: object) -> None:
        """Update the watcher baseline for one param after a confirmed live set.

        Prevents the next 2-second poll from re-reporting the GUI-initiated
        change as an external modification.

        Args:
            param_name: The parameter name (dot-notation).
            value: The confirmed new value.
        """
        self._watcher.update_baseline_entry(param_name, value)

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

    def request_load_map(self, map_url: str, node_name: str = "/map_server") -> None:
        """Ask the ROS2 thread to call the load_map service for *node_name*.

        Non-blocking.  Result is emitted via ``signals.load_map_result``.

        Args:
            map_url: Absolute path to the map YAML file to load.
            node_name: Full ROS2 path of the map_server node, e.g.
                ``/robot1/map_server``.  Defaults to ``/map_server``.
        """
        self._request_queue.put(('load_map', map_url, node_name))

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

    def get_manager_for_node(self, node_path: str) -> str | None:
        """Return the lifecycle_manager full_path that manages *node_path*.

        Safe to call from any thread — reads only the cached mapping, no ROS2
        service calls.  The mapping is rebuilt on every discovery tick so it
        reflects the current state of the running stack.

        Args:
            node_path: Full ROS2 node path, e.g. ``"/controller_server"`` or
                ``"/robot1/planner_server"``.

        Returns:
            The full_path of the managing lifecycle_manager node (e.g.
            ``"/lifecycle_manager_navigation"``), or ``None`` if no lifecycle_manager
            currently claims this node.
        """
        return self._node_to_manager.get(node_path)

    def request_lifecycle_pause_stack(self) -> None:
        """Ask the ROS2 thread to pause all Nav2 nodes via lifecycle_manager.

        Sends the PAUSE command to lifecycle_manager, which deactivates all
        managed nodes without cleanup.  Nodes land in ``inactive`` state and
        can be resumed cheaply via :meth:`request_lifecycle_resume_stack`.

        Requires lifecycle_manager to be running.  If it is absent the request
        silently emits a failure via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_manager_pause',))

    def request_lifecycle_resume_stack(self) -> None:
        """Ask the ROS2 thread to resume all Nav2 nodes via lifecycle_manager.

        Sends the RESUME command to lifecycle_manager, which reactivates all
        managed nodes from ``inactive`` back to ``active`` state.  This is the
        lightweight counterpart to :meth:`request_lifecycle_pause_stack` —
        much faster than a full RESET/STARTUP restart cycle.

        Requires lifecycle_manager to be running.  If it is absent the request
        silently emits a failure via ``signals.lifecycle_change_result``.
        """
        self._request_queue.put(('lifecycle_manager_resume',))

    def request_lifecycle_restart_stack(self, stack_namespace: str) -> None:
        """Ask the ROS2 thread to restart only the managers in *stack_namespace*.

        Like :meth:`request_nav2_stack_restart` but scoped to a single
        namespace — only lifecycle_managers whose ``stack_namespace`` matches
        are restarted.  Falls back to direct per-node restart if no matching
        manager is found.

        Args:
            stack_namespace: The stack root namespace to target, e.g. ``'/'``
                or ``'/robot1'``.
        """
        self._request_queue.put(('lifecycle_manager_restart_ns', stack_namespace))

    def request_lifecycle_pause_stack_ns(self, stack_namespace: str) -> None:
        """Ask the ROS2 thread to pause only the managers in *stack_namespace*.

        Sends the PAUSE command to every lifecycle_manager whose
        ``stack_namespace`` matches *stack_namespace*.  If no matching manager
        is found the request emits a failure via ``signals.lifecycle_change_result``.

        Args:
            stack_namespace: The stack root namespace to target.
        """
        self._request_queue.put(('lifecycle_manager_pause_ns', stack_namespace))

    def request_lifecycle_resume_stack_ns(self, stack_namespace: str) -> None:
        """Ask the ROS2 thread to resume only the managers in *stack_namespace*.

        Sends the RESUME command to every lifecycle_manager whose
        ``stack_namespace`` matches *stack_namespace*.  If no matching manager
        is found the request emits a failure via ``signals.lifecycle_change_result``.

        Args:
            stack_namespace: The stack root namespace to target.
        """
        self._request_queue.put(('lifecycle_manager_resume_ns', stack_namespace))

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

    def _on_robot_mode_tick(self) -> None:
        """5-second timer callback: detect simulation vs real robot mode.

        Runs on the ROS2 spin thread.  Emits ``signals.robot_mode_changed``
        only when the detected mode differs from the last emitted value so
        that the GUI is not spammed with no-op updates.

        Failures are caught and logged at DEBUG level; the method never raises.
        """
        try:
            mode = self._robot_mode_detector.detect(list(self._prev_discovered or set()))
        except Exception as exc:
            self.get_logger().debug(f"Robot mode detection error: {exc}")
            return
        if mode != self._current_robot_mode:
            self._current_robot_mode = mode
            self.signals.robot_mode_changed.emit(mode)

    def _on_poll_tick(self) -> None:
        """2-second timer callback: drain request queue, then re-fetch watched node params."""
        self._drain_request_queue()
        watched = self._watcher.watched_node
        if not watched:
            return
        try:
            fresh = self._build_param_values(watched)
        except Exception as exc:
            self.get_logger().warning(
                f"Unexpected error polling params for {watched}: {exc}"
            )
            self._watcher.clear_baseline()
            return
        if not any(pv.is_live for pv in fresh):
            self._watcher.clear_baseline()
            return
        changed = self._watcher.diff(fresh)
        if changed:
            self.signals.params_externally_changed.emit(watched, changed)
            self.get_logger().info(
                f"External param changes on {watched}: {', '.join(f'{n}={new}' for n, _old, new in changed)}"
            )

    # ------------------------------------------------------------------
    # Node discovery
    # ------------------------------------------------------------------

    def _on_discovery_tick(self) -> None:
        """Periodic callback: discover Nav2 nodes, emit signal every tick, poll lifecycle."""
        nodes_and_ns = self.get_node_names_and_namespaces()
        found_nodes = discover_nav2_nodes(self, nodes_and_ns)

        # Actual full paths of running Nav2 nodes (namespace-aware).
        discovered = {n.full_path for n in found_nodes.values()}

        # Log appeared / lost nodes relative to previous tick.
        if self._prev_discovered is not None:
            for path in discovered - self._prev_discovered:
                spec = NAV2_NODE_SPECS.get(path_basename(path))
                label = spec.display_name if spec else path
                self.get_logger().info(f"Nav2 node appeared: {path} ({label})")

            disappeared = self._prev_discovered - discovered
            for path in disappeared:
                spec = NAV2_NODE_SPECS.get(path_basename(path))
                label = spec.display_name if spec else path
                self.get_logger().info(f"Nav2 node lost: {path} ({label})")

            # Prune stale param clients for each disappeared node.
            for path in disappeared:
                self._param_client.prune_node(path)

            # Invalidate the param-name list cache for disappeared nodes so the
            # next fetch triggers a fresh list_params RPC (the node may have
            # restarted with a different parameter set).
            for path in disappeared:
                self._param_names_cache.pop(path, None)

            # Prune /initialpose publishers for AMCL nodes that have disappeared.
            # Each AMCL node has at most one publisher, keyed by its initialpose topic.
            for path in disappeared:
                if path_basename(path) == 'amcl':
                    topic = self._initialpose_topic(path)
                    pub = self._initialpose_pubs.pop(topic, None)
                    if pub is not None:
                        try:
                            self.destroy_publisher(pub)
                        except Exception as exc:
                            self.get_logger().debug(
                                f"Error destroying initialpose publisher for {topic}: {exc}"
                            )
                        self.get_logger().debug(
                            f"Pruned /initialpose publisher for {path} ({topic})"
                        )

            # Prune stale service clients for each stack namespace that has no
            # remaining nodes after this tick. Deduplicate so each namespace is
            # only pruned once.
            if disappeared:
                from nav2_config.core.node_discovery import infer_stack_namespace as _infer_ns
                remaining_namespaces = {
                    n.stack_namespace for n in found_nodes.values()
                }
                gone_namespaces: set[str] = set()
                for path in disappeared:
                    ns = _infer_ns(path, path_basename(path))
                    if ns not in remaining_namespaces and ns not in gone_namespaces:
                        gone_namespaces.add(ns)
                        self._service_caller.prune_namespace(ns)
        else:
            disappeared = set()
        self._prev_discovered = discovered

        # Detect which lifecycle_manager (if any) is running (reuse cached graph data).
        self._update_lifecycle_manager_status(nodes_and_ns)

        # Emit full topology — used by node panel for namespace grouping.
        # Guard: skip emit when neither the node set nor the manager set changed.
        nodes_by_path = {n.full_path: n for n in found_nodes.values()}
        new_topology_key = (frozenset(nodes_by_path), frozenset(self._discovered_managers))
        if new_topology_key != self._prev_topology_key:
            self._prev_topology_key = new_topology_key
            self.signals.topology_updated.emit(nodes_by_path, dict(self._discovered_managers))

        # Poll lifecycle state for all discovered nodes and emit if changed.
        self._poll_lifecycle_states(discovered)

    def _poll_lifecycle_states(self, discovered: set[str]) -> None:
        """Query lifecycle state for all *discovered* nodes; emit if any changed.

        Performance guards for multi-robot setups:
        - Per-node poll timeout capped at 0.05 s (fast-fail, never blocks the tick).
        - Nodes polled within the last 6 s whose state is already known are skipped,
          unless they just appeared or are the currently-selected node.
        - When more than 15 nodes are discovered, non-selected nodes are polled on
          alternating ticks to spread the load.
        """
        self._poll_tick_count += 1
        now = time.monotonic()
        large_fleet = len(discovered) > 15
        even_tick = (self._poll_tick_count % 2) == 0

        new_states: dict[str, str] = {}
        for path in discovered:
            is_selected = path == self._selected_node_path
            just_appeared = path not in self._last_confirmed_poll
            recently_polled = (now - self._last_confirmed_poll.get(path, 0.0)) < 6.0
            known_state = self._lifecycle_states.get(path)

            # Skip if: not new, not selected, state already known, polled recently.
            if not just_appeared and not is_selected and known_state and recently_polled:
                new_states[path] = known_state
                continue

            # Large-fleet even/odd throttle for non-selected, non-new nodes.
            if large_fleet and not is_selected and not just_appeared and even_tick:
                if known_state:
                    new_states[path] = known_state
                    continue

            state = self._lifecycle_client.get_state(
                path, availability_timeout=0.05
            )
            new_states[path] = state
            self._last_confirmed_poll[path] = now

        # Prune stale entries for nodes that are no longer in the discovered set.
        stale_keys = [k for k in self._lifecycle_states if k not in discovered]
        for key in stale_keys:
            del self._lifecycle_states[key]
        # Also prune poll timestamps for departed nodes.
        for key in list(self._last_confirmed_poll):
            if key not in discovered:
                del self._last_confirmed_poll[key]

        # Emit if any node was pruned or if any live state changed.
        live_changed = new_states != {k: v for k, v in self._lifecycle_states.items() if k in discovered}
        if stale_keys or live_changed:
            self._lifecycle_states.update(new_states)
            self.signals.lifecycle_states_updated.emit(dict(self._lifecycle_states))

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
            try:
                self._set_param(node_name, param_name, value, type_hint)
            except ValueError as e:
                self.get_logger().error(f"Invalid value for {node_name}/{param_name}: {e}")
                self.signals.param_set_result.emit(node_name, param_name, False)
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
        elif op == 'lifecycle_manager_resume':
            self._do_lifecycle_manager_resume()
        elif op == 'lifecycle_manager_restart_ns':
            _, stack_namespace = item
            self._do_lifecycle_manager_restart_ns(stack_namespace)
        elif op == 'lifecycle_manager_pause_ns':
            _, stack_namespace = item
            self._do_lifecycle_manager_pause_ns(stack_namespace)
        elif op == 'lifecycle_manager_resume_ns':
            _, stack_namespace = item
            self._do_lifecycle_manager_resume_ns(stack_namespace)
        elif op == 'lifecycle_shutdown':
            _, node_name = item
            self._do_lifecycle_shutdown(node_name)
        elif op == 'load_map':
            _, map_url, node_name = item
            self._do_load_map(map_url, node_name)
        elif op == 'discover':
            self._on_discovery_tick()
        else:
            logger.warning('Unknown request op: %r', op)

    def _fetch_params_for_node(self, node_name: str) -> None:
        """Fetch all live params for *node_name*, merging with schema where available.

        Called on the ROS2 thread.  Emits ``signals.params_received``.
        An explicit fetch always bypasses the param-name cache so that a
        user-initiated refresh picks up any new or removed parameters.
        """
        self._param_names_cache.pop(node_name, None)
        param_values = self._build_param_values(node_name)
        # Update watcher baseline so poll doesn't flag these values as external changes.
        if self._watcher.watched_node == node_name:
            if any(pv.is_live for pv in param_values):
                self._watcher.set_baseline(param_values)
            else:
                self._watcher.clear_baseline()
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

        if node_name in self._param_names_cache:
            live_names = self._param_names_cache[node_name]
        else:
            try:
                live_names = [
                    n for n in self._param_client.list_params(node_name)
                    if not any(f in n for f in _PARAM_FILTER_SUBSTRINGS)
                ]
            except Exception as exc:
                self.get_logger().warning(
                    f"Unexpected error listing params for {node_name}: {exc}"
                )
                raise
            if live_names:
                self._param_names_cache[node_name] = live_names

        if not live_names:
            # Node offline — fall back to schema defaults so the panel isn't empty.
            return self._param_client.get_all_nav2_params(node_name, self._schema)

        try:
            live_typed = self._param_client.get_params(node_name, live_names)
        except Exception as exc:
            self.get_logger().warning(
                f"Unexpected error fetching param values for {node_name}: {exc}"
            )
            raise

        results: list[ParamValue] = []
        for name in live_names:
            schema_entry = self._find_schema_entry(node_name, name)
            entry = live_typed.get(name)
            value, ros2_type = entry if entry is not None else (None, None)

            if schema_entry:
                detected_type = self._detect_type(value, ros2_type) if value is not None else None
                if detected_type and detected_type != schema_entry.type:
                    self.get_logger().warning(
                        f"Schema type mismatch for {node_name}/{name}: schema says '{schema_entry.type}'"
                        f" but ROS2 reports '{detected_type}'. Using ROS2 type."
                    )
                    schema_entry = dataclasses.replace(schema_entry, type=detected_type)
                results.append(ParamValue(
                    definition=schema_entry,
                    current_value=value if value is not None else schema_entry.default,
                    is_modified=False,
                    is_live=(value is not None),
                    node_path=node_name,
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
                    node_path=node_name,
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
            # Empty list: can't infer element type from contents, so prefer
            # ros2_type when available rather than blindly returning string_array.
            if not value and ros2_type is not None and ros2_type in Nav2ConfigNode._ROS2_TYPE_MAP:
                return Nav2ConfigNode._ROS2_TYPE_MAP[ros2_type]
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
            success = self._service_caller.clear_costmaps(node_name)
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
            success, code = self._service_caller.load_map(map_url, node_name)
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
            success = self._service_caller.nomotion_update(node_name)
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
        self._discovered_managers = mgr_status
        active = set(mgr_status.keys())

        # Lazily create service clients for any newly discovered managers.
        with self._lifecycle_lock:
            for full_path in active:
                if full_path not in self._lifecycle_manager_clients:
                    self._lifecycle_manager_clients[full_path] = LifecycleManagerClient(
                        self, full_path, self._cb_group
                    )

        # Prune clients for managers that have disappeared from the graph.
        vanished_managers = set(self._lifecycle_manager_clients) - active
        with self._lifecycle_lock:
            for full_path in vanished_managers:
                mgr_client = self._lifecycle_manager_clients.pop(full_path)
                if mgr_client._client is not None:
                    try:
                        self.destroy_client(mgr_client._client)
                    except Exception as exc:
                        self.get_logger().debug(
                            f'Error destroying lifecycle_manager client for {full_path}: {exc}'
                        )
                self.get_logger().debug(f'Pruned lifecycle_manager client for {full_path}')

        # Rebuild node↔manager mappings on every tick so that changes to
        # node_names (e.g. dynamic plugin loads or namespace remaps) are
        # picked up without waiting for the manager set itself to change.
        # Per-manager we skip the write if the resolved node set is identical
        # to what we already have, avoiding unnecessary churn.
        # First-tick guard: increment seen count per manager; skip node_names read
        # on the very first appearance to avoid a thundering herd on stack startup.
        for full_path in active:
            self._manager_first_seen[full_path] = self._manager_first_seen.get(full_path, 0) + 1
        # Prune seen counts for managers that have vanished.
        for full_path in list(self._manager_first_seen):
            if full_path not in active:
                del self._manager_first_seen[full_path]

        new_node_to_manager: dict[str, str] = {}
        new_manager_to_nodes: dict[str, set[str]] = {}
        for full_path, manager in mgr_status.items():
            # Skip reading node_names on the very first tick for this manager.
            if self._manager_first_seen.get(full_path, 0) <= 1:
                self.get_logger().debug(
                    f"lifecycle_manager {full_path}: first-tick skip of node_names read"
                )
                continue
            try:
                result = self._param_client.get_params(full_path, ["node_names"])
                relative_names = result.get("node_names", (None, None))[0]
                if not relative_names:
                    self.get_logger().debug(
                        f"lifecycle_manager {full_path}: node_names param missing or empty"
                    )
                    continue
                if not isinstance(relative_names, list):
                    self.get_logger().warning(
                        f"lifecycle_manager {full_path} node_names is not a list "
                        f"(got {type(relative_names).__name__}), skipping"
                    )
                    continue
                valid_names: list[str] = []
                for item in relative_names:
                    if not isinstance(item, str):
                        self.get_logger().warning(
                            f"lifecycle_manager {full_path} node_names contains "
                            f"non-string entry: {item}, skipping"
                        )
                    elif item:
                        valid_names.append(item)
                node_paths: set[str] = set()
                for rel in valid_names:
                    node_path = join_ros_path(manager.stack_namespace, rel)
                    new_node_to_manager[node_path] = full_path
                    node_paths.add(node_path)
                # Only update this manager's entry when the node set has changed.
                if node_paths != self._manager_to_nodes.get(full_path):
                    new_manager_to_nodes[full_path] = node_paths
                else:
                    new_manager_to_nodes[full_path] = self._manager_to_nodes[full_path]
            except Exception as exc:
                self.get_logger().debug(
                    f"Could not read node_names from {full_path}: {exc}"
                )
        self._node_to_manager = new_node_to_manager
        self._manager_to_nodes = new_manager_to_nodes

        with self._lifecycle_lock:
            if active == self._active_lifecycle_managers:
                return
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

    # ------------------------------------------------------------------
    # AMCL pose preservation helpers (ROS2 thread only)
    # ------------------------------------------------------------------

    def _find_amcl_nodes(self) -> list[str]:
        """Return sorted full paths of currently discovered AMCL nodes."""
        return sorted(
            p for p in (self._prev_discovered or set())
            if path_basename(p) == 'amcl'
        )

    def _amcl_pose_topic(self, amcl_path: str) -> str:
        """Return the /amcl_pose topic for *amcl_path*.

        Examples::
            '/amcl'         -> '/amcl_pose'
            '/robot1/amcl'  -> '/robot1/amcl_pose'
        """
        ns = amcl_path.rsplit('/', 1)[0] or '/'
        return '/amcl_pose' if ns == '/' else f'{ns}/amcl_pose'

    def _initialpose_topic(self, amcl_path: str) -> str:
        """Return the /initialpose topic for *amcl_path*.

        Examples::
            '/amcl'         -> '/initialpose'
            '/robot1/amcl'  -> '/robot1/initialpose'
        """
        ns = amcl_path.rsplit('/', 1)[0] or '/'
        return '/initialpose' if ns == '/' else f'{ns}/initialpose'

    def _capture_amcl_pose(self, amcl_path: str) -> object | None:
        """Subscribe to the amcl_pose topic and return the first message within 1 s.

        Creates a transient subscription on the ROS2 node, waits for one
        message using a ``threading.Event``, then destroys the subscription.
        The ``MultiThreadedExecutor`` with ``ReentrantCallbackGroup`` delivers
        the subscription callback on a different thread while this one blocks.

        Returns:
            A deep copy of the ``PoseWithCovarianceStamped`` message, or
            ``None`` if no message arrives within 1 second (topic not
            published, or AMCL not yet localised).
        """
        from geometry_msgs.msg import PoseWithCovarianceStamped
        topic = self._amcl_pose_topic(amcl_path)
        captured: list[object] = [None]
        event = threading.Event()

        def _cb(msg: 'PoseWithCovarianceStamped') -> None:
            captured[0] = copy.deepcopy(msg)
            event.set()

        sub = self.create_subscription(
            PoseWithCovarianceStamped, topic, _cb, 10,
            callback_group=self._cb_group,
        )
        try:
            event.wait(timeout=1.0)
        finally:
            self.destroy_subscription(sub)
        return captured[0]

    def _wait_for_amcl_active(self, amcl_path: str, timeout_sec: float = 15.0) -> bool:
        """Poll *amcl_path* lifecycle state every 500 ms until active or timeout.

        Blocks the calling (ROS2) thread without touching the Qt main thread.

        Returns:
            ``True`` if AMCL reaches ``active`` within *timeout_sec*.
        """
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            state = self._lifecycle_client.get_state(amcl_path, availability_timeout=0.5)
            if state == 'active':
                return True
            time.sleep(0.5)
        return False

    def _publish_initial_pose(self, amcl_path: str, pose_msg: object) -> None:
        """Publish *pose_msg* to /initialpose with a fresh header timestamp.

        Creates and caches a publisher per topic so repeated restarts do not
        leak publishers.  Sets ``header.frame_id = 'map'`` and stamps to the
        current ROS2 clock so AMCL accepts the message.

        Args:
            amcl_path: Full ROS2 path of the AMCL node (derives topic name).
            pose_msg: A captured ``PoseWithCovarianceStamped`` to republish.
        """
        from geometry_msgs.msg import PoseWithCovarianceStamped
        topic = self._initialpose_topic(amcl_path)
        if topic not in self._initialpose_pubs:
            self._initialpose_pubs[topic] = self.create_publisher(
                PoseWithCovarianceStamped, topic, 10
            )
        pub = self._initialpose_pubs[topic]
        msg = copy.deepcopy(pose_msg)
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        pub.publish(msg)

    def _restore_amcl_poses(self, captured_poses: dict[str, object]) -> None:
        """Wait for each captured AMCL to become active, then republish its pose.

        Args:
            captured_poses: Mapping of amcl_path → captured PoseWithCovarianceStamped.
                Only paths present in this dict are processed.
        """
        if not captured_poses:
            return
        self.signals.amcl_pose_status.emit('Waiting for AMCL...')
        for amcl_path, pose in captured_poses.items():
            if self._wait_for_amcl_active(amcl_path):
                self._publish_initial_pose(amcl_path, pose)
                self.get_logger().info(f'AMCL pose restored for {amcl_path}')
                self.signals.amcl_pose_status.emit('Pose restored')
            else:
                self.get_logger().warning(
                    f'AMCL {amcl_path} did not become active within 15 s — '
                    'pose restoration skipped'
                )
                self.signals.amcl_pose_status.emit('Pose restoration skipped')

    def _do_lifecycle_manager_restart(self) -> None:
        """Restart all Nav2 nodes via all active lifecycle_managers.

        If no lifecycle_manager is detected, falls back to the direct
        per-node restart sequence.  Emits ``lifecycle_progress`` and
        a single aggregated ``lifecycle_change_result``.

        Preserves AMCL localisation pose across the restart: captures the
        last published /amcl_pose before RESET, waits for AMCL to return to
        ``active``, then republishes to /initialpose.
        """
        # Capture AMCL pose(s) before the restart tears down the node state.
        amcl_nodes = self._find_amcl_nodes()
        captured_poses: dict[str, object] = {}
        if amcl_nodes:
            self.signals.amcl_pose_status.emit('Restarting Nav2... capturing pose')
            for amcl_path in amcl_nodes:
                pose = self._capture_amcl_pose(amcl_path)
                if pose is not None:
                    captured_poses[amcl_path] = pose
                    self.get_logger().info(f'AMCL pose captured for {amcl_path}')
                else:
                    self.get_logger().warning(
                        f'No AMCL pose within 1 s for {amcl_path} — restoration skipped'
                    )

        if not self._active_lifecycle_managers:
            self.get_logger().warning(
                'request_nav2_stack_restart: no lifecycle_manager detected, '
                'falling back to direct per-node restart'
            )
            self._do_lifecycle_restart_all_impl()
            self._restore_amcl_poses(captured_poses)
            return

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in sorted(self._active_lifecycle_managers):
            client = self._lifecycle_manager_clients[mgr_path]

            def _progress(step: str, _mgr: str = mgr_path) -> None:
                self.signals.lifecycle_progress.emit(_mgr, step)

            ok, msg = client.restart_stack(
                progress_cb=_progress,
                lifecycle_client=self._lifecycle_client,
                discovered_nodes=self._prev_discovered or set(),
            )
            self.get_logger().info(f'lifecycle_manager restart via {mgr_path}: {msg}')
            short = mgr_path.lstrip('/')
            if ok:
                succeeded.append(f'{short} → ok')
            else:
                failed.append(f'{short} → failed ({msg})')

        all_ok = not failed
        if not failed:
            summary = 'Stack restarted successfully'
        elif not succeeded:
            summary = 'Failed: ' + '; '.join(failed)
        else:
            summary = 'Partial: ' + '; '.join(succeeded + failed)
        self.signals.lifecycle_change_result.emit('', all_ok, summary)

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

        # Restore AMCL pose(s) once nodes are active again.
        self._restore_amcl_poses(captured_poses)

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

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in sorted(self._active_lifecycle_managers):
            ok = self._lifecycle_manager_clients[mgr_path].pause()
            short = mgr_path.lstrip('/')
            self.get_logger().info(
                f'lifecycle_manager pause via {mgr_path}: {"ok" if ok else "failed"}'
            )
            (succeeded if ok else failed).append(short)

        all_ok = not failed
        if not failed:
            msg = 'Stack paused (nodes inactive)'
        elif not succeeded:
            msg = 'Pause failed: ' + '; '.join(f'{m} → failed' for m in failed)
        else:
            msg = ('Partial: '
                   + '; '.join(f'{m} → ok' for m in succeeded)
                   + '; '
                   + '; '.join(f'{m} → failed' for m in failed))
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

    def _do_lifecycle_manager_resume(self) -> None:
        """Resume all Nav2 nodes via all active lifecycle_managers.

        Reactivates all managed nodes from ``inactive`` back to ``active``
        state using the RESUME command — the lightweight counterpart to
        :meth:`_do_lifecycle_manager_pause`.  If no lifecycle_manager is
        detected, emits a failure result so the GUI can report it.
        """
        if not self._active_lifecycle_managers:
            self.get_logger().warning(
                'request_lifecycle_resume_stack: no lifecycle_manager detected — cannot resume'
            )
            self.signals.lifecycle_change_result.emit(
                '', False, 'Resume failed: lifecycle_manager not found'
            )
            return

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in sorted(self._active_lifecycle_managers):
            ok = self._lifecycle_manager_clients[mgr_path].resume()
            short = mgr_path.lstrip('/')
            self.get_logger().info(
                f'lifecycle_manager resume via {mgr_path}: {"ok" if ok else "failed"}'
            )
            (succeeded if ok else failed).append(short)

        all_ok = not failed
        if not failed:
            msg = 'Stack resumed (nodes active)'
        elif not succeeded:
            msg = 'Resume failed: ' + '; '.join(f'{m} → failed' for m in failed)
        else:
            msg = ('Partial: '
                   + '; '.join(f'{m} → ok' for m in succeeded)
                   + '; '
                   + '; '.join(f'{m} → failed' for m in failed))
        self.signals.lifecycle_change_result.emit('', all_ok, msg)

        # Re-poll states so the GUI reflects active immediately.
        discovered = self._prev_discovered or set()
        new_states: dict[str, str] = {}
        for path in discovered:
            new_states[path] = self._lifecycle_client.get_state(
                path, availability_timeout=0.5
            )
        self._lifecycle_states.update(new_states)
        if new_states:
            self.signals.lifecycle_states_updated.emit(new_states)

    def _managers_for_namespace(self, stack_namespace: str) -> list[str]:
        """Return sorted full_paths of active managers whose stack_namespace matches.

        Args:
            stack_namespace: The stack root namespace to filter by.

        Returns:
            Sorted list of lifecycle_manager full_paths in the target namespace.
        """
        return sorted(
            mgr_path
            for mgr_path, mgr in self._discovered_managers.items()
            if mgr.stack_namespace == stack_namespace
            and mgr_path in self._active_lifecycle_managers
        )

    def _do_lifecycle_manager_restart_ns(self, stack_namespace: str) -> None:
        """Restart Nav2 nodes via lifecycle_managers in *stack_namespace* only.

        Falls back to direct per-node restart scoped to *stack_namespace* if no
        matching lifecycle_manager is found.  Never touches nodes outside the
        requested namespace.
        """
        targets = self._managers_for_namespace(stack_namespace)
        if not targets:
            self.get_logger().warning(
                f'No nodes found for namespace {stack_namespace}'
            )
            ns_nodes = {
                path
                for path in (self._prev_discovered or set())
                if infer_stack_namespace(path, path_basename(path)) == stack_namespace
            }
            if not ns_nodes:
                self.get_logger().warning(
                    f'No nodes found for namespace {stack_namespace}'
                )
                self.signals.lifecycle_change_result.emit(
                    '',
                    False,
                    f'Restart failed: no nodes found for namespace {stack_namespace!r}',
                )
                return

            def _progress(node_name: str, step: str) -> None:
                self.signals.lifecycle_progress.emit(node_name, step)

            results = self._lifecycle_client.restart_all_nav2(
                ns_nodes, progress_cb=_progress
            )

            for node_name, (success, msg) in results.items():
                self.signals.lifecycle_change_result.emit(node_name, success, msg)
                self.get_logger().info(f'restart_ns_fallback {node_name}: {msg}')

            new_states: dict[str, str] = {}
            for path in ns_nodes:
                new_states[path] = self._lifecycle_client.get_state(
                    path, availability_timeout=0.5
                )
            self._lifecycle_states.update(new_states)
            if new_states:
                self.signals.lifecycle_states_updated.emit(new_states)
            return

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in targets:
            client = self._lifecycle_manager_clients[mgr_path]

            def _progress(step: str, _mgr: str = mgr_path) -> None:
                self.signals.lifecycle_progress.emit(_mgr, step)

            ok, msg = client.restart_stack(
                progress_cb=_progress,
                lifecycle_client=self._lifecycle_client,
                discovered_nodes=self._prev_discovered or set(),
            )
            self.get_logger().info(f'lifecycle_manager restart via {mgr_path}: {msg}')
            short = mgr_path.lstrip('/')
            if ok:
                succeeded.append(f'{short} → ok')
            else:
                failed.append(f'{short} → failed ({msg})')

        all_ok = not failed
        if not failed:
            summary = 'Stack restarted successfully'
        elif not succeeded:
            summary = 'Failed: ' + '; '.join(failed)
        else:
            summary = 'Partial: ' + '; '.join(succeeded + failed)
        self.signals.lifecycle_change_result.emit('', all_ok, summary)

        discovered = self._prev_discovered or set()
        new_states: dict[str, str] = {}
        for path in discovered:
            new_states[path] = self._lifecycle_client.get_state(
                path, availability_timeout=0.5
            )
        self._lifecycle_states.update(new_states)
        if new_states:
            self.signals.lifecycle_states_updated.emit(new_states)

    def _do_lifecycle_manager_pause_ns(self, stack_namespace: str) -> None:
        """Pause Nav2 nodes via lifecycle_managers in *stack_namespace* only."""
        targets = self._managers_for_namespace(stack_namespace)
        if not targets:
            self.get_logger().warning(
                f'request_lifecycle_pause_stack_ns: no lifecycle_manager found for '
                f'namespace {stack_namespace!r} — cannot pause'
            )
            self.signals.lifecycle_change_result.emit(
                '', False, f'Pause failed: no lifecycle_manager for {stack_namespace!r}'
            )
            return

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in targets:
            ok = self._lifecycle_manager_clients[mgr_path].pause()
            short = mgr_path.lstrip('/')
            self.get_logger().info(
                f'lifecycle_manager pause via {mgr_path}: {"ok" if ok else "failed"}'
            )
            (succeeded if ok else failed).append(short)

        all_ok = not failed
        if not failed:
            msg = 'Stack paused (nodes inactive)'
        elif not succeeded:
            msg = 'Pause failed: ' + '; '.join(f'{m} → failed' for m in failed)
        else:
            msg = ('Partial: '
                   + '; '.join(f'{m} → ok' for m in succeeded)
                   + '; '
                   + '; '.join(f'{m} → failed' for m in failed))
        self.signals.lifecycle_change_result.emit('', all_ok, msg)

        discovered = self._prev_discovered or set()
        new_states: dict[str, str] = {}
        for path in discovered:
            new_states[path] = self._lifecycle_client.get_state(
                path, availability_timeout=0.5
            )
        self._lifecycle_states.update(new_states)
        if new_states:
            self.signals.lifecycle_states_updated.emit(new_states)

    def _do_lifecycle_manager_resume_ns(self, stack_namespace: str) -> None:
        """Resume Nav2 nodes via lifecycle_managers in *stack_namespace* only."""
        targets = self._managers_for_namespace(stack_namespace)
        if not targets:
            self.get_logger().warning(
                f'request_lifecycle_resume_stack_ns: no lifecycle_manager found for '
                f'namespace {stack_namespace!r} — cannot resume'
            )
            self.signals.lifecycle_change_result.emit(
                '', False, f'Resume failed: no lifecycle_manager for {stack_namespace!r}'
            )
            return

        succeeded: list[str] = []
        failed: list[str] = []
        for mgr_path in targets:
            ok = self._lifecycle_manager_clients[mgr_path].resume()
            short = mgr_path.lstrip('/')
            self.get_logger().info(
                f'lifecycle_manager resume via {mgr_path}: {"ok" if ok else "failed"}'
            )
            (succeeded if ok else failed).append(short)

        all_ok = not failed
        if not failed:
            msg = 'Stack resumed (nodes active)'
        elif not succeeded:
            msg = 'Resume failed: ' + '; '.join(f'{m} → failed' for m in failed)
        else:
            msg = ('Partial: '
                   + '; '.join(f'{m} → ok' for m in succeeded)
                   + '; '
                   + '; '.join(f'{m} → failed' for m in failed))
        self.signals.lifecycle_change_result.emit('', all_ok, msg)

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
        """Restart all discovered Nav2 nodes in lifecycle order, with pose preservation.

        Public entry point called when the user triggers a direct per-node
        restart (no lifecycle_manager).  Captures AMCL pose(s) before the
        restart, runs the bare restart, then restores the pose(s).
        """
        amcl_nodes = self._find_amcl_nodes()
        captured_poses: dict[str, object] = {}
        if amcl_nodes:
            self.signals.amcl_pose_status.emit('Restarting Nav2... capturing pose')
            for amcl_path in amcl_nodes:
                pose = self._capture_amcl_pose(amcl_path)
                if pose is not None:
                    captured_poses[amcl_path] = pose
                    self.get_logger().info(f'AMCL pose captured for {amcl_path}')
                else:
                    self.get_logger().warning(
                        f'No AMCL pose within 1 s for {amcl_path} — restoration skipped'
                    )

        self._do_lifecycle_restart_all_impl()
        self._restore_amcl_poses(captured_poses)

    def _do_lifecycle_restart_all_impl(self) -> None:
        """Bare restart of all discovered Nav2 nodes in lifecycle order.

        Emits ``lifecycle_progress`` per step, ``lifecycle_change_result`` per
        node, and ``lifecycle_states_updated`` when finished.  Does not touch
        AMCL pose — callers are responsible for pose capture/restore.
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

    def _do_load_map(self, map_url: str, node_name: str = "/map_server") -> None:
        """Call the load_map service for *node_name* to reload the map at runtime.

        Delegates to :class:`Nav2ServiceCaller` so that namespace resolution is
        handled consistently (e.g. ``/robot1/map_server`` → ``/robot1/map_server/load_map``).

        Called on the ROS2 thread.  Emits ``signals.load_map_result``.

        Args:
            map_url: Absolute path to the map YAML file to load.
            node_name: Full ROS2 path of the map_server node, e.g.
                ``/robot1/map_server``.  Defaults to ``/map_server``.
        """
        success, code = self._service_caller.load_map(map_url, node_name)
        if success:
            msg = f'Map loaded: {map_url}'
            self.get_logger().info(msg)
        else:
            _code_msgs = {
                1: 'map file not found',
                2: 'invalid map',
                3: 'load_map service unavailable',
            }
            detail = _code_msgs.get(code, f'result code {code}')
            msg = f'load_map failed: {detail}'
            self.get_logger().warning(msg)
        self.signals.load_map_result.emit(success, msg)
