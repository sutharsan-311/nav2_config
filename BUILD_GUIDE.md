# nav2_config — Claude Code Build Guide

## Prerequisites

1. **ROS2 Humble or Jazzy** installed and sourced
2. **Python 3.10+** with pip
3. **PyQt6:** `pip install PyQt6`
4. **Claude Code** installed and authenticated
5. **A ROS2 workspace:**
```bash
mkdir -p ~/ros2_ws/src
cd ~/ros2_ws/src
# Clone or copy nav2_config here
```

## Quick Test — Make Sure Nav2 Runs

Before building the GUI, confirm you can interact with Nav2 params:
```bash
# Terminal 1: Launch Nav2 in simulation
ros2 launch nav2_bringup tb3_simulation_launch.py

# Terminal 2: List params on a running node
ros2 param list /controller_server

# Terminal 3: Get a param value
ros2 param get /controller_server controller_frequency

# Terminal 4: Set a param (LIVE, takes effect immediately)
ros2 param set /controller_server controller_frequency 30.0
```

If those commands work, you have everything needed.

## Build Workflow

For each session:
1. `cd ~/ros2_ws/src/nav2_config`
2. Open Claude Code: `claude`
3. Run `/clear` before each session
4. Paste the prompt
5. After it finishes:
```bash
cd ~/ros2_ws
colcon build --packages-select nav2_config
source install/setup.bash
ros2 run nav2_config gui  # test it
```
6. Commit: `git add . && git commit -m "..."`

---

## SESSION 1: Entry Point + Threading + Empty Window (~15 min)

```
Read CLAUDE.md for full project context. This is a ROS2 Python package with PyQt6 GUI.

Build the application entry point and threading model:

1. nav2_config/main.py:
- Main function that:
  a) Initializes rclpy
  b) Creates the ROS2 node (Nav2ConfigNode)
  c) Creates QApplication and main window
  d) Starts rclpy.spin() in a background daemon thread
  e) Runs app.exec() on the main thread
  f) On exit: cleanly shuts down node, destroys it, shuts down rclpy
- Handle Ctrl+C gracefully (signal handler that closes Qt app)

2. nav2_config/node.py — Nav2ConfigNode(rclpy.node.Node):
- Node name: 'nav2_config_node'
- For now just an empty node that logs "Nav2 Config GUI started"
- Add a QObject-based signal bridge class (SignalBridge) that inherits
  from QObject and defines Qt signals for:
  - nodes_discovered(list) — emitted when Nav2 nodes are found
  - params_received(str, dict) — emitted when params for a node arrive
  - param_set_result(str, str, bool) — emitted when a param set succeeds/fails
  - connection_status(bool) — emitted when ROS2 connection changes
- The node holds a reference to SignalBridge so GUI can connect to signals

3. nav2_config/gui/theme.py:
- A QSS (Qt Style Sheet) string for the ROS-tool dark theme:
  - QWidget background: #1e1e1e
  - QLabel color: #d4d4d4
  - QPushButton: bg #2d2d2d, border 1px #3e3e42, color #d4d4d4, hover bg #3e3e42
  - QLineEdit: bg #1e1e1e, border 1px #3e3e42, color #d4d4d4, focus border #4fc3f7
  - QComboBox: bg #2d2d2d, border 1px #3e3e42
  - QScrollBar: thin (8px), bg #1e1e1e, handle #3e3e42
  - QSplitter handle: 2px, #3e3e42
  - QTreeWidget: bg #252526, item hover bg #2a2d2e
  - Selection color: #f57c00 (ROS orange)
  - All text: no-bold by default, font-family monospace for data
- Export as DARK_THEME_QSS string
- Function apply_theme(app: QApplication) that sets the stylesheet

4. nav2_config/gui/main_window.py — MainWindow(QMainWindow):
- Window title: "Nav2 Config"
- Minimum size: 1200x700
- Three-panel layout using QSplitter (horizontal):
  - Left panel: QWidget placeholder (will become node panel)
  - Center panel: QWidget placeholder (will become param panel)
  - Right panel: QWidget placeholder (will become YAML panel)
- Splitter initial sizes: [240, stretch, 300]
- All three panels collapsible (splitter handles are draggable to 0)
- Bottom status bar: QStatusBar showing "Disconnected — No Nav2 nodes found"
- Menu bar: File (Import YAML, Export YAML, Quit), Presets (5 preset actions), Help (About)
- Apply the dark theme from theme.py

5. Make sure the entry point works:
   ros2 run nav2_config gui
   Should open an empty dark window with three splitter panels and a status bar.
```

