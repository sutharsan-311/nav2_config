# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""ConfigFile — manages the user's nav2_params.yaml as the source of truth.

Nav2's YAML structure has two forms:

Simple nodes::

    controller_server:
      ros__parameters:
        controller_frequency: 20.0
        FollowPath:
          plugin: "dwb_core::DWBLocalPlanner"
          max_vel_x: 0.26

Double-nested costmap nodes::

    local_costmap:
      local_costmap:
        ros__parameters:
          update_frequency: 5.0

``get_value`` / ``set_value`` accept ROS2 node paths
(e.g. ``'/local_costmap/local_costmap'``) and dot-notation param names
(e.g. ``'FollowPath.max_vel_x'``), and handle the mapping transparently.
"""

from __future__ import annotations

import copy
import logging
import shutil
from io import StringIO
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _node_name_to_yaml_keys(node_name: str) -> list[str]:
    """Map a ROS2 node path to the YAML key list ending with 'ros__parameters'.

    Examples::

        '/controller_server'           → ['controller_server', 'ros__parameters']
        '/local_costmap/local_costmap' → ['local_costmap', 'local_costmap', 'ros__parameters']
        '/amcl'                        → ['amcl', 'ros__parameters']
    """
    bare = node_name.lstrip('/')
    parts = [p for p in bare.split('/') if p]
    return parts + ['ros__parameters']


def _traverse_get(data: dict, key_path: list[str], param_parts: list[str]) -> Any:
    """Navigate *data* through *key_path*, then through dot-notation *param_parts*.

    Returns the value found, or ``None`` if any key is missing.
    """
    d: Any = data
    for k in key_path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    for p in param_parts:
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


def _traverse_set(data: dict, key_path: list[str], param_parts: list[str], value: Any) -> None:
    """Navigate *data* through *key_path*, creating missing dicts, then set *value*."""
    d = data
    for k in key_path:
        if not isinstance(d.get(k), dict):
            d[k] = CommentedMap()
        d = d[k]
    for p in param_parts[:-1]:
        if not isinstance(d.get(p), dict):
            d[p] = CommentedMap()
        d = d[p]
    d[param_parts[-1]] = value


def _find_ros_param_paths(data: dict, prefix: list[str]) -> list[str]:
    """Recursively collect all ROS2 node paths that have ros__parameters.

    Descends *data* at any nesting depth.  When a dict value contains the
    key ``ros__parameters``, the accumulated key path is recorded as a ROS2
    node path (``'/' + '/'.join(path)``).  Keys whose values are dicts but
    that do *not* directly contain ``ros__parameters`` are recursed into.

    Args:
        data: The (sub-)dict to search.
        prefix: Key components accumulated from parent levels.

    Returns:
        Sorted list of ROS2 node paths, e.g.
        ``['/amcl', '/local_costmap/local_costmap', '/robot1/controller_server']``.
    """
    paths: list[str] = []
    for key, val in data.items():
        if not isinstance(val, dict):
            continue
        if 'ros__parameters' in val:
            paths.append('/' + '/'.join(prefix + [str(key)]))
        else:
            paths.extend(_find_ros_param_paths(val, prefix + [str(key)]))
    return paths


def _flatten_params(d: Any, prefix: str = '') -> dict[str, Any]:
    """Flatten a nested dict to dot-notation keys.

    Non-dict leaf values are included; dict values are recursed into.
    """
    result: dict[str, Any] = {}
    if not isinstance(d, dict):
        return result
    for k, v in d.items():
        full_key = f'{prefix}.{k}' if prefix else str(k)
        if isinstance(v, dict):
            result.update(_flatten_params(v, full_key))
        else:
            result[full_key] = v
    return result


# ---------------------------------------------------------------------------
# ConfigFile
# ---------------------------------------------------------------------------

class ConfigFile:
    """Manages the user's nav2_params.yaml file.

    Wraps load / save operations and provides per-parameter get/set access
    using ROS2 node paths and dot-notation param names.

    Attributes:
        filepath: Absolute path to the YAML file (may change after ``save_as``).
        original_data: Deep-copy of the data at load time (used to compute diffs).
        modified_data: Working copy of the data; updated by ``set_value``.
    """

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        self.original_data: dict = {}
        self.modified_data: dict = {}
        self._dirty: bool = False
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.allow_unicode = True
        self._yaml.indent(mapping=2, sequence=4, offset=2)

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load and parse the YAML file.

        Returns:
            The parsed data as a nested dict.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file cannot be parsed as YAML.
        """
        path = Path(self.filepath)
        if not path.exists():
            raise FileNotFoundError(f'Config file not found: {self.filepath}')

        try:
            with open(path, encoding='utf-8') as fh:
                data = self._yaml.load(fh) or CommentedMap()
        except YAMLError as exc:
            raise ValueError(f'Failed to parse YAML: {exc}') from exc

        self.original_data = data
        self.modified_data = copy.deepcopy(data)
        self._dirty = False
        logger.info(f'Loaded config file: {self.filepath}')
        return self.modified_data

    def save(self) -> str:
        """Save *modified_data* back to the YAML file.

        Creates a ``.bak`` backup of the original file before writing.
        Clears the dirty flag.

        Returns:
            The file path that was written.
        """
        path = Path(self.filepath)
        if path.exists():
            shutil.copy2(str(path), str(path) + '.bak')
        self._write_yaml(path, self.modified_data)
        self._dirty = False
        logger.info(f'Saved config file: {self.filepath}')
        return self.filepath

    def save_as(self, new_filepath: str) -> str:
        """Save *modified_data* to a different path and update ``self.filepath``.

        Returns:
            The new file path.
        """
        path = Path(new_filepath)
        self._write_yaml(path, self.modified_data)
        self.filepath = new_filepath
        self._dirty = False
        logger.info(f'Saved config file as: {new_filepath}')
        return new_filepath

    def _write_yaml(self, path: Path, data: dict) -> None:
        """Serialize *data* and write it to *path*."""
        with open(path, 'w', encoding='utf-8') as fh:
            self._yaml.dump(data, fh)

    # ------------------------------------------------------------------
    # Per-parameter access
    # ------------------------------------------------------------------

    def get_value(self, node_name: str, param_name: str) -> Any:
        """Get a parameter value from the in-memory YAML.

        Args:
            node_name: Full ROS2 node path, e.g. ``'/controller_server'``.
            param_name: Parameter name, optionally dot-notation, e.g.
                ``'FollowPath.max_vel_x'``.

        Returns:
            The value, or ``None`` if not present in the file.
        """
        key_path = _node_name_to_yaml_keys(node_name)
        param_parts = param_name.split('.')
        return _traverse_get(self.modified_data, key_path, param_parts)

    def set_value(self, node_name: str, param_name: str, value: Any) -> None:
        """Set a parameter value in the in-memory YAML.

        Creates intermediate dicts as needed.  Marks the config as dirty.

        Args:
            node_name: Full ROS2 node path, e.g. ``'/controller_server'``.
            param_name: Parameter name, optionally dot-notation.
            value: New value (Python native type).
        """
        key_path = _node_name_to_yaml_keys(node_name)
        param_parts = param_name.split('.')
        _traverse_set(self.modified_data, key_path, param_parts, value)
        self._dirty = True

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def get_node_names(self) -> list[str]:
        """Return all node names found in the YAML file as ROS2 paths.

        Recursively searches *modified_data* at any nesting depth, so it
        handles simple nodes, double-nested costmap nodes, and arbitrarily
        namespaced nodes produced by the exporter.

        Returns:
            Sorted list of ROS2 node paths, e.g. ``['/amcl', '/controller_server']``.
        """
        return sorted(_find_ros_param_paths(self.modified_data, []))

    def get_all_params_for_node(self, node_name: str) -> dict[str, Any]:
        """Return a flat dict of ``param_name → value`` for *node_name*.

        Dot-notation keys are used for nested params (e.g. ``'FollowPath.max_vel_x'``).

        Returns:
            Empty dict if the node is not present in the file.
        """
        key_path = _node_name_to_yaml_keys(node_name)
        d: Any = self.modified_data
        for k in key_path:
            if not isinstance(d, dict) or k not in d:
                return {}
            d = d[k]
        return _flatten_params(d) if isinstance(d, dict) else {}

    def get_modified_params(self) -> list[tuple[str, str, Any]]:
        """Return all parameters that differ from the originally-loaded values.

        Returns:
            List of ``(node_name, param_name, new_value)`` tuples.
        """
        result: list[tuple[str, str, Any]] = []
        for node_name in self.get_node_names():
            key_path = _node_name_to_yaml_keys(node_name)
            orig_ros = _traverse_get(self.original_data, key_path[:-1], [key_path[-1]])
            mod_ros = _traverse_get(self.modified_data, key_path[:-1], [key_path[-1]])
            if not isinstance(orig_ros, dict) or not isinstance(mod_ros, dict):
                continue
            orig_flat = _flatten_params(orig_ros)
            mod_flat = _flatten_params(mod_ros)
            for pname, new_val in mod_flat.items():
                if orig_flat.get(pname) != new_val:
                    result.append((node_name, pname, new_val))
        return result

    def to_yaml_string(self) -> str:
        """Return the current *modified_data* serialised as a YAML string."""
        buf = StringIO()
        self._yaml.dump(self.modified_data, buf)
        return buf.getvalue()

    @property
    def is_dirty(self) -> bool:
        """``True`` if there are unsaved changes."""
        return self._dirty
