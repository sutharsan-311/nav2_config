# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ROS2 lifecycle service client for Nav2 nodes.

All public methods are synchronous and must be called from the ROS2 thread.
Service clients are created lazily and cached per node to avoid re-creation overhead.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Callable

from lifecycle_msgs.msg import Transition
from lifecycle_msgs.srv import ChangeState, GetState

try:
    from nav2_msgs.srv import ManageLifecycleNodes as _ManageNodes
    _HAS_NAV2_MSGS = True
except ImportError:
    _ManageNodes = None  # type: ignore[assignment, misc]
    _HAS_NAV2_MSGS = False

if TYPE_CHECKING:
    from rclpy.callback_groups import CallbackGroup
    from rclpy.node import Node

from nav2_config.core.node_discovery import NAV2_NODES

logger = logging.getLogger(__name__)

#: Seconds to wait for a lifecycle service response before giving up.
_SERVICE_TIMEOUT: float = 5.0

#: Seconds to wait for a service to become available before giving up.
_AVAILABILITY_TIMEOUT: float = 2.0

#: Short timeout used when polling lifecycle state for all discovered nodes.
_POLL_AVAILABILITY_TIMEOUT: float = 0.3

#: Restart order derived from NAV2_NODES — single source of truth, includes costmap nodes.
NAV2_RESTART_ORDER: list[str] = list(NAV2_NODES.keys())


