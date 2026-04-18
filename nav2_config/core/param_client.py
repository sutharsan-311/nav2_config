# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ROS2 parameter service client for Nav2 nodes.

All public methods are synchronous and must be called from the ROS2 thread.
Service clients are cached per (node_name, service_type) to avoid the overhead
of creating a new client on every call.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from rclpy.node import Node
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import GetParameters, ListParameters, SetParameters

from nav2_config.types.params import Nav2ParamDef, ParamValue

logger = logging.getLogger(__name__)

#: Seconds to wait for a parameter service response before giving up.
_SERVICE_TIMEOUT: float = 5.0

#: Seconds to wait for a service to become available before giving up.
#: Healthy services respond in <50 ms; 0.5 s gives fast failure when the
#: node is gone without false negatives on a loaded system.
_AVAILABILITY_TIMEOUT: float = 0.5


# ---------------------------------------------------------------------------
# ParameterValue <-> Python value helpers
# ---------------------------------------------------------------------------

def _extract_value(pv: ParameterValue) -> Any:
    """Extract a plain Python value from a ``rcl_interfaces`` ParameterValue."""
    t = pv.type
    if t == ParameterType.PARAMETER_BOOL:
        return pv.bool_value
    if t == ParameterType.PARAMETER_INTEGER:
        return pv.integer_value
    if t == ParameterType.PARAMETER_DOUBLE:
        return pv.double_value
    if t == ParameterType.PARAMETER_STRING:
        return pv.string_value
    if t == ParameterType.PARAMETER_BYTE_ARRAY:
        return list(pv.byte_array_value)
    if t == ParameterType.PARAMETER_BOOL_ARRAY:
        return list(pv.bool_array_value)
    if t == ParameterType.PARAMETER_INTEGER_ARRAY:
        return list(pv.integer_array_value)
    if t == ParameterType.PARAMETER_DOUBLE_ARRAY:
        return list(pv.double_array_value)
    if t == ParameterType.PARAMETER_STRING_ARRAY:
        return list(pv.string_array_value)
    # PARAMETER_NOT_SET or unknown
    return None


def _make_parameter_value(value: Any, type_hint: str) -> ParameterValue:
    """Build a ``ParameterValue`` message from a Python value and schema type hint.

    ``type_hint`` comes from ``Nav2ParamDef.type``: one of
    ``"double"``, ``"int"``, ``"bool"``, ``"string"``, ``"string_array"``,
    ``"bool_array"``, ``"int_array"``, ``"double_array"``.
    """
    pv = ParameterValue()
    if type_hint == "bool":
        pv.type = ParameterType.PARAMETER_BOOL
        if isinstance(value, bool):
            pv.bool_value = value
        elif isinstance(value, str) and value.lower() in ("true", "false", "1", "0", "yes", "no"):
            pv.bool_value = value.lower() in ("true", "1", "yes")
        else:
            raise ValueError(
                f"Cannot convert {value!r} to bool: expected one of "
                f"true/false/1/0/yes/no (case-insensitive) or a Python bool"
            )
    elif type_hint == "int":
        pv.type = ParameterType.PARAMETER_INTEGER
        try:
            pv.integer_value = int(value)
        except ValueError as e:
            raise ValueError(f"Cannot convert '{value}' to int: {e}") from e
    elif type_hint == "double":
        pv.type = ParameterType.PARAMETER_DOUBLE
        try:
            pv.double_value = float(value)
        except ValueError as e:
            raise ValueError(f"Cannot convert '{value}' to double: {e}") from e
    elif type_hint == "string":
        pv.type = ParameterType.PARAMETER_STRING
        pv.string_value = str(value)
    elif type_hint == "bool_array":
        pv.type = ParameterType.PARAMETER_BOOL_ARRAY
        pv.bool_array_value = [bool(v) for v in value]
    elif type_hint == "int_array":
        pv.type = ParameterType.PARAMETER_INTEGER_ARRAY
        pv.integer_array_value = [int(v) for v in value]
    elif type_hint == "double_array":
        pv.type = ParameterType.PARAMETER_DOUBLE_ARRAY
        pv.double_array_value = [float(v) for v in value]
    elif type_hint == "string_array":
        pv.type = ParameterType.PARAMETER_STRING_ARRAY
        pv.string_array_value = list(value)
    else:
        # Best-effort type inference for unknown schema types.
        if isinstance(value, bool):
            pv.type = ParameterType.PARAMETER_BOOL
            pv.bool_value = value
        elif isinstance(value, int):
            pv.type = ParameterType.PARAMETER_INTEGER
            pv.integer_value = value
        elif isinstance(value, float):
            pv.type = ParameterType.PARAMETER_DOUBLE
            pv.double_value = value
        elif isinstance(value, str):
            pv.type = ParameterType.PARAMETER_STRING
            pv.string_value = value
        else:
            logger.warning("Cannot encode value %r with unknown type hint %r", value, type_hint)
    return pv


