# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""FrameDiscovery must list root frames (found by the live sim test)."""

from nav2_config.core.frame_discovery import FrameDiscovery

# tf2's Buffer.all_frames_as_yaml() keys only frames that have a parent, so the
# root (`map`) shows up solely as somebody's `parent`.
TF2_YAML = """
odom:
  parent: 'map'
  broadcaster: 'default_authority'
base_link:
  parent: 'odom'
  broadcaster: 'default_authority'
base_scan:
  parent: 'base_link'
  broadcaster: 'default_authority'
"""


class _FakeBuffer:
    def all_frames_as_yaml(self) -> str:
        return TF2_YAML


def _discovery() -> FrameDiscovery:
    fd = object.__new__(FrameDiscovery)  # skip the real tf2 listener setup
    fd._tf_buffer = _FakeBuffer()
    return fd


def test_root_frame_is_listed():
    assert "map" in _discovery().get_all_frames()


def test_common_frames_put_map_first():
    assert _discovery().get_common_frames()[:3] == ["map", "odom", "base_link"]
