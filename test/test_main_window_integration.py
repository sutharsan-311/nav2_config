# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for MainWindow business logic.

Tests cover:
- param_set_requested uses ros2_name (not display name) for the ROS2 call
- _pending_config_set is keyed by (node_path, ros2_name)
- _on_param_set_result clears the correct pending entry
- _on_undo_requested triggers _apply_param_change with source=ChangeSource.UNDO
- namespace-scoped restart routes to the correct stack_namespace

All tests are mock-based — no live Nav2 stack required.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))


# ---------------------------------------------------------------------------
# Session-scoped Qt application (required by QObject / signals)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Provide a QCoreApplication for the test session."""
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


# ---------------------------------------------------------------------------
# Imports guarded behind the fixture so the Qt app exists first
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def imports(qapp):
    """Import modules that require a running QCoreApplication."""
    from nav2_config.core.history_manager import HistoryManager
    from nav2_config.types.history import ChangeSource, ParamHistoryEntry, ParamRef
    from nav2_config.types.params import Nav2ParamDef, ParamValue
    from nav2_config.core.node_discovery import DiscoveredNav2Node, DiscoveredLifecycleManager
    from nav2_config.gui.main_window import ApplyParamRequest

    return {
        "HistoryManager": HistoryManager,
        "ChangeSource": ChangeSource,
        "ParamHistoryEntry": ParamHistoryEntry,
        "ParamRef": ParamRef,
        "Nav2ParamDef": Nav2ParamDef,
        "ParamValue": ParamValue,
        "DiscoveredNav2Node": DiscoveredNav2Node,
        "DiscoveredLifecycleManager": DiscoveredLifecycleManager,
        "ApplyParamRequest": ApplyParamRequest,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_param_def(
    node: str,
    param: str,
    ros2_name: str = "",
    type: str = "double",
    hot_reload: bool = True,
) -> Any:
    from nav2_config.types.params import Nav2ParamDef

    return Nav2ParamDef(
        node=node,
        param=param,
        type=type,
        default=20.0,
        range=None,
        unit="",
        description="test",
        impact="",
        category="general",
        plugin_specific=False,
        plugin=None,
        hot_reload=hot_reload,
        tags=[],
        ros2_name=ros2_name or param,
    )


def _make_param_value(node: str, param: str, ros2_name: str = "", value: float = 20.0) -> Any:
    from nav2_config.types.params import ParamValue

    defn = _make_param_def(node, param, ros2_name)
    pv = ParamValue(definition=defn, current_value=value)
    pv.node_path = f"/{node}"
    return pv


def _make_history_entry(
    node_path: str,
    param_name: str,
    ros2_name: str,
    old_value: float,
    new_value: float,
    source: Any,
) -> Any:
    from nav2_config.types.history import ParamHistoryEntry, ParamRef

    return ParamHistoryEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        ref=ParamRef(node_path=node_path, param_name=param_name),
        old_value=old_value,
        new_value=new_value,
        source=source,
        batch_id=None,
        ros2_name=ros2_name,
        type_hint="double",
        hot_reload=True,
        status="pending",
    )


def _make_bare_main_window(imports: dict) -> Any:
    """Construct a MainWindow-like object bypassing __init__.

    We bypass the full __init__ (which requires a wired Qt UI) and manually
    set only the attributes exercised by the methods under test.  This matches
    the pattern used in test_param_client.py, which constructs real objects
    using mock dependencies rather than a full integration environment.
    """
    from nav2_config.gui.main_window import MainWindow

    win = object.__new__(MainWindow)

    # Core state
    win._node = MagicMock()
    win._config_file = None
    win._dirty = False
    win._pending_config_set: dict = {}
    win._current_params: list = []
    win._all_node_params: dict = {}
    win._selected_node_path = None
    win._topology_nodes: dict = {}
    win._topology_managers: dict = {}
    win._pending_history: dict = {}
    win._pending_set_values: dict = {}
    win._pending_undo_map: dict = {}
    win._schema_index = None

    # History
    HistoryManager = imports["HistoryManager"]
    win._history = HistoryManager()

    # Lightweight panel mocks — only the methods called by the logic under test
    win._param_panel = MagicMock()
    win._param_panel._all_rows = []
    win._param_panel.pending_param_names = MagicMock(return_value=[])

    win._yaml_panel = MagicMock()
    win._node_panel = MagicMock()
    win._history_panel = MagicMock()
    win._compare_panel = MagicMock()
    win._notification_bar = MagicMock()
    win._status_last_set = MagicMock()
    win._last_set_timer = MagicMock()
    win._status_bar = MagicMock()

    # QMainWindow / QAction methods used by _mark_dirty, _update_title, set_status
    win._save_action = MagicMock()
    win._save_as_action = MagicMock()
    win.setWindowTitle = MagicMock()
    # set_status calls self._status_bar.showMessage — mock it at the instance level
    # so tests that call _on_param_set_result or _on_param_set_requested don't hit
    # the real QMainWindow plumbing.
    win.set_status = MagicMock()

    return win


