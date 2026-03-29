"""Node panel — left panel showing discovered Nav2 nodes with lifecycle state.

Flat QListWidget with one row per node: icon, display name, state label,
and param count.  No expand arrows.  No bottom button bar.
Right-click shows lifecycle context menu.
"""

import logging

from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.node_discovery import NAV2_NODES
from nav2_config.gui.icons import node_icon

logger = logging.getLogger(__name__)

# ── Colour constants ──────────────────────────────────────────────────────────
_GREEN    = '#4caf50'
_AMBER    = '#ff9800'
_GRAY     = '#999999'
_RED      = '#e53935'
_ORANGE   = '#ff6d00'
_BLUE     = '#3399ff'
_BG_PANEL = '#ffffff'
_BG_HDR   = '#d0d0d0'
_BORDER   = '#c0c0c0'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'

# ── Node icon definitions (letter + color for the colored-square fallback) ────
_NODE_ICON_DEFS: dict[str, tuple[str, str]] = {
    '/amcl':                          ('A',  '#2196f3'),
    '/controller_server':             ('C',  '#4caf50'),
    '/planner_server':                ('P',  '#2196f3'),
    '/bt_navigator':                  ('B',  '#ff9800'),
    '/local_costmap/local_costmap':   ('LC', '#9c27b0'),
    '/global_costmap/global_costmap': ('GC', '#9c27b0'),
    '/smoother_server':               ('S',  '#607d8b'),
    '/velocity_smoother':             ('V',  '#009688'),
    '/behavior_server':               ('BR', '#f44336'),
    '/waypoint_follower':             ('W',  '#795548'),
    '/map_server':                    ('M',  '#3f51b5'),
}

_ICON_CACHE: dict[tuple[str, str], QIcon] = {}
_ROW_HEIGHT = 36


