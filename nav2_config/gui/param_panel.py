# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ParamPanel — center panel: scrollable, searchable parameter editor.

Styled to match RViz2's Properties panel: two-column tree layout with
light gray headers, collapsible category sections.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from nav2_config.types.params import ParamValue
from nav2_config.gui.widgets.param_row import ParamRow

if TYPE_CHECKING:
    from nav2_config.core.topic_discovery import TopicDiscovery
    from nav2_config.core.frame_discovery import FrameDiscovery

logger = logging.getLogger(__name__)

# ── RViz2 light colour constants ─────────────────────────────────────────────
_BG_PANEL = '#e8e8e8'
_BG_HDR   = '#d0d0d0'
_BG_CAT   = '#e0e0e0'   # Category section header background
_BORDER   = '#c0c0c0'
_BLUE     = '#3399ff'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'
_AMBER    = '#ff9800'


class _CategorySection(QWidget):
    """Collapsible section grouping ParamRow widgets under a category header.

    Header looks like RViz2's group rows: slightly darker background,
    expand arrow, category name, row count in dim text.
    """

    toggled = pyqtSignal(str, bool)  # (category, expanded)

    def __init__(self, category: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._category = category
        self._expanded = False  # collapsed by default
        self._rows: list[ParamRow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header is a clickable container with two labels side by side
        self._header = QWidget()
        self._header.setFixedHeight(24)
        self._header.setStyleSheet(
            f'QWidget {{ '
            f'    background: {_BG_CAT}; '
            f'    border-bottom: 1px solid {_BORDER}; '
            f'    border-top: 1px solid {_BORDER}; '
            f'}}'
        )
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header.mousePressEvent = lambda _e: self._toggle()

        hdr_layout = QHBoxLayout(self._header)
        hdr_layout.setContentsMargins(8, 0, 8, 0)
        hdr_layout.setSpacing(4)

        self._name_label = QLabel()
        self._name_label.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;'
        )
        hdr_layout.addWidget(self._name_label)

        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 10pt; font-weight: normal; background: transparent;'
        )
        hdr_layout.addWidget(self._count_lbl)
        hdr_layout.addStretch()

        layout.addWidget(self._header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content)

        self._refresh_header()
        self._content.setVisible(False)  # start collapsed

    def _refresh_header(self) -> None:
        arrow = '▾' if self._expanded else '▸'
        self._name_label.setText(f'{arrow}  {self._category.replace("_", " ").title()}')
        self._count_lbl.setText(f'({len(self._rows)})')

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._refresh_header()
        self.toggled.emit(self._category, self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Programmatically expand or collapse without emitting the toggled signal."""
        self._expanded = expanded
        self._content.setVisible(expanded)
        self._refresh_header()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_row(self, row: ParamRow) -> None:
        """Append a ParamRow to this section with alternating background."""
        idx = len(self._rows)
        row.set_row_index(idx)
        self._rows.append(row)
        self._content_layout.addWidget(row)
        self._refresh_header()

    def apply_filter(self, query: str) -> int:
        """Show/hide rows based on *query*. Returns the count of visible rows."""
        visible = 0
        for row in self._rows:
            matches = row.matches_search(query)
            row.setVisible(matches)
            if matches:
                visible += 1
        self.setVisible(visible > 0)
        return visible

    def apply_plugin_filter(self, plugin: str | None) -> None:
        """Show/hide rows based on the selected plugin (None = show all)."""
        for row in self._rows:
            if plugin is None:
                row.setVisible(True)
            else:
                defn = row._param_value.definition
                row.setVisible((not defn.plugin_specific) or defn.plugin == plugin)

    def set_descriptions_visible(self, visible: bool) -> None:
        """Toggle description text visibility on all rows in this section."""
        for row in self._rows:
            row.set_description_visible(visible)

    @property
    def rows(self) -> list[ParamRow]:
        return self._rows


class ParamPanel(QWidget):
    """Center panel: scrollable, searchable parameter editor with category grouping.

    Displays the parameters of one Nav2 node at a time.

    Signals:
        param_change_requested(str, str, Any):
            ``(node_name, param_name, new_value)`` — emitted on every GUI
            value change, used to keep the YAML preview current.  Does NOT
            trigger a ROS2 set_parameters call.
        param_set_requested(str, str, Any):
            ``(node_name, param_name, value)`` — emitted when the user
            explicitly clicks a row's Set button or the "Set All" button.
            The main window routes this to the ROS2 node.
    """

    param_change_requested = pyqtSignal(str, str, object)
    param_set_requested    = pyqtSignal(str, str, object)

    def __init__(
        self,
        topic_discovery: 'TopicDiscovery | None' = None,
        frame_discovery: 'FrameDiscovery | None' = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._node_name: str = ''
        self._param_values: list[ParamValue] = []
        self._sections: dict[str, _CategorySection] = {}
        self._all_rows: list[ParamRow] = []
        self._show_descriptions: bool = False
        self._topic_discovery = topic_discovery
        self._frame_discovery = frame_discovery
        # per-node memory: {node_name -> set of expanded category names}
        self._expanded_categories: dict[str, set[str]] = {}
        # pre-search snapshot of expanded state (None = not in search mode)
        self._pre_search_expanded: set[str] | None = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())

        # Scroll area for the parameter rows
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(0)
        self._scroll_layout.addStretch()

        self._scroll_area.setWidget(self._scroll_content)
        layout.addWidget(self._scroll_area, stretch=1)

    def _make_title_bar(self) -> QWidget:
        """Header bar: title left, Set All + search + Desc toggle right."""
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        self._title_label = QLabel('Parameters')
        self._title_label.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;'
        )
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title_label)

        self._count_label = QLabel('')
        self._count_label.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 9pt; background: transparent;'
        )
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._count_label)

        layout.addStretch()

        # "Set All (N)" button — enabled only when ≥1 row is ready to set
        self._set_all_btn = QPushButton('Set All')
        self._set_all_btn.setEnabled(False)
        self._set_all_btn.setFixedHeight(20)
        self._set_all_btn.setToolTip('Set all modified parameters at once')
        self._set_all_btn.setStyleSheet(
            f'QPushButton {{ background: #e0e0e0; border: 1px solid {_BORDER}; '
            f'color: #999999; font-size: 9pt; padding: 0 6px; }}'
            f'QPushButton:enabled {{ background: #2a82da; border-color: #1a6abf; '
            f'color: #ffffff; font-weight: bold; }}'
            f'QPushButton:enabled:hover {{ background: #1e70c8; }}'
        )
        self._set_all_btn.clicked.connect(self._set_all_modified)
        layout.addWidget(self._set_all_btn)

        # Inline search field in the header
        self._search = QLineEdit()
        self._search.setPlaceholderText('Search…')
        self._search.setFixedWidth(160)
        self._search.setFixedHeight(20)
        self._search.setStyleSheet(
            f'QLineEdit {{ background: {_BG_PANEL}; border: 1px solid {_BORDER}; '
            f'color: {_FG}; font-size: 9pt; padding: 0 4px; }}'
            f'QLineEdit:focus {{ border-color: {_BLUE}; }}'
        )
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        shortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        shortcut.activated.connect(self._search.setFocus)
        escape = QShortcut(QKeySequence('Escape'), self)
        escape.activated.connect(self._clear_search)

        # "Expand All / Collapse All" toggle
        self._expand_all_btn = QPushButton('⊞ All')
        self._expand_all_btn.setCheckable(True)
        self._expand_all_btn.setChecked(False)
        self._expand_all_btn.setFixedHeight(20)
        self._expand_all_btn.setToolTip('Expand all categories / Collapse all categories')
        self._expand_all_btn.setStyleSheet(
            f'QPushButton {{ background: #e0e0e0; border: 1px solid {_BORDER}; '
            f'color: {_FG}; font-size: 9pt; padding: 0 6px; }}'
            f'QPushButton:checked {{ background: {_BLUE}; border-color: #1a6abf; '
            f'color: #ffffff; }}'
            f'QPushButton:hover:!checked {{ background: #d4d4d4; }}'
        )
        self._expand_all_btn.toggled.connect(self._on_expand_all_toggled)
        layout.addWidget(self._expand_all_btn)

        # "Desc" toggle button
        self._desc_btn = QPushButton('Desc')
        self._desc_btn.setCheckable(True)
        self._desc_btn.setChecked(False)
        self._desc_btn.setFixedHeight(20)
        self._desc_btn.setToolTip('Toggle parameter descriptions')
        self._desc_btn.setStyleSheet(
            f'QPushButton {{ background: #555555; border: 1px solid {_BORDER}; '
            f'color: {_FG}; font-size: 9pt; padding: 0 6px; }}'
            f'QPushButton:checked {{ background: {_BLUE}; border-color: #1a6abf; '
            f'color: #ffffff; }}'
            f'QPushButton:hover:!checked {{ background: #666666; }}'
        )
        self._desc_btn.toggled.connect(self._on_toggle_descriptions)
        layout.addWidget(self._desc_btn)

        return bar

    # ------------------------------------------------------------------
    # Private: filtering and description toggle
    # ------------------------------------------------------------------

    def _on_toggle_descriptions(self, checked: bool) -> None:
        """Show or hide description lines on all param rows."""
        self._show_descriptions = checked
        for section in self._sections.values():
            section.set_descriptions_visible(checked)

    def filter_params(self, query: str) -> None:
        """Apply a search filter from an external widget (e.g., toolbar search box)."""
        self._search.setText(query)

    def _clear_search(self) -> None:
        if self._search.text():
            self._search.clear()

    def _on_search_changed(self, query: str) -> None:
        total_visible = 0
        if query:
            # Save collapsed state on first keystroke, then expand all matching sections
            if self._pre_search_expanded is None:
                self._pre_search_expanded = {
                    cat for cat, sec in self._sections.items() if sec._expanded
                }
            for section in self._sections.values():
                count = section.apply_filter(query)
                if count > 0:
                    section.set_expanded(True)
                total_visible += count
            total_all = len(self._all_rows)
            self._count_label.setText(f'{total_visible}/{total_all}')
        else:
            # Restore pre-search collapsed state
            pre = self._pre_search_expanded or set()
            for cat, section in self._sections.items():
                section.apply_filter('')
                section.set_expanded(cat in pre)
            self._pre_search_expanded = None
            self._refresh_count_label()

    def _on_section_toggled(self, category: str, expanded: bool) -> None:
        """Remember which categories are open for the current node."""
        node_set = self._expanded_categories.setdefault(self._node_name, set())
        if expanded:
            node_set.add(category)
        else:
            node_set.discard(category)

    def _on_expand_all_toggled(self, checked: bool) -> None:
        """Expand or collapse all category sections at once."""
        self._expand_all_btn.setText('⊟ All' if checked else '⊞ All')
        for section in self._sections.values():
            section.set_expanded(checked)
        # Update remembered state to match
        node_set = self._expanded_categories.setdefault(self._node_name, set())
        if checked:
            node_set.update(self._sections.keys())
        else:
            node_set.clear()

    def _refresh_count_label(self) -> None:
        modified = sum(1 for pv in self._param_values if pv.is_modified)
        n = len(self._param_values)
        if n:
            mod_part = f'  ·  {modified} modified' if modified else ''
            self._count_label.setText(f'{n} params{mod_part}')
        else:
            self._count_label.setText('')

    def _update_set_all_btn(self) -> None:
        """Refresh the Set All button label and enabled state."""
        count = sum(1 for row in self._all_rows if row.is_ready_to_set())
        if count > 0:
            self._set_all_btn.setText(f'Set All ({count})')
            self._set_all_btn.setEnabled(True)
        else:
            self._set_all_btn.setText('Set All')
            self._set_all_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Private: row rebuild
    # ------------------------------------------------------------------

    def _clear_rows(self) -> None:
        layout = self._scroll_layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._sections = {}
        self._all_rows = []

    # ------------------------------------------------------------------
    # Private: "Set All" handler
    # ------------------------------------------------------------------

    def _set_all_modified(self) -> None:
        """Trigger set on every row that is currently in READY or FAILED state."""
        for row in self._all_rows:
            if row.is_ready_to_set():
                row.trigger_set()
        self._update_set_all_btn()

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def set_node_name(self, node_name: str) -> None:
        """Update the panel title to reflect the selected node."""
        self._node_name = node_name
        bare = node_name.lstrip('/')
        display = bare.replace('_', ' ').title()
        self._title_label.setText(f'Parameters  —  {display}')

    def load_params(self, params: list[ParamValue]) -> None:
        """Rebuild the parameter rows for the given list of ParamValue objects."""
        self._clear_rows()
        self._param_values = params
        self._search.clear()

        if not params:
            self._count_label.setText('No parameters')
            self._update_set_all_btn()
            return

        categories: dict[str, list[ParamValue]] = {}
        for pv in params:
            categories.setdefault(pv.definition.category, []).append(pv)

        self._scroll_layout.takeAt(self._scroll_layout.count() - 1)

        remembered = self._expanded_categories.get(self._node_name, set())
        # Reset expand-all button without triggering its toggle handler
        self._expand_all_btn.blockSignals(True)
        self._expand_all_btn.setChecked(False)
        self._expand_all_btn.setText('⊞ All')
        self._expand_all_btn.blockSignals(False)
        self._pre_search_expanded = None

        for category in sorted(categories):
            section = _CategorySection(category)
            for pv in sorted(categories[category], key=lambda p: p.definition.param):
                row = ParamRow(
                    pv,
                    show_description=self._show_descriptions,
                    topic_discovery=self._topic_discovery,
                    frame_discovery=self._frame_discovery,
                )
                row.param_changed.connect(self._on_param_changed)
                row.param_set_requested.connect(self._on_row_set_requested)
                section.add_row(row)
                self._all_rows.append(row)
            # Restore remembered expansion state for this node
            if category in remembered:
                section.set_expanded(True)
            section.toggled.connect(self._on_section_toggled)
            self._sections[category] = section
            self._scroll_layout.addWidget(section)

        self._scroll_layout.addStretch()
        self._refresh_count_label()
        self._update_set_all_btn()
        logger.debug(
            'ParamPanel: loaded %d params in %d categories',
            len(params), len(categories),
        )

    def update_set_result(self, param_name: str, success: bool) -> None:
        """Route a ROS2 set_parameters result to the matching row's Set button."""
        for row in self._all_rows:
            if row._param_value.definition.param == param_name:
                row.receive_set_result(success)
                break
        self._update_set_all_btn()

    def mark_param_file_saved(self, param_name: str) -> None:
        """Mark *param_name* as saved to the config file (non-hot-reload).

        Transitions the matching row's Set button to the amber SAVED_FILE state
        to indicate the value is queued for the next Nav2 restart.
        """
        for row in self._all_rows:
            if row._param_value.definition.param == param_name:
                row.receive_file_save_result()
                break
        self._update_set_all_btn()

    def update_file_values(self, file_values: dict[str, object]) -> None:
        """Update the file-vs-live indicator on all rows.

        Args:
            file_values: Mapping of ``param_name -> file_value`` from the
                loaded nav2_params.yaml.  Missing keys mean the param is
                absent from the file.
        """
        for row in self._all_rows:
            param_name = row._param_value.definition.param
            fv = file_values.get(param_name)
            row.update_file_value(fv)

    def highlight_external_change(self, param_name: str) -> None:
        """Flash a param row with RViz2 blue to indicate an externally-set change."""
        from PyQt6.QtCore import QTimer
        for row in self._all_rows:
            if row._param_value.definition.param == param_name:
                row.setStyleSheet('QWidget { background: #3399ff33; }')
                QTimer.singleShot(1500, lambda r=row: r.restore_row_bg())
                break

    def scroll_to_param(self, param_name: str) -> None:
        """Scroll the parameter list to the row matching *param_name*."""
        for section in self._sections.values():
            for row in section.rows:
                if row._param_value.definition.param == param_name:
                    if not section._expanded:
                        section._toggle()
                    self._scroll_area.ensureWidgetVisible(row)
                    return

    def refresh_dropdowns(self) -> None:
        """Refresh all topic and frame selector dropdowns in the current view."""
        for row in self._all_rows:
            row.refresh_discovery_widget()

    def pending_param_names(self) -> set[str]:
        """Return the set of param names that have pending (unsent) changes."""
        return {
            row._param_value.definition.param
            for row in self._all_rows
            if row._param_value.is_pending
        }

    def _on_param_changed(self, param_name: str, value: Any) -> None:
        """Called when any row's displayed value changes (before Set is clicked)."""
        self.param_change_requested.emit(self._node_name, param_name, value)
        self._refresh_count_label()
        self._update_set_all_btn()
        # Auto-expand the category containing the modified param so it's visible
        for cat, section in self._sections.items():
            for row in section.rows:
                if row._param_value.definition.param == param_name:
                    if not section._expanded:
                        section.set_expanded(True)
                        self._expanded_categories.setdefault(
                            self._node_name, set()
                        ).add(cat)
                    return

    def _on_row_set_requested(self, param_name: str, value: object) -> None:
        """Called when a row's Set button is clicked; forwards to the main window."""
        self.param_set_requested.emit(self._node_name, param_name, value)
        self._update_set_all_btn()
