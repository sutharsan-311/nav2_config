# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Config diff utilities: snapshots and parameter-level diffing."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Optional

from nav2_config.types.history import ParamRef
from nav2_config.types.params import ParamValue


@dataclass
class ParamSnapshotEntry:
    """Snapshot of a single parameter at a point in time.

    Args:
        ref: Identifies the node and parameter.
        value: The parameter value at snapshot time.
        type_hint: ROS2 parameter type string.
        ros2_name: The ROS2 parameter name (may differ from dot-notation).
    """

    ref: ParamRef
    value: Any
    type_hint: str
    ros2_name: str


@dataclass
class ParamSnapshot:
    """Collection of parameter values captured at a single point in time.

    Args:
        snapshot_id: UUID4 string identifying this snapshot.
        label: Human-readable label (e.g. 'session_start', filename, timestamp).
        captured_at: When this snapshot was taken.
        entries: Map from ParamRef to ParamSnapshotEntry.
    """

    snapshot_id: str
    label: str
    captured_at: datetime
    entries: dict[ParamRef, ParamSnapshotEntry] = field(default_factory=dict)


class DiffKind(Enum):
    """Describes the relationship between a parameter in two snapshots."""

    ADDED = auto()     # present in right but not in left
    REMOVED = auto()   # present in left but not in right
    CHANGED = auto()   # present in both but values differ


@dataclass
class ParamDiffEntry:
    """One line in a diff result between two snapshots.

    Args:
        ref: The parameter being compared.
        kind: Whether the param was added, removed, or changed.
        left_value: Value in the left (base) snapshot; None if ADDED.
        right_value: Value in the right (target) snapshot; None if REMOVED.
        type_hint: ROS2 parameter type string.
        ros2_name: The ROS2 parameter name.
    """

    ref: ParamRef
    kind: DiffKind
    left_value: Any
    right_value: Any
    type_hint: str
    ros2_name: str

    @property
    def node_path(self) -> str:
        """Full ROS2 node path from the ref."""
        return self.ref.node_path

    @property
    def param_name(self) -> str:
        """Dot-notation parameter name from the ref."""
        return self.ref.param_name


def snapshot_from_param_values(
    node_path: str,
    params: list[ParamValue],
    label: str,
) -> ParamSnapshot:
    """Create a snapshot from live parameter values for one node.

    Args:
        node_path: Full ROS2 path of the node, e.g. '/robot1/controller_server'.
        params: List of ParamValue objects for that node.
        label: Human-readable snapshot label (e.g. 'session_start').

    Returns:
        A ParamSnapshot populated from the given params.
    """
    snapshot = ParamSnapshot(
        snapshot_id=str(uuid.uuid4()),
        label=label,
        captured_at=datetime.now(),
    )
    for pv in params:
        ref = ParamRef(
            node_path=node_path,
            param_name=pv.definition.param,
        )
        snapshot.entries[ref] = ParamSnapshotEntry(
            ref=ref,
            value=pv.current_value,
            type_hint=pv.definition.type,
            ros2_name=pv.definition.ros2_name,
        )
    return snapshot


def diff_snapshots(
    left: ParamSnapshot,
    right: ParamSnapshot,
) -> list[ParamDiffEntry]:
    """Compare two snapshots and return a list of differences.

    Uses str() comparison for values to handle float precision and mixed types
    from different ROS2 parameter sources.

    Args:
        left: The base (older or reference) snapshot.
        right: The target (newer or current) snapshot.

    Returns:
        List of ParamDiffEntry, one per differing parameter.
        Order: changed params first (by param_name), then removed, then added.
    """
    result: list[ParamDiffEntry] = []

    left_keys = set(left.entries.keys())
    right_keys = set(right.entries.keys())

    # Changed: present in both but values differ
    for ref in sorted(left_keys & right_keys, key=lambda r: (r.node_path, r.param_name)):
        left_entry = left.entries[ref]
        right_entry = right.entries[ref]
        if str(left_entry.value) != str(right_entry.value):
            result.append(ParamDiffEntry(
                ref=ref,
                kind=DiffKind.CHANGED,
                left_value=left_entry.value,
                right_value=right_entry.value,
                type_hint=right_entry.type_hint,
                ros2_name=right_entry.ros2_name,
            ))

    # Removed: in left but not in right
    for ref in sorted(left_keys - right_keys, key=lambda r: (r.node_path, r.param_name)):
        left_entry = left.entries[ref]
        result.append(ParamDiffEntry(
            ref=ref,
            kind=DiffKind.REMOVED,
            left_value=left_entry.value,
            right_value=None,
            type_hint=left_entry.type_hint,
            ros2_name=left_entry.ros2_name,
        ))

    # Added: in right but not in left
    for ref in sorted(right_keys - left_keys, key=lambda r: (r.node_path, r.param_name)):
        right_entry = right.entries[ref]
        result.append(ParamDiffEntry(
            ref=ref,
            kind=DiffKind.ADDED,
            left_value=None,
            right_value=right_entry.value,
            type_hint=right_entry.type_hint,
            ros2_name=right_entry.ros2_name,
        ))

    return result
