"""Node panel — left panel showing discovered Nav2 nodes with lifecycle state.

Styled to match RViz2's Displays panel: 28px header, 24px rows, #3399ff
selection highlight, system sans-serif font (not monospace).
"""

import logging

from lifecycle_msgs.msg import Transition
from PyQt6.QtCore import Qt, QPoint, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.node_discovery import NAV2_NODES

logger = logging.getLogger(__name__)

# ── RViz2 light colour constants ─────────────────────────────────────────────
_GREEN    = '#4caf50'    # active
_AMBER    = '#ff9800'    # inactive
_GRAY     = '#999999'    # unconfigured / not discovered
_RED      = '#e53935'    # finalized / error
_ORANGE   = '#ff6d00'    # restart pending indicator
_BLUE     = '#3399ff'    # RViz2 selection / active highlight
_BG_PANEL = '#ffffff'
_BG_HDR   = '#d0d0d0'
_BG_LC    = '#f0f0f0'    # lifecycle control bar background
_BORDER   = '#c0c0c0'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'


def _lifecycle_color(state: str, found: bool) -> str:
    """Return the dot colour for a node given its discovered/lifecycle state."""
    if not found:
        return _GRAY
    if state == 'active':
        return _GREEN
    if state == 'inactive':
        return _AMBER
    if state in ('finalized', 'error'):
        return _RED
    return _GRAY  # unconfigured / unknown


class NodeRow(QWidget):
    """Single row in the node list: coloured dot + display name + state + param count."""

    def __init__(
        self, display_name: str, found: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._build(display_name, found)

    def _build(self, display_name: str, found: bool) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 12, 4)
        layout.setSpacing(6)

        self._dot = QLabel('●')
        self._dot.setFixedWidth(10)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._dot)

        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(0)

        self._name = QLabel(display_name)
        self._name.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._name.setStyleSheet(f'color: {_FG}; font-size: 10pt;')
        name_col.addWidget(self._name)

        self._state_label = QLabel('')
        self._state_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._state_label.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 8pt; font-style: italic;'
        )
        name_col.addWidget(self._state_label)

        layout.addLayout(name_col)
        layout.addStretch()

        self._pending_dot = QLabel('●')
        self._pending_dot.setFixedWidth(8)
        self._pending_dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._pending_dot.setStyleSheet(f'color: {_ORANGE}; font-size: 7px;')
        self._pending_dot.setToolTip('Restart pending — param change requires node restart')
        self._pending_dot.setVisible(False)
        layout.addWidget(self._pending_dot)

        self._param_count = QLabel('')
        self._param_count.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._param_count.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')
        layout.addWidget(self._param_count)

        self._found = found
        self._state = 'unknown'
        self._update_dot()

    # ------------------------------------------------------------------
    # Public state setters
    # ------------------------------------------------------------------

    def set_found(self, found: bool) -> None:
        """Update whether the node is currently discovered."""
        self._found = found
        self._update_dot()
        if not found:
            self._state_label.setText('')

    def set_lifecycle_state(self, state: str) -> None:
        """Update the lifecycle state label and dot colour."""
        self._state = state
        self._update_dot()
        self._state_label.setText(f'({state})' if state not in ('unknown', '') else '')

    def set_selected(self, selected: bool) -> None:
        """Apply / clear the RViz2 blue selection highlight."""
        if selected:
            self.setStyleSheet(f'QWidget {{ background: {_BLUE}; }}')
            self._name.setStyleSheet('color: #ffffff; font-size: 10pt;')
            self._param_count.setStyleSheet('color: #dddddd; font-size: 9pt;')
            self._state_label.setStyleSheet(
                'color: #cccccc; font-size: 8pt; font-style: italic;'
            )
        else:
            self.setStyleSheet('QWidget { background: transparent; }')
            self._name.setStyleSheet(f'color: {_FG}; font-size: 10pt;')
            self._param_count.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')
            self._state_label.setStyleSheet(
                f'color: {_FG_DIM}; font-size: 8pt; font-style: italic;'
            )

    def set_param_count(self, count: int) -> None:
        """Show the number of parameters."""
        self._param_count.setText(str(count) if count else '')

    def set_restart_pending(self, pending: bool) -> None:
        """Show / hide the orange restart-pending indicator dot."""
        self._pending_dot.setVisible(pending)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_dot(self) -> None:
        color = _lifecycle_color(self._state, self._found)
        self._dot.setStyleSheet(f'color: {color}; font-size: 8px;')


