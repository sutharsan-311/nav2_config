"""Preset loading and application for nav2_config.

Presets are standard nav2_params.yaml files stored in schema/presets/.
Each preset contains only the parameter overrides relevant to a target
environment — all other parameters stay at their current values.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from nav2_config.node import Nav2ConfigNode
    from nav2_config.types.params import Nav2ParamDef

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Node path translation: bare schema name → full ROS2 path
# ---------------------------------------------------------------------------

_NODE_PATH_MAP: dict[str, str] = {
    'amcl': '/amcl',
    'controller_server': '/controller_server',
    'planner_server': '/planner_server',
    'bt_navigator': '/bt_navigator',
    'local_costmap': '/local_costmap/local_costmap',
    'global_costmap': '/global_costmap/global_costmap',
    'smoother_server': '/smoother_server',
    'velocity_smoother': '/velocity_smoother',
    'behavior_server': '/behavior_server',
    'waypoint_follower': '/waypoint_follower',
    'map_server': '/map_server',
}

# ---------------------------------------------------------------------------
# Preset metadata (for display in the dialog)
# ---------------------------------------------------------------------------

PRESET_META: dict[str, dict[str, str]] = {
    'hospital_corridor': {
        'name': 'Hospital Corridor',
        'description': 'Slow, precise navigation in narrow hallways with pedestrians.',
        'scenario': 'Indoor · Dynamic · Narrow',
    },
    'open_warehouse': {
        'name': 'Open Warehouse',
        'description': 'Fast throughput on wide, clear lanes between shelving.',
        'scenario': 'Indoor · Semi-static · Wide lanes',
    },
    'outdoor_campus': {
        'name': 'Outdoor Campus',
        'description': 'Moderate speed on paved paths with varied obstacles.',
        'scenario': 'Outdoor · Mixed terrain · Pedestrians',
    },
    'simulation_turtlebot3': {
        'name': 'Simulation (TurtleBot3)',
        'description': 'Conservative defaults tuned for TurtleBot3 Waffle in Gazebo.',
        'scenario': 'Simulation · TurtleBot3 · ROS2 Nav2 defaults',
    },
    'tight_retail': {
        'name': 'Tight Retail',
        'description': 'Very slow, high-precision navigation in congested retail aisles.',
        'scenario': 'Indoor · Dynamic · Very narrow',
    },
}

# Canonical display order for the preset list.
PRESET_ORDER: list[str] = [
    'hospital_corridor',
    'open_warehouse',
    'outdoor_campus',
    'simulation_turtlebot3',
    'tight_retail',
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_presets_dir() -> str:
    """Return the path to the presets directory.

    Tries the ament-installed share directory first (for deployed packages),
    then falls back to the source tree (for development without colcon build).
    """
    try:
        from ament_index_python.packages import get_package_share_directory
        share_dir = get_package_share_directory('nav2_config')
        return os.path.join(share_dir, 'schema', 'presets')
    except Exception:
        return os.path.join(
            os.path.dirname(__file__), '..', 'schema', 'presets'
        )


def load_preset(name: str) -> dict[str, dict[str, Any]]:
    """Load a preset YAML and return its parameter overrides.

    Args:
        name: Preset key, e.g. ``'hospital_corridor'``.

    Returns:
        Nested dict ``{bare_node_name: {param_name: value}}``.
        The node names match schema convention (e.g. ``'controller_server'``),
        not ROS2 full paths.

    Raises:
        FileNotFoundError: If the preset file does not exist.
        ValueError: If the YAML cannot be parsed into the expected structure.
    """
    presets_dir = get_presets_dir()
    filepath = os.path.join(presets_dir, f'{name}.yaml')

    if not os.path.exists(filepath):
        raise FileNotFoundError(f'Preset file not found: {filepath}')

    with open(filepath, encoding='utf-8') as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f'Preset {name}: expected a YAML mapping at top level')

    result: dict[str, dict[str, Any]] = {}
    for node_key, node_data in raw.items():
        if not isinstance(node_data, dict):
            continue
        # Support both flat {node: {param: val}} and ROS2 style {node: {ros__parameters: {...}}}
        ros_params = node_data.get('ros__parameters', node_data)
        if isinstance(ros_params, dict):
            result[node_key] = ros_params

    logger.debug(
        'Loaded preset %r: %d nodes, %d total params',
        name,
        len(result),
        sum(len(v) for v in result.values()),
    )
    return result


def count_preset_params(preset_data: dict[str, dict[str, Any]]) -> int:
    """Return the total number of parameter overrides in a loaded preset."""
    return sum(len(params) for params in preset_data.values())


def apply_preset(
    node: 'Nav2ConfigNode',
    preset_data: dict[str, dict[str, Any]],
    schema: 'list[Nav2ParamDef]',
) -> int:
    """Submit set_param requests for every override in *preset_data*.

    Requests are placed on the ROS2 node's work queue (non-blocking).  Results
    are reported asynchronously via ``node.signals.param_set_result``.

    Args:
        node: The running :class:`~nav2_config.node.Nav2ConfigNode`.
        preset_data: Preset overrides as returned by :func:`load_preset`.
        schema: Full parameter schema list used to resolve type hints.

    Returns:
        Total number of set_param requests submitted.
    """
    # Build a (bare_node, param) → type_hint lookup from the schema.
    type_map: dict[tuple[str, str], str] = {
        (d.node, d.param): d.type for d in schema
    }

    count = 0
    for bare_node, params in preset_data.items():
        node_path = _NODE_PATH_MAP.get(bare_node, f'/{bare_node}')
        for param_name, value in params.items():
            type_hint = type_map.get((bare_node, param_name), '')
            node.request_set_param(node_path, param_name, value, type_hint)
            count += 1
            logger.debug('Preset: queuing %s/%s = %r', node_path, param_name, value)

    logger.info('apply_preset: submitted %d param set requests', count)
    return count
