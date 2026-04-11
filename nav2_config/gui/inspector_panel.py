# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""InspectorPanel — tabbed container for YAML, History, and Compare panels.

Wraps a QTabWidget with three tabs, each embedding an existing panel widget
passed in through the constructor.  The tab widget fills the entire widget area.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from nav2_config.gui.yaml_panel import YamlPanel
    from nav2_config.gui.history_panel import HistoryPanel
    from nav2_config.gui.compare_panel import ComparePanel


class InspectorPanel(QWidget):
    """Tabbed inspector widget embedding YAML, History, and Compare sub-panels.

    Args:
        yaml_panel: Pre-constructed YamlPanel instance.
        history_panel: Pre-constructed HistoryPanel instance.
        compare_panel: Pre-constructed ComparePanel instance.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        yaml_panel: "YamlPanel",
        history_panel: "HistoryPanel",
        compare_panel: "ComparePanel",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._yaml_panel = yaml_panel
        self._history_panel = history_panel
        self._compare_panel = compare_panel

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.addTab(yaml_panel, "YAML")
        self._tabs.addTab(history_panel, "History")
        self._tabs.addTab(compare_panel, "Compare")

        layout.addWidget(self._tabs)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def yaml_panel(self) -> "YamlPanel":
        """The embedded YamlPanel."""
        return self._yaml_panel

    @property
    def history_panel(self) -> "HistoryPanel":
        """The embedded HistoryPanel."""
        return self._history_panel

    @property
    def compare_panel(self) -> "ComparePanel":
        """The embedded ComparePanel."""
        return self._compare_panel
