# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Data types for Nav2 parameter schema and live values."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParamRange:
    """Numeric range or discrete options for a parameter."""

    min: float | None = None
    max: float | None = None
    options: list[str] | None = None


@dataclass
class Nav2ParamDef:
    """Definition of a single Nav2 parameter from the schema database."""

    node: str
    param: str
    type: str  # "double", "int", "bool", "string", "string_array"
    default: Any
    range: ParamRange | None
    unit: str
    description: str
    impact: str
    category: str
    plugin_specific: bool
    plugin: str | None
    hot_reload: bool
    tags: list[str] = field(default_factory=list)
    # Full ROS2 parameter name as reported by the running node (e.g.
    # "FollowPath.max_vel_x").  Defaults to ``param`` when not set in JSON,
    # which is correct for all top-level parameters that need no namespace.
    ros2_name: str = field(default="")
    # Service to call after a successful param set.
    # None: takes effect immediately; no follow-up needed.
    # "clear_costmaps": call clear_entirely on both costmaps.
    # "load_map": call /map_server/load_map with the new value.
    # "nomotion_update": call /request_nomotion_update on AMCL.
    # "restart_stack": requires Nav2 restart; show notification instead.
    post_set_action: str | None = None

    def __post_init__(self) -> None:
        if not self.ros2_name:
            self.ros2_name = self.param

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Nav2ParamDef":
        """Construct a Nav2ParamDef from a raw JSON dictionary."""
        raw_range = data.get("range")
        param_range: ParamRange | None = None
        if raw_range:
            param_range = ParamRange(
                min=raw_range.get("min"),
                max=raw_range.get("max"),
                options=raw_range.get("options"),
            )
        return cls(
            node=data["node"],
            param=data["param"],
            type=data["type"],
            default=data["default"],
            range=param_range,
            unit=data.get("unit", ""),
            description=data["description"],
            impact=data.get("impact", ""),
            category=data.get("category", "general"),
            plugin_specific=data.get("plugin_specific", False),
            plugin=data.get("plugin"),
            hot_reload=data.get("hot_reload", True),
            tags=data.get("tags", []),
            ros2_name=data.get("ros2_name", data["param"]),
            post_set_action=data.get("post_set_action"),
        )


@dataclass
class ParamValue:
    """A live parameter value paired with its schema definition.

    Three value fields are tracked:
    - ``current_value``: the pending/displayed value (updated on every GUI change).
    - ``confirmed_value``: the value last confirmed as live on the ROS2 node
      (updated only when a parameter set succeeds or fresh params are fetched).
    - ``file_value``: the value read from the nav2_params.yaml config file
      (set by MainWindow after a config file is loaded; None if no file is loaded).

    ``is_pending`` is True when the user has made a change that has not yet been
    sent to the ROS2 node (current_value != confirmed_value).
    """

    definition: Nav2ParamDef
    current_value: Any          # Pending/displayed value; updated on every GUI change
    is_modified: bool = False   # True if current_value differs from definition.default
    is_live: bool = False       # True if current_value was fetched from a running node
    confirmed_value: Any = None # Last value confirmed live on the ROS2 node
    file_value: Any = None      # Value from nav2_params.yaml; None if no config loaded

    def __post_init__(self) -> None:
        if self.confirmed_value is None:
            self.confirmed_value = self.current_value

    def update(self, new_value: Any) -> None:
        """Update the pending/displayed value and recalculate the modified flag.

        Does NOT update confirmed_value — call :meth:`confirm` for that.
        """
        self.current_value = new_value
        self.is_modified = new_value != self.definition.default

    def confirm(self, confirmed: Any) -> None:
        """Record that *confirmed* was successfully set on the ROS2 node.

        Updates confirmed_value.  current_value is left unchanged (the user
        may have typed a new value during the pending period).
        """
        self.confirmed_value = confirmed

    @property
    def is_pending(self) -> bool:
        """True if current_value differs from the confirmed live value."""
        return self.current_value != self.confirmed_value

    @property
    def live_value(self) -> Any:
        """The value last confirmed live on the ROS2 node."""
        return self.confirmed_value

    @property
    def display_value(self) -> str:
        """Return a human-readable string for the current value."""
        if self.definition.unit:
            return f"{self.current_value} {self.definition.unit}"
        return str(self.current_value)


def load_schema() -> list[Nav2ParamDef]:
    """Load the Nav2 parameter schema from the installed package share directory.

    Returns a list of Nav2ParamDef objects parsed from nav2_params.json.
    Falls back to reading from the source tree if the package is not installed.
    """
    import os

    # Try installed location first (colcon build / apt install)
    try:
        from ament_index_python.packages import get_package_share_directory
        share_dir = get_package_share_directory("nav2_config")
        schema_path = os.path.join(share_dir, "schema", "nav2_params.json")
    except Exception:
        # Fall back to source-relative path for development without colcon
        schema_path = os.path.join(
            os.path.dirname(__file__), "..", "schema", "nav2_params.json"
        )

    with open(schema_path, encoding="utf-8") as f:
        raw: list[dict[str, Any]] = json.load(f)

    return [Nav2ParamDef.from_dict(entry) for entry in raw]
