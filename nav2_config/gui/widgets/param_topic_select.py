"""param_topic_select — RViz2-style topic and TF frame dropdown widgets.

ParamTopicSelect: editable combo that auto-populates with ROS2 topics
  filtered by the expected message type for the given parameter name.

ParamFrameSelect: editable combo that shows all available TF2 frames
  with Nav2 priority frames (map, odom, base_link …) at the top.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QWidget

from nav2_config.core.topic_discovery import TopicDiscovery
from nav2_config.core.frame_discovery import FrameDiscovery

logger = logging.getLogger(__name__)

# Map from keyword found in param name → TopicDiscovery method name
_PARAM_TO_TOPIC_METHOD: list[tuple[str, str]] = [
    ('scan',       'get_scan_topics'),
    ('odom',       'get_odom_topics'),
    ('costmap',    'get_costmap_topics'),
    ('map',        'get_map_topics'),
    ('pointcloud', 'get_pointcloud_topics'),
    ('cloud',      'get_pointcloud_topics'),
    ('cmd_vel',    'get_twist_topics'),
]


def _detect_topic_method(param_name: str) -> str:
    """Return the TopicDiscovery method name appropriate for *param_name*."""
    lower = param_name.lower()
    for keyword, method in _PARAM_TO_TOPIC_METHOD:
        if keyword in lower:
            return method
    return 'get_all_topics'  # Fallback: show all topics (returns dict; handled below)


class ParamTopicSelect(QComboBox):
    """Editable dropdown showing ROS2 topics filtered by expected message type.

    The filter is auto-detected from the parameter name:
    - ``scan_topic``      → ``sensor_msgs/msg/LaserScan`` topics
    - ``odom_topic``      → ``nav_msgs/msg/Odometry`` topics
    - ``map_topic``       → ``nav_msgs/msg/OccupancyGrid`` topics
    - ``costmap_topic``   → ``nav_msgs/msg/OccupancyGrid`` topics
    - ``pointcloud``      → ``sensor_msgs/msg/PointCloud2`` topics
    - ``cmd_vel``         → ``geometry_msgs/msg/Twist`` topics
    - anything else       → all topics

    The current value is always shown, even if not in the discovered list.
    The box is editable so the user can type a custom topic name.

    Signals:
        value_changed(str): emitted when the user commits a selection or edit.
    """

    value_changed = pyqtSignal(str)

    def __init__(
        self,
        topic_discovery: TopicDiscovery,
        param_name: str,
        current_value: str = '',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._topic_discovery = topic_discovery
        self._param_name = param_name
        self._topic_method = _detect_topic_method(param_name)
        self._current_value = current_value

        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumWidth(140)

        self.refresh_topics()

        self.currentTextChanged.connect(self._on_text_changed)
        self.lineEdit().editingFinished.connect(
            lambda: self.value_changed.emit(self.currentText())
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_topics(self) -> None:
        """Re-query ROS2 for topics and rebuild the dropdown list.

        Preserves the current text selection.
        """
        current_text = self.currentText() or self._current_value
        self.blockSignals(True)
        self.clear()

        try:
            method = getattr(self._topic_discovery, self._topic_method)
            if self._topic_method == 'get_all_topics':
                topics = sorted(self._topic_discovery.get_all_topics().keys())
            else:
                topics = method()
        except Exception:
            logger.debug('ParamTopicSelect.refresh_topics failed', exc_info=True)
            topics = []

        # Current value always appears first
        if current_text and current_text not in topics:
            self.addItem(current_text)
        for topic in topics:
            self.addItem(topic)

        # Restore selection
        idx = self.findText(current_text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(current_text)

        self.blockSignals(False)

    def set_value(self, value: str) -> None:
        """Set the displayed value without emitting value_changed."""
        self._current_value = value
        self.blockSignals(True)
        idx = self.findText(value)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(value)
        self.blockSignals(False)

    def get_value(self) -> str:
        """Return the current text."""
        return self.currentText()

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def showPopup(self) -> None:
        """Refresh topic list every time the dropdown is opened."""
        self.refresh_topics()
        super().showPopup()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        self._current_value = text
        self.value_changed.emit(text)


class ParamFrameSelect(QComboBox):
    """Editable dropdown showing all available TF2 frames.

    Nav2-priority frames (map, odom, base_link, base_footprint, base_scan)
    appear at the top of the list.  The box is editable so the user can
    type a custom frame ID.

    Signals:
        value_changed(str): emitted when the user commits a selection or edit.
    """

    value_changed = pyqtSignal(str)

    def __init__(
        self,
        frame_discovery: FrameDiscovery,
        current_value: str = '',
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._frame_discovery = frame_discovery
        self._current_value = current_value

        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumWidth(140)

        self.refresh_frames()

        self.currentTextChanged.connect(self._on_text_changed)
        self.lineEdit().editingFinished.connect(
            lambda: self.value_changed.emit(self.currentText())
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh_frames(self) -> None:
        """Re-query tf2 for frames and rebuild the dropdown list.

        Preserves the current text selection.
        """
        current_text = self.currentText() or self._current_value
        self.blockSignals(True)
        self.clear()

        try:
            frames = self._frame_discovery.get_common_frames()
        except Exception:
            logger.debug('ParamFrameSelect.refresh_frames failed', exc_info=True)
            frames = []

        # Current value always appears (even before TF data arrives)
        if current_text and current_text not in frames:
            self.addItem(current_text)
        for frame in frames:
            self.addItem(frame)

        idx = self.findText(current_text)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(current_text)

        self.blockSignals(False)

    def set_value(self, value: str) -> None:
        """Set the displayed value without emitting value_changed."""
        self._current_value = value
        self.blockSignals(True)
        idx = self.findText(value)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentText(value)
        self.blockSignals(False)

    def get_value(self) -> str:
        """Return the current text."""
        return self.currentText()

    # ------------------------------------------------------------------
    # Overrides
    # ------------------------------------------------------------------

    def showPopup(self) -> None:
        """Refresh frame list every time the dropdown is opened."""
        self.refresh_frames()
        super().showPopup()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _on_text_changed(self, text: str) -> None:
        self._current_value = text
        self.value_changed.emit(text)
