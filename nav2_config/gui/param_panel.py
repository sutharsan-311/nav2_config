"""ParamPanel — center panel: scrollable, searchable parameter editor."""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
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

logger = logging.getLogger(__name__)

# ── Nodes whose plugin selector bar is shown ────────────────────────────────
_CONTROLLER_PLUGINS = ['RPP', 'MPPI', 'DWB']
_PLANNER_PLUGINS = ['NavFn', 'SmacPlanner2D', 'SmacPlannerHybrid', 'ThetaStar']


class _CategorySection(QWidget):
    """Collapsible section grouping ParamRow widgets under a category header."""

    def __init__(self, category: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._category = category
        self._expanded = True
        self._rows: list[ParamRow] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._header = QPushButton()
        self._header.setStyleSheet(
            'QPushButton { '
            '    text-align: left; padding: 4px 8px; '
            '    background: #252526; border: none; '
            '    border-bottom: 1px solid #3e3e42; '
            '    color: #f57c00; font-size: 11px; font-weight: bold; '
            '    letter-spacing: 1px; '
            '}'
            'QPushButton:hover { background: #2a2d2e; }'
        )
        self._header.clicked.connect(self._toggle)
        layout.addWidget(self._header)

        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)
        layout.addWidget(self._content)

        self._refresh_header()

    def _refresh_header(self) -> None:
        icon = '▼' if self._expanded else '▶'
        self._header.setText(f'{icon}  {self._category.upper()}  ({len(self._rows)})')

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        self._content.setVisible(self._expanded)
        self._refresh_header()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_row(self, row: ParamRow) -> None:
        """Append a ParamRow to this section."""
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

    @property
    def rows(self) -> list[ParamRow]:
        return self._rows


