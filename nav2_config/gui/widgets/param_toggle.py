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
        self._checkbox.stateChanged.connect(
            lambda state: self.value_changed.emit(bool(state))
        )
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
