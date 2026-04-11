# Graph Report - .  (2026-04-10)

## Corpus Check
- 67 files · ~50,440 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1126 nodes · 3013 edges · 94 communities detected
- Extraction: 51% EXTRACTED · 49% INFERRED · 0% AMBIGUOUS · INFERRED: 1483 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `ParamValue` - 201 edges
2. `TopicDiscovery` - 134 edges
3. `FrameDiscovery` - 129 edges
4. `DiscoveredNav2Node` - 126 edges
5. `Nav2ConfigNode` - 105 edges
6. `DiscoveredLifecycleManager` - 86 edges
7. `ParamPanel` - 84 edges
8. `NodePanel` - 75 edges
9. `Nav2ParamClient` - 73 edges
10. `ParamRow` - 72 edges

## Surprising Connections (you probably didn't know these)
- `Write ROUND_TRIP_YAML to a temp file and return a loaded ConfigFile.` --uses--> `ConfigFile`  [INFERRED]
  test/test_config_file.py → nav2_config/core/config_file.py
- `ruamel.yaml must preserve structure that PyYAML discards on dump.` --uses--> `ConfigFile`  [INFERRED]
  test/test_config_file.py → nav2_config/core/config_file.py
- `Comments present in the original YAML survive a load → set → dump cycle.` --uses--> `ConfigFile`  [INFERRED]
  test/test_config_file.py → nav2_config/core/config_file.py
- `Flow-style (inline) sequences are not exploded into block style.` --uses--> `ConfigFile`  [INFERRED]
  test/test_config_file.py → nav2_config/core/config_file.py
- `Blank lines between parameters are kept.` --uses--> `ConfigFile`  [INFERRED]
  test/test_config_file.py → nav2_config/core/config_file.py

## Hyperedges (group relationships)
- **GUI Widget Layer** — widget_param_slider, widget_param_toggle, widget_param_select, widget_param_input, widget_param_row, widget_node_item, widget_status_bar, widget_collapsible [EXTRACTED 1.00]
- **Core Services Layer** — core_param_client, core_node_discovery, core_param_watcher, core_yaml_exporter, core_yaml_importer, core_health_check [EXTRACTED 1.00]
- **GUI Panels Layer** — gui_main_window, gui_node_panel, gui_param_panel, gui_yaml_panel, gui_health_panel, gui_import_export, gui_theme [EXTRACTED 1.00]
- **Threading Bridge Components** — main_py, node_py, signal_bridge, threading_model [EXTRACTED 1.00]
- **Three-Panel UI Layout Components** — screenshot_node_panel, screenshot_param_panel, screenshot_yaml_panel [EXTRACTED 0.98]

## Communities

### Community 0 - "Parameter Input Widgets"
Cohesion: 0.02
Nodes (106): Enum, ParamInput, Dark-themed QLineEdit for string and unconstrained numeric params.      Emits ``, Set the displayed text., Return the current text., _CategorySection, Hide the bar when no node is selected., Collapsible section grouping ParamRow widgets under a category header.      Head (+98 more)

### Community 1 - "Config File & YAML Management"
Cohesion: 0.04
Nodes (88): ConfigFile, Manages the user's nav2_params.yaml file.      Wraps load / save operations and, Load and parse the YAML file.          Returns:             The parsed data as a, Return the current *modified_data* serialised as a YAML string., _find_default_path(), LoadConfigDialog, Return the chosen file path, or '' if cancelled / left blank., Return True if 'Connect to running Nav2 nodes' is checked. (+80 more)

### Community 2 - "TF Frame Discovery"
Cohesion: 0.04
Nodes (100): FrameDiscovery, Discovers TF2 frames published on the running ROS2 system.      Uses a ``tf2_ros, Initialise the tf2 buffer and listener., Return a sorted list of all known TF2 frame IDs.          Parses the YAML string, Return all frames with Nav2-priority frames listed first.          Priority orde, LifecycleClient, LifecycleManagerClient, Restart all discovered Nav2 nodes in the correct lifecycle order.          Seque (+92 more)

