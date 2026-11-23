# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Live check: config file load/save and the Compare tab against a running stack."""

import re
import shutil

import pytest

from sim.helpers import ros2_param_get, select_node, wait_until

pytestmark = pytest.mark.sim

BRINGUP_YAML = "/opt/ros/humble/share/nav2_bringup/params/nav2_params.yaml"
LIVE, LOADED = "Live (current node)", "Loaded YAML (current)"


class _FakeLoadDialog:
    """Stands in for LoadDialog so we can drive MainWindow._load_config_from_dialog."""

    def __init__(self, path: str) -> None:
        self._path = path

    def selected_filepath(self) -> str:
        return self._path

    def connect_to_nodes(self) -> bool:
        return True


def _load_config(app, path: str) -> None:
    app.window._load_config_from_dialog(_FakeLoadDialog(path), 1)
    assert app.window._config_file is not None


def _diff(app, node: str):
    from nav2_config.core.config_diff import diff_snapshots

    left = app.window._build_compare_snapshot(LIVE, node, "left")
    right = app.window._build_compare_snapshot(LOADED, node, "right")
    assert left is not None and right is not None, "could not build compare snapshots"
    return diff_snapshots(left, right)


def _float(text: str) -> float:
    return float(re.search(r"[-\d.]+$", text).group())


@pytest.mark.parametrize("node", ["/controller_server", "/local_costmap/local_costmap"])
def test_bringup_config_matches_live_stack(app, node):
    """The sim was launched from this exact file, so it should differ only by sim overrides."""
    select_node(app, node)
    _load_config(app, BRINGUP_YAML)
    app.window._on_compare_requested(LIVE, LOADED)  # the GUI path must not raise
    from nav2_config.core.config_diff import DiffKind

    changed = [d for d in _diff(app, node) if d.kind is DiffKind.CHANGED]
    unexpected = [(d.param_name, d.left_value, d.right_value) for d in changed
                  if d.param_name != "use_sim_time"]  # the launch file forces this
    assert not unexpected, f"live differs from the file it was launched with: {unexpected}"


def test_compare_apply_selected_diff(app, restore_params, tmp_path):
    from nav2_config.core.config_file import ConfigFile
    from nav2_config.core.config_diff import DiffKind

    node, name = "/controller_server", "FollowPath.max_vel_x"
    restore_params(node, name)
    edited = tmp_path / "edited.yaml"
    shutil.copy(BRINGUP_YAML, edited)
    cfg = ConfigFile(str(edited))
    cfg.load()
    cfg.set_value("controller_server", name, 0.19)
    cfg.save()

    select_node(app, node)
    _load_config(app, str(edited))
    diff = next(d for d in _diff(app, node)
                if d.param_name == name and d.kind is DiffKind.CHANGED)
    assert diff.right_value == pytest.approx(0.19)

    app.window._on_compare_apply([diff])
    wait_until(lambda: _float(ros2_param_get(node, name)) == pytest.approx(0.19), 30,
               what="live value changed by Compare > Apply")


def test_save_roundtrip_preserves_comments(app, restore_params, tmp_path):
    node, name = "/controller_server", "FollowPath.max_vel_x"
    restore_params(node, name)
    path = tmp_path / "params.yaml"
    shutil.copy(BRINGUP_YAML, path)
    original = path.read_text().splitlines()
    assert any(line.strip().startswith("#") for line in original), "fixture has no comments"

    select_node(app, node)
    _load_config(app, str(path))
    app.window._on_param_set_requested(node, name, 0.2)
    wait_until(lambda: _float(ros2_param_get(node, name)) == pytest.approx(0.2), 30,
               what="live set")
    # The config change is staged until ROS2 confirms; wait for the file model to take it.
    wait_until(lambda: app.window._config_file.get_value(node, name) == pytest.approx(0.2), 30,
               what="config value committed after successful set")
    app.window._on_save()

    import yaml  # PyYAML: parse both files to compare meaning, not spelling

    saved_text = path.read_text()
    saved = saved_text.splitlines()
    # What docs/yaml-round-trip.md promises: comments and blank lines survive.
    # (Booleans may be respelled and long inline arrays re-wrapped: cosmetic, ledgered.)
    comments = lambda lines: [l[l.index("#"):] for l in lines if "#" in l]  # noqa: E731
    assert comments(saved) == comments(original)
    assert sum(1 for l in saved if not l.strip()) == sum(1 for l in original if not l.strip())
    # No inline array was converted to a block list (or the reverse).
    block_items = lambda lines: sum(1 for l in lines if l.lstrip().startswith("- "))  # noqa: E731
    assert block_items(saved) == block_items(original)
    # Same meaning as the original, except the one edited value.
    expected = yaml.safe_load("\n".join(original))
    expected["controller_server"]["ros__parameters"]["FollowPath"]["max_vel_x"] = 0.2
    assert yaml.safe_load(saved_text) == expected
