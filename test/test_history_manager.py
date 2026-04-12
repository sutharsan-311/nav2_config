# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for HistoryManager — no ROS2 environment required."""

from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.core.history_manager import HistoryManager
from nav2_config.types.history import ChangeSource, ParamHistoryEntry, ParamRef


# ---------------------------------------------------------------------------
# Session-scoped Qt application (required by QObject / signals)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def qapp():
    """Provide a QCoreApplication for the test session.

    HistoryManager is a QObject subclass with pyqtSignals.  PyQt6 requires a
    QCoreApplication instance to exist before any QObject is created.
    """
    from PyQt6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ref(
    node_path: str = "/controller_server",
    param_name: str = "controller_frequency",
) -> ParamRef:
    return ParamRef(node_path=node_path, param_name=param_name)


def _make_entry(
    *,
    node_path: str = "/controller_server",
    param_name: str = "controller_frequency",
    old_value: object = 10.0,
    new_value: object = 20.0,
    source: ChangeSource = ChangeSource.LIVE_SET,
    status: str = "pending",
) -> ParamHistoryEntry:
    return ParamHistoryEntry(
        entry_id=str(uuid.uuid4()),
        timestamp=datetime.now(),
        ref=ParamRef(node_path=node_path, param_name=param_name),
        old_value=old_value,
        new_value=new_value,
        source=source,
        batch_id=None,
        ros2_name=param_name,
        type_hint="double",
        hot_reload=True,
        status=status,
    )


# ---------------------------------------------------------------------------
# record_change — basic append behaviour
# ---------------------------------------------------------------------------


def test_record_change_adds_entry_to_history(qapp) -> None:
    """record_change() makes the entry retrievable via get_history()."""
    mgr = HistoryManager()
    entry = _make_entry()
    mgr.record_change(entry)
    assert entry in mgr.get_history()


def test_record_change_increments_history_length(qapp) -> None:
    """Each call to record_change() grows the history by one."""
    mgr = HistoryManager()
    mgr.record_change(_make_entry())
    mgr.record_change(_make_entry())
    assert len(mgr.get_history()) == 2


def test_record_change_updates_latest_value_cache(qapp) -> None:
    """record_change() stores new_value in the latest-value cache keyed by ref."""
    mgr = HistoryManager()
    ref = _make_ref()
    mgr.record_change(_make_entry(old_value=10.0, new_value=20.0))
    assert mgr.get_latest_value(ref) == 20.0


def test_record_change_latest_value_reflects_most_recent(qapp) -> None:
    """When the same param is changed twice, get_latest_value() returns the last value."""
    mgr = HistoryManager()
    ref = _make_ref()
    mgr.record_change(_make_entry(old_value=10.0, new_value=20.0))
    mgr.record_change(_make_entry(old_value=20.0, new_value=30.0))
    assert mgr.get_latest_value(ref) == 30.0


def test_get_latest_value_returns_none_for_unknown_ref(qapp) -> None:
    """get_latest_value() returns None when the param has never been recorded."""
    mgr = HistoryManager()
    assert mgr.get_latest_value(_make_ref()) is None


# ---------------------------------------------------------------------------
# get_history — ordering and copy safety
# ---------------------------------------------------------------------------


def test_get_history_returns_entries_in_recorded_order(qapp) -> None:
    """Entries are stored in insertion order: first recorded is history[0].

    The newest-first display is the GUI panel's (HistoryPanel) responsibility —
    it inserts new QTreeWidgetItems at position 0.  HistoryManager itself is
    an append-only log and returns entries oldest-first.
    """
    mgr = HistoryManager()
    first = _make_entry(new_value=1.0)
    second = _make_entry(new_value=2.0)
    third = _make_entry(new_value=3.0)
    mgr.record_change(first)
    mgr.record_change(second)
    mgr.record_change(third)

    history = mgr.get_history()
    assert history[0] is first
    assert history[1] is second
    assert history[2] is third


def test_get_history_returns_shallow_copy(qapp) -> None:
    """get_history() returns a new list; mutating it does not affect internal state."""
    mgr = HistoryManager()
    mgr.record_change(_make_entry())
    copy = mgr.get_history()
    copy.clear()
    assert len(mgr.get_history()) == 1