# ---------------------------------------------------------------------------
# param_set_requested: ros2_name dispatched to ROS2, not display name
# ---------------------------------------------------------------------------


class TestParamSetRequestedUsesRos2Name:
    """_on_param_set_requested must use ros2_name for the ROS2 service call."""

    def test_ros2_name_sent_to_node(self, imports):
        """When a param has a plugin-namespaced ros2_name, request_set_param
        is called with the ros2_name, not the schema display name."""
        win = _make_bare_main_window(imports)
        ParamValue = imports["ParamValue"]

        # Param whose display name differs from its ros2_name
        display_name = "max_vel_x"
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", display_name, ros2_name, value=1.0)

        # Build a fake row the panel scan will find
        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]

        win._on_param_set_requested("/controller_server", display_name, 2.0)

        win._node.request_set_param.assert_called_once_with(
            "/controller_server", ros2_name, 2.0, "double"
        )

    def test_display_name_not_sent_to_node(self, imports):
        """The display name (schema .param field) is never passed to request_set_param."""
        win = _make_bare_main_window(imports)

        display_name = "max_vel_x"
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", display_name, ros2_name, value=1.0)

        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]

        win._on_param_set_requested("/controller_server", display_name, 2.0)

        # Verify the display name was NOT used as the param name argument
        call_args = win._node.request_set_param.call_args
        assert call_args[0][1] == ros2_name
        assert call_args[0][1] != display_name

    def test_simple_param_uses_param_name_as_ros2_name(self, imports):
        """Params without a separate ros2_name still work: param name == ros2_name."""
        win = _make_bare_main_window(imports)

        pv = _make_param_value("controller_server", "controller_frequency", value=20.0)
        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]

        win._on_param_set_requested("/controller_server", "controller_frequency", 30.0)

        win._node.request_set_param.assert_called_once_with(
            "/controller_server", "controller_frequency", 30.0, "double"
        )


# ---------------------------------------------------------------------------
# _pending_config_set keyed by (node_path, ros2_name)
# ---------------------------------------------------------------------------


class TestPendingConfigSetKey:
    """_pending_config_set must be keyed by (node_path, ros2_name), not display name."""

    def test_pending_config_set_key_uses_ros2_name(self, imports):
        """When a config file is loaded, the staged entry is keyed by ros2_name."""
        win = _make_bare_main_window(imports)

        display_name = "max_vel_x"
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", display_name, ros2_name, value=1.0)

        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]

        # Attach a mock config file so the pending staging branch executes
        win._config_file = MagicMock()
        win._config_file.to_yaml_string = MagicMock(return_value="")

        win._on_param_set_requested("/controller_server", display_name, 2.0)

        key = ("/controller_server", ros2_name)
        assert key in win._pending_config_set

    def test_pending_config_set_key_not_display_name(self, imports):
        """The display name alone must not appear as a key in _pending_config_set."""
        win = _make_bare_main_window(imports)

        display_name = "max_vel_x"
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", display_name, ros2_name, value=1.0)

        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]
        win._config_file = MagicMock()
        win._config_file.to_yaml_string = MagicMock(return_value="")

        win._on_param_set_requested("/controller_server", display_name, 2.0)

        bad_key = ("/controller_server", display_name)
        assert bad_key not in win._pending_config_set

    def test_pending_config_set_value_contains_ros2_name(self, imports):
        """The staged tuple's second element is ros2_name, used later by the config file."""
        win = _make_bare_main_window(imports)

        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", "max_vel_x", ros2_name, value=1.0)
        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]
        win._config_file = MagicMock()
        win._config_file.to_yaml_string = MagicMock(return_value="")

        win._on_param_set_requested("/controller_server", "max_vel_x", 2.0)

        staged = win._pending_config_set[("/controller_server", ros2_name)]
        _node, _ros2, _val = staged
        assert _ros2 == ros2_name