---

## SESSION 2: Node Discovery (~15 min)

```
Read CLAUDE.md. Build the node discovery system.

1. nav2_config/core/node_discovery.py:
- NAV2_NODES constant: dict mapping expected node names to display names:
  "/amcl": "AMCL",
  "/controller_server": "Controller Server",
  "/planner_server": "Planner Server",
  "/bt_navigator": "BT Navigator",
  "/local_costmap/local_costmap": "Local Costmap",
  "/global_costmap/global_costmap": "Global Costmap",
  "/smoother_server": "Smoother Server",
  "/velocity_smoother": "Velocity Smoother",
  "/behavior_server": "Behavior Server",
  "/waypoint_follower": "Waypoint Follower",
  "/map_server": "Map Server"

- Function discover_nav2_nodes(node: Node) -> dict[str, bool]:
  Uses node.get_node_names_and_namespaces() to get all running nodes.
  Returns a dict mapping each NAV2_NODES key to True (found) or False (not found).

2. Update nav2_config/node.py:
- Add a QTimer-driven discovery loop that runs every 3 seconds
- On each tick: call discover_nav2_nodes, emit nodes_discovered signal
- Track previous state so we only emit when the set of discovered nodes changes
- Log discovered/lost nodes

3. nav2_config/gui/node_panel.py — NodePanel(QWidget):
- Vertical layout
- Title label: "NODES" in monospace, small, uppercase, muted color
- A QTreeWidget or QListWidget showing discovered nodes:
  - Each row: colored dot (green=running, gray=not found) + node display name + param count
  - Clicking a node emits a node_selected(str) signal
  - Selected node gets highlighted with ROS orange left border
- Below the list: "Discovered: X/11 nodes" label
- Refresh button that manually triggers discovery

4. Wire it into main_window.py:
- Replace left panel placeholder with NodePanel
- Connect SignalBridge.nodes_discovered to NodePanel.update_nodes
- Connect NodePanel.node_selected to a slot (print for now)
- Status bar updates: "Connected — X/11 Nav2 nodes discovered"

Test: Launch Nav2 in sim, then run nav2_config gui.
The left panel should show which nodes are running with green dots.
```

---

## SESSION 3: Parameter Schema + Types (~15 min)

```
Read CLAUDE.md. Port the parameter schema from the web version.

1. nav2_config/types/params.py:
- Python dataclasses:

@dataclass
class ParamRange:
    min: float | None = None
    max: float | None = None
    options: list[str] | None = None

@dataclass
class Nav2ParamDef:
    node: str
    param: str
    type: str  # "double", "int", "bool", "string", "string_array"
    default: Any
    range: ParamRange | None
    unit: str
    description: str
    impact: str
    category: str
    plugin_specific: bool
    plugin: str | None
    hot_reload: bool
    tags: list[str]

@dataclass
class ParamValue:
    definition: Nav2ParamDef
    current_value: Any  # live value from ROS2
    is_modified: bool   # differs from default
    is_live: bool       # True if fetched from running node

- Function load_schema() -> list[Nav2ParamDef]:
  Loads nav2_params.json from the package share directory and returns
  a list of Nav2ParamDef objects.

2. nav2_config/schema/nav2_params.json:
- Port the parameter database from the web project.
- If you have the web project's nav2-params.json, convert it to match
  the Nav2ParamDef schema above (add hot_reload field).
- Cover all 11 nodes with at least the core params.
- 150+ parameters minimum.
- Focus on accuracy — these descriptions are the product's value.
- For hot_reload: most numeric params are true, plugin selections are false,
  frame names are false (require node restart).

3. nav2_config/schema/plugins.json:
- Plugin registry with: name, plugin_class, category, description,
  when_to_use, params list.
- Cover all Nav2 plugins: NavFn, SmacPlannerHybrid, SmacPlanner2D, ThetaStar,
  DWB, MPPI, RegulatedPurePursuit, StaticLayer, ObstacleLayer, InflationLayer,
  VoxelLayer.

4. Write a test: test/test_schema.py
- Test that nav2_params.json loads and parses correctly
- Test that all params have required fields
- Test that defaults match expected types
- Test that param count is >= 150
```

