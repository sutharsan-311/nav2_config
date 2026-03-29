# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""LoadConfigDialog -- shown on startup or via File > Load Config.

Lets the user select their nav2_params.yaml file.  Remembers the last
five files opened and suggests common default locations automatically.
"""

from __future__ import annotations

import glob
import logging
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Common locations to probe for a default nav2_params.yaml
_CANDIDATE_PATTERNS: list[str] = [
    str(Path.home() / 'nav2_params.yaml'),
    str(Path.home() / 'ros2_ws/src/*/params/nav2_params.yaml'),
    str(Path.home() / 'ros2_ws/src/*/config/nav2_params.yaml'),
    '/opt/ros/humble/share/nav2_bringup/params/nav2_params.yaml',
    '/opt/ros/iron/share/nav2_bringup/params/nav2_params.yaml',
    '/opt/ros/jazzy/share/nav2_bringup/params/nav2_params.yaml',
]


def _find_default_path() -> str:
    """Return the first nav2_params.yaml found in common locations, or ''."""
    for pattern in _CANDIDATE_PATTERNS:
        if '*' in pattern:
            matches = glob.glob(pattern)
            if matches:
                return matches[0]
        elif Path(pattern).exists():
            return pattern
    return ''


class LoadConfigDialog(QDialog):
    """Dialog for selecting the nav2_params.yaml to load.

    Shows a file path entry, a Browse button, a recent-files list, and a
    checkbox for whether to also connect to running Nav2 nodes.

    After exec() returns Accepted, read:
      - selected_filepath(): the chosen YAML path (may be '').
      - connect_to_nodes(): whether the node-connect checkbox is set.
    """

    def __init__(
        self,
        recent_files: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._filepath = ''
        self._recent_files: list[str] = recent_files or []
        self._build_ui()
        self._populate_default()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle('Load Nav2 Configuration')
        self.setMinimumWidth(560)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        title = QLabel('Load Nav2 Configuration')
        title.setStyleSheet('font-size: 12pt; font-weight: bold;')
        layout.addWidget(title)

        subtitle = QLabel(
            'Select your nav2_params.yaml file.\n'
            'This file is the source of truth -- changes are saved back to it.'
        )
        subtitle.setStyleSheet('color: #555; font-size: 9pt;')
        layout.addWidget(subtitle)

        # File path row
        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText('Path to nav2_params.yaml...')
        self._path_edit.setStyleSheet('font-size: 9pt;')
        path_row.addWidget(self._path_edit, stretch=1)

        browse_btn = QPushButton('Browse...')
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        # Recent files
        if self._recent_files:
            recent_label = QLabel('Recent files:')
            recent_label.setStyleSheet('color: #555; font-size: 9pt;')
            layout.addWidget(recent_label)

            self._recent_list = QListWidget()
            self._recent_list.setMaximumHeight(100)
            self._recent_list.setStyleSheet('font-size: 9pt;')
            for fp in self._recent_files:
                self._recent_list.addItem(QListWidgetItem(fp))
            self._recent_list.itemClicked.connect(
                lambda item: self._path_edit.setText(item.text())
            )
            self._recent_list.itemDoubleClicked.connect(self._on_recent_double_click)
            layout.addWidget(self._recent_list)

        # Connect checkbox
        self._connect_cb = QCheckBox('Connect to running Nav2 nodes (recommended)')
        self._connect_cb.setChecked(True)
        layout.addWidget(self._connect_cb)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open
            | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Open).setText('Load')
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _populate_default(self) -> None:
        if self._recent_files:
            self._path_edit.setText(self._recent_files[0])
        else:
            default = _find_default_path()
            if default:
                self._path_edit.setText(default)

    def _browse(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            'Select Nav2 Parameters File',
            str(Path.home()),
            'YAML Files (*.yaml *.yml);;All Files (*)',
        )
        if filepath:
            self._path_edit.setText(filepath)

    def _on_recent_double_click(self, item: QListWidgetItem) -> None:
        self._path_edit.setText(item.text())
        self._on_accept()

    def _on_accept(self) -> None:
        self._filepath = self._path_edit.text().strip()
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def selected_filepath(self) -> str:
        """Return the chosen file path, or '' if cancelled / left blank."""
        return self._filepath

    def connect_to_nodes(self) -> bool:
        """Return True if 'Connect to running Nav2 nodes' is checked."""
        return self._connect_cb.isChecked()