def _colored_letter_icon(letter: str, color: str, size: int = 20) -> QIcon:
    """Colored rounded-rectangle with a white letter — fallback when SVG unavailable."""
    cache_key = (letter, color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    p.setPen(QColor('#ffffff'))
    pt = 9 if len(letter) == 1 else 6
    p.setFont(QFont('Ubuntu', pt, QFont.Weight.Bold))
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    icon = QIcon(px)
    _ICON_CACHE[cache_key] = icon
    return icon


def _panel_icon(size: int = 14) -> QPixmap:
    """Small grid pixmap for the panel header."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setPen(QColor(_FG_DIM))
    step = (size - 2) // 3
    for i in range(4):
        v = 1 + i * step
        p.drawLine(v, 1, v, size - 1)
        p.drawLine(1, v, size - 1, v)
    p.end()
    return px


def _state_color(state: str, found: bool) -> str:
    if not found:
        return _GRAY
    return {
        'active':       _GREEN,
        'inactive':     _AMBER,
        'unconfigured': _GRAY,
        'finalized':    _RED,
        'not found':    _GRAY,
    }.get(state, _GRAY)


# ── Per-node row widget ───────────────────────────────────────────────────────

class _NodeRow(QWidget):
    """Single flat node row: [icon] [name] [state] [count]."""

    ICON_SIZE = 20

    def __init__(self, node_path: str, display_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_path = node_path
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui(display_name)

    def _build_ui(self, display_name: str) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        # Node type icon
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self._icon_lbl.setStyleSheet('background: transparent;')
        self._set_icon(active=False)
        layout.addWidget(self._icon_lbl)

        # Display name (bold)
        self._name_lbl = QLabel(display_name)
        self._name_lbl.setStyleSheet(
            f'font-weight: bold; font-size: 9pt; color: {_GRAY}; background: transparent;'
        )
        layout.addWidget(self._name_lbl, stretch=1)

        # Lifecycle state label
        self._state_lbl = QLabel('not found')
        self._state_lbl.setFixedWidth(76)
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._state_lbl.setStyleSheet(
            f'color: {_GRAY}; font-size: 8pt; background: transparent;'
        )
        layout.addWidget(self._state_lbl)

        # Param count (right-aligned gray)
        self._count_lbl = QLabel('')
        self._count_lbl.setFixedWidth(32)
        self._count_lbl.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._count_lbl.setStyleSheet(
            f'color: {_GRAY}; font-size: 8pt; background: transparent;'
        )
        layout.addWidget(self._count_lbl)

    def _set_icon(self, active: bool) -> None:
        icon = node_icon(self._node_path, active)
        if not icon.isNull():
            self._icon_lbl.setPixmap(icon.pixmap(self.ICON_SIZE, self.ICON_SIZE))
        else:
            letter, color = _NODE_ICON_DEFS.get(self._node_path, ('?', '#666666'))
            fallback = _colored_letter_icon(letter, color, self.ICON_SIZE)
            self._icon_lbl.setPixmap(fallback.pixmap(self.ICON_SIZE, self.ICON_SIZE))

    def update_state(self, found: bool, state: str, pending: bool) -> None:
        """Refresh the name color, state label, and icon."""
        self._set_icon(active=found and state == 'active')

        # Name color
        if not found:
            name_color = _GRAY
        else:
            _, icon_color = _NODE_ICON_DEFS.get(self._node_path, ('?', '#666666'))
            name_color = icon_color if state == 'active' else _FG
        self._name_lbl.setStyleSheet(
            f'font-weight: bold; font-size: 9pt; color: {name_color}; background: transparent;'
        )

        # State label
        display_state = (state if state not in ('unknown', '') else 'found') if found else 'not found'
        if pending and found:
            display_state = 'restart!'
        color = _state_color(display_state, found)
        if pending and found:
            color = _AMBER
        self._state_lbl.setText(display_state)
        self._state_lbl.setStyleSheet(
            f'color: {color}; font-size: 8pt; background: transparent;'
        )

    def update_count(self, count: int) -> None:
        """Update the param count display."""
        self._count_lbl.setText(str(count) if count else '')


# ── NodePanel ────────────────────────────────────────────────────────────────

class NodePanel(QWidget):
    """Left panel: flat list of Nav2 nodes with lifecycle state.

    Signals:
        node_selected(str): ROS2 node path when user clicks a node row.
        refresh_requested(): user clicked Refresh (toolbar).
        lifecycle_action_requested(str, str): (node_path, action) from context menu.
        load_config_requested(): user clicked Load Config (toolbar).
        save_requested(): user clicked Save (toolbar).
    """

    node_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    lifecycle_action_requested = pyqtSignal(str, str)
    load_config_requested = pyqtSignal()
    save_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._found_nodes: set[str] = set()
        self._lifecycle_states: dict[str, str] = {}
        self._param_counts: dict[str, int] = {}
        self._restart_pending: set[str] = set()
        self._lifecycle_manager_present: bool = False
        self._selected_node: str | None = None
        self._node_rows: dict[str, _NodeRow] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._make_header())
        layout.addWidget(self._make_count_bar())
        layout.addWidget(self._make_list(), stretch=1)

    def _make_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}'
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 6, 0)
        layout.setSpacing(5)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setPixmap(_panel_icon())
        icon_lbl.setStyleSheet('background: transparent;')
        layout.addWidget(icon_lbl)

        title = QLabel('Nav2 Nodes')
        title.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addStretch()

        dot = QLabel('●')
        dot.setFixedSize(14, 14)
        dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dot.setStyleSheet(
            f'color: {_ORANGE}; font-size: 10px; background: transparent; border: none;'
        )
        dot.setToolTip('Nav2 Nodes panel')
        layout.addWidget(dot)
        return bar

    def _make_count_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(22)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_PANEL}; border-bottom: 1px solid {_BORDER}; }}'
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)

        self._count_header = QLabel()
        self._count_header.setStyleSheet('background: transparent;')
        self._count_header.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._update_count_header(0)
        layout.addWidget(self._count_header)
        layout.addStretch()
        return bar

    def _update_count_header(self, found: int) -> None:
        total = len(NAV2_NODES)
        if found == total:
            count_color = _GREEN
        elif found == 0:
            count_color = _RED
        else:
            count_color = _AMBER
        self._count_header.setText(
            f'<span style="color:{_FG_DIM}; font-size:8pt;">'
            f'Nav2 Nodes — '
            f'<b style="color:{count_color};">{found}/{total}</b>'
            f'<span style="color:{_FG_DIM};"> connected</span>'
            f'</span>'
        )

    def _make_list(self) -> QListWidget:
        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.setStyleSheet(
            f'QListWidget {{'
            f'  background: {_BG_PANEL};'
            f'  border: none;'
            f'  outline: none;'
            f'}}'
            f'QListWidget::item {{'
            f'  border: none;'
            f'  padding: 0;'
            f'}}'
            f'QListWidget::item:selected {{'
            f'  background: {_BLUE};'
            f'}}'
            f'QListWidget::item:hover:!selected {{'
            f'  background: #f0f0f0;'
            f'}}'
        )

        for path, display_name in NAV2_NODES.items():
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._list.addItem(item)

            row = _NodeRow(path, display_name)
            self._list.setItemWidget(item, row)
            self._node_rows[path] = row

        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        return self._list

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def update_nodes(self, status: dict[str, bool]) -> None:
        """Update discovery state for all nodes."""
        self._found_nodes = {p for p, found in status.items() if found}
        for path in status:
            self._refresh_row(path)
        self._update_count_header(len(self._found_nodes))
        logger.debug(
            'Node panel: %d/%d nodes discovered',
            len(self._found_nodes), len(NAV2_NODES),
        )

    def update_lifecycle_states(self, states: dict[str, str]) -> None:
        """Update lifecycle state labels for the given nodes."""
        self._lifecycle_states.update(states)
        for path in states:
            self._refresh_row(path)

    def set_param_count(self, node_path: str, count: int) -> None:
        """Update the param count shown in the row."""
        self._param_counts[node_path] = count
        row = self._node_rows.get(node_path)
        if row:
            row.update_count(count)

    def set_node_restart_pending(self, node_path: str, pending: bool) -> None:
        """Show / clear a restart-pending indicator on a node row."""
        if pending:
            self._restart_pending.add(node_path)
        else:
            self._restart_pending.discard(node_path)
        self._refresh_row(node_path)

    def set_lifecycle_manager_present(self, present: bool) -> None:
        """Record lifecycle_manager presence (used by context menu logic)."""
        self._lifecycle_manager_present = present

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_row(self, node_path: str) -> None:
        """Recompute the visual state of a single row."""
        row = self._node_rows.get(node_path)
        if not row:
            return
        found   = node_path in self._found_nodes
        state   = self._lifecycle_states.get(node_path, 'unknown')
        pending = node_path in self._restart_pending
        row.update_state(found, state, pending)

    def _item_for_pos(self, pos: QPoint) -> QListWidgetItem | None:
        return self._list.itemAt(pos)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        node_path: object = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(node_path, str) and node_path.startswith('/'):
            self._selected_node = node_path
            self.node_selected.emit(node_path)
            logger.debug('Node selected: %s', node_path)

    def _on_context_menu(self, pos: QPoint) -> None:
        """Show lifecycle-action context menu for the node under the cursor."""
        item = self._item_for_pos(pos)
        if not item:
            return
        node_path: object = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(node_path, str) or not node_path.startswith('/'):
            return

        state = self._lifecycle_states.get(node_path, 'unknown')
        found = node_path in self._found_nodes
        menu  = QMenu(self)

        def _add(label: str, action: str, enabled: bool) -> None:
            act = menu.addAction(label)
            act.setEnabled(enabled)
            act.triggered.connect(
                lambda _checked, a=action, n=node_path:
                    self.lifecycle_action_requested.emit(n, a)
            )

        if self._lifecycle_manager_present:
            _add('Restart Nav2 Stack', 'restart_stack', found)
            menu.addSeparator()
            state_act = menu.addAction(f'State: {state}')
            state_act.setEnabled(False)
            menu.addSeparator()
            warn = menu.addAction('\u26a0 Direct Control (unsafe with lifecycle_manager)')
            warn.setEnabled(False)
            _add('  Activate (direct — may cause CRITICAL FAILURE)',
                 'activate', found and state == 'inactive')
            _add('  Deactivate (direct — may cause CRITICAL FAILURE)',
                 'deactivate', found and state == 'active')
            _add('  Configure (direct — may cause CRITICAL FAILURE)',
                 'configure', found and state == 'unconfigured')
            _add('  Cleanup (direct — may cause CRITICAL FAILURE)',
                 'cleanup', found and state == 'inactive')
        else:
            _add('Activate',     'activate',   found and state == 'inactive')
            _add('Deactivate',   'deactivate', found and state == 'active')
            _add('Configure',    'configure',  found and state == 'unconfigured')
            _add('Cleanup',      'cleanup',    found and state == 'inactive')
            _add('Restart Node', 'restart',    found and state in ('active', 'inactive'))
            menu.addSeparator()
            _add('Shutdown Node', 'shutdown',
                 found and state in ('active', 'inactive', 'unconfigured'))

        menu.popup(self._list.viewport().mapToGlobal(pos))