---

## SESSION 4: Parameter Client (Read/Write via ROS2) (~20 min)

```
Read CLAUDE.md. Build the ROS2 parameter service client.

1. nav2_config/core/param_client.py:

class Nav2ParamClient:
    def __init__(self, node: Node):
        self.node = node
        self._clients = {}  # cache service clients per node

    def list_params(self, node_name: str) -> list[str]:
        "Call /{node}/list_parameters service, return param names"

    def get_params(self, node_name: str, param_names: list[str]) -> dict[str, Any]:
        "Call /{node}/get_parameters, return {name: value} dict"

    def set_param(self, node_name: str, param_name: str, value: Any) -> bool:
        "Call /{node}/set_parameters for a single param. Return success bool."

    def get_all_nav2_params(self, node_name: str, schema: list[Nav2ParamDef]) -> list[ParamValue]:
        "Get all params for a node, merge with schema definitions.
         For each param in schema where node matches:
         - Try to get live value via get_params
         - If live value exists, use it and mark is_live=True
         - If not (node not running), use schema default and mark is_live=False
         - Set is_modified = (current_value != definition.default)"

- Use rcl_interfaces.srv for ListParameters, GetParameters, SetParameters
- Use rcl_interfaces.msg for Parameter, ParameterValue, ParameterType
- Handle service timeouts gracefully (node might not be running)
- All service calls are synchronous (called from the ROS2 thread)

2. Update nav2_config/node.py:
- Add Nav2ParamClient as a member
- Add methods:
  - fetch_params_for_node(node_name: str) — calls get_all_nav2_params,
    emits params_received signal with results
  - set_param(node_name: str, param_name: str, value: Any) — calls
    set_param on client, emits param_set_result signal
- These methods are called from GUI thread via Qt signals, executed on ROS2 thread

3. Create a thread-safe way for GUI to request param operations:
- QMetaObject.invokeMethod or a simple queue that the ROS2 thread processes
- Or use Qt custom events
- The pattern: GUI calls node.request_fetch_params(node_name),
  node processes it on next spin, emits signal with results

4. Write test: test/test_param_client.py
- Mock the ROS2 service calls
- Test list_params, get_params, set_param
- Test get_all_nav2_params merges schema correctly
- Test timeout handling
```

---

## SESSION 5: Parameter Editor Panel (~25 min)

```
Read CLAUDE.md. Build the central parameter editor panel.

1. nav2_config/gui/widgets/param_slider.py — ParamSlider(QWidget):
- Horizontal layout: QSlider + QDoubleSpinBox (or QSpinBox for ints)
- Slider and spinbox are synced — changing one updates the other
- Range from param schema (min/max)
- Step size: computed from range (range/100 for doubles, 1 for ints)
- Unit label on the right side (e.g., "Hz", "m", "m/s")
- Emits value_changed(float) signal
- Style: slider groove thin (#3e3e42), handle small, chunk color #f57c00

2. nav2_config/gui/widgets/param_toggle.py — ParamToggle(QWidget):
- Horizontal layout: custom toggle switch + "ENABLED"/"DISABLED" label
- The toggle is a small rectangular switch (not rounded pill)
- OFF: bg #3e3e42, ON: bg #4caf50 (green)
- Emits value_changed(bool) signal

3. nav2_config/gui/widgets/param_select.py — ParamSelect(QComboBox):
- Styled QComboBox for enum params
- Populated from param schema range.options
- Emits value_changed(str) signal

4. nav2_config/gui/widgets/param_input.py — ParamInput(QLineEdit):
- For free-text string params
- Styled with dark bg, monospace font
- Emits value_changed(str) signal on editingFinished (not every keystroke)

5. nav2_config/gui/widgets/param_row.py — ParamRow(QWidget):
- Two-column layout (label left, input right)
- Left side: param name in monospace (#4fc3f7 color), description below in muted gray
- Right side: appropriate widget based on param type (slider/toggle/select/input)
- Modified indicator: small orange dot before param name if value != default
- Hot-reload indicator: small icon showing if this param is live-tunable
- "Tuning advice" collapsible section showing the impact field
- Emits param_changed(str, Any) signal (param_name, new_value)
- Method set_value(value) to update the display from external sources

6. nav2_config/gui/param_panel.py — ParamPanel(QWidget):
- Vertical layout with scroll area
- Top bar: current node name + param count + "modified: X" label
- Search field: QLineEdit with Ctrl+K shortcut
- Below search: list of ParamRow widgets grouped by category
- Category headers: collapsible sections with name, param count, collapse toggle
- Plugin selector: when node is controller_server or planner_server,
  show a segmented button bar for plugin selection (MPPI/DWB/RPP etc.)
  Changing plugin filters which params are visible.
- Method load_params(params: list[ParamValue]): creates/updates ParamRow widgets
- Method filter_search(query: str): hides non-matching param rows
- When a param is changed: emit param_change_requested(node_name, param_name, value)

7. Wire into main_window.py:
- Replace center placeholder with ParamPanel
- Connect NodePanel.node_selected → fetch params for that node → load into ParamPanel
- Connect ParamPanel.param_change_requested → Node.set_param (fires ros2 param set)
- Connect Node.param_set_result → update ParamRow status (success/failure feedback)
```

