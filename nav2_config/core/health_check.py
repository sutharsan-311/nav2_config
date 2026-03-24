"""Health check engine for Nav2 parameter validation.

Each rule is a function that receives a nested parameter lookup dict
``{node_name: {param_name: current_value}}`` and returns a
:class:`HealthCheckResult` or ``None`` if the rule cannot be evaluated
(i.e. the required parameters are not in the current view).

Call :func:`run_health_checks` with a flat ``list[ParamValue]`` to run
all registered rules and collect the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from nav2_config.types.params import ParamValue

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

Severity = str  # "error" | "warning" | "info"


@dataclass
class HealthCheckResult:
    """A single health check finding."""

    severity: Severity
    title: str
    message: str
    affected_params: list[str] = field(default_factory=list)


# A rule takes the nested lookup dict and returns a result (or None to skip).
_Lookup = dict[str, dict[str, Any]]
HealthRule = Callable[[_Lookup], HealthCheckResult | None]

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get(lk: _Lookup, node: str, param: str) -> Any | None:
    """Return the current value for (node, param) or None if not loaded."""
    return lk.get(node, {}).get(param)


def _has(lk: _Lookup, node: str, *params: str) -> bool:
    """Return True if ALL of the given param names are present for *node*."""
    node_params = lk.get(node, {})
    return all(p in node_params for p in params)


# ---------------------------------------------------------------------------
# Individual rules
# ---------------------------------------------------------------------------

def _rule_local_inflation_lt_robot_radius(lk: _Lookup) -> HealthCheckResult | None:
    """Local costmap: inflation_radius must be >= robot_radius."""
    if not _has(lk, 'local_costmap', 'inflation_layer.inflation_radius', 'robot_radius'):
        return None
    inflation = float(_get(lk, 'local_costmap', 'inflation_layer.inflation_radius'))
    robot_r = float(_get(lk, 'local_costmap', 'robot_radius'))
    if inflation < robot_r:
        return HealthCheckResult(
            severity='error',
            title='Local inflation radius < robot radius',
            message=(
                f'inflation_layer.inflation_radius ({inflation:.3f} m) is less than '
                f'robot_radius ({robot_r:.3f} m). The robot will collide with obstacles '
                f'it should treat as lethal. Set inflation_radius ≥ robot_radius.'
            ),
            affected_params=['inflation_layer.inflation_radius', 'robot_radius'],
        )
    return None


def _rule_global_inflation_lt_robot_radius(lk: _Lookup) -> HealthCheckResult | None:
    """Global costmap: inflation_radius must be >= robot_radius."""
    if not _has(lk, 'global_costmap', 'inflation_layer.inflation_radius', 'robot_radius'):
        return None
    inflation = float(_get(lk, 'global_costmap', 'inflation_layer.inflation_radius'))
    robot_r = float(_get(lk, 'global_costmap', 'robot_radius'))
    if inflation < robot_r:
        return HealthCheckResult(
            severity='error',
            title='Global inflation radius < robot radius',
            message=(
                f'Global inflation_layer.inflation_radius ({inflation:.3f} m) is less than '
                f'robot_radius ({robot_r:.3f} m). The planner will generate paths that '
                f'clip obstacles. Set inflation_radius ≥ robot_radius.'
            ),
            affected_params=['inflation_layer.inflation_radius', 'robot_radius'],
        )
    return None


def _rule_rpp_lookahead_range_invalid(lk: _Lookup) -> HealthCheckResult | None:
    """RPP: min_lookahead_dist must be <= max_lookahead_dist."""
    if not _has(lk, 'controller_server',
                'FollowPath.min_lookahead_dist', 'FollowPath.max_lookahead_dist'):
        return None
    mn = float(_get(lk, 'controller_server', 'FollowPath.min_lookahead_dist'))
    mx = float(_get(lk, 'controller_server', 'FollowPath.max_lookahead_dist'))
    if mn > mx:
        return HealthCheckResult(
            severity='error',
            title='RPP lookahead range inverted',
            message=(
                f'min_lookahead_dist ({mn:.2f} m) > max_lookahead_dist ({mx:.2f} m). '
                f'This is nonsensical — the adaptive lookahead band is empty. '
                f'Swap the values or increase max_lookahead_dist.'
            ),
            affected_params=['FollowPath.min_lookahead_dist', 'FollowPath.max_lookahead_dist'],
        )
    return None


def _rule_rpp_fixed_lookahead_outside_range(lk: _Lookup) -> HealthCheckResult | None:
    """RPP: lookahead_dist should lie within [min, max]."""
    if not _has(lk, 'controller_server',
                'FollowPath.lookahead_dist',
                'FollowPath.min_lookahead_dist',
                'FollowPath.max_lookahead_dist'):
        return None
    fixed = float(_get(lk, 'controller_server', 'FollowPath.lookahead_dist'))
    mn = float(_get(lk, 'controller_server', 'FollowPath.min_lookahead_dist'))
    mx = float(_get(lk, 'controller_server', 'FollowPath.max_lookahead_dist'))
    if not (mn <= fixed <= mx):
        return HealthCheckResult(
            severity='warning',
            title='RPP fixed lookahead outside adaptive range',
            message=(
                f'lookahead_dist ({fixed:.2f} m) is outside '
                f'[min_lookahead_dist={mn:.2f}, max_lookahead_dist={mx:.2f}]. '
                f'When adaptive lookahead is enabled, this value is unused, '
                f'but it suggests a misconfiguration.'
            ),
            affected_params=[
                'FollowPath.lookahead_dist',
                'FollowPath.min_lookahead_dist',
                'FollowPath.max_lookahead_dist',
            ],
        )
    return None


def _rule_goal_tolerance_too_tight(lk: _Lookup) -> HealthCheckResult | None:
    """Goal tolerance < 0.05 m is practically unreachable on real hardware."""
    if not _has(lk, 'controller_server', 'goal_checker.xy_goal_tolerance'):
        return None
    tol = float(_get(lk, 'controller_server', 'goal_checker.xy_goal_tolerance'))
    if tol < 0.05:
        return HealthCheckResult(
            severity='warning',
            title='xy_goal_tolerance very tight',
            message=(
                f'goal_checker.xy_goal_tolerance ({tol:.3f} m) is below 0.05 m. '
                f'On real hardware, localization noise and wheel slip will prevent '
                f'the robot from reaching such a tight goal. Consider ≥ 0.10 m.'
            ),
            affected_params=['goal_checker.xy_goal_tolerance'],
        )
    return None


def _rule_goal_tolerance_too_loose(lk: _Lookup) -> HealthCheckResult | None:
    """Goal tolerance > 0.5 m may result in the robot stopping far from the goal."""
    if not _has(lk, 'controller_server', 'goal_checker.xy_goal_tolerance'):
        return None
    tol = float(_get(lk, 'controller_server', 'goal_checker.xy_goal_tolerance'))
    if tol > 0.5:
        return HealthCheckResult(
            severity='warning',
            title='xy_goal_tolerance very loose',
            message=(
                f'goal_checker.xy_goal_tolerance ({tol:.3f} m) exceeds 0.5 m. '
                f'The robot will declare success while still {tol:.1f} m from the '
                f'requested position, which may surprise downstream code.'
            ),
            affected_params=['goal_checker.xy_goal_tolerance'],
        )
    return None


def _rule_goal_tolerance_inside_inflation(lk: _Lookup) -> HealthCheckResult | None:
    """Goal tolerance should exceed the local inflation radius, otherwise the goal
    cell is lethal and the controller will never converge cleanly."""
    tol = _get(lk, 'controller_server', 'goal_checker.xy_goal_tolerance')
    inflation = _get(lk, 'local_costmap', 'inflation_layer.inflation_radius')
    if tol is None or inflation is None:
        return None
    tol = float(tol)
    inflation = float(inflation)
    if tol < inflation * 0.5:
        return HealthCheckResult(
            severity='warning',
            title='Goal tolerance inside inflation zone',
            message=(
                f'goal_checker.xy_goal_tolerance ({tol:.3f} m) is less than half of '
                f'local inflation_radius ({inflation:.3f} m). The goal position lies '
                f'inside the inflated obstacle zone; the controller may oscillate near '
                f'the goal or report a planning failure.'
            ),
            affected_params=[
                'goal_checker.xy_goal_tolerance',
                'inflation_layer.inflation_radius',
            ],
        )
    return None


def _rule_controller_frequency_too_low(lk: _Lookup) -> HealthCheckResult | None:
    """controller_frequency < 5 Hz produces jerky, unstable control."""
    if not _has(lk, 'controller_server', 'controller_frequency'):
        return None
    freq = float(_get(lk, 'controller_server', 'controller_frequency'))
    if freq < 5.0:
        return HealthCheckResult(
            severity='warning',
            title='Controller frequency very low',
            message=(
                f'controller_frequency ({freq:.1f} Hz) is below 5 Hz. '
                f'At this rate the robot updates its velocity command infrequently, '
                f'producing jerky motion and poor path tracking. '
                f'Typical values are 10–30 Hz.'
            ),
            affected_params=['controller_frequency'],
        )
    return None


def _rule_controller_frequency_too_high(lk: _Lookup) -> HealthCheckResult | None:
    """controller_frequency > 50 Hz wastes CPU with diminishing returns."""
    if not _has(lk, 'controller_server', 'controller_frequency'):
        return None
    freq = float(_get(lk, 'controller_server', 'controller_frequency'))
    if freq > 50.0:
        return HealthCheckResult(
            severity='info',
            title='Controller frequency unusually high',
            message=(
                f'controller_frequency ({freq:.1f} Hz) exceeds 50 Hz. '
                f'This is rarely beneficial and significantly increases CPU usage. '
                f'Typical values are 10–30 Hz.'
            ),
            affected_params=['controller_frequency'],
        )
    return None


def _rule_local_update_lt_controller_freq(lk: _Lookup) -> HealthCheckResult | None:
    """Local costmap should update at least as fast as the controller loops."""
    ctrl_freq = _get(lk, 'controller_server', 'controller_frequency')
    update_freq = _get(lk, 'local_costmap', 'update_frequency')
    if ctrl_freq is None or update_freq is None:
        return None
    ctrl_freq = float(ctrl_freq)
    update_freq = float(update_freq)
    if update_freq < ctrl_freq:
        return HealthCheckResult(
            severity='warning',
            title='Local costmap update rate < controller rate',
            message=(
                f'local_costmap.update_frequency ({update_freq:.1f} Hz) is slower than '
                f'controller_frequency ({ctrl_freq:.1f} Hz). '
                f'The controller will make decisions on stale obstacle data. '
                f'Set update_frequency ≥ controller_frequency.'
            ),
            affected_params=['update_frequency', 'controller_frequency'],
        )
    return None


def _rule_failure_tolerance_excessive(lk: _Lookup) -> HealthCheckResult | None:
    """failure_tolerance > 5 s means the robot waits a long time before aborting."""
    if not _has(lk, 'controller_server', 'failure_tolerance'):
        return None
    tol = float(_get(lk, 'controller_server', 'failure_tolerance'))
    if tol > 5.0:
        return HealthCheckResult(
            severity='warning',
            title='failure_tolerance is very high',
            message=(
                f'failure_tolerance ({tol:.1f} s) exceeds 5 seconds. '
                f'The robot will sit in a failure state for up to {tol:.0f} s before '
                f'reporting failure. This delays recovery behaviors significantly. '
                f'Typical values are 0.3–2.0 s.'
            ),
            affected_params=['failure_tolerance'],
        )
    return None


def _rule_progress_time_allowance_too_short(lk: _Lookup) -> HealthCheckResult | None:
    """movement_time_allowance < 5 s may abort navigation in crowded areas."""
    if not _has(lk, 'controller_server', 'progress_checker.movement_time_allowance'):
        return None
    allowance = float(_get(lk, 'controller_server', 'progress_checker.movement_time_allowance'))
    if allowance < 5.0:
        return HealthCheckResult(
            severity='warning',
            title='progress_checker.movement_time_allowance very short',
            message=(
                f'progress_checker.movement_time_allowance ({allowance:.1f} s) is under '
                f'5 seconds. In dynamic environments (e.g. corridors with people), the '
                f'robot may be blocked briefly and incorrectly declared stuck. '
                f'Typical values are 10–30 s.'
            ),
            affected_params=['progress_checker.movement_time_allowance'],
        )
    return None


def _rule_rpp_desired_vel_high(lk: _Lookup) -> HealthCheckResult | None:
    """desired_linear_vel > 1.5 m/s is fast for a ground robot in a shared environment."""
    if not _has(lk, 'controller_server', 'FollowPath.desired_linear_vel'):
        return None
    vel = float(_get(lk, 'controller_server', 'FollowPath.desired_linear_vel'))
    if vel > 1.5:
        return HealthCheckResult(
            severity='warning',
            title='RPP desired_linear_vel is very high',
            message=(
                f'FollowPath.desired_linear_vel ({vel:.2f} m/s) exceeds 1.5 m/s. '
                f'At this speed, reaction time to new obstacles is reduced and braking '
                f'distances increase. Verify your robot hardware supports this speed '
                f'and that inflation radii are sized accordingly.'
            ),
            affected_params=['FollowPath.desired_linear_vel'],
        )
    return None


def _rule_rpp_collision_detection_disabled(lk: _Lookup) -> HealthCheckResult | None:
    """Warn if RPP collision detection is disabled while speed is non-trivial."""
    use_collision = _get(lk, 'controller_server', 'FollowPath.use_collision_detection')
    vel = _get(lk, 'controller_server', 'FollowPath.desired_linear_vel')
    if use_collision is None or vel is None:
        return None
    if not bool(use_collision) and float(vel) > 0.3:
        return HealthCheckResult(
            severity='error',
            title='RPP collision detection disabled at non-trivial speed',
            message=(
                f'FollowPath.use_collision_detection is False while '
                f'desired_linear_vel is {float(vel):.2f} m/s. '
                f'The controller will not predict collisions before they occur. '
                f'Only disable collision detection for very slow, carefully supervised operation.'
            ),
            affected_params=['FollowPath.use_collision_detection', 'FollowPath.desired_linear_vel'],
        )
    return None


def _rule_amcl_particles_inverted(lk: _Lookup) -> HealthCheckResult | None:
    """AMCL: max_particles must exceed min_particles."""
    if not _has(lk, 'amcl', 'min_particles', 'max_particles'):
        return None
    mn = int(_get(lk, 'amcl', 'min_particles'))
    mx = int(_get(lk, 'amcl', 'max_particles'))
    if mx <= mn:
        return HealthCheckResult(
            severity='error',
            title='AMCL particle bounds inverted',
            message=(
                f'amcl.max_particles ({mx}) ≤ min_particles ({mn}). '
                f'AMCL requires max_particles > min_particles to operate. '
                f'This will cause a runtime error.'
            ),
            affected_params=['max_particles', 'min_particles'],
        )
    return None


def _rule_transform_tolerance_zero(lk: _Lookup) -> HealthCheckResult | None:
    """Any transform_tolerance at or below zero is invalid."""
    checks = [
        ('local_costmap', 'transform_tolerance'),
        ('global_costmap', 'transform_tolerance'),
        ('amcl', 'transform_tolerance'),
    ]
    for node, param in checks:
        val = _get(lk, node, param)
        if val is not None and float(val) <= 0.0:
            return HealthCheckResult(
                severity='error',
                title=f'{node} transform_tolerance ≤ 0',
                message=(
                    f'{node}.transform_tolerance is {float(val):.3f} s. '
                    f'A zero or negative tolerance causes all TF lookups to fail. '
                    f'Set to a small positive value (0.1–0.3 s is typical).'
                ),
                affected_params=[param],
            )
    return None


def _rule_local_costmap_too_small(lk: _Lookup) -> HealthCheckResult | None:
    """Local costmap smaller than 2 m leaves almost no room for obstacle avoidance."""
    w = _get(lk, 'local_costmap', 'width')
    h = _get(lk, 'local_costmap', 'height')
    if w is None or h is None:
        return None
    w, h = int(w), int(h)
    if min(w, h) < 2:
        return HealthCheckResult(
            severity='warning',
            title='Local costmap very small',
            message=(
                f'local_costmap is {w} m × {h} m. '
                f'A costmap smaller than 2 m in any dimension leaves almost no '
                f'margin for obstacle avoidance and can cause the controller to '
                f'immediately declare failure. Typical values are 3–5 m.'
            ),
            affected_params=['width', 'height'],
        )
    return None


def _rule_global_resolution_finer_than_local(lk: _Lookup) -> HealthCheckResult | None:
    """Global costmap at finer resolution than local is unusual and wastes memory."""
    global_res = _get(lk, 'global_costmap', 'resolution')
    local_res = _get(lk, 'local_costmap', 'resolution')
    if global_res is None or local_res is None:
        return None
    global_res = float(global_res)
    local_res = float(local_res)
    if global_res < local_res:
        return HealthCheckResult(
            severity='info',
            title='Global costmap finer than local costmap',
            message=(
                f'global_costmap.resolution ({global_res:.3f} m/cell) is finer than '
                f'local_costmap.resolution ({local_res:.3f} m/cell). '
                f'This is unusual: the global map typically has coarser resolution '
                f'(e.g. 0.05 m vs 0.05 m local is fine, but 0.02 m global is wasteful). '
                f'Verify this is intentional.'
            ),
            affected_params=['resolution'],
        )
    return None


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

_RULES: list[HealthRule] = [
    _rule_local_inflation_lt_robot_radius,
    _rule_global_inflation_lt_robot_radius,
    _rule_rpp_lookahead_range_invalid,
    _rule_rpp_fixed_lookahead_outside_range,
    _rule_goal_tolerance_too_tight,
    _rule_goal_tolerance_too_loose,
    _rule_goal_tolerance_inside_inflation,
    _rule_controller_frequency_too_low,
    _rule_controller_frequency_too_high,
    _rule_local_update_lt_controller_freq,
    _rule_failure_tolerance_excessive,
    _rule_progress_time_allowance_too_short,
    _rule_rpp_desired_vel_high,
    _rule_rpp_collision_detection_disabled,
    _rule_amcl_particles_inverted,
    _rule_transform_tolerance_zero,
    _rule_local_costmap_too_small,
    _rule_global_resolution_finer_than_local,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_lookup(params: list[ParamValue]) -> _Lookup:
    """Build a ``{node: {param: value}}`` lookup dict from a flat ParamValue list."""
    lookup: _Lookup = {}
    for pv in params:
        lookup.setdefault(pv.definition.node, {})[pv.definition.param] = pv.current_value
    return lookup


def run_health_checks(params: list[ParamValue]) -> list[HealthCheckResult]:
    """Run all registered health check rules against the given parameter list.

    Rules that require parameters not present in *params* are silently skipped
    (they return ``None``).  Only rules with sufficient data produce results.

    Args:
        params: Flat list of :class:`~nav2_config.types.params.ParamValue`
            objects — may span multiple Nav2 nodes.

    Returns:
        List of :class:`HealthCheckResult` findings, sorted by severity
        (errors first, then warnings, then info).
    """
    lookup = build_lookup(params)
    results: list[HealthCheckResult] = []
    for rule in _RULES:
        try:
            result = rule(lookup)
        except Exception:
            # A buggy rule must not crash the GUI.
            continue
        if result is not None:
            results.append(result)

    severity_order = {'error': 0, 'warning': 1, 'info': 2}
    results.sort(key=lambda r: severity_order.get(r.severity, 9))
    return results
