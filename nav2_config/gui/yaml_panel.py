"""YamlPanel — right panel: live YAML preview with VS Code-style syntax highlighting.

Styled to match RViz2's panel headers (light gray, 28px) with a white editor
area. Syntax colors match VS Code Light for familiarity.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import Qt, QRegularExpression, pyqtSignal
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

# RViz2 light panel colors
_BG_HDR  = '#d0d0d0'
_BG_EDIT = '#ffffff'
_BORDER  = '#c0c0c0'
_FG      = '#1a1a1a'
_FG_DIM  = '#666666'


# ---------------------------------------------------------------------------
# Syntax highlighter — VS Code Dark+ palette
# ---------------------------------------------------------------------------

class _YamlHighlighter(QSyntaxHighlighter):
    """YAML syntax highlighter using VS Code Light colors.

    Keys      — #0000cc  (dark blue)
    Numbers   — #098658  (dark green)
    Booleans  — #0000cc  (same as keys)
    Strings   — #a31515  (dark red)
    Comments  — #008000  (green)
    Pending   — #1565c0  (blue, whole line) when line contains ``# (pending)``
    """

    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self._pending_fmt = self._make_fmt('#1565c0', bold=True)
        self._build_rules()

    @staticmethod
    def _make_fmt(color: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(700)
        return fmt

    def _build_rules(self) -> None:
        # Comments override everything on their span — add last.
        # Booleans first (before generic key/number rules).
        self._rules.append((
            QRegularExpression(r'\b(true|false|yes|no|True|False)\b'),
            self._make_fmt('#0000cc'),
        ))
        # Numbers: integers, floats, negative, scientific notation.
        self._rules.append((
            QRegularExpression(r'(?<![:\w])-?\b\d+(\.\d+)?([eE][+-]?\d+)?\b'),
            self._make_fmt('#098658'),
        ))
        # YAML keys: identifier followed by a colon.
        self._rules.append((
            QRegularExpression(r'^[ \t]*[\w._\-]+(?=\s*:)'),
            self._make_fmt('#0000cc'),
        ))
        # Double-quoted strings.
        self._rules.append((
            QRegularExpression(r'"(?:[^"\\]|\\.)*"'),
            self._make_fmt('#a31515'),
        ))
        # Single-quoted strings.
        self._rules.append((
            QRegularExpression(r"'[^']*'"),
            self._make_fmt('#a31515'),
        ))
        # Comments — applied last so they override all prior spans.
        self._rules.append((
            QRegularExpression(r'#[^\n]*'),
            self._make_fmt('#008000'),
        ))

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)
        # Pending params: override the whole line with blue so they stand out.
        if '# (pending)' in text:
            self.setFormat(0, len(text), self._pending_fmt)


# ---------------------------------------------------------------------------
# YamlPanel widget
# ---------------------------------------------------------------------------

class YamlPanel(QWidget):
    """Right panel: YAML preview — shows file content when a config file is loaded,
    or a generated per-node preview otherwise.

    Signals:
        save_requested(): emitted when the user clicks the Save button.
    """

    save_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_node: str = ''
        self._file_mode: bool = False  # True while showing config-file content
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
        self._editor.setStyleSheet(
            f'QPlainTextEdit {{'
            f'    background: {_BG_EDIT};'
            f'    color: {_FG};'
            f'    border: none;'
            f'    selection-background-color: #3399ff;'
            f'}}'
        )

        mono = QFont()
        mono.setFamily('Ubuntu Mono')
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(9)
        self._editor.setFont(mono)

        layout.addWidget(self._editor, stretch=1)
        self._highlighter = _YamlHighlighter(self._editor.document())

        self._editor.setPlainText(
            '# Generated by nav2_config\n'
            '# Select a node in the left panel to preview its parameters.\n'
        )
        self._update_title(2)

    def _make_title_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; border-bottom: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        self._title_label = QLabel('YAML Output')
        self._title_label.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; background: transparent;'
        )
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._title_label)

        layout.addStretch()

        self._line_count_label = QLabel('')
        self._line_count_label.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 9pt; background: transparent;'
        )
        self._line_count_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._line_count_label)

        self._save_btn = QPushButton('Save')
        self._save_btn.setFixedHeight(20)
        self._save_btn.setToolTip('Save config file  (Ctrl+S)')
        self._save_btn.setVisible(False)
        self._save_btn.setStyleSheet(
            'QPushButton { background: #2a82da; color: #ffffff; '
            'border: 1px solid #1a6abf; font-size: 9pt; font-weight: bold; padding: 0 8px; }'
            'QPushButton:hover { background: #1e70c8; }'
            'QPushButton:pressed { background: #155d9e; }'
            'QPushButton:disabled { background: #e0e0e0; color: #999; border-color: #c0c0c0; }'
        )
        self._save_btn.clicked.connect(self.save_requested.emit)
        layout.addWidget(self._save_btn)

        copy_btn = QPushButton('Copy')
        copy_btn.setFixedHeight(20)
        copy_btn.setToolTip('Copy YAML to clipboard')
        copy_btn.setStyleSheet(
            f'QPushButton:pressed {{ background: #3399ff; color: #ffffff; '
            f'border-color: #2277cc; }}'
        )
        copy_btn.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(copy_btn)

        return bar

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_title(self, line_count: int) -> None:
        self._line_count_label.setText(f'{line_count} lines')

    def _copy_to_clipboard(self) -> None:
        QApplication.clipboard().setText(self._editor.toPlainText())

    def _scroll_to_node(self, node_name: str) -> None:
        bare = node_name.lstrip('/')
        doc: QTextDocument = self._editor.document()
        cursor = doc.find(f'\n{bare}:')
        if cursor.isNull():
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
        pending_params: set[str] | None = None,
    ) -> None:
        """Regenerate the YAML preview from the current parameter values.

        Args:
            params: Parameter values to render (current_value is used, which
                reflects any pending GUI edits not yet sent to the ROS2 node).
            plugin_filter: When set, only show params for this plugin.
            pending_params: Set of param names whose values are pending (not yet
                confirmed by the ROS2 node).  These lines are shown in blue.
        """
        yaml_str = export_yaml(
            params,
            plugin_filter=plugin_filter,
            pending_params=pending_params,
        )
        self._editor.setPlainText(yaml_str)
        line_count = yaml_str.count('\n') + 1
        self._update_title(line_count)
        if self._current_node:
            self._scroll_to_node(self._current_node)

    def set_current_node(self, node_name: str) -> None:
        """Track the selected node and scroll to its section in the preview."""
        self._current_node = node_name
        if node_name:
            self._scroll_to_node(node_name)

    def set_file_content(self, yaml_str: str, dirty: bool = False) -> None:
        """Show the raw config file content instead of a generated YAML snippet.

        Switches the panel to file mode: the Save button becomes visible,
        and future calls to ``update_yaml`` are ignored until
        ``clear_file_mode`` is called.

        Args:
            yaml_str: Full content of the nav2_params.yaml file.
            dirty: When ``True``, the Save button is highlighted to indicate
                unsaved changes.
        """
        self._file_mode = True
        self._editor.setPlainText(yaml_str)
        line_count = yaml_str.count('\n') + 1
        self._update_title(line_count)
        self._save_btn.setVisible(True)
        self._save_btn.setEnabled(dirty)
        if self._current_node:
            self._scroll_to_node(self._current_node)

    def set_save_button_dirty(self, dirty: bool) -> None:
        """Enable or disable the Save button to reflect unsaved-changes state."""
        if self._file_mode:
            self._save_btn.setEnabled(dirty)

    def clear_file_mode(self) -> None:
        """Return to generated-YAML mode (no config file loaded)."""
        self._file_mode = False
        self._save_btn.setVisible(False)
        self._editor.setPlainText(
            '# Generated by nav2_config\n'
            '# Select a node in the left panel to preview its parameters.\n'
        )
        self._update_title(2)
