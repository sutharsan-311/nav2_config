"""ParamSlider — synced QSlider + spinbox with unit label."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QWidget,
)


class ParamSlider(QWidget):
    """Horizontal slider paired with a spinbox, kept in sync.

    For ``double`` params the slider is quantised into 100 steps over
    ``[min, max]``; for ``int`` params each slider tick is one integer unit.
    A unit label is shown on the right when provided.

    Signals:
        value_changed(float): emitted when the value changes (from either
            the slider or the spinbox).
    """

    value_changed = pyqtSignal(float)

    _STEPS = 100  # Number of discrete positions for double sliders.

    def __init__(
        self,
        min_val: float,
        max_val: float,
        is_int: bool = False,
        unit: str = '',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min = float(min_val)
        self._max = float(max_val)
        self._is_int = is_int
        self._updating = False  # Re-entrancy guard for bidirectional sync.
        self._build_ui(unit)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self, unit: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(0)
        if self._is_int:
            self._slider.setMaximum(max(0, int(self._max - self._min)))
        else:
            self._slider.setMaximum(self._STEPS)
        self._slider.setFixedWidth(110)
        self._slider.setStyleSheet(
            'QSlider::groove:horizontal { background: #3e3e42; height: 3px; }'
            'QSlider::handle:horizontal { background: #4fc3f7; width: 10px; '
            '                            height: 10px; margin: -4px 0; }'
            'QSlider::handle:horizontal:hover { background: #f57c00; }'
            'QSlider::sub-page:horizontal { background: #f57c00; }'
        )
        layout.addWidget(self._slider)

        if self._is_int:
            self._spinbox: QSpinBox | QDoubleSpinBox = QSpinBox()
            self._spinbox.setMinimum(int(self._min))
            self._spinbox.setMaximum(int(self._max))
        else:
            self._spinbox = QDoubleSpinBox()
            self._spinbox.setMinimum(self._min)
            self._spinbox.setMaximum(self._max)
            step = (self._max - self._min) / self._STEPS if self._max != self._min else 0.01
            self._spinbox.setSingleStep(step)
            self._spinbox.setDecimals(4)

        self._spinbox.setFixedWidth(82)
        layout.addWidget(self._spinbox)

        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet('color: #6d6d6d; font-size: 11px;')
            unit_label.setFixedWidth(36)
            layout.addWidget(unit_label)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)

    # ------------------------------------------------------------------
    # Private: value ↔ slider-position conversion
    # ------------------------------------------------------------------

    def _pos_to_value(self, pos: int) -> float:
        if self._is_int:
            return self._min + pos
        if self._max == self._min:
            return self._min
        return self._min + (pos / self._STEPS) * (self._max - self._min)

    def _value_to_pos(self, value: float) -> int:
        if self._is_int:
            return int(value - self._min)
        if self._max == self._min:
            return 0
        return round((value - self._min) / (self._max - self._min) * self._STEPS)

    # ------------------------------------------------------------------
    # Private: change handlers
    # ------------------------------------------------------------------

    def _on_slider_changed(self, pos: int) -> None:
        if self._updating:
            return
        self._updating = True
        value = self._pos_to_value(pos)
        self._spinbox.setValue(value)
        self._updating = False
        self.value_changed.emit(float(value))

    def _on_spinbox_changed(self, value: float | int) -> None:
        if self._updating:
            return
        self._updating = True
        self._slider.setValue(self._value_to_pos(float(value)))
        self._updating = False
        self.value_changed.emit(float(value))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: float) -> None:
        """Set the displayed value without emitting value_changed."""
        self._updating = True
        self._spinbox.setValue(value)
        self._slider.setValue(self._value_to_pos(float(value)))
        self._updating = False

    def get_value(self) -> float:
        """Return the current value."""
        return float(self._spinbox.value())
