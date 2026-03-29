# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Tests for Nav2ParamClient: mocked ROS2 service calls."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Allow importing from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.core.param_client import (
    Nav2ParamClient,
    _extract_value,
    _make_parameter_value,
)
from nav2_config.types.params import Nav2ParamDef, ParamRange, ParamValue


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_node() -> MagicMock:
    """A minimal mock rclpy Node."""
    node = MagicMock()
    node.create_client = MagicMock(side_effect=_make_mock_client)
    return node


def _make_mock_client(srv_class, service_name: str) -> MagicMock:
    """Return a mock service client that records its service name."""
    client = MagicMock()
    client.srv_name = service_name
    client.wait_for_service = MagicMock(return_value=True)
    return client


@pytest.fixture()
def client(mock_node: MagicMock) -> Nav2ParamClient:
    return Nav2ParamClient(mock_node)


def _make_param_def(
    node: str,
    param: str,
    type: str,
    default: Any,
    *,
    hot_reload: bool = True,
) -> Nav2ParamDef:
    return Nav2ParamDef(
        node=node,
        param=param,
        type=type,
        default=default,
        range=None,
        unit="",
        description="test",
        impact="",
        category="general",
        plugin_specific=False,
        plugin=None,
        hot_reload=hot_reload,
        tags=[],
    )


# ---------------------------------------------------------------------------
# _extract_value / _make_parameter_value round-trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("type_hint,value", [
    ("bool",         True),
    ("bool",         False),
    ("int",          42),
    ("double",       3.14),
    ("string",       "hello"),
    ("string_array", ["a", "b", "c"]),
])
def test_parameter_value_round_trip(type_hint: str, value: Any) -> None:
    """Encoding a Python value then extracting it should give back the original."""
    pv = _make_parameter_value(value, type_hint)
    result = _extract_value(pv)
    assert result == value, f"Round-trip failed for type={type_hint}: {value!r} -> {result!r}"


def test_extract_not_set_returns_none() -> None:
    from rcl_interfaces.msg import ParameterType, ParameterValue
    pv = ParameterValue()
    pv.type = ParameterType.PARAMETER_NOT_SET
    assert _extract_value(pv) is None


# ---------------------------------------------------------------------------
# list_params
# ---------------------------------------------------------------------------


def _spin_complete(node, future, timeout_sec=None):
    """Immediately marks the future as done (simulates a fast service response)."""
    # The future is already set up with a result by the test — nothing to do.


