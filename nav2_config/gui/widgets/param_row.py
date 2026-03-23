"""ParamRow — single parameter row: label + input widget + tuning advice."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nav2_config.types.params import ParamValue
from nav2_config.gui.widgets.param_input import ParamInput
from nav2_config.gui.widgets.param_select import ParamSelect
from nav2_config.gui.widgets.param_slider import ParamSlider
from nav2_config.gui.widgets.param_toggle import ParamToggle


class ParamRow(QWidget):
    """Two-column row displaying one parameter with its label and input widget.

    Left column: parameter name (monospace blue), optional modified dot,
                 optional restart-required badge, description in muted gray.
    Right column: appropriate input widget chosen from the schema type.
    Below:        collapsible "Tuning advice" section (impact text).

    Signals:
        param_changed(str, Any): ``(param_name, new_value)`` emitted whenever
            the user changes the parameter value.
    """

    param_changed = pyqtSignal(str, object)

    def __init__(
        self,
        param_value: ParamValue,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._param_value = param_value
        self._input_widget: ParamSlider | ParamToggle | ParamSelect | ParamInput | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 4)
        outer.setSpacing(2)

        outer.addLayout(self._build_main_row())

        if self._param_value.definition.impact:
            self._build_tuning_advice(outer)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #2d2d2d;')
        outer.addWidget(sep)

    def _build_main_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addLayout(self._build_label_column(), stretch=3)
        row.addLayout(self._build_input_column(), stretch=2)
        return row

    def _build_label_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)

        # Name row: modified dot + param name + hot-reload badge
        name_row = QHBoxLayout()
        name_row.setSpacing(4)
        name_row.setContentsMargins(0, 0, 0, 0)

        self._modified_dot = QLabel('●')
        self._modified_dot.setStyleSheet('color: #f57c00; font-size: 8px;')
        self._modified_dot.setFixedWidth(10)
        self._modified_dot.setVisible(self._param_value.is_modified)
        name_row.addWidget(self._modified_dot)

        name_label = QLabel(self._param_value.definition.param)
        name_label.setStyleSheet(
            'color: #4fc3f7; '
            'font-family: "Consolas", "JetBrains Mono", "Courier New", monospace; '
            'font-size: 12px;'
        )
        name_row.addWidget(name_label)

        if not self._param_value.definition.hot_reload:
            badge = QLabel('↻ restart')
            badge.setStyleSheet(
                'color: #f57c00; font-size: 10px; '
                'background: #2d1a00; padding: 1px 4px;'
            )
            name_row.addWidget(badge)

        name_row.addStretch()
        col.addLayout(name_row)

        desc = QLabel(self._param_value.definition.description)
        desc.setStyleSheet('color: #6d6d6d; font-size: 11px;')
        desc.setWordWrap(True)
        col.addWidget(desc)

        return col

    def _build_input_column(self) -> QVBoxLayout:
        col = QVBoxLayout()
        col.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        col.setContentsMargins(0, 0, 0, 0)

        self._input_widget = self._make_input_widget()
        col.addWidget(self._input_widget)

        return col

    def _make_input_widget(
        self,
    ) -> ParamSlider | ParamToggle | ParamSelect | ParamInput:
        """Instantiate the appropriate input widget from the param schema."""
        defn = self._param_value.definition
        val = self._param_value.current_value

        # Boolean → toggle switch
        if defn.type == 'bool':
            w = ParamToggle()
            w.set_value(bool(val))
            w.value_changed.connect(self._on_value_changed)
            return w

        # Enum → dropdown
        if defn.range and defn.range.options:
            w = ParamSelect(defn.range.options)
            w.set_value(str(val))
            w.value_changed.connect(self._on_value_changed)
            return w

        # Numeric with range → slider
        if (
            defn.type in ('double', 'int')
            and defn.range
            and defn.range.min is not None
            and defn.range.max is not None
        ):
            w = ParamSlider(
                defn.range.min,
                defn.range.max,
                is_int=(defn.type == 'int'),
                unit=defn.unit,
            )
            try:
                w.set_value(float(val))
            except (TypeError, ValueError):
                pass
            w.value_changed.connect(self._on_value_changed)
            return w

        # Fallback → free-text input
        w = ParamInput()
        w.set_value(str(val) if val is not None else '')
        w.value_changed.connect(self._on_value_changed)
        return w

    def _build_tuning_advice(self, outer: QVBoxLayout) -> None:
        """Add a collapsible 'Tuning advice' section below the main row."""
        self._advice_visible = False

        btn = QPushButton('▶  Tuning advice')
        btn.setStyleSheet(
            'QPushButton { '
            '    color: #555558; font-size: 10px; text-align: left; '
            '    background: transparent; border: none; padding: 0 0 0 0; '
            '}'
            'QPushButton:hover { color: #9d9d9d; }'
        )
        outer.addWidget(btn)

        self._advice_label = QLabel(self._param_value.definition.impact)
        self._advice_label.setStyleSheet(
            'color: #9d9d9d; font-size: 11px; padding-left: 14px;'
        )
        self._advice_label.setWordWrap(True)
        self._advice_label.setVisible(False)
        outer.addWidget(self._advice_label)

        self._advice_btn = btn

        def _toggle() -> None:
            self._advice_visible = not self._advice_visible
            self._advice_label.setVisible(self._advice_visible)
            self._advice_btn.setText(
                '▼  Tuning advice' if self._advice_visible else '▶  Tuning advice'
            )

        btn.clicked.connect(_toggle)

    # ------------------------------------------------------------------
    # Private: change handler
    # ------------------------------------------------------------------

    def _on_value_changed(self, value: Any) -> None:
        self._param_value.update(value)
        self._modified_dot.setVisible(self._param_value.is_modified)
        self.param_changed.emit(self._param_value.definition.param, value)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_value(self, value: Any) -> None:
        """Update the display from an external source (e.g., live param poll).

        Does NOT emit param_changed — external updates should not trigger
        a ROS2 set_parameters call.
        """
        self._param_value.update(value)
        self._modified_dot.setVisible(self._param_value.is_modified)
        if self._input_widget is None:
            return
        if isinstance(self._input_widget, ParamToggle):
            self._input_widget.set_value(bool(value))
        elif isinstance(self._input_widget, ParamSlider):
            try:
                self._input_widget.set_value(float(value))
            except (TypeError, ValueError):
                pass
        else:
            self._input_widget.set_value(str(value) if value is not None else '')

    def matches_search(self, query: str) -> bool:
        """Return True if this row should be visible for the given search query."""
        if not query:
            return True
        q = query.lower()
        defn = self._param_value.definition
        return (
            q in defn.param.lower()
            or q in defn.description.lower()
            or q in defn.category.lower()
            or any(q in tag.lower() for tag in defn.tags)
        )
