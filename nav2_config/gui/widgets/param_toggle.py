"""ParamToggle — rectangular boolean toggle switch widget."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget


class _ToggleSwitch(QWidget):
    """Low-level rectangular toggle, painted manually for full style control."""

    toggled = pyqtSignal(bool)

    _W, _H = 36, 16  # Widget dimensions (px).

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checked = False
        self.setFixedSize(self._W, self._H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)  # flat / square

        # Background track
        bg = QColor('#4caf50' if self._checked else '#3e3e42')
        p.fillRect(self.rect(), bg)

        # Sliding handle — snaps to right when ON, left when OFF
        handle_x = self._W - 15 if self._checked else 1
        p.fillRect(handle_x, 1, 14, self._H - 2, QColor('#ffffff'))
        p.end()

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self._checked = not self._checked
        self.update()
        self.toggled.emit(self._checked)

    def set_checked(self, checked: bool) -> None:
        """Update state without emitting the signal."""
        self._checked = checked
        self.update()

    def is_checked(self) -> bool:
        return self._checked


class ParamToggle(QWidget):
    """Boolean parameter widget: rectangular toggle + ENABLED / DISABLED label.

    Signals:
        value_changed(bool): emitted when the toggle state changes.
    """

    value_changed = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._switch = _ToggleSwitch()
        layout.addWidget(self._switch)

        self._label = QLabel('DISABLED')
        self._label.setStyleSheet('font-size: 11px; color: #6d6d6d;')
        layout.addWidget(self._label)
        layout.addStretch()

        self._switch.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self._update_label(checked)
        self.value_changed.emit(checked)

    def _update_label(self, checked: bool) -> None:
        if checked:
            self._label.setText('ENABLED')
            self._label.setStyleSheet('font-size: 11px; color: #4caf50;')
        else:
            self._label.setText('DISABLED')
            self._label.setStyleSheet('font-size: 11px; color: #6d6d6d;')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: bool) -> None:
        """Update displayed state without emitting value_changed."""
        self._switch.set_checked(bool(value))
        self._update_label(bool(value))

    def get_value(self) -> bool:
        """Return the current toggle state."""
        return self._switch.is_checked()