### Community 3 - "Node Panel UI"
Cohesion: 0.05
Nodes (21): _colored_letter_icon(), _CountBadge, _NamespaceHeader, _NamespaceSection, _NodeRow, Rounded-rectangle pill showing a param count.  Hidden when count is 0., Rounded rectangle with a white letter — cached., Thin strip with Restart Stack, Pause Stack, and Resume Stack buttons.      All b (+13 more)

### Community 4 - "Icon Resources"
Cohesion: 0.07
Nodes (49): app_icon(), category_icon(), _dot(), _letter_icon(), menu_about(), menu_descriptions(), menu_export(), menu_import() (+41 more)

### Community 5 - "Live Param Tests"
Cohesion: 0.11
Nodes (40): _bare_node(), _bold(), _check_pass(), _color(), compare_node(), _cyan(), get_live_value(), _green() (+32 more)

### Community 6 - "Lifecycle Management"
Cohesion: 0.06
Nodes (17): Send *request* and block until the response arrives or times out.          Uses, Call ``/{node_name}/get_state`` and return the state label.          Args:, Call ``/{node_name}/change_state`` with *transition_id*.          Args:, Transition node from ``unconfigured`` → ``inactive``., Transition node from ``inactive`` → ``active``., Transition node from ``active`` → ``inactive``., Transition node from ``inactive`` → ``unconfigured``., Shut down *node_name* using the appropriate shutdown transition.          Querie (+9 more)

### Community 7 - "Schema Tests"
Cohesion: 0.07
Nodes (5): parsed_params(), raw_params(), test_all_nodes_covered(), test_node_param_uniqueness(), test_numeric_default_within_range()

### Community 8 - "App Entry & Threading"
Cohesion: 0.09
Nodes (7): main(), Target function for the ROS2 background thread.      Uses MultiThreadedExecutor, Launch the nav2_config GUI with a co-running ROS2 node., _spin_node(), _detect_type(), _dot_prefix_category(), rclpy — ROS2 Python Client Library

### Community 9 - "Config File Tests"
Cohesion: 0.08
Nodes (10): config_file(), Write ROUND_TRIP_YAML to a temp file and return a loaded ConfigFile., ruamel.yaml must preserve structure that PyYAML discards on dump., Comments present in the original YAML survive a load → set → dump cycle., Flow-style (inline) sequences are not exploded into block style., Blank lines between parameters are kept., Boolean values survive the round-trip as Python True/False.          ruamel.yaml, The modified value actually appears in the serialised output. (+2 more)

### Community 10 - "Param Client Tests"
Cohesion: 0.13
Nodes (16): _make_mock_client(), _make_mock_future(), mock_node(), _mock_set_response(), _setup_get_params_mock(), test_get_all_nav2_params_fallback_to_defaults(), test_get_all_nav2_params_filters_other_nodes(), test_get_all_nav2_params_live_values() (+8 more)

### Community 11 - "YAML Preview Panel"
Cohesion: 0.1
Nodes (10): QSyntaxHighlighter, _make_fmt(), Extract the top-level section for *bare_node* from a full YAML string., Display only the selected node's section from *_full_yaml_str*., Regenerate the YAML preview showing only the selected node's params.          Ar, Track the selected node; in file mode, re-filter the display., Store the full config file and display only the selected node's section., Return to generated-YAML mode (no config file loaded). (+2 more)

### Community 12 - "Live Param Client Tests"
Cohesion: 0.27
Nodes (21): _bold(), _color(), _cyan(), _fail(), _green(), main(), _ok(), print_summary() (+13 more)

### Community 13 - "Parameter Panel UI"
Cohesion: 0.12
Nodes (8): _LifecycleBar, Shown above the param list when a node is selected.      Displays the node's cur, Update the bar for the currently selected node., Toggle expert mode — refresh visibility of transition buttons., Header bar: title left, Set All + search + Desc toggle right., Refresh the lifecycle bar for *node_path* if it is currently shown., Small colored pill showing lifecycle state text., _StateBadge

