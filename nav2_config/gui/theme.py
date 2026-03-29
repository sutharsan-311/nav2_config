# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""RViz2 light theme for nav2_config using Qt Fusion style + QPalette.

Matches RViz2's actual appearance: light gray Qt Fusion application with a
standard light palette. A ROS developer sitting next to RViz2 should feel
instantly at home.
"""

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def create_rviz_palette() -> QPalette:
    """Return a light QPalette matching RViz2's default Qt appearance."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor('#e8e8e8'))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor('#1a1a1a'))
    palette.setColor(QPalette.ColorRole.Base,            QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor('#f5f5f5'))
    palette.setColor(QPalette.ColorRole.Text,            QColor('#1a1a1a'))
    palette.setColor(QPalette.ColorRole.Button,          QColor('#e0e0e0'))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor('#1a1a1a'))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor('#3399ff'))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor('#ffffdc'))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor('#1a1a1a'))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor('#999999'))
    palette.setColor(QPalette.ColorRole.Mid,             QColor('#c0c0c0'))
    palette.setColor(QPalette.ColorRole.Dark,            QColor('#b0b0b0'))
    palette.setColor(QPalette.ColorRole.Shadow,          QColor('#808080'))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor('#ffffff'))
    palette.setColor(QPalette.ColorRole.Link,            QColor('#3399ff'))

    # Disabled state
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor('#999999')
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor('#999999')
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor('#999999')
    )

    return palette


def apply_theme(app: QApplication) -> None:
    """Apply the RViz2-accurate light theme to the QApplication."""
    app.setStyle('Fusion')
    app.setPalette(create_rviz_palette())
    # Minimal QSS for structural fine-tuning only — not a full theme override.
    app.setStyleSheet(
        'QSplitter::handle { background: #c0c0c0; }'
        'QSplitter::handle:horizontal { width: 2px; }'
        'QSplitter::handle:vertical { height: 2px; }'
        'QSplitter::handle:hover { background: #3399ff; }'
        'QStatusBar { border-top: 1px solid #c0c0c0; }'
        'QToolBar { border-bottom: 1px solid #c0c0c0; spacing: 4px; padding: 2px 4px; }'
        'QHeaderView::section {'
        '    background-color: #d8d8d8;'
        '    border: none;'
        '    border-bottom: 1px solid #c0c0c0;'
        '    border-right: 1px solid #c0c0c0;'
        '    padding: 2px 6px;'
        '}'
        'QTreeWidget { alternate-background-color: #f5f5f5; }'
        'QTreeWidget::item { height: 24px; padding: 0 2px; }'
        'QListWidget { alternate-background-color: #f5f5f5; }'
        'QPlainTextEdit, QTextEdit {'
        '    font-family: "Ubuntu Mono", "DejaVu Sans Mono", "Courier New", monospace;'
        '    font-size: 9pt;'
        '}'
    )
