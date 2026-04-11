# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ComparePanel — diff view between two parameter snapshots.

Shows a table of differences between a left and a right parameter source.
Each row can be checked individually; the "Apply Selected" button emits
the list of checked ParamDiffEntry objects so the caller can apply them
to the live node.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from nav2_config.core.config_diff import ParamDiffEntry, DiffKind

logger = logging.getLogger(__name__)

# ── Change kind background colors ─────────────────────────────────────────────
_BG_ADDED   = "#E8F5E9"   # light green
_BG_REMOVED = "#FFEBEE"   # light red
_BG_CHANGED = "#FFF3E0"   # light orange

# Panel header colors — RViz2 light theme
_BG_HDR = "#d0d0d0"
_BORDER  = "#c0c0c0"
_FG      = "#1a1a1a"
_FG_DIM  = "#666666"

# Fixed source options shown in the dropdowns
_SOURCE_OPTIONS = [
    "Live (current node)",
    "Loaded YAML (current)",
    "Loaded YAML (original)",
    "Browse YAML file...",
]

# Column indices
_COL_CHECK  = 0
_COL_NODE   = 1
_COL_PARAM  = 2
_COL_CHANGE = 3
_COL_LEFT   = 4
_COL_RIGHT  = 5

_COLUMNS = ["☐", "Node", "Param", "Change", "Left value", "Right value"]