# ---------------------------------------------------------------------------
# record_change — all ChangeSource values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("source", [
    ChangeSource.LIVE_SET,
    ChangeSource.FILE_LOAD,
    ChangeSource.EXTERNAL_CHANGE,
    ChangeSource.COMPARE_APPLY,
    ChangeSource.UNDO,
])
def test_record_change_stores_all_sources(qapp, source: ChangeSource) -> None:
    """record_change() stores entries for every ChangeSource variant."""
    mgr = HistoryManager()
    entry = _make_entry(source=source)
    mgr.record_change(entry)

    history = mgr.get_history()
    assert len(history) == 1
    assert history[0].source is source


# ---------------------------------------------------------------------------
# undo_entry
# ---------------------------------------------------------------------------


def test_undo_entry_swaps_old_and_new_values(qapp) -> None:
    """undo_entry() reverses old/new: the undo entry restores the pre-change value."""
    mgr = HistoryManager()
    original = _make_entry(old_value=10.0, new_value=20.0)
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    assert undo is not None
    assert undo.old_value == 20.0
    assert undo.new_value == 10.0


def test_undo_entry_source_is_undo(qapp) -> None:
    """The undo entry always carries ChangeSource.UNDO regardless of original source."""
    mgr = HistoryManager()
    original = _make_entry(source=ChangeSource.LIVE_SET)
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    assert undo is not None
    assert undo.source is ChangeSource.UNDO


def test_undo_entry_is_recorded_in_history(qapp) -> None:
    """undo_entry() calls record_change() internally, so the undo appears in get_history()."""
    mgr = HistoryManager()
    original = _make_entry()
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    history = mgr.get_history()
    assert len(history) == 2
    assert history[-1] is undo


def test_undo_entry_preserves_ref(qapp) -> None:
    """The undo entry points to the same node/param as the original."""
    mgr = HistoryManager()
    original = _make_entry(node_path="/robot1/planner_server", param_name="max_vel_x")
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    assert undo is not None
    assert undo.ref == original.ref


def test_undo_entry_preserves_ros2_name_type_hint_hot_reload(qapp) -> None:
    """ros2_name, type_hint, and hot_reload are copied verbatim from the original."""
    mgr = HistoryManager()
    original = _make_entry()
    # Override fields that _make_entry sets to defaults
    original.ros2_name = "FollowPath.max_vel_x"
    original.type_hint = "double"
    original.hot_reload = False
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    assert undo is not None
    assert undo.ros2_name == "FollowPath.max_vel_x"
    assert undo.type_hint == "double"
    assert undo.hot_reload is False


def test_undo_entry_gets_new_entry_id(qapp) -> None:
    """The undo entry has a different entry_id than the original (it is a new event)."""
    mgr = HistoryManager()
    original = _make_entry()
    mgr.record_change(original)

    undo = mgr.undo_entry(original.entry_id)

    assert undo is not None
    assert undo.entry_id != original.entry_id


def test_undo_entry_unknown_id_returns_none(qapp) -> None:
    """undo_entry() returns None when the entry_id is not in the history."""
    mgr = HistoryManager()
    assert mgr.undo_entry("nonexistent-id") is None


def test_undo_entry_unknown_id_does_not_grow_history(qapp) -> None:
    """A failed undo (unknown id) leaves the history unchanged."""
    mgr = HistoryManager()
    mgr.record_change(_make_entry())
    mgr.undo_entry("nonexistent-id")
    assert len(mgr.get_history()) == 1


# ---------------------------------------------------------------------------
# Session-start snapshot
# ---------------------------------------------------------------------------


def test_get_session_start_snapshot_initially_none(qapp) -> None:
    """The session-start snapshot is None before set_session_start_snapshot() is called."""
    mgr = HistoryManager()
    assert mgr.get_session_start_snapshot() is None


def test_set_session_start_snapshot_stores_object(qapp) -> None:
    """set_session_start_snapshot() stores the snapshot and get_session_start_snapshot() returns it."""
    mgr = HistoryManager()
    sentinel = object()
    mgr.set_session_start_snapshot(sentinel)
    assert mgr.get_session_start_snapshot() is sentinel