class _LifecycleBar(QWidget):
    """Small control bar showing lifecycle state and action buttons for one node."""

    action_requested = pyqtSignal(str, str)  # (node_path, action)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_path = ''
        self._state = 'unknown'
        self._found = False
        self._lifecycle_manager_present = False
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            f'QWidget {{ background: {_BG_LC}; border-top: 1px solid {_BORDER}; }}'
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(3)

        # Top row: node name + state value
        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(4)
        self._node_label = QLabel('No node selected')
        self._node_label.setStyleSheet(f'color: {_FG}; font-size: 9pt; font-weight: bold;')
        info_row.addWidget(self._node_label)
        info_row.addStretch()
        self._state_val = QLabel('')
        self._state_val.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')
        info_row.addWidget(self._state_val)
        outer.addLayout(info_row)

        # Managed-mode row: shown when lifecycle_manager is running
        self._managed_row = QHBoxLayout()
        self._managed_row.setContentsMargins(0, 0, 0, 0)
        self._managed_row.setSpacing(3)

        self._btn_restart_stack = QPushButton('Restart Nav2 Stack')
        self._btn_restart_stack.setFixedHeight(20)
        self._btn_restart_stack.setToolTip(
            'Restart all Nav2 nodes via lifecycle_manager (safe — avoids bond failure)'
        )
        self._btn_restart_stack.setStyleSheet(
            f'QPushButton {{ background: #1565c0; border: 1px solid #0d47a1; '
            f'color: #ffffff; font-size: 8pt; padding: 0 8px; }}'
            f'QPushButton:hover {{ background: #1976d2; }}'
            f'QPushButton:pressed {{ background: #0d47a1; }}'
            f'QPushButton:disabled {{ background: #cccccc; color: #999999; '
            f'border-color: {_BORDER}; }}'
        )
        self._btn_restart_stack.clicked.connect(
            lambda: self.action_requested.emit(self._node_path, 'restart_stack')
        )
        self._managed_row.addWidget(self._btn_restart_stack)
        self._managed_row.addStretch()

        self._managed_label = QLabel('lifecycle_manager active')
        self._managed_label.setStyleSheet(f'color: {_GREEN}; font-size: 8pt; font-style: italic;')
        self._managed_row.addWidget(self._managed_label)
        outer.addLayout(self._managed_row)

        # Direct-control row: shown when lifecycle_manager is NOT running
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(3)

        def _btn(label: str, action: str, tooltip: str) -> QPushButton:
            b = QPushButton(label)
            b.setFixedHeight(20)
            b.setToolTip(tooltip)
            b.setStyleSheet(
                f'QPushButton {{ background: #555555; border: 1px solid {_BORDER}; '
                f'color: {_FG}; font-size: 8pt; padding: 0 5px; }}'
                f'QPushButton:hover {{ background: #666666; }}'
                f'QPushButton:pressed {{ background: #444444; }}'
                f'QPushButton:disabled {{ background: #cccccc; color: #999999; }}'
            )
            b.clicked.connect(
                lambda _checked, a=action: self.action_requested.emit(self._node_path, a)
            )
            btn_row.addWidget(b)
            return b

        self._btn_activate   = _btn('Activate',   'activate',   'Transition to active')
        self._btn_deactivate = _btn('Deactivate', 'deactivate', 'Transition to inactive')
        self._btn_configure  = _btn('Configure',  'configure',  'Transition to inactive (configure)')
        self._btn_cleanup    = _btn('Cleanup',     'cleanup',    'Transition to unconfigured')
        self._btn_restart    = _btn('Restart',     'restart',    'Full restart: deactivate→cleanup→configure→activate')
        outer.addLayout(btn_row)
        self._direct_btn_row_widget = btn_row  # keep reference to hide/show

        self._btn_shutdown = QPushButton('Shutdown')
        self._btn_shutdown.setFixedHeight(20)
        self._btn_shutdown.setToolTip('Shut down this node')
        self._btn_shutdown.setStyleSheet(
            f'QPushButton {{ background: #8b1a1a; border: 1px solid #c62828; '
            f'color: #ffffff; font-size: 8pt; padding: 0 5px; }}'
            f'QPushButton:hover {{ background: #b71c1c; }}'
            f'QPushButton:pressed {{ background: #6d1111; }}'
            f'QPushButton:disabled {{ background: #cccccc; color: #999999; '
            f'border-color: {_BORDER}; }}'
        )
        self._btn_shutdown.clicked.connect(
            lambda: self.action_requested.emit(self._node_path, 'shutdown')
        )
        outer.addWidget(self._btn_shutdown)

        self._direct_buttons = [
            self._btn_activate, self._btn_deactivate, self._btn_configure,
            self._btn_cleanup, self._btn_restart, self._btn_shutdown,
        ]

    def set_lifecycle_manager_mode(self, present: bool) -> None:
        """Switch between managed mode (lifecycle_manager present) and direct mode."""
        self._lifecycle_manager_present = present
        # Managed row: shown when manager is running
        self._btn_restart_stack.setVisible(present)
        self._managed_label.setVisible(present)
        # Direct buttons: hidden when manager is running
        for btn in self._direct_buttons:
            btn.setVisible(not present)
        self._refresh()

    def update_node(self, node_path: str, state: str, found: bool) -> None:
        """Update the bar for a newly selected node or changed lifecycle state."""
        self._node_path = node_path
        self._state = state
        self._found = found
        self._refresh()

    def _refresh(self) -> None:
        """Update labels and button enable/disable based on current state."""
        if not self._node_path:
            self._node_label.setText('No node selected')
            self._state_val.setText('')
            self._btn_restart_stack.setEnabled(False)
            for btn in self._direct_buttons:
                btn.setEnabled(False)
            return

        bare = self._node_path.lstrip('/')
        self._node_label.setText(f'/{bare}')

        state_colors = {
            'active': _GREEN, 'inactive': _AMBER,
            'unconfigured': _GRAY, 'finalized': _RED,
        }
        color = state_colors.get(self._state, _GRAY)
        self._state_val.setText(
            f'<span style="color:{color}; font-weight:bold;">{self._state}</span>'
        )
        self._state_val.setTextFormat(Qt.TextFormat.RichText)

        avail = self._found
        self._btn_restart_stack.setEnabled(avail)

        if not self._lifecycle_manager_present:
            s = self._state
            self._btn_activate.setEnabled(avail and s == 'inactive')
            self._btn_deactivate.setEnabled(avail and s == 'active')
            self._btn_configure.setEnabled(avail and s == 'unconfigured')
            self._btn_cleanup.setEnabled(avail and s == 'inactive')
            self._btn_restart.setEnabled(avail and s in ('active', 'inactive'))
            self._btn_shutdown.setEnabled(avail and s in ('active', 'inactive', 'unconfigured'))


