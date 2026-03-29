# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Node panel — left panel showing discovered Nav2 nodes with lifecycle state.

Flat QListWidget with two-line rows: [icon] [name / state + dot] [count badge].
Right-click shows lifecycle context menu.  Selected row gets a 3 px left border
in the node's icon colour, like an IDE active-file indicator.
"""

import logging

from PyQt6.QtCore import Qt, QPoint, QRect, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
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

# ── Colour palette ────────────────────────────────────────────────────────────
_GREEN    = '#4caf50'
_AMBER    = '#ff9800'
_GRAY     = '#999999'
_RED      = '#e53935'
_ORANGE   = '#ff6d00'
_BLUE     = '#3399ff'
_BG_PANEL = '#ffffff'
_BG_ROW2  = '#fafafa'          # alternating row tint
_BG_HDR   = '#f0f0f0'          # header strip
_BG_SEL   = '#3399ff'          # selected row
_BG_HOV   = '#e3f2fd'          # hovered row
_BORDER   = '#c0c0c0'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'

# ── Icon letter + colour per node ─────────────────────────────────────────────
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
_ROW_HEIGHT = 44
_LEFT_BORDER_W = 3   # px — coloured left-edge on selected row


# ── Small helper widgets ──────────────────────────────────────────────────────

class _StatusDot(QWidget):
    """6 px filled circle drawn with QPainter — state indicator."""

    _D = 6

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(self._D + 4, self._D + 4)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        offset = (self.width() - self._D) // 2
        p.drawEllipse(offset, offset, self._D, self._D)
        p.end()


class _CountBadge(QWidget):
    """Rounded-rectangle pill showing a param count.  Hidden when count is 0."""

    _W = 36
    _H = 18

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = 0
        self.setFixedSize(self._W, self._H)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def set_count(self, count: int) -> None:
        self._count = count
        self.setVisible(count > 0)
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[override]
        if self._count <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Pill background
        p.setBrush(QColor('#e8e8e8'))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 2, self._W, self._H - 4, 7, 7)
        # Count text
        p.setPen(QColor('#444444'))
        p.setFont(QFont('Ubuntu', 7))
        p.drawText(QRect(0, 2, self._W, self._H - 4), Qt.AlignmentFlag.AlignCenter,
                   str(self._count))
        p.end()


# ── Coloured letter icon (fallback when SVG unavailable) ─────────────────────

def _colored_letter_icon(letter: str, color: str, size: int = 20) -> QIcon:
    """Rounded rectangle with a white letter — cached."""
    cache_key = (letter, color)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(1, 1, size - 2, size - 2, 4, 4)
    p.setPen(QColor('#ffffff'))
    pt = 9 if len(letter) == 1 else 6
    p.setFont(QFont('Ubuntu', pt, QFont.Weight.Bold))
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    icon = QIcon(px)
    _ICON_CACHE[cache_key] = icon
    return icon


def _panel_icon(size: int = 14) -> QPixmap:
    """Small grid pixmap for the panel header decoration."""
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
        'restart!':     _AMBER,
    }.get(state, _GRAY)


# ── Per-node row widget ───────────────────────────────────────────────────────

class _NodeRow(QWidget):
    """Two-line row: [icon] [name\\nstate ● ] [count badge].

    Selected rows get a 3 px left border in the node's icon colour, drawn via
    paintEvent so it sits on top of the QListWidget blue selection highlight.
    Label colours flip to white when selected so they remain legible.
    """

    ICON_SIZE = 20

    def __init__(self, node_path: str, display_name: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_path = node_path
        self._found = False
        self._state = 'not found'
        self._is_selected = False
        _, self._border_color = _NODE_ICON_DEFS.get(node_path, ('?', '#666666'))
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui(display_name)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self, display_name: str) -> None:
        layout = QHBoxLayout(self)
        # Left margin > border width so text doesn't overlap the painted border
        layout.setContentsMargins(_LEFT_BORDER_W + 8, 0, 8, 0)
        layout.setSpacing(8)

        # ── Node type icon ──
        self._icon_lbl = QLabel()
        self._icon_lbl.setFixedSize(self.ICON_SIZE, self.ICON_SIZE)
        self._icon_lbl.setStyleSheet('background: transparent;')
        self._set_icon(active=False)
        layout.addWidget(self._icon_lbl)

        # ── Centre column: name + state row ──
        center = QWidget()
        center.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        center.setStyleSheet('background: transparent;')
        cv = QVBoxLayout(center)
        cv.setContentsMargins(0, 5, 0, 5)
        cv.setSpacing(1)

        self._name_lbl = QLabel(display_name)
        self._name_lbl.setStyleSheet(
            f'font-weight: 600; font-size: 10pt; color: {_GRAY}; background: transparent;'
        )
        cv.addWidget(self._name_lbl)

        # State label + status dot side by side
        state_row = QWidget()
        state_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        state_row.setStyleSheet('background: transparent;')
        sr = QHBoxLayout(state_row)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(4)

        self._state_lbl = QLabel('not found')
        self._state_lbl.setStyleSheet(
            f'color: {_GRAY}; font-size: 8pt; background: transparent;'
        )
        sr.addWidget(self._state_lbl)

        self._dot = _StatusDot(_GRAY)
        sr.addWidget(self._dot)
        sr.addStretch()

        cv.addWidget(state_row)
        layout.addWidget(center, stretch=1)

        # ── Right: param count badge ──
        self._badge = _CountBadge()
        layout.addWidget(self._badge)

    # ------------------------------------------------------------------
    # paintEvent — coloured left border when selected
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self._is_selected:
            p = QPainter(self)
            p.fillRect(0, 0, _LEFT_BORDER_W, self.height(), QColor(self._border_color))
            p.end()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_selected(self, selected: bool) -> None:
        """Flip selected state — updates label colours and left border."""
        self._is_selected = selected
        self._apply_label_colors()
        self.update()

    def update_state(self, found: bool, state: str, pending: bool) -> None:
        """Refresh icon, state text, dot colour, and label colours."""
        self._found = found
        self._state = state
        self._set_icon(active=found and state == 'active')

        display_state = (
            (state if state not in ('unknown', '') else 'found') if found else 'not found'
        )
        if pending and found:
            display_state = 'restart!'

        self._state_lbl.setText(display_state)
        dot_color = _AMBER if (pending and found) else _state_color(display_state, found)
        self._dot.set_color(dot_color)

        if not self._is_selected:
            self._apply_label_colors()

    def update_count(self, count: int) -> None:
        """Update the param count badge."""
        self._badge.set_count(count)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_label_colors(self) -> None:
        """Set name/state label colours depending on selection + node state."""
        if self._is_selected:
            self._name_lbl.setStyleSheet(
                'font-weight: 600; font-size: 10pt; color: white; background: transparent;'
            )
            self._state_lbl.setStyleSheet(
                'color: rgba(255,255,255,200); font-size: 8pt; background: transparent;'
            )
        else:
            if not self._found:
                name_color = _GRAY
            else:
                _, icon_color = _NODE_ICON_DEFS.get(self._node_path, ('?', '#666666'))
                name_color = icon_color if self._state == 'active' else _FG
            self._name_lbl.setStyleSheet(
                f'font-weight: 600; font-size: 10pt; color: {name_color}; background: transparent;'
            )
            state_color = _state_color(self._state, self._found)
            self._state_lbl.setStyleSheet(
                f'color: {state_color}; font-size: 8pt; background: transparent;'
            )

    def _set_icon(self, active: bool) -> None:
        icon = node_icon(self._node_path, active)
        if not icon.isNull():
            self._icon_lbl.setPixmap(icon.pixmap(self.ICON_SIZE, self.ICON_SIZE))
        else:
            letter, color = _NODE_ICON_DEFS.get(self._node_path, ('?', '#666666'))
            fallback = _colored_letter_icon(letter, color, self.ICON_SIZE)
            self._icon_lbl.setPixmap(fallback.pixmap(self.ICON_SIZE, self.ICON_SIZE))


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
    # paintEvent — right border separating this panel from param panel
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        p = QPainter(self)
        p.setPen(QColor(_BORDER))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        p.end()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._make_header())
        layout.addWidget(self._make_list(), stretch=1)

    def _make_header(self) -> QWidget:
        """Panel header: icon + bold title on left, connected count on right."""
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}'
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(5)

        # Decorative grid icon
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(14, 14)
        icon_lbl.setPixmap(_panel_icon())
        icon_lbl.setStyleSheet('background: transparent;')
        layout.addWidget(icon_lbl)

        # Title
        title = QLabel('Nav2 Nodes')
        title.setStyleSheet(
            f'color: {_FG}; font-size: 11pt; font-weight: bold; background: transparent;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title, stretch=1)

        # Connected count — right-aligned, colour-coded
        self._count_header = QLabel()
        self._count_header.setStyleSheet('background: transparent;')
        self._count_header.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._update_count_header(0)
        layout.addWidget(self._count_header)

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
            f'<span style="font-size:8pt; color:{count_color}; font-weight:bold;">'
            f'{found}/{total}'
            f'</span>'
            f'<span style="font-size:8pt; color:{_FG_DIM};"> connected</span>'
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
            f'  border-bottom: 1px solid #e0e0e0;'
            f'  padding: 0;'
            f'}}'
            f'QListWidget::item:selected {{'
            f'  background: {_BG_SEL};'
            f'}}'
            f'QListWidget::item:hover:!selected {{'
            f'  background: {_BG_HOV};'
            f'}}'
        )

        for i, (path, display_name) in enumerate(NAV2_NODES.items()):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(0, _ROW_HEIGHT))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            # Subtle alternating tint — QSS selected/hover states override this
            item.setBackground(QColor(_BG_ROW2 if i % 2 else _BG_PANEL))
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
        """Update the param count shown in the row badge."""
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

    def _set_row_selected(self, node_path: str | None, selected: bool) -> None:
        if node_path and node_path in self._node_rows:
            self._node_rows[node_path].set_selected(selected)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        node_path: object = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(node_path, str) or not node_path.startswith('/'):
            return
        # Update left-border selection indicator
        self._set_row_selected(self._selected_node, False)
        self._selected_node = node_path
        self._set_row_selected(node_path, True)
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
