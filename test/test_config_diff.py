# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for config_diff — ParamSnapshot creation and diff_snapshots().

No ROS2 environment required.  config_diff has no PyQt6 dependency so no
QCoreApplication fixture is needed here.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.core.config_diff import (
    DiffKind,
    ParamSnapshot,
    ParamSnapshotEntry,
    diff_snapshots,
    snapshot_from_param_values,
)
from nav2_config.types.history import ParamRef
from nav2_config.types.params import Nav2ParamDef, ParamValue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_param_def(
    node: str,
    param: str,
    type: str = "double",
    default: object = 0.0,
    *,
    ros2_name: str = "",
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
        hot_reload=True,
        tags=[],
        ros2_name=ros2_name or param,
    )


def _make_param_value(
    node: str,
    param: str,
    value: object,
    type: str = "double",
) -> ParamValue:
    """Create a ParamValue whose current_value is *value*."""
    defn = _make_param_def(node, param, type, default=value)
    return ParamValue(definition=defn, current_value=value)


def _make_snapshot(*entries: tuple[str, str, object, str]) -> ParamSnapshot:
    """Build a ParamSnapshot directly from (node_path, param_name, value, type_hint) tuples."""
    snapshot = ParamSnapshot(
        snapshot_id="test-snapshot-id",
        label="test",
        captured_at=datetime.now(),
    )
    for node_path, param_name, value, type_hint in entries:
        ref = ParamRef(node_path=node_path, param_name=param_name)
        snapshot.entries[ref] = ParamSnapshotEntry(
            ref=ref,
            value=value,
            type_hint=type_hint,
            ros2_name=param_name,
        )
    return snapshot


# ---------------------------------------------------------------------------
# ParamSnapshot: snapshot_from_param_values
# ---------------------------------------------------------------------------


def test_snapshot_from_param_values_returns_param_snapshot() -> None:
    """snapshot_from_param_values() returns a ParamSnapshot instance."""
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    result = snapshot_from_param_values("/controller_server", [pv], "session_start")
    assert isinstance(result, ParamSnapshot)


def test_snapshot_from_param_values_preserves_label() -> None:
    """The label argument is stored verbatim on the snapshot."""
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    snap = snapshot_from_param_values("/controller_server", [pv], "my_label")
    assert snap.label == "my_label"


def test_snapshot_from_param_values_generates_uuid_snapshot_id() -> None:
    """Each snapshot gets a non-empty UUID4 string as snapshot_id."""
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    snap = snapshot_from_param_values("/controller_server", [pv], "test")
    assert snap.snapshot_id
    assert "-" in snap.snapshot_id  # UUID4 contains hyphens


def test_snapshot_from_param_values_two_snapshots_have_different_ids() -> None:
    """Two calls produce two distinct snapshot_ids."""
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    a = snapshot_from_param_values("/controller_server", [pv], "test")
    b = snapshot_from_param_values("/controller_server", [pv], "test")
    assert a.snapshot_id != b.snapshot_id


def test_snapshot_from_param_values_correct_node_path_in_ref() -> None:
    """The ParamRef key uses the node_path argument, not the definition's node field."""
    pv = _make_param_value("controller_server", "controller_frequency", 20.0)
    snap = snapshot_from_param_values("/robot1/controller_server", [pv], "test")

    ref = ParamRef(node_path="/robot1/controller_server", param_name="controller_frequency")
    assert ref in snap.entries


def test_snapshot_from_param_values_correct_param_name_in_ref() -> None:
    """The ParamRef key uses the dot-notation param name from the definition."""
    pv = _make_param_value("controller_server", "min_x_velocity_threshold", 0.0001)
    snap = snapshot_from_param_values("/controller_server", [pv], "test")

    ref = ParamRef(node_path="/controller_server", param_name="min_x_velocity_threshold")
    assert ref in snap.entries


def test_snapshot_from_param_values_stores_current_value() -> None:
    """The snapshot entry value is current_value, not the schema default."""
    defn = _make_param_def("controller_server", "controller_frequency", default=20.0)
    pv = ParamValue(definition=defn, current_value=42.0)
    snap = snapshot_from_param_values("/controller_server", [pv], "test")

    ref = ParamRef(node_path="/controller_server", param_name="controller_frequency")
    assert snap.entries[ref].value == 42.0


def test_snapshot_from_param_values_stores_type_hint() -> None:
    """The type field from the definition is stored in the snapshot entry's type_hint."""
    defn = _make_param_def("controller_server", "use_realtime_priority", type="bool", default=False)
    pv = ParamValue(definition=defn, current_value=True)
    snap = snapshot_from_param_values("/controller_server", [pv], "test")

    ref = ParamRef(node_path="/controller_server", param_name="use_realtime_priority")
    assert snap.entries[ref].type_hint == "bool"


def test_snapshot_from_param_values_multiple_params_all_stored() -> None:
    """All params in the list appear as separate entries."""
    params = [
        _make_param_value("controller_server", "controller_frequency", 20.0),
        _make_param_value("controller_server", "min_x_velocity_threshold", 0.0001),
        _make_param_value("controller_server", "failure_tolerance", 0.3),
    ]
    snap = snapshot_from_param_values("/controller_server", params, "test")
    assert len(snap.entries) == 3


