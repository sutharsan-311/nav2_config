# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Nav2 service caller — fires follow-up services after parameter changes."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from nav2_config.core.node_discovery import path_basename, infer_stack_namespace, join_ros_path

if TYPE_CHECKING:
    from rclpy.node import Node
    from rclpy.callback_groups import CallbackGroup


class Nav2ServiceCaller:
    """Calls Nav2 services after parameter changes.

    All methods are synchronous (block until the service call completes or
    times out) and are intended to run on the ROS2 background thread, not
    the Qt main thread.
    """

    # Seconds to wait for a service to become available before giving up.
    SERVICE_TIMEOUT: float = 2.0
    # Seconds to wait for a service response.
    CALL_TIMEOUT: float = 10.0

    def __init__(self, node: "Node", cb_group: "CallbackGroup") -> None:
        self._node = node
        self._cb_group = cb_group
        # Service clients created lazily on first use, keyed by (SrvType, service_name).
        self._clients: dict[tuple[type, str], Any] = {}
        self._clients_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def clear_costmaps(self, node_path: str) -> bool:
        """Call clear_entirely on both global and local costmaps.

        Resolves service paths relative to the stack namespace derived from
        *node_path*, so namespaced deployments (e.g. /robot1/...) work correctly.

        Args:
            node_path: Full ROS2 path of the node that triggered the action,
                e.g. ``/robot1/controller_server``.

        Returns:
            True if both calls succeed, False otherwise.
        """
        from nav2_msgs.srv import ClearEntireCostmap

        stack_ns = infer_stack_namespace(node_path, path_basename(node_path))
        global_svc = join_ros_path(stack_ns, "global_costmap/clear_entirely_global_costmap")
        local_svc = join_ros_path(stack_ns, "local_costmap/clear_entirely_local_costmap")

        key_global = (ClearEntireCostmap, global_svc)
        with self._clients_lock:
            if key_global not in self._clients:
                self._clients[key_global] = self._node.create_client(
                    ClearEntireCostmap,
                    global_svc,
                    callback_group=self._cb_group,
                )

        key_local = (ClearEntireCostmap, local_svc)
        with self._clients_lock:
            if key_local not in self._clients:
                self._clients[key_local] = self._node.create_client(
                    ClearEntireCostmap,
                    local_svc,
                    callback_group=self._cb_group,
                )

        ok_global = self._call_empty_like(
            self._clients[key_global],
            ClearEntireCostmap.Request(),
            global_svc,
        )
        ok_local = self._call_empty_like(
            self._clients[key_local],
            ClearEntireCostmap.Request(),
            local_svc,
        )
        return ok_global and ok_local

    def load_map(self, map_url: str, node_path: str = "/map_server") -> tuple[bool, int]:
        """Call load_map with the given map file path.

        Resolves the service path relative to the stack namespace derived from
        *node_path*.

        Args:
            map_url: Absolute path to the map YAML file.
            node_path: Full ROS2 path of the node that triggered the action,
                e.g. ``/robot1/map_server``. Defaults to ``/map_server``.

        Returns:
            (success, result_code).
            Result codes: 0=success, 1=map_does_not_exist, 2=invalid_map, 3=undefined.
        """
        from nav2_msgs.srv import LoadMap

        # Do not check os.path.exists(map_url) here. When connected to a remote
        # robot the map file lives on the robot's filesystem, not the GUI laptop.
        # The ROS service will return result_code=1 (map_does_not_exist) if the
        # path cannot be resolved on the robot side.
        stack_ns = infer_stack_namespace(node_path, path_basename(node_path))
        svc = join_ros_path(stack_ns, "map_server/load_map")

        key = (LoadMap, svc)
        if key not in self._clients:
            self._clients[key] = self._node.create_client(
                LoadMap,
                svc,
                callback_group=self._cb_group,
            )
        client = self._clients[key]

        if not client.wait_for_service(timeout_sec=self.SERVICE_TIMEOUT):
            self._node.get_logger().warning(f'load_map service not available on {svc}')
            return False, 3

        req = LoadMap.Request()
        req.map_url = map_url
        response = self._call_sync(client, req)
        if response is None:
            return False, 3
        success = response.result == 0
        return success, int(response.result)

    def nomotion_update(self, node_path: str) -> bool:
        """Call request_nomotion_update to force AMCL to update without motion.

        Resolves the service path relative to the stack namespace derived from
        *node_path*.

        Args:
            node_path: Full ROS2 path of the node that triggered the action,
                e.g. ``/robot1/amcl``.

        Returns:
            True if the service call succeeded.
        """
        from std_srvs.srv import Empty

        stack_ns = infer_stack_namespace(node_path, path_basename(node_path))
        svc = join_ros_path(stack_ns, "request_nomotion_update")

        key = (Empty, svc)
        if key not in self._clients:
            self._clients[key] = self._node.create_client(
                Empty,
                svc,
                callback_group=self._cb_group,
            )

        return self._call_empty_like(self._clients[key], Empty.Request(), svc)

    def reinitialize_localization(self, node_path: str) -> bool:
        """Call reinitialize_global_localization to scatter AMCL particles.

        Useful after changing AMCL parameters drastically. Resolves the service
        path relative to the stack namespace derived from *node_path*.

        Args:
            node_path: Full ROS2 path of the node that triggered the action,
                e.g. ``/robot1/amcl``.

        Returns:
            True if the service call succeeded.
        """
        from std_srvs.srv import Empty

        stack_ns = infer_stack_namespace(node_path, path_basename(node_path))
        svc = join_ros_path(stack_ns, "reinitialize_global_localization")

        key = (Empty, svc)
        if key not in self._clients:
            self._clients[key] = self._node.create_client(
                Empty,
                svc,
                callback_group=self._cb_group,
            )

        return self._call_empty_like(self._clients[key], Empty.Request(), svc)

    def prune_namespace(self, stack_namespace: str) -> None:
        """Destroy and remove all cached service clients whose path is under *stack_namespace*.

        Called when an entire Nav2 stack namespace disappears so that stale
        clients do not accumulate across long sessions with changing namespaces.

        Args:
            stack_namespace: Stack root namespace, e.g. ``"/"`` or ``"/robot1"``.
        """
        # A service path belongs to this namespace when it starts with
        # "<stack_namespace>/" (non-root) or "/" (root namespace catches all
        # absolute service paths that have no deeper namespace prefix).
        prefix = stack_namespace.rstrip('/') + '/'
        stale_keys = [
            key for key in self._clients
            if key[1].startswith(prefix)
        ]
        for key in stale_keys:
            try:
                self._node.destroy_client(self._clients[key])
            except Exception as exc:
                self._node.get_logger().debug(
                    f'Error destroying service client for {key[1]}: {exc}'
                )
            del self._clients[key]
        if stale_keys:
            self._node.get_logger().debug(
                f'Pruned {len(stale_keys)} service client(s) for namespace {stack_namespace}'
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_sync(self, client: Any, request: Any) -> Any:
        """Send *request* on *client* synchronously; return response or None on timeout."""
        if not client.wait_for_service(timeout_sec=self.SERVICE_TIMEOUT):
            return None

        done_event = threading.Event()
        result_holder: list[Any] = [None]

        def _on_done(fut: Any) -> None:
            try:
                result_holder[0] = fut.result()
            except Exception as exc:
                self._node.get_logger().warning(
                    f'Service call failed on {client.srv_name}: {exc}'
                )
            finally:
                done_event.set()

        future = client.call_async(request)
        future.add_done_callback(_on_done)

        if not done_event.wait(timeout=self.CALL_TIMEOUT):
            return None
        return result_holder[0]

    def _call_empty_like(self, client: Any, request: Any, service_name: str) -> bool:
        """Call *client* with *request*; return True on success, False on failure/timeout."""
        response = self._call_sync(client, request)
        if response is None:
            self._node.get_logger().warning(
                f'Service call timed out or unavailable: {service_name}'
            )
            return False
        return True
