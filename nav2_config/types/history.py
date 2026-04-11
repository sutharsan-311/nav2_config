# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""History tracking types for nav2_config compare/history feature."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Any


@dataclass(frozen=True)
class ParamRef:
    """Uniquely identifies a single parameter on a single ROS2 node."""

    node_path: str   # full ROS2 path, e.g. /robot1/controller_server
    param_name: str  # dot-notation param name


class ChangeSource(Enum):
    """Where a parameter change originated."""

    LIVE_SET = auto()
    FILE_LOAD = auto()
    EXTERNAL_CHANGE = auto()
    UNDO = auto()
    COMPARE_APPLY = auto()


@dataclass
class ParamHistoryEntry:
    """A single recorded parameter change event.

    Args:
        entry_id: UUID4 string uniquely identifying this entry.
        timestamp: When the change was recorded.
        ref: The node/param being changed.
        old_value: The value before the change (None if unknown).
        new_value: The value after the change.
        source: Which subsystem produced this change.
        batch_id: Optional UUID grouping simultaneous changes (e.g. file load).
        ros2_name: The ROS2 parameter name, which may differ from dot-notation.
        type_hint: ROS2 parameter type string ('double', 'bool', 'string', etc.).
        hot_reload: True if this parameter supports live set without a restart.
        status: Lifecycle of this entry: 'pending', 'applied', 'failed', or 'undone'.
    """

    entry_id: str
    timestamp: datetime
    ref: ParamRef
    old_value: Any         # None if unknown
    new_value: Any
    source: ChangeSource
    batch_id: Optional[str]    # groups simultaneous changes (e.g. file load)
    ros2_name: str             # the ROS2 parameter name (may differ from dot-notation)
    type_hint: str             # 'double', 'bool', 'string', 'integer', etc.
    hot_reload: bool           # whether this param supports live set
    status: str = "pending"    # 'pending', 'applied', 'failed', 'undone'
