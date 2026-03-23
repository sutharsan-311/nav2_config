"""ParamSelect — dropdown for enum parameters."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget


class ParamSelect(QComboBox):
    """Styled QComboBox populated from a parameter schema's ``range.options``.

    Signals:
        value_changed(str): emitted when the selected option changes.
    """

    value_changed = pyqtSignal(str)

    def __init__(
        self,
        options: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        for option in options:
            self.addItem(option)
        self.currentTextChanged.connect(self.value_changed.emit)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: str) -> None:
        """Select the entry matching *value* (no-op if not found)."""
        idx = self.findText(str(value))
        if idx >= 0:
            self.setCurrentIndex(idx)

    def get_value(self) -> str:
        """Return the currently selected option string."""
        return self.currentText()
