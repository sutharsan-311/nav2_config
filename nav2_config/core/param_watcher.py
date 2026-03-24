"""ParamWatcher — detects externally-changed parameters by snapshot diffing."""

from __future__ import annotations

from nav2_config.types.params import ParamValue


class ParamWatcher:
    """Detects externally-changed parameters by comparing against a baseline.

    The baseline is set after each full GUI-initiated fetch.  The watcher is
    then polled on a 2-second timer; it compares the fresh ROS2 values against
    the baseline and reports any parameters whose values differ.

    This distinguishes changes made by *this GUI* (which update the baseline
    immediately after the fetch) from changes made by *other tools* (which
    only show up on the next poll).
    """

    def __init__(self) -> None:
        self._watched_node: str | None = None
        self._baseline: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Watch management
    # ------------------------------------------------------------------

    def watch(self, node_name: str) -> None:
        """Start watching *node_name*.

        Clears the baseline so the first poll establishes a new snapshot
        without reporting false positives.

        Args:
            node_name: Full ROS2 node path, e.g. ``"/controller_server"``.
        """
        self._watched_node = node_name
        self._baseline = {}

    def unwatch(self) -> None:
        """Stop watching and clear all internal state."""
        self._watched_node = None
        self._baseline = {}

    @property
    def watched_node(self) -> str | None:
        """The node currently being watched, or None if not watching."""
        return self._watched_node

    # ------------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------------

    def set_baseline(self, params: list[ParamValue]) -> None:
        """Record the current values as the new baseline.

        Call this immediately after a GUI-triggered fetch so the watcher
        won't report these values as "external changes" on the next poll.

        Args:
            params: Fresh parameter list just received from ROS2.
        """
        self._baseline = {pv.definition.param: pv.live_value for pv in params}

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def diff(self, fresh_params: list[ParamValue]) -> list[tuple[str, object]]:
        """Compare *fresh_params* against the baseline.

        Returns a list of ``(param_name, new_value)`` pairs for params whose
        values differ from the baseline.  The baseline is then updated so
        subsequent polls use the latest observed values.

        On the first call (empty baseline), the method just records the
        snapshot and returns an empty list — grace period to avoid spurious
        alerts on startup.

        Args:
            fresh_params: Parameters just fetched from the ROS2 node.

        Returns:
            ``[(name, new_value), ...]`` for externally-changed params.
        """
        if not self._baseline:
            self._baseline = {pv.definition.param: pv.live_value for pv in fresh_params}
            return []

        changed: list[tuple[str, object]] = []
        for pv in fresh_params:
            name = pv.definition.param
            new_val = pv.live_value
            old_val = self._baseline.get(name)
            if old_val is not None and old_val != new_val:
                changed.append((name, new_val))
            self._baseline[name] = new_val

        return changed
