# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Central icon provider for nav2_config.

Icons are sourced from the local ROS2 installation (RViz2 icons), with
fallbacks to Qt standard icons and programmatically-drawn pixmaps.

Preference order:
  1. RViz2 PNG/SVG files copied into resources/icons/
  2. QIcon.fromTheme() — system theme icons (works on Ubuntu/GNOME)
  3. QStyle.StandardPixmap — Qt built-in cross-platform icons
  4. Programmatically drawn QPixmap (colored dots, letters)
"""

import os

from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QStyle

from nav2_config.core.node_discovery import path_basename

_ICON_DIR = os.path.join(os.path.dirname(__file__), '..', 'resources', 'icons')


def _rviz(filename: str) -> QIcon:
    """Load an icon from resources/icons/ by exact filename (with extension)."""
    path = os.path.join(_ICON_DIR, filename)
    if os.path.isfile(path):
        return QIcon(path)
    return QIcon()


def _theme(name: str) -> QIcon:
    """Return a theme icon; null QIcon if not found."""
    return QIcon.fromTheme(name)


def _std(key: 'QStyle.StandardPixmap') -> QIcon:
    """Return a Qt standard icon."""
    return QApplication.style().standardIcon(key)


def _rviz_or_theme(filename: str, theme_name: str) -> QIcon:
    icon = _rviz(filename)
    if not icon.isNull():
        return icon
    return _theme(theme_name)


def _rviz_or_std(filename: str, fallback: 'QStyle.StandardPixmap') -> QIcon:
    icon = _rviz(filename)
    if not icon.isNull():
        return icon
    return _std(fallback)


def _theme_or_std(name: str, fallback: 'QStyle.StandardPixmap') -> QIcon:
    icon = _theme(name)
    if not icon.isNull():
        return icon
    return _std(fallback)


def _dot(color: str, size: int = 16) -> QIcon:
    """Solid filled circle icon in *color*."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    margin = max(1, size // 8)
    p.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    p.end()
    return QIcon(px)


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

def toolbar_import() -> QIcon:
    # No RViz2 open-file icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_DialogOpenButton)


def toolbar_export() -> QIcon:
    # No RViz2 save icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_DialogSaveButton)


def toolbar_refresh() -> QIcon:
    # rviz_rotate.svg is the RViz2 rotate/refresh icon
    return _rviz_or_std('rviz_rotate.svg', QStyle.StandardPixmap.SP_BrowserReload)


def toolbar_health() -> QIcon:
    # warning.png is from rviz_common/icons/
    return _rviz_or_std('warning.png', QStyle.StandardPixmap.SP_MessageBoxWarning)


def toolbar_restart() -> QIcon:
    # rviz_rotate.svg is the RViz2 rotate/refresh icon
    return _rviz_or_std('rviz_rotate.svg', QStyle.StandardPixmap.SP_BrowserReload)


def toolbar_load_config() -> QIcon:
    # No RViz2 open-file icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_DialogOpenButton)


def toolbar_save() -> QIcon:
    # No RViz2 save icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_DialogSaveButton)


def toolbar_search() -> QIcon:
    # zoom.svg is from rviz_common/icons/ — magnifying-glass shape suits search
    return _rviz_or_std('zoom.svg', QStyle.StandardPixmap.SP_FileDialogContentsView)


# ---------------------------------------------------------------------------
# Menu bar
# ---------------------------------------------------------------------------

def menu_open() -> QIcon:
    return _theme_or_std('document-open', QStyle.StandardPixmap.SP_DialogOpenButton)


def menu_save() -> QIcon:
    return _theme_or_std('document-save', QStyle.StandardPixmap.SP_DialogSaveButton)


def menu_save_as() -> QIcon:
    return _theme_or_std('document-save-as', QStyle.StandardPixmap.SP_DialogSaveButton)


def menu_export() -> QIcon:
    return _theme_or_std('document-send', QStyle.StandardPixmap.SP_ArrowRight)


def menu_import() -> QIcon:
    return _theme_or_std('document-revert', QStyle.StandardPixmap.SP_ArrowLeft)


