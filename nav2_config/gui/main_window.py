"""Main window for nav2_config: three-panel splitter layout.

Styled to match RViz2: light gray Qt Fusion theme, QToolBar with
flat icon buttons, full menu bar, 22px status bar.
"""

import json
import logging
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.node_discovery import NAV2_NODES
from nav2_config.core.presets import PRESET_META, PRESET_ORDER, apply_preset
from nav2_config.gui.health_panel import HealthPanel
from nav2_config.gui.import_export import ExportDialog, ImportDialog
from nav2_config.gui.node_panel import NodePanel
from nav2_config.gui.param_panel import ParamPanel
from nav2_config.gui.preset_dialog import PresetDialog
from nav2_config.gui.yaml_panel import YamlPanel
from nav2_config.node import Nav2ConfigNode
from nav2_config.types.params import ParamValue

_CONFIG_PATH = Path.home() / '.config' / 'nav2_config' / 'settings.json'

# RViz2 light palette for inline stylesheet strings
_BG_HDR   = '#d0d0d0'
_BG_PANEL = '#e8e8e8'
_BORDER   = '#c0c0c0'
_FG       = '#1a1a1a'
_FG_DIM   = '#666666'
_BLUE     = '#3399ff'
_GREEN    = '#4caf50'
_RED      = '#e53935'

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level application window.

    Three-panel horizontal splitter:
      Left   (240px)  — Nav2 node list
      Center (stretch) — parameter editor + health check
      Right  (300px)  — YAML preview
    """

    def __init__(self, node: Nav2ConfigNode) -> None:
        super().__init__()
        self._node = node
        self._current_params: list[ParamValue] = []
        self._all_node_params: dict[str, list[ParamValue]] = {}
        self._saved_panel_sizes: list[int] = [240, 10000, 300]
        self._build_ui()
        self._connect_signals()
        self._restore_window_state()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.setWindowTitle('nav2_config')
        self.setMinimumSize(1200, 700)
        # Fusion handles the main window background via the palette.

        self._setup_menu_bar()
        self._setup_toolbar()
        self._setup_central_splitter()
        self._setup_status_bar()

    def _setup_menu_bar(self) -> None:
        bar: QMenuBar = self.menuBar()

        # ── File ────────────────────────────────────────────────────────
        file_menu: QMenu = bar.addMenu('File')

        import_action = QAction('Import YAML...', self)
        import_action.setShortcut(QKeySequence('Ctrl+I'))
        import_action.triggered.connect(self._on_import)
        file_menu.addAction(import_action)

        export_action = QAction('Export YAML...', self)
        export_action.setShortcut(QKeySequence('Ctrl+S'))
        export_action.triggered.connect(self._on_export)
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        refresh_action = QAction('Refresh Nodes', self)
        refresh_action.setShortcut(QKeySequence('Ctrl+R'))
        refresh_action.triggered.connect(self._node.force_discover)
        file_menu.addAction(refresh_action)

        file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut(QKeySequence('Ctrl+Q'))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # ── Edit ─────────────────────────────────────────────────────────
        edit_menu: QMenu = bar.addMenu('Edit')

        undo_action = QAction('Undo Param Change', self)
        undo_action.setShortcut(QKeySequence('Ctrl+Z'))
        undo_action.setEnabled(False)
        edit_menu.addAction(undo_action)

        redo_action = QAction('Redo', self)
        redo_action.setShortcut(QKeySequence('Ctrl+Y'))
        redo_action.setEnabled(False)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        reset_action = QAction('Reset to Defaults', self)
        reset_action.setEnabled(False)
        edit_menu.addAction(reset_action)

        # ── Presets ──────────────────────────────────────────────────────
        presets_menu: QMenu = bar.addMenu('Presets')
        for key in PRESET_ORDER:
            meta = PRESET_META.get(key, {})
            display_name = meta.get('name', key)
            action = QAction(display_name, self)
            action.triggered.connect(
                lambda _checked, k=key: self._open_preset_dialog(k)
            )
            presets_menu.addAction(action)

        # ── View ─────────────────────────────────────────────────────────
        view_menu: QMenu = bar.addMenu('View')

        toggle_node_action = QAction('Toggle Node Panel', self)
        toggle_node_action.setShortcut(QKeySequence('Ctrl+1'))
        toggle_node_action.triggered.connect(lambda: self._toggle_panel(0))
        view_menu.addAction(toggle_node_action)

        toggle_param_action = QAction('Toggle Param Panel', self)
        toggle_param_action.setShortcut(QKeySequence('Ctrl+2'))
        toggle_param_action.triggered.connect(lambda: self._toggle_panel(1))
        view_menu.addAction(toggle_param_action)

        toggle_yaml_action = QAction('Toggle YAML Panel', self)
        toggle_yaml_action.setShortcut(QKeySequence('Ctrl+3'))
        toggle_yaml_action.triggered.connect(lambda: self._toggle_panel(2))
        view_menu.addAction(toggle_yaml_action)

        view_menu.addSeparator()

        self._toggle_desc_action = QAction('Show Descriptions', self)
        self._toggle_desc_action.setCheckable(True)
        self._toggle_desc_action.setChecked(True)
        self._toggle_desc_action.setShortcut(QKeySequence('Ctrl+D'))
        self._toggle_desc_action.triggered.connect(self._on_toggle_descriptions)
        view_menu.addAction(self._toggle_desc_action)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu: QMenu = bar.addMenu('Help')

        shortcuts_action = QAction('Keyboard Shortcuts', self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction('About nav2_config', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        """Build the RViz2-style flat toolbar."""
        tb: QToolBar = self.addToolBar('Main')
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setObjectName('mainToolBar')

        def _add_action(label: str, tooltip: str) -> QAction:
            action = QAction(label, self)
            action.setToolTip(tooltip)
            tb.addAction(action)
            return action

        self._tb_import = _add_action('Import', 'Import YAML parameters  (Ctrl+I)')
        self._tb_import.triggered.connect(self._on_import)

        self._tb_export = _add_action('Export', 'Export YAML parameters  (Ctrl+S)')
        self._tb_export.triggered.connect(self._on_export)

        tb.addSeparator()

        self._tb_refresh = _add_action('Refresh', 'Refresh node discovery  (Ctrl+R)')
        self._tb_refresh.triggered.connect(self._node.force_discover)

        tb.addSeparator()

        self._tb_presets = _add_action('Presets', 'Apply environment preset')
        self._tb_presets.triggered.connect(lambda: self._open_preset_dialog(None))

        tb.addSeparator()

        self._tb_health = _add_action('Health Check', 'Run health check now')
        self._tb_health.triggered.connect(self._run_health_now)

        self._toolbar = tb

    def _setup_central_splitter(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(True)
        splitter.setHandleWidth(1)

        self._node_panel = NodePanel()
        self._param_panel = ParamPanel(
            topic_discovery=self._node.topic_discovery,
            frame_discovery=self._node.frame_discovery,
        )
        self._health_panel = HealthPanel()
        self._yaml_panel = YamlPanel()

        center_splitter = QSplitter(Qt.Orientation.Vertical)
        center_splitter.setHandleWidth(1)
        center_splitter.addWidget(self._param_panel)
        center_splitter.addWidget(self._health_panel)
        center_splitter.setSizes([10000, 160])

        splitter.addWidget(self._node_panel)
        splitter.addWidget(center_splitter)
        splitter.addWidget(self._yaml_panel)
        splitter.setSizes([240, 10000, 300])

        self.setCentralWidget(splitter)
        self._splitter = splitter

    def _setup_status_bar(self) -> None:
        """Configure the 22px status bar with left / center / right sections."""
        status: QStatusBar = self.statusBar()
        status.setFixedHeight(22)

        self._status_connection = QLabel('Disconnected')
        self._status_connection.setStyleSheet(
            f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
        )
        status.addWidget(self._status_connection)

        self._status_last_set = QLabel('')
        self._status_last_set.setStyleSheet(
            f'color: {_FG_DIM}; padding: 0 8px; font-size: 9pt;'
        )
        status.addPermanentWidget(self._status_last_set)

        self._last_set_timer = QTimer(self)
        self._last_set_timer.setSingleShot(True)
        self._last_set_timer.timeout.connect(
            lambda: self._status_last_set.setText('')
        )

        self._status_bar = status

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._node.signals.nodes_discovered.connect(self._node_panel.update_nodes)
        self._node.signals.nodes_discovered.connect(self._on_nodes_discovered)
        self._node_panel.node_selected.connect(self._on_node_selected)
        self._node_panel.refresh_requested.connect(self._node.force_discover)
        self._node.signals.params_received.connect(self._on_params_received)
        # param_change_requested: user edited a value — update YAML preview only
        self._param_panel.param_change_requested.connect(self._on_param_change_requested)
        # param_set_requested: user clicked Set — send to ROS2 node
        self._param_panel.param_set_requested.connect(self._on_param_set_requested)
        self._node.signals.param_set_result.connect(self._on_param_set_result)
        self._health_panel.param_focus_requested.connect(
            self._param_panel.scroll_to_param
        )
        self._node.signals.params_externally_changed.connect(
            self._on_params_externally_changed
        )
        self._node.signals.discovery_refreshed.connect(
            self._param_panel.refresh_dropdowns
        )
        self._node_panel.import_btn.clicked.connect(self._on_import)
        self._node_panel.export_btn.clicked.connect(self._on_export)
        self._node_panel.presets_btn.clicked.connect(
            lambda: self._open_preset_dialog(None)
        )

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_nodes_discovered(self, status: dict[str, bool]) -> None:
        found = sum(1 for v in status.values() if v)
        total = len(NAV2_NODES)
        total_params = sum(len(p) for p in self._all_node_params.values())

        if found == 0:
            self._status_connection.setText(f'Disconnected  |  0/{total} nodes')
            self._status_connection.setStyleSheet(
                f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
            )
        else:
            param_part = f'  |  {total_params} params' if total_params else ''
            self._status_connection.setText(
                f'Connected  |  {found}/{total} nodes{param_part}'
            )
            self._status_connection.setStyleSheet(
                f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
            )

        current = self._param_panel._node_name
        if current:
            for path, running in status.items():
                if path == current and not running:
                    self.set_status(f'Node {current.lstrip("/")} went offline')
                    break

    def _on_node_selected(self, node_path: str) -> None:
        logger.info('Node selected: %s', node_path)
        self._param_panel.set_node_name(node_path)
        self._yaml_panel.set_current_node(node_path)
        self._node.watch_node(node_path)
        self._node.request_fetch_params(node_path)
        self._status_bar.showMessage(node_path.lstrip('/'))

    def _on_params_received(self, node_name: str, params: list) -> None:
        self._current_params = params
        bare = node_name.lstrip('/')
        self._all_node_params[bare] = params
        self._param_panel.load_params(params)
        self._yaml_panel.update_yaml(
            params,
            plugin_filter=self._param_panel._selected_plugin,
            pending_params=set(),
        )
        modified = sum(1 for p in params if p.is_modified)
        mod_part = f'  |  {modified} modified' if modified else ''
        self._status_bar.showMessage(f'{bare}  |  {len(params)} params{mod_part}')

        total_params = sum(len(p) for p in self._all_node_params.values())
        found_text = self._status_connection.text()
        if '|' in found_text and 'params' in found_text:
            base = found_text.rsplit('|', 1)[0].rstrip()
            self._status_connection.setText(f'{base}  |  {total_params} params')
        elif '|' in found_text:
            self._status_connection.setText(f'{found_text}  |  {total_params} params')

        self._schedule_health_check()

    def _on_param_change_requested(
        self, node_name: str, param_name: str, value: object
    ) -> None:
        """User edited a value in the GUI — update YAML preview only.

        Does NOT call ros2 param set.  The explicit Set button or Set All
        action triggers :meth:`_on_param_set_requested` for that.
        """
        self._yaml_panel.update_yaml(
            self._current_params,
            plugin_filter=self._param_panel._selected_plugin,
            pending_params=self._param_panel.pending_param_names(),
        )
        self._schedule_health_check()

    def _on_param_set_requested(
        self, node_name: str, param_name: str, value: object
    ) -> None:
        """User clicked Set (or Set All) — send the value to the ROS2 node."""
        type_hint = ''
        for row in self._param_panel._all_rows:
            if row._param_value.definition.param == param_name:
                type_hint = row._param_value.definition.type
                break
        self._node.request_set_param(node_name, param_name, value, type_hint)

    def _on_param_set_result(
        self, node_name: str, param_name: str, success: bool
    ) -> None:
        # Route result to the matching row's Set button (updates confirmed_value).
        self._param_panel.update_set_result(param_name, success)

        # Refresh YAML with updated pending state.
        self._yaml_panel.update_yaml(
            self._current_params,
            plugin_filter=self._param_panel._selected_plugin,
            pending_params=self._param_panel.pending_param_names(),
        )

        if success:
            val: object = '?'
            for pv in self._current_params:
                if pv.definition.param == param_name:
                    val = pv.live_value  # confirmed_value after update_set_result
                    break
            self._status_last_set.setText(f'✓ {param_name} → {val}')
            self._status_last_set.setStyleSheet(
                f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
            )
            logger.debug('Set %s/%s = %r', node_name, param_name, val)
        else:
            self._status_last_set.setText(f'✗ {param_name} — failed')
            self._status_last_set.setStyleSheet(
                f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
            )
            self.set_status(
                f'Failed to set {node_name.lstrip("/")}/{param_name}'
            )
        self._last_set_timer.start(5000)

    def _on_export(self) -> None:
        yaml_str = self._yaml_panel._editor.toPlainText()
        ExportDialog.run(self, yaml_str)

    def _on_import(self) -> None:
        ImportDialog.run(self, self._apply_imported_params)

    def _apply_imported_params(
        self, filepath: str, data: dict[str, dict[str, Any]]
    ) -> None:
        type_map: dict[str, str] = {
            pv.definition.param: pv.definition.type
            for pv in self._current_params
        }
        total = 0
        for node_name, params in data.items():
            full_node = node_name if node_name.startswith('/') else f'/{node_name}'
            for param_name, value in params.items():
                type_hint = type_map.get(param_name, '')
                self._node.request_set_param(full_node, param_name, value, type_hint)
                total += 1
        self.set_status(f'Importing {total} parameters from {Path(filepath).name}')

    def _on_params_externally_changed(self, node_name: str, changed: list) -> None:
        for param_name, _new_value in changed:
            self._param_panel.highlight_external_change(param_name)
        if len(changed) == 1:
            name, val = changed[0]
            self.set_status(f'External change: {name} = {val}')
        else:
            self.set_status(
                f'{len(changed)} params changed externally on {node_name.lstrip("/")}'
            )
        logger.info('External changes on %s: %s', node_name, changed)

    def _on_toggle_descriptions(self, checked: bool) -> None:
        """Sync View > Show Descriptions with the param panel Desc toggle."""
        self._param_panel._desc_btn.setChecked(checked)

    def _toggle_panel(self, index: int) -> None:
        sizes = self._splitter.sizes()
        if sizes[index] > 0:
            self._saved_panel_sizes[index] = sizes[index]
            sizes[index] = 0
        else:
            sizes[index] = max(self._saved_panel_sizes[index], 100)
        self._splitter.setSizes(sizes)

    def _run_health_now(self) -> None:
        all_params: list[ParamValue] = []
        for params in self._all_node_params.values():
            all_params.extend(params)
        self._health_panel.run_checks_now(all_params)
        self.set_status('Health check complete.')

    def _show_shortcuts(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle('Keyboard Shortcuts')
        dialog.setFixedSize(400, 300)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(6)

        title = QLabel('Keyboard Shortcuts')
        title.setStyleSheet('font-size: 11pt; font-weight: bold;')
        layout.addWidget(title)

        shortcuts = QTextBrowser()
        shortcuts.setStyleSheet('font-size: 9pt; padding: 6px;')
        shortcuts.setHtml(
            '<table cellspacing="4">'
            '<tr><td><b>Ctrl+K</b></td><td>Focus param search</td></tr>'
            '<tr><td><b>Ctrl+I</b></td><td>Import YAML</td></tr>'
            '<tr><td><b>Ctrl+S</b></td><td>Export YAML</td></tr>'
            '<tr><td><b>Ctrl+R</b></td><td>Refresh node discovery</td></tr>'
            '<tr><td><b>Ctrl+D</b></td><td>Toggle descriptions</td></tr>'
            '<tr><td><b>Ctrl+1</b></td><td>Toggle Node panel</td></tr>'
            '<tr><td><b>Ctrl+2</b></td><td>Toggle Param panel</td></tr>'
            '<tr><td><b>Ctrl+3</b></td><td>Toggle YAML panel</td></tr>'
            '<tr><td><b>Ctrl+Q</b></td><td>Quit</td></tr>'
            '<tr><td><b>Escape</b></td><td>Clear search</td></tr>'
            '</table>'
        )
        layout.addWidget(shortcuts)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle('About nav2_config')
        dialog.setFixedSize(400, 220)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(8)

        title = QLabel('nav2_config  v0.1.0')
        title.setStyleSheet('font-size: 14pt; font-weight: bold;')
        layout.addWidget(title)

        subtitle = QLabel('Real-time Nav2 parameter tuning')
        subtitle.setStyleSheet(f'color: {_FG_DIM}; font-size: 10pt;')
        layout.addWidget(subtitle)

        layout.addSpacing(4)

        info = QTextBrowser()
        info.setOpenExternalLinks(True)
        info.setStyleSheet('font-size: 9pt; padding: 6px;')
        info.setHtml(
            '<p>Built by <b>Sutharsan</b><br>'
            'A ROS2 desktop GUI for live Nav2 parameter tuning. '
            'No node restarts required.</p>'
        )
        info.setMaximumHeight(72)
        layout.addWidget(info)
        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def _save_window_state(self) -> None:
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            state = {
                'geometry': {
                    'x': self.x(), 'y': self.y(),
                    'width': self.width(), 'height': self.height(),
                },
                'splitter_sizes': self._splitter.sizes(),
            }
            _CONFIG_PATH.write_text(json.dumps(state, indent=2))
        except Exception:
            logger.warning('Failed to save window state', exc_info=True)

    def _restore_window_state(self) -> None:
        if not _CONFIG_PATH.exists():
            return
        try:
            state = json.loads(_CONFIG_PATH.read_text())
            if 'geometry' in state:
                g = state['geometry']
                self.setGeometry(g['x'], g['y'], g['width'], g['height'])
            if 'splitter_sizes' in state:
                self._splitter.setSizes(state['splitter_sizes'])
        except Exception:
            logger.warning('Failed to restore window state', exc_info=True)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        self._save_window_state()
        self._node.unwatch_node()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Health check scheduling
    # ------------------------------------------------------------------

    def _schedule_health_check(self) -> None:
        all_params: list[ParamValue] = []
        for params in self._all_node_params.values():
            all_params.extend(params)
        self._health_panel.schedule_check(all_params)

    # ------------------------------------------------------------------
    # Preset handling
    # ------------------------------------------------------------------

    def _open_preset_dialog(self, initial_preset: str | None = None) -> None:
        dialog = PresetDialog(
            on_apply=self._apply_preset,
            initial_preset=initial_preset,
            parent=self,
        )
        dialog.exec()

    def _apply_preset(self, preset_name: str, preset_data: dict[str, dict]) -> None:
        count = apply_preset(self._node, preset_data, self._node._schema)
        display_name = PRESET_META.get(preset_name, {}).get('name', preset_name)
        self.set_status(
            f'Applying preset "{display_name}" ({count} parameter updates queued)'
        )
        logger.info('Applied preset %r: %d params queued', preset_name, count)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_status(self, message: str, timeout_ms: int = 5000) -> None:
        """Update the center status bar message.

        Args:
            message: Text to display.
            timeout_ms: Auto-clear after this many ms (0 = permanent).
        """
        self._status_bar.showMessage(message, timeout_ms)
