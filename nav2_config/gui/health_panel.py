"""HealthPanel — collapsible panel showing Nav2 parameter health check results.

The panel auto-runs health checks after params change (debounced 1 second)
and shows each finding with a severity icon, title, detail message, and the
names of affected parameters.  Clicking an affected param badge emits
:attr:`param_focus_requested` so the ParamPanel can scroll to that row.
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

# Severity → (icon, accent colour)
_SEVERITY_STYLE: dict[str, tuple[str, str]] = {
    'error':   ('✕', '#f44336'),
    'warning': ('⚠', '#f57c00'),
    'info':    ('ℹ', '#4fc3f7'),
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
        icon, colour = _SEVERITY_STYLE.get(
            self._result.severity, ('•', '#d4d4d4')
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        self.setStyleSheet(
            f'QWidget {{ background: {colour}18; border-left: 3px solid {colour}; }}'
        )

        # ── Title row ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f'color: {colour}; font-weight: bold; font-size: 13px;')
        icon_label.setFixedWidth(16)
        title_row.addWidget(icon_label)

        title_label = QLabel(self._result.title)
        title_label.setStyleSheet('color: #e0e0e0; font-weight: bold; font-size: 12px;')
        title_label.setWordWrap(True)
        title_row.addWidget(title_label, stretch=1)

        layout.addLayout(title_row)

        # ── Message ───────────────────────────────────────────────────────
        msg_label = QLabel(self._result.message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet(
            'color: #b0b0b0; font-size: 11px; padding-left: 22px;'
        )
        layout.addWidget(msg_label)

        # ── Affected param badges ──────────────────────────────────────────
        if self._result.affected_params:
            badge_row = QHBoxLayout()
            badge_row.setContentsMargins(22, 0, 0, 0)
            badge_row.setSpacing(4)

            for param_name in self._result.affected_params:
                badge = QPushButton(param_name)
                badge.setStyleSheet(
                    f'QPushButton {{'
                    f'    background: {colour}33; border: 1px solid {colour}66;'
                    f'    color: {colour}; font-size: 10px;'
                    f'    padding: 1px 6px; font-family: monospace;'
                    f'}}'
                    f'QPushButton:hover {{ background: {colour}55; }}'
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
    """Collapsible panel that displays health check results for the current params.

    Usage::

        panel = HealthPanel()
        panel.param_focus_requested.connect(param_panel.scroll_to_param)
        # After params change:
        panel.schedule_check(all_params)

    Signals:
        param_focus_requested(str): Emitted when the user clicks an affected-
            param badge.  The payload is the parameter name to scroll to.
    """

    param_focus_requested = pyqtSignal(str)

    #: Milliseconds to wait after the last param change before running checks.
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

        # Scroll area for issue cards
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet('QScrollArea { border: none; }')
        self._scroll.setMaximumHeight(260)

        self._cards_widget = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(4, 4, 4, 4)
        self._cards_layout.setSpacing(4)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_widget)
        layout.addWidget(self._scroll)

        # Separator line at the bottom of the panel
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet('color: #3e3e42;')
        layout.addWidget(sep)

        self._refresh_empty_state()

    def _make_header(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet(
            'background: #252526; border-bottom: 1px solid #3e3e42; '
            'border-top: 1px solid #3e3e42;'
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)

        self._toggle_btn = QPushButton('▼')
        self._toggle_btn.setFixedSize(18, 18)
        self._toggle_btn.setStyleSheet(
            'QPushButton { background: none; border: none; '
            'color: #6d6d6d; font-size: 10px; }'
            'QPushButton:hover { color: #d4d4d4; }'
        )
        self._toggle_btn.clicked.connect(self._toggle_expanded)
        layout.addWidget(self._toggle_btn)

        self._status_label = QLabel('HEALTH CHECK')
        self._status_label.setStyleSheet(
            'color: #d4d4d4; font-size: 11px; font-weight: bold; letter-spacing: 1px;'
        )
        layout.addWidget(self._status_label)

        layout.addStretch()

        run_btn = QPushButton('Run Now')
        run_btn.setFixedHeight(18)
        run_btn.setStyleSheet(
            'QPushButton { background: #2d2d2d; border: 1px solid #3e3e42; '
            'color: #9d9d9d; font-size: 10px; padding: 0 6px; }'
            'QPushButton:hover { background: #3e3e42; color: #d4d4d4; }'
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
        self._toggle_btn.setText('▼' if self._expanded else '▶')

    def _run_checks(self) -> None:
        """Run health checks synchronously and refresh the display."""
        self._results = run_health_checks(self._params)
        self._refresh_display()
        logger.debug('HealthPanel: %d issues found', len(self._results))

    def _refresh_display(self) -> None:
        """Rebuild the issue card list from ``self._results``."""
        # Remove all existing cards (keep the stretch at the end)
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
            self._cards_layout.insertWidget(
                self._cards_layout.count() - 1, card
            )

        self._update_header_status(errors, warnings)

    def _refresh_empty_state(self) -> None:
        """Show a 'clean' placeholder when there are no issues."""
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._params:
            placeholder = QLabel('Select a node to run health checks.')
        else:
            placeholder = QLabel('✓  No issues found.')
            placeholder.setStyleSheet('color: #4caf50; font-size: 11px; padding: 8px;')

        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet('color: #5d5d5d; font-size: 11px; padding: 8px;')
        self._cards_layout.insertWidget(0, placeholder)
        self._update_header_status(0, 0)

    def _update_header_status(self, errors: int, warnings: int) -> None:
        """Refresh the header label to reflect current issue counts."""
        if errors > 0:
            colour = '#f44336'
            text = f'HEALTH CHECK  ·  ✕ {errors} error{"s" if errors > 1 else ""}'
            if warnings:
                text += f'  ⚠ {warnings}'
        elif warnings > 0:
            colour = '#f57c00'
            text = f'HEALTH CHECK  ·  ⚠ {warnings} warning{"s" if warnings > 1 else ""}'
        else:
            colour = '#4caf50'
            text = 'HEALTH CHECK  ·  ✓ Clean'

        self._status_label.setText(text)
        self._status_label.setStyleSheet(
            f'color: {colour}; font-size: 11px; font-weight: bold; letter-spacing: 1px;'
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule_check(self, params: list[ParamValue]) -> None:
        """Accumulate params and schedule a debounced health check run.

        Calling this repeatedly within :attr:`DEBOUNCE_MS` milliseconds will
        only trigger one check — after the final call's debounce expires.

        Args:
            params: Flat list of :class:`~nav2_config.types.params.ParamValue`
                objects (may span multiple nodes).
        """
        self._params = params
        self._debounce_timer.start()  # Restarts the timer if already running.

    def run_checks_now(self, params: list[ParamValue]) -> None:
        """Run health checks immediately (bypass debounce).

        Args:
            params: Flat list of ParamValue objects.
        """
        self._debounce_timer.stop()
        self._params = params
        self._run_checks()
