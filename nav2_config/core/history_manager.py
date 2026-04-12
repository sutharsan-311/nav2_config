# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""HistoryManager — tracks parameter change history for the compare/history feature."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from PyQt6.QtCore import QObject, pyqtSignal

from nav2_config.types.history import ChangeSource, ParamHistoryEntry, ParamRef


class HistoryManager(QObject):
    """Tracks all parameter changes during a session.

    Maintains an ordered list of ParamHistoryEntry records and a map of the
    latest confirmed value per ParamRef, so callers can quickly check what value
    a parameter last had without scanning the full history.

    Also holds an optional session-start snapshot (set once at connection time)
    so the compare panel can diff current state against the initial state.

    All signals are emitted synchronously on whatever thread calls the mutating
    methods — callers must ensure they operate on the Qt main thread, or use
    Qt's queued connection mechanism for cross-thread delivery.
    """

    #: Emitted after the history list is cleared.
    history_reset = pyqtSignal()

    #: Emitted when a new entry is appended; carries the new ParamHistoryEntry.
    history_entry_added = pyqtSignal(object)

    #: Emitted when an existing entry's status is mutated; carries the entry.
    history_entry_updated = pyqtSignal(object)

    #: Emitted when the session-start snapshot changes (set or cleared).
    snapshots_changed = pyqtSignal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._history: list[ParamHistoryEntry] = []
        self._latest_values: dict[ParamRef, Any] = {}
        self._session_start_snapshot: Optional[object] = None  # ParamSnapshot from config_diff

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_change(self, entry: ParamHistoryEntry) -> None:
        """Append *entry* to the history and update the latest-value cache.

        Args:
            entry: The change event to record. Must have a unique entry_id.
        """
        self._history.append(entry)
        self._latest_values[entry.ref] = entry.new_value
        self.history_entry_added.emit(entry)

    def update_entry_status(self, entry_id: str, status: str) -> None:
        """Mutate the status field of the entry identified by *entry_id*.

        Emits history_entry_updated after the mutation.

        Args:
            entry_id: UUID string of the entry to update.
            status: New status string ('pending', 'applied', 'failed', 'undone').
        """
        for entry in self._history:
            if entry.entry_id == entry_id:
                entry.status = status
                self.history_entry_updated.emit(entry)
                return

    # ------------------------------------------------------------------
    # Undo
    # ------------------------------------------------------------------

    def undo_entry(self, entry_id: str) -> Optional[ParamHistoryEntry]:
        """Create and record an undo entry that reverses a previous change.

        Looks up the original entry, creates a new ParamHistoryEntry with
        UNDO source, old and new values swapped, then records it via
        record_change().

        The caller is responsible for actually applying the reversed parameter
        value to the live ROS2 node.

        Args:
            entry_id: UUID string of the entry to undo.

        Returns:
            The newly created undo entry, or None if *entry_id* is not found.
        """
        original: Optional[ParamHistoryEntry] = None
        for entry in self._history:
            if entry.entry_id == entry_id:
                original = entry
                break
        if original is None:
            return None

        self.update_entry_status(entry_id, "undone")
        undo_entry = ParamHistoryEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            ref=original.ref,
            old_value=original.new_value,
            new_value=original.old_value,
            source=ChangeSource.UNDO,
            batch_id=None,
            ros2_name=original.ros2_name,
            type_hint=original.type_hint,
            hot_reload=original.hot_reload,
            status="pending",
        )
        self.record_change(undo_entry)
        return undo_entry

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_history(self) -> list[ParamHistoryEntry]:
        """Return a shallow copy of the full history list.

        Returns:
            A new list containing all recorded ParamHistoryEntry objects.
        """
        return list(self._history)

    def get_latest_value(self, ref: ParamRef) -> Optional[Any]:
        """Return the most recently recorded value for *ref*, or None if unseen.

        Args:
            ref: The node/param to look up.

        Returns:
            The latest value, or None if no change has been recorded for *ref*.
        """
        return self._latest_values.get(ref)

    # ------------------------------------------------------------------
    # Session snapshot
    # ------------------------------------------------------------------

    def get_session_start_snapshot(self) -> Optional[object]:
        """Return the session-start ParamSnapshot, or None if not yet set.

        Returns:
            A ParamSnapshot (from config_diff) or None.
        """
        return self._session_start_snapshot

    def set_session_start_snapshot(self, snapshot: object) -> None:
        """Store the session-start snapshot and emit snapshots_changed.

        Args:
            snapshot: A ParamSnapshot from config_diff.snapshot_from_param_values().
        """
        self._session_start_snapshot = snapshot
        self.snapshots_changed.emit()

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all history and cached values, then emit history_reset."""
        self._history.clear()
        self._latest_values.clear()
        self._session_start_snapshot = None
        self.history_reset.emit()
