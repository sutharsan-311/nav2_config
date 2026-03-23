"""ParamInput — monospace text / number input for free-form parameters."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLineEdit, QWidget


class ParamInput(QLineEdit):
    """Dark-themed monospace QLineEdit for string and unconstrained params.

    Emits ``value_changed`` on ``editingFinished`` (Enter / focus-out) rather
    than on every keystroke, so that ROS2 service calls are not spammed.

    Signals:
        value_changed(str): emitted when the user commits a new value.
    """

    value_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            'font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;'
        )
        self.editingFinished.connect(lambda: self.value_changed.emit(self.text()))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value) -> None:
        """Set the displayed text."""
        self.setText(str(value))

    def get_value(self) -> str:
        """Return the current text."""
        return self.text()
