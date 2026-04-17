# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Main window for nav2_config: three-panel splitter layout.

Styled to match RViz2: light gray Qt Fusion theme, QToolBar with
flat icon buttons, full menu bar, 22px status bar.
"""

import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from nav2_config.core.config_file import ConfigFile

from lifecycle_msgs.msg import Transition
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.node_discovery import (
    NAV2_NODE_SPECS,
    DiscoveredNav2Node,
    DiscoveredLifecycleManager,
)
try:
    from nav2_config.core.robot_mode_detector import RobotMode
    _ROBOT_MODE_AVAILABLE = True
except ImportError:
    RobotMode = None  # type: ignore[assignment,misc]
    _ROBOT_MODE_AVAILABLE = False
from nav2_config.gui.icons import (
    menu_about, menu_descriptions, menu_open,
    menu_quit, menu_refresh, menu_save, menu_save_as,
    menu_shortcuts, status_connected, status_disconnected,
    toolbar_load_config, toolbar_refresh, toolbar_restart, toolbar_save,
)
from nav2_config.gui.node_panel import NodePanel
from nav2_config.gui.param_panel import ParamPanel
from nav2_config.gui.yaml_panel import YamlPanel
from nav2_config.node import Nav2ConfigNode
from nav2_config.types.params import ParamValue

# --- History/compare feature imports (graceful fallback if not yet built) ---
try:
    from nav2_config.core.history_manager import HistoryManager
    from nav2_config.types.history import (
        ChangeSource,
        ParamHistoryEntry,
        ParamRef,
    )
    from nav2_config.core.config_diff import (
        diff_snapshots,
        snapshot_from_param_values,
        ParamSnapshot,
        ParamSnapshotEntry,
    )
    from nav2_config.core.yaml_importer import import_yaml as _import_yaml_for_compare
    _HISTORY_AVAILABLE = True
except ImportError:
    HistoryManager = None  # type: ignore[assignment,misc]
    ChangeSource = None  # type: ignore[assignment,misc]
    ParamHistoryEntry = None  # type: ignore[assignment,misc]
    ParamRef = None  # type: ignore[assignment,misc]
    diff_snapshots = None  # type: ignore[assignment,misc]
    snapshot_from_param_values = None  # type: ignore[assignment,misc]
    ParamSnapshot = None  # type: ignore[assignment,misc]
    ParamSnapshotEntry = None  # type: ignore[assignment,misc]
    _import_yaml_for_compare = None  # type: ignore[assignment,misc]
    _HISTORY_AVAILABLE = False

try:
    from nav2_config.gui.history_panel import HistoryPanel
    from nav2_config.gui.compare_panel import ComparePanel
    from nav2_config.gui.inspector_panel import InspectorPanel
    _INSPECTOR_AVAILABLE = True
except ImportError:
    HistoryPanel = None  # type: ignore[assignment,misc]
    ComparePanel = None  # type: ignore[assignment,misc]
    InspectorPanel = None  # type: ignore[assignment,misc]
    _INSPECTOR_AVAILABLE = False


@dataclass
class ApplyParamRequest:
    """Request to apply a single parameter change, with history metadata."""

    node_path: str
    param_name: str
    value: Any
    ros2_name: str
    type_hint: str
    hot_reload: bool
    source: Any  # ChangeSource enum value (or None when history unavailable)
    batch_id: Optional[str] = None
    history_entry_id: Optional[str] = None

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

_ROS_DISTRO: str = os.environ.get('ROS_DISTRO', 'unknown').capitalize()


class _RobotModePill(QLabel):
    """Status bar pill showing detected simulation / real-robot mode.

    Always visible on the right side of the status bar.  Colors match the
    RViz2 light theme:

    - SIMULATION → blue pill  (``#1565c0`` on ``#e3f2fd``)
    - REAL ROBOT → green pill (``#2e7d32`` on ``#e8f5e9``)
    - UNKNOWN    → gray pill  (``#757575`` on ``#f5f5f5``)
    """

    _STYLES: dict = {
        'SIMULATION': ('SIMULATION', '#1565c0', '#bbdefb', '#1565c0'),
        'REAL':       ('REAL ROBOT', '#1b5e20', '#c8e6c9', '#2e7d32'),
        'UNKNOWN':    ('DETECTING...', '#424242', '#eeeeee', '#9e9e9e'),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_style('UNKNOWN')

    def set_mode(self, mode: object) -> None:
        """Update pill appearance for *mode* (a :class:`~nav2_config.core.robot_mode_detector.RobotMode`)."""
        if mode is None or not _ROBOT_MODE_AVAILABLE:
            self._apply_style('UNKNOWN')
            return
        self._apply_style(mode.name)

    def _apply_style(self, mode_name: str) -> None:
        label, fg, bg, border = self._STYLES.get(mode_name, self._STYLES['UNKNOWN'])
        self.setText(label)
        self.setStyleSheet(
            f'QLabel {{'
            f'  background: {bg};'
            f'  color: {fg};'
            f'  font-size: 11px;'
            f'  font-weight: bold;'
            f'  border-radius: 8px;'
            f'  border: 1px solid {border};'
            f'  padding: 2px 8px;'
            f'}}'
        )


class _RestartNotificationBar(QWidget):
    """Amber banner shown when a non-hot-reload param is saved to config.

    Offers "Save & Restart" and "Save Only" actions.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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

        self._save_restart_btn = QPushButton('Save & Restart')
        self._save_restart_btn.setFixedHeight(22)
        self._save_restart_btn.setStyleSheet(
            'QPushButton { background: #f57c00; border: 1px solid #e65100; '
            'color: white; font-size: 9pt; padding: 0 10px; }'
            'QPushButton:hover { background: #e65100; }'
        )
        layout.addWidget(self._save_restart_btn)

        self._save_only_btn = QPushButton('Save Only')
        self._save_only_btn.setFixedHeight(22)
        self._save_only_btn.setStyleSheet(
            'QPushButton { background: transparent; border: 1px solid #bbb; '
            'color: #555; font-size: 9pt; padding: 0 8px; }'
            'QPushButton:hover { background: #ffe0b2; }'
        )
        layout.addWidget(self._save_only_btn)

    def show_for(
        self,
        param_name: str,
        on_save_restart: 'Callable[[], None]',
        on_save_only: 'Callable[[], None]',
    ) -> None:
        """Display the bar for a non-hot-reload param saved to config.

        Args:
            param_name: The parameter that was saved to the config file.
            on_save_restart: Called when the user clicks "Save & Restart".
            on_save_only: Called when the user clicks "Save Only".
        """
        self._message.setText(
            f'{param_name} updated in config. Restart Nav2 to apply.'
        )
        for btn, cb in (
            (self._save_restart_btn, on_save_restart),
            (self._save_only_btn, on_save_only),
        ):
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(lambda _checked=False, c=cb: (self.setVisible(False), c()))
        self.setVisible(True)


class _RestartAllProgressDialog(QDialog):
    """Modal progress dialog for the Restart Nav2 Stack operation.

    Receives ``lifecycle_progress`` and ``lifecycle_change_result`` signals
    and updates its log text area in real time.
    """

    def __init__(self, node_count: int, signals: object, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expected = node_count
        self._done_count = 0
        self._signals = signals
        self._build_ui()
        self.finished.connect(self._cleanup)

    def _cleanup(self) -> None:
        """Disconnect owned signal connections when the dialog closes."""
        try:
            self._signals.lifecycle_progress.disconnect(self.on_progress)
        except (RuntimeError, TypeError):
            pass
        try:
            self._signals.lifecycle_change_result.disconnect(self.on_result)
        except (RuntimeError, TypeError):
            pass

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
        self._pending_config_set: dict[tuple[str, str], tuple] = {}
        self._current_params: list[ParamValue] = []
        self._all_node_params: dict[str, list[ParamValue]] = {}
        self._saved_panel_sizes: list[int] = [240, 10000, 300]
        self._lifecycle_manager_present: bool = False
        self._expert_mode: bool = False
        self._expert_mode_warned: bool = False
        self._connect_to_nodes: bool = True
        self._topology_nodes: dict[str, DiscoveredNav2Node] = {}
        self._topology_managers: dict[str, DiscoveredLifecycleManager] = {}
        self._selected_node_path: str | None = None

        # Schema index for type inference in _yaml_dict_to_snapshot.
        # Built lazily on first compare; maps (bare_node, param_name) -> Nav2ParamDef.
        self._schema_index: dict[tuple[str, str], Any] | None = None

        # History/compare feature — guarded in case modules aren't built yet
        self._history: Optional[Any] = HistoryManager() if _HISTORY_AVAILABLE else None
        # Maps (node_path, ros2_name) -> entry_id for in-flight set calls
        self._pending_history: dict[tuple[str, str], str] = {}
        # Maps (node_path, ros2_name) -> new_value for in-flight set calls,
        # consumed in _on_param_set_result to update the watcher baseline.
        self._pending_set_values: dict[tuple[str, str], Any] = {}
        # Maps undo_entry_id -> original_entry_id for undo confirmation routing.
        self._pending_undo_map: dict[str, str] = {}

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
        self.setWindowTitle(f'nav2_config (ROS2 {_ROS_DISTRO})')
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

        load_action = QAction(menu_open(), 'Load Config...', self)
        load_action.setShortcut(QKeySequence('Ctrl+O'))
        load_action.triggered.connect(self._on_load_config)
        self._file_menu.addAction(load_action)

        self._file_menu.addSeparator()

        self._save_action = QAction(menu_save(), 'Save', self)
        self._save_action.setShortcut(QKeySequence('Ctrl+S'))
        self._save_action.setEnabled(False)
        self._save_action.triggered.connect(self._on_save)
        self._file_menu.addAction(self._save_action)

        self._save_as_action = QAction(menu_save_as(), 'Save As...', self)
        self._save_as_action.setShortcut(QKeySequence('Ctrl+Shift+S'))
        self._save_as_action.setEnabled(False)
        self._save_as_action.triggered.connect(self._on_save_as)
        self._file_menu.addAction(self._save_as_action)

        self._file_menu.addSeparator()

        # Recent files placeholder — populated by _update_recent_files_menu()
        self._recent_files_sep = self._file_menu.addSeparator()
        self._recent_actions: list[QAction] = []

        refresh_action = QAction(menu_refresh(), 'Refresh Nodes', self)
        refresh_action.setShortcut(QKeySequence('Ctrl+R'))
        refresh_action.triggered.connect(self._node.force_discover)
        self._file_menu.addAction(refresh_action)

        self._file_menu.addSeparator()

        quit_action = QAction(menu_quit(), 'Quit', self)
        quit_action.setShortcut(QKeySequence('Ctrl+Q'))
        quit_action.triggered.connect(self.close)
        self._file_menu.addAction(quit_action)

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

        self._toggle_desc_action = QAction(menu_descriptions(), 'Show Descriptions', self)
        self._toggle_desc_action.setCheckable(True)
        self._toggle_desc_action.setChecked(False)
        self._toggle_desc_action.setShortcut(QKeySequence('Ctrl+D'))
        self._toggle_desc_action.triggered.connect(self._on_toggle_descriptions)
        view_menu.addAction(self._toggle_desc_action)

        # ── Help ─────────────────────────────────────────────────────────
        help_menu: QMenu = bar.addMenu('Help')

        shortcuts_action = QAction(menu_shortcuts(), 'Keyboard Shortcuts', self)
        shortcuts_action.triggered.connect(self._show_shortcuts)
        help_menu.addAction(shortcuts_action)

        help_menu.addSeparator()

        about_action = QAction(menu_about(), 'About nav2_config', self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self) -> None:
        """Build the main toolbar with icon+text buttons and a search field."""
        tb: QToolBar = self.addToolBar('Main')
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setObjectName('mainToolBar')
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        tb.setIconSize(QSize(16, 16))

        def _add_action(icon: 'QIcon', label: str, tooltip: str) -> QAction:
            action = QAction(icon, label, self)
            action.setToolTip(tooltip)
            tb.addAction(action)
            return action

        self._tb_refresh = _add_action(
            toolbar_refresh(), 'Refresh', 'Refresh node discovery  (Ctrl+R)'
        )
        self._tb_refresh.triggered.connect(self._node.force_discover)

        self._tb_restart_all = _add_action(
            toolbar_restart(),
            'Restart Nav2',
            'Restart all Nav2 nodes in lifecycle order',
        )
        self._tb_restart_all.triggered.connect(self._on_restart_all_nav2)

        self._tb_load_config = _add_action(
            toolbar_load_config(), 'Load Config', 'Load a Nav2 configuration YAML  (Ctrl+O)'
        )
        self._tb_load_config.triggered.connect(self._on_load_config)

        self._tb_save = _add_action(
            toolbar_save(), 'Save', 'Save current parameters to YAML  (Ctrl+S)'
        )
        self._tb_save.triggered.connect(self._on_save)

        # Spacer to push the search field to the right
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        tb.addSeparator()

        # Expert Mode toggle
        self._expert_mode_cb = QCheckBox('Expert Mode')
        self._expert_mode_cb.setToolTip(
            'Show direct per-node lifecycle transitions even when lifecycle_manager is active'
        )
        self._expert_mode_cb.setStyleSheet('QCheckBox { font-size: 9pt; padding: 0 4px; }')
        self._expert_mode_cb.toggled.connect(self._on_expert_mode_toggled)
        tb.addWidget(self._expert_mode_cb)

        tb.addSeparator()

        # Search field
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText('Search params...')
        self._search_box.setFixedWidth(220)
        self._search_box.setFixedHeight(24)
        self._search_box.setClearButtonEnabled(True)
        self._search_box.setStyleSheet(
            'QLineEdit { border: 1px solid #aaa; padding: 0 6px; font-size: 9pt; }'
            'QLineEdit:focus { border-color: #3399ff; }'
        )
        self._search_box.textChanged.connect(self._on_search_changed)
        tb.addWidget(self._search_box)

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
        self._yaml_panel = YamlPanel()

        # Wrap YamlPanel in InspectorPanel when the history/compare modules are available.
        if _INSPECTOR_AVAILABLE:
            self._history_panel = HistoryPanel()
            self._compare_panel = ComparePanel()
            self._inspector = InspectorPanel(
                self._yaml_panel, self._history_panel, self._compare_panel
            )
            right_widget = self._inspector
        else:
            self._history_panel = None
            self._compare_panel = None
            self._inspector = None
            right_widget = self._yaml_panel

        splitter.addWidget(self._node_panel)
        splitter.addWidget(self._param_panel)
        splitter.addWidget(right_widget)
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

        from PyQt6.QtWidgets import QLabel as _QLabel
        self._status_dot = _QLabel()
        self._status_dot.setFixedSize(14, 14)
        self._status_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_dot.setPixmap(
            status_disconnected().pixmap(10, 10)
        )
        status.addWidget(self._status_dot)

        self._status_connection = QLabel('Disconnected')
        self._status_connection.setStyleSheet(
            f'color: {_RED}; padding: 0 4px 0 0; font-size: 9pt;'
        )
        status.addWidget(self._status_connection)

        self._status_last_set = QLabel('')
        self._status_last_set.setStyleSheet(
            f'color: {_FG_DIM}; padding: 0 8px; font-size: 9pt;'
        )
        status.addPermanentWidget(self._status_last_set)

        self._robot_mode_pill = _RobotModePill()
        status.addPermanentWidget(self._robot_mode_pill)

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
        self._node.signals.params_externally_changed.connect(
            self._on_params_externally_changed
        )
        self._node.signals.discovery_refreshed.connect(
            self._param_panel.refresh_dropdowns
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
        self._node_panel.stack_action_requested.connect(self._on_stack_action_requested)
        self._node.signals.topology_updated.connect(self._on_topology_updated)
        self._param_panel.lifecycle_action_requested.connect(
            self._on_lifecycle_action_requested
        )
        self._node.signals.lifecycle_states_updated.connect(
            self._on_lifecycle_states_updated_for_param_panel
        )
        self._node.signals.lifecycle_manager_status.connect(
            self._on_lifecycle_manager_status
        )
        self._yaml_panel.save_requested.connect(self._on_save)
        self._node.signals.load_map_result.connect(self._on_load_map_result)
        self._node.signals.post_action_result.connect(self._on_post_action_result)
        self._node.signals.restart_suggested.connect(self._on_restart_suggested)
        self._node.signals.amcl_pose_status.connect(self._on_amcl_pose_status)
        if _ROBOT_MODE_AVAILABLE:
            self._node.signals.robot_mode_changed.connect(self._on_robot_mode_changed)

        # History/compare feature signal wiring
        if _HISTORY_AVAILABLE and self._history is not None:
            self._history.history_entry_added.connect(
                self._history_panel.add_entry
                if self._history_panel is not None
                else lambda _e: None
            )
            self._history.history_entry_updated.connect(
                self._history_panel.update_entry
                if self._history_panel is not None
                else lambda _e: None
            )
            self._history.history_reset.connect(
                self._history_panel.clear
                if self._history_panel is not None
                else lambda: None
            )
        if self._history_panel is not None:
            self._history_panel.undo_requested.connect(self._on_undo_requested)
        if self._compare_panel is not None:
            self._compare_panel.compare_requested.connect(self._on_compare_requested)
            self._compare_panel.apply_selected_requested.connect(self._on_compare_apply)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_robot_mode_changed(self, mode: object) -> None:
        """Update status bar pill and param panel banner when robot mode changes."""
        self._robot_mode_pill.set_mode(mode)
        self._param_panel.set_robot_mode(mode)

    def _on_nodes_discovered(self, status: dict[str, bool]) -> None:
        found = sum(1 for v in status.values() if v)
        total = len(NAV2_NODE_SPECS)
        total_params = sum(len(p) for p in self._all_node_params.values())

        if found == 0:
            self._status_connection.setText(
                f'Disconnected  |  0/{total} nodes  |  ROS2 {_ROS_DISTRO}'
            )
            self._status_connection.setStyleSheet(
                f'color: {_RED}; padding: 0 4px 0 0; font-size: 9pt;'
            )
            self._status_dot.setPixmap(status_disconnected().pixmap(10, 10))
        else:
            param_part = f'  |  {total_params} params' if total_params else ''
            self._status_connection.setText(
                f'Connected  |  {found}/{total} nodes{param_part}  |  ROS2 {_ROS_DISTRO}'
            )
            self._status_connection.setStyleSheet(
                f'color: {_GREEN}; padding: 0 4px 0 0; font-size: 9pt;'
            )
            self._status_dot.setPixmap(status_connected().pixmap(10, 10))

        current = self._param_panel._node_name
        if current:
            for path, running in status.items():
                if path == current and not running:
                    self.set_status(f'Node {current.lstrip("/")} went offline')
                    break

    def _on_topology_updated(self, nodes_by_path: dict, managers_by_path: dict) -> None:
        """Store topology caches and refresh the node panel."""
        self._topology_nodes = nodes_by_path
        self._topology_managers = managers_by_path
        self._node_panel.update_topology(nodes_by_path, managers_by_path)
        if self._selected_node_path:
            self._refresh_selected_node_context()

    def _stack_has_manager(self, stack_namespace: str) -> bool:
        """Return True if any discovered lifecycle_manager manages this stack."""
        return any(
            m.stack_namespace == stack_namespace
            for m in self._topology_managers.values()
        )

    def _on_stack_action_requested(self, stack_namespace: str, action: str) -> None:
        """Handle stack-level lifecycle actions from the node panel."""
        if action == 'restart_stack':
            self._node.request_lifecycle_restart_stack(stack_namespace)
            self.set_status(f'Restarting stack {stack_namespace}...')
        elif action == 'pause_stack':
            self._node.request_lifecycle_pause_stack_ns(stack_namespace)
            self.set_status(f'Pausing stack {stack_namespace}...')
        elif action == 'resume_stack':
            self._node.request_lifecycle_resume_stack_ns(stack_namespace)
            self.set_status(f'Resuming stack {stack_namespace}...')

    def _refresh_selected_node_context(self) -> None:
        """Refresh param panel lifecycle bar using per-stack manager context."""
        if not self._selected_node_path:
            return
        node = self._topology_nodes.get(self._selected_node_path)
        if node is None:
            return
        stack_has_manager = self._stack_has_manager(node.stack_namespace)
        known_state = self._node.get_lifecycle_state(self._selected_node_path)
        self._param_panel.update_lifecycle_state(
            self._selected_node_path, known_state, stack_has_manager
        )

    def _on_node_selected(self, node_path: str) -> None:
        logger.info('Node selected: %s', node_path)
        self._selected_node_path = node_path
        node = self._topology_nodes.get(node_path)
        if node is not None:
            self._param_panel.set_selected_node(node)
        else:
            self._param_panel.set_node_name(node_path)
        self._yaml_panel.set_current_node(node_path)
        if self._connect_to_nodes:
            self._node.watch_node(node_path)
            self._node.request_fetch_params(node_path)
        else:
            self._node.unwatch_node()
        self._status_bar.showMessage(node_path.lstrip('/'))
        self._refresh_selected_node_context()

    def _attach_restart_dialog(
        self,
        dialog: '_RestartAllProgressDialog',
        clear_node: str | None = None,
    ) -> None:
        """Wire lifecycle signals to *dialog* and optionally clear a restart-pending marker.

        Args:
            dialog: The progress dialog to wire up.
            clear_node: If provided, clears the restart-pending state for this node
                        on the first success result for this node (or the global result).
        """
        self._node.signals.lifecycle_progress.connect(dialog.on_progress)
        self._node.signals.lifecycle_change_result.connect(dialog.on_result)

        if clear_node is not None:
            def _clear_pending(node_path: str, ok: bool, _msg: str) -> None:
                if ok and (node_path == '' or node_path == clear_node):
                    self._node_panel.set_node_restart_pending(clear_node, False)
                    try:
                        self._node.signals.lifecycle_change_result.disconnect(_clear_pending)
                    except (RuntimeError, TypeError):
                        pass

            self._node.signals.lifecycle_change_result.connect(_clear_pending)

            def _disconnect_clear() -> None:
                try:
                    self._node.signals.lifecycle_change_result.disconnect(_clear_pending)
                except (RuntimeError, TypeError):
                    pass

            dialog.finished.connect(_disconnect_clear)

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
                plugin_filter=None,
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
                plugin_filter=None,
                pending_params=self._param_panel.pending_param_names(),
            )

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
        post_set_action: str | None = None
        for row in self._param_panel._all_rows:
            if row._param_value.definition.param == param_name:
                type_hint = row._param_value.definition.type
                hot_reload = row._param_value.definition.hot_reload
                ros2_name = row._param_value.definition.ros2_name
                post_set_action = row._param_value.definition.post_set_action
                break

        if hot_reload:
            # Stage config change — applied only after ROS2 confirms success.
            # This prevents the in-memory config from diverging when the set
            # call times out or is rejected by the node.
            if self._config_file:
                self._pending_config_set[(node_name, ros2_name)] = (node_name, ros2_name, value)
            # Immediate live effect via ROS2 service.
            # Any follow-up action (clear_costmaps, load_map, nomotion_update)
            # is handled automatically by _after_param_set in the ROS2 thread.
            if post_set_action == 'load_map':
                self.set_status('Loading map...', timeout_ms=0)
            # Record to history before dispatching; status updated in _on_param_set_result.
            # Keyed by (node_name, ros2_name) — matches what param_set_result signal carries.
            if _HISTORY_AVAILABLE and self._history is not None:
                _entry_id = str(uuid.uuid4())
                _old_value: Any = None
                for _pv in self._current_params:
                    if _pv.definition.param == param_name:
                        _old_value = _pv.confirmed_value
                        break
                self._history.record_change(ParamHistoryEntry(
                    entry_id=_entry_id,
                    timestamp=datetime.now(),
                    ref=ParamRef(node_path=node_name, param_name=param_name),
                    old_value=_old_value,
                    new_value=value,
                    source=ChangeSource.LIVE_SET,
                    batch_id=None,
                    ros2_name=ros2_name,
                    type_hint=type_hint,
                    hot_reload=True,
                    status="pending",
                ))
                self._pending_history[(node_name, ros2_name)] = _entry_id
            self._pending_set_values[(node_name, ros2_name)] = value
            self._node.request_set_param(node_name, ros2_name, value, type_hint)
        else:
            # Non-hot-reload: update config in-memory then save to disk immediately.
            if self._config_file is None:
                QMessageBox.warning(
                    self,
                    'No Config File Loaded',
                    'Cannot apply this parameter change: no config file is loaded.\n\n'
                    'Load a config file first via File > Open, then try again.',
                )
                return
            self._config_file.set_value(node_name, ros2_name, value)
            self._mark_dirty()
            try:
                self._config_file.save()
            except Exception as exc:
                logger.warning('Auto-save failed after non-hot-reload param set: %s', exc)
                QMessageBox.critical(
                    self,
                    'Save Failed',
                    f'Could not save config to disk:\n{exc}\n\n'
                    'The parameter change was NOT written to the file.',
                )
                return
            self._dirty = False
            self._update_title()
            self._yaml_panel.set_save_button_dirty(False)
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=False
            )
            self._node.get_logger().info(
                f"Config saved: {param_name} = {value}"
            )
            self._param_panel.mark_param_file_saved(param_name)
            self._node_panel.set_node_restart_pending(node_name, True)
            self.set_status(f'Config saved: {param_name}. Restart Nav2 to apply.')

            def _on_save_restart() -> None:
                self.set_status('Restarting Nav2 via lifecycle_manager...', timeout_ms=0)
                dialog = _RestartAllProgressDialog(1, signals=self._node.signals, parent=self)
                self._attach_restart_dialog(dialog, clear_node=node_name)
                _node_info = self._topology_nodes.get(node_name)
                if _node_info is not None:
                    self._node.request_lifecycle_restart_stack_ns(_node_info.stack_namespace)
                else:
                    logger.warning(
                        'Could not find topology entry for %s; falling back to global restart',
                        node_name,
                    )
                    self._node.request_nav2_stack_restart()
                dialog.show()

            def _on_save_only() -> None:
                self.set_status('Config saved. Restart Nav2 when ready.')

            self._notification_bar.show_for(
                param_name,
                on_save_restart=_on_save_restart,
                on_save_only=_on_save_only,
            )

    def _on_param_set_result(
        self, node_name: str, ros2_name: str, success: bool
    ) -> None:
        # Resolve display name (schema .param field) from ros2_name for UI calls.
        display_name = ros2_name
        for pv in self._current_params:
            if pv.definition.ros2_name == ros2_name:
                display_name = pv.definition.param
                break

        # Only update the panel rows if the result belongs to the currently
        # selected node.  If the user switched nodes before the service call
        # returned, the rows shown no longer correspond to this result, so
        # routing it would update the wrong widget.
        if node_name == self._selected_node_path:
            # Route result to the matching row's Set button (updates confirmed_value).
            self._param_panel.update_set_result(display_name, success)
        else:
            logging.debug(
                'Discarding stale param-set result for %s/%s '
                '(current node is %s)',
                node_name, ros2_name, self._selected_node_path,
            )

        # Update history entry status for this in-flight set call.
        # Also handles undo confirmation via _pending_undo_map.
        if _HISTORY_AVAILABLE and self._history is not None:
            pending_id = self._pending_history.pop((node_name, ros2_name), None)
            if pending_id is not None:
                original_id = self._pending_undo_map.pop(pending_id, None)
                if original_id is not None:
                    # This result is for an undo operation — update both entries.
                    self._history.update_entry_status(
                        pending_id, 'applied' if success else 'failed'
                    )
                    if success:
                        self._history.update_entry_status(original_id, 'undone')
                    else:
                        self._history.update_entry_status(original_id, 'undo_failed')
                else:
                    self._history.update_entry_status(
                        pending_id, 'applied' if success else 'failed'
                    )

        # Update watcher baseline so the next poll doesn't re-report this as external.
        set_value = self._pending_set_values.pop((node_name, ros2_name), None)
        if set_value is not None and success:
            self._node.update_watcher_baseline_entry(ros2_name, set_value)

        # Apply or discard the staged config change for hot-reload params.
        staged = self._pending_config_set.pop((node_name, ros2_name), None)
        if staged is not None and success and self._config_file:
            staged_node, staged_ros2_name, staged_value = staged
            self._config_file.set_value(staged_node, staged_ros2_name, staged_value)
            self._mark_dirty()
            # The live value now matches the file value — clear the amber mismatch dot.
            self._param_panel.update_file_values({display_name: staged_value})

        # Refresh YAML panel
        if self._config_file:
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=self._dirty
            )
        else:
            self._yaml_panel.update_yaml(
                self._current_params,
                plugin_filter=None,
                pending_params=self._param_panel.pending_param_names(),
            )

        if success:
            val: object = '?'
            for pv in self._current_params:
                if pv.definition.ros2_name == ros2_name:
                    val = pv.live_value  # confirmed_value after update_set_result
                    break
            self._status_last_set.setText(f'\u2713 {display_name} \u2192 {val}')
            self._status_last_set.setStyleSheet(
                f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
            )
            logger.debug('Set %s/%s = %r', node_name, ros2_name, val)
        else:
            self._status_last_set.setText(f'\u2717 {display_name} -- failed')
            self._status_last_set.setStyleSheet(
                f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
            )
            self.set_status(
                f'Failed to set {node_name.lstrip("/")}/{ros2_name}'
            )
        self._last_set_timer.start(5000)

    def _on_load_map_result(self, success: bool, message: str) -> None:
        if success:
            self.set_status('Map loaded successfully')
            self._status_last_set.setText('\u2713 map reloaded')
            self._status_last_set.setStyleSheet(
                f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
            )
            self._last_set_timer.start(5000)
        else:
            self.set_status(f'Map load failed: {message}')
            self._status_last_set.setText('\u2717 map load failed')
            self._status_last_set.setStyleSheet(
                f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
            )
            self._last_set_timer.start(8000)

    def _on_post_action_result(
        self, param_name: str, action: str, success: bool, detail: str
    ) -> None:
        """Update the status bar after a post-set service action completes."""
        # Find the current (confirmed) value for the param to show in the bar.
        val: object = ''
        for pv in self._current_params:
            if pv.definition.param == param_name:
                val = pv.live_value
                break

        if action == 'clear_costmaps':
            if success:
                self._status_last_set.setText(
                    f'\u2713 {param_name} \u2192 {val} \u2014 costmaps cleared'
                )
                self._status_last_set.setStyleSheet(
                    f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
                )
                self.set_status(f'Set {param_name} = {val} — costmaps cleared')
            else:
                self._status_last_set.setText(f'\u2717 costmap clear failed')
                self._status_last_set.setStyleSheet(
                    f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
                )
                self.set_status(f'Set {param_name} — costmap clear failed')
        elif action == 'nomotion_update':
            if success:
                self._status_last_set.setText(
                    f'\u2713 {param_name} \u2192 {val} \u2014 AMCL updated'
                )
                self._status_last_set.setStyleSheet(
                    f'color: {_GREEN}; padding: 0 8px; font-size: 9pt;'
                )
                self.set_status(f'Set {param_name} = {val} — AMCL nomotion update triggered')
            else:
                self._status_last_set.setText(f'\u2717 AMCL update failed')
                self._status_last_set.setStyleSheet(
                    f'color: {_RED}; padding: 0 8px; font-size: 9pt;'
                )
                self.set_status(f'Set {param_name} — AMCL nomotion update failed')
        self._last_set_timer.start(6000)

    def _on_restart_suggested(self, node_name: str, param_name: str) -> None:
        """Show the restart notification bar when a restart_stack param is set live."""
        def _on_save_restart() -> None:
            self.set_status('Restarting Nav2 via lifecycle_manager...', timeout_ms=0)
            dialog = _RestartAllProgressDialog(1, signals=self._node.signals, parent=self)
            self._node.signals.lifecycle_progress.connect(dialog.on_progress)
            self._node.signals.lifecycle_change_result.connect(dialog.on_result)
            _node_info = self._topology_nodes.get(node_name)
            if _node_info is not None:
                self._node.request_lifecycle_restart_stack_ns(_node_info.stack_namespace)
            else:
                logger.warning(
                    'Could not find topology entry for %s; falling back to global restart',
                    node_name,
                )
                self._node.request_nav2_stack_restart()
            dialog.show()

        def _on_save_only() -> None:
            self.set_status('Plugin changed. Restart Nav2 when ready.')

        self._notification_bar.show_for(
            param_name,
            on_save_restart=_on_save_restart,
            on_save_only=_on_save_only,
        )

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
                f'nav2_config (ROS2 {_ROS_DISTRO}) -- {self._config_file.filepath}{dirty_marker}'
            )
            self._save_action.setEnabled(True)
            self._save_as_action.setEnabled(True)
        else:
            self.setWindowTitle(f'nav2_config (ROS2 {_ROS_DISTRO})')
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
        connect_to_nodes: bool = dialog.connect_to_nodes()  # type: ignore[attr-defined]
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
        logger.info('Config loaded from recent: %s', filepath)
        # Record FILE_LOAD history entries for params that differ from current live values.
        if _HISTORY_AVAILABLE and self._history is not None and self._current_params:
            _batch_id = str(uuid.uuid4())
            _now = datetime.now()
            for _pv in self._current_params:
                _node_path = _pv.node_path or f'/{_pv.definition.node}'
                _file_val = cfg.get_value(_node_path, _pv.definition.ros2_name)
                if _file_val is None:
                    continue
                if str(_file_val) == str(_pv.confirmed_value):
                    continue
                self._history.record_change(ParamHistoryEntry(
                    entry_id=str(uuid.uuid4()),
                    timestamp=_now,
                    ref=ParamRef(node_path=_node_path, param_name=_pv.definition.param),
                    old_value=_pv.confirmed_value,
                    new_value=_file_val,
                    source=ChangeSource.FILE_LOAD,
                    batch_id=_batch_id,
                    ros2_name=_pv.definition.ros2_name,
                    type_hint=_pv.definition.type,
                    hot_reload=_pv.definition.hot_reload,
                    status="applied",
                ))
        self._connect_to_nodes = connect_to_nodes
        if not connect_to_nodes:
            self._node.unwatch_node()
        watched = self._node._watcher.watched_node
        if connect_to_nodes and watched and self._node._prev_discovered:
            self._node.request_fetch_params(watched)

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

    def _on_params_externally_changed(self, node_name: str, changed: list) -> None:
        # changed is a list of (param_name, old_value, new_value) 3-tuples
        for item in changed:
            if len(item) == 3:
                param_name, old_value, new_value = item
            else:
                # Backwards-compat: 2-tuple (param_name, new_value)
                param_name, new_value = item
                old_value = None
            self._param_panel.update_param_value(param_name, new_value)
            self._param_panel.highlight_external_change(param_name)
            # Record to history
            if _HISTORY_AVAILABLE and self._history is not None:
                entry_id = str(uuid.uuid4())
                entry = ParamHistoryEntry(
                    entry_id=entry_id,
                    timestamp=datetime.now(),
                    ref=ParamRef(node_path=node_name, param_name=param_name),
                    old_value=old_value,
                    new_value=new_value,
                    source=ChangeSource.EXTERNAL_CHANGE,
                    batch_id=None,
                    ros2_name=param_name,
                    type_hint="string",
                    hot_reload=True,
                    status="applied",
                )
                self._history.record_change(entry)
        if len(changed) == 1:
            item = changed[0]
            name = item[0]
            val = item[2] if len(item) == 3 else item[1]
            self.set_status(f'External change: {name} = {val}')
        else:
            self.set_status(
                f'{len(changed)} params changed externally on {node_name.lstrip("/")}'
            )
        logger.info('External changes on %s: %s', node_name, changed)

    # ------------------------------------------------------------------
    # History/compare integration
    # ------------------------------------------------------------------

    def _apply_param_change(self, req: 'ApplyParamRequest') -> None:
        """Apply a parameter change and record it in the history.

        Records the change before dispatching it to the ROS2 node.  The history
        entry status is updated to 'applied' or 'failed' when the ROS2 result
        arrives via ``_on_param_set_result``.

        Args:
            req: The parameter change to apply.
        """
        if _HISTORY_AVAILABLE and self._history is not None:
            entry_id = req.history_entry_id or str(uuid.uuid4())

            if req.history_entry_id is None:
                old_value = self._history.get_latest_value(
                    ParamRef(node_path=req.node_path, param_name=req.param_name)
                )
                entry = ParamHistoryEntry(
                    entry_id=entry_id,
                    timestamp=datetime.now(),
                    ref=ParamRef(node_path=req.node_path, param_name=req.param_name),
                    old_value=old_value,
                    new_value=req.value,
                    source=req.source,
                    batch_id=req.batch_id,
                    ros2_name=req.ros2_name,
                    type_hint=req.type_hint,
                    hot_reload=req.hot_reload,
                    status="pending",
                )
                self._history.record_change(entry)

            # Track entry so _on_param_set_result can update its status
            self._pending_history[(req.node_path, req.param_name)] = entry_id

        if req.hot_reload:
            # Stage config change — applied only after ROS2 confirms success.
            if self._config_file:
                self._pending_config_set[(req.node_path, req.param_name)] = (
                    req.node_path, req.ros2_name, req.value
                )
            self._pending_set_values[(req.node_path, req.param_name)] = req.value
            self._node.request_set_param(
                req.node_path, req.ros2_name, req.value, req.type_hint
            )
        else:
            # Non-hot-reload: update config file and save to disk immediately.
            if self._config_file is None:
                logger.warning(
                    f"_apply_param_change: no config file loaded for "
                    f"{req.node_path}/{req.param_name}"
                )
                if _HISTORY_AVAILABLE and self._history is not None:
                    pending_id = self._pending_history.pop(
                        (req.node_path, req.param_name), None
                    )
                    if pending_id is not None:
                        self._history.update_entry_status(pending_id, "failed")
                return
            self._config_file.set_value(req.node_path, req.ros2_name, req.value)
            self._mark_dirty()
            try:
                self._config_file.save()
            except Exception as exc:
                logger.warning(
                    f"_apply_param_change: auto-save failed for "
                    f"{req.node_path}/{req.param_name}: {exc}"
                )
                if _HISTORY_AVAILABLE and self._history is not None:
                    pending_id = self._pending_history.pop(
                        (req.node_path, req.param_name), None
                    )
                    if pending_id is not None:
                        self._history.update_entry_status(pending_id, "failed")
                return
            self._dirty = False
            self._update_title()
            self._yaml_panel.set_save_button_dirty(False)
            self._yaml_panel.set_file_content(
                self._config_file.to_yaml_string(), dirty=False
            )
            self._param_panel.mark_param_file_saved(req.param_name)
            self._node_panel.set_node_restart_pending(req.node_path, True)
            # Update history entry status to "applied" (saved to file)
            if _HISTORY_AVAILABLE and self._history is not None:
                pending_id = self._pending_history.pop(
                    (req.node_path, req.param_name), None
                )
                if pending_id is not None:
                    self._history.update_entry_status(pending_id, "applied")
            logger.info(
                f"Config saved (non-hot-reload): {req.param_name} = {req.value}"
            )

    def _on_undo_requested(self, entry_id: str) -> None:
        """Undo a previously-recorded parameter change.

        Looks up the original entry, creates a reverse entry, and re-applies
        the old value to the live ROS2 node.

        Args:
            entry_id: UUID string of the history entry to undo.
        """
        if not _HISTORY_AVAILABLE or self._history is None:
            return
        undo_entry = self._history.undo_entry(entry_id)
        if undo_entry is None:
            logger.warning('_on_undo_requested: entry_id %r not found', entry_id)
            return
        self._pending_undo_map[undo_entry.entry_id] = entry_id
        req = ApplyParamRequest(
            node_path=undo_entry.ref.node_path,
            param_name=undo_entry.ref.param_name,
            value=undo_entry.new_value,
            ros2_name=undo_entry.ros2_name,
            type_hint=undo_entry.type_hint,
            hot_reload=undo_entry.hot_reload,
            source=ChangeSource.UNDO,
            history_entry_id=undo_entry.entry_id,
        )
        self._apply_param_change(req)

    def _on_compare_requested(self, left_id: str, right_id: str) -> None:
        """Build snapshots from the two selected sources and populate the compare table.

        Node paths are normalized to a canonical form (leading slash, no trailing
        slash, whitespace stripped) so that ROS2 live paths and YAML-derived paths
        match regardless of whether the YAML omits the leading slash.

        Args:
            left_id: Source identifier for the left (base) snapshot.
            right_id: Source identifier for the right (target) snapshot.
        """
        if self._compare_panel is None or not _HISTORY_AVAILABLE:
            return

        node_path = self._selected_node_path
        if not node_path:
            self.set_status("Select a node first before comparing")
            return

        left_snap = self._build_compare_snapshot(left_id, node_path, "left")
        right_snap = self._build_compare_snapshot(right_id, node_path, "right")

        if left_snap is None:
            self.set_status(f"Cannot build left snapshot from '{left_id}'")
            return
        if right_snap is None:
            self.set_status(f"Cannot build right snapshot from '{right_id}'")
            return

        diffs = diff_snapshots(left_snap, right_snap)
        self._compare_panel.show_diff(diffs)
        count = len(diffs)
        self.set_status(
            f"Compare: {count} difference(s) found" if count else "Compare: no differences found"
        )

    def _build_compare_snapshot(
        self, source_id: str, node_path: str, label: str
    ) -> "ParamSnapshot | None":
        """Return a ParamSnapshot for *source_id*, or None if unavailable.

        Normalizes the node path to canonical form ('/' + stripped segments) so
        that live paths ('/local_costmap/local_costmap') and YAML-derived paths
        ('local_costmap/local_costmap') map to the same ParamRef keys.

        Args:
            source_id: One of the built-in labels or a full filepath for Browse sources.
            node_path: The currently-selected ROS2 node path.
            label: Human-readable label for the resulting snapshot.
        """
        norm_path = "/" + node_path.strip("/").strip()

        if source_id == "Live (current node)":
            # Use _all_node_params so we always get the params for the requested node,
            # not whatever _current_params happens to hold (which may be a different
            # node if the user switched selection before params arrived).
            bare = node_path.lstrip("/")
            node_params = self._all_node_params.get(bare) or self._current_params
            if not node_params:
                return None
            return snapshot_from_param_values(norm_path, node_params, label)

        if source_id in ("Loaded YAML (current)", "Loaded YAML (original)"):
            if self._config_file is None:
                return None
            if source_id == "Loaded YAML (current)":
                params_dict = self._config_file.get_all_params_for_node(node_path)
            else:
                params_dict = self._config_file.get_all_params_for_node_original(node_path)
            if not params_dict:
                return None
            return self._yaml_dict_to_snapshot(
                norm_path, params_dict, label, self._get_schema_index()
            )

        # Any other string is a filepath from "Browse YAML file..."
        if _import_yaml_for_compare is None:
            return None
        imported = _import_yaml_for_compare(source_id)
        for raw_path, params_dict in imported.items():
            if "/" + raw_path.strip("/").strip() == norm_path:
                return self._yaml_dict_to_snapshot(
                    norm_path, params_dict, label, self._get_schema_index()
                )
        return None

    @staticmethod
    def _yaml_dict_to_snapshot(
        node_path: str,
        params_dict: dict[str, Any],
        label: str,
        schema_index: "dict[tuple[str, str], Any] | None" = None,
    ) -> "ParamSnapshot":
        """Build a ParamSnapshot from a flat {param_name: value} dict.

        Looks up each param in the schema index to get the correct type_hint
        and ros2_name.  For params not in the schema, the type is inferred from
        the Python value type.  Falls back to "string" / param_name when the
        schema index is not provided.

        Args:
            node_path: Normalized ROS2 node path (used as ParamRef.node_path).
            params_dict: Flat mapping of dot-notation param names to values.
            label: Human-readable label for the snapshot.
            schema_index: Optional dict keyed by (bare_node, param_name) →
                Nav2ParamDef.  When provided, type_hint and ros2_name are taken
                from the matching definition instead of being guessed.
        """
        # Derive the bare node name (last path segment) for schema lookup.
        bare_node = node_path.rstrip("/").rsplit("/", 1)[-1]

        def _infer_type(v: Any) -> str:
            if isinstance(v, bool):
                return "bool"
            if isinstance(v, int):
                return "integer"
            if isinstance(v, float):
                return "double"
            if isinstance(v, list):
                return "string_array"
            return "string"

        snap = ParamSnapshot(
            snapshot_id=str(uuid.uuid4()),
            label=label,
            captured_at=datetime.now(),
        )
        for param_name, value in params_dict.items():
            ref = ParamRef(node_path=node_path, param_name=param_name)
            # Try schema lookup: first by (bare_node, param_name), then by
            # (bare_node, ros2_name) for plugin-namespaced params.
            schema_def = None
            if schema_index is not None:
                schema_def = schema_index.get((bare_node, param_name))
            if schema_def is not None:
                type_hint = schema_def.type
                ros2_name = schema_def.ros2_name
            else:
                type_hint = _infer_type(value)
                ros2_name = param_name
            snap.entries[ref] = ParamSnapshotEntry(
                ref=ref,
                value=value,
                type_hint=type_hint,
                ros2_name=ros2_name,
            )
        return snap

    def _get_schema_index(self) -> "dict[tuple[str, str], Any]":
        """Return a schema index keyed by (bare_node, param_name).

        Built once and cached.  Falls back to an empty dict on import error.
        """
        if self._schema_index is not None:
            return self._schema_index
        try:
            from nav2_config.types.params import load_schema as _load_schema
            defs = _load_schema()
            self._schema_index = {(d.node, d.param): d for d in defs}
        except Exception as exc:
            logger.warning(f"Could not load schema for snapshot type inference: {exc}")
            self._schema_index = {}
        return self._schema_index

    def _on_compare_apply(self, diffs: list) -> None:
        """Apply a batch of diff entries from the compare panel.

        All entries are applied as a single batch (shared batch_id) so they
        appear grouped in the history panel.

        Args:
            diffs: List of ParamDiffEntry objects selected in the compare panel.
        """
        if not diffs:
            return
        batch_id = str(uuid.uuid4())
        for diff_entry in diffs:
            ref = getattr(diff_entry, 'ref', None)
            if ref is None:
                continue
            # ParamDiffEntry stores right_value directly (not as a nested object).
            right_value = getattr(diff_entry, 'right_value', None)
            right_type = getattr(diff_entry, 'type_hint', 'string')
            right_ros2_name = getattr(diff_entry, 'ros2_name', ref.param_name)
            # Look up hot_reload from current params; default True if not found.
            right_hot = True
            for _pv in self._current_params:
                if (_pv.definition.ros2_name == right_ros2_name
                        and _pv.node_path == ref.node_path):
                    right_hot = _pv.definition.hot_reload
                    break
            req = ApplyParamRequest(
                node_path=ref.node_path,
                param_name=ref.param_name,
                value=right_value,
                ros2_name=right_ros2_name,
                type_hint=right_type,
                hot_reload=right_hot,
                source=ChangeSource.COMPARE_APPLY if _HISTORY_AVAILABLE else None,
                batch_id=batch_id,
            )
            self._apply_param_change(req)

    # ------------------------------------------------------------------
    # Lifecycle action slots
    # ------------------------------------------------------------------

    def _on_lifecycle_states_updated_for_param_panel(
        self, states: dict[str, str]
    ) -> None:
        """Forward lifecycle state updates to the param panel's lifecycle bar."""
        current = self._param_panel._node_name
        if current and current in states:
            node = self._topology_nodes.get(current)
            stack_has_manager = (
                self._stack_has_manager(node.stack_namespace)
                if node is not None
                else self._lifecycle_manager_present
            )
            self._param_panel.update_lifecycle_state(
                current, states[current], stack_has_manager
            )

    def _on_pause_stack(self) -> None:
        """Handler for Pause Stack button — fire immediately, no confirmation."""
        self._node.request_lifecycle_pause_stack()
        self.set_status('Pausing Nav2 stack...')

    def _on_resume_stack(self) -> None:
        """Handler for Resume Stack button — fire immediately, no confirmation."""
        self._node.request_lifecycle_resume_stack()
        self.set_status('Resuming Nav2 stack...')

    def _on_lifecycle_manager_status(self, present: bool, manager_path: str) -> None:
        """Called when lifecycle_manager presence changes."""
        self._lifecycle_manager_present = present
        self._node_panel.set_lifecycle_manager_present(present)
        # Refresh the param panel's lifecycle bar with the updated manager state.
        current = self._param_panel._node_name
        if current:
            known_state = self._node.get_lifecycle_state(current)
            node = self._topology_nodes.get(current)
            stack_has_manager = (
                self._stack_has_manager(node.stack_namespace)
                if node is not None
                else present
            )
            self._param_panel.update_lifecycle_state(current, known_state, stack_has_manager)
        if present:
            bare = manager_path.lstrip('/')
            self.set_status(f'lifecycle_manager detected: /{bare} — stack-level restart enabled')
        else:
            self.set_status('lifecycle_manager not found — direct node lifecycle control enabled')

    def set_expert_mode(self, enabled: bool) -> None:
        """Propagate expert mode to both panels."""
        self._expert_mode = enabled
        self._node_panel.set_expert_mode(enabled)
        self._param_panel.set_expert_mode(enabled)

    def _on_expert_mode_toggled(self, checked: bool) -> None:
        """Handle Expert Mode checkbox toggle."""
        if checked and self._lifecycle_manager_present and not self._expert_mode_warned:
            self._expert_mode_warned = True
            QMessageBox.warning(
                self,
                'Expert Mode',
                'Expert Mode enables direct per-node lifecycle transitions, '
                'bypassing lifecycle_manager.\n\n'
                'This can cause CRITICAL FAILURE and bring down the Nav2 stack.\n\n'
                'Only use this for manual recovery of stuck nodes.',
            )
        self.set_expert_mode(checked)

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
            dialog = _RestartAllProgressDialog(1, signals=self._node.signals, parent=self)
            self._attach_restart_dialog(dialog, clear_node=node_path)
            _node_info = self._topology_nodes.get(node_path)
            if _node_info is not None:
                self._node.request_lifecycle_restart_stack_ns(_node_info.stack_namespace)
            else:
                logger.warning(
                    'Could not find topology entry for %s; falling back to global restart',
                    node_path,
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
                try:
                    self._node.signals.lifecycle_progress.disconnect(_on_progress)
                except (RuntimeError, TypeError):
                    pass
                try:
                    self._node.signals.lifecycle_change_result.disconnect(_on_result)
                except (RuntimeError, TypeError):
                    pass
                if success:
                    self._node_panel.set_node_restart_pending(node_path, False)

        self._node.signals.lifecycle_change_result.connect(_on_result)

    def _on_amcl_pose_status(self, message: str) -> None:
        """Update the status bar with AMCL pose preservation progress."""
        self.set_status(message, 10000)

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
            dialog = _RestartAllProgressDialog(1, signals=self._node.signals, parent=self)
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

        dialog = _RestartAllProgressDialog(discovered_count, signals=self._node.signals, parent=self)
        self._node.signals.lifecycle_progress.connect(dialog.on_progress)
        self._node.signals.lifecycle_change_result.connect(dialog.on_result)
        self._node.request_lifecycle_restart_all()
        dialog.show()

    def _on_search_changed(self, text: str) -> None:
        """Forward the search field text to the param panel filter."""
        self._param_panel.filter_params(text)

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
            '<tr><td><b>Ctrl+O</b></td><td>Load config file</td></tr>'
            '<tr><td><b>Ctrl+S</b></td><td>Save config</td></tr>'
            '<tr><td><b>Ctrl+Shift+S</b></td><td>Save config as...</td></tr>'
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
        from PyQt6.QtCore import QT_VERSION_STR
        python_version = (
            f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
        )

        dialog = QDialog(self)
        dialog.setWindowTitle('About nav2_config')
        dialog.setFixedSize(400, 260)

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
        ros2_line = f'ROS2: {_ROS_DISTRO}'
        python_line = f'Python: {python_version}'
        qt_line = f'Qt: {QT_VERSION_STR}'
        info.setHtml(
            '<p>Built by <b>Sutharsan</b><br>'
            'A ROS2 desktop GUI for live Nav2 parameter tuning. '
            'No node restarts required.</p>'
            f'<p>{ros2_line}<br>{python_line}<br>{qt_line}</p>'
        )
        info.setMaximumHeight(110)
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
                val = state['show_descriptions']
                self._toggle_desc_action.setChecked(val)
                self._param_panel._desc_btn.setChecked(val)
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
    # Public helpers
    # ------------------------------------------------------------------

    def set_status(self, message: str, timeout_ms: int = 5000) -> None:
        """Update the center status bar message.

        Args:
            message: Text to display.
            timeout_ms: Auto-clear after this many ms (0 = permanent).
        """
        self._status_bar.showMessage(message, timeout_ms)