# ---------------------------------------------------------------------------
# _on_param_set_result: clears the correct pending entry
# ---------------------------------------------------------------------------


class TestOnParamSetResultClearsPending:
    """_on_param_set_result must clear the matching (node_path, ros2_name) entries."""

    def _setup_pending(self, win, node_path, ros2_name, value, imports):
        """Pre-populate pending dicts as _on_param_set_requested would."""
        ChangeSource = imports["ChangeSource"]
        entry_id = str(uuid.uuid4())
        win._pending_history[(node_path, ros2_name)] = entry_id
        win._pending_set_values[(node_path, ros2_name)] = value
        win._config_file = MagicMock()
        win._config_file.to_yaml_string = MagicMock(return_value="")
        win._pending_config_set[(node_path, ros2_name)] = (node_path, ros2_name, value)
        win._selected_node_path = node_path
        return entry_id

    def test_pending_history_cleared_on_success(self, imports):
        win = _make_bare_main_window(imports)
        pv = _make_param_value("controller_server", "controller_frequency")
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", "controller_frequency", 30.0, imports)
        win._on_param_set_result("/controller_server", "controller_frequency", True)

        assert ("/controller_server", "controller_frequency") not in win._pending_history

    def test_pending_config_set_cleared_on_success(self, imports):
        win = _make_bare_main_window(imports)
        pv = _make_param_value("controller_server", "controller_frequency")
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", "controller_frequency", 30.0, imports)
        win._on_param_set_result("/controller_server", "controller_frequency", True)

        assert ("/controller_server", "controller_frequency") not in win._pending_config_set

    def test_pending_set_values_cleared_on_success(self, imports):
        win = _make_bare_main_window(imports)
        pv = _make_param_value("controller_server", "controller_frequency")
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", "controller_frequency", 30.0, imports)
        win._on_param_set_result("/controller_server", "controller_frequency", True)

        assert ("/controller_server", "controller_frequency") not in win._pending_set_values

    def test_pending_config_set_cleared_on_failure(self, imports):
        """A failed set still clears the staged entry (no stale config update)."""
        win = _make_bare_main_window(imports)
        pv = _make_param_value("controller_server", "controller_frequency")
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", "controller_frequency", 30.0, imports)
        win._on_param_set_result("/controller_server", "controller_frequency", False)

        assert ("/controller_server", "controller_frequency") not in win._pending_config_set

    def test_config_file_set_value_called_on_success(self, imports):
        """When the set succeeds, the staged config change is written to the config file."""
        win = _make_bare_main_window(imports)
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", "max_vel_x", ros2_name)
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", ros2_name, 2.0, imports)
        win._on_param_set_result("/controller_server", ros2_name, True)

        win._config_file.set_value.assert_called_once_with(
            "/controller_server", ros2_name, 2.0
        )

    def test_config_file_not_written_on_failure(self, imports):
        """A failed set must NOT write to the config file."""
        win = _make_bare_main_window(imports)
        ros2_name = "FollowPath.max_vel_x"
        pv = _make_param_value("controller_server", "max_vel_x", ros2_name)
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", ros2_name, 2.0, imports)
        win._on_param_set_result("/controller_server", ros2_name, False)

        win._config_file.set_value.assert_not_called()

    def test_only_matching_key_is_cleared(self, imports):
        """Pending entries for other params are not disturbed."""
        win = _make_bare_main_window(imports)
        pv = _make_param_value("controller_server", "controller_frequency")
        win._current_params = [pv]

        self._setup_pending(win, "/controller_server", "controller_frequency", 30.0, imports)

        # A separate unrelated entry
        win._pending_history[("/planner_server", "planner_frequency")] = str(uuid.uuid4())

        win._on_param_set_result("/controller_server", "controller_frequency", True)

        assert ("/planner_server", "planner_frequency") in win._pending_history


