# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0
"""Test that fetch errors emit params_received([]) instead of hanging."""
from unittest.mock import MagicMock, patch

import pytest

try:
    from PyQt6.QtWidgets import QApplication
    import sys
    _app = QApplication.instance() or QApplication(sys.argv)
except Exception:
    pytest.skip("PyQt6 not available", allow_module_level=True)


def _make_minimal_node():
    """Build a Nav2ConfigNode with just enough wiring for _fetch_params_for_node."""
    from nav2_config.node import Nav2ConfigNode, SignalBridge

    node = object.__new__(Nav2ConfigNode)
    node.signals = SignalBridge()
    node._param_names_cache = {}
    node._watcher = MagicMock()
    node._watcher.watched_node = None
    return node


def test_fetch_error_emits_empty_params_received():
    """params_received must be emitted with [] when _build_param_values raises."""
    node = _make_minimal_node()
    received: list = []
    node.signals.params_received.connect(lambda n, ps: received.append((n, ps)))

    with patch.object(
        type(node), '_build_param_values', side_effect=RuntimeError("rpc error")
    ):
        with patch.object(type(node), 'get_logger', return_value=MagicMock()):
            from nav2_config.node import Nav2ConfigNode
            Nav2ConfigNode._fetch_params_for_node(node, '/controller_server')

    assert len(received) == 1
    node_name, params = received[0]
    assert node_name == '/controller_server'
    assert params == []


def test_fetch_success_emits_params_received():
    """When _build_param_values succeeds, params_received carries the real list."""
    from nav2_config.types.params import ParamValue, Nav2ParamDef
    node = _make_minimal_node()
    received: list = []
    node.signals.params_received.connect(lambda n, ps: received.append((n, ps)))

    fake_defn = Nav2ParamDef(
        node='controller_server', param='max_vel_x', type='double',
        default=0.5, range=None, unit='m/s', description='', impact='',
        category='Base Parameters', plugin_specific=False, plugin=None,
        hot_reload=True,
    )
    fake_pv = ParamValue(definition=fake_defn, current_value=0.5, is_live=True,
                         node_path='/controller_server')
    fake_params = [fake_pv]

    with patch.object(type(node), '_build_param_values', return_value=fake_params):
        with patch.object(type(node), 'get_logger', return_value=MagicMock()):
            from nav2_config.node import Nav2ConfigNode
            Nav2ConfigNode._fetch_params_for_node(node, '/controller_server')

    assert len(received) == 1
    assert received[0][1] == fake_params
