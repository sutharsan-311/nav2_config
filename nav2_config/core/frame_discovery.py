"""FrameDiscovery — discovers available TF2 frames.

Sets up a tf2_ros Buffer + TransformListener on the given ROS2 node and
exposes the current frame list so the GUI can populate frame-selector
dropdowns.
"""

from __future__ import annotations

import logging

import yaml
from rclpy.node import Node

logger = logging.getLogger(__name__)

# Frames that appear first in Nav2 config dropdowns
_PRIORITY_FRAMES = ['map', 'odom', 'base_link', 'base_footprint', 'base_scan']

try:
    from tf2_ros import Buffer, TransformListener
    _TF2_AVAILABLE = True
except ImportError:
    _TF2_AVAILABLE = False
    logger.warning('tf2_ros not available — frame discovery disabled')


class FrameDiscovery:
    """Discovers TF2 frames published on the running ROS2 system.

    Uses a ``tf2_ros.Buffer`` populated by a ``TransformListener`` that
    subscribes to ``/tf`` and ``/tf_static``.  The listener runs on the
    same ROS2 thread as the parent node.

    If tf2_ros is not installed, all methods return empty lists gracefully.
    """

    def __init__(self, node: Node) -> None:
        self._node = node
        self._tf_buffer: 'Buffer | None' = None
        self._tf_listener: 'TransformListener | None' = None
        self._setup_tf()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_tf(self) -> None:
        """Initialise the tf2 buffer and listener."""
        if not _TF2_AVAILABLE:
            return
        try:
            self._tf_buffer = Buffer()
            self._tf_listener = TransformListener(self._tf_buffer, self._node)
            logger.debug('FrameDiscovery: tf2 listener started')
        except Exception:
            logger.warning('FrameDiscovery: failed to start tf2 listener', exc_info=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_all_frames(self) -> list[str]:
        """Return a sorted list of all known TF2 frame IDs.

        Parses the YAML string returned by ``Buffer.all_frames_as_yaml()``.
        Returns an empty list if tf2 is unavailable or no frames exist yet.
        """
        if self._tf_buffer is None:
            return []
        try:
            frames_yaml = self._tf_buffer.all_frames_as_yaml()
            if not frames_yaml or not frames_yaml.strip():
                return []
            data = yaml.safe_load(frames_yaml)
            if isinstance(data, dict):
                return sorted(data.keys())
        except Exception:
            logger.debug('FrameDiscovery.get_all_frames failed', exc_info=True)
        return []

    def get_common_frames(self) -> list[str]:
        """Return all frames with Nav2-priority frames listed first.

        Priority order: map, odom, base_link, base_footprint, base_scan,
        then all remaining frames in alphabetical order.
        """
        all_frames = self.get_all_frames()
        seen: set[str] = set()
        result: list[str] = []

        for frame in _PRIORITY_FRAMES:
            if frame in all_frames:
                result.append(frame)
                seen.add(frame)

        for frame in all_frames:
            if frame not in seen:
                result.append(frame)

        return result
