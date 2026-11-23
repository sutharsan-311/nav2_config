# Developer notes & ideas for review

Durable home for maintenance notes and triage ideas. Unlike `BACKLOG.md` (which
`scripts/nav2_param_gap.py` regenerates from scratch on every run and therefore
overwrites), this file is hand-maintained and safe for long-lived notes.

## Ideas for review

- **`restart_node` / `restart_controller` post_set_actions are not dispatched.**
  `Nav2ParamDef.post_set_action` (nav2_config/types/params.py) defines
  `restart_node` and `restart_controller`, and the schema currently uses them on
  9 params (4 `behavior_server` costmap/footprint topic params → `restart_node`;
  5 `controller_server` `follow_path.*` / `path_handler.*` params →
  `restart_controller`). However `node.py`'s `_after_param_set` dispatch only
  handles `clear_costmaps`, `load_map`, `nomotion_update` and `restart_stack`;
  the two restart actions fall through to a silent no-op, so the GUI gives the
  user no signal that the change requires a node/controller restart to take
  effect. Suggested fix: mirror the `restart_stack` branch and emit
  `signals.restart_suggested` (or a dedicated notification) for these two
  actions. Behavioural change — leave for Sutharsan to triage.

- **One-sided numeric ranges never reach a slider and are silently unenforced.**
  `param_row._make_input_widget` (nav2_config/gui/widgets/param_row.py) only
  builds a `ParamSlider` when a `double`/`int` param has **both** bounds set
  (`defn.range.min is not None and defn.range.max is not None`); otherwise it
  falls through to the free-form `ParamInput` at the end of the method.
  `ParamInput` carries no validator/clamp logic, so a param that declares only
  one bound gets a plain text box that accepts any value. 14 schema entries do
  this today, each with a `min` and `max: null`: 10 on `collision_monitor`
  (`min_points`, `min_height`, `max_height`, `min_range`, `time_before_collision`,
  `radius`, `linear_limit`, `angular_limit`, `trigger_consecutive_points`,
  `release_consecutive_points`) and 4 on `collision_detector` (`radius`,
  `min_points`, `trigger_consecutive_points`, `release_consecutive_points`).
  For these the declared lower bound (e.g.
  `radius >= 0.0`, `min_points >= 1`) is documented and still used by
  `test_numeric_default_within_range` to validate the schema default, but it does
  **not** constrain what the user can type in the GUI — a negative radius or a
  zero `min_points` can be entered and sent to the node. The one-sided bound is
  deliberate (these params have a natural floor but no meaningful ceiling), so the
  values are correct; it is only the GUI enforcement that is missing. Possible
  fixes: give `ParamInput` an optional `QDoubleValidator`/`QIntValidator` seeded
  from a one-sided `range`, or let `ParamSlider` accept a single bound with a
  sensible open other end. GUI/behavioural change — leave for Sutharsan to triage.

- **Saving a loaded config re-wraps long inline arrays.** `ConfigFile` uses ruamel's
  default width (80), so a one-value edit to `nav2_params.yaml` rewrites about 35
  lines: `True` becomes `true` (documented in `docs/yaml-round-trip.md`) and long
  `[...]` arrays wrap onto a second line (not documented; the README says inline
  arrays survive unchanged). Probable fix: `self._yaml.width = 4096` in `ConfigFile`.
  Found by the sim test; cosmetic, leave for Sutharsan to triage.

- **The tool's own Set can be re-reported as an external change.** The 2 s watcher can
  poll between a successful set and the baseline update, so the GUI's own change shows
  up as an `EXTERNAL_CHANGE` history row and resets the row's Set button right after
  SUCCESS. Seen in the sim test. Probable fix: update the baseline before the set is
  sent, or ignore a poll that lands while a set is pending.

## Running the sim test

`test/sim/` boots a headless TurtleBot3 Nav2 simulation, runs the real
`Nav2ConfigNode` and `MainWindow` (offscreen) against it, and checks every feature:
discovery, param set, post-set actions, history/undo, config files, Compare, the GUI,
a real navigation goal (including a param change that changes robot speed), and
lifecycle control. It is the `sim` pytest marker and is deselected by default.

```bash
source /opt/ros/humble/setup.bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 QT_QPA_PLATFORM=offscreen \
  python3 -m pytest -m sim test/sim -v
```

- Needs `ros-humble-navigation2`, `nav2-bringup`, `turtlebot3-gazebo`, `nav2-simple-commander`.
- Takes about 6 minutes (about 40 to 100 s of that is booting the sim).
- Refuses to start if Nav2 nodes already exist, and changes live params (it restores them).
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` avoids ROS Humble's `launch_testing` pytest plugin,
  which breaks bare pytest on newer pytest versions.
- Stop a run with Ctrl+C or `timeout -s INT`, never `-s KILL`: KILL skips teardown and
  leaves the sim running, which breaks the next run.
- CI: `.github/workflows/sim-test.yaml` runs it on every push and PR, parallel to `ci.yaml`.
- `test/sim/schema_absent.txt` lists schema params a Humble stack does not declare.
- The two `xfail(strict=True)` restart tests track the bug in "Ideas for review"; fixing
  it makes them pass, which fails the strict xfail and tells you to remove the marker.

## Resolved

- **Duplicate `docking_server` controller params (bare vs `controller.`-prefixed).**
  The 18 docking controller parameters declared as
  `declare_or_get_parameter("controller.<name>", ...)` in
  `nav2_docking/opennav_docking/src/controller.cpp` existed in the schema
  *twice*: once under the bare leaf name (e.g. `param: "k_phi"`, the older
  entries) and once under the correct `controller.`-prefixed name (e.g.
  `controller.k_phi`, added later when the gap tool re-flagged them as missing
  because the bare names did not match the YAML's `controller:` namespace). The
  bare entries never bound to a running node: `param_client` intersects
  `d.ros2_name` against the node's reported names, and the node reports
  `controller.k_phi`, never `k_phi`, so the bare rows always rendered the schema
  default and silently no-opped on write. The 18 bare duplicates were removed,
  keeping the correctly-binding `controller.<name>` entries (defaults verified
  against controller.cpp). This also resolves the former "docking_server
  controller params never bind" idea above.

## Known false positives in the coverage backlog

- **`docking_server` `simulation_step`.** `scripts/nav2_param_gap.py` derives
  the backlog from `nav2_bringup/params/nav2_params.yaml`, whose docking
  `controller:` example lists `simulation_step: 0.1`. That key is stale/renamed:
  the parameter actually declared in
  `nav2_docking/opennav_docking/src/controller.cpp` is
  `controller.simulation_time_step` (default `0.1`), which is already covered in
  the schema as `docking_server` `controller.simulation_time_step`. Do **not** add a
  `simulation_step` entry — it would fabricate a parameter that no longer exists
  in the Nav2 source.
