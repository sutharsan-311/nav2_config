"""Node panel — left panel showing discovered Nav2 nodes with status dots.

Styled to match RViz2's Displays panel: 28px header, 24px rows, #3399ff
selection highlight, system sans-serif font (not monospace).
"""

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

# ── RViz2 light colour constants ─────────────────────────────────────────────
_GREEN    = '#4caf50'
_GRAY     = '#999999'
_BLUE     = '#3399ff'     # RViz2 selection / active highlight
_BG_PANEL = '#ffffff'
_BG_HDR   = '#d0d0d0'
_BORDER   = '#c0c0c0'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'


class NodeRow(QWidget):
    """Single row in the node list: coloured dot + display name + param count."""

    def __init__(
        self, display_name: str, found: bool, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._build(display_name, found)

    def _build(self, display_name: str, found: bool) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 12, 8)
        layout.setSpacing(7)

        self._dot = QLabel('●')
        self._dot.setFixedWidth(10)
        self._dot.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._dot)

        self._name = QLabel(display_name)
        self._name.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._name.setStyleSheet(f'color: {_FG}; font-size: 10pt;')
        layout.addWidget(self._name)
        layout.addStretch()

        self._param_count = QLabel('')
        self._param_count.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self._param_count.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')
        layout.addWidget(self._param_count)

        self.set_found(found)

    # ------------------------------------------------------------------
    # Public state setters
    # ------------------------------------------------------------------

    def set_found(self, found: bool) -> None:
        """Update the status dot colour."""
        color = _GREEN if found else _GRAY
        self._dot.setStyleSheet(f'color: {color}; font-size: 8px;')

    def set_selected(self, selected: bool) -> None:
        """Apply / clear the RViz2 blue selection highlight."""
        if selected:
            self.setStyleSheet(f'QWidget {{ background: {_BLUE}; }}')
            self._name.setStyleSheet('color: #ffffff; font-size: 10pt;')
            self._param_count.setStyleSheet('color: #dddddd; font-size: 9pt;')
        else:
            self.setStyleSheet('QWidget { background: transparent; }')
            self._name.setStyleSheet(f'color: {_FG}; font-size: 10pt;')
            self._param_count.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt;')

    def set_param_count(self, count: int) -> None:
        """Show the number of parameters."""
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
        layout.addWidget(self._make_action_bar())
        layout.addWidget(self._make_footer())

        # Populate rows immediately (all offline) so the panel is never empty.
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
        self._list.setSpacing(2)
        self._list.currentItemChanged.connect(self._on_current_changed)
        return self._list

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
            # Store refs so MainWindow can connect them later.
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
        item.setSizeHint(QSize(0, 32))
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
        for path, found in status.items():
            if path in self._rows:
                self._rows[path][1].set_found(found)

        found_count = sum(1 for v in status.values() if v)
        self._count_label.setText(
            f'{found_count}/{len(NAV2_NODES)} nodes discovered'
        )
        logger.debug(
            'Node panel updated: %d/%d nodes running', found_count, len(NAV2_NODES)
        )

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
