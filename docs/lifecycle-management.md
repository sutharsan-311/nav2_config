# Lifecycle Management

Nav2 uses ROS2 managed nodes, which means every navigation node goes through a defined state machine before it starts running. Understanding this matters because nav2_config can trigger those transitions — and triggering them wrong can crash your stack.

## How lifecycle_manager Works

Nav2 nodes don't start themselves. `lifecycle_manager` starts them in sequence, monitors them, and restarts the stack if something goes wrong. The normal lifecycle flow:

```
Unconfigured → [configure] → Inactive → [activate] → Active
                                         ↓
                              [deactivate] → Inactive → [cleanup] → Unconfigured
```

When you use the stack controls in nav2_config, all transitions go through `lifecycle_manager`. It handles ordering (e.g. costmaps must be active before the controller can activate) and failure recovery.

## Stack Controls

The top of the node panel has three buttons:

**Restart Stack**

Full cycle: deactivate all → cleanup all → configure all → activate all.

Use this when you've changed a parameter that can't take effect at runtime — like changing a plugin type, or switching the global planner. The restart is managed and ordered by `lifecycle_manager`, so nodes come back up in the right order.

Restart takes 5-15 seconds depending on your hardware and the number of nodes. The robot will not move during this time.

**Pause Stack**

Deactivates all nodes without cleanup. Nav2 nodes transition to `Inactive` state. The robot stops, but nodes retain their configuration — no re-configure needed to resume.

Use this when you need to stop navigation temporarily (e.g. reposition the robot manually) without the full overhead of a restart.

**Resume Stack**

Reactivates a paused stack. Nodes transition from `Inactive` back to `Active`.

This only works after a Pause. If nodes were cleaned up or crashed, Resume will fail — use Restart instead.

## Expert Mode

Expert Mode is a toolbar toggle. When enabled, the node panel shows direct transition buttons for each node: Configure, Activate, Deactivate, Cleanup.

These bypass `lifecycle_manager` entirely. You're calling the lifecycle service on the node directly.

**When to use it:** A node is stuck in a bad state and lifecycle_manager won't help. For example, a node is in `Inactive` but lifecycle_manager thinks it's `Active` and won't transition it. Direct transitions let you manually move the node to a known state.

**The risk:** Nav2 nodes have ordering dependencies. Activating the controller before the costmaps are active will fail. Cleaning up a node while lifecycle_manager is still managing it can cause lifecycle_manager to enter a fault state and trigger an emergency shutdown.

The UI makes this obvious — Expert Mode displays a red warning banner.

## The Finalized State

ROS2 has a `Finalized` state that's different from `Unconfigured`. A node enters `Finalized` when:
- It crashed
- It received an unrecoverable error during a transition
- It was explicitly finalized

**You cannot recover a finalized node without restarting the process.** nav2_config cannot help here — no lifecycle transition can bring a `Finalized` node back. You need to kill and relaunch the Nav2 process.

If a node shows as `Finalized` in the nav2_config status panel, the fix is:
```bash
# Kill and relaunch nav2 (whatever your bringup launch file is)
ros2 launch nav2_bringup navigation_launch.py
```

## Multi-Manager Setups

Some Nav2 configurations run two lifecycle managers: one for navigation (controller, planner, bt_navigator, etc.) and one for localization (amcl, map_server). This is common when you want localization to stay running while restarting the navigation stack.

nav2_config's stack controls talk to all discovered lifecycle managers. Restart Stack restarts all managed nodes across all managers. If you only want to restart navigation without touching localization, use Expert Mode to target specific nodes — but be careful about ordering.