### Community 14 - "Config File Core"
Cohesion: 0.12
Nodes (15): _find_ros_param_paths(), _flatten_params(), _node_name_to_yaml_keys(), Flatten a nested dict to dot-notation keys.      Non-dict leaf values are includ, Get a parameter value from the in-memory YAML.          Args:             node_n, Set a parameter value in the in-memory YAML.          Creates intermediate dicts, Return all node names found in the YAML file as ROS2 paths.          Recursively, Return a flat dict of ``param_name → value`` for *node_name*.          Dot-notat (+7 more)

### Community 15 - "Post-Set Action Tests"
Cohesion: 0.19
Nodes (17): Test: load_map service fires with a valid map file., Test: change AMCL param → nomotion_update fires., Test: change AMCL alpha1 → nomotion_update fires., Test: change controller_frequency → no service needed, immediate effect., Test the full flow through Nav2ParamClient + Nav2ServiceCaller., Run a cleanup/restore command; silently ignore failures., Test: change inflation_radius → costmaps auto-clear., Test: change cost_scaling_factor → costmaps auto-clear. (+9 more)

### Community 16 - "Build Guide & Docs"
Cohesion: 0.13
Nodes (15): Build Session 1: Entry Point + Threading, Build Session 4: Parameter Client, Build Session 5: Parameter Editor Panel, core/node_discovery.py — Node Discovery, core/param_client.py — ROS2 Param Client, core/yaml_exporter.py — YAML Exporter, gui/main_window.py — Main Window, gui/node_panel.py — Node Panel (+7 more)

### Community 17 - "Nav2 Node Discovery"
Cohesion: 0.18
Nodes (12): discover_lifecycle_managers(), discover_nav2_nodes(), infer_stack_namespace(), join_ros_path(), Nav2NodeSpec, path_basename(), Join a ROS2 namespace and a relative node path fragment.      Examples::, Discover running Nav2 nodes by matching on basename.      Namespace-agnostic: no (+4 more)

### Community 18 - "ROS2 Service Clients"
Cohesion: 0.17
Nodes (6): Call request_nomotion_update to force AMCL to update without motion.          Re, Call reinitialize_global_localization to scatter AMCL particles.          Useful, Send *request* on *client* synchronously; return response or None on timeout., Call *client* with *request*; return True on success, False on failure/timeout., Call clear_entirely on both global and local costmaps.          Resolves service, Call load_map with the given map file path.          Resolves the service path r

### Community 19 - "Lifecycle Live Tests"
Cohesion: 0.28
Nodes (7): Test getting lifecycle state for all Nav2 nodes via CLI., Test deactivate then reactivate a safe node via CLI., Test our LifecycleClient class directly against the live simulation., run(), test_deactivate_activate(), test_get_state(), test_lifecycle_client()

### Community 20 - "YAML Exporter"
Cohesion: 0.28
Nodes (8): export_yaml(), _format_value(), _node_path_to_yaml_keys(), Write a YAML string to a file.      Args:         yaml_str: YAML content to writ, Format a Python value as a YAML scalar or inline sequence.      Args:         va, Map a ROS2 node path to the YAML key list ending with 'ros__parameters'.      Ex, Generate a nav2_params.yaml string from live parameter values.      Parameters a, save_yaml_to_file()

### Community 21 - "YAML Save Operations"
Cohesion: 0.33
Nodes (3): Save *modified_data* back to the YAML file.          Creates a ``.bak`` backup o, Save *modified_data* to a different path and update ``self.filepath``., Serialize *data* and write it to *path*.

### Community 22 - "GUI Screenshot Assets"
Cohesion: 0.33
Nodes (6): AMCL Node (selected), nav2_config GUI Screenshot, Node Panel (Left Panel), Parameter Panel (Center Panel), Three-Panel Layout Design, YAML Output Panel (Right Panel)

### Community 23 - "Theme & Styling"
Cohesion: 0.5
Nodes (4): apply_theme(), create_rviz_palette(), Return a light QPalette matching RViz2's default Qt appearance., Apply the RViz2-accurate light theme to the QApplication.

### Community 24 - "YAML Importer"
Cohesion: 0.5
Nodes (4): _find_ros_parameters(), import_yaml(), Recursively find all ros__parameters dicts in *data*.      Descends any number o, Parse a nav2_params.yaml file into a flat nested dict.      Handles the ``ros__p

