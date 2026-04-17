# History and Compare

nav2_config tracks every parameter change you make and lets you diff the live stack against a YAML file. Both features live in the bottom panel tabs.

---

## History Tab

### What gets recorded

Every parameter set that succeeds on the ROS2 node is recorded as a history entry. Each entry captures:

- **Timestamp** — wall-clock time when the set was confirmed
- **Source** — how the change originated (`GUI`, `external` for changes detected via the param watcher, or `import` for bulk YAML imports)
- **Node** — full ROS2 path (e.g. `/robot1/controller_server`)
- **Parameter name** — dot-notation (e.g. `FollowPath.max_vel_x`)
- **Old value** — the value before the change
- **New value** — the value that was set

Entries appear newest-first. The list is not paginated — it grows for the duration of the session.

### How to undo a change

1. Click the entry you want to revert in the History tab
2. Click **Undo** — nav2_config calls `set_parameters` on the live node with the old value

The entry's status updates to reflect whether the undo succeeded or failed. If the node is no longer reachable, the undo will fail and the entry will be marked accordingly.

### Limitations

- **Session-only.** History is held in memory. Restarting nav2_config clears it — there is no persistence to disk.
- **Single-step undo only.** Clicking Undo reverts that one entry; it does not roll back subsequent changes to the same parameter that happened after it.
- **No undo for stack restarts.** Lifecycle operations (Restart Stack, Pause Stack) are not recorded in the history.

---

## Compare Tab

### Source options

The Compare tab diffs the live Nav2 parameter state against a reference snapshot. Three sources are available from the dropdown:

- **Live Nav2** — compares the current in-memory param values against a previously captured snapshot of the same live stack (useful for seeing what changed since you started tuning)
- **Current YAML file** — compares live node values against the YAML file loaded via File > Load Config; highlights params that have drifted from the file
- **Browse…** — opens a file dialog so you can pick any `nav2_params.yaml` on disk as the reference

### Loading a snapshot and reading the diff

1. Select the source from the dropdown and click **Load**
2. The diff table populates with one row per parameter that differs between live and the reference
3. Each row shows the parameter name, node, the live value, and the reference value
4. Rows are colour-coded by diff kind: `added` (present in live, absent in reference), `removed` (present in reference, absent in live), and `changed` (present in both, different values)

### Selective apply

You can push reference values back to the live stack selectively:

1. Check the rows you want to apply in the leftmost column (or use **Check All** to select everything enabled)
2. Click **Apply Selected**
3. nav2_config calls `set_parameters` for each checked row, using the reference value as the target

**Apply Selected** is only enabled when at least one checkbox is checked.

### Limitations

- **Param-level diffs only.** The Compare tab diffs individual parameter values — it does not do a file-level text diff or preserve YAML comments from the reference.
- **Removed params are shown but not actionable.** Parameters present in the reference but absent from the live node are listed as `removed`; they cannot be applied because the live node does not have that parameter declared.
- **No apply for array params with structural differences.** If a live array and the reference array have different lengths, the row is shown as `changed` and can be applied, but the result depends on whether the live node accepts the new array shape.
