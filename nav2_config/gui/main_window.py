"""Main window for nav2_config: three-panel splitter layout.

Styled to match RViz2: light gray Qt Fusion theme, QToolBar with
flat icon buttons, full menu bar, 22px status bar.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nav2_config.core.config_file import ConfigFile

from lifecycle_msgs.msg import Transition
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
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


def _load_settings() -> dict:
    """Load persistent settings from *_CONFIG_PATH*; return {} on error."""
    try:
        return json.loads(_CONFIG_PATH.read_text())
    except Exception:
        return {}


def _save_settings_partial(updates: dict) -> None:
    """Merge *updates* into the persisted settings dict."""
    try:
        settings = _load_settings()
        settings.update(updates)
        _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CONFIG_PATH.write_text(json.dumps(settings, indent=2))
    except Exception:
        logger.warning('Failed to save settings', exc_info=True)

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


class _RestartNotificationBar(QWidget):
    """Amber banner shown when a non-hot-reload param is changed.

    Offers "Restart Now" and "Later" actions.
    """

    restart_requested = pyqtSignal_type = None  # filled below

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._node_name = ''
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            'QWidget { background: #fff8e1; border-bottom: 1px solid #ffc107; }'
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        self._icon = QLabel('⚠')
        self._icon.setStyleSheet('font-size: 12pt; color: #f57c00;')
        layout.addWidget(self._icon)

        self._message = QLabel('')
        self._message.setStyleSheet('color: #333; font-size: 9pt;')
        layout.addWidget(self._message)
        layout.addStretch()

        self._restart_btn = QPushButton('Restart Now')
        self._restart_btn.setFixedHeight(22)
        self._restart_btn.setStyleSheet(
            'QPushButton { background: #f57c00; border: 1px solid #e65100; '
            'color: white; font-size: 9pt; padding: 0 10px; }'
            'QPushButton:hover { background: #e65100; }'
        )
        layout.addWidget(self._restart_btn)

        later_btn = QPushButton('Later')
        later_btn.setFixedHeight(22)
        later_btn.setStyleSheet(
            'QPushButton { background: transparent; border: 1px solid #bbb; '
            'color: #555; font-size: 9pt; padding: 0 8px; }'
            'QPushButton:hover { background: #ffe0b2; }'
        )
        later_btn.clicked.connect(self.setVisible)
        later_btn.clicked.connect(lambda: self.setVisible(False))
        layout.addWidget(later_btn)

        # Store the Restart Now button so the caller can connect its signal
        self._restart_btn.clicked.connect(lambda: self.setVisible(False))

    def show_for(
        self,
        node_name: str,
        param_name: str,
        on_restart: 'Callable[[], None]',
        stack_restart: bool = False,
    ) -> None:
        """Display the bar for a specific param change.

        Args:
            node_name: Full ROS2 node path.
            param_name: The parameter that changed.
            on_restart: Called when the user clicks the restart button.
            stack_restart: When ``True``, the button says "Restart Nav2 Stack"
                and the message references the full stack (for use when
                lifecycle_manager is running).
        """
        self._node_name = node_name
        bare = node_name.lstrip('/')
        if stack_restart:
            self._message.setText(
                f'{param_name} changed. This requires restarting the Nav2 stack to take effect.'
            )
        else:
            self._message.setText(
                f'{param_name} requires a node restart to take effect.'
            )
        # Disconnect any previous restart handler and connect the new one.
        try:
            self._restart_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._restart_btn.clicked.connect(lambda: self.setVisible(False))
        self._restart_btn.clicked.connect(on_restart)
        self._restart_btn.setText('Restart Nav2 Stack' if stack_restart else f'Restart {bare} Now')
        self.setVisible(True)


class _RestartAllProgressDialog(QDialog):
    """Modal progress dialog for the Restart Nav2 Stack operation.

    Receives ``lifecycle_progress`` and ``lifecycle_change_result`` signals
    and updates its log text area in real time.
    """

    def __init__(self, node_count: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expected = node_count
        self._done_count = 0
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle('Restarting Nav2 Stack...')
        self.setMinimumSize(460, 300)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        header = QLabel('Restarting Nav2 nodes in lifecycle order...')
        header.setStyleSheet('font-size: 10pt; font-weight: bold;')
        layout.addWidget(header)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            'QPlainTextEdit { background: #1e1e1e; color: #d4d4d4; '
            'font-family: monospace; font-size: 9pt; border: none; }'
        )
        layout.addWidget(self._log)

        self._status_label = QLabel('In progress...')
        self._status_label.setStyleSheet('color: #666; font-size: 9pt;')
        layout.addWidget(self._status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setEnabled(False)
        buttons.rejected.connect(self.reject)
        self._close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(buttons)

    def on_progress(self, node_path: str, step: str) -> None:
        """Called when a lifecycle_progress signal arrives."""
        bare = node_path.lstrip('/') if node_path else '...'
        self._log.appendPlainText(f'  {bare}: {step}...')

    def on_result(self, node_path: str, success: bool, message: str) -> None:
        """Called when a lifecycle_change_result signal arrives."""
        bare = node_path.lstrip('/')
        icon = '✓' if success else '✗'
        self._log.appendPlainText(f'{icon} {bare}: {message}')
        self._done_count += 1
        if self._done_count >= self._expected:
            self._finish()

    def mark_done_early(self) -> None:
        """Force completion if node_count was zero."""
        self._finish()

    def _finish(self) -> None:
        self._status_label.setText('Done.')
        self._status_label.setStyleSheet('color: #4caf50; font-size: 9pt; font-weight: bold;')
        self._close_btn.setEnabled(True)


# Need to import Callable for type hints in the notification bar
from typing import Callable  # noqa: E402  (after class definition is fine here)


class MainWindow(QMainWindow):
    """Top-level application window.

    Three-panel horizontal splitter:
      Left   (240px)  — Nav2 node list
      Center (stretch) — parameter editor + health check
      Right  (300px)  — YAML preview
    """

    def __init__(
        self,
        node: Nav2ConfigNode,
        config_file: 'ConfigFile | None' = None,
    ) -> None:
        super().__init__()
        self._node = node
        self._config_file: 'ConfigFile | None' = config_file
        self._dirty: bool = False
        self._current_params: list[ParamValue] = []
        self._all_node_params: dict[str, list[ParamValue]] = {}
        self._saved_panel_sizes: list[int] = [240, 10000, 300]
        self._lifecycle_manager_present: bool = False
        self._build_ui()
        self._connect_signals()
        self._restore_window_state()
        # Apply initial config file state after UI is built
        if self._config_file:
            self._update_title()
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=False
            )
            self._update_recent_files_menu()

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
        self._file_menu: QMenu = bar.addMenu('File')

        load_action = QAction('Load Config...', self)
        load_action.setShortcut(QKeySequence('Ctrl+O'))
        load_action.triggered.connect(self._on_load_config)
        self._file_menu.addAction(load_action)

        self._file_menu.addSeparator()

        self._save_action = QAction('Save', self)
        self._save_action.setShortcut(QKeySequence('Ctrl+S'))
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._on_save)
        self._file_menu.addAction(self._save_action)

        self._save_as_action = QAction('Save As...', self)
        self._save_as_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self._save_as_action.setEnabled(False)
        self._save_as_action.triggered.connect(self._on_save_as)
        self._file_menu.addAction(self._save_as_action)

        self._file_menu.addSeparator()

        export_live_action = QAction('Export Current Live Params...', self)
        export_live_action.setShortcut(QKeySequence('Ctrl+E'))
        export_live_action.triggered.connect(self._on_export)
        self._file_menu.addAction(export_live_action)

        import_action = QAction('Import YAML...', self)
        import_action.setShortcut(QKeySequence('Ctrl+I'))
        import_action.triggered.connect(self._on_import)
        self._file_menu.addAction(import_action)

        self._file_menu.addSeparator()

        # Recent files placeholder — populated by _update_recent_files_menu()
        self._recent_files_sep = self._file_menu.addSeparator()
        self._recent_actions: list[QAction] = []

        refresh_action = QAction('Refresh Nodes', self)
        refresh_action.setShortcut(QKeySequence('Ctrl+R'))
        refresh_action.triggered.connect(self._node.force_discover)
        self._file_menu.addAction(refresh_action)

        self._file_menu.addSeparator()

        quit_action = QAction('Quit', self)
        quit_action.setShortcut(QKeySequence('Ctrl+Q'))
        quit_action.triggered.connect(self.close)
        self._file_menu.addAction(quit_action)

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

        tb.addSeparator()

        self._tb_restart_all = _add_action(
            'Restart Nav2 Stack',
            'Restart all Nav2 nodes in lifecycle order',
        )
        self._tb_restart_all.triggered.connect(self._on_restart_all_nav2)

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

        # Wrap splitter in a container so the notification bar can sit above it.
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        self._notification_bar = _RestartNotificationBar()
        container_layout.addWidget(self._notification_bar)
        container_layout.addWidget(splitter)

        self.setCentralWidget(container)
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
        # Lifecycle signals
        self._node.signals.lifecycle_states_updated.connect(
            self._node_panel.update_lifecycle_states
        )
        self._node.signals.lifecycle_change_result.connect(
            self._on_lifecycle_change_result
        )
        self._node_panel.lifecycle_action_requested.connect(
            self._on_lifecycle_action_requested
        )
        self._node.signals.lifecycle_manager_status.connect(
            self._on_lifecycle_manager_status
        )
        self._yaml_panel.save_requested.connect(self._on_save)

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
        # Overlay file values from the config file so rows can show file-vs-live
        if self._config_file:
            for pv in params:
                fv = self._config_file.get_value(node_name, pv.definition.ros2_name)
                pv.file_value = fv

        self._current_params = params
        bare = node_name.lstrip('/')
        self._all_node_params[bare] = params
        self._node_panel.set_param_count(node_name, len(params))
        self._param_panel.load_params(params)

        # YAML panel: show file content in file mode, generated YAML otherwise
        if self._config_file:
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=self._dirty
            )
        else:
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
        """User edited a value in the GUI -- update YAML preview only.

        Does NOT call ros2 param set.  The explicit Set button or Set All
        action triggers _on_param_set_requested for that.
        """
        if not self._config_file:
            self._yaml_panel.update_yaml(
                self._current_params,
                plugin_filter=self._param_panel._selected_plugin,
                pending_params=self._param_panel.pending_param_names(),
            )
        self._schedule_health_check()

    def _on_param_set_requested(
        self, node_name: str, param_name: str, value: object
    ) -> None:
        """User clicked Set (or Set All).

        For hot-reload params: updates the config file AND fires ros2 param set
        for immediate live effect.
        For non-hot-reload params: updates the config file only and marks the
        row with the amber SAVED_FILE state; a restart is needed to apply.
        """
        type_hint = ''
        hot_reload = True
        ros2_name = param_name
        for row in self._param_panel._all_rows:
            if row._param_value.definition.param == param_name:
                type_hint = row._param_value.definition.type
                hot_reload = row._param_value.definition.hot_reload
                ros2_name = row._param_value.definition.ros2_name
                break

        # Always update the config file in-memory when one is loaded
        if self._config_file:
            self._config_file.set_value(node_name, ros2_name, value)
            self._mark_dirty()

        if hot_reload:
            # Immediate live effect via ROS2 service
            self._node.request_set_param(node_name, param_name, value, type_hint)
        else:
            # Config-file-only: value will apply after next Nav2 restart
            self._param_panel.mark_param_file_saved(param_name)
            self._node_panel.set_node_restart_pending(node_name, True)
            self._notification_bar.show_for(
                node_name,
                param_name,
                on_restart=lambda checked=False, n=node_name: self._do_restart_node(n),
                stack_restart=self._lifecycle_manager_present,
            )
            self.set_status(f'Saved {param_name} to config -- restart Nav2 to apply')

    def _on_param_set_result(
        self, node_name: str, param_name: str, success: bool
    ) -> None:
        # Route result to the matching row's Set button (updates confirmed_value).
        self._param_panel.update_set_result(param_name, success)

        # Refresh YAML panel
        if self._config_file:
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=self._dirty
            )
        else:
            self._yaml_panel.update_yaml(
                self._current_params,
                plugin_filter=self._param_panel._selected_plugin,
                pending_params=self._param_panel.pending_param_names(),
            )

        if success:
            val: object = '?'
            needs_restart = False
            for pv in self._current_params:
                if pv.definition.param == param_name:
                    val = pv.live_value  # confirmed_value after update_set_result
                    needs_restart = not pv.definition.hot_reload
                    break
            self._status_last_set.setText(f'\u2713 {param_name} \u2192 {val}')
            self._status_last_set.setStyleSheet(
                f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
            )
            logger.debug('Set %s/%s = %r', node_name, param_name, val)

            # Non-hot-reload notification: only when no config file is loaded
            # (with a config file, _on_param_set_requested already handled this)
            if needs_restart and not self._config_file:
                self._node_panel.set_node_restart_pending(node_name, True)
                self._notification_bar.show_for(
                    node_name,
                    param_name,
                    on_restart=lambda checked=False, n=node_name: self._do_restart_node(n),
                    stack_restart=self._lifecycle_manager_present,
                )
        else:
            self._status_last_set.setText(f'\u2717 {param_name} -- failed')
            self._status_last_set.setStyleSheet(
                f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
            )
            self.set_status(
                f'Failed to set {node_name.lstrip("/")}/{param_name}'
            )
        self._last_set_timer.start(5000)

    # ------------------------------------------------------------------
    # Config file management
    # ------------------------------------------------------------------

    def _mark_dirty(self) -> None:
        """Mark the config file as having unsaved changes."""
        if not self._dirty:
            self._dirty = True
            self._update_title()
            self._save_action.setEnabled(True)
            self._yaml_panel.set_save_button_dirty(True)

    def _update_title(self) -> None:
        """Refresh the window title to reflect config file path and dirty state."""
        if self._config_file:
            dirty_marker = ' *' if self._dirty else ''
            self.setWindowTitle(
                f'nav2_config -- {self._config_file.filepath}{dirty_marker}'
            )
            self._save_action.setEnabled(True)
            self._save_as_action.setEnabled(True)
        else:
            self.setWindowTitle('nav2_config')
            self._save_action.setEnabled(False)
            self._save_as_action.setEnabled(False)

    def _on_load_config(self) -> None:
        """File > Load Config: prompt for save if dirty, then show the load dialog."""
        if self._dirty:
            reply = QMessageBox.question(
                self,
                'Unsaved Changes',
                'You have unsaved changes. Save before loading a new config?',
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()

        from nav2_config.gui.load_dialog import LoadConfigDialog
        settings = _load_settings()
        recent_files: list[str] = settings.get('recent_files', [])
        dialog = LoadConfigDialog(recent_files=recent_files, parent=self)
        # Use open() (non-blocking) + finished signal instead of exec()
        dialog.finished.connect(
            lambda result, d=dialog: self._load_config_from_dialog(d, result)
        )
        dialog.open()

    def _load_config_from_dialog(self, dialog: 'object', result: int) -> None:
        """Callback after the load dialog closes; loads the chosen file."""
        if not result:
            return
        filepath: str = dialog.selected_filepath()  # type: ignore[attr-defined]
        if not filepath:
            return
        from nav2_config.core.config_file import ConfigFile
        try:
            cfg = ConfigFile(filepath)
            cfg.load()
        except Exception as exc:
            QMessageBox.critical(
                self, 'Load Failed', f'Could not load {filepath}:\n{exc}'
            )
            return
        self._config_file = cfg
        self._dirty = False
        self._update_title()
        self._yaml_panel.set_file_content(cfg.to_yaml_string(), dirty=False)
        self._add_recent_file(filepath)
        self.set_status(f'Loaded config: {filepath}')
        logger.info('Config loaded: %s', filepath)

    def _on_save(self) -> None:
        """File > Save (Ctrl+S): write the config file in place."""
        if not self._config_file:
            self._on_save_as()
            return
        try:
            self._config_file.save()
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', f'Could not save:\n{exc}')
            return
        self._dirty = False
        self._update_title()
        self._yaml_panel.set_save_button_dirty(False)
        self.set_status(f'Saved to {self._config_file.filepath}')

    def _on_save_as(self) -> None:
        """File > Save As: write the config file to a new path."""
        start = self._config_file.filepath if self._config_file else str(Path.home())
        filepath, _ = QFileDialog.getSaveFileName(
            self, 'Save As', start, 'YAML Files (*.yaml *.yml);;All Files (*)'
        )
        if not filepath:
            return
        if not self._config_file:
            from nav2_config.core.config_file import ConfigFile
            self._config_file = ConfigFile(filepath)
        try:
            self._config_file.save_as(filepath)
        except Exception as exc:
            QMessageBox.critical(self, 'Save Failed', f'Could not save:\n{exc}')
            return
        self._dirty = False
        self._update_title()
        self._yaml_panel.set_save_button_dirty(False)
        self._add_recent_file(filepath)
        self.set_status(f'Saved to {filepath}')

    def _add_recent_file(self, filepath: str) -> None:
        """Add *filepath* to the persisted recent-files list."""
        settings = _load_settings()
        recent: list[str] = settings.get('recent_files', [])
        if filepath in recent:
            recent.remove(filepath)
        recent.insert(0, filepath)
        _save_settings_partial({'recent_files': recent[:5]})
        self._update_recent_files_menu()

    def _update_recent_files_menu(self) -> None:
        """Rebuild the File menu's recent-file entries."""
        for action in self._recent_actions:
            self._file_menu.removeAction(action)
        self._recent_actions.clear()

        settings = _load_settings()
        recent: list[str] = settings.get('recent_files', [])
        if not recent:
            return

        after = self._recent_files_sep
        for fp in recent:
            action = QAction(fp, self)
            action.triggered.connect(
                lambda checked=False, path=fp: self._open_recent_file(path)
            )
            self._file_menu.insertAction(after, action)
            self._recent_actions.append(action)

    def _open_recent_file(self, filepath: str) -> None:
        """Load a file from the recent-files list."""
        if self._dirty:
            reply = QMessageBox.question(
                self,
                'Unsaved Changes',
                'You have unsaved changes. Save before switching?',
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()

        from nav2_config.core.config_file import ConfigFile
        try:
            cfg = ConfigFile(filepath)
            cfg.load()
        except Exception as exc:
            QMessageBox.critical(
                self, 'Load Failed', f'Could not load {filepath}:\n{exc}'
            )
            return
        self._config_file = cfg
        self._dirty = False
        self._update_title()
        self._yaml_panel.set_file_content(cfg.to_yaml_string(), dirty=False)
        self._add_recent_file(filepath)
        self.set_status(f'Loaded config: {filepath}')

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

    # ------------------------------------------------------------------
    # Lifecycle action slots
    # ------------------------------------------------------------------

    def _on_lifecycle_manager_status(self, present: bool, manager_path: str) -> None:
        """Called when lifecycle_manager presence changes."""
        self._lifecycle_manager_present = present
        self._node_panel.set_lifecycle_manager_present(present)
        if present:
            bare = manager_path.lstrip('/')
            self.set_status(f'lifecycle_manager detected: /{bare} — stack-level restart enabled')
        else:
            self.set_status('lifecycle_manager not found — direct node lifecycle control enabled')

    def _on_lifecycle_action_requested(self, node_path: str, action: str) -> None:
        """Dispatch lifecycle actions from the node panel (bar or context menu)."""
        bare = node_path.lstrip('/')

        if action == 'restart_stack':
            self._on_restart_all_nav2()

        elif action == 'restart':
            reply = QMessageBox.question(
                self,
                'Restart Node',
                f'Restart {node_path}?\nThis will briefly interrupt navigation.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._do_restart_node(node_path)

        elif action == 'shutdown':
            reply = QMessageBox.question(
                self,
                'Shutdown Node',
                f'This will shut down {node_path}. Are you sure?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._node.request_lifecycle_shutdown(node_path)
            self.set_status(f'Shutting down {bare}...')

        elif action == 'activate':
            self._node.request_lifecycle_change(
                node_path, Transition.TRANSITION_ACTIVATE
            )
            self.set_status(f'Activating {bare}...')

        elif action == 'deactivate':
            self._node.request_lifecycle_change(
                node_path, Transition.TRANSITION_DEACTIVATE
            )
            self.set_status(f'Deactivating {bare}...')

        elif action == 'configure':
            self._node.request_lifecycle_change(
                node_path, Transition.TRANSITION_CONFIGURE
            )
            self.set_status(f'Configuring {bare}...')

        elif action == 'cleanup':
            self._node.request_lifecycle_change(
                node_path, Transition.TRANSITION_CLEANUP
            )
            self.set_status(f'Cleaning up {bare}...')

    def _do_restart_node(self, node_path: str) -> None:
        """Restart *node_path*, using lifecycle_manager if it is running.

        When lifecycle_manager is detected, a direct per-node restart would
        trigger its bond monitoring and cause a CRITICAL FAILURE.  In that
        case the entire stack is restarted via manage_nodes (RESET + STARTUP)
        instead.  When no lifecycle_manager is running, the direct per-node
        restart sequence (deactivate → cleanup → configure → activate) is used.
        """
        if self._lifecycle_manager_present:
            # Safe path: let lifecycle_manager handle the restart.
            bare = node_path.lstrip('/')
            self.set_status(
                f'Nav2 stack restart triggered by change on {bare}...', timeout_ms=0
            )
            dialog = _RestartAllProgressDialog(1, parent=self)
            self._node.signals.lifecycle_progress.connect(dialog.on_progress)
            self._node.signals.lifecycle_change_result.connect(dialog.on_result)
            self._node.signals.lifecycle_change_result.connect(
                lambda np, ok, _msg, n=node_path: (
                    self._node_panel.set_node_restart_pending(n, False) if ok else None
                )
            )
            self._node.request_nav2_stack_restart()
            dialog.show()
            return

        # Direct path: no lifecycle_manager — per-node restart is safe.
        bare = node_path.lstrip('/')
        self.set_status(f'Restarting {bare}... Deactivating', timeout_ms=0)

        def _on_progress(np: str, step: str) -> None:
            if np == node_path:
                self.set_status(f'Restarting {bare}... {step}', timeout_ms=0)

        self._node.signals.lifecycle_progress.connect(_on_progress)
        self._node.request_lifecycle_restart(node_path)

        def _on_result(np: str, success: bool, msg: str) -> None:
            if np == node_path:
                self._node.signals.lifecycle_progress.disconnect(_on_progress)
                self._node.signals.lifecycle_change_result.disconnect(_on_result)
                if success:
                    self._node_panel.set_node_restart_pending(node_path, False)

        self._node.signals.lifecycle_change_result.connect(_on_result)

    def _on_lifecycle_change_result(
        self, node_path: str, success: bool, message: str
    ) -> None:
        """Update status bar when a lifecycle transition completes."""
        bare = node_path.lstrip('/')
        icon = '✓' if success else '✗'
        self.set_status(f'{icon} {bare}: {message}')
        if success:
            logger.info('Lifecycle %s: %s', node_path, message)
        else:
            logger.warning('Lifecycle %s: %s', node_path, message)

    def _on_restart_all_nav2(self) -> None:
        """Toolbar / context-menu handler: restart all Nav2 nodes.

        When lifecycle_manager is running, uses the safe manage_nodes service
        (RESET + STARTUP) so bond monitoring is not triggered.  Falls back to
        direct per-node lifecycle transitions when no lifecycle_manager is found.
        If there are unsaved config changes, prompts the user to save first so
        Nav2 reads the updated YAML on restart.
        """
        # Prompt to save unsaved changes before restarting so Nav2 picks them up
        if self._dirty and self._config_file:
            reply = QMessageBox.question(
                self,
                'Save Before Restart?',
                'You have unsaved config changes.\n'
                'Save now so Nav2 reads the updated file on restart?',
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()

        if self._lifecycle_manager_present:
            reply = QMessageBox.question(
                self,
                'Restart Nav2 Stack',
                'Restart all Nav2 nodes via lifecycle_manager?\n'
                'Navigation will be interrupted for several seconds.\n\n'
                'This uses the safe manage_nodes service to avoid bond failures.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            # One result expected (lifecycle_change_result from lifecycle_manager restart)
            dialog = _RestartAllProgressDialog(1, parent=self)
            self._node.signals.lifecycle_progress.connect(dialog.on_progress)
            self._node.signals.lifecycle_change_result.connect(dialog.on_result)
            self._node.request_nav2_stack_restart()
            dialog.show()
            return

        # Direct restart path (no lifecycle_manager).
        discovered_count = sum(
            1 for n in self._node._prev_discovered or set()
            if n
        )
        if discovered_count == 0:
            QMessageBox.information(
                self, 'No Nodes', 'No Nav2 nodes are currently discovered.'
            )
            return

        reply = QMessageBox.question(
            self,
            'Restart Nav2 Stack',
            f'Restart all {discovered_count} Nav2 nodes?\n'
            'Navigation will be interrupted for several seconds.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        dialog = _RestartAllProgressDialog(discovered_count, parent=self)
        self._node.signals.lifecycle_progress.connect(dialog.on_progress)
        self._node.signals.lifecycle_change_result.connect(dialog.on_result)
        self._node.request_lifecycle_restart_all()
        dialog.show()

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
            updates = {
                'geometry': {
                    'x': self.x(), 'y': self.y(),
                    'width': self.width(), 'height': self.height(),
                },
                'splitter_sizes': self._splitter.sizes(),
                'show_descriptions': self._toggle_desc_action.isChecked(),
            }
            if self._config_file:
                updates['last_config_file'] = self._config_file.filepath
            _save_settings_partial(updates)
        except Exception:
            logger.warning('Failed to save window state', exc_info=True)

    def _restore_window_state(self) -> None:
        try:
            state = _load_settings()
            if 'geometry' in state:
                g = state['geometry']
                self.setGeometry(g['x'], g['y'], g['width'], g['height'])
            if 'splitter_sizes' in state:
                self._splitter.setSizes(state['splitter_sizes'])
            if 'show_descriptions' in state:
                self._toggle_desc_action.setChecked(state['show_descriptions'])
        except Exception:
            logger.warning('Failed to restore window state', exc_info=True)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        if self._dirty and self._config_file:
            reply = QMessageBox.question(
                self,
                'Unsaved Changes',
                'You have unsaved changes. Save before closing?',
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                try:
                    self._config_file.save()
                except Exception:
                    logger.warning('Failed to save config on close', exc_info=True)
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
