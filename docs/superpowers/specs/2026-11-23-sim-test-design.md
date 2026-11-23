# Sim test: nav2_config against a live Nav2 simulation

Status: draft, waiting for approval. Nothing is built yet.

## Why

The tool's whole point is tuning a *running* Nav2 stack. Today nothing proves
that. The 39k passing tests are mock-based (mostly parametrized schema checks),
and the "live" tests (`test_lifecycle_live.py`, `test_param_client_live.py`, 7
tests in `test_post_set_actions.py`) are hard-skipped and only shell out to the
`ros2` CLI, so they never touch `Nav2ConfigNode`, `Nav2ParamClient` or the GUI.

Goal: one automated test that boots a TurtleBot3 Nav2 sim, runs the real tool
against it, checks every feature, and runs on every push in CI (free: the repo
is public).

## Goals

- Fully automatic. One command locally, one workflow in CI. No manual steps.
- Exercises the real code paths (`Nav2ConfigNode`, `MainWindow`) offscreen,
  not the `ros2` CLI. The CLI is used only as an independent check of results.
- Covers every feature in the README (list below), including real navigation.
- Leaves no sim processes behind, even on failure or Ctrl+C.
- Failures are readable: logs uploaded as a CI artifact.

## Non-goals

- Jazzy (Humble only at first), real hardware, multi-robot / namespaced stacks.
- Pixel-level GUI checks. We assert on widget state and signals, not looks.
- Replacing the fast mock tests. They keep running in `ci.yaml` unchanged.

## Anti-goals (a failure even if it "passes")

- Tests that pass without the sim being healthy (e.g. skipping silently).
- A flaky sim start turning every push red.
- A test that leaves the stack in a changed state so later tests lie.

## Approaches considered

- A. Sim step inside `ci.yaml`: one place, but a sim flake blocks the fast checks.
- **B. Separate `sim-test.yaml`, parallel to `ci.yaml` (chosen).** Isolated,
  fast CI keeps its timing, same command works locally.
- C. PR/nightly only: cheapest, but skips direct pushes to `main`. Fallback if B
  proves too flaky.

## Design

### Layout

```
test/sim/conftest.py       fixtures: sim_stack, app (node+window), wait_until
test/sim/test_*.py         one module per area (below)
.github/workflows/sim-test.yaml
```

`sim` pytest marker, registered in `setup.cfg`. Default runs deselect it
(`-m "not sim"`) so `colcon test` and local quick runs stay fast.
Run: `pytest -m sim test/sim` (locally with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
QT_QPA_PLATFORM=offscreen`, because ROS Humble's `launch_testing` plugin breaks
bare pytest on this machine).

### Fixtures

- `sim_stack` (session): launches
  `ros2 launch nav2_bringup tb3_simulation_launch.py headless:=True use_rviz:=False`
  in its own process group with `TURTLEBOT3_MODEL=waffle` and an empty
  `GAZEBO_MODEL_DATABASE_URI` (stops gzserver hanging on model downloads).
  Waits until every lifecycle node reports `active`, publishes the initial
  pose, waits for `/amcl_pose`. Budget 120 s; on timeout it kills the group and
  retries the launch **once**, then fails with the log tail. Teardown:
  SIGINT, then SIGKILL the group, then sweep stray `gzserver`/`gzclient`.
- `app` (session): same wiring as `main.py` (rclpy executor thread, `Nav2ConfigNode`,
  `QApplication`, `MainWindow`), offscreen. About 15 lines, copied rather than
  refactoring `main.py`.
- `wait_until(cond, timeout)`: polls while pumping Qt events. No fixed sleeps.
- `restore_params` (function): snapshots any param a test touches and restores it
  afterwards, so tests don't contaminate each other.

### Test modules (every README feature)

1. **discovery**: all Nav2 nodes found, lifecycle manager found, robot mode
   detected, topic and TF-frame dropdown sources non-empty.
2. **live schema check**: for every schema param on a discovered node, the
   param exists live with a compatible type. Known absences go in an allowlist
   file; anything else fails. This validates the 827 entries against real Nav2.
3. **param set**: round trip for each type (double, int, bool, string, array)
   through the tool, verified with `ros2 param get` as an independent check,
   then restored. Set-button state cycle idle, pending, success, and failure
   on a bad value.
4. **post-set actions**: `clear_costmaps`, `load_map`, `nomotion_update` fire
   and report success. `restart_node` / `restart_controller` are
   `xfail(strict=True)` for the known no-op bug (fixing it flips the test and
   forces removing the marker).
5. **external change detection**: `ros2 param set` out of band, the tool's
   `params_externally_changed` fires and the row updates.
6. **history + undo**: set, entry recorded with source/old/new, undo restores
   the live value.
7. **config files**: load `nav2_bringup`'s `nav2_params.yaml`, compare tab
   diff against live, apply one selected diff, save, comments survive the
   round trip.
8. **GUI**: select a node, edit a `ParamRow`, press Set; YAML, History and
   Compare tabs populate; Ctrl+K search, Ctrl+S, Ctrl+O shortcuts.
9. **navigation (the headline)**: send a `NavigateToPose` goal, expect
   SUCCEEDED. Then through the tool lower `FollowPath.max_vel_x`, send the same
   kind of goal, and assert peak odom speed stays under the new limit, then
   raise it and assert the robot goes faster. This is the README's "change
   `max_vel_x` and watch the robot" claim as a test.
10. **lifecycle (runs last)**: pause stack, all nodes inactive; resume, all
    active; restart stack; expert-mode per-node deactivate/activate. A final
    check that the stack is healthy again and a goal still succeeds.

### CI: `.github/workflows/sim-test.yaml`

- Triggers: push and PR to `main`/`master`, plus `workflow_dispatch`.
  `concurrency` cancels older runs of the same ref.
- `ubuntu-22.04`, `ros-tooling/setup-ros@v0.7` (same as `ci.yaml`), apt
  installs `ros-humble-navigation2`, `ros-humble-nav2-bringup`,
  `ros-humble-turtlebot3-gazebo`, `ros-humble-nav2-simple-commander`;
  `pip install PyQt6 pytest`.
- `timeout-minutes: 30`; target runtime 10 to 15 minutes.
- On failure, upload the sim stdout and `~/.ros/log` as an artifact.

## Calls I made (change any you disagree with)

- Humble only. Jazzy later.
- Copy the ~15 lines of app wiring into the fixture instead of refactoring `main.py`.
- Retry only the sim *start* once, not the whole job, so real test failures are
  never hidden by a retry.
- The two known bugs are strict `xfail`, not fixed here.
- After the sim suite reaches parity, delete the three hard-skipped CLI live
  test files and the skipped live tests in `test_post_set_actions.py`.
  Dead tests that never run are worse than none. This is the last step and
  can be dropped.
- Not committed yet; I'll commit when you say so.

## Left to the builder

Exact world coordinates for the navigation goals (TurtleBot3 world), timeout
tuning once real timings are seen, and the allowlist contents for step 2 (found
by running it once).
