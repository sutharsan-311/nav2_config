# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Saving a config must not re-wrap long inline arrays (found by the sim test)."""

from nav2_config.core.config_file import ConfigFile

LONG = ('      critics: ["RotateToGoal", "Oscillation", "BaseObstacle", "GoalAlign", '
        '"PathAlign", "PathDist", "GoalDist"]')
SRC = f"""controller_server:
  ros__parameters:
    FollowPath:
      max_vel_x: 0.26
{LONG}
"""


def test_long_inline_array_survives_save_unchanged(tmp_path):
    assert len(LONG) > 80   # longer than ruamel's default wrap width
    path = tmp_path / "p.yaml"
    path.write_text(SRC)
    cfg = ConfigFile(str(path))
    cfg.load()
    cfg.set_value("controller_server", "FollowPath.max_vel_x", 0.2)
    cfg.save()
    saved = path.read_text().splitlines()
    assert LONG in saved                           # array line untouched, not wrapped
    assert "      max_vel_x: 0.2" in saved        # and the edit landed
    assert len(saved) == len(SRC.splitlines())