def test_set_session_start_snapshot_can_be_replaced(qapp) -> None:
    """Calling set_session_start_snapshot() again replaces the previous value."""
    mgr = HistoryManager()
    first = object()
    second = object()
    mgr.set_session_start_snapshot(first)
    mgr.set_session_start_snapshot(second)
    assert mgr.get_session_start_snapshot() is second


# ---------------------------------------------------------------------------
# update_entry_status
# ---------------------------------------------------------------------------


def test_update_entry_status_mutates_status_field(qapp) -> None:
    """update_entry_status() changes the status on the matching entry in place."""
    mgr = HistoryManager()
    entry = _make_entry(status="pending")
    mgr.record_change(entry)
    mgr.update_entry_status(entry.entry_id, "applied")
    assert entry.status == "applied"


def test_update_entry_status_unknown_id_is_noop(qapp) -> None:
    """Updating an unknown entry_id does not raise and leaves existing entries intact."""
    mgr = HistoryManager()
    entry = _make_entry(status="pending")
    mgr.record_change(entry)
    mgr.update_entry_status("nonexistent-id", "failed")  # must not raise
    assert entry.status == "pending"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


def test_clear_empties_history(qapp) -> None:
    """clear() removes all recorded entries from the history list."""
    mgr = HistoryManager()
    mgr.record_change(_make_entry())
    mgr.record_change(_make_entry())
    mgr.clear()
    assert mgr.get_history() == []


def test_clear_empties_latest_value_cache(qapp) -> None:
    """clear() flushes the latest-value cache; get_latest_value returns None afterwards."""
    mgr = HistoryManager()
    ref = _make_ref()
    mgr.record_change(_make_entry())
    mgr.clear()
    assert mgr.get_latest_value(ref) is None


def test_clear_resets_session_start_snapshot(qapp) -> None:
    """clear() sets the session-start snapshot back to None."""
    mgr = HistoryManager()
    mgr.set_session_start_snapshot(object())
    mgr.clear()
    assert mgr.get_session_start_snapshot() is None


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def test_history_entry_added_signal_emitted_on_record(qapp) -> None:
    """history_entry_added fires with the new entry every time record_change() is called."""
    mgr = HistoryManager()
    received: list[object] = []
    mgr.history_entry_added.connect(received.append)

    entry = _make_entry()
    mgr.record_change(entry)

    assert len(received) == 1
    assert received[0] is entry


def test_history_entry_added_signal_carries_undo_entry(qapp) -> None:
    """undo_entry() also triggers history_entry_added because it calls record_change()."""
    mgr = HistoryManager()
    received: list[object] = []
    original = _make_entry()
    mgr.record_change(original)

    mgr.history_entry_added.connect(received.append)
    undo = mgr.undo_entry(original.entry_id)

    assert len(received) == 1
    assert received[0] is undo


def test_history_reset_signal_emitted_on_clear(qapp) -> None:
    """history_reset fires once when clear() is called."""
    mgr = HistoryManager()
    fired: list[int] = []
    mgr.history_reset.connect(lambda: fired.append(1))

    mgr.clear()

    assert len(fired) == 1


def test_snapshots_changed_signal_emitted_on_set_snapshot(qapp) -> None:
    """snapshots_changed fires when set_session_start_snapshot() is called."""
    mgr = HistoryManager()
    fired: list[int] = []
    mgr.snapshots_changed.connect(lambda: fired.append(1))

    mgr.set_session_start_snapshot(object())

    assert len(fired) == 1


def test_history_entry_updated_signal_emitted_on_status_change(qapp) -> None:
    """history_entry_updated fires with the mutated entry when update_entry_status() matches."""
    mgr = HistoryManager()
    received: list[object] = []
    mgr.history_entry_updated.connect(received.append)

    entry = _make_entry()
    mgr.record_change(entry)
    mgr.update_entry_status(entry.entry_id, "applied")

    assert len(received) == 1
    assert received[0] is entry


# ---------------------------------------------------------------------------
# Bounded log (not yet implemented)
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="max_size parameter not yet implemented in HistoryManager.__init__")
def test_log_is_bounded_at_max_size(qapp) -> None:
    """When constructed with a max_size, recording beyond that limit evicts oldest entries."""
    mgr = HistoryManager(max_size=3)  # type: ignore[call-arg]
    for i in range(5):
        mgr.record_change(_make_entry(new_value=float(i)))
    assert len(mgr.get_history()) == 3
