# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ParamSlider — synced QSlider + spinbox with unit label.

RViz2 light style: light groove (#e0e0e0), gray handle (#888888), blue
filled track (#3399ff). Spinbox uses system font at 9pt.
"""

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

_GROOVE  = '#d8d8d8'
_HANDLE  = '#888888'
_CHUNK   = '#3399ff'
_BORDER  = '#c0c0c0'
_FG_DIM  = '#666666'
_FG      = '#1a1a1a'
_INPUT   = '#ffffff'


class ParamSlider(QWidget):
    """Horizontal slider paired with a spinbox, kept in sync.

    Signals:
        value_changed(float): emitted when value changes.
    """

    value_changed = pyqtSignal(float)

    _STEPS = 100

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
        self._updating = False
        self._build_ui(unit)

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
        self._slider.setFixedWidth(100)
        self._slider.setStyleSheet(
            f'QSlider::groove:horizontal {{'
            f'    background: {_GROOVE}; height: 4px; '
            f'    border: 1px solid {_BORDER}; border-radius: 0; '
            f'}}'
            f'QSlider::handle:horizontal {{'
            f'    background: {_HANDLE}; width: 10px; height: 10px; '
            f'    margin: -4px 0; border-radius: 1px; '
            f'}}'
            f'QSlider::handle:horizontal:hover {{'
            f'    background: {_FG}; '
            f'}}'
            f'QSlider::sub-page:horizontal {{'
            f'    background: {_CHUNK}; height: 4px; '
            f'}}'
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
            step = (
                (self._max - self._min) / self._STEPS
                if self._max != self._min
                else 0.01
            )
            self._spinbox.setSingleStep(step)
            self._spinbox.setDecimals(4)

        self._spinbox.setFixedWidth(78)
        layout.addWidget(self._spinbox)

        if unit:
            unit_label = QLabel(unit)
            unit_label.setStyleSheet(
                f'color: {_FG_DIM}; font-size: 9pt; background: transparent;'
            )
            unit_label.setFixedWidth(32)
            layout.addWidget(unit_label)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._spinbox.valueChanged.connect(self._on_spinbox_changed)

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

    def set_value(self, value: float) -> None:
        """Set the displayed value without emitting value_changed."""
        self._updating = True
        self._spinbox.setValue(value)
        self._slider.setValue(self._value_to_pos(float(value)))
        self._updating = False

    def get_value(self) -> float:
        """Return the current value."""
        return float(self._spinbox.value())
