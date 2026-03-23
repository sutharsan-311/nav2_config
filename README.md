# nav2_config

> Real-time visual parameter tuning GUI for ROS2 Nav2

Tune your robot's navigation parameters **while it's running** — without killing and relaunching nodes. See the effect of every parameter change immediately.

## What It Does

nav2_config connects to your running Nav2 stack and gives you a visual editor for every navigation parameter. Change `max_vel_x` and watch your robot speed up. Adjust `inflation_radius` and see the costmap update. No more edit-kill-relaunch-wait-test cycles.

**167 parameters** across 11 Nav2 nodes, each with human-readable descriptions and tuning advice.

## Features

- **Real-time tuning** — change a param, see the effect immediately on the robot
- **Auto-discovery** — finds running Nav2 nodes automatically
- **Parameter descriptions** — every param has a plain-English description and tuning advice
- **Health check** — catches dangerous configs (inflation_radius < robot_radius, mismatched frames, etc.)
- **Plugin-aware** — select MPPI/DWB/RPP controller, see only relevant params
- **Environment presets** — hospital, warehouse, outdoor, simulation, retail starter configs
- **YAML export** — save your tuned params to a deployment-ready nav2_params.yaml
- **YAML import** — load a YAML and apply params to running nodes instantly

## Installation

### From Source

```bash
cd ~/ros2_ws/src
git clone https://github.com/sutharsan-311/nav2_config.git
cd ~/ros2_ws
colcon build --packages-select nav2_config
source install/setup.bash
```

### Dependencies

```bash
pip install PyQt6
# rclpy and rcl_interfaces come with your ROS2 installation
```

## Usage

```bash
# Make sure Nav2 is running (simulation or real robot)
ros2 launch nav2_bringup tb3_simulation_launch.py

# In another terminal, launch nav2_config
ros2 run nav2_config gui
```

The GUI will automatically discover running Nav2 nodes and let you start tuning.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+K | Focus search |
| Ctrl+S | Export YAML |
| Ctrl+I | Import YAML |
| Ctrl+R | Refresh node discovery |
| Escape | Clear search |

## Supported ROS2 Distros

- ROS2 Humble Hawksbill (Ubuntu 22.04)
- ROS2 Iron Irwini (Ubuntu 22.04)
- ROS2 Jazzy Jalisco (Ubuntu 24.04)

## How It Works

nav2_config uses ROS2's built-in parameter services (`list_parameters`, `get_parameters`, `set_parameters`) to read and write parameters on running nodes. Most Nav2 parameters support dynamic reconfiguration — the change takes effect immediately without restarting the node.

Parameters that require a node restart (like changing plugins) are marked in the GUI.

## vs rqt_reconfigure

| Feature | rqt_reconfigure | nav2_config |
|---------|----------------|-------------|
| Generic params | ✓ | ✓ |
| Nav2-specific descriptions | ✗ | ✓ |
| Tuning advice | ✗ | ✓ |
| Health check | ✗ | ✓ |
| Plugin awareness | ✗ | ✓ |
| Environment presets | ✗ | ✓ |
| YAML export | ✗ | ✓ |

## Contributing

PRs welcome. If you have parameter descriptions or tuning tips to improve, the schema lives in `nav2_config/schema/nav2_params.json`.

## License

MIT

## Author

Built by [Sutharsan](https://sutharsan.is-a.dev) — a ROS2 developer who got tired of the kill-edit-relaunch cycle while deploying AMRs in hospitals.