def menu_quit() -> QIcon:
    return _theme_or_std('application-exit', QStyle.StandardPixmap.SP_DialogCloseButton)


def menu_undo() -> QIcon:
    return _theme_or_std('edit-undo', QStyle.StandardPixmap.SP_ArrowBack)


def menu_redo() -> QIcon:
    return _theme_or_std('edit-redo', QStyle.StandardPixmap.SP_ArrowForward)


def menu_reset() -> QIcon:
    return _theme_or_std('edit-clear', QStyle.StandardPixmap.SP_DialogResetButton)


def menu_refresh() -> QIcon:
    # rviz_rotate.svg is from rviz_common/icons/
    return _rviz_or_theme('rviz_rotate.svg', 'view-refresh')


def menu_descriptions() -> QIcon:
    return _theme('format-justify-left')


def menu_shortcuts() -> QIcon:
    return _theme('preferences-desktop-keyboard')


def menu_about() -> QIcon:
    return _theme_or_std('help-about', QStyle.StandardPixmap.SP_MessageBoxInformation)


# ---------------------------------------------------------------------------
# Node status dots
# ---------------------------------------------------------------------------

def status_active() -> QIcon:
    return _dot('#4caf50')    # green


def status_inactive() -> QIcon:
    return _dot('#ff9800')    # amber


def status_unconfigured() -> QIcon:
    return _dot('#999999')    # gray


def status_error() -> QIcon:
    return _dot('#e53935')    # red


def status_disconnected() -> QIcon:
    return _dot('#e53935', 10)


def status_connected() -> QIcon:
    return _dot('#4caf50', 10)


def status_pending() -> QIcon:
    return _dot('#ff6d00', 8)   # orange, small


# ---------------------------------------------------------------------------
# Node type icons — RViz2 class icons mapped to Nav2 nodes
# ---------------------------------------------------------------------------
#
# Source: /opt/ros/humble/share/rviz_default_plugins/icons/classes/
#
# Mapping rationale:
#   AMCL              → PoseArray  (publishes a particle cloud = array of poses)
#   controller_server → TwistStamped (outputs velocity commands)
#   planner_server    → Path       (outputs a global path)
#   bt_navigator      → MarkerArray (publishes BT visualization markers)
#   local_costmap     → GridCells  (costmap cells = occupancy grid)
#   global_costmap    → Map        (global occupancy map)
#   smoother_server   → Path       (outputs a smoothed path)
#   velocity_smoother → TwistStamped (smooths velocity commands)
#   behavior_server   → Wrench     (recovery behaviors / actuator forces)
#   waypoint_follower → Pose       (each waypoint is a target pose)
#   map_server        → Map        (serves the static map)

_NODE_RVIZ_ICON: dict[str, str] = {
    'amcl':              'PoseArray.png',
    'controller_server': 'TwistStamped.png',
    'planner_server':    'Path.png',
    'bt_navigator':      'MarkerArray.png',
    'local_costmap':     'GridCells.png',
    'global_costmap':    'Map.png',
    'smoother_server':   'Path.png',
    'velocity_smoother': 'TwistStamped.png',
    'behavior_server':   'Wrench.png',
    'waypoint_follower': 'Pose.png',
    'map_server':        'Map.png',
}

# System theme fallbacks (used when RViz2 PNG fails to load)
_NODE_THEME_MAP: dict[str, str] = {
    'amcl':              'find-location',
    'controller_server': 'media-playback-start',
    'planner_server':    'go-jump',
    'bt_navigator':      'preferences-system',
    'local_costmap':     'view-grid',
    'global_costmap':    'view-grid',
    'smoother_server':   'draw-freehand',
    'velocity_smoother': 'go-next',
    'behavior_server':   'system-run',
    'waypoint_follower': 'flag',
    'map_server':        'image-x-generic',
}

