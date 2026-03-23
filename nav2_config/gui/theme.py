"""Dark theme QSS stylesheet for nav2_config.

Designed to match the ROS tool aesthetic: RViz2, rqt, Foxglove.
Flat rectangles, dense layout, monospace data, ROS orange accents.
"""

from PyQt6.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
# BG_DARK    — deepest background (editor areas, tree views)
# BG_MID     — panel / widget backgrounds
# BG_LIGHT   — hover / selection highlight
# BORDER     — thin separator lines
# FG         — primary text
# FG_DIM     — secondary / placeholder text
# ACCENT_ORN — ROS orange: active selection, buttons
# ACCENT_BLU — ROS2 blue: focus ring, active indicators
# OK         — healthy / connected green
# ERR        — error / disconnected red

DARK_THEME_QSS: str = """
/* ── Global reset ───────────────────────────────────────────────────────── */
QWidget {
    background-color: #1e1e1e;
    color: #d4d4d4;
    font-family: "Segoe UI", "Ubuntu", "Helvetica Neue", sans-serif;
    font-size: 13px;
    border: none;
    outline: none;
}

/* ── Labels ─────────────────────────────────────────────────────────────── */
QLabel {
    color: #d4d4d4;
    background: transparent;
    font-weight: normal;
}

QLabel[role="heading"] {
    color: #f57c00;
    font-size: 11px;
    font-weight: bold;
    letter-spacing: 1px;
    text-transform: uppercase;
}

QLabel[role="dim"] {
    color: #6d6d6d;
    font-size: 12px;
}

/* ── Push buttons ────────────────────────────────────────────────────────── */
QPushButton {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 4px 12px;
    min-height: 24px;
}

QPushButton:hover {
    background-color: #3e3e42;
    border-color: #555558;
}

QPushButton:pressed {
    background-color: #252526;
}

QPushButton:disabled {
    color: #555558;
    border-color: #2d2d2d;
}

QPushButton[role="primary"] {
    background-color: #f57c00;
    border-color: #e65100;
    color: #ffffff;
    font-weight: bold;
}

QPushButton[role="primary"]:hover {
    background-color: #ff8f00;
}

/* ── Line edits ──────────────────────────────────────────────────────────── */
QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 3px 6px;
    selection-background-color: #f57c00;
    selection-color: #ffffff;
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
}

QLineEdit:focus {
    border-color: #4fc3f7;
}

QLineEdit:disabled {
    color: #555558;
    background-color: #252526;
}

/* ── Combo boxes ─────────────────────────────────────────────────────────── */
QComboBox {
    background-color: #2d2d2d;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 3px 6px;
    min-height: 22px;
}

QComboBox:hover {
    border-color: #555558;
}

QComboBox:focus {
    border-color: #4fc3f7;
}

QComboBox::drop-down {
    border: none;
    width: 20px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #d4d4d4;
    width: 0;
    height: 0;
    margin-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #252526;
    border: 1px solid #3e3e42;
    selection-background-color: #f57c00;
    selection-color: #ffffff;
    outline: none;
}

/* ── Scroll bars ─────────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #1e1e1e;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #3e3e42;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #555558;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}

QScrollBar:horizontal {
    background: #1e1e1e;
    height: 8px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #3e3e42;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover {
    background: #555558;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}

/* ── Splitter ────────────────────────────────────────────────────────────── */
QSplitter::handle {
    background: #3e3e42;
}

QSplitter::handle:horizontal {
    width: 2px;
}

QSplitter::handle:vertical {
    height: 2px;
}

QSplitter::handle:hover {
    background: #4fc3f7;
}

/* ── Tree widget ─────────────────────────────────────────────────────────── */
QTreeWidget {
    background-color: #252526;
    border: none;
    outline: none;
    alternate-background-color: #2a2d2e;
}

QTreeWidget::item {
    padding: 3px 4px;
}

QTreeWidget::item:hover {
    background-color: #2a2d2e;
}

QTreeWidget::item:selected {
    background-color: #f57c00;
    color: #ffffff;
}

QTreeWidget::branch {
    background: #252526;
}

QHeaderView::section {
    background-color: #252526;
    border: none;
    border-bottom: 1px solid #3e3e42;
    color: #6d6d6d;
    font-size: 11px;
    padding: 4px 6px;
    font-weight: normal;
}

/* ── Scroll area ─────────────────────────────────────────────────────────── */
QScrollArea {
    border: none;
    background: transparent;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {
    background-color: #252526;
    color: #6d6d6d;
    border-top: 1px solid #3e3e42;
    font-size: 12px;
}

QStatusBar::item {
    border: none;
}

/* ── Menu bar ────────────────────────────────────────────────────────────── */
QMenuBar {
    background-color: #252526;
    color: #d4d4d4;
    border-bottom: 1px solid #3e3e42;
    spacing: 0;
}

QMenuBar::item {
    padding: 4px 12px;
    background: transparent;
}

QMenuBar::item:selected {
    background-color: #3e3e42;
}

QMenuBar::item:pressed {
    background-color: #f57c00;
    color: #ffffff;
}

/* ── Menus ───────────────────────────────────────────────────────────────── */
QMenu {
    background-color: #252526;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
}

QMenu::item {
    padding: 5px 24px 5px 12px;
}

QMenu::item:selected {
    background-color: #f57c00;
    color: #ffffff;
}

QMenu::separator {
    height: 1px;
    background: #3e3e42;
    margin: 2px 0;
}

/* ── Sliders ─────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    background: #3e3e42;
    height: 4px;
}

QSlider::handle:horizontal {
    background: #4fc3f7;
    width: 12px;
    height: 12px;
    margin: -4px 0;
}

QSlider::handle:horizontal:hover {
    background: #f57c00;
}

QSlider::sub-page:horizontal {
    background: #4fc3f7;
}

/* ── Check boxes ─────────────────────────────────────────────────────────── */
QCheckBox {
    spacing: 6px;
    color: #d4d4d4;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #3e3e42;
    background: #1e1e1e;
}

QCheckBox::indicator:checked {
    background: #f57c00;
    border-color: #f57c00;
}

QCheckBox::indicator:hover {
    border-color: #4fc3f7;
}

/* ── Group boxes ─────────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #3e3e42;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 11px;
    color: #6d6d6d;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 4px;
    color: #f57c00;
}

/* ── Tool tips ───────────────────────────────────────────────────────────── */
QToolTip {
    background-color: #252526;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    padding: 4px 8px;
    font-size: 12px;
}

/* ── Monospace data areas (YAML, param values) ───────────────────────────── */
QPlainTextEdit, QTextEdit {
    background-color: #1e1e1e;
    border: 1px solid #3e3e42;
    color: #d4d4d4;
    font-family: "Consolas", "JetBrains Mono", "Courier New", monospace;
    font-size: 12px;
    selection-background-color: #f57c00;
    selection-color: #ffffff;
}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the ROS-tool dark theme to the QApplication."""
    app.setStyleSheet(DARK_THEME_QSS)