# ---------------------------------------------------------------------------
# _on_undo_requested: triggers _apply_param_change with source=ChangeSource.UNDO
# ---------------------------------------------------------------------------


class TestOnUndoRequested:
    """_on_undo_requested must reverse the change and dispatch with UNDO source."""

    def _record_original(self, win, imports) -> Any:
        """Record an original LIVE_SET entry and return it."""
        ChangeSource = imports["ChangeSource"]
        entry = _make_history_entry(
            node_path="/controller_server",
            param_name="controller_frequency",
            ros2_name="controller_frequency",
            old_value=10.0,
            new_value=30.0,
            source=ChangeSource.LIVE_SET,
        )
        win._history.record_change(entry)
        return entry

    def test_undo_calls_request_set_param(self, imports):
        """Undoing an entry calls request_set_param on the node."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        win._node.request_set_param.assert_called_once()

    def test_undo_sends_old_value(self, imports):
        """The undo call sets the param back to the original old_value."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        call_args = win._node.request_set_param.call_args[0]
        # request_set_param(node_path, ros2_name, value, type_hint)
        assert call_args[2] == 10.0  # original old_value

    def test_undo_sends_to_correct_node_path(self, imports):
        """The undo call targets the same node as the original entry."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        call_args = win._node.request_set_param.call_args[0]
        assert call_args[0] == "/controller_server"

    def test_undo_records_undo_source_in_history(self, imports):
        """The undo entry recorded in history has source=ChangeSource.UNDO."""
        ChangeSource = imports["ChangeSource"]
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        history = win._history.get_history()
        # The undo entry is appended after the original
        undo_entry = history[-1]
        assert undo_entry.source is ChangeSource.UNDO

    def test_undo_pending_undo_map_populated(self, imports):
        """_pending_undo_map tracks the undo_entry_id → original_entry_id mapping."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        # The undo entry ID should be in _pending_undo_map pointing to original
        assert original.entry_id in win._pending_undo_map.values()

    def test_undo_unknown_entry_id_is_noop(self, imports):
        """Undoing an unknown entry_id does not call request_set_param."""
        win = _make_bare_main_window(imports)

        win._on_undo_requested("nonexistent-id")

        win._node.request_set_param.assert_not_called()

    def test_undo_confirmation_marks_original_undone(self, imports):
        """When the undo set succeeds, the original entry status becomes 'undone'."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        # Trigger undo — this populates _pending_undo_map and _pending_history
        win._on_undo_requested(original.entry_id)

        # Simulate ROS2 confirming the undo set succeeded
        undo_entry = win._history.get_history()[-1]
        win._on_param_set_result(
            undo_entry.ref.node_path, undo_entry.ros2_name, True
        )

        assert original.status == "undone"

    def test_undo_failure_marks_original_undo_failed(self, imports):
        """When the undo set fails, the original entry status becomes 'undo_failed'."""
        win = _make_bare_main_window(imports)
        original = self._record_original(win, imports)

        win._on_undo_requested(original.entry_id)

        undo_entry = win._history.get_history()[-1]
        win._on_param_set_result(
            undo_entry.ref.node_path, undo_entry.ros2_name, False
        )

        assert original.status == "undo_failed"


# ---------------------------------------------------------------------------
# namespace-scoped restart routes to correct stack_namespace
# ---------------------------------------------------------------------------


class TestNamespaceScopedRestart:
    """Non-hot-reload param save must restart only the correct stack_namespace."""

    def _make_discovered_node(self, node_path: str, stack_namespace: str) -> Any:
        from nav2_config.core.node_discovery import DiscoveredNav2Node

        return DiscoveredNav2Node(
            full_path=node_path,
            basename=node_path.split("/")[-1],
            ros_namespace=stack_namespace,
            stack_namespace=stack_namespace,
            display_name=node_path.split("/")[-1],
        )

    def _trigger_save_restart(self, win: Any, node_path: str, param_name: str) -> None:
        """Invoke the Save & Restart callback wired by _on_param_set_requested.

        Patches _RestartAllProgressDialog so no real QDialog is constructed
        (that would require a full QApplication, not just QCoreApplication).
        """
        import nav2_config.gui.main_window as mw_module

        with patch.object(mw_module, "_RestartAllProgressDialog") as MockDialog:
            MockDialog.return_value = MagicMock()
            win._on_param_set_requested(node_path, param_name, True)

        show_for_call = win._notification_bar.show_for.call_args
        on_save_restart = show_for_call[1]["on_save_restart"]

        with patch.object(mw_module, "_RestartAllProgressDialog") as MockDialog:
            MockDialog.return_value = MagicMock()
            on_save_restart()

    def _make_non_hot_reload_setup(self, win: Any, node_path: str) -> None:
        defn = _make_param_def(
            node_path.split("/")[-1], "use_sim_time", hot_reload=False, type="bool"
        )
        from nav2_config.types.params import ParamValue

        pv = ParamValue(definition=defn, current_value=False)
        mock_row = MagicMock()
        mock_row._param_value = pv
        win._param_panel._all_rows = [mock_row]
        win._current_params = [pv]
        win._config_file = MagicMock()
        win._config_file.to_yaml_string = MagicMock(return_value="")
        win._config_file.save = MagicMock()

    def test_restart_routes_to_node_stack_namespace(self, imports):
        """When the user triggers Save & Restart, request_lifecycle_restart_stack_ns
        is called with the stack_namespace of the node being saved, not a global restart."""
        win = _make_bare_main_window(imports)

        node_path = "/robot1/controller_server"
        stack_namespace = "/robot1"
        win._topology_nodes[node_path] = self._make_discovered_node(node_path, stack_namespace)
        self._make_non_hot_reload_setup(win, node_path)

        self._trigger_save_restart(win, node_path, "use_sim_time")

        win._node.request_lifecycle_restart_stack_ns.assert_called_once_with(stack_namespace)

    def test_restart_uses_robot1_not_robot2_namespace(self, imports):
        """Restarting a /robot1 node must never call restart on /robot2."""
        win = _make_bare_main_window(imports)

        node_path = "/robot1/planner_server"
        win._topology_nodes[node_path] = self._make_discovered_node(node_path, "/robot1")
        self._make_non_hot_reload_setup(win, node_path)

        self._trigger_save_restart(win, node_path, "use_sim_time")

        call_args = win._node.request_lifecycle_restart_stack_ns.call_args[0]
        assert call_args[0] == "/robot1"
        assert call_args[0] != "/robot2"

    def test_missing_topology_falls_back_to_global_restart(self, imports):
        """If the node is not in _topology_nodes, fall back to request_nav2_stack_restart."""
        win = _make_bare_main_window(imports)

        # No entry in _topology_nodes for this node
        node_path = "/unknown_ns/controller_server"
        self._make_non_hot_reload_setup(win, node_path)

        self._trigger_save_restart(win, node_path, "use_sim_time")

        win._node.request_nav2_stack_restart.assert_called_once()
        win._node.request_lifecycle_restart_stack_ns.assert_not_called()


# ---------------------------------------------------------------------------
# _on_stack_action_requested: namespace-scoped restart from node panel
# ---------------------------------------------------------------------------


class TestStackActionRequestedRestart:
    """_on_stack_action_requested dispatches restart to the correct stack."""

    def test_restart_stack_action_uses_stack_namespace(self, imports):
        """A 'restart_stack' action from the node panel targets the supplied namespace."""
        win = _make_bare_main_window(imports)

        win._on_stack_action_requested("/robot2", "restart_stack")

        win._node.request_lifecycle_restart_stack.assert_called_once_with("/robot2")

    def test_pause_stack_action_uses_stack_namespace(self, imports):
        win = _make_bare_main_window(imports)
        win._on_stack_action_requested("/robot1", "pause_stack")
        win._node.request_lifecycle_pause_stack_ns.assert_called_once_with("/robot1")

    def test_resume_stack_action_uses_stack_namespace(self, imports):
        win = _make_bare_main_window(imports)
        win._on_stack_action_requested("/robot1", "resume_stack")
        win._node.request_lifecycle_resume_stack_ns.assert_called_once_with("/robot1")

    def test_restart_stack_robot1_not_robot2(self, imports):
        """Restarting /robot1 must not restart /robot2."""
        win = _make_bare_main_window(imports)
        win._on_stack_action_requested("/robot1", "restart_stack")

        call_args = win._node.request_lifecycle_restart_stack.call_args[0]
        assert call_args[0] == "/robot1"
        assert call_args[0] != "/robot2"