### Community 25 - "Project Overview Docs"
Cohesion: 0.5
Nodes (4): Nav2 Navigation Stack, nav2_config ROS2 Package, Rationale: nav2_config vs rqt_reconfigure, nav2_config README

### Community 26 - "Health Check"
Cohesion: 0.67
Nodes (3): Build Session 7: Health Check, core/health_check.py — Health Check Engine, gui/health_panel.py — Health Panel

### Community 27 - "Hot Reload Params"
Cohesion: 0.67
Nodes (3): Hot Reload Parameter Concept, Rationale: hot_reload field distinguishes live-tunable vs restart-required params, schema/nav2_params.json — Parameter Database

### Community 28 - "MarkerArray Visualization"
Cohesion: 0.67
Nodes (3): MarkerArray Icon, ROS2 MarkerArray Message Type, RViz2 Visualization Tool

### Community 29 - "Velocity Command Types"
Cohesion: 0.67
Nodes (3): Nav2 Velocity Commands, TwistStamped ROS2 Message, TwistStamped Icon

### Community 30 - "Project Documentation"
Cohesion: 1.0
Nodes (2): nav2_config Build Guide, nav2_config CLAUDE.md Project Instructions

### Community 31 - "Parameter Type Defs"
Cohesion: 1.0
Nodes (2): Nav2ParamDef Dataclass, types/params.py — Parameter Dataclasses

### Community 32 - "Threading Rationale"
Cohesion: 1.0
Nodes (2): Rationale: Qt on main thread, ROS2 on background thread, Threading Model: Qt Main + ROS2 Background Thread

### Community 33 - "RobotModel Display"
Cohesion: 1.0
Nodes (2): RobotModel Icon, RViz2 RobotModel Display

### Community 34 - "Odometry Sensor"
Cohesion: 1.0
Nodes (2): Odometry, Odometry Icon

### Community 35 - "PoseArray Message"
Cohesion: 1.0
Nodes (2): PoseArray Icon, ROS2 PoseArray Message Type

### Community 36 - "LaserScan Sensor"
Cohesion: 1.0
Nodes (2): LaserScan Icon, LaserScan ROS2 Sensor Topic

### Community 37 - "Initial Pose Action"
Cohesion: 1.0
Nodes (2): SetInitialPose ROS2 Action, SetInitialPose Icon

### Community 38 - "OK Status Indicator"
Cohesion: 1.0
Nodes (2): OK Status Icon, Status Indicator (Success/OK State)

### Community 39 - "Pose Estimation"
Cohesion: 1.0
Nodes (2): Pose Estimation / Localization, Pose Icon

### Community 40 - "GridCells Costmap"
Cohesion: 1.0
Nodes (2): GridCells Costmap Layer Concept, GridCells Icon

### Community 41 - "Settings Config"
Cohesion: 1.0
Nodes (2): Settings / Configuration Concept, Wrench Icon

### Community 42 - "RViz Rotate Tool"
Cohesion: 1.0
Nodes (2): RViz2 Rotate View Tool, RViz Rotate Tool Icon

### Community 43 - "Occupancy Map"
Cohesion: 1.0
Nodes (2): Map Icon, Occupancy Grid / Map Concept

### Community 44 - "Navigation Goal"
Cohesion: 1.0
Nodes (2): Nav2 Navigation Goal Setting, Set Goal Icon

### Community 45 - "Planned Path"
Cohesion: 1.0
Nodes (2): Nav2 Planned Path Visualization, Path Icon

### Community 46 - "RViz Grid Display"
Cohesion: 1.0
Nodes (2): Grid Icon, RViz2 Grid Display

### Community 47 - "Component 47"
Cohesion: 1.0
Nodes (0): 

### Community 48 - "Component 48"
Cohesion: 1.0
Nodes (0): 

### Community 49 - "Component 49"
Cohesion: 1.0
Nodes (1): ``True`` if ``nav2_msgs`` is installed (service may or may not be running).

### Community 50 - "Component 50"
Cohesion: 1.0
Nodes (1): ``True`` if there are unsaved changes.