# ---------------------------------------------------------------------------
# Nav2ParamClient
# ---------------------------------------------------------------------------

class Nav2ParamClient:
    """Synchronous client for ROS2 parameter services on Nav2 nodes.

    Service clients are created lazily and cached so that repeated calls to the
    same node do not incur re-creation overhead.

    All methods block until the service responds or a timeout expires.  They
    must be called from the ROS2 spin thread (never from the Qt main thread).

    Args:
        node: The ``rclpy.Node`` used to create service clients.
    """

    def __init__(self, node: Node, callback_group: Any = None) -> None:
        self._node = node
        self._callback_group = callback_group
        # Cache: (node_name, service_class) -> rclpy client
        self._clients: dict[tuple[str, type], Any] = {}
        self._clients_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    # ROS2 param service names are snake_case; map from the Python class names.
    _SRV_NAMES: dict[type, str] = {
        ListParameters: "list_parameters",
        GetParameters: "get_parameters",
        SetParameters: "set_parameters",
    }

    def _get_client(self, node_name: str, srv_class: type) -> Any:
        """Return a cached (or newly created) service client.

        The service name follows ROS2 convention:
          ``/{node_name}/{service_name}``
        where ``/{node_name}`` is already the full path (e.g. ``/controller_server``).
        """
        key = (node_name, srv_class)
        with self._clients_lock:
            if key not in self._clients:
                srv_name = self._SRV_NAMES[srv_class]
                service_name = f"{node_name}/{srv_name}"
                self._clients[key] = self._node.create_client(
                    srv_class, service_name, callback_group=self._callback_group
                )
                logger.debug("Created service client for %s", service_name)
            return self._clients[key]

    def _call(self, client: Any, request: Any) -> Any | None:
        """Send *request* and block until the response arrives or times out.

        Uses threading.Event rather than rclpy.spin_until_future_complete so
        that this method is safe to call from inside a running executor
        callback.  The MultiThreadedExecutor in main.py can process the
        service response on a different thread while this one waits.

        Returns the response object, or ``None`` on timeout / unavailable.
        """
        if not client.wait_for_service(timeout_sec=_AVAILABILITY_TIMEOUT):
            logger.debug("Service %s not available", client.srv_name)
            return None

        future = client.call_async(request)

        done_event = threading.Event()
        result_holder: list[Any] = [None]

        def _on_done(fut: Any) -> None:
            try:
                result_holder[0] = fut.result()
            except Exception as exc:
                logger.warning("Service call failed on %s: %s", client.srv_name, exc)
            finally:
                done_event.set()

        future.add_done_callback(_on_done)

        if not done_event.wait(timeout=_SERVICE_TIMEOUT):
            logger.warning("Service call to %s timed out", client.srv_name)
            return None
        return result_holder[0]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_params(self, node_name: str) -> list[str]:
        """Return all parameter names advertised by the given Nav2 node.

        Calls ``/{node_name}/list_parameters`` with no prefix filter (depth 0
        means unlimited).

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.

        Returns:
            List of parameter name strings, or an empty list on failure.
        """
        client = self._get_client(node_name, ListParameters)
        req = ListParameters.Request()
        req.depth = ListParameters.Request.DEPTH_RECURSIVE

        response = self._call(client, req)
        if response is None:
            return []

        names: list[str] = list(response.result.names)
        logger.debug("list_params(%s): %d params", node_name, len(names))
        return names

    def get_params(self, node_name: str, param_names: list[str]) -> dict[str, tuple[Any, int]]:
        """Fetch current values for the given parameter names from a Nav2 node.

        Calls ``/{node_name}/get_parameters``.

        Args:
            node_name: Full ROS2 node path.
            param_names: Names of parameters to fetch.

        Returns:
            ``{name: (value, ros2_type)}`` dict for each successfully retrieved
            parameter, where ``ros2_type`` is the raw ``ParameterType`` int from
            the ROS2 response.  Parameters that could not be fetched are omitted.
        """
        if not param_names:
            return {}

        client = self._get_client(node_name, GetParameters)
        req = GetParameters.Request()
        req.names = param_names

        response = self._call(client, req)
        if response is None:
            return {}

        result: dict[str, tuple[Any, int]] = {}
        for name, pv in zip(param_names, response.values):
            if pv.type != ParameterType.PARAMETER_NOT_SET:
                result[name] = (_extract_value(pv), pv.type)

        logger.debug("get_params(%s): fetched %d/%d", node_name, len(result), len(param_names))
        return result

    def set_param(
        self,
        node_name: str,
        param_name: str,
        value: Any,
        type_hint: str = "",
    ) -> tuple[bool, str]:
        """Write a single parameter value to a running Nav2 node.

        Calls ``/{node_name}/set_parameters`` with a single-element list.

        Args:
            node_name: Full ROS2 node path.
            param_name: Name of the parameter to set.
            value: New value (Python native type).
            type_hint: Schema type string (``"double"``, ``"int"``, etc.) used
                to encode the value correctly.  Falls back to type inference
                when empty.

        Returns:
            ``(True, "")`` if the node accepted the change,
            ``(False, reason)`` otherwise.
        """
        client = self._get_client(node_name, SetParameters)

        param_msg = Parameter()
        param_msg.name = param_name
        param_msg.value = _make_parameter_value(value, type_hint)

        req = SetParameters.Request()
        req.parameters = [param_msg]

        response = self._call(client, req)
        if response is None:
            return False, "service call failed"

        if not response.results:
            reason = "empty results list"
            logger.warning("set_param(%s, %s): %s", node_name, param_name, reason)
            return False, reason

        result = response.results[0]
        if not result.successful:
            logger.warning(
                "set_param(%s, %s) rejected: %s",
                node_name, param_name, result.reason,
            )
        return result.successful, result.reason if not result.successful else ""

    def prune_node(self, node_path: str) -> None:
        """Destroy and remove all cached service clients for *node_path*.

        Called when a node disappears from the ROS2 graph so that stale
        clients do not accumulate across long sessions with changing namespaces.

        Args:
            node_path: Full ROS2 node path, e.g. ``"/robot1/controller_server"``.
        """
        with self._clients_lock:
            stale_keys = [key for key in self._clients if key[0] == node_path]
            for key in stale_keys:
                try:
                    self._node.destroy_client(self._clients[key])
                except Exception as exc:
                    logger.debug("Error destroying param client for %s: %s", key, exc)
                del self._clients[key]
        if stale_keys:
            logger.debug("Pruned %d param service client(s) for %s", len(stale_keys), node_path)

    def get_all_nav2_params(
        self,
        node_name: str,
        schema: list[Nav2ParamDef],
    ) -> list[ParamValue]:
        """Merge live parameter values from a running node with schema definitions.

        For each parameter in *schema* whose ``node`` field matches *node_name*
        (without the leading ``/``), this method:

        - Tries to fetch the live value via :meth:`get_params`.
        - If a live value exists, sets ``is_live=True`` and uses it as
          ``current_value``.
        - If the node is not reachable (or the param is not set), falls back to
          ``definition.default`` and sets ``is_live=False``.
        - Sets ``is_modified = (current_value != definition.default)``.

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.
            schema: Full parameter schema list (all nodes).  Entries for other
                nodes are ignored.

        Returns:
            List of :class:`~nav2_config.types.params.ParamValue` objects, one
            per matching schema entry, sorted by param name.
        """
        # Extract the bare node name from the full ROS2 node path.
        # ROS2 reports namespaced nodes as "/namespace/node_name", so we take
        # the last path segment:
        #   "/controller_server"              -> "controller_server"
        #   "/local_costmap/local_costmap"    -> "local_costmap"
        #   "/global_costmap/global_costmap"  -> "global_costmap"
        bare_node = node_name.rstrip("/").rsplit("/", 1)[-1]

        # Filter schema to only this node's params
        node_defs = [d for d in schema if d.node == bare_node]

        if not node_defs:
            return []

        # GetParameters fails silently (returns 0 values) if ANY requested param
        # is not declared on the node.  Call list_parameters first, then
        # intersect using the ros2_name (the exact name the node knows) so we
        # only request params that actually exist on the running node.
        existing_names: set[str] = set(self.list_params(node_name))
        ros2_names = [d.ros2_name for d in node_defs if d.ros2_name in existing_names]
        live_typed = self.get_params(node_name, ros2_names) if ros2_names else {}
        # Strip type info — schema-defined params already carry the correct type.
        live_values = {k: v for k, (v, _) in live_typed.items()}

        result: list[ParamValue] = []
        for d in node_defs:
            if d.ros2_name in live_values:
                current_value = live_values[d.ros2_name]
                is_live = True
            else:
                current_value = d.default
                is_live = False
            result.append(
                ParamValue(
                    definition=d,
                    current_value=current_value,
                    is_modified=is_live and (current_value != d.default),
                    is_live=is_live,
                )
            )

        return sorted(result, key=lambda pv: pv.definition.param)
