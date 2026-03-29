# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""TopicDiscovery — discovers available ROS2 topics by type.

Wraps node.get_topic_names_and_types() so the GUI can populate
topic-selector dropdowns with live, filtered topic lists.
"""

from __future__ import annotations

import logging

from rclpy.node import Node

logger = logging.getLogger(__name__)


class TopicDiscovery:
    """Queries the ROS2 graph for available topics.

    All methods are safe to call from any thread; they delegate to
    ``node.get_topic_names_and_types()`` which is thread-safe in rclpy.
    """

    def __init__(self, node: Node) -> None:
        self._node = node

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def get_all_topics(self) -> dict[str, list[str]]:
        """Return ``{topic_name: [msg_types]}`` for every active topic."""
        try:
            return {
                name: types
                for name, types in self._node.get_topic_names_and_types()
            }
        except Exception:
            logger.debug('TopicDiscovery.get_all_topics failed', exc_info=True)
            return {}

    def get_topics_by_type(self, msg_type: str) -> list[str]:
        """Return topic names whose type matches *msg_type* exactly.

        Args:
            msg_type: Full message type, e.g. ``"sensor_msgs/msg/LaserScan"``.

        Returns:
            Sorted list of matching topic names.
        """
        return sorted(
            name
            for name, types in self.get_all_topics().items()
            if msg_type in types
        )

    # ------------------------------------------------------------------
    # Convenience shortcuts
    # ------------------------------------------------------------------

    def get_scan_topics(self) -> list[str]:
        """All ``sensor_msgs/msg/LaserScan`` topics."""
        return self.get_topics_by_type('sensor_msgs/msg/LaserScan')

    def get_map_topics(self) -> list[str]:
        """All ``nav_msgs/msg/OccupancyGrid`` topics."""
        return self.get_topics_by_type('nav_msgs/msg/OccupancyGrid')

    def get_odom_topics(self) -> list[str]:
        """All ``nav_msgs/msg/Odometry`` topics."""
        return self.get_topics_by_type('nav_msgs/msg/Odometry')

    def get_pointcloud_topics(self) -> list[str]:
        """All ``sensor_msgs/msg/PointCloud2`` topics."""
        return self.get_topics_by_type('sensor_msgs/msg/PointCloud2')

    def get_costmap_topics(self) -> list[str]:
        """All ``nav_msgs/msg/OccupancyGrid`` topics (costmap alias)."""
        return self.get_topics_by_type('nav_msgs/msg/OccupancyGrid')

    def get_twist_topics(self) -> list[str]:
        """All ``geometry_msgs/msg/Twist`` topics."""
        return self.get_topics_by_type('geometry_msgs/msg/Twist')