### Community 51 - "Component 51"
Cohesion: 1.0
Nodes (1): Construct a Nav2ParamDef from a raw JSON dictionary.

### Community 52 - "Component 52"
Cohesion: 1.0
Nodes (1): True if current_value differs from the confirmed live value.

### Community 53 - "Component 53"
Cohesion: 1.0
Nodes (1): The value last confirmed live on the ROS2 node.

### Community 54 - "Component 54"
Cohesion: 1.0
Nodes (1): Return a human-readable string for the current value.

### Community 55 - "Component 55"
Cohesion: 1.0
Nodes (1): gui/import_export.py — Import/Export Dialogs

### Community 56 - "Component 56"
Cohesion: 1.0
Nodes (1): gui/theme.py — Dark Theme QSS

### Community 57 - "Component 57"
Cohesion: 1.0
Nodes (1): widgets/param_slider.py — Param Slider

### Community 58 - "Component 58"
Cohesion: 1.0
Nodes (1): widgets/param_toggle.py — Param Toggle

### Community 59 - "Component 59"
Cohesion: 1.0
Nodes (1): widgets/param_select.py — Param Select

### Community 60 - "Component 60"
Cohesion: 1.0
Nodes (1): widgets/param_input.py — Param Input

### Community 61 - "Component 61"
Cohesion: 1.0
Nodes (1): widgets/param_row.py — Param Row

### Community 62 - "Component 62"
Cohesion: 1.0
Nodes (1): widgets/node_item.py — Node Item

### Community 63 - "Component 63"
Cohesion: 1.0
Nodes (1): widgets/status_bar.py — Status Bar

### Community 64 - "Component 64"
Cohesion: 1.0
Nodes (1): widgets/collapsible.py — Collapsible Widget

### Community 65 - "Component 65"
Cohesion: 1.0
Nodes (1): core/param_watcher.py — Param Watcher

### Community 66 - "Component 66"
Cohesion: 1.0
Nodes (1): core/yaml_importer.py — YAML Importer

### Community 67 - "Component 67"
Cohesion: 1.0
Nodes (1): schema/plugins.json — Plugin Registry

### Community 68 - "Component 68"
Cohesion: 1.0
Nodes (1): ParamValue Dataclass

### Community 69 - "Component 69"
Cohesion: 1.0
Nodes (1): ParamRange Dataclass

### Community 70 - "Component 70"
Cohesion: 1.0
Nodes (1): Phase 1: Foundation (Sessions 1-3)

### Community 71 - "Component 71"
Cohesion: 1.0
Nodes (1): Phase 2: Parameter Editing (Sessions 4-6)

### Community 72 - "Component 72"
Cohesion: 1.0
Nodes (1): Phase 3: YAML (Sessions 7-8)

### Community 73 - "Component 73"
Cohesion: 1.0
Nodes (1): Phase 4: Health Check + Polish (Sessions 9-10)

### Community 74 - "Component 74"
Cohesion: 1.0
Nodes (1): Phase 5: Packaging (Session 11)

### Community 75 - "Component 75"
Cohesion: 1.0
Nodes (1): PyQt6 — GUI Framework

### Community 76 - "Component 76"
Cohesion: 1.0
Nodes (1): colcon — ROS2 Build System

### Community 77 - "Component 77"
Cohesion: 1.0
Nodes (1): rqt_reconfigure — Comparison Tool

### Community 78 - "Component 78"
Cohesion: 1.0
Nodes (1): Build Session 2: Node Discovery

### Community 79 - "Component 79"
Cohesion: 1.0
Nodes (1): Build Session 3: Parameter Schema + Types

### Community 80 - "Component 80"
Cohesion: 1.0
Nodes (1): Build Session 6: YAML Preview Panel

### Community 81 - "Component 81"
Cohesion: 1.0
Nodes (1): Build Session 8: Search + Shortcuts + Polish

### Community 82 - "Component 82"
Cohesion: 1.0
Nodes (1): Build Session 9: Packaging + README

### Community 83 - "Component 83"
Cohesion: 1.0
Nodes (1): Dark Theme (ROS Tool Aesthetic)

