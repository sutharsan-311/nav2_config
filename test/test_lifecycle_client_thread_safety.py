# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0
"""Thread-safety tests for LifecycleClient service client caches."""
import threading
import time
from unittest.mock import MagicMock


def _make_lc():
    """Build a bare LifecycleClient without a real rclpy node."""
    from nav2_config.core.lifecycle_client import LifecycleClient
    mock_node = MagicMock()
    lc = LifecycleClient.__new__(LifecycleClient)
    lc._node = mock_node
    lc._callback_group = None
    lc._get_clients = {}
    lc._change_clients = {}
    lc._get_clients_lock = threading.Lock()
    lc._change_clients_lock = threading.Lock()
    return lc, mock_node


def test_concurrent_get_state_client_creates_exactly_one():
    """Two threads racing _get_state_client for the same node must create only one client."""
    lc, mock_node = _make_lc()

    def _slow_create(srv_class, svc_name, **kwargs):
        # Sleep so that, without a lock, the second thread would also enter here.
        time.sleep(0.05)
        return MagicMock()

    mock_node.create_client.side_effect = _slow_create

    results = []
    errors = []

    def _call():
        try:
            results.append(lc._get_state_client('/controller_server'))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Threads raised exceptions: {errors}"
    assert mock_node.create_client.call_count == 1, (
        f"Expected 1 client created, got {mock_node.create_client.call_count} — "
        "lock is missing or not working"
    )
    assert results[0] is results[1], "Both threads should receive the same client object"


def test_concurrent_change_state_client_creates_exactly_one():
    """Two threads racing _change_state_client for the same node must create only one client."""
    lc, mock_node = _make_lc()

    def _slow_create(srv_class, svc_name, **kwargs):
        time.sleep(0.05)
        return MagicMock()

    mock_node.create_client.side_effect = _slow_create

    results = []
    errors = []

    def _call():
        try:
            results.append(lc._change_state_client('/controller_server'))
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"Threads raised exceptions: {errors}"
    assert mock_node.create_client.call_count == 1, (
        f"Expected 1 client created, got {mock_node.create_client.call_count}"
    )
    assert results[0] is results[1], "Both threads should receive the same client object"
