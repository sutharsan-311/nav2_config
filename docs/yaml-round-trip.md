# YAML Round-Trip Preservation

nav2_config uses [ruamel.yaml](https://yaml.readthedocs.io/en/latest/) instead of PyYAML for all config file operations. The difference: ruamel.yaml preserves your file's formatting when it writes back. PyYAML doesn't — it dumps a clean AST and your comments disappear.

## What Is Preserved

**Comments** — both inline and standalone:
```yaml
controller_server:
  ros__parameters:
    # Increase this if the robot oscillates at low speed
    min_vel_x: 0.05  # m/s
```
Both the `# Increase this...` comment above the param and the `# m/s` inline comment survive load/save intact.

**Blank lines** between parameter groups:
```yaml
    controller_frequency: 20.0

    # Velocity limits
    max_vel_x: 0.5
    min_vel_x: 0.05
```
The blank line is preserved.

**Inline arrays:**
```yaml
    observation_sources: [scan, pointcloud]
```
ruamel.yaml writes this back as an inline array, not as:
```yaml
    observation_sources:
    - scan
    - pointcloud
```

**Nested structure** — the indentation style and nesting depth you wrote originally.

## What May Change

**Boolean canonical form.** YAML has multiple valid spellings for booleans: `True`, `true`, `yes`, `on` all mean the same thing. ruamel.yaml normalizes these to lowercase (`true`/`false`) on write. The value is preserved; the spelling changes. This is cosmetic.

**Trailing whitespace** is stripped. If your editor adds trailing spaces, they'll be gone after save. Not a problem in practice.

## Loading a Config

File > Load Config → select your nav2_params.yaml.

nav2_config reads the file, parses it with ruamel.yaml (preserving the formatting data), and loads the parameter values into the editor. The original file is not modified at this point.

## Saving

`Ctrl+S` writes back to the same file that was loaded. Before writing, nav2_config creates a `.bak` backup:

```
nav2_params.yaml      ← updated file
nav2_params.yaml.bak  ← previous version
```

Only one `.bak` is kept. Each save overwrites the previous backup.

## The YAML Preview Panel

The right panel shows a live YAML preview as you edit parameters. This is **not** the same as the saved file. The preview is generated fresh from current parameter values — it won't have your comments or blank lines. It's useful for seeing what a minimal config would look like, or for copying specific sections.

To see the preserved version, load the file and save it; then open it in a text editor.

## Edge Cases

**Loading a file before making changes.** If you make changes in the GUI without loading a file first, there's no source document for ruamel.yaml to preserve formatting from. The save will produce a clean dump without comments. Load your config first.

**Merging configs.** nav2_config doesn't merge YAML files. If you load a new config, it replaces the previous one entirely. Use the YAML preview to manually copy sections between configs if needed.

**YAML anchors and aliases.** Some hand-written nav2_params.yaml files use YAML anchors (`&anchor`) and aliases (`*anchor`) to avoid repeating values. ruamel.yaml preserves these, but nav2_config's parameter editor doesn't understand them — it shows the resolved values. If you edit a parameter that came from an anchored value, the anchor relationship is broken on save.
