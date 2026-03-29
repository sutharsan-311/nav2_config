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
    for node_name, node_data in raw.items():
        if not isinstance(node_data, dict):
            logger.debug("Skipping non-dict node entry: %s", node_name)
            continue

        # Unwrap ros__parameters if present; otherwise treat the dict directly.
        ros_params = node_data.get("ros__parameters")
        params: dict[str, Any] | None = None
        if isinstance(ros_params, dict):
            params = ros_params
        elif ros_params is None:
            # No ros__parameters key — the dict itself may be flat params.
            params = {k: v for k, v in node_data.items() if not isinstance(v, dict)}
        else:
            logger.warning(
                "Node %s has a non-dict ros__parameters value (%s) — skipping",
                node_name,
                type(ros_params).__name__,
            )
            continue

        if params:
            result[str(node_name)] = {str(k): v for k, v in params.items()}

    logger.debug("import_yaml(%s): found %d nodes", filepath, len(result))
    return result
