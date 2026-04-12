# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Simulation vs real-robot detection for nav2_config.

Runs on the ROS2 background thread.  All methods are safe to call from a
ROS2 timer callback; they never touch the Qt main thread directly.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rclpy.node import Node
    from nav2_config.core.param_client import Nav2ParamClient

logger = logging.getLogger(__name__)


class RobotMode(Enum):
    """Detected environment mode."""

    SIMULATION = auto()
    REAL = auto()
    UNKNOWN = auto()  # not yet determined


class RobotModeDetector:
    """Infers whether nav2_config is talking to a simulator or a real robot.

    Detection checks are applied in priority order:

    1. ``use_sim_time`` ROS2 parameter — queried on the first discovered Nav2
       node via the existing :class:`~nav2_config.core.param_client.Nav2ParamClient`.
       If the parameter is ``True`` → SIMULATION; ``False`` → REAL.
    2. ``/clock`` topic presence — a ``/clock`` publisher is the universal
       sign that a simulator is driving time.
    3. Any topic whose name contains ``"gazebo"`` or ``"simulation"``.

    If all checks are inconclusive but at least one Nav2 node is running,
    REAL is returned (a real robot running without sim_time is the common case).
    When no Nav2 nodes are present yet, UNKNOWN is returned.

    Args:
        node: The ``rclpy.Node`` used to query the ROS2 graph.
        param_client: Existing :class:`~nav2_config.core.param_client.Nav2ParamClient`
            instance; shared with the rest of the node to avoid duplicate clients.
    """

    #: Maximum number of Nav2 nodes to query for use_sim_time before
    #: falling back to topic-based checks.  Caps service-call latency.
    _MAX_PARAM_NODES: int = 2

    def __init__(self, node: 'Node', param_client: 'Nav2ParamClient') -> None:
        self._node = node
        self._param_client = param_client

    def detect(self, discovered_node_paths: list[str]) -> RobotMode:
        """Run all detection checks and return the inferred :class:`RobotMode`.

        Designed for periodic calls from a ROS2 timer callback (ROS2 thread).
        Failures in any individual check are caught and logged at DEBUG level;
        the method always returns a valid :class:`RobotMode`.

        Args:
            discovered_node_paths: Full ROS2 paths of currently-running Nav2
                nodes (e.g. ``["/controller_server", "/planner_server"]``).
                Empty list → no nodes discovered yet → likely UNKNOWN.

        Returns:
            The detected :class:`RobotMode`.
        """
        # ------------------------------------------------------------------
        # Priority 1: use_sim_time parameter on a discovered Nav2 node.
        # Authoritative — a node that reports use_sim_time=False is definitely
        # on a real clock; use_sim_time=True → simulation clock.
        # ------------------------------------------------------------------
        for node_path in discovered_node_paths[: self._MAX_PARAM_NODES]:
            try:
                result = self._param_client.get_params(node_path, ['use_sim_time'])
                if 'use_sim_time' in result:
                    val, _ = result['use_sim_time']
                    mode = RobotMode.SIMULATION if bool(val) else RobotMode.REAL
                    logger.debug(
                        f"Robot mode from use_sim_time on {node_path}: {mode.name}"
                    )
                    return mode
            except Exception as exc:
                logger.debug(f"use_sim_time check failed on {node_path}: {exc}")

        # ------------------------------------------------------------------
        # Priority 2 & 3: topic-based — fast, no service call required.
        # ------------------------------------------------------------------
        try:
            topics: set[str] = {
                name for name, _ in self._node.get_topic_names_and_types()
            }

            if '/clock' in topics:
                logger.debug("Robot mode SIMULATION: /clock topic present")
                return RobotMode.SIMULATION

            for name in topics:
                lower = name.lower()
                if 'gazebo' in lower or 'simulation' in lower:
                    logger.debug(f"Robot mode SIMULATION: topic {name!r} matches keyword")
                    return RobotMode.SIMULATION

        except Exception as exc:
            logger.debug(f"Topic-based robot mode check failed: {exc}")

        # ------------------------------------------------------------------
        # Fallback: nodes running, no simulation signals found → real robot.
        # No nodes yet → still determining.
        # ------------------------------------------------------------------
        if discovered_node_paths:
            logger.debug("Robot mode REAL: Nav2 nodes present, no simulation signals")
            return RobotMode.REAL

        return RobotMode.UNKNOWN
