# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""YamlPanel — right panel: live YAML preview with VS Code-style syntax highlighting.

Styled to match RViz2's panel headers (light gray, 28px) with a white editor
area. Syntax colors match VS Code Light for familiarity.
"""

from __future__ import annotations

import logging
import re

from PyQt6.QtCore import Qt, QRegularExpression, QSize, pyqtSignal
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

from nav2_config.gui import icons as _icons

from nav2_config.types.params import ParamValue
from nav2_config.core.yaml_exporter import export_yaml
from nav2_config.core.node_discovery import path_basename, infer_stack_namespace

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
        self._full_yaml_str: str | None = None  # Full file YAML stored for saving
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

        self._editor.setPlainText('# Select a node to preview its YAML')
        self._update_title(1)

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
        _save_icon = _icons.yaml_save()
        if not _save_icon.isNull():
            self._save_btn.setIcon(_save_icon)
            self._save_btn.setIconSize(QSize(14, 14))
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
        _copy_icon = _icons.yaml_copy()
        if not _copy_icon.isNull():
            copy_btn.setIcon(_copy_icon)
            copy_btn.setIconSize(QSize(14, 14))
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

    _TOP_KEY_RE = re.compile(r'^[\w./\-]+\s*:')

    def _extract_node_section(
        self, yaml_str: str, bare_node: str, stack_namespace: str = '/'
    ) -> str | None:
        """Extract the section for *bare_node* from a full YAML string.

        Handles root-namespace nodes (``controller_server:`` at indent 0) as
        well as arbitrarily deep namespaces (``/fleet/robot2`` → descend
        ``fleet:`` then ``robot2:`` then find ``controller_server:``).

        Args:
            yaml_str: Full YAML file content as a string.
            bare_node: The node basename, e.g. ``controller_server``.
            stack_namespace: The stack namespace, e.g. ``/robot1``,
                ``/fleet/robot2``, or ``/``.

        Returns:
            The node's YAML section as a string (trailing blank lines
            stripped), or ``None`` if the key cannot be found.
        """
        lines = yaml_str.splitlines()

        # Build the ordered list of namespace segments to descend through.
        # e.g. stack_namespace='/fleet/robot2' → ['fleet', 'robot2']
        #      stack_namespace='/'             → []
        ns_segments = [s for s in stack_namespace.split('/') if s]

        # Descend into each namespace segment in turn, narrowing `lines` at
        # each level.  After this loop, `lines` is scoped to the innermost
        # namespace block and `depth` is the nesting level (in units of 2
        # spaces per level).
        depth = 0
        for segment in ns_segments:
            indent = '  ' * depth
            seg_key_bare = f'{indent}{segment}:'
            seg_key_inline = f'{indent}{segment}: '
            # Regex for a peer key at the same indent depth (signals block end).
            peer_re = re.compile(rf'^{re.escape(indent)}[\w./\-]+\s*:')

            seg_start: int | None = None
            seg_end = len(lines)
            for i, line in enumerate(lines):
                if line == seg_key_bare or line.startswith(seg_key_inline):
                    seg_start = i
                elif seg_start is not None and peer_re.match(line) and i != seg_start:
                    seg_end = i
                    break
            if seg_start is None:
                return None
            lines = lines[seg_start:seg_end]
            depth += 1

        # Now locate bare_node within the (possibly narrowed) lines.
        key_indent = '  ' * depth
        node_key_bare = f'{key_indent}{bare_node}:'
        node_key_inline = f'{key_indent}{bare_node}: '
        peer_re = re.compile(rf'^{re.escape(key_indent)}[\w./\-]+\s*:')

        start: int | None = None
        end = len(lines)
        for i, line in enumerate(lines):
            if line == node_key_bare or line.startswith(node_key_inline):
                start = i
            elif start is not None and peer_re.match(line) and i != start:
                end = i
                break
        if start is None:
            return None

        section = lines[start:end]
        while section and not section[-1].strip():
            section.pop()
        return '\n'.join(section)

    def _show_filtered_yaml(self) -> None:
        """Display only the selected node's section from *_full_yaml_str*."""
        if not self._current_node:
            self._editor.setPlainText('# Select a node to preview its YAML')
            self._update_title(1)
            return

        bare = path_basename(self._current_node)
        stack_ns = infer_stack_namespace(self._current_node, bare)
        section = self._extract_node_section(self._full_yaml_str or '', bare, stack_ns)

        if section is None:
            self._editor.setPlainText(f'# {bare}: not found in config file')
            self._update_title(1)
            return

        # Count parameter value lines (4-space indent, contains colon, not a comment).
        n = sum(
            1 for ln in section.splitlines()
            if ln.startswith('    ') and ':' in ln and not ln.strip().startswith('#')
        )
        text = f'# {bare} — {n} params\n{section}'
        self._editor.setPlainText(text)
        self._update_title(text.count('\n') + 1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update_yaml(
        self,
        params: list[ParamValue],
        plugin_filter: str | None = None,
        pending_params: set[str] | None = None,
    ) -> None:
        """Regenerate the YAML preview showing only the selected node's params.

        Args:
            params: Parameter values for the currently selected node.
            plugin_filter: When set, only show params for this plugin.
            pending_params: Set of param names whose values are pending (not yet
                confirmed by the ROS2 node).  These lines are shown in blue.
        """
        if self._file_mode:
            return  # File mode has its own display path via _show_filtered_yaml.

        if not params:
            self._editor.setPlainText('# Select a node to preview its YAML')
            self._update_title(1)
            return

        yaml_str = export_yaml(
            params,
            plugin_filter=plugin_filter,
            pending_params=pending_params,
        )

        # Strip the generic file header lines (comments + blank lines at top).
        lines = yaml_str.splitlines()
        body_start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('#') or line.strip() == '':
                body_start = i + 1
            else:
                break
        yaml_body = '\n'.join(lines[body_start:])

        node_name = (
            self._current_node.lstrip('/')
            if self._current_node
            else params[0].definition.node
        )
        n = len(params)
        text = f'# {node_name} — {n} params\n{yaml_body}'

        self._editor.setPlainText(text)
        self._update_title(text.count('\n') + 1)

    def set_current_node(self, node_name: str) -> None:
        """Track the selected node; in file mode, re-filter the display."""
        self._current_node = node_name
        if self._file_mode:
            self._show_filtered_yaml()

    def set_file_content(self, yaml_str: str, dirty: bool = False) -> None:
        """Store the full config file and display only the selected node's section.

        Switches the panel to file mode: the Save button becomes visible,
        and future calls to ``update_yaml`` are ignored until
        ``clear_file_mode`` is called.  The full ``yaml_str`` is retained
        so the Save action writes the complete file.

        Args:
            yaml_str: Full content of the nav2_params.yaml file.
            dirty: When ``True``, the Save button is enabled to indicate
                unsaved changes.
        """
        self._file_mode = True
        self._full_yaml_str = yaml_str
        self._save_btn.setVisible(True)
        self._save_btn.setEnabled(dirty)
        self._show_filtered_yaml()

    def set_save_button_dirty(self, dirty: bool) -> None:
        """Enable or disable the Save button to reflect unsaved-changes state."""
        if self._file_mode:
            self._save_btn.setEnabled(dirty)

    def clear_file_mode(self) -> None:
        """Return to generated-YAML mode (no config file loaded)."""
        self._file_mode = False
        self._full_yaml_str = None
        self._save_btn.setVisible(False)
        self._editor.setPlainText('# Select a node to preview its YAML')
        self._update_title(1)
