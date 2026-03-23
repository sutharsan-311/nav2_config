"""Main window for nav2_config: three-panel splitter layout."""

import logging
from PyQt6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QWidget,
    QLabel,
    QVBoxLayout,
    QStatusBar,
    QMenuBar,
    QMenu,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence

from nav2_config.node import Nav2ConfigNode
from nav2_config.core.node_discovery import NAV2_NODES
from nav2_config.gui.node_panel import NodePanel
from nav2_config.gui.param_panel import ParamPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level application window.

    Three-panel horizontal splitter:
      Left   (240px)  — node list (to be replaced by NodePanel)
      Center (stretch) — parameter editor (to be replaced by ParamPanel)
      Right  (300px)  — YAML preview (to be replaced by YamlPanel)

    All panels are collapsible by dragging the splitter handle to zero.
    """

    def __init__(self, node: Nav2ConfigNode) -> None:
        super().__init__()
        self._node = node
        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Assemble window chrome and three-panel layout."""
        self.setWindowTitle('Nav2 Config')
        self.setMinimumSize(1200, 700)

        self._setup_menu_bar()
        self._setup_central_splitter()
        self._setup_status_bar()

    def _setup_menu_bar(self) -> None:
        """Build File / Presets / Help menu bar."""
        bar: QMenuBar = self.menuBar()

        # ── File ────────────────────────────────────────────────────────
        file_menu: QMenu = bar.addMenu('File')

        import_action = QAction('Import YAML…', self)
        import_action.setShortcut(QKeySequence('Ctrl+O'))
        file_menu.addAction(import_action)

        export_action = QAction('Export YAML…', self)
        export_action.setShortcut(QKeySequence('Ctrl+S'))
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut(QKeySequence('Ctrl+Q'))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── Presets ──────────────────────────────────────────────────────
        presets_menu: QMenu = bar.addMenu('Presets')
        preset_names = [
            'Hospital Corridor',
            'Open Warehouse',
            'Outdoor Campus',
            'Simulation (TurtleBot3)',
            'Tight Retail',
        ]
        for name in preset_names:
            action = QAction(name, self)
            presets_menu.addAction(action)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu: QMenu = bar.addMenu('Help')
        about_action = QAction('About nav2_config', self)
        help_menu.addAction(about_action)

    def _setup_central_splitter(self) -> None:
        """Build horizontal QSplitter with three panels."""
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(True)
        splitter.setHandleWidth(2)

        self._node_panel = NodePanel()
        self._param_panel = ParamPanel()
        right = self._make_placeholder('YAML Preview', '#1e1e1e')

        splitter.addWidget(self._node_panel)
        splitter.addWidget(self._param_panel)
        splitter.addWidget(right)

        # setSizes is proportional — use 240 / big stretch / 300.
        splitter.setSizes([240, 10000, 300])

        self.setCentralWidget(splitter)
        self._splitter = splitter

    def _make_placeholder(self, label: str, bg: str) -> QWidget:
        """Return a styled placeholder widget for a not-yet-built panel."""
        widget = QWidget()
        widget.setObjectName('panel')
        widget.setStyleSheet(f'QWidget#panel {{ background: {bg}; border-right: 1px solid #3e3e42; }}')

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        title_bar = QWidget()
        title_bar.setFixedHeight(26)
        title_bar.setStyleSheet('background: #252526; border-bottom: 1px solid #3e3e42;')
        title_layout = QVBoxLayout(title_bar)
        title_layout.setContentsMargins(8, 0, 8, 0)

        title_label = QLabel(label.upper())
        title_label.setProperty('role', 'heading')
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        title_layout.addWidget(title_label)

        layout.addWidget(title_bar)
        layout.addStretch()

        return widget

    def _setup_status_bar(self) -> None:
        """Configure the bottom status bar."""
        status: QStatusBar = self.statusBar()
        status.showMessage('Disconnected — No Nav2 nodes found')
        self._status_bar = status

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        """Wire ROS2 signals → GUI slots and panel cross-signals."""
        # Discovery results → node panel display
        self._node.signals.nodes_discovered.connect(self._node_panel.update_nodes)

        # Discovery results → status bar
        self._node.signals.nodes_discovered.connect(self._on_nodes_discovered)

        # Node panel selection → fetch params → load into param panel
        self._node_panel.node_selected.connect(self._on_node_selected)

        # Refresh button → force immediate discovery pass
        self._node_panel.refresh_requested.connect(self._node.force_discover)

        # ROS2 params received → populate param panel
        self._node.signals.params_received.connect(self._on_params_received)

        # Param panel change → ROS2 set_parameters
        self._param_panel.param_change_requested.connect(self._on_param_change_requested)

        # ROS2 set result → param panel visual feedback
        self._node.signals.param_set_result.connect(self._on_param_set_result)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_nodes_discovered(self, status: dict[str, bool]) -> None:
        """Update status bar when discovery results arrive."""
        found = sum(1 for v in status.values() if v)
        total = len(NAV2_NODES)
        if found == 0:
            self.set_status(f'Disconnected — No Nav2 nodes found (0/{total})')
        else:
            self.set_status(f'Connected — {found}/{total} Nav2 nodes discovered')

    def _on_node_selected(self, node_path: str) -> None:
        """Request a parameter fetch for the selected node."""
        logger.info('Node selected: %s', node_path)
        self._param_panel.set_node_name(node_path)
        self._node.request_fetch_params(node_path)

    def _on_params_received(self, node_name: str, params: list) -> None:
        """Load fetched parameters into the param panel."""
        self._param_panel.load_params(params)
        self.set_status(
            f'Loaded {len(params)} parameters for {node_name.lstrip("/")}',
        )

    def _on_param_change_requested(
        self, node_name: str, param_name: str, value: object
    ) -> None:
        """Forward a param change from the GUI to the ROS2 node."""
        # Look up the schema type hint so the ROS2 client encodes correctly.
        type_hint = ''
        for row in self._param_panel._all_rows:
            if row._param_value.definition.param == param_name:
                type_hint = row._param_value.definition.type
                break
        self._node.request_set_param(node_name, param_name, value, type_hint)

    def _on_param_set_result(
        self, node_name: str, param_name: str, success: bool
    ) -> None:
        """Relay set-parameter result back to the param panel for visual feedback."""
        self._param_panel.update_param_result(param_name, success)
        if not success:
            self.set_status(
                f'Failed to set {node_name.lstrip("/")}/{param_name}'
            )

    # ------------------------------------------------------------------
    # Public helpers (called by GUI slots once real panels are added)
    # ------------------------------------------------------------------

    def set_status(self, message: str) -> None:
        """Update the status bar message."""
        self._status_bar.showMessage(message)
