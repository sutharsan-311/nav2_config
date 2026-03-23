# nav2_config — Real-Time Nav2 Parameter Tuning GUI

## Project Overview

nav2_config is a ROS2 desktop application (Python + PyQt6) that connects to a running Nav2 stack and lets developers visually tune navigation parameters in real-time — without killing and relaunching nodes. Think of it as "rqt_reconfigure but built specifically for Nav2" with parameter descriptions, health checks, presets, and YAML export.

**This is a ROS2 package, not a web app.** It installs via `colcon build` or eventually `sudo apt install ros-humble-nav2-config`. It runs as `ros2 run nav2_config gui`.

## Tech Stack

- **Language:** Python 3.10+
- **GUI Framework:** PyQt6
- **ROS2 Client:** rclpy
- **ROS2 Distros:** Humble, Iron, Jazzy
- **Build System:** colcon / setuptools
- **Testing:** pytest + launch_testing

## Commands

```bash
# Build
cd ~/ros2_ws && colcon build --packages-select nav2_config

# Source
source install/setup.bash

# Run
ros2 run nav2_config gui

# Run with specific config file
ros2 run nav2_config gui --ros-args -p config_file:=/path/to/nav2_params.yaml

# Test
colcon test --packages-select nav2_config
```

## Architecture

```
nav2_config/
├── package.xml                    # ROS2 package manifest
├── setup.py                       # Python package setup (ROS2 style)
├── setup.cfg                      # Entry points
├── resource/
│   └── nav2_config                # ROS2 ament resource marker
├── nav2_config/
│   ├── __init__.py
│   ├── main.py                    # Entry point — launches GUI + ROS2 node
│   ├── node.py                    # ROS2 node: discovers Nav2 nodes, reads/writes params
│   ├── gui/
│   │   ├── __init__.py
│   │   ├── main_window.py         # Main window — three collapsible panels
│   │   ├── node_panel.py          # Left panel: discovered Nav2 nodes with status
│   │   ├── param_panel.py         # Center panel: parameter editor with descriptions
│   │   ├── yaml_panel.py          # Right panel: live YAML preview
│   │   ├── health_panel.py        # Health check results panel (in center, collapsible)
│   │   ├── preset_dialog.py       # Preset selection dialog
│   │   ├── import_export.py       # Import/export YAML dialogs
│   │   ├── theme.py               # Dark theme QSS stylesheet (ROS tool aesthetic)
│   │   └── widgets/
│   │       ├── __init__.py
│   │       ├── param_slider.py    # Custom slider with value label + range
│   │       ├── param_toggle.py    # Boolean toggle widget
│   │       ├── param_select.py    # Dropdown for enum params
│   │       ├── param_input.py     # Text/number input
│   │       ├── param_row.py       # Single parameter row (label + input + description)
│   │       ├── node_item.py       # Single node in the node list
│   │       ├── status_bar.py      # Bottom status bar (connection, node count, etc.)
│   │       └── collapsible.py     # Collapsible panel/section widget
│   ├── core/
│   │   ├── __init__.py
│   │   ├── param_client.py        # ROS2 parameter service client (get/set/list)
│   │   ├── node_discovery.py      # Discover running Nav2 nodes
│   │   ├── param_watcher.py       # Watch for external param changes (polling)
│   │   ├── yaml_exporter.py       # Export current params to nav2_params.yaml
│   │   ├── yaml_importer.py       # Import params from YAML file
│   │   ├── health_check.py        # Cross-parameter validation rules
│   │   └── presets.py             # Load/apply environment presets
│   ├── schema/
│   │   ├── __init__.py
│   │   ├── nav2_params.json       # 167+ parameter database (descriptions, ranges, defaults)
│   │   ├── plugins.json           # Plugin registry (planners, controllers, costmap layers)
│   │   └── presets/
│   │       ├── hospital_corridor.yaml
│   │       ├── open_warehouse.yaml
│   │       ├── outdoor_campus.yaml
│   │       ├── simulation_turtlebot3.yaml
│   │       └── tight_retail.yaml
│   └── types/
│       ├── __init__.py
│       └── params.py              # Python dataclasses for param schema, config, etc.
├── test/
│   ├── test_param_client.py
│   ├── test_yaml_exporter.py
│   ├── test_health_check.py
│   └── test_node_discovery.py
├── CLAUDE.md                      # This file
├── BUILD_GUIDE.md                 # Session-by-session Claude Code build plan
└── README.md
```

## How It Works (Runtime Flow)

1. User runs `ros2 run nav2_config gui`
2. App starts a ROS2 node (`nav2_config_node`) in a background thread
3. Node discovers running Nav2 nodes by scanning for known node names:
   `/amcl`, `/controller_server`, `/planner_server`, `/bt_navigator`,
   `/local_costmap/local_costmap`, `/global_costmap/global_costmap`,
   `/smoother_server`, `/velocity_smoother`, `/behavior_server`,
   `/waypoint_follower`, `/map_server`
