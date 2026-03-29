# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ParamInput — system-font text / number input for free-form parameters.

RViz2 style: dark input background (#2d2d2d), system sans-serif font (not
monospace — monospace is reserved for the YAML panel only).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QWidget


class ParamInput(QLineEdit):
    """Dark-themed QLineEdit for string and unconstrained numeric params.

    Emits ``value_changed`` on ``editingFinished`` (Enter / focus-out).

    Signals:
        value_changed(str): emitted when the user commits a new value.
    """

    value_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.editingFinished.connect(lambda: self.value_changed.emit(self.text()))

    def set_value(self, value) -> None:
        """Set the displayed text."""
        self.setText(str(value))

    def get_value(self) -> str:
        """Return the current text."""
        return self.text()
