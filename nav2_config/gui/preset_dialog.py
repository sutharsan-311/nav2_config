"""PresetDialog — dialog for selecting and applying Nav2 environment presets.

Shows the 5 built-in presets with descriptions.  "Preview" shows what
parameters would change; "Apply" sets them on the live Nav2 nodes.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.presets import (
    PRESET_META,
    PRESET_ORDER,
    count_preset_params,
    load_preset,
)

logger = logging.getLogger(__name__)


class PresetDialog(QDialog):
    """Modal dialog for selecting and applying Nav2 environment presets.

    Args:
        on_apply: Callback invoked when the user confirms Apply.
            Signature: ``(preset_name: str, preset_data: dict) -> None``.
        initial_preset: Key of the preset to select on open (optional).
        parent: Qt parent widget.
    """

    def __init__(
        self,
        on_apply: Callable[[str, dict[str, dict[str, Any]]], None],
        initial_preset: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_apply = on_apply
        self._initial_preset = initial_preset
        self._loaded_presets: dict[str, dict[str, dict[str, Any]]] = {}

        self.setWindowTitle('Apply Environment Preset')
        self.setMinimumSize(740, 460)
        self.setModal(True)
        self._build_ui()
        self._preload_presets()

        # Select initial preset after preloading.
        if initial_preset and initial_preset in PRESET_META:
            idx = PRESET_ORDER.index(initial_preset) if initial_preset in PRESET_ORDER else 0
            self._list.setCurrentRow(idx)
        elif self._list.count() > 0:
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Header ────────────────────────────────────────────────────────
        header = QLabel('Select a preset to apply parameter overrides to your running Nav2 nodes.')
        header.setWordWrap(True)
        header.setStyleSheet('color: #9d9d9d; font-size: 12px;')
        root.addWidget(header)

        # ── Main splitter: list (left) + detail (right) ───────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setChildrenCollapsible(False)

        self._list = QListWidget()
        self._list.setFixedWidth(220)
        self._list.setStyleSheet(
            'QListWidget { background: #1e1e1e; border: 1px solid #3e3e42; }'
            'QListWidget::item { padding: 8px 10px; color: #d4d4d4; '
            '    border-bottom: 1px solid #2d2d2d; }'
            'QListWidget::item:selected { background: #f57c00; color: #fff; }'
            'QListWidget::item:hover:!selected { background: #2a2d2e; }'
        )
        self._list.currentRowChanged.connect(self._on_preset_selected)

        for key in PRESET_ORDER:
            meta = PRESET_META.get(key, {})
            item = QListWidgetItem(meta.get('name', key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self._list.addItem(item)

        splitter.addWidget(self._list)
        splitter.addWidget(self._make_detail_panel())
        splitter.setSizes([220, 10000])

        root.addWidget(splitter, stretch=1)

        # ── Button row ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)

        self._preview_btn = QPushButton('Preview Changes')
        self._preview_btn.setEnabled(False)
        self._preview_btn.setStyleSheet(
            'QPushButton { background: #2d2d2d; border: 1px solid #3e3e42; '
            'color: #d4d4d4; padding: 4px 14px; }'
            'QPushButton:hover:enabled { background: #3e3e42; }'
            'QPushButton:disabled { color: #555; }'
        )
        self._preview_btn.clicked.connect(self._on_preview)
        btn_row.addWidget(self._preview_btn)

        btn_row.addStretch()

        self._apply_btn = QPushButton('Apply Preset')
        self._apply_btn.setEnabled(False)
        self._apply_btn.setDefault(True)
        self._apply_btn.setStyleSheet(
            'QPushButton { background: #f57c00; border: 1px solid #e65100; '
            'color: #fff; font-weight: bold; padding: 4px 18px; }'
            'QPushButton:hover:enabled { background: #fb8c00; }'
            'QPushButton:disabled { background: #3d3d3d; border-color: #555; color: #555; }'
        )
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        btn_row.addWidget(self._apply_btn)

        cancel_btn = QPushButton('Cancel')
        cancel_btn.setStyleSheet(
            'QPushButton { background: #2d2d2d; border: 1px solid #3e3e42; '
            'color: #d4d4d4; padding: 4px 14px; }'
            'QPushButton:hover { background: #3e3e42; }'
        )
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        root.addLayout(btn_row)

    def _make_detail_panel(self) -> QWidget:
        """Create the right-side detail / preview area."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(6)

        self._name_label = QLabel('')
        self._name_label.setStyleSheet(
            'color: #e0e0e0; font-size: 15px; font-weight: bold;'
        )
        layout.addWidget(self._name_label)

        self._scenario_label = QLabel('')
        self._scenario_label.setStyleSheet('color: #f57c00; font-size: 11px;')
        layout.addWidget(self._scenario_label)

        self._desc_label = QLabel('')
        self._desc_label.setWordWrap(True)
        self._desc_label.setStyleSheet('color: #9d9d9d; font-size: 12px;')
        layout.addWidget(self._desc_label)

        # Separator
        sep = QWidget()
        sep.setFixedHeight(1)
        sep.setStyleSheet('background: #3e3e42;')
        layout.addWidget(sep)

        # Scrollable param override preview
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')

        self._preview_widget = QWidget()
        self._preview_layout = QVBoxLayout(self._preview_widget)
        self._preview_layout.setContentsMargins(0, 4, 0, 0)
        self._preview_layout.setSpacing(2)
        self._preview_layout.addStretch()
        scroll.setWidget(self._preview_widget)
        layout.addWidget(scroll, stretch=1)

        return container

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _preload_presets(self) -> None:
        """Load all preset files eagerly so the UI is immediately responsive."""
        for key in PRESET_ORDER:
            try:
                self._loaded_presets[key] = load_preset(key)
            except Exception as exc:
                logger.warning('Could not load preset %r: %s', key, exc)

    def _selected_key(self) -> str | None:
        item = self._list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def _on_preset_selected(self, row: int) -> None:
        key = self._selected_key()
        if key is None:
            return

        meta = PRESET_META.get(key, {})
        self._name_label.setText(meta.get('name', key))
        self._scenario_label.setText(meta.get('scenario', ''))
        self._desc_label.setText(meta.get('description', ''))

        preset_data = self._loaded_presets.get(key)
        self._apply_btn.setEnabled(preset_data is not None)
        self._preview_btn.setEnabled(preset_data is not None)

        if preset_data:
            self._render_preview(preset_data)

    def _render_preview(self, preset_data: dict[str, dict[str, Any]]) -> None:
        """Populate the scrollable preview area with param override rows."""
        # Clear existing preview rows
        while self._preview_layout.count() > 1:
            item = self._preview_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        total = count_preset_params(preset_data)
        summary = QLabel(f'{total} parameter overrides across {len(preset_data)} nodes:')
        summary.setStyleSheet('color: #7d7d7d; font-size: 11px;')
        self._preview_layout.insertWidget(0, summary)

        row_idx = 1
        for bare_node, params in sorted(preset_data.items()):
            # Node header
            node_hdr = QLabel(bare_node)
            node_hdr.setStyleSheet(
                'color: #f57c00; font-size: 11px; font-weight: bold; '
                'margin-top: 6px;'
            )
            self._preview_layout.insertWidget(row_idx, node_hdr)
            row_idx += 1

            for param_name, value in sorted(params.items()):
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 0, 0, 0)
                row_layout.setSpacing(8)

                param_label = QLabel(param_name)
                param_label.setStyleSheet(
                    'color: #9cdcfe; font-family: monospace; font-size: 11px;'
                )
                param_label.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
                )

                value_label = QLabel(str(value))
                value_label.setStyleSheet(
                    'color: #ce9178; font-family: monospace; font-size: 11px;'
                )

                row_layout.addWidget(param_label)
                row_layout.addWidget(value_label)
                self._preview_layout.insertWidget(row_idx, row)
                row_idx += 1

    def _on_preview(self) -> None:
        """Ensure the detail panel is visible and scrolled to the preview."""
        # The preview is always shown in the detail panel; this button can
        # expand the panel if it was collapsed.  Currently it's a no-op since
        # the detail panel is always shown, but reserved for future use.
        pass

    def _on_apply_clicked(self) -> None:
        """Confirm with the user and invoke the apply callback."""
        key = self._selected_key()
        if key is None:
            return

        preset_data = self._loaded_presets.get(key)
        if not preset_data:
            QMessageBox.warning(
                self,
                'Preset Unavailable',
                f'Could not load preset "{key}". Check that preset files are installed.',
            )
            return

        meta = PRESET_META.get(key, {})
        total = count_preset_params(preset_data)
        node_count = len(preset_data)

        reply = QMessageBox.question(
            self,
            'Apply Preset',
            (
                f'Apply <b>{meta.get("name", key)}</b>?\n\n'
                f'This will change <b>{total} parameters</b> across '
                f'<b>{node_count} node{"s" if node_count != 1 else ""}</b>.\n\n'
                f'Only running nodes will be updated. Parameters for nodes '
                f'that are not currently running will be silently skipped.'
            ),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )

        if reply == QMessageBox.StandardButton.Ok:
            self._on_apply(key, preset_data)
            self.accept()
