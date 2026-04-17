# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""HistoryPanel — chronological log of parameter changes.

Displays a QTreeWidget showing every parameter change recorded by
HistoryManager.  Rows are inserted newest-first (row 0).  Each row
carries a QPushButton to request an undo operation.  Color coding
on the row text signals the source of each change.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from nav2_config.core.history_manager import ParamHistoryEntry

logger = logging.getLogger(__name__)

# ── Source color palette ──────────────────────────────────────────────────────
_SOURCE_COLORS: dict[str, str] = {
    "live_set":       "#2979FF",   # blue
    "external change": "#FF8F00",  # amber
    "undo":           "#757575",   # gray
    "file load":      "#2E7D32",   # green
    "compare apply":  "#6A1B9A",   # purple
}

# Fallback for unrecognised source keys
_DEFAULT_FG = "#1a1a1a"

# Column indices
_COL_TIME   = 0
_COL_NODE   = 1
_COL_PARAM  = 2
_COL_OLD    = 3
_COL_NEW    = 4
_COL_SOURCE = 5
_COL_UNDO   = 6

_COLUMNS = ["Time", "Node", "Param", "Old", "New", "Source", "Undo"]

# Panel header colors — match RViz2 panel style from theme.py
_BG_HDR = "#d0d0d0"
_BORDER  = "#c0c0c0"
_FG      = "#1a1a1a"
_FG_DIM  = "#666666"


class HistoryPanel(QWidget):
    """Displays a chronological log of parameter changes, newest first.

    Signals:
        undo_requested(str): Emitted when the undo button on a row is clicked.
            The argument is the ``entry_id`` of the entry to undo.
    """

    undo_requested = pyqtSignal(str)  # entry_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())

        self._tree = QTreeWidget()
        self._tree.setColumnCount(len(_COLUMNS))
        self._tree.setHeaderLabels(_COLUMNS)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self._tree.setUniformRowHeights(True)

        header = self._tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_TIME,   QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_NODE,   QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_PARAM,  QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_OLD,    QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_NEW,    QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_SOURCE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_UNDO,   QHeaderView.ResizeMode.ResizeToContents)

        # Reasonable default column widths
        self._tree.setColumnWidth(_COL_NODE,   140)
        self._tree.setColumnWidth(_COL_OLD,    100)
        self._tree.setColumnWidth(_COL_NEW,    100)

        layout.addWidget(self._tree, stretch=1)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        title = QLabel("Parameter History")
        title.setStyleSheet(
            f"color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(20)
        clear_btn.setToolTip("Clear all history entries")
        clear_btn.setStyleSheet(
            f"QPushButton {{ font-size: 9pt; padding: 0 8px; }}"
        )
        clear_btn.clicked.connect(self.clear)
        layout.addWidget(clear_btn)

        return bar

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _source_label(self, entry: "ParamHistoryEntry") -> str:
        """Return a human-readable source string from the entry's ChangeSource."""
        try:
            raw = entry.source.name.lower().replace("_", " ")
        except AttributeError:
            raw = str(entry.source).lower()
        return raw

    def _row_color(self, source_label: str) -> str:
        return _SOURCE_COLORS.get(source_label, _DEFAULT_FG)

    def _apply_row_visuals(
        self,
        item: QTreeWidgetItem,
        entry: "ParamHistoryEntry",
        source_label: str,
    ) -> None:
        """Apply color, italic, and strikethrough depending on entry status."""
        fg = QColor(self._row_color(source_label))
        col_count = self._tree.columnCount()

        status = getattr(entry, "status", None)

        for col in range(col_count - 1):  # Skip the Undo button column
            item.setForeground(col, fg)

            if status == "failed":
                item.setForeground(col, QColor("#e53935"))
                font = item.font(col)
                font.setItalic(True)
                item.setFont(col, font)

            elif status == "undone":
                font = item.font(col)
                font.setStrikeOut(True)
                item.setFont(col, font)

            elif status == "undo_pending":
                font = item.font(col)
                font.setItalic(True)
                item.setFont(col, font)
                item.setForeground(col, QColor("#9e9e9e"))

            elif status == "undo_failed":
                item.setForeground(col, QColor("#e53935"))
                font = item.font(col)
                font.setItalic(True)
                item.setFont(col, font)

    def _make_undo_button(self, entry_id: str) -> QPushButton:
        btn = QPushButton("↩")
        btn.setFixedSize(26, 22)
        btn.setToolTip(f"Undo this change (id: {entry_id})")
        btn.setStyleSheet(
            "QPushButton { font-size: 11pt; padding: 0; }"
            "QPushButton:hover { background: #e3f2fd; }"
        )
        btn.clicked.connect(lambda: self.undo_requested.emit(entry_id))
        return btn

    def _build_item(self, entry: "ParamHistoryEntry") -> QTreeWidgetItem:
        """Create a QTreeWidgetItem from a ParamHistoryEntry."""
        import datetime

        # Format time
        ts = getattr(entry, "timestamp", None)
        if ts is None:
            time_str = "--:--:--"
        elif isinstance(ts, (int, float)):
            time_str = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        else:
            try:
                time_str = ts.strftime("%H:%M:%S")
            except AttributeError:
                time_str = str(ts)

        # Node display: basename + full path as tooltip.
        # node_path and param_name live on entry.ref (a ParamRef), not on the entry itself.
        ref = getattr(entry, "ref", None)
        node_path = (ref.node_path if ref is not None else "") or ""
        node_display = node_path.rstrip("/").rsplit("/", 1)[-1] if node_path else "—"

        param_name = (ref.param_name if ref is not None else "") or "—"
        old_value = entry.old_value if entry.old_value is not None else "—"
        new_value = getattr(entry, "new_value", "—")
        if new_value is None:
            new_value = "—"

        source_label = self._source_label(entry)

        item = QTreeWidgetItem([
            time_str,
            node_display,
            param_name,
            str(old_value),
            str(new_value),
            source_label,
            "",  # Undo button placeholder
        ])

        if node_path:
            item.setToolTip(_COL_NODE, node_path)

        item.setData(_COL_TIME, Qt.ItemDataRole.UserRole, entry.entry_id)

        self._apply_row_visuals(item, entry, source_label)

        return item

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_entry(self, entry: "ParamHistoryEntry") -> None:
        """Insert a new history entry at the top of the list (newest first).

        Args:
            entry: A ParamHistoryEntry from HistoryManager.
        """
        item = self._build_item(entry)
        self._tree.insertTopLevelItem(0, item)

        undo_btn = self._make_undo_button(entry.entry_id)
        self._tree.setItemWidget(item, _COL_UNDO, undo_btn)

    def update_entry(self, entry: "ParamHistoryEntry") -> None:
        """Find an existing row by entry_id and refresh its status visuals.

        Args:
            entry: Updated ParamHistoryEntry with new status.
        """
        root = self._tree.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item is None:
                continue
            stored_id = item.data(_COL_TIME, Qt.ItemDataRole.UserRole)
            if stored_id == entry.entry_id:
                source_label = self._source_label(entry)
                self._apply_row_visuals(item, entry, source_label)
                return

        logger.debug(f"update_entry: entry_id {entry.entry_id!r} not found in history tree")

    def clear(self) -> None:
        """Remove all history entries from the panel."""
        self._tree.clear()