4. For each discovered node, calls `list_parameters` service to get live params
5. Left panel shows discovered nodes with green (running) / gray (not found) dots
6. Clicking a node fetches its current param values via `get_parameters` service
7. Center panel displays params with descriptions from nav2_params.json schema
8. When user changes a value: `set_parameters` service is called immediately
9. The param takes effect on the running node — no restart needed
10. Right panel shows what the equivalent YAML file would look like
11. "Save to File" writes current live params to a YAML file
12. Health check validates the live config and warns about issues

## ROS2 Parameter Service API

Every ROS2 node exposes these services automatically:
- `/{node}/list_parameters` — list all param names
- `/{node}/get_parameters` — get values for given param names
- `/{node}/set_parameters` — set values (takes effect immediately if node supports it)
- `/{node}/describe_parameters` — get param type/description metadata

Nav2 nodes support dynamic parameter updates for most params. Some params
(like `plugin` selections) require a node restart — the GUI should indicate
which params are "hot-reloadable" vs "requires restart" in the schema.

## Nav2 Parameter Schema (nav2_params.json)

Same schema from the web version. Each entry:
```json
{
  "node": "controller_server",
  "param": "controller_frequency",
  "type": "double",
  "default": 20.0,
  "range": { "min": 1.0, "max": 100.0 },
  "unit": "Hz",
  "description": "How often the controller computes velocity commands.",
  "impact": "Higher = smoother path following but more CPU.",
  "category": "performance",
  "plugin_specific": false,
  "plugin": null,
  "hot_reload": true,
  "tags": ["controller", "frequency", "performance"]
}
```

New field: `hot_reload` — true if this param can be changed at runtime without
restarting the node. false if a node restart is needed (e.g., changing plugins).

## GUI Design — ROS Tool Aesthetic

The GUI should look like it belongs alongside RViz2, Foxglove, and rqt:

- **Colors:** Dark gray panels (#2d2d2d), thin borders (#3e3e42), ROS orange (#f57c00) accent, ROS2 blue (#4fc3f7) for active states, green (#4caf50) for healthy/connected, red (#f44336) for errors
- **Typography:** Monospace for param names, values, YAML. System sans-serif for descriptions and labels.
- **Panels:** Three collapsible panels with thin title bars. Looks like rqt or Foxglove panels.
- **Status bar:** Bottom bar showing connection status, discovered node count, param count
- **No rounded corners:** Flat, rectangular everything. Like RViz.
- **Dense:** Robotics devs want data density. Compact param rows, no wasted space.

## Qt Theme (QSS)

Define in gui/theme.py as a QSS stylesheet string. Apply to QApplication.
Use Qt's property system for state-based styling (active, modified, error).

## Coding Conventions

- Python 3.10+ with type hints everywhere
- Dataclasses for data models
- ROS2 logging via `self.get_logger()` in the node, `logging` in GUI
- Signals/slots for GUI-ROS2 communication (Qt signals from background thread)
- No global state — pass dependencies through constructors
- Test with pytest
- Docstrings on all public methods
- Follow ROS2 Python package conventions (setup.py, package.xml, resource marker)

## Threading Model

Qt runs on the main thread. ROS2 must also run on a thread.
The approach:
1. Main thread: Qt event loop (`app.exec()`)
2. Background thread: `rclpy.spin()` for the ROS2 node
3. Communication: Qt signals emitted from the ROS2 thread, connected to GUI slots
4. Use `QTimer` for periodic GUI updates (param polling every 2 seconds)
5. Parameter set/get calls happen on the ROS2 thread, results emitted as signals

## Development Phases

### Phase 1: Foundation (Session 1-3)
- ROS2 package skeleton
- Parameter schema (port nav2_params.json)
- Qt dark theme
- Main window with three-panel layout
- Node discovery (find running Nav2 nodes)

### Phase 2: Parameter Editing (Session 4-6)
- Param client (get/set via ROS2 services)
- Param panel with custom widgets (sliders, toggles, dropdowns)
- Real-time param writing (change slider → ros2 param set fires)
- Live value polling (detect external param changes)

### Phase 3: YAML + Presets (Session 7-8)
- YAML preview panel (live generation)
- Export to YAML file
- Import from YAML file
- Environment presets (apply preset → set all params at once)

### Phase 4: Health Check + Polish (Session 9-10)
- Health check engine (port rules from web version)
- Health check panel in GUI
- Plugin-aware param filtering
- Search across all params (Ctrl+K)
- Keyboard shortcuts
- Status bar

### Phase 5: Packaging (Session 11)
- Clean up setup.py / package.xml
- Desktop entry file (so it shows up in app launchers)
- README with install instructions
- Test on Humble + Jazzy
