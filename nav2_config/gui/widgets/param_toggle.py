# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ParamToggle — standard QCheckBox wrapper for boolean parameters.

RViz2 light style: uses Qt's native Fusion checkbox — no custom painting.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QWidget


class ParamToggle(QWidget):
    """Boolean parameter widget: standard QCheckBox with true/false label.

    Signals:
        value_changed(bool): emitted when the checkbox state changes.
    """

    value_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._checkbox = QCheckBox()
        # Use toggled(bool) rather than stateChanged(Qt.CheckState) — in PyQt6
        # versions < 6.4, Qt.CheckState is not an IntEnum, so bool(Unchecked)
        # is True (it's a non-None object), which breaks the IDLE→READY state
        # machine when the user unchecks a True-default parameter.
        self._checkbox.toggled.connect(self.value_changed)
        layout.addWidget(self._checkbox)
        layout.addStretch()

    def set_value(self, value: bool) -> None:
        """Update displayed state without emitting value_changed."""
        self._checkbox.blockSignals(True)
        self._checkbox.setChecked(bool(value))
        self._checkbox.blockSignals(False)

    def get_value(self) -> bool:
        """Return the current checkbox state."""
        return self._checkbox.isChecked()
