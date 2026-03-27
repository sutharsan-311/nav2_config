"""HealthPanel — collapsible panel showing Nav2 parameter health check results.

Styled to match RViz2: 28px header, light gray header background, #3399ff
active indicators, system font.
"""

from __future__ import annotations

import logging
from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nav2_config.core.health_check import HealthCheckResult, run_health_checks
from nav2_config.types.params import ParamValue

logger = logging.getLogger(__name__)

# RViz2 light palette
_BG_HDR  = '#d0d0d0'
_BG_PANEL = '#e8e8e8'
_BORDER  = '#c0c0c0'
_FG      = '#1a1a1a'
_FG_DIM  = '#666666'

# Severity → (icon, accent colour)
_SEVERITY_STYLE: dict[str, tuple[str, str]] = {
    'error':   ('✕', '#e53935'),
    'warning': ('⚠', '#ff9800'),
    'info':    ('ℹ', '#3399ff'),
}


class _IssueCard(QWidget):
    """Single health check finding displayed as a compact card."""

    param_focus_requested = pyqtSignal(str)

    def __init__(
        self, result: HealthCheckResult, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._result = result
        self._build_ui()

    def _build_ui(self) -> None:
        icon, colour = _SEVERITY_STYLE.get(self._result.severity, ('•', _FG))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(2)

        self.setStyleSheet(
            f'QWidget {{ background: {colour}14; '
            f'border-left: 3px solid {colour}; }}'
        )

        # ── Title row ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(
            f'color: {colour}; font-weight: bold; font-size: 10pt; '
            f'background: transparent;'
        )
        icon_label.setFixedWidth(14)
        title_row.addWidget(icon_label)

        title_label = QLabel(self._result.title)
        title_label.setStyleSheet(
            f'color: {_FG}; font-weight: bold; font-size: 10pt; '
            f'background: transparent;'
        )
        title_label.setWordWrap(True)
        title_row.addWidget(title_label, stretch=1)

        layout.addLayout(title_row)

        # ── Message ───────────────────────────────────────────────────────
        msg_label = QLabel(self._result.message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(
            f'color: {_FG_DIM}; font-size: 9pt; '
            f'padding-left: 20px; background: transparent;'
        )
        layout.addWidget(msg_label)

        # ── Affected param badges ──────────────────────────────────────────
        if self._result.affected_params:
            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(20, 0, 0, 0)
            badge_row.setSpacing(3)

            for param_name in self._result.affected_params:
                badge = QPushButton(param_name)
                badge.setStyleSheet(
                    f'QPushButton {{'
                    f'    background: {colour}22; border: 1px solid {colour}66;'
                    f'    color: {colour}; font-size: 8pt; padding: 1px 5px;'
                    f'}}'
                    f'QPushButton:hover {{ background: {colour}44; }}'
                )
                badge.setSizePolicy(
                    QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed
                )
                badge.clicked.connect(
                    lambda _checked, p=param_name: self.param_focus_requested.emit(p)
                )
                badge_row.addWidget(badge)

            badge_row.addStretch()
            layout.addLayout(badge_row)


class HealthPanel(QWidget):
    """Collapsible panel showing health check results for the current params.

    Signals:
        param_focus_requested(str): emitted when user clicks an affected-param badge.
    """

    param_focus_requested = pyqtSignal(str)

    DEBOUNCE_MS: int = 1000

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._params: list[ParamValue] = []
        self._results: list[HealthCheckResult] = []
        self._expanded: bool = True

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(self.DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._run_checks)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._make_header())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet('QScrollArea { border: none; }')
        self._scroll.setMaximumHeight(220)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(4, 4, 4, 4)
        self._cards_layout.setSpacing(3)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_widget)
        layout.addWidget(self._scroll)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f'color: {_BORDER}; background: {_BORDER};')
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        self._refresh_empty_state()

    def _make_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(28)
        bar.setStyleSheet(
            f'QWidget {{ background: {_BG_HDR}; '
            f'border-bottom: 1px solid {_BORDER}; '
            f'border-top: 1px solid {_BORDER}; }}'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(4)

        self._toggle_btn = QPushButton('▾')
        self._toggle_btn.setFixedSize(18, 18)
        self._toggle_btn.setStyleSheet(
            f'QPushButton {{ background: none; border: none; '
            f'color: {_FG_DIM}; font-size: 10px; }}'
            f'QPushButton:hover {{ color: {_FG}; }}'
        )
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        layout.addWidget(self._toggle_btn)

        self._status_label = QLabel('Health Check')
        self._status_label.setStyleSheet(
            f'color: {_FG}; font-size: 10pt; font-weight: bold; '
            f'background: transparent;'
        )
        layout.addWidget(self._status_label)

        layout.addStretch()

        run_btn = QPushButton('Run Now')
        run_btn.setFixedHeight(20)
        run_btn.setStyleSheet(
            f'QPushButton {{ border: 1px solid {_BORDER}; '
            f'font-size: 9pt; padding: 0 8px; }}'
        )
        run_btn.clicked.connect(self._run_checks)
        layout.addWidget(run_btn)

        return bar

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._scroll.setVisible(self._expanded)
        self._toggle_btn.setText('▾' if self._expanded else '▸')

    def _run_checks(self) -> None:
        self._results = run_health_checks(self._params)
        self._refresh_display()
        logger.debug('HealthPanel: %d issues found', len(self._results))

    def _refresh_display(self) -> None:
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._results:
            self._refresh_empty_state()
            return

        errors = sum(1 for r in self._results if r.severity == 'error')
        warnings = sum(1 for r in self._results if r.severity == 'warning')

        for result in self._results:
            card = _IssueCard(result)
            card.param_focus_requested.connect(self.param_focus_requested)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        self._update_header_status(errors, warnings)

    def _refresh_empty_state(self) -> None:
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._params:
            placeholder = QLabel('Select a node to run health checks.')
        else:
            placeholder = QLabel('✓  No issues found.')

        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet(f'color: {_FG_DIM}; font-size: 9pt; padding: 8px;')
        self._cards_layout.insertWidget(0, placeholder)
        self._update_header_status(0, 0)

    def _update_header_status(self, errors: int, warnings: int) -> None:
        if errors > 0:
            colour = '#e53935'
            text = (
                f'Health Check  ·  ✕ {errors} error{"s" if errors > 1 else ""}'
            )
            if warnings:
                text += f'  ⚠ {warnings}'
        elif warnings > 0:
            colour = '#ff9800'
            text = (
                f'Health Check  ·  ⚠ {warnings} '
                f'warning{"s" if warnings > 1 else ""}'
            )
        else:
            colour = '#4caf50'
            text = 'Health Check  ·  ✓ Clean'

        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f'color: {colour}; font-size: 10pt; font-weight: bold; '
            f'background: transparent;'
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule_check(self, params: list[ParamValue]) -> None:
        """Accumulate params and schedule a debounced health check run."""
        self._params = params
        self._debounce_timer.start()

    def run_checks_now(self, params: list[ParamValue]) -> None:
        """Run health checks immediately (bypass debounce)."""
        self._debounce_timer.stop()
        self._params = params
        self._run_checks()