# Letter for the final programmatic fallback
_NODE_LETTER_MAP: dict[str, str] = {
    'amcl':              'A',
    'controller_server': 'C',
    'planner_server':    'P',
    'bt_navigator':      'B',
    'local_costmap':     'L',
    'global_costmap':    'G',
    'smoother_server':   'S',
    'velocity_smoother': 'V',
    'behavior_server':   'R',
    'waypoint_follower': 'W',
    'map_server':        'M',
}

_NODE_ICON_CACHE: dict[tuple[str, bool], QIcon] = {}


def _letter_icon(letter: str, active: bool, size: int = 16) -> QIcon:
    """Colored circle with a letter inside — last-resort fallback."""
    bg = '#4caf50' if active else '#999999'
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.setPen(QColor('#ffffff'))
    font = QFont()
    font.setPointSize(max(6, size // 3))
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, letter)
    p.end()
    return QIcon(px)


def node_icon(node_path: str, active: bool) -> QIcon:
    """Return a meaningful icon for *node_path*.

    Tries the RViz2 class PNG first, then system theme, then a colored
    letter circle as a last resort.
    """
    cache_key = (node_path, active)
    if cache_key in _NODE_ICON_CACHE:
        return _NODE_ICON_CACHE[cache_key]

    icon: QIcon | None = None
    basename = path_basename(node_path)

    # 1. RViz2 PNG
    rviz_filename = _NODE_RVIZ_ICON.get(basename)
    if rviz_filename:
        candidate = _rviz(rviz_filename)
        if not candidate.isNull():
            icon = candidate

    # 2. System theme icon
    if icon is None:
        theme_name = _NODE_THEME_MAP.get(basename)
        if theme_name:
            candidate = _theme(theme_name)
            if not candidate.isNull():
                icon = candidate

    # 3. Colored letter fallback
    if icon is None:
        letter = _NODE_LETTER_MAP.get(basename, basename[:1].upper() or '?')
        icon = _letter_icon(letter, active)

    _NODE_ICON_CACHE[cache_key] = icon
    return icon


# ---------------------------------------------------------------------------
# Category section icons
# ---------------------------------------------------------------------------

_CATEGORY_THEME_MAP: dict[str, str] = {
    'base':        'preferences-system',
    'followpath':  'media-playback-start',
    'controller':  'media-playback-start',
    'gridbase':    'go-jump',
    'smac':        'go-jump',
    'planner':     'go-jump',
    'thetastar':   'go-jump',
    'inflation':   'zoom-out',
    'obstacle':    'dialog-warning',
    'voxel':       'view-grid',
    'static':      'image-x-generic',
    'velocity':    'go-next',
    'safety':      'security-high',
    'connectivity': 'network-wired',
    'topics':      'network-wired',
    'frames':      'preferences-desktop-display',
    'general':     'preferences-system',
    'recovery':    'view-refresh',
    'behavior':    'system-run',
    'waypoint':    'flag',
    'costmap':     'view-grid',
    'performance': 'media-playback-start',
}


def category_icon(category: str) -> QIcon | None:
    """Return a theme icon for a parameter category, or None if unavailable."""
    key = category.lower().replace('_', '').replace(' ', '')
    for prefix, theme_name in _CATEGORY_THEME_MAP.items():
        if key.startswith(prefix):
            icon = _theme(theme_name)
            if not icon.isNull():
                return icon
    return None


# ---------------------------------------------------------------------------
# YAML panel buttons
# ---------------------------------------------------------------------------

def yaml_copy() -> QIcon:
    # No RViz2 copy icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_FileLinkIcon)


def yaml_save() -> QIcon:
    # No RViz2 save icon — use Qt standard
    return _std(QStyle.StandardPixmap.SP_DialogSaveButton)


# ---------------------------------------------------------------------------
# Application window icon
# ---------------------------------------------------------------------------

def app_icon() -> QIcon:
    """'N2' on a ROS2 blue background."""
    size = 64
    px = QPixmap(size, size)
    px.fill(QColor('#2a82da'))
    p = QPainter(px)
    p.setPen(QColor('#ffffff'))
    font = QFont()
    font.setPointSize(22)
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRect(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, 'N2')
    p.end()
    return QIcon(px)
