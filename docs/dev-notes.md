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

- **`docking_server` controller params never bind to the live node.** All 18
  parameters the docking controller declares under the `controller.` prefix in
  `nav2_docking/opennav_docking/src/controller.cpp`
  (`k_phi`, `k_delta`, `beta`, `lambda`, `v_linear_min`, `v_linear_max`,
  `v_angular_max`, `slowdown_radius`, `deceleration_max`,
  `rotate_to_heading_angular_vel`, `rotate_to_heading_max_angular_accel`,
  `use_collision_detection`, `costmap_topic`, `footprint_topic`,
  `transform_tolerance`, `projection_time`, `simulation_time_step`,
  `dock_collision_threshold`) are declared via
  `declare_or_get_parameter("controller.<name>", ...)`, so the running node
  reports them as `controller.<name>`. In the schema these entries store the
  bare name (e.g. `param: "k_phi"`) with no `ros2_name`, so
  `Nav2ParamDef.ros2_name` falls back to `"k_phi"`.
  `param_client.get_all_nav2_params` binds live values by intersecting
  `d.ros2_name` against the node's reported names
  (`ros2_names = [d.ros2_name for d in node_defs if d.ros2_name in existing_names]`,
  param_client.py). `"k_phi"` is never in `existing_names` (which holds
  `"controller.k_phi"`), so these params are never fetched and never set — they
  always render the schema default and silently no-op on write. Contrast the
  established nested-param convention (e.g. `controller_server`
  `FollowPath.desired_linear_vel`), where the full dotted name lives in `param`
  itself and `ros2_name` is null. Suggested fix: make the docking controller
  entries match that convention — either rename `param` to `controller.<name>`
  (changes the GUI display label and the `(node, param)` key, matching
  `FollowPath.*`) or add an explicit `ros2_name: "controller.<name>"` (keeps the
  short display label but diverges from the convention). Behavioural change
  touching 18 entries plus a display/convention decision — leave for Sutharsan
  to triage.

## Known false positives in the coverage backlog

- **`docking_server` `simulation_step`.** `scripts/nav2_param_gap.py` derives
  the backlog from `nav2_bringup/params/nav2_params.yaml`, whose docking
  `controller:` example lists `simulation_step: 0.1`. That key is stale/renamed:
  the parameter actually declared in
  `nav2_docking/opennav_docking/src/controller.cpp` is
  `controller.simulation_time_step` (default `0.1`), which is already covered in
  the schema as `docking_server.simulation_time_step`. Do **not** add a
  `simulation_step` entry — it would fabricate a parameter that no longer exists
  in the Nav2 source.
