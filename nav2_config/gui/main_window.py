"""Main window for nav2_config: three-panel splitter layout."""

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

#: Persisted window state path.
_CONFIG_PATH = Path.home() / '.config' / 'nav2_config' / 'settings.json'

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
        self._current_params: list[ParamValue] = []
        # Accumulate params from every node the user has selected so that
        # cross-node health checks (e.g. costmap vs controller) can fire.
        self._all_node_params: dict[str, list[ParamValue]] = {}
        # Saved panel sizes for Ctrl+1/2/3 toggle (index = splitter child).
        self._saved_panel_sizes: list[int] = [240, 10000, 300]
        self._build_ui()
        self._connect_signals()
        self._restore_window_state()

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
        import_action.setShortcut(QKeySequence('Ctrl+I'))
        import_action.triggered.connect(self._on_import)
        file_menu.addAction(import_action)

        export_action = QAction('Export YAML…', self)
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
        for i, label in enumerate(('Toggle Node Panel', 'Toggle Param Panel', 'Toggle YAML Panel'), 1):
            action = QAction(label, self)
            action.setShortcut(QKeySequence(f'Ctrl+{i}'))
            action.triggered.connect(lambda _checked, idx=i - 1: self._toggle_panel(idx))
            view_menu.addAction(action)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu: QMenu = bar.addMenu('Help')
        about_action = QAction('About nav2_config', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_central_splitter(self) -> None:
        """Build horizontal QSplitter with three panels.

        The center column is itself a vertical splitter containing the
        ParamPanel (top) and the HealthPanel (bottom).
        """
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(True)
        splitter.setHandleWidth(2)

        self._node_panel = NodePanel()
        self._param_panel = ParamPanel()
        self._health_panel = HealthPanel()
        self._yaml_panel = YamlPanel()

        # Vertical splitter for center column: params on top, health below.
        center_splitter = QSplitter(Qt.Orientation.Vertical)
        center_splitter.setHandleWidth(2)
        center_splitter.addWidget(self._param_panel)
        center_splitter.addWidget(self._health_panel)
        center_splitter.setSizes([10000, 180])

        splitter.addWidget(self._node_panel)
        splitter.addWidget(center_splitter)
        splitter.addWidget(self._yaml_panel)

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
        """Configure the bottom status bar with three sections.

        Left (permanent):  connection state + node / param counts.
        Center (message):  current node name / transient feedback.
        Right (permanent): last-set param result with success/fail colour.
        """
        status: QStatusBar = self.statusBar()

        # Left section — connection state.
        self._status_connection = QLabel('Disconnected')
        self._status_connection.setStyleSheet(
            'color: #f44336; padding: 0 8px; font-size: 11px;'
        )
        status.addWidget(self._status_connection)

        # Right section — last set-param result.
        self._status_last_set = QLabel('')
        self._status_last_set.setStyleSheet('color: #6d6d6d; padding: 0 8px; font-size: 11px;')
        status.addPermanentWidget(self._status_last_set)

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

        # Param panel change → ROS2 set_parameters + YAML update
        self._param_panel.param_change_requested.connect(self._on_param_change_requested)

        # ROS2 set result → param panel visual feedback
        self._node.signals.param_set_result.connect(self._on_param_set_result)

        # Health panel → scroll param panel to the clicked param
        self._health_panel.param_focus_requested.connect(self._param_panel.scroll_to_param)

        # External param changes (another tool changed a value)
        self._node.signals.params_externally_changed.connect(self._on_params_externally_changed)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_nodes_discovered(self, status: dict[str, bool]) -> None:
        """Update the left status label when discovery results arrive."""
        found = sum(1 for v in status.values() if v)
        total = len(NAV2_NODES)
        total_params = sum(len(p) for p in self._all_node_params.values())

        if found == 0:
            self._status_connection.setText(f'Disconnected  ·  0/{total} nodes')
            self._status_connection.setStyleSheet(
                'color: #f44336; padding: 0 8px; font-size: 11px;'
            )
        else:
            param_part = f'  ·  {total_params} params' if total_params else ''
            self._status_connection.setText(f'Connected  ·  {found}/{total} nodes{param_part}')
            self._status_connection.setStyleSheet(
                'color: #4caf50; padding: 0 8px; font-size: 11px;'
            )

        # Warn if the currently-edited node just went offline.
        current = self._param_panel._node_name
        if current:
            for path, running in status.items():
                if path == current and not running:
                    self.set_status(f'⚠  Node {current.lstrip("/")} went offline')
                    break

    def _on_node_selected(self, node_path: str) -> None:
        """Request a parameter fetch for the selected node and start polling."""
        logger.info('Node selected: %s', node_path)
        self._param_panel.set_node_name(node_path)
        self._yaml_panel.set_current_node(node_path)
        self._node.watch_node(node_path)
        self._node.request_fetch_params(node_path)
        bare = node_path.lstrip('/')
        self._status_bar.showMessage(f'Editing  {bare}')

    def _on_params_received(self, node_name: str, params: list) -> None:
        """Load fetched parameters into the param panel and refresh YAML preview."""
        self._current_params = params
        # Accumulate per-node params for cross-node health checks.
        bare = node_name.lstrip('/')
        self._all_node_params[bare] = params
        self._param_panel.load_params(params)
        self._yaml_panel.update_yaml(
            params, plugin_filter=self._param_panel._selected_plugin
        )
        self._status_bar.showMessage(f'Editing  {bare}  ·  {len(params)} params')

        # Refresh left label with updated param count.
        total_params = sum(len(p) for p in self._all_node_params.values())
        found_text = self._status_connection.text()
        # Replace param count suffix if present, else append.
        if '·' in found_text and 'params' in found_text:
            base = found_text.rsplit('·', 1)[0].rstrip()
            self._status_connection.setText(f'{base}  ·  {total_params} params')
        elif '·' in found_text:
            self._status_connection.setText(f'{found_text}  ·  {total_params} params')

        # Schedule debounced health check with all accumulated params.
        self._schedule_health_check()

    def _on_param_change_requested(
        self, node_name: str, param_name: str, value: object
    ) -> None:
        """Forward a param change from the GUI to the ROS2 node and refresh YAML."""
        # Look up the schema type hint so the ROS2 client encodes correctly.
        type_hint = ''
        for row in self._param_panel._all_rows:
            if row._param_value.definition.param == param_name:
                type_hint = row._param_value.definition.type
                break
        self._node.request_set_param(node_name, param_name, value, type_hint)
        # ParamValue.update() was already called by ParamRow — re-render YAML.
        self._yaml_panel.update_yaml(
            self._current_params, plugin_filter=self._param_panel._selected_plugin
        )
        # Re-schedule health check — fires 1 s after the last change.
        self._schedule_health_check()

    def _on_param_set_result(
        self, node_name: str, param_name: str, success: bool
    ) -> None:
        """Relay set-parameter result back to the param panel and right status."""
        self._param_panel.update_param_result(param_name, success)
        if success:
            # Find the new value from the current param list for display.
            val: object = '?'
            for pv in self._current_params:
                if pv.definition.param == param_name:
                    val = pv.live_value
                    break
            self._status_last_set.setText(f'Last set: {param_name} = {val}  ✓')
            self._status_last_set.setStyleSheet(
                'color: #4caf50; padding: 0 8px; font-size: 11px;'
            )
            logger.debug('Set %s/%s = %r', node_name, param_name, val)
        else:
            self._status_last_set.setText(f'Failed: {param_name}  ✗')
            self._status_last_set.setStyleSheet(
                'color: #f44336; padding: 0 8px; font-size: 11px;'
            )
            self.set_status(
                f'⚠  Failed to set {node_name.lstrip("/")}/{param_name}'
            )

    def _on_export(self) -> None:
        """Open the Export YAML dialog and save the current YAML preview."""
        yaml_str = self._yaml_panel._editor.toPlainText()
        ExportDialog.run(self, yaml_str)

    def _on_import(self) -> None:
        """Open the Import YAML dialog and apply the loaded parameters live."""
        ImportDialog.run(self, self._apply_imported_params)

    def _apply_imported_params(
        self, filepath: str, data: dict[str, dict[str, Any]]
    ) -> None:
        """Forward imported parameter values to running Nav2 nodes.

        For each (node, param, value) in the imported YAML, submits a
        request_set_param call on the ROS2 thread.  Type hints are resolved
        from the currently loaded param list; unknown params get best-effort
        type inference.

        Args:
            filepath: Path the YAML was imported from (used for status message).
            data: Parsed data from import_yaml: ``{node: {param: value}}``.
        """
        # Build a quick lookup from param name to schema type for the current node.
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

        self.set_status(
            f'Importing {total} parameters from {filepath.split("/")[-1]}…'
        )

    def _on_params_externally_changed(self, node_name: str, changed: list) -> None:
        """Handle externally-changed parameters detected by the poll watcher."""
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

    def _toggle_panel(self, index: int) -> None:
        """Collapse or expand splitter panel *index* (0=left, 1=center, 2=right)."""
        sizes = self._splitter.sizes()
        if sizes[index] > 0:
            self._saved_panel_sizes[index] = sizes[index]
            sizes[index] = 0
        else:
            sizes[index] = max(self._saved_panel_sizes[index], 100)
        self._splitter.setSizes(sizes)

    def _show_about(self) -> None:
        """Show the About nav2_config dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle('About nav2_config')
        dialog.setFixedSize(420, 260)
        dialog.setStyleSheet('QDialog { background: #2d2d2d; }')

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(8)

        title = QLabel('nav2_config  v0.1.0')
        title.setStyleSheet('color: #f57c00; font-size: 18px; font-weight: bold;')
        layout.addWidget(title)

        subtitle = QLabel('Real-time Nav2 parameter tuning')
        subtitle.setStyleSheet('color: #d4d4d4; font-size: 13px;')
        layout.addWidget(subtitle)

        layout.addSpacing(8)

        info = QTextBrowser()
        info.setOpenExternalLinks(True)
        info.setStyleSheet(
            'QTextBrowser { background: #1e1e1e; border: 1px solid #3e3e42; '
            'color: #d4d4d4; font-size: 12px; padding: 8px; }'
        )
        info.setHtml(
            '<p>Built by <b>Sutharsan</b><br>'
            'A ROS2 desktop GUI for live Nav2 parameter tuning — '
            'no node restarts required.</p>'
            '<p><a href="https://github.com/ros-navigation/navigation2" '
            'style="color:#4fc3f7;">Navigation2 on GitHub</a></p>'
        )
        info.setMaximumHeight(100)
        layout.addWidget(info)

        layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def _save_window_state(self) -> None:
        """Persist window geometry and splitter sizes to the config file."""
        try:
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            state = {
                'geometry': {
                    'x': self.x(),
                    'y': self.y(),
                    'width': self.width(),
                    'height': self.height(),
                },
                'splitter_sizes': self._splitter.sizes(),
            }
            _CONFIG_PATH.write_text(json.dumps(state, indent=2))
        except Exception:
            logger.warning('Failed to save window state', exc_info=True)

    def _restore_window_state(self) -> None:
        """Restore window geometry and splitter sizes from the config file."""
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
        """Save window state and stop the watcher before closing."""
        self._save_window_state()
        self._node.unwatch_node()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Health check scheduling
    # ------------------------------------------------------------------

    def _schedule_health_check(self) -> None:
        """Collect all accumulated params and schedule a debounced health check."""
        all_params: list[ParamValue] = []
        for params in self._all_node_params.values():
            all_params.extend(params)
        self._health_panel.schedule_check(all_params)

    # ------------------------------------------------------------------
    # Preset handling
    # ------------------------------------------------------------------

    def _open_preset_dialog(self, initial_preset: str | None = None) -> None:
        """Open the preset selection dialog."""
        dialog = PresetDialog(
            on_apply=self._apply_preset,
            initial_preset=initial_preset,
            parent=self,
        )
        dialog.exec()

    def _apply_preset(
        self, preset_name: str, preset_data: dict[str, dict]
    ) -> None:
        """Apply a loaded preset to the running Nav2 nodes."""
        count = apply_preset(self._node, preset_data, self._node._schema)
        display_name = PRESET_META.get(preset_name, {}).get('name', preset_name)
        self.set_status(
            f'Applying preset "{display_name}" — {count} parameter updates queued'
        )
        logger.info('Applied preset %r: %d params queued', preset_name, count)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_status(self, message: str, timeout_ms: int = 5000) -> None:
        """Update the center status bar message.

        Args:
            message: Text to display in the center section.
            timeout_ms: Auto-clear after this many ms (0 = permanent).
        """
        self._status_bar.showMessage(message, timeout_ms)
