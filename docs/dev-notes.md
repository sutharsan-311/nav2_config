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
