"""Node panel — left panel showing discovered Nav2 nodes with status dots."""

import logging

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
)

from nav2_config.core.node_discovery import NAV2_NODES

logger = logging.getLogger(__name__)

# ── Colour constants (mirror theme.py palette) ──────────────────────────────
_GREEN = '#4caf50'
_GRAY = '#555558'
_ORANGE = '#f57c00'
_BG_TITLE = '#252526'
_BORDER = '#3e3e42'
_FG_DIM = '#6d6d6d'


class NodeRow(QWidget):
    """Single row in the node list: coloured dot + display name + param count."""

    def __init__(self, display_name: str, found: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build(display_name, found)

    def _build(self, display_name: str, found: bool) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        self._dot = QLabel('●')
        self._dot.setFixedWidth(12)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._dot.setStyleSheet('font-size: 9px;')
        layout.addWidget(self._dot)

        self._name = QLabel(display_name)
        self._name.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._name)
        layout.addStretch()

        self._param_count = QLabel('')
        self._param_count.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._param_count.setStyleSheet(f'color: {_FG_DIM}; font-size: 11px;')
        layout.addWidget(self._param_count)

        self.set_found(found)

    # ------------------------------------------------------------------
    # Public state setters
    # ------------------------------------------------------------------

    def set_found(self, found: bool) -> None:
        """Update the status dot colour."""
        color = _GREEN if found else _GRAY
        self._dot.setStyleSheet(f'color: {color}; font-size: 9px;')

    def set_selected(self, selected: bool) -> None:
        """Apply / clear the ROS orange left-border selection highlight."""
        if selected:
            self.setStyleSheet(
                f'QWidget {{ background: #2a2d2e; border-left: 3px solid {_ORANGE}; }}'
            )
        else:
            self.setStyleSheet('')

    def set_param_count(self, count: int) -> None:
        """Show the number of parameters (populated in Phase 2)."""
        self._param_count.setText(str(count) if count else '')


class NodePanel(QWidget):
    """Left panel: lists all expected Nav2 nodes with running/offline status.

    Signals:
        node_selected(str): emitted when user clicks a node; carries the
            ROS2 node path (e.g. '/controller_server').
        refresh_requested(): emitted when user clicks the Refresh button.
    """

    node_selected = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # path → (QListWidgetItem, NodeRow)
        self._rows: dict[str, tuple[QListWidgetItem, NodeRow]] = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())
        layout.addWidget(self._make_list())
        layout.addWidget(self._make_footer())

        # Populate rows immediately (all offline) so the panel is never empty.
        for path, display_name in NAV2_NODES.items():
            self._add_row(path, display_name, found=False)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_TITLE}; border-bottom: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        title = QLabel('NODES')
        title.setProperty('role', 'heading')
        title.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(title)
        layout.addStretch()

        refresh_btn = QPushButton('↻')
        refresh_btn.setFixedSize(22, 22)
        refresh_btn.setToolTip('Refresh node discovery')
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)

        return bar

    def _make_list(self) -> QListWidget:
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.currentItemChanged.connect(self._on_current_changed)
        return self._list

    def _make_footer(self) -> QWidget:
        footer = QWidget()
        footer.setFixedHeight(28)
        footer.setStyleSheet(
            f'QWidget {{ background: {_BG_TITLE}; border-top: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(8, 0, 8, 0)

        self._count_label = QLabel(f'Discovered: 0/{len(NAV2_NODES)} nodes')
        self._count_label.setProperty('role', 'dim')
        layout.addWidget(self._count_label)

        return footer

    def _add_row(self, path: str, display_name: str, found: bool) -> None:
        """Create and register one node row."""
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setSizeHint(QSize(0, 32))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        # Re-enable selection (the above expression disables it; use proper flags):
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        row = NodeRow(display_name, found)

        self._list.addItem(item)
        self._list.setItemWidget(item, row)
        self._rows[path] = (item, row)

    # ------------------------------------------------------------------
    # Public slots
    # ------------------------------------------------------------------

    def update_nodes(self, status: dict[str, bool]) -> None:
        """Update dot colours to reflect new discovery results.

        Connected to SignalBridge.nodes_discovered. Safe to call from any
        thread because Qt delivers cross-thread signals on the receiver's
        thread (the Qt main thread here).
        """
        for path, found in status.items():
            if path in self._rows:
                self._rows[path][1].set_found(found)

        found_count = sum(1 for v in status.values() if v)
        self._count_label.setText(f'Discovered: {found_count}/{len(NAV2_NODES)} nodes')
        logger.debug('Node panel updated: %d/%d nodes running', found_count, len(NAV2_NODES))

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
            if curr_path in self._rows:
                self._rows[curr_path][1].set_selected(True)
            self.node_selected.emit(curr_path)
            logger.debug('Node selected: %s', curr_path)
