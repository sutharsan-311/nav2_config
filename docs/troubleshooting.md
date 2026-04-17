# Troubleshooting

## No nodes discovered

The left panel is empty or all nodes show gray dots.

**Check Nav2 is actually running:**
```bash
ros2 node list
```
You should see `/controller_server`, `/planner_server`, `/amcl`, etc. If not, Nav2 isn't up — nav2_config can't help here.

**Check ROS_DOMAIN_ID:**
```bash
echo $ROS_DOMAIN_ID
```
nav2_config and Nav2 must use the same domain ID. If the robot uses ID 42 and your laptop has 0 (the default), they can't find each other.

```bash
export ROS_DOMAIN_ID=42
ros2 run nav2_config gui
```

**Check the ROS environment is sourced:**
```bash
source /opt/ros/$ROS_DISTRO/setup.bash
source ~/ros2_ws/install/setup.bash
```

For remote robots, see [remote-robot.md](remote-robot.md) for DDS discovery setup.

---

## Service timeout / nodes show gray even when running

nav2_config calls the `list_parameters` service on each node to check if it's alive. If the service doesn't respond within the timeout, the node shows as gray.

This happens most often with remote robots on higher-latency networks (Wi-Fi, especially 5 GHz with interference, or robots on a separate subnet).

The timeouts are hardcoded in `nav2_config/core/param_client.py` — there is no `service_timeout` ROS parameter. nav2_config waits up to 2 seconds for a service to appear, then up to 5 seconds for the service call to complete. These values cannot be changed at runtime.

If nodes are showing gray despite being up, the problem is usually one of:

- **Wrong `ROS_DOMAIN_ID`:** nav2_config and Nav2 must use the same domain ID. Confirm with:
  ```bash
  echo $ROS_DOMAIN_ID
  ```
  Then set it to match your robot before launching:
  ```bash
  export ROS_DOMAIN_ID=42
  ros2 run nav2_config gui
  ```

- **DDS discovery not working:** Run `ros2 node list` on the machine running nav2_config — if Nav2 nodes don't appear there, nav2_config won't see them either. Fix DDS discovery first; see [remote-robot.md](remote-robot.md) for multicast and unicast peer configuration.

- **Firewall blocking DDS traffic:** DDS uses UDP multicast on port 7400 by default. Check that firewall rules aren't dropping this traffic between machines.

Once `ros2 node list` shows the expected Nav2 nodes, nav2_config should discover them successfully.

---

## Wrong parameter type error

You set a parameter and get an error like `Parameter type mismatch` or the set fails silently.

nav2_config reads the parameter's type from the live node via `ParameterType` in `get_parameters` responses and sends values in the correct type. If you're seeing type errors, it's likely a schema mismatch — the schema says a parameter is `double` but the node expects `integer`, for example.

**Fix:** pull the latest version — type fixes are regularly patched in the schema:
```bash
cd ~/ros2_ws/src/nav2_config
git pull
colcon build --packages-select nav2_config && source ~/ros2_ws/install/setup.bash
```

If you're on the latest version and still seeing the error, please [open an issue](https://github.com/sutharsan-311/nav2_config/issues) with:
- The parameter name and node
- The error message
- Your ROS2 distro

---

## Node stuck in Finalized state

The node panel shows a node as `Finalized`. nav2_config cannot recover this — no lifecycle transition can bring a `Finalized` node back. The process needs to restart.

```bash
# Kill and relaunch Nav2 (adjust to your bringup launch file)
ros2 launch nav2_bringup navigation_launch.py
```

See [lifecycle-management.md](lifecycle-management.md) for a full explanation of the `Finalized` state.

---

## YAML comments disappeared after save

You saved the config and the comments in nav2_params.yaml are gone.

This happens when you save without having loaded a config first. nav2_config needs to load the original file to know its formatting — if you make changes and save without loading, it generates a fresh YAML dump with no comments.

**Fix:** always load your config before making changes. File > Load Config before editing anything.

See [yaml-round-trip.md](yaml-round-trip.md) for full details on what is and isn't preserved.

---

## Parameters show as modified when nothing changed

The parameter editor shows a "modified" indicator on parameters you haven't touched.

This is a known issue with schema defaults. nav2_config compares live parameter values against the schema defaults — if a node was launched with a custom config that differs from schema defaults, those params appear modified even though you haven't changed them.

It's cosmetic. The actual values are correct. Pull the latest version for schema default fixes:
```bash
cd ~/ros2_ws/src/nav2_config && git pull
colcon build --packages-select nav2_config && source ~/ros2_ws/install/setup.bash
```

---

## double_array parameters showing as string

Some `double_array` or `integer_array` parameters display as a comma-separated string instead of an editable array.

This is a schema type issue — the schema entry has the wrong type for that parameter. Pull the latest version:
```bash
cd ~/ros2_ws/src/nav2_config && git pull
colcon build --packages-select nav2_config && source ~/ros2_ws/install/setup.bash
```

If the issue persists after updating, [open an issue](https://github.com/sutharsan-311/nav2_config/issues) with the parameter name and node.

---

## GUI doesn't launch / PyQt6 import error

```
ModuleNotFoundError: No module named 'PyQt6'
```

On Humble (Ubuntu 22.04), `python3-pyqt6` isn't in the apt repos. Install via pip:
```bash
pip install PyQt6
colcon build --packages-select nav2_config
source ~/ros2_ws/install/setup.bash
```

---

## libGL error on headless / Docker systems

```
libGL error: unable to load driver
```

or

```
qt.qpa.xcb: could not connect to display
```

The first error needs OpenGL libraries:
```bash
sudo apt install libgl1
```

The second means there's no display server. For headless systems, use a virtual display:
```bash
sudo apt install xvfb
Xvfb :99 -screen 0 1024x768x24 &
export DISPLAY=:99
ros2 run nav2_config gui
```