def test_list_params_returns_names(client: Nav2ParamClient, mock_node: MagicMock) -> None:
    from rcl_interfaces.srv import ListParameters

    mock_response = MagicMock()
    mock_response.result.names = ["controller_frequency", "min_x_velocity_threshold"]

    future = MagicMock()
    future.result = MagicMock(return_value=mock_response)

    mock_client = client._get_client("/controller_server", ListParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.list_params("/controller_server")

    assert result == ["controller_frequency", "min_x_velocity_threshold"]


def test_list_params_returns_empty_on_timeout(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import ListParameters

    future = MagicMock()
    future.result = MagicMock(return_value=None)  # Timeout: future has no result

    mock_client = client._get_client("/controller_server", ListParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.list_params("/controller_server")

    assert result == []


def test_list_params_returns_empty_when_service_unavailable(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import ListParameters

    mock_client = client._get_client("/controller_server", ListParameters)
    mock_client.wait_for_service = MagicMock(return_value=False)

    result = client.list_params("/controller_server")
    assert result == []


# ---------------------------------------------------------------------------
# get_params
# ---------------------------------------------------------------------------


def test_get_params_returns_values(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import GetParameters

    # Build mock ParameterValue for a double
    pv_double = _make_parameter_value(20.0, "double")
    pv_int = _make_parameter_value(5, "int")

    mock_response = MagicMock()
    mock_response.values = [pv_double, pv_int]

    future = MagicMock()
    future.result = MagicMock(return_value=mock_response)

    mock_client = client._get_client("/controller_server", GetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.get_params("/controller_server", ["controller_frequency", "min_x_velocity_threshold"])

    assert result == {"controller_frequency": 20.0, "min_x_velocity_threshold": 5}


def test_get_params_empty_input_returns_empty(client: Nav2ParamClient) -> None:
    result = client.get_params("/controller_server", [])
    assert result == {}


def test_get_params_skips_not_set_values(client: Nav2ParamClient) -> None:
    from rcl_interfaces.msg import ParameterType, ParameterValue
    from rcl_interfaces.srv import GetParameters

    pv_set = _make_parameter_value(42.0, "double")
    pv_not_set = ParameterValue()  # type defaults to PARAMETER_NOT_SET (0)

    mock_response = MagicMock()
    mock_response.values = [pv_set, pv_not_set]

    future = MagicMock()
    future.result = MagicMock(return_value=mock_response)

    mock_client = client._get_client("/controller_server", GetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.get_params("/controller_server", ["controller_frequency", "missing_param"])

    assert "controller_frequency" in result
    assert "missing_param" not in result


# ---------------------------------------------------------------------------
# set_param
# ---------------------------------------------------------------------------


def _mock_set_response(successful: bool, reason: str = "") -> MagicMock:
    single_result = MagicMock()
    single_result.successful = successful
    single_result.reason = reason
    response = MagicMock()
    response.results = [single_result]
    return response


def test_set_param_returns_true_on_success(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import SetParameters

    future = MagicMock()
    future.result = MagicMock(return_value=_mock_set_response(True))

    mock_client = client._get_client("/controller_server", SetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.set_param("/controller_server", "controller_frequency", 25.0, "double")

    assert result is True


def test_set_param_returns_false_on_rejection(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import SetParameters

    future = MagicMock()
    future.result = MagicMock(return_value=_mock_set_response(False, "read-only param"))

    mock_client = client._get_client("/controller_server", SetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.set_param("/controller_server", "use_sim_time", True, "bool")

    assert result is False


def test_set_param_returns_false_on_timeout(client: Nav2ParamClient) -> None:
    from rcl_interfaces.srv import SetParameters

    future = MagicMock()
    future.result = MagicMock(return_value=None)  # Timeout

    mock_client = client._get_client("/controller_server", SetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        result = client.set_param("/controller_server", "controller_frequency", 25.0, "double")

    assert result is False


# ---------------------------------------------------------------------------
# get_all_nav2_params — schema merge
# ---------------------------------------------------------------------------


CONTROLLER_SCHEMA = [
    _make_param_def("controller_server", "controller_frequency", "double", 20.0),
    _make_param_def("controller_server", "min_x_velocity_threshold", "double", 0.0001),
    _make_param_def("controller_server", "failure_tolerance", "double", 0.3),
    # A different node — should be ignored
    _make_param_def("planner_server", "planner_frequency", "double", 1.0),
]


def _setup_get_params_mock(
    client: Nav2ParamClient,
    live_values: dict[str, Any],
    param_types: dict[str, str],
) -> None:
    """Wire the GetParameters mock to return *live_values* for the expected names."""
    from rcl_interfaces.srv import GetParameters

    def call_async_side_effect(request):
        pvs = []
        for name in request.names:
            if name in live_values:
                pv = _make_parameter_value(live_values[name], param_types.get(name, "double"))
            else:
                from rcl_interfaces.msg import ParameterValue
                pv = ParameterValue()  # NOT_SET
            pvs.append(pv)

        mock_response = MagicMock()
        mock_response.values = pvs
        future = MagicMock()
        future.result = MagicMock(return_value=mock_response)
        return future

    mock_client = client._get_client("/controller_server", GetParameters)
    mock_client.call_async = MagicMock(side_effect=call_async_side_effect)


def test_get_all_nav2_params_live_values(client: Nav2ParamClient) -> None:
    """Live values from the node override schema defaults."""
    live = {
        "controller_frequency": 30.0,
        "min_x_velocity_threshold": 0.001,
        "failure_tolerance": 0.3,  # Same as default
    }
    _setup_get_params_mock(client, live, {"controller_frequency": "double", "min_x_velocity_threshold": "double", "failure_tolerance": "double"})

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        results = client.get_all_nav2_params("/controller_server", CONTROLLER_SCHEMA)

    assert len(results) == 3  # Only controller_server params
    by_name = {r.definition.param: r for r in results}

    freq = by_name["controller_frequency"]
    assert freq.current_value == 30.0
    assert freq.is_live is True
    assert freq.is_modified is True  # 30.0 != 20.0

    tol = by_name["failure_tolerance"]
    assert tol.current_value == 0.3
    assert tol.is_live is True
    assert tol.is_modified is False  # Same as default


def test_get_all_nav2_params_fallback_to_defaults(client: Nav2ParamClient) -> None:
    """When node is unreachable (get_params returns {}), schema defaults are used."""
    from rcl_interfaces.srv import GetParameters

    future = MagicMock()
    future.result = MagicMock(return_value=None)  # Timeout

    mock_client = client._get_client("/controller_server", GetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        results = client.get_all_nav2_params("/controller_server", CONTROLLER_SCHEMA)

    assert len(results) == 3
    for pv in results:
        assert pv.is_live is False
        assert pv.current_value == pv.definition.default
        assert pv.is_modified is False


def test_get_all_nav2_params_filters_other_nodes(client: Nav2ParamClient) -> None:
    """Params from other nodes must not appear in results."""
    from rcl_interfaces.srv import GetParameters

    future = MagicMock()
    future.result = MagicMock(return_value=None)

    mock_client = client._get_client("/planner_server", GetParameters)
    mock_client.call_async = MagicMock(return_value=future)

    with patch("nav2_config.core.param_client.rclpy.spin_until_future_complete", _spin_complete):
        results = client.get_all_nav2_params("/planner_server", CONTROLLER_SCHEMA)

    # Only planner_server params (1 entry in CONTROLLER_SCHEMA)
    assert len(results) == 1
    assert results[0].definition.node == "planner_server"


def test_get_all_nav2_params_empty_schema(client: Nav2ParamClient) -> None:
    results = client.get_all_nav2_params("/controller_server", [])
    assert results == []


def test_get_all_nav2_params_unknown_node(client: Nav2ParamClient) -> None:
    results = client.get_all_nav2_params("/some_unknown_node", CONTROLLER_SCHEMA)
    assert results == []