### Community 84 - "Component 84"
Cohesion: 1.0
Nodes (1): Parameter Categories

### Community 85 - "Component 85"
Cohesion: 1.0
Nodes (1): Toolbar

### Community 86 - "Component 86"
Cohesion: 1.0
Nodes (1): Status Bar

### Community 87 - "Component 87"
Cohesion: 1.0
Nodes (1): Error Icon

### Community 88 - "Component 88"
Cohesion: 1.0
Nodes (1): Close Icon

### Community 89 - "Component 89"
Cohesion: 1.0
Nodes (1): Zoom Icon

### Community 90 - "Component 90"
Cohesion: 1.0
Nodes (1): Minus Icon

### Community 91 - "Component 91"
Cohesion: 1.0
Nodes (1): Options Icon

### Community 92 - "Component 92"
Cohesion: 1.0
Nodes (1): Plus Icon

### Community 93 - "Component 93"
Cohesion: 1.0
Nodes (1): Warning Icon

## Knowledge Gaps
- **209 isolated node(s):** `Run a ros2 CLI command and return stdout, or None on failure.`, `Return parameter names from a live ROS2 node, or None if unreachable.`, `Fetch a single parameter value from the live node.      Retries once after a 1 s`, `Load nav2_params.json into {bare_node: {ros2_name: entry}}.      ros2_name defau`, `/local_costmap/local_costmap' -> 'local_costmap'.` (+204 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Project Documentation`** (2 nodes): `nav2_config Build Guide`, `nav2_config CLAUDE.md Project Instructions`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Parameter Type Defs`** (2 nodes): `Nav2ParamDef Dataclass`, `types/params.py — Parameter Dataclasses`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Threading Rationale`** (2 nodes): `Rationale: Qt on main thread, ROS2 on background thread`, `Threading Model: Qt Main + ROS2 Background Thread`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RobotModel Display`** (2 nodes): `RobotModel Icon`, `RViz2 RobotModel Display`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Odometry Sensor`** (2 nodes): `Odometry`, `Odometry Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PoseArray Message`** (2 nodes): `PoseArray Icon`, `ROS2 PoseArray Message Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LaserScan Sensor`** (2 nodes): `LaserScan Icon`, `LaserScan ROS2 Sensor Topic`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Initial Pose Action`** (2 nodes): `SetInitialPose ROS2 Action`, `SetInitialPose Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `OK Status Indicator`** (2 nodes): `OK Status Icon`, `Status Indicator (Success/OK State)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Pose Estimation`** (2 nodes): `Pose Estimation / Localization`, `Pose Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `GridCells Costmap`** (2 nodes): `GridCells Costmap Layer Concept`, `GridCells Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Settings Config`** (2 nodes): `Settings / Configuration Concept`, `Wrench Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RViz Rotate Tool`** (2 nodes): `RViz2 Rotate View Tool`, `RViz Rotate Tool Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Occupancy Map`** (2 nodes): `Map Icon`, `Occupancy Grid / Map Concept`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Navigation Goal`** (2 nodes): `Nav2 Navigation Goal Setting`, `Set Goal Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Planned Path`** (2 nodes): `Nav2 Planned Path Visualization`, `Path Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RViz Grid Display`** (2 nodes): `Grid Icon`, `RViz2 Grid Display`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 47`** (1 nodes): `setup.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 48`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 49`** (1 nodes): ```True`` if ``nav2_msgs`` is installed (service may or may not be running).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 50`** (1 nodes): ```True`` if there are unsaved changes.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 51`** (1 nodes): `Construct a Nav2ParamDef from a raw JSON dictionary.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 52`** (1 nodes): `True if current_value differs from the confirmed live value.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 53`** (1 nodes): `The value last confirmed live on the ROS2 node.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 54`** (1 nodes): `Return a human-readable string for the current value.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 55`** (1 nodes): `gui/import_export.py — Import/Export Dialogs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 56`** (1 nodes): `gui/theme.py — Dark Theme QSS`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 57`** (1 nodes): `widgets/param_slider.py — Param Slider`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 58`** (1 nodes): `widgets/param_toggle.py — Param Toggle`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 59`** (1 nodes): `widgets/param_select.py — Param Select`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 60`** (1 nodes): `widgets/param_input.py — Param Input`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 61`** (1 nodes): `widgets/param_row.py — Param Row`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 62`** (1 nodes): `widgets/node_item.py — Node Item`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 63`** (1 nodes): `widgets/status_bar.py — Status Bar`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 64`** (1 nodes): `widgets/collapsible.py — Collapsible Widget`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 65`** (1 nodes): `core/param_watcher.py — Param Watcher`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 66`** (1 nodes): `core/yaml_importer.py — YAML Importer`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 67`** (1 nodes): `schema/plugins.json — Plugin Registry`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 68`** (1 nodes): `ParamValue Dataclass`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 69`** (1 nodes): `ParamRange Dataclass`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 70`** (1 nodes): `Phase 1: Foundation (Sessions 1-3)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 71`** (1 nodes): `Phase 2: Parameter Editing (Sessions 4-6)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 72`** (1 nodes): `Phase 3: YAML (Sessions 7-8)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 73`** (1 nodes): `Phase 4: Health Check + Polish (Sessions 9-10)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 74`** (1 nodes): `Phase 5: Packaging (Session 11)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 75`** (1 nodes): `PyQt6 — GUI Framework`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 76`** (1 nodes): `colcon — ROS2 Build System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 77`** (1 nodes): `rqt_reconfigure — Comparison Tool`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 78`** (1 nodes): `Build Session 2: Node Discovery`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 79`** (1 nodes): `Build Session 3: Parameter Schema + Types`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 80`** (1 nodes): `Build Session 6: YAML Preview Panel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 81`** (1 nodes): `Build Session 8: Search + Shortcuts + Polish`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 82`** (1 nodes): `Build Session 9: Packaging + README`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 83`** (1 nodes): `Dark Theme (ROS Tool Aesthetic)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 84`** (1 nodes): `Parameter Categories`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 85`** (1 nodes): `Toolbar`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 86`** (1 nodes): `Status Bar`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 87`** (1 nodes): `Error Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 88`** (1 nodes): `Close Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 89`** (1 nodes): `Zoom Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 90`** (1 nodes): `Minus Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 91`** (1 nodes): `Options Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 92`** (1 nodes): `Plus Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Component 93`** (1 nodes): `Warning Icon`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `ParamValue` connect `TF Frame Discovery` to `Parameter Input Widgets`, `Config File & YAML Management`, `YAML Preview Panel`, `Parameter Panel UI`, `YAML Exporter`?**
  _High betweenness centrality (0.206) - this node is a cross-community bridge._
- **Why does `Nav2ConfigNode` connect `Config File & YAML Management` to `App Entry & Threading`, `Parameter Input Widgets`, `TF Frame Discovery`, `Post-Set Action Tests`?**
  _High betweenness centrality (0.140) - this node is a cross-community bridge._
- **Why does `ConfigFile` connect `Config File & YAML Management` to `Config File Tests`, `YAML Save Operations`, `Config File Core`?**
  _High betweenness centrality (0.081) - this node is a cross-community bridge._
- **Are the 196 inferred relationships involving `ParamValue` (e.g. with `Return a MagicMock future that immediately fires any registered callback.      N` and `A minimal mock rclpy Node.`) actually correct?**
  _`ParamValue` has 196 INFERRED edges - model-reasoned connections that need verification._
- **Are the 123 inferred relationships involving `TopicDiscovery` (e.g. with `SignalBridge` and `Nav2ConfigNode`) actually correct?**
  _`TopicDiscovery` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 123 inferred relationships involving `FrameDiscovery` (e.g. with `SignalBridge` and `Nav2ConfigNode`) actually correct?**
  _`FrameDiscovery` has 123 INFERRED edges - model-reasoned connections that need verification._
- **Are the 123 inferred relationships involving `DiscoveredNav2Node` (e.g. with `_StateBadge` and `_LifecycleBar`) actually correct?**
  _`DiscoveredNav2Node` has 123 INFERRED edges - model-reasoned connections that need verification._