# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ParamRow — single parameter row styled exactly like RViz2's property editor.

Two columns: name (40%) | widget (60%).
- Name: regular weight, dark system font (NOT monospace).
- Modified: blue dot (#3399ff) and blue name text.
- Description: 8pt #666666, collapsible via parent panel's Desc toggle.
- Alternating row backgrounds: #ffffff / #f5f5f5.
- Row height: 24px without description, taller with description visible.

Each row has a per-parameter Set button at the right edge with a 5-state
machine: IDLE → READY → PENDING → SUCCESS / FAILED.
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Any

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
from nav2_config.gui.widgets.param_topic_select import ParamFrameSelect, ParamTopicSelect

if TYPE_CHECKING:
    from nav2_config.core.topic_discovery import TopicDiscovery
    from nav2_config.core.frame_discovery import FrameDiscovery

# Alternating row background colors matching RViz2 light theme
_ROW_BG   = ('#ffffff', '#f5f5f5')
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'
_BLUE     = '#3399ff'   # Modified indicator / selection
_AMBER    = '#ff9800'   # Warning


def _is_frame_param(param_name: str) -> bool:
    """Return True if *param_name* should use a TF frame selector."""
    lower = param_name.lower()
    return lower.endswith('_frame') or lower.endswith('_frame_id')


def _is_topic_param(param_name: str) -> bool:
    """Return True if *param_name* should use a topic selector."""
    return 'topic' in param_name.lower()


# ---------------------------------------------------------------------------
# SetButton state machine
# ---------------------------------------------------------------------------

class _SetState(Enum):
    IDLE       = auto()   # Value matches live — button disabled, grayed
    READY      = auto()   # User changed value — button enabled, blue
    PENDING    = auto()   # Waiting for ROS2 response — button shows "..."
    SUCCESS    = auto()   # Set succeeded — shows green checkmark
    FAILED     = auto()   # Set failed — shows red X, clickable to retry
    SAVED_FILE = auto()   # Non-hot-reload: saved to file, restart needed — amber


_STATE_CFG: dict[_SetState, tuple[str, str, bool]] = {
    # state → (stylesheet, label, enabled)
    _SetState.IDLE: (
        'QPushButton {'
        '    background: #e0e0e0; color: #999999;'
        '    border: 1px solid #c0c0c0; font-size: 8pt; padding: 0;'
        '}',
        'Set', False,
    ),
    _SetState.READY: (
        'QPushButton {'
        '    background: #2a82da; color: #ffffff;'
        '    border: 1px solid #1a6abf; font-size: 8pt;'
        '    font-weight: bold; padding: 0;'
        '}'
        'QPushButton:hover { background: #1e70c8; }',
        'Set', True,
    ),
    _SetState.PENDING: (
        'QPushButton {'
        '    background: #e0e0e0; color: #666666;'
        '    border: 1px solid #c0c0c0; font-size: 8pt; padding: 0;'
        '}',
        '...', False,
    ),
    _SetState.SUCCESS: (
        'QPushButton {'
        '    background: #e8f5e9; color: #4caf50;'
        '    border: none; font-size: 11pt; padding: 0;'
        '}',
        '\u2713', False,
    ),
    _SetState.FAILED: (
        'QPushButton {'
        '    background: #ffebee; color: #e53935;'
        '    border: 1px solid #ef9a9a; font-size: 11pt; padding: 0;'
        '}'
        'QPushButton:hover { background: #ffcdd2; }',
        '\u2717', True,
    ),
    _SetState.SAVED_FILE: (
        'QPushButton {'
        '    background: #fff3e0; color: #f57c00;'
        '    border: 1px solid #ffb74d; font-size: 10pt; padding: 0;'
        '}',
        '\u21bb', False,
    ),
}


class _SetButton(QPushButton):
    """Compact per-parameter Set button with 5 display states."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = _SetState.IDLE
        self.setFixedWidth(38)
        self.setFixedHeight(18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply(_SetState.IDLE)

    @property
    def state(self) -> _SetState:
        return self._state

    def set_state(self, state: _SetState) -> None:
        """Transition to *state* and update appearance."""
        if self._state == state:
            return
        self._state = state
        self._apply(state)

    def _apply(self, state: _SetState) -> None:
        style, text, enabled = _STATE_CFG[state]
        self.setStyleSheet(style)
        self.setText(text)
        self.setEnabled(enabled)
        if state == _SetState.FAILED:
            self.setToolTip('Failed to set parameter — click to retry')
        elif state == _SetState.SAVED_FILE:
            self.setToolTip('Saved to config file — restart Nav2 to apply')
        else:
            self.setToolTip('')


# ---------------------------------------------------------------------------
# ParamRow
# ---------------------------------------------------------------------------

class ParamRow(QWidget):
    """Two-column property row for one Nav2 parameter.

    Left 40%: name + optional modified dot + optional restart badge.
    Right 60%: inline input widget (slider / toggle / combobox / text)
               + Set button at the far right.

    Signals:
        param_changed(str, Any):
            ``(param_name, new_value)`` — emitted on every GUI value change,
            used to keep the YAML preview in sync.  Does NOT trigger a ROS2
            ``set_parameters`` call.
        param_set_requested(str, Any):
            ``(param_name, value)`` — emitted when the user explicitly clicks
            the Set button (or via :meth:`trigger_set`).  The parent panel
            routes this to the ROS2 node.
    """

    param_changed      = pyqtSignal(str, object)
    param_set_requested = pyqtSignal(str, object)

    def __init__(
        self,
        param_value: ParamValue,
        show_description: bool = True,
        topic_discovery: 'TopicDiscovery | None' = None,
        frame_discovery: 'FrameDiscovery | None' = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._param_value = param_value
        self._input_widget: (
            ParamSlider | ParamToggle | ParamSelect
            | ParamInput | ParamTopicSelect | ParamFrameSelect | None
        ) = None
        self._set_btn: _SetButton
        self._sent_value: Any = None   # Value in flight (between Set click and result)
        self._show_description = show_description
        self._topic_discovery = topic_discovery
        self._frame_discovery = frame_discovery
        self._row_index: int = 0
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Main two-column row
        main_row = QWidget()
        main_row.setFixedHeight(24)
        row_layout = QHBoxLayout(main_row)
        row_layout.setContentsMargins(4, 0, 4, 0)
        row_layout.setSpacing(0)

        # Left: name column (40%)
        name_widget = QWidget()
        name_layout = QHBoxLayout(name_widget)
        name_layout.setContentsMargins(4, 0, 4, 0)
        name_layout.setSpacing(4)

        self._modified_dot = QLabel('\u25cf')
        self._modified_dot.setFixedWidth(8)
        self._modified_dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._modified_dot.setStyleSheet(f'color: {_BLUE}; font-size: 7px;')
        self._modified_dot.setVisible(self._param_value.is_modified)
        name_layout.addWidget(self._modified_dot)

        # Amber dot: visible when file value differs from live (confirmed) value
        self._file_dot = QLabel('\u25cf')
        self._file_dot.setFixedWidth(8)
        self._file_dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._file_dot.setStyleSheet(f'color: {_AMBER}; font-size: 7px;')
        self._file_dot.setVisible(False)
        name_layout.addWidget(self._file_dot)

        self._name_label = QLabel(self._param_value.definition.param)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._name_label.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: normal; '
            f'background: transparent;'
        )
        name_layout.addWidget(self._name_label, stretch=1)

        if not self._param_value.definition.hot_reload:
            badge = QLabel('↻')
            badge.setToolTip('Requires node restart')
            badge.setStyleSheet(
                f'color: {_AMBER}; font-size: 8px; background: transparent;'
            )
            badge.setFixedWidth(12)
            name_layout.addWidget(badge)

        row_layout.addWidget(name_widget, stretch=40)

        # Thin column separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet('color: #e0e0e0;')
        sep.setFixedWidth(1)
        row_layout.addWidget(sep)

        # Right: input column (60%) — input widget | stretch | Set button
        input_widget = QWidget()
        input_layout = QHBoxLayout(input_widget)
        input_layout.setContentsMargins(4, 0, 2, 0)
        input_layout.setSpacing(4)

        self._input_widget = self._make_input_widget()
        input_layout.addWidget(self._input_widget)
        input_layout.addStretch()

        self._set_btn = _SetButton()
        self._set_btn.clicked.connect(self._on_set_clicked)
        input_layout.addWidget(self._set_btn)

        row_layout.addWidget(input_widget, stretch=60)
        outer.addWidget(main_row)

        # Description line (below the main row, smaller text)
        self._desc_label = QLabel(self._param_value.definition.description)
        self._desc_label.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 8pt; '
            f'padding: 0 8px 3px 20px; background: transparent;'
        )
        self._desc_label.setWordWrap(True)
        self._desc_label.setVisible(self._show_description)
        outer.addWidget(self._desc_label)

        # Bottom separator line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet('color: #e0e0e0; background: #e0e0e0;')
        line.setFixedHeight(1)
        outer.addWidget(line)

        self._apply_row_bg()
        self._update_name_style()
        self._refresh_file_dot()

    def _make_input_widget(
        self,
    ) -> ParamSlider | ParamToggle | ParamSelect | ParamInput | ParamTopicSelect | ParamFrameSelect:
        """Instantiate the appropriate input widget from the param schema."""
        defn = self._param_value.definition
        val = self._param_value.current_value
        current_str = str(val) if val is not None else ''

        if defn.type == 'bool':
            w = ParamToggle()
            w.set_value(bool(val))
            w.value_changed.connect(self._on_value_changed)
            return w

        if defn.range and defn.range.options:
            w = ParamSelect(defn.range.options)
            w.set_value(current_str)
            w.value_changed.connect(self._on_value_changed)
            return w

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

        # TF frame selector — for any param whose name ends with _frame / _frame_id
        if defn.type == 'string' and self._frame_discovery and _is_frame_param(defn.param):
            w = ParamFrameSelect(self._frame_discovery, current_value=current_str)
            w.value_changed.connect(self._on_value_changed)
            return w

        # Topic selector — for any string param whose name contains "topic"
        if defn.type == 'string' and self._topic_discovery and _is_topic_param(defn.param):
            w = ParamTopicSelect(
                self._topic_discovery, param_name=defn.param, current_value=current_str
            )
            w.value_changed.connect(self._on_value_changed)
            return w

        w = ParamInput()
        w.set_value(current_str)
        w.value_changed.connect(self._on_value_changed)
        return w

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_row_bg(self) -> None:
        """Set alternating background color based on row index."""
        bg = _ROW_BG[self._row_index % 2]
        self.setStyleSheet(f'QWidget {{ background: {bg}; }}')

    def _update_name_style(self) -> None:
        """Blue name text when modified, default otherwise."""
        if self._param_value.is_modified:
            self._name_label.setStyleSheet(
                f'color: {_BLUE}; font-size: 10pt; font-weight: normal; '
                f'background: transparent;'
            )
        else:
            self._name_label.setStyleSheet(
                f'color: {_FG}; font-size: 10pt; font-weight: normal; '
                f'background: transparent;'
            )

    def _refresh_file_dot(self) -> None:
        """Show/hide/update the amber file-vs-live dot for the current file_value."""
        fv = self._param_value.file_value
        if fv is None:
            self._file_dot.setVisible(False)
            return
        live = self._param_value.confirmed_value
        differs = fv != live
        self._file_dot.setVisible(differs)
        if differs:
            self._file_dot.setToolTip(
                f'File: {fv} | Live: {live} -- values differ'
            )
        else:
            self._file_dot.setToolTip('')

    def _sync_set_button(self) -> None:
        """Update Set button state based on current vs confirmed value.

        Never overrides PENDING or SAVED_FILE states.
        """
        if self._set_btn.state in (_SetState.PENDING, _SetState.SAVED_FILE):
            return
        if self._param_value.is_pending:
            self._set_btn.set_state(_SetState.READY)
        else:
            self._set_btn.set_state(_SetState.IDLE)

    # ------------------------------------------------------------------
    # Private: change / set handlers
    # ------------------------------------------------------------------

    def _on_value_changed(self, value: Any) -> None:
        """Called by the input widget whenever the user changes the displayed value.

        Updates the ParamValue's pending/current value, refreshes the modified
        dot and name style, emits ``param_changed`` for the YAML panel, and
        updates the Set button state.
        """
        self._param_value.update(value)
        self._modified_dot.setVisible(self._param_value.is_modified)
        self._update_name_style()
        self.param_changed.emit(self._param_value.definition.param, value)
        # If the row was in SAVED_FILE state (non-hot-reload saved to file), allow
        # the user to re-edit — clear that state so _sync_set_button() can proceed.
        if self._set_btn.state == _SetState.SAVED_FILE:
            self._set_btn.set_state(_SetState.IDLE)
        self._sync_set_button()

    def _on_set_clicked(self) -> None:
        """Handle Set button click (also used as retry for FAILED state)."""
        if self._set_btn.state in (_SetState.READY, _SetState.FAILED):
            self.trigger_set()

    # ------------------------------------------------------------------
    # Public API — called by parent panel
    # ------------------------------------------------------------------

    def trigger_set(self) -> None:
        """Record the pending value, go PENDING, and emit param_set_requested.

        Safe to call externally (e.g. from "Set All Modified" action).
        Only acts when button is in READY or FAILED state.
        """
        if self._set_btn.state not in (_SetState.READY, _SetState.FAILED):
            return
        self._sent_value = self._param_value.current_value
        self._set_btn.set_state(_SetState.PENDING)
        self.param_set_requested.emit(
            self._param_value.definition.param, self._sent_value
        )

    def receive_set_result(self, success: bool) -> None:
        """Called by the parent panel when the ROS2 set_parameters call completes.

        On success: records the confirmed value and transitions to SUCCESS (or
        back to READY if the user changed the value during the pending period).
        On failure: transitions to FAILED so the user can retry.
        """
        if success:
            self._param_value.confirm(self._sent_value)
            self._modified_dot.setVisible(self._param_value.is_modified)
            self._update_name_style()
            self._refresh_file_dot()
            if self._param_value.is_pending:
                self._set_btn.set_state(_SetState.READY)
            else:
                self._set_btn.set_state(_SetState.SUCCESS)
        else:
            self._set_btn.set_state(_SetState.FAILED)

    def is_ready_to_set(self) -> bool:
        """Return True if this row has a pending change that can be sent now."""
        return self._set_btn.state in (_SetState.READY, _SetState.FAILED)

    def set_row_index(self, index: int) -> None:
        """Set the row's position index for alternating backgrounds."""
        self._row_index = index
        self._apply_row_bg()

    def restore_row_bg(self) -> None:
        """Restore the alternating background after a flash effect."""
        self._apply_row_bg()

    def receive_file_save_result(self) -> None:
        """Mark this row as saved to the config file (non-hot-reload param).

        Transitions the Set button to the amber SAVED_FILE state to indicate
        the value is queued for the next Nav2 restart.  The confirmed_value is
        updated to match current_value so is_pending becomes False.
        """
        self._sent_value = self._param_value.current_value
        self._param_value.confirm(self._sent_value)
        self._modified_dot.setVisible(self._param_value.is_modified)
        self._update_name_style()
        self._set_btn.set_state(_SetState.SAVED_FILE)

    def update_file_value(self, file_value: Any) -> None:
        """Update the file-vs-live indicator based on *file_value*.

        Shows the amber dot when *file_value* differs from the confirmed live
        value, with a tooltip explaining both values.

        Args:
            file_value: The value currently in the nav2_params.yaml file,
                or ``None`` if the param is absent from the file.
        """
        self._param_value.file_value = file_value
        self._refresh_file_dot()

    def set_description_visible(self, visible: bool) -> None:
        """Show or hide the description text line."""
        self._show_description = visible
        self._desc_label.setVisible(visible)

    def set_value(self, value: Any) -> None:
        """Update the display from an external source (e.g. watcher-detected change).

        Confirms the new value immediately (it came from the live robot) and
        resets the Set button to IDLE.
        """
        self._param_value.update(value)
        self._param_value.confirm(value)
        self._modified_dot.setVisible(self._param_value.is_modified)
        self._update_name_style()
        self._refresh_file_dot()
        self._set_btn.set_state(_SetState.IDLE)
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

    def refresh_discovery_widget(self) -> None:
        """Refresh topic or frame dropdown if this row uses one."""
        if isinstance(self._input_widget, ParamTopicSelect):
            self._input_widget.refresh_topics()
        elif isinstance(self._input_widget, ParamFrameSelect):
            self._input_widget.refresh_frames()

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
