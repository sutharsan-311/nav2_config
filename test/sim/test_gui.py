# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: the GUI widgets themselves, driven offscreen against the running stack."""

import re

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from nav2_config.gui.widgets.param_row import _SetState
from sim.helpers import SignalRecorder, ros2_param_get, select_node, wait_until

pytestmark = pytest.mark.sim

NODE = "/controller_server"


def _find_row(app, param: str):
    return next((r for r in app.window._param_panel._all_rows
                 if r._param_value.definition.param == param), None)


def _row(app, param: str):
    """The ParamRow for *param*, waiting for the panel to build it."""
    try:
        wait_until(lambda: _find_row(app, param) is not None, 30, what=f"row for {param}")
    except TimeoutError:
        rows = app.window._param_panel._all_rows
        pytest.fail(f"no row for {param}; panel has {len(rows)} rows, e.g. "
                    f"{[r._param_value.definition.param for r in rows[:8]]}")
    return _find_row(app, param)


def _wait_state(app, row, state, what: str) -> None:
    try:
        wait_until(lambda: row._set_btn.state is state, 30, what=what)
    except TimeoutError:
        pytest.fail(f"{what}: button is {row._set_btn.state.name}; "
                    f"window selected={app.window._selected_node_path!r} "
                    f"pending_set={dict(app.window._pending_set_values)}")


def _float(text: str) -> float:
    return float(re.search(r"[-\d.]+$", text).group())


def test_select_node_populates_rows(app):
    select_node(app, NODE)
    wait_until(lambda: len(app.window._param_panel._all_rows) > 50, 30,
               what="more than 50 parameter rows")
    rows = app.window._param_panel._all_rows
    assert all(r._param_value.definition.node == "controller_server" for r in rows)
    live = _row(app, "FollowPath.max_vel_x")._param_value
    assert live.is_live
    assert live.current_value == pytest.approx(_float(ros2_param_get(NODE, "FollowPath.max_vel_x")))


def test_set_button_cycle_and_inspector_tabs(app, restore_params):
    name = "FollowPath.max_vel_x"
    restore_params(NODE, name)
    row = select_node(app, NODE, name)
    assert row._set_btn.state is _SetState.IDLE
    # Record every state the button passes through; polling alone can miss a short SUCCESS.
    seen: list[str] = []
    real_set_state = row._set_btn.set_state
    row._set_btn.set_state = lambda st: (seen.append(st.name), real_set_state(st))[1]

    row._on_value_changed(0.17)              # what the input widget calls on user edit
    assert row._set_btn.state is _SetState.READY
    row._set_btn.click()
    assert row._set_btn.state is _SetState.PENDING
    wait_until(lambda: "SUCCESS" in seen, 30, what=f"Set button SUCCESS (saw {seen})")
    assert seen.index("PENDING") < seen.index("SUCCESS")
    assert _float(ros2_param_get(NODE, name)) == pytest.approx(0.17)

    # YAML tab shows the new value, History tab lists the change.
    wait_until(lambda: "max_vel_x: 0.17" in app.window._yaml_panel._editor.toPlainText(),
               15, what="YAML preview shows max_vel_x: 0.17")
    assert app.window._history_panel._tree.topLevelItemCount() >= 1
    # Compare tab: live against itself has no differences and does not raise.
    app.window._on_compare_requested("Live (current node)", "Live (current node)")
    assert app.window._compare_panel._table.rowCount() == 0
    tabs = app.window._inspector._tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["YAML", "History", "Compare"]


def test_set_button_failed_state_on_unsendable_value(app):
    # Text typed into a numeric row that cannot be encoded: the set must fail visibly, not hang.
    row = select_node(app, NODE, "FollowPath.max_vel_theta")
    before = ros2_param_get(NODE, "FollowPath.max_vel_theta")
    row._on_value_changed("abc")
    assert row._set_btn.state is _SetState.READY
    results = SignalRecorder(app.node.signals.param_set_result)
    row._set_btn.click()
    try:
        _wait_state(app, row, _SetState.FAILED, "Set button FAILED")
    except pytest.fail.Exception as exc:
        raise AssertionError(f"{exc}; param_set_result calls={results.calls}") from None
    assert ros2_param_get(NODE, "FollowPath.max_vel_theta") == before


def test_ctrl_k_focuses_search_and_filters_rows(app):
    select_node(app, NODE)
    window = app.window
    window.activateWindow()
    window.raise_()
    QApplication.processEvents()
    search = window._param_panel._search

    QTest.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    wait_until(search.hasFocus, 5, what="Ctrl+K to focus the search box")
    QTest.keyClicks(search, "max_vel_x")
    wait_until(lambda: _row(app, "controller_frequency").isHidden(), 5,
               what="non-matching row hidden by search")
    assert not _row(app, "FollowPath.max_vel_x").isHidden()

    QTest.keyClick(search, Qt.Key.Key_Escape)
    wait_until(lambda: search.text() == "", 5, what="Escape to clear search")
    wait_until(lambda: not _row(app, "controller_frequency").isHidden(), 5,
               what="rows shown again after clearing search")


def test_file_shortcuts_are_bound(app):
    # Not triggered: Save/Open would pop modal file dialogs nobody can answer offscreen.
    w = app.window
    assert w._save_action.shortcut() == QKeySequence("Ctrl+S")
    opens = [a for a in w.findChildren(type(w._save_action))
             if a.shortcut() == QKeySequence("Ctrl+O")]
    assert opens, "no action bound to Ctrl+O"