def test_snapshot_from_param_values_empty_params_list() -> None:
    """An empty params list produces a snapshot with no entries."""
    snap = snapshot_from_param_values("/controller_server", [], "empty")
    assert snap.entries == {}


# ---------------------------------------------------------------------------
# diff_snapshots — empty and identical snapshots
# ---------------------------------------------------------------------------


def test_diff_snapshots_both_empty_returns_empty() -> None:
    """Two empty snapshots produce an empty diff."""
    assert diff_snapshots(_make_snapshot(), _make_snapshot()) == []


def test_diff_snapshots_identical_params_excluded() -> None:
    """A param present in both snapshots with the same value does not appear in the diff."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    assert diff_snapshots(left, right) == []


def test_diff_snapshots_identical_bool_param_excluded() -> None:
    """Identical bool params (str(False) == str(False)) are excluded."""
    left = _make_snapshot(("/controller_server", "use_realtime_priority", False, "bool"))
    right = _make_snapshot(("/controller_server", "use_realtime_priority", False, "bool"))
    assert diff_snapshots(left, right) == []


# ---------------------------------------------------------------------------
# diff_snapshots — CHANGED
# ---------------------------------------------------------------------------


def test_diff_snapshots_changed_kind() -> None:
    """A param in both snapshots with differing values produces DiffKind.CHANGED."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot(("/controller_server", "controller_frequency", 30.0, "double"))

    result = diff_snapshots(left, right)
    assert len(result) == 1
    assert result[0].kind is DiffKind.CHANGED


def test_diff_snapshots_changed_carries_correct_left_and_right_values() -> None:
    """The CHANGED entry's left_value and right_value match the snapshot values."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot(("/controller_server", "controller_frequency", 30.0, "double"))

    entry = diff_snapshots(left, right)[0]
    assert entry.left_value == 20.0
    assert entry.right_value == 30.0


def test_diff_snapshots_changed_bool_param() -> None:
    """A bool param that flips from False to True is detected as CHANGED."""
    left = _make_snapshot(("/controller_server", "use_realtime_priority", False, "bool"))
    right = _make_snapshot(("/controller_server", "use_realtime_priority", True, "bool"))

    result = diff_snapshots(left, right)
    assert len(result) == 1
    assert result[0].kind is DiffKind.CHANGED


def test_diff_snapshots_changed_string_param() -> None:
    """A string param whose value changes is detected."""
    left = _make_snapshot(("/controller_server", "robot_base_frame", "base_link", "string"))
    right = _make_snapshot(("/controller_server", "robot_base_frame", "base_footprint", "string"))

    result = diff_snapshots(left, right)
    assert len(result) == 1
    assert result[0].kind is DiffKind.CHANGED


# ---------------------------------------------------------------------------
# diff_snapshots — REMOVED
# ---------------------------------------------------------------------------


def test_diff_snapshots_removed_kind() -> None:
    """A param only in the left snapshot yields DiffKind.REMOVED."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot()

    result = diff_snapshots(left, right)
    assert len(result) == 1
    assert result[0].kind is DiffKind.REMOVED


def test_diff_snapshots_removed_has_left_value_and_no_right_value() -> None:
    """A REMOVED entry carries the original value as left_value; right_value is None."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot()

    entry = diff_snapshots(left, right)[0]
    assert entry.left_value == 20.0
    assert entry.right_value is None


# ---------------------------------------------------------------------------
# diff_snapshots — ADDED
# ---------------------------------------------------------------------------


def test_diff_snapshots_added_kind() -> None:
    """A param only in the right snapshot yields DiffKind.ADDED."""
    left = _make_snapshot()
    right = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))

    result = diff_snapshots(left, right)
    assert len(result) == 1
    assert result[0].kind is DiffKind.ADDED


def test_diff_snapshots_added_has_no_left_value_and_right_value() -> None:
    """An ADDED entry has left_value as None and carries the new value as right_value."""
    left = _make_snapshot()
    right = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))

    entry = diff_snapshots(left, right)[0]
    assert entry.left_value is None
    assert entry.right_value == 20.0


# ---------------------------------------------------------------------------
# diff_snapshots — entry field correctness
# ---------------------------------------------------------------------------


def test_diff_entry_ref_has_correct_node_path_and_param_name() -> None:
    """The diff entry's ref carries the node_path and param_name from the snapshot."""
    left = _make_snapshot(("/robot1/controller_server", "max_vel_x", 1.0, "double"))
    right = _make_snapshot(("/robot1/controller_server", "max_vel_x", 2.0, "double"))

    entry = diff_snapshots(left, right)[0]
    assert entry.ref.node_path == "/robot1/controller_server"
    assert entry.ref.param_name == "max_vel_x"