class ParamPanel(QWidget):
    """Center panel: scrollable, searchable parameter editor with category grouping.

    Displays the parameters of one Nav2 node at a time.  The node is selected
    externally via ``set_node_name`` + ``load_params``.

    For ``controller_server`` and ``planner_server`` a plugin selector bar is
    shown at the top of the panel.

    Signals:
        param_change_requested(str, str, Any):
            ``(node_name, param_name, new_value)`` — emitted when the user
            changes a parameter value.  The caller should forward this to
            :meth:`Nav2ConfigNode.request_set_param`.
    """

    param_change_requested = pyqtSignal(str, str, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_name: str = ''
        self._param_values: list[ParamValue] = []
        self._sections: dict[str, _CategorySection] = {}
        self._all_rows: list[ParamRow] = []
        self._selected_plugin: str | None = None
        self._plugin_buttons: dict[str, QPushButton] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())
        layout.addWidget(self._make_plugin_bar())
        layout.addWidget(self._make_search_bar())

        # Scroll area for the parameter rows
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(0)
        self._scroll_layout.addStretch()

        scroll.setWidget(self._scroll_content)
        layout.addWidget(scroll, stretch=1)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet('background: #252526; border-bottom: 1px solid #3e3e42;')

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._title_label = QLabel('PARAMETERS')
        self._title_label.setProperty('role', 'heading')
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title_label)

        layout.addStretch()

        self._count_label = QLabel('')
        self._count_label.setProperty('role', 'dim')
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._count_label)

        return bar

    def _make_plugin_bar(self) -> QWidget:
        self._plugin_bar = QWidget()
        self._plugin_bar.setFixedHeight(32)
        self._plugin_bar.setStyleSheet(
            'background: #1e1e1e; border-bottom: 1px solid #3e3e42;'
        )
        self._plugin_bar.setVisible(False)

        self._plugin_bar_layout = QHBoxLayout(self._plugin_bar)
        self._plugin_bar_layout.setContentsMargins(8, 4, 8, 4)
        self._plugin_bar_layout.setSpacing(2)

        lbl = QLabel('Plugin:')
        lbl.setStyleSheet('color: #6d6d6d; font-size: 11px;')
        self._plugin_bar_layout.addWidget(lbl)
        self._plugin_bar_layout.addStretch()

        return self._plugin_bar

    def _make_search_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet('background: #1e1e1e; border-bottom: 1px solid #3e3e42;')

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 4, 8, 4)

        self._search = QLineEdit()
        self._search.setPlaceholderText('Search parameters…  (Ctrl+K)')
        self._search.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search)

        shortcut = QShortcut(QKeySequence('Ctrl+K'), self)
        shortcut.activated.connect(self._search.setFocus)

        return bar

    # ------------------------------------------------------------------
    # Private: plugin bar setup
    # ------------------------------------------------------------------

    def _setup_plugin_bar(self, plugins: list[str]) -> None:
        # Remove old plugin buttons from the layout (keep label + stretch).
        for btn in self._plugin_buttons.values():
            self._plugin_bar_layout.removeWidget(btn)
            btn.deleteLater()
        self._plugin_buttons.clear()
        self._selected_plugin = None

        # Remove trailing stretch so we can re-add buttons before it.
        stretch = self._plugin_bar_layout.takeAt(self._plugin_bar_layout.count() - 1)

        for plugin in plugins:
            btn = QPushButton(plugin)
            btn.setCheckable(True)
            btn.setStyleSheet(
                'QPushButton { '
                '    background: #2d2d2d; border: 1px solid #3e3e42; '
                '    color: #d4d4d4; padding: 2px 8px; font-size: 11px; '
                '}'
                'QPushButton:checked { '
                '    background: #f57c00; color: #ffffff; border-color: #e65100; '
                '}'
                'QPushButton:hover:!checked { background: #3e3e42; }'
            )
            btn.clicked.connect(
                lambda checked, p=plugin: self._on_plugin_selected(p, checked)
            )
            self._plugin_buttons[plugin] = btn
            self._plugin_bar_layout.addWidget(btn)

        # Re-add stretch at end.
        self._plugin_bar_layout.addStretch()
        self._plugin_bar.setVisible(True)

    # ------------------------------------------------------------------
    # Private: filtering
    # ------------------------------------------------------------------

    def _on_plugin_selected(self, plugin: str, checked: bool) -> None:
        if checked:
            self._selected_plugin = plugin
            for p, btn in self._plugin_buttons.items():
                if p != plugin:
                    btn.setChecked(False)
        else:
            self._selected_plugin = None

        for section in self._sections.values():
            section.apply_plugin_filter(self._selected_plugin)

        # Re-apply any active search on top of plugin filter.
        if self._search.text():
            self._on_search_changed(self._search.text())

    def _on_search_changed(self, query: str) -> None:
        total_visible = 0
        for section in self._sections.values():
            total_visible += section.apply_filter(query)

        if query:
            self._count_label.setText(f'{total_visible} matching')
        else:
            self._refresh_count_label()

    def _refresh_count_label(self) -> None:
        modified = sum(1 for pv in self._param_values if pv.is_modified)
        n = len(self._param_values)
        self._count_label.setText(
            f'{n} params  •  modified: {modified}' if n else ''
        )

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
    # Public slots
    # ------------------------------------------------------------------

    def set_node_name(self, node_name: str) -> None:
        """Update the panel title to reflect the selected node."""
        self._node_name = node_name
        bare = node_name.lstrip('/')
        self._title_label.setText(f'PARAMETERS — {bare.upper()}')

    def load_params(self, params: list[ParamValue]) -> None:
        """Rebuild the parameter rows for the given list of ParamValue objects.

        Grouped by ``ParamValue.definition.category``, sorted alphabetically
        within each category.

        Args:
            params: Parameters to display (typically from one Nav2 node).
        """
        self._clear_rows()
        self._param_values = params
        self._search.clear()

        if not params:
            self._count_label.setText('No parameters')
            return

        # Show / hide plugin selector bar.
        bare_node = self._node_name.lstrip('/')
        if bare_node == 'controller_server':
            self._setup_plugin_bar(_CONTROLLER_PLUGINS)
        elif bare_node == 'planner_server':
            self._setup_plugin_bar(_PLANNER_PLUGINS)
        else:
            for btn in self._plugin_buttons.values():
                btn.deleteLater()
            self._plugin_buttons.clear()
            self._plugin_bar.setVisible(False)
            self._selected_plugin = None

        # Group params by category, preserving within-category schema order.
        categories: dict[str, list[ParamValue]] = {}
        for pv in params:
            categories.setdefault(pv.definition.category, []).append(pv)

        # Remove trailing stretch before adding sections.
        self._scroll_layout.takeAt(self._scroll_layout.count() - 1)

        for category in sorted(categories):
            section = _CategorySection(category)
            for pv in sorted(categories[category], key=lambda p: p.definition.param):
                row = ParamRow(pv)
                row.param_changed.connect(self._on_param_changed)
                section.add_row(row)
                self._all_rows.append(row)
            self._sections[category] = section
            self._scroll_layout.addWidget(section)

        self._scroll_layout.addStretch()
        self._refresh_count_label()
        logger.debug('ParamPanel: loaded %d params in %d categories', len(params), len(categories))

    def update_param_result(self, param_name: str, success: bool) -> None:
        """Apply visual feedback after a set_parameters call completes.

        Args:
            param_name: Name of the parameter that was set.
            success: Whether the ROS2 node accepted the change.
        """
        for row in self._all_rows:
            if row._param_value.definition.param == param_name:
                color = '#4caf50' if success else '#f44336'
                row.setStyleSheet(f'QWidget {{ background: {color}22; }}')
                # Clear the flash after a short delay via a one-shot timer.
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(800, lambda r=row: r.setStyleSheet(''))
                break

    # ------------------------------------------------------------------
    # Private: param change handler
    # ------------------------------------------------------------------

    def _on_param_changed(self, param_name: str, value: Any) -> None:
        self.param_change_requested.emit(self._node_name, param_name, value)
        self._refresh_count_label()