---

## SESSION 6: YAML Preview Panel (~15 min)

```
Read CLAUDE.md. Build the YAML preview and export/import.

1. nav2_config/core/yaml_exporter.py:
- Function export_yaml(params: list[ParamValue], ros_version: str = "humble") -> str:
  Generates a clean nav2_params.yaml string from current param values.
  Groups by node, proper YAML indentation.
  Header comment: "# Generated by nav2_config"
  Comments above non-default values explaining what they do.
  Only exports params for the selected plugin (not all plugins).

- Function save_yaml_to_file(yaml_str: str, filepath: str):
  Writes YAML string to file.

2. nav2_config/core/yaml_importer.py:
- Function import_yaml(filepath: str) -> dict[str, dict[str, Any]]:
  Reads a nav2_params.yaml file.
  Returns nested dict: {node_name: {param_name: value}}.
  Handles the ros__parameters nesting.
  Handles malformed YAML gracefully.

3. nav2_config/gui/yaml_panel.py — YamlPanel(QWidget):
- QPlainTextEdit in read-only mode, monospace font
- Title bar: "YAML PREVIEW · 211 lines"
- Copy button in title bar
- Syntax highlighting using QSyntaxHighlighter subclass:
  - YAML keys: #4fc3f7
  - Numbers: #4caf50
  - Strings: #f57c00
  - Booleans: #4caf50
  - Comments: #808080
- Method update_yaml(params: list[ParamValue]):
  Regenerates the YAML string and updates the text
- Auto-scrolls to show the section for the currently selected node

4. nav2_config/gui/import_export.py:
- ImportDialog: QFileDialog to pick a .yaml file + parse it
- ExportDialog: QFileDialog to save a .yaml file
- Apply imported params: for each param in the YAML, call set_param
  on the running node (live import!)

5. Wire into main_window.py:
- Replace right placeholder with YamlPanel
- Update YAML preview whenever any param changes
- Connect File > Import to ImportDialog
- Connect File > Export to ExportDialog
```

---

## SESSION 7: Health Check + Presets (~20 min)

```
Read CLAUDE.md. Port health check and presets from web version.

1. nav2_config/core/health_check.py:
- Port the health check rules from the web version.
- Same structure: list of rules, each is a function that takes
  a list of ParamValue and returns HealthCheckResult or None.
- At least 15 rules covering safety, consistency, performance, common mistakes.
- Examples: inflation_radius < robot_radius, mismatched frames, etc.

2. nav2_config/gui/health_panel.py — HealthPanel(QWidget):
- Collapsible panel that shows health check results
- Header: "HEALTH CHECK · ✓ Clean" or "⚠ 3 warnings"
- List of issues: severity icon, title, message, affected params
- Clicking an affected param scrolls to it in the ParamPanel
- Auto-runs when params change (debounced 1 second)

3. nav2_config/core/presets.py:
- Function load_preset(name: str) -> dict[str, dict[str, Any]]:
  Loads a preset YAML from the schema/presets/ directory.
  Returns the param overrides.

- Function apply_preset(node: Nav2ConfigNode, preset: dict):
  For each param in the preset, calls set_param on the live node.
  Returns list of successes and failures.

4. Create preset YAML files in schema/presets/:
- hospital_corridor.yaml
- open_warehouse.yaml
- outdoor_campus.yaml
- simulation_turtlebot3.yaml
- tight_retail.yaml
Each file is a standard nav2_params.yaml with only the overridden values.

5. nav2_config/gui/preset_dialog.py — PresetDialog(QDialog):
- Shows the 5 presets in a list
- Each shows: name, description, plugin combo, override count
- "Apply" button: loads the preset and applies params to live nodes
- "Preview" button: shows what params would change
- Warning: "This will change X parameters on Y running nodes. Continue?"

6. Wire into main_window.py:
- Add HealthPanel below the status bar in ParamPanel (or as a collapsible dock)
- Connect Presets menu actions to PresetDialog
- Health check runs automatically after param changes
```

