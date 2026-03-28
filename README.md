# nav2_config

> Real-time visual parameter tuning GUI for ROS2 Nav2

Tune your robot's navigation parameters **while it's running** — without killing and relaunching nodes. nav2_config connects to your live Nav2 stack and gives you a visual editor for every navigation parameter. Change `max_vel_x` and watch your robot speed up. Adjust `inflation_radius` and see the costmap respond. No more edit–kill–relaunch–wait–test cycles.

## Screenshot

![nav2_config screenshot](docs/screenshot.png)

*Screenshot placeholder — replace with an actual screenshot once the GUI is running.*

## Features

- **Real-time tuning** — change a parameter, the effect is immediate on the running robot
- **Auto-discovery** — finds all running Nav2 nodes automatically via ROS2 node graph
- **167 parameters** across 11 Nav2 nodes, each with human-readable descriptions and tuning advice
- **Health check** — catches dangerous configs (e.g. `inflation_radius < robot_radius`, mismatched frames)
- **Plugin-aware** — select MPPI / DWB / RPP controller and see only the relevant parameters
- **YAML export** — save your tuned parameters to a deployment-ready `nav2_params.yaml`
- **YAML import** — load a YAML file and apply its parameters to running nodes instantly
- **Dark theme** — ROS tool aesthetic matching RViz2, rqt, and Foxglove

## Supported ROS2 Distros

| Distro | Ubuntu | Status |
|--------|--------|--------|
| Humble Hawksbill | 22.04 LTS | Supported |
| Iron Irwini | 22.04 LTS | Supported |
| Jazzy Jalisco | 24.04 LTS | Supported |

## Installation

### From Source

```bash
# Clone into your workspace
cd ~/ros2_ws/src
git clone https://github.com/sutharsan-311/nav2_config.git

# Install system dependency
sudo apt install python3-pyqt6

# Build
cd ~/ros2_ws
colcon build --packages-select nav2_config
source install/setup.bash
```

### apt (coming soon)

```bash
sudo apt install ros-humble-nav2-config
```

## Usage

```bash
# 1. Make sure Nav2 is running (simulation or real robot)
ros2 launch nav2_bringup tb3_simulation_launch.py

# 2. In another terminal, launch nav2_config
source ~/ros2_ws/install/setup.bash
ros2 run nav2_config gui

# 3. Optional: start with a specific parameter file pre-loaded
ros2 run nav2_config gui --ros-args -p config_file:=/path/to/nav2_params.yaml
```

The GUI auto-discovers running Nav2 nodes. Click any node in the left panel to view and edit its parameters.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` | Focus search |
| `Ctrl+S` | Export YAML |
| `Ctrl+I` | Import YAML |
| `Ctrl+R` | Refresh node discovery |
| `Escape` | Clear search |

## How It Works

nav2_config uses ROS2's built-in parameter services (`list_parameters`, `get_parameters`, `set_parameters`) to read and write parameters on running nodes. Most Nav2 parameters support dynamic reconfiguration — changes take effect immediately without restarting the node.

Parameters that require a node restart (like changing plugins) are marked with a restart icon in the GUI.

## vs rqt_reconfigure

| Feature | rqt_reconfigure | nav2_config |
|---------|----------------|-------------|
| Generic params | ✓ | ✓ |
| Nav2-specific descriptions | ✗ | ✓ |
| Tuning advice | ✗ | ✓ |
| Health check | ✗ | ✓ |
| Plugin awareness | ✗ | ✓ |
| YAML export | ✗ | ✓ |

## Contributing

PRs are welcome. A few areas where contributions are especially valuable:

- **Parameter schema** (`nav2_config/schema/nav2_params.json`) — better descriptions, missing parameters, corrected ranges
- **Health check rules** (`nav2_config/core/health_check.py`) — new cross-parameter validation rules
- **ROS2 distro testing** — test reports on Iron and Jazzy

### Development Setup

```bash
cd ~/ros2_ws/src
git clone https://github.com/sutharsan-311/nav2_config.git
cd ~/ros2_ws
colcon build --packages-select nav2_config
source install/setup.bash

# Run tests
colcon test --packages-select nav2_config
colcon test-result --verbose
```

### Code Style

- Python 3.10+ with type hints everywhere
- Follow existing patterns (dataclasses for models, Qt signals for thread communication)
- Add docstrings to all public methods
- Run `flake8` before submitting

## License

MIT — see [LICENSE](LICENSE) for details.

## Author

Built by [Sutharsan](https://sutharsan.is-a.dev) — a ROS2 developer who got tired of the kill-edit-relaunch cycle while deploying AMRs in hospitals.
