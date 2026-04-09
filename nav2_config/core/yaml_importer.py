# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""YAML import for Nav2 parameter files.

Parses nav2_params.yaml files and returns a nested dict of
{node_name: {param_name: value}}, unwrapping the ``ros__parameters`` nesting
that ROS2 parameter YAML files use.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _find_ros_parameters(data: dict, path: list[str]) -> list[tuple[list[str], dict]]:
    """Recursively find all ros__parameters dicts in *data*.

    Descends any number of nesting levels.  When a key ``ros__parameters``
    whose value is a dict is found, the current path and that dict are
    collected.  Recursion continues into non-``ros__parameters`` dict values.

    Args:
        data: The (sub-)dict to search.
        path: YAML key components accumulated so far (grows with each recursion).

    Returns:
        List of ``(path_components, params_dict)`` where *path_components* are
        the YAML keys leading to that ``ros__parameters`` section.
    """
    results: list[tuple[list[str], dict]] = []
    for key, val in data.items():
        if key == 'ros__parameters':
            if isinstance(val, dict):
                results.append((list(path), val))
        elif isinstance(val, dict):
            results.extend(_find_ros_parameters(val, path + [str(key)]))
    return results


def import_yaml(filepath: str) -> dict[str, dict[str, Any]]:
    """Parse a nav2_params.yaml file into a flat nested dict.

    Handles the ``ros__parameters`` nesting convention used by Nav2 and
    ROS2 parameter files.  Any node entry that lacks ``ros__parameters``
    is treated as if the top-level dict *is* the parameter dict.

    Malformed YAML, missing files, and unexpected structures are logged
    as warnings/errors and result in an empty dict rather than exceptions.

    Args:
        filepath: Path to the ``.yaml`` / ``.yml`` file to import.

    Returns:
        ``{node_name: {param_name: value}}`` for each node found.
        Returns an empty dict if the file cannot be read or parsed.
    """
    try:
        import yaml  # PyYAML — standard ROS2 dep (python3-yaml)
    except ImportError:
        logger.error("PyYAML is not installed — cannot import YAML files")
        return {}

    try:
        with open(filepath, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except OSError as exc:
        logger.error("Cannot read YAML file %s: %s", filepath, exc)
        return {}
    except yaml.YAMLError as exc:
        logger.error("Malformed YAML in %s: %s", filepath, exc)
        return {}

    if raw is None:
        logger.warning("YAML file %s is empty", filepath)
        return {}

    if not isinstance(raw, dict):
        logger.warning(
            "YAML file %s does not contain a top-level mapping (got %s)",
            filepath,
            type(raw).__name__,
        )
        return {}

    result: dict[str, dict[str, Any]] = {}

    # Recursively locate all ros__parameters sections at any nesting depth.
    found = _find_ros_parameters(raw, [])
    for path_components, ros_params in found:
        # Reconstruct the full ROS2 node path from the YAML key path.
        node_path = '/' + '/'.join(path_components)
        params = {str(k): v for k, v in ros_params.items()}
        if params:
            result[node_path] = params

    logger.debug("import_yaml(%s): found %d nodes", filepath, len(result))
    return result