class LifecycleClient:
    """Synchronous client for ROS2 lifecycle services on Nav2 nodes.

    Service clients are created lazily and cached so that repeated calls to the
    same node do not incur re-creation overhead.

    All methods block until the service responds or a timeout expires.  They
    must be called from the ROS2 spin thread (never from the Qt main thread).
    Uses ``threading.Event`` rather than ``rclpy.spin_until_future_complete``
    so that calls are safe inside a running ``MultiThreadedExecutor``.

    Args:
        node: The ``rclpy.Node`` used to create service clients.
        callback_group: Optional callback group for the clients.
    """

    def __init__(self, node: 'Node', callback_group: 'CallbackGroup | None' = None) -> None:
        self._node = node
        self._callback_group = callback_group
        self._get_clients: dict[str, object] = {}
        self._change_clients: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_state_client(self, node_name: str) -> object:
        """Return a cached (or newly created) GetState client for *node_name*."""
        if node_name not in self._get_clients:
            svc = f'{node_name}/get_state'
            self._get_clients[node_name] = self._node.create_client(
                GetState, svc, callback_group=self._callback_group
            )
        return self._get_clients[node_name]

    def _change_state_client(self, node_name: str) -> object:
        """Return a cached (or newly created) ChangeState client for *node_name*."""
        if node_name not in self._change_clients:
            svc = f'{node_name}/change_state'
            self._change_clients[node_name] = self._node.create_client(
                ChangeState, svc, callback_group=self._callback_group
            )
        return self._change_clients[node_name]

    def _call(
        self,
        client: object,
        request: object,
        availability_timeout: float = _AVAILABILITY_TIMEOUT,
    ) -> object | None:
        """Send *request* and block until the response arrives or times out.

        Uses ``threading.Event`` so that this is safe to call from inside a
        running executor callback (the ``MultiThreadedExecutor`` can process
        the response on a different thread while this one waits).

        Returns:
            The response object, or ``None`` on timeout or service unavailable.
        """
        if not client.wait_for_service(timeout_sec=availability_timeout):
            return None

        future = client.call_async(request)
        done_event = threading.Event()
        result_holder: list[object] = [None]

        def _on_done(fut: object) -> None:
            try:
                result_holder[0] = fut.result()
            except Exception as exc:
                logger.warning('Lifecycle service call failed on %s: %s', client.srv_name, exc)
            finally:
                done_event.set()

        future.add_done_callback(_on_done)
        if not done_event.wait(timeout=_SERVICE_TIMEOUT):
            logger.warning('Lifecycle service call timed out for %s', client.srv_name)
            return None
        return result_holder[0]

    # ------------------------------------------------------------------
    # Public API — state query
    # ------------------------------------------------------------------

    def get_state(
        self,
        node_name: str,
        availability_timeout: float = _AVAILABILITY_TIMEOUT,
    ) -> str:
        """Call ``/{node_name}/get_state`` and return the state label.

        Args:
            node_name: Full ROS2 node path, e.g. ``'/controller_server'``.
            availability_timeout: How long to wait for the service to appear.
                Use a short value (e.g. 0.3 s) when polling many nodes.

        Returns:
            State label: ``'unconfigured'``, ``'inactive'``, ``'active'``,
            ``'finalized'``, or ``'unknown'`` if unavailable / timed out.
        """
        client = self._get_state_client(node_name)
        response = self._call(client, GetState.Request(), availability_timeout)
        if response is not None:
            return response.current_state.label
        return 'unknown'

    # ------------------------------------------------------------------
    # Public API — state transitions
    # ------------------------------------------------------------------

    def change_state(self, node_name: str, transition_id: int) -> bool:
        """Call ``/{node_name}/change_state`` with *transition_id*.

        Args:
            node_name: Full ROS2 node path.
            transition_id: One of the ``Transition.TRANSITION_*`` constants.

        Returns:
            ``True`` if the transition was accepted and succeeded.
        """
        client = self._change_state_client(node_name)
        req = ChangeState.Request()
        req.transition.id = transition_id
        response = self._call(client, req)
        if response is not None:
            if not response.success:
                logger.warning(
                    'Transition %d rejected by %s', transition_id, node_name
                )
            return response.success
        logger.warning(
            'change_state timed out for %s (transition %d)', node_name, transition_id
        )
        return False

    def configure(self, node_name: str) -> bool:
        """Transition node from ``unconfigured`` → ``inactive``."""
        return self.change_state(node_name, Transition.TRANSITION_CONFIGURE)

    def activate(self, node_name: str) -> bool:
        """Transition node from ``inactive`` → ``active``."""
        return self.change_state(node_name, Transition.TRANSITION_ACTIVATE)

    def deactivate(self, node_name: str) -> bool:
        """Transition node from ``active`` → ``inactive``."""
        return self.change_state(node_name, Transition.TRANSITION_DEACTIVATE)

    def cleanup(self, node_name: str) -> bool:
        """Transition node from ``inactive`` → ``unconfigured``."""
        return self.change_state(node_name, Transition.TRANSITION_CLEANUP)

    def shutdown(self, node_name: str) -> bool:
        """Shut down *node_name* using the appropriate shutdown transition.

        Queries current state first and picks the matching shutdown transition:
        - active → TRANSITION_ACTIVE_SHUTDOWN
        - inactive → TRANSITION_INACTIVE_SHUTDOWN
        - unconfigured → TRANSITION_UNCONFIGURED_SHUTDOWN

        Returns:
            ``True`` if the node accepted the shutdown transition.
        """
        state = self.get_state(node_name, availability_timeout=_POLL_AVAILABILITY_TIMEOUT)
        if state == 'active':
            return self.change_state(node_name, Transition.TRANSITION_ACTIVE_SHUTDOWN)
        if state == 'inactive':
            return self.change_state(node_name, Transition.TRANSITION_INACTIVE_SHUTDOWN)
        if state == 'unconfigured':
            return self.change_state(
                node_name, Transition.TRANSITION_UNCONFIGURED_SHUTDOWN
            )
        logger.warning('Cannot shut down %s: current state is %r', node_name, state)
        return False

    # ------------------------------------------------------------------
    # Public API — compound operations
    # ------------------------------------------------------------------

    def restart(
        self,
        node_name: str,
        progress_cb: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Full restart sequence, starting from the node's current state.

        Queries current state first and skips transitions that have already
        happened:
        - active       → deactivate → cleanup → configure → activate
        - inactive     →              cleanup → configure → activate
        - unconfigured →                        configure → activate

        Args:
            node_name: Full ROS2 node path.
            progress_cb: Optional callback invoked before each step with the
                step description (e.g. ``"Deactivating"``).

        Returns:
            ``(success, message)`` — if a step fails, *message* names the step.
        """
        current_state = self.get_state(node_name, availability_timeout=_POLL_AVAILABILITY_TIMEOUT)

        if current_state == 'active':
            steps = [
                ('Deactivating', self.deactivate),
                ('Cleaning up', self.cleanup),
                ('Configuring', self.configure),
                ('Activating', self.activate),
            ]
        elif current_state == 'inactive':
            steps = [
                ('Cleaning up', self.cleanup),
                ('Configuring', self.configure),
                ('Activating', self.activate),
            ]
        elif current_state == 'unconfigured':
            steps = [
                ('Configuring', self.configure),
                ('Activating', self.activate),
            ]
        else:
            return False, f'Cannot restart: current state is {current_state!r}'

        for step_name, func in steps:
            if progress_cb:
                progress_cb(step_name)
            logger.info('Restart %s: %s', node_name, step_name)
            if not func(node_name):
                msg = f'Failed at: {step_name}'
                logger.warning('Restart %s: %s', node_name, msg)
                return False, msg
        return True, 'Restart complete'

    def restart_all_nav2(
        self,
        discovered_nodes: set[str],
        progress_cb: Callable[[str, str], None] | None = None,
    ) -> dict[str, tuple[bool, str]]:
        """Restart all discovered Nav2 nodes in the correct lifecycle order.

        Sequence:
        1. Deactivate all in reverse order
        2. Cleanup all in reverse order
        3. Configure all in forward order
        4. Activate all in forward order

        Args:
            discovered_nodes: Set of currently-running node paths.
            progress_cb: Optional ``(node_name, step)`` callback for progress
                reporting; called before each per-node transition attempt.

        Returns:
            ``{node_name: (success, message)}`` for each node in *discovered_nodes*
            that appears in :data:`NAV2_RESTART_ORDER`.
        """
        ordered = [n for n in NAV2_RESTART_ORDER if n in discovered_nodes]
        failed: set[str] = set()
        results: dict[str, tuple[bool, str]] = {}

        def _step(node_name: str, step: str, func: Callable[[str], bool]) -> bool:
            if progress_cb:
                progress_cb(node_name, step)
            ok = func(node_name)
            if not ok:
                failed.add(node_name)
                results[node_name] = (False, f'Failed at: {step}')
                logger.warning('restart_all: %s failed at %s', node_name, step)
            return ok

        for node_name in reversed(ordered):
            _step(node_name, 'Deactivating', self.deactivate)

        for node_name in reversed(ordered):
            if node_name not in failed:
                _step(node_name, 'Cleaning up', self.cleanup)

        for node_name in ordered:
            if node_name not in failed:
                _step(node_name, 'Configuring', self.configure)

        for node_name in ordered:
            if node_name not in failed:
                ok = _step(node_name, 'Activating', self.activate)
                if ok:
                    results[node_name] = (True, 'Restarted')

        return results


# ---------------------------------------------------------------------------
# ManageLifecycleNodes command codes (from nav2_msgs/srv/ManageLifecycleNodes)
# ---------------------------------------------------------------------------
_MGR_STARTUP  = 0
_MGR_PAUSE    = 1
_MGR_RESUME   = 2
_MGR_RESET    = 3
_MGR_SHUTDOWN = 4

#: Seconds to wait for lifecycle_manager's manage_nodes service call.
_MGR_CALL_TIMEOUT: float = 30.0


class LifecycleManagerClient:
    """Client for Nav2's lifecycle_manager ``manage_nodes`` service.

    Uses :class:`nav2_msgs.srv.ManageLifecycleNodes` to safely RESET and
    STARTUP all Nav2 nodes through lifecycle_manager rather than directly
    transitioning individual nodes.  Direct per-node transitions cause
    lifecycle_manager's bond monitoring to detect a ``CRITICAL FAILURE`` and
    tear down the entire stack.

    Falls back gracefully if ``nav2_msgs`` is not installed — callers should
    check :attr:`available` before using this client.

    Args:
        node: The rclpy Node used to create the service client.
        manager_path: Full ROS2 path of the lifecycle_manager node,
            e.g. ``'/lifecycle_manager_navigation'``.
        callback_group: Optional callback group for the service client.
    """

    def __init__(
        self,
        node: 'Node',
        manager_path: str,
        callback_group: 'CallbackGroup | None' = None,
    ) -> None:
        self._node = node
        self._manager_path = manager_path
        self._client: object | None = None
        if _HAS_NAV2_MSGS:
            svc = f'{manager_path}/manage_nodes'
            self._client = node.create_client(
                _ManageNodes, svc, callback_group=callback_group
            )

    @property
    def available(self) -> bool:
        """``True`` if ``nav2_msgs`` is installed (service may or may not be running)."""
        return _HAS_NAV2_MSGS

    def is_service_ready(self, timeout_sec: float = 1.0) -> bool:
        """Check if the manage_nodes service is currently reachable."""
        if self._client is None:
            return False
        return self._client.wait_for_service(timeout_sec=timeout_sec)

    def _call_command(self, command: int) -> bool:
        """Send *command* to manage_nodes and return success flag."""
        if self._client is None:
            logger.warning('LifecycleManagerClient: nav2_msgs not available')
            return False
        if not self._client.wait_for_service(timeout_sec=2.0):
            logger.warning(
                'lifecycle_manager %s: manage_nodes service not available',
                self._manager_path,
            )
            return False

        req = _ManageNodes.Request()
        req.command = command
        future = self._client.call_async(req)
        done_event = threading.Event()
        result_holder: list[object] = [None]

        def _on_done(fut: object) -> None:
            try:
                result_holder[0] = fut.result()
            except Exception as exc:
                logger.warning(
                    'lifecycle_manager %s command %d failed: %s',
                    self._manager_path, command, exc,
                )
            finally:
                done_event.set()

        future.add_done_callback(_on_done)
        if not done_event.wait(timeout=_MGR_CALL_TIMEOUT):
            logger.warning(
                'lifecycle_manager %s: command %d timed out after %.0fs',
                self._manager_path, command, _MGR_CALL_TIMEOUT,
            )
            return False

        response = result_holder[0]
        return bool(getattr(response, 'success', False))

    def reset(self) -> bool:
        """Send RESET — all managed nodes go to ``unconfigured`` state."""
        logger.info('lifecycle_manager %s: sending RESET', self._manager_path)
        return self._call_command(_MGR_RESET)

    def startup(self) -> bool:
        """Send STARTUP — all managed nodes go to ``active`` state."""
        logger.info('lifecycle_manager %s: sending STARTUP', self._manager_path)
        return self._call_command(_MGR_STARTUP)

    def pause(self) -> bool:
        """Send PAUSE — deactivates all managed nodes without cleanup.

        Nodes land in ``inactive`` state and can be resumed cheaply with
        :meth:`startup` (STARTUP).  This is the safe way to temporarily halt
        navigation without a full RESET/STARTUP cycle.
        """
        logger.info('lifecycle_manager %s: sending PAUSE', self._manager_path)
        return self._call_command(_MGR_PAUSE)

    def restart_stack(
        self,
        progress_cb: Callable[[str], None] | None = None,
    ) -> tuple[bool, str]:
        """Full stack restart: RESET then STARTUP via lifecycle_manager.

        This is the safe way to restart Nav2 nodes when lifecycle_manager is
        running.  Directly deactivating individual nodes would cause
        lifecycle_manager to detect a bond failure and tear down the whole stack.

        Args:
            progress_cb: Optional callback invoked before each step with a
                human-readable step description.

        Returns:
            ``(success, message)``
        """
        if not _HAS_NAV2_MSGS:
            return (
                False,
                'nav2_msgs not installed — cannot use lifecycle_manager service. '
                'Restart Nav2 manually.',
            )

        if progress_cb:
            progress_cb('Resetting all nodes via lifecycle_manager')
        if not self.reset():
            return False, 'RESET command to lifecycle_manager failed'

        if progress_cb:
            progress_cb('Starting up all nodes via lifecycle_manager')
        if not self.startup():
            return False, 'STARTUP command to lifecycle_manager failed'

        return True, 'Nav2 stack restarted successfully'