---

## SESSION 8: Search + Keyboard Shortcuts + Polish (~15 min)

```
Read CLAUDE.md. Final polish pass.

1. Search functionality:
- Ctrl+K focuses the search field in ParamPanel
- Typing filters params across all groups (name, description, tags)
- Show: "Showing X of Y parameters"
- Escape clears search and restores all params

2. Keyboard shortcuts:
- Ctrl+K: focus search
- Ctrl+S: export YAML (save to file)
- Ctrl+I: import YAML
- Ctrl+1/2/3: collapse/expand left/center/right panels
- Ctrl+R: refresh node discovery
- Escape: clear search / close dialogs

3. Status bar improvements:
- Left: "Connected · 8/11 nodes · 167 params"
- Center: current node name being edited
- Right: "Last param set: controller_frequency = 30.0 ✓"

4. Param polling:
- Every 2 seconds, re-fetch params for the currently selected node
- If a param changed externally (another tool set it), update the display
- Show a brief flash/highlight on params that changed externally

5. Window state persistence:
- Save window size, position, splitter sizes to a config file
  (~/.config/nav2_config/settings.json)
- Restore on next launch

6. About dialog:
- "nav2_config v0.1.0"
- "Real-time Nav2 parameter tuning"
- "Built by Sutharsan"
- Link to GitHub repo
- ROS2 distro info

7. Clean up any rough edges:
- Make sure all widgets update correctly
- Handle edge cases: node disappears while editing, param set fails, etc.
- Add proper logging throughout
```

---

## SESSION 9: Packaging + README (~10 min)

```
Read CLAUDE.md. Finalize the package for distribution.

1. Verify package.xml has all dependencies correct.

2. Verify setup.py installs all data files (schema JSON, preset YAMLs).

3. Create a .desktop file for Linux app launchers:
nav2_config/resource/nav2_config.desktop:
[Desktop Entry]
Name=Nav2 Config
Comment=Real-time Nav2 parameter tuning GUI
Exec=ros2 run nav2_config gui
Type=Application
Categories=Development;ROS;

4. Update README.md with:
- What nav2_config does (one paragraph)
- Screenshot placeholder
- Installation instructions (from source + eventual apt)
- Usage: ros2 run nav2_config gui
- Features list
- Supported ROS2 distros
- Contributing guide
- License (MIT)

5. Run the full test suite:
cd ~/ros2_ws && colcon test --packages-select nav2_config

6. Build and verify clean install:
cd ~/ros2_ws && colcon build --packages-select nav2_config
source install/setup.bash
ros2 run nav2_config gui

7. Create a GitHub Actions CI workflow at .github/workflows/ci.yaml
that builds and tests the package on Ubuntu 22.04 with ROS2 Humble.
```

---

## Testing Checklist

After all sessions, verify:
- [ ] `colcon build` succeeds with no warnings
- [ ] `ros2 run nav2_config gui` opens the window
- [ ] Node discovery finds running Nav2 nodes (test with simulation)
- [ ] Clicking a node loads its live parameters
- [ ] Changing a slider fires `ros2 param set` and takes effect immediately
- [ ] YAML preview updates live
- [ ] Export saves a valid nav2_params.yaml
- [ ] Import loads a YAML and applies params to running nodes
- [ ] Health check catches inflation_radius < robot_radius
- [ ] Presets apply correctly to running nodes
- [ ] Search filters params
- [ ] Ctrl+K, Ctrl+S, Ctrl+I shortcuts work
- [ ] Status bar shows accurate info
- [ ] Window state persists between launches
- [ ] All pytest tests pass