class NodePanel(QWidget):
    """Left panel: lists all expected Nav2 nodes with lifecycle state.

    Signals:
        node_selected(str): emitted when user clicks a node; carries the
            ROS2 node path (e.g. '/controller_server').
        refresh_requested(): emitted when user clicks the Refresh button.
        lifecycle_action_requested(str, str): emitted when the user requests a
            lifecycle action; carries (node_path, action) where action is one of
            'activate', 'deactivate', 'configure', 'cleanup', 'restart', 'shutdown'.
    """

    node_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()
    lifecycle_action_requested = pyqtSignal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, tuple[QListWidgetItem, NodeRow]] = {}
        self._lifecycle_states: dict[str, str] = {}
        self._found_nodes: set[str] = set()
        self._restart_pending: set[str] = set()
        self._selected_node: str | None = None
        self._lifecycle_manager_present: bool = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())
        layout.addWidget(self._make_list(), stretch=1)
        layout.addWidget(self._make_lifecycle_bar())
        layout.addWidget(self._make_action_bar())
        layout.addWidget(self._make_footer())

        for path, display_name in NAV2_NODES.items():
            self._add_row(path, display_name, found=False)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        title = QLabel('Nav2 Nodes')
        title.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addStretch()

        refresh_btn = QPushButton('↻')
        refresh_btn.setFixedSize(22, 22)
        refresh_btn.setToolTip('Refresh node discovery  (Ctrl+R)')
        refresh_btn.setStyleSheet(
            f'QPushButton {{ background: transparent; border: 1px solid transparent; '
            f'color: {_FG_DIM}; font-size: 12px; }}'
            f'QPushButton:hover {{ background: {_BORDER}; border-color: {_BORDER}; '
            f'color: {_FG}; }}'
        )
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)

        return bar

    def _make_list(self) -> QListWidget:
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setStyleSheet(
            f'QListWidget {{ background: {_BG_PANEL}; border: none; outline: none; }}'
            f'QListWidget::item {{ border: none; padding: 0; margin: 0; }}'
            f'QListWidget::item:alternate {{ background: #f5f5f5; }}'
            f'QListWidget::item:selected {{ background: transparent; }}'
            f'QListWidget::item:selected:active {{ background: transparent; }}'
        )
        self._list.setSpacing(0)
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        return self._list

    def _make_lifecycle_bar(self) -> _LifecycleBar:
        self._lc_bar = _LifecycleBar()
        self._lc_bar.action_requested.connect(self._on_lc_bar_action)
        return self._lc_bar

    def _make_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(30)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-top: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(3)

        for label, tooltip in [
            ('Import', 'Import parameters from YAML  (Ctrl+I)'),
            ('Export', 'Export parameters to YAML  (Ctrl+S)'),
            ('Presets', 'Apply environment preset'),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(22)
            btn.setStyleSheet(
                f'QPushButton {{ background: #555555; border: 1px solid {_BORDER}; '
                f'color: {_FG}; font-size: 9pt; padding: 0 6px; }}'
                f'QPushButton:hover {{ background: #666666; }}'
                f'QPushButton:pressed {{ background: #444444; }}'
            )
            layout.addWidget(btn)
            if label == 'Import':
                self.import_btn = btn
            elif label == 'Export':
                self.export_btn = btn
            elif label == 'Presets':
                self.presets_btn = btn

        layout.addStretch()
        return bar

    def _make_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(22)
        footer.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-top: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(8, 0, 8, 0)

        self._count_label = QLabel(f'0/{len(NAV2_NODES)} nodes discovered')
        self._count_label.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')
        self._count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._count_label)

        return footer

    def _add_row(self, path: str, display_name: str, found: bool) -> None:
        """Create and register one node row."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 38))
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        row = NodeRow(display_name, found)

        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        self._rows[path] = (item, row)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def update_nodes(self, status: dict[str, bool]) -> None:
        """Update dot colours to reflect new discovery results."""
        self._found_nodes = {p for p, found in status.items() if found}
        for path, found in status.items():
            if path in self._rows:
                row = self._rows[path][1]
                row.set_found(found)
                lc_state = self._lifecycle_states.get(path, 'unknown')
                row.set_lifecycle_state(lc_state if found else '')

        found_count = len(self._found_nodes)
        self._count_label.setText(
            f'{found_count}/{len(NAV2_NODES)} nodes discovered'
        )

        if self._selected_node:
            self._refresh_lc_bar()

        logger.debug(
            'Node panel updated: %d/%d nodes running', found_count, len(NAV2_NODES)
        )

    def update_lifecycle_states(self, states: dict[str, str]) -> None:
        """Update lifecycle state labels and dot colours for the given nodes."""
        self._lifecycle_states.update(states)
        for path, state in states.items():
            if path in self._rows:
                found = path in self._found_nodes
                self._rows[path][1].set_lifecycle_state(state if found else '')

        if self._selected_node and self._selected_node in states:
            self._refresh_lc_bar()

    def set_node_restart_pending(self, node_path: str, pending: bool) -> None:
        """Show / clear the orange restart-pending indicator on *node_path*."""
        if pending:
            self._restart_pending.add(node_path)
        else:
            self._restart_pending.discard(node_path)
        if node_path in self._rows:
            self._rows[node_path][1].set_restart_pending(pending)

    def set_param_count(self, node_path: str, count: int) -> None:
        """Update the parameter count label for *node_path*."""
        if node_path in self._rows:
            self._rows[node_path][1].set_param_count(count)

    def set_lifecycle_manager_present(self, present: bool) -> None:
        """Switch the node panel between managed and direct lifecycle control modes.

        When lifecycle_manager is detected, the per-node Activate/Deactivate/
        Cleanup/Configure/Shutdown buttons are hidden and replaced with a single
        "Restart Nav2 Stack" button that uses the safe manage_nodes service.
        """
        self._lifecycle_manager_present = present
        self._lc_bar.set_lifecycle_manager_mode(present)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_lc_bar(self) -> None:
        """Sync the lifecycle bar to the currently selected node."""
        if not self._selected_node:
            self._lc_bar.update_node('', 'unknown', False)
            return
        state = self._lifecycle_states.get(self._selected_node, 'unknown')
        found = self._selected_node in self._found_nodes
        self._lc_bar.update_node(self._selected_node, state, found)

    def _on_lc_bar_action(self, node_path: str, action: str) -> None:
        if node_path:
            self.lifecycle_action_requested.emit(node_path, action)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _on_context_menu(self, pos: QPoint) -> None:
        """Show lifecycle context menu for the node under the cursor."""
        item = self._list.itemAt(pos)
        if item is None:
            return
        node_path: str = item.data(Qt.ItemDataRole.UserRole)
        state = self._lifecycle_states.get(node_path, 'unknown')
        found = node_path in self._found_nodes

        menu = QMenu(self)

        def _add(label: str, action: str, enabled: bool) -> None:
            act = menu.addAction(label)
            act.setEnabled(enabled)
            act.triggered.connect(
                lambda _checked, a=action, n=node_path:
                    self.lifecycle_action_requested.emit(n, a)
            )

        if self._lifecycle_manager_present:
            # Safe mode: use lifecycle_manager for all stack operations.
            _add('Restart Nav2 Stack', 'restart_stack', found)
            menu.addSeparator()
            # Show current state as a read-only item.
            state_act = menu.addAction(f'State: {state}')
            state_act.setEnabled(False)
            menu.addSeparator()
            # Advanced / dangerous direct controls with clear warning.
            warn_act = menu.addAction(
                '\u26a0 Direct Control (unsafe with lifecycle_manager)'
            )
            warn_act.setEnabled(False)
            _add('  Activate (direct — may cause CRITICAL FAILURE)',
                 'activate', found and state == 'inactive')
            _add('  Deactivate (direct — may cause CRITICAL FAILURE)',
                 'deactivate', found and state == 'active')
            _add('  Configure (direct — may cause CRITICAL FAILURE)',
                 'configure', found and state == 'unconfigured')
            _add('  Cleanup (direct — may cause CRITICAL FAILURE)',
                 'cleanup', found and state == 'inactive')
        else:
            # Direct mode: no lifecycle_manager, direct transitions are safe.
            _add('Activate',      'activate',   found and state == 'inactive')
            _add('Deactivate',    'deactivate', found and state == 'active')
            _add('Configure',     'configure',  found and state == 'unconfigured')
            _add('Cleanup',       'cleanup',    found and state == 'inactive')
            _add('Restart Node',  'restart',    found and state in ('active', 'inactive'))
            menu.addSeparator()
            _add('Shutdown Node', 'shutdown',
                 found and state in ('active', 'inactive', 'unconfigured'))

        menu.popup(self._list.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_current_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        """Handle list selection change: update row highlights and emit signal."""
        if previous is not None:
            prev_path: str = previous.data(Qt.ItemDataRole.UserRole)
            if prev_path in self._rows:
                self._rows[prev_path][1].set_selected(False)

        if current is not None:
            curr_path: str = current.data(Qt.ItemDataRole.UserRole)
            self._selected_node = curr_path
            if curr_path in self._rows:
                self._rows[curr_path][1].set_selected(True)
            self._refresh_lc_bar()
            self.node_selected.emit(curr_path)
            logger.debug('Node selected: %s', curr_path)
        else:
            self._selected_node = None
            self._lc_bar.update_node('', 'unknown', False)