def test_diff_entry_type_hint_taken_from_right_on_changed() -> None:
    """For a CHANGED param, type_hint comes from the right (target) snapshot entry."""
    left = _make_snapshot(("/controller_server", "use_realtime_priority", False, "bool"))
    right = _make_snapshot(("/controller_server", "use_realtime_priority", True, "bool"))

    entry = diff_snapshots(left, right)[0]
    assert entry.type_hint == "bool"


def test_diff_entry_ros2_name_preserved() -> None:
    """The diff entry's ros2_name matches the ros2_name stored in the snapshot entry."""
    left = _make_snapshot(("/controller_server", "controller_frequency", 20.0, "double"))
    right = _make_snapshot(("/controller_server", "controller_frequency", 30.0, "double"))

    entry = diff_snapshots(left, right)[0]
    assert entry.ros2_name == "controller_frequency"


# ---------------------------------------------------------------------------
# diff_snapshots — multiple params and nodes
# ---------------------------------------------------------------------------


def test_diff_snapshots_multiple_changed_params_all_detected() -> None:
    """All changed params in a snapshot appear in the diff."""
    left = _make_snapshot(
        ("/controller_server", "controller_frequency", 20.0, "double"),
        ("/controller_server", "min_x_velocity_threshold", 0.0001, "double"),
    )
    right = _make_snapshot(
        ("/controller_server", "controller_frequency", 30.0, "double"),
        ("/controller_server", "min_x_velocity_threshold", 0.001, "double"),
    )

    result = diff_snapshots(left, right)
    assert len(result) == 2
    assert all(e.kind is DiffKind.CHANGED for e in result)


def test_diff_snapshots_unchanged_param_excluded_in_mixed_snapshot() -> None:
    """A stable param is excluded even when sibling params differ."""
    left = _make_snapshot(
        ("/controller_server", "controller_frequency", 20.0, "double"),
        ("/controller_server", "stable_param", 5.0, "double"),
    )
    right = _make_snapshot(
        ("/controller_server", "controller_frequency", 30.0, "double"),
        ("/controller_server", "stable_param", 5.0, "double"),
    )

    result = diff_snapshots(left, right)
    param_names = {e.ref.param_name for e in result}
    assert "stable_param" not in param_names
    assert "controller_frequency" in param_names


def test_diff_snapshots_multiple_nodes_both_detected() -> None:
    """Params from different nodes are each diffed independently."""
    left = _make_snapshot(
        ("/controller_server", "controller_frequency", 20.0, "double"),
        ("/planner_server", "planner_frequency", 1.0, "double"),
    )
    right = _make_snapshot(
        ("/controller_server", "controller_frequency", 30.0, "double"),
        ("/planner_server", "planner_frequency", 2.0, "double"),
    )

    result = diff_snapshots(left, right)
    node_paths = {e.ref.node_path for e in result}
    assert "/controller_server" in node_paths
    assert "/planner_server" in node_paths
    assert len(result) == 2


def test_diff_snapshots_mixed_kinds_all_detected() -> None:
    """CHANGED, REMOVED, and ADDED params are all found in one pass."""
    left = _make_snapshot(
        ("/controller_server", "a_changed", 1.0, "double"),
        ("/controller_server", "b_removed", 2.0, "double"),
    )
    right = _make_snapshot(
        ("/controller_server", "a_changed", 9.0, "double"),
        ("/controller_server", "c_added", 3.0, "double"),
    )

    result = diff_snapshots(left, right)
    kinds = {e.kind for e in result}
    assert DiffKind.CHANGED in kinds
    assert DiffKind.REMOVED in kinds
    assert DiffKind.ADDED in kinds


# ---------------------------------------------------------------------------
# diff_snapshots — output ordering (CHANGED → REMOVED → ADDED)
# ---------------------------------------------------------------------------


def test_diff_snapshots_ordering_changed_before_removed_before_added() -> None:
    """diff_snapshots returns CHANGED first, then REMOVED, then ADDED."""
    left = _make_snapshot(
        ("/controller_server", "a_changed", 1.0, "double"),
        ("/controller_server", "b_removed", 2.0, "double"),
    )
    right = _make_snapshot(
        ("/controller_server", "a_changed", 9.0, "double"),
        ("/controller_server", "c_added", 3.0, "double"),
    )

    kinds = [e.kind for e in diff_snapshots(left, right)]
    changed_idx = kinds.index(DiffKind.CHANGED)
    removed_idx = kinds.index(DiffKind.REMOVED)
    added_idx = kinds.index(DiffKind.ADDED)
    assert changed_idx < removed_idx < added_idx


def test_diff_snapshots_changed_group_sorted_by_node_then_param() -> None:
    """Within the CHANGED group, entries are sorted by (node_path, param_name)."""
    left = _make_snapshot(
        ("/planner_server", "planner_frequency", 1.0, "double"),
        ("/controller_server", "controller_frequency", 20.0, "double"),
    )
    right = _make_snapshot(
        ("/planner_server", "planner_frequency", 2.0, "double"),
        ("/controller_server", "controller_frequency", 30.0, "double"),
    )

    result = diff_snapshots(left, right)
    assert len(result) == 2
    assert result[0].ref.node_path == "/controller_server"
    assert result[1].ref.node_path == "/planner_server"
