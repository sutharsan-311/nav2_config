"""YamlPanel — right panel: live YAML preview with syntax highlighting.

Displays the current parameter set as a nav2_params.yaml preview.
Includes a QSyntaxHighlighter for YAML tokens and a Copy button.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nav2_config.types.params import ParamValue
from nav2_config.core.yaml_exporter import export_yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Syntax highlighter
# ---------------------------------------------------------------------------

class _YamlHighlighter(QSyntaxHighlighter):
    """Minimal YAML syntax highlighter for the preview pane.

    Token colours match the CLAUDE.md palette:
      Keys      — #4fc3f7  (ROS2 blue)
      Numbers   — #4caf50  (green)
      Booleans  — #4caf50  (green)
      Strings   — #f57c00  (ROS orange)
      Comments  — #808080  (muted gray)
    """

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._comment_fmt = self._make_fmt('#808080')
        self._build_rules()

    @staticmethod
    def _make_fmt(color: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        return fmt

    def _build_rules(self) -> None:
        # Booleans — before generic number/string rules.
        self._rules.append((
            QRegularExpression(r'\b(true|false|yes|no)\b'),
            self._make_fmt('#4caf50'),
        ))
        # Numbers: integers and floats (including negative and scientific).
        self._rules.append((
            QRegularExpression(r'(?<![:\w])-?\b\d+(\.\d+)?([eE][+-]?\d+)?\b'),
            self._make_fmt('#4caf50'),
        ))
        # YAML keys: word characters followed by a colon at any indent level.
        # Match the key portion only (not the colon).
        self._rules.append((
            QRegularExpression(r'^[ \t]*[\w._\-]+(?=\s*:)'),
            self._make_fmt('#4fc3f7'),
        ))
        # Double-quoted strings.
        self._rules.append((
            QRegularExpression(r'"(?:[^"\\]|\\.)*"'),
            self._make_fmt('#f57c00'),
        ))
        # Single-quoted strings.
        self._rules.append((
            QRegularExpression(r"'[^']*'"),
            self._make_fmt('#f57c00'),
        ))
        # Comments are applied last so they override everything on their span.
        self._rules.append((
            QRegularExpression(r'#[^\n]*'),
            self._comment_fmt,
        ))

    def highlightBlock(self, text: str) -> None:
        """Apply all rules to a single line of text."""
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)


# ---------------------------------------------------------------------------
# YamlPanel widget
# ---------------------------------------------------------------------------

class YamlPanel(QWidget):
    """Right panel showing a live, read-only YAML preview of loaded parameters.

    Call :meth:`update_yaml` whenever the parameter list changes.
    Call :meth:`set_current_node` to auto-scroll to a node's section.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_node: str = ''
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_title_bar())

        self._editor = QPlainTextEdit()
        self._editor.setReadOnly(True)

        mono = QFont()
        mono.setFamily('Consolas')
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._editor.setFont(mono)

        self._editor.setStyleSheet(
            'QPlainTextEdit {'
            '    background: #1e1e1e;'
            '    color: #d4d4d4;'
            '    border: none;'
            '    selection-background-color: #264f78;'
            '}'
        )
        layout.addWidget(self._editor, stretch=1)

        self._highlighter = _YamlHighlighter(self._editor.document())

        # Show placeholder text before any node is selected.
        self._editor.setPlainText(
            '# Generated by nav2_config\n'
            '# Select a node in the left panel to preview its parameters.\n'
        )
        self._update_title(2)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet('background: #252526; border-bottom: 1px solid #3e3e42;')

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._title_label = QLabel('YAML PREVIEW')
        self._title_label.setProperty('role', 'heading')
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title_label)

        layout.addStretch()

        copy_btn = QPushButton('Copy')
        copy_btn.setFixedHeight(18)
        copy_btn.setStyleSheet(
            'QPushButton {'
            '    background: #2d2d2d; border: 1px solid #3e3e42;'
            '    color: #d4d4d4; font-size: 10px; padding: 0 6px;'
            '}'
            'QPushButton:hover { background: #3e3e42; }'
            'QPushButton:pressed { background: #f57c00; color: #ffffff; }'
        )
        copy_btn.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(copy_btn)

        return bar

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_title(self, line_count: int) -> None:
        self._title_label.setText(f'YAML PREVIEW  ·  {line_count} lines')

    def _copy_to_clipboard(self) -> None:
        """Copy the full YAML text to the system clipboard."""
        QApplication.clipboard().setText(self._editor.toPlainText())

    def _scroll_to_node(self, node_name: str) -> None:
        """Scroll the editor to the section that starts with *node_name*."""
        bare = node_name.lstrip('/')
        doc: QTextDocument = self._editor.document()

        # Try to find the node as a top-level YAML key (bare word + colon).
        cursor = doc.find(f'\n{bare}:')
        if cursor.isNull():
            # Handle case where the node is the very first entry in the file.
            cursor = doc.find(f'{bare}:')
        if not cursor.isNull():
            self._editor.setTextCursor(cursor)
            self._editor.ensureCursorVisible()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_yaml(
        self,
        params: list[ParamValue],
        plugin_filter: str | None = None,
    ) -> None:
        """Regenerate the YAML preview from the current parameter values.

        Safe to call repeatedly as params change — diffs are handled by Qt's
        document model.

        Args:
            params: Current parameter values (read-only; may be modified
                in-place by the param panel).
            plugin_filter: If set, only params matching this plugin are shown.
        """
        yaml_str = export_yaml(params, plugin_filter=plugin_filter)
        self._editor.setPlainText(yaml_str)

        line_count = yaml_str.count('\n') + 1
        self._update_title(line_count)

        if self._current_node:
            self._scroll_to_node(self._current_node)

    def set_current_node(self, node_name: str) -> None:
        """Track the selected node and scroll to its section in the preview.

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.
        """
        self._current_node = node_name
        if node_name:
            self._scroll_to_node(node_name)