class ComparePanel(QWidget):
    """Shows a diff between two parameter snapshots and lets the user apply changes.

    Signals:
        compare_requested(str, str): Emitted when Refresh is clicked.
            Arguments are the left source ID and right source ID.
        apply_selected_requested(list): Emitted when Apply Selected is clicked.
            Argument is the list of checked ParamDiffEntry objects.
    """

    compare_requested = pyqtSignal(str, str)           # left_source_id, right_source_id
    apply_selected_requested = pyqtSignal(list)         # list[ParamDiffEntry]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._diff_entries: list["ParamDiffEntry"] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())
        layout.addWidget(self._make_source_bar())
        layout.addWidget(self._make_table(), stretch=1)
        layout.addWidget(self._make_footer_bar())

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f"QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        title = QLabel("Compare Parameters")
        title.setStyleSheet(
            f"color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;"
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addStretch()
        return bar

    def _make_source_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"QWidget {{ background: #eeeeee; border-bottom: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._left_combo = QComboBox()
        self._left_combo.addItems(_SOURCE_OPTIONS)
        self._left_combo.setToolTip("Left (base) source for comparison")
        self._left_combo.currentIndexChanged.connect(
            lambda idx: self._on_source_changed(self._left_combo, idx)
        )
        layout.addWidget(self._left_combo, stretch=2)

        vs_label = QLabel("vs")
        vs_label.setStyleSheet(f"color: {_FG_DIM}; font-size: 9pt; background: transparent;")
        vs_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(vs_label)

        self._right_combo = QComboBox()
        self._right_combo.addItems(_SOURCE_OPTIONS)
        self._right_combo.setCurrentIndex(1)  # Default to "Loaded YAML (current)"
        self._right_combo.setToolTip("Right (target) source for comparison")
        self._right_combo.currentIndexChanged.connect(
            lambda idx: self._on_source_changed(self._right_combo, idx)
        )
        layout.addWidget(self._right_combo, stretch=2)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedHeight(24)
        refresh_btn.setToolTip("Run comparison between selected sources")
        refresh_btn.setStyleSheet("QPushButton { font-size: 9pt; padding: 0 10px; }")
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        layout.addWidget(refresh_btn)

        return bar

    def _make_table(self) -> QWidget:
        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(_COL_CHECK,  QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_NODE,   QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_PARAM,  QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_CHANGE, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_LEFT,   QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(_COL_RIGHT,  QHeaderView.ResizeMode.Interactive)

        self._table.setColumnWidth(_COL_NODE,  140)
        self._table.setColumnWidth(_COL_LEFT,  120)
        self._table.setColumnWidth(_COL_RIGHT, 120)

        return self._table

    def _make_footer_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(36)
        bar.setStyleSheet(
            f"QWidget {{ background: #eeeeee; border-top: 1px solid {_BORDER}; }}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._select_all_btn = QPushButton("Select All")
        self._select_all_btn.setFixedHeight(24)
        self._select_all_btn.setStyleSheet("QPushButton { font-size: 9pt; padding: 0 8px; }")
        self._select_all_btn.clicked.connect(self._on_select_all_clicked)
        layout.addWidget(self._select_all_btn)

        layout.addStretch()

        self._apply_btn = QPushButton("Apply Selected")
        self._apply_btn.setFixedHeight(24)
        self._apply_btn.setEnabled(False)
        self._apply_btn.setToolTip("Apply checked parameter changes to the live node")
        self._apply_btn.setStyleSheet(
            "QPushButton { background: #2a82da; color: #ffffff; "
            "border: 1px solid #1a6abf; font-size: 9pt; font-weight: bold; padding: 0 12px; }"
            "QPushButton:hover { background: #1e70c8; }"
            "QPushButton:pressed { background: #155d9e; }"
            "QPushButton:disabled { background: #e0e0e0; color: #999; border-color: #c0c0c0; }"
        )
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        layout.addWidget(self._apply_btn)

        return bar

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _change_bg(self, kind_name: str) -> str:
        """Return the background color for a given DiffKind name string."""
        name = kind_name.lower()
        if name == "added":
            return _BG_ADDED
        if name == "removed":
            return _BG_REMOVED
        return _BG_CHANGED

    def _update_apply_button(self) -> None:
        """Enable Apply Selected only when at least one checkbox is checked."""
        for row in range(self._table.rowCount()):
            cb_widget = self._table.cellWidget(row, _COL_CHECK)
            if isinstance(cb_widget, QCheckBox) and cb_widget.isChecked():
                self._apply_btn.setEnabled(True)
                return
        self._apply_btn.setEnabled(False)

    def _on_source_changed(self, combo: QComboBox, index: int) -> None:
        """Handle source dropdown change; open file dialog for Browse option."""
        if combo.itemText(index) == "Browse YAML file...":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Select YAML File",
                "",
                "YAML Files (*.yaml *.yml);;All Files (*)",
            )
            if path:
                filename = os.path.basename(path)
                # Replace the "Browse YAML file..." entry with the chosen filename
                combo.setItemText(index, filename)
                combo.setItemData(index, path, Qt.ItemDataRole.UserRole)
                combo.setToolTip(path)
            else:
                # User cancelled — revert to previous item
                combo.blockSignals(True)
                combo.setCurrentIndex(0)
                combo.blockSignals(False)

    def _on_refresh_clicked(self) -> None:
        """Emit compare_requested with the current source IDs."""
        left_id = self._left_combo.currentText()
        right_id = self._right_combo.currentText()
        self.compare_requested.emit(left_id, right_id)

    def _on_select_all_clicked(self) -> None:
        """Check all checkboxes in the table."""
        for row in range(self._table.rowCount()):
            cb_widget = self._table.cellWidget(row, _COL_CHECK)
            if isinstance(cb_widget, QCheckBox):
                cb_widget.setChecked(True)
        self._update_apply_button()

    def _on_apply_clicked(self) -> None:
        """Collect checked rows and emit apply_selected_requested."""
        selected: list["ParamDiffEntry"] = []
        for row in range(self._table.rowCount()):
            cb_widget = self._table.cellWidget(row, _COL_CHECK)
            if isinstance(cb_widget, QCheckBox) and cb_widget.isChecked():
                if row < len(self._diff_entries):
                    selected.append(self._diff_entries[row])
        if selected:
            self.apply_selected_requested.emit(selected)

    def _make_checkbox_widget(self, row: int) -> QWidget:
        """Return a centred QCheckBox widget for the checkbox column."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb = QCheckBox()
        cb.stateChanged.connect(lambda _: self._update_apply_button())
        layout.addWidget(cb)
        return container

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_diff(self, diff: list["ParamDiffEntry"]) -> None:
        """Populate the table from a list of ParamDiffEntry objects.

        Args:
            diff: Ordered list of diff entries to display.
        """
        self.clear()
        self._diff_entries = list(diff)
        self._table.setRowCount(len(diff))

        for row, entry in enumerate(diff):
            # Checkbox
            cb_widget = self._make_checkbox_widget(row)
            self._table.setCellWidget(row, _COL_CHECK, cb_widget)

            # Node column — show basename, full path as tooltip
            node_path = getattr(entry, "node_path", "") or ""
            node_display = node_path.rstrip("/").rsplit("/", 1)[-1] if node_path else "—"
            node_item = QTableWidgetItem(node_display)
            if node_path:
                node_item.setToolTip(node_path)
            node_item.setFlags(node_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_NODE, node_item)

            # Param column
            param_name = getattr(entry, "param_name", "") or "—"
            param_item = QTableWidgetItem(param_name)
            param_item.setFlags(param_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_PARAM, param_item)

            # Change column (DiffKind)
            try:
                kind_name = entry.kind.name.lower()
            except AttributeError:
                kind_name = str(getattr(entry, "kind", "changed")).lower()

            bg_color = self._change_bg(kind_name)
            change_item = QTableWidgetItem(kind_name)
            change_item.setBackground(Qt.GlobalColor.transparent)
            change_item.setFlags(change_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            from PyQt6.QtGui import QColor
            change_item.setBackground(QColor(bg_color))
            self._table.setItem(row, _COL_CHANGE, change_item)

            # Left value
            left_val = getattr(entry, "left_value", None)
            left_item = QTableWidgetItem("—" if left_val is None else str(left_val))
            left_item.setFlags(left_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_LEFT, left_item)

            # Right value
            right_val = getattr(entry, "right_value", None)
            right_item = QTableWidgetItem("—" if right_val is None else str(right_val))
            right_item.setFlags(right_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, _COL_RIGHT, right_item)

        self._update_apply_button()

    def clear(self) -> None:
        """Clear the diff table."""
        self._table.setRowCount(0)
        self._diff_entries = []
        self._apply_btn.setEnabled(False)
