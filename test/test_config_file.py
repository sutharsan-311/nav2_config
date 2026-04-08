# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for ConfigFile — covers round-trip YAML preservation."""

import tempfile
from pathlib import Path

import pytest

from nav2_config.core.config_file import ConfigFile


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ROUND_TRIP_YAML = """\
# Top-level comment preserved by ruamel
controller_server:
  ros__parameters:
    # Frequency comment
    controller_frequency: 20.0

    use_realtime_priority: True

    costmap_topics: [/local_costmap/costmap, /global_costmap/costmap]

    plugin_names: ["FollowPath"]
"""


@pytest.fixture()
def config_file(tmp_path: Path) -> ConfigFile:
    """Write ROUND_TRIP_YAML to a temp file and return a loaded ConfigFile."""
    p = tmp_path / 'nav2_params.yaml'
    p.write_text(ROUND_TRIP_YAML, encoding='utf-8')
    cf = ConfigFile(str(p))
    cf.load()
    return cf


# ---------------------------------------------------------------------------
# Round-trip preservation tests
# ---------------------------------------------------------------------------

class TestRoundTripPreservation:
    """ruamel.yaml must preserve structure that PyYAML discards on dump."""

    def test_comments_preserved(self, config_file: ConfigFile) -> None:
        """Comments present in the original YAML survive a load → set → dump cycle."""
        config_file.set_value('/controller_server', 'controller_frequency', 15.0)
        result = config_file.to_yaml_string()
        assert '# Top-level comment preserved by ruamel' in result
        assert '# Frequency comment' in result

    def test_inline_arrays_stay_inline(self, config_file: ConfigFile) -> None:
        """Flow-style (inline) sequences are not exploded into block style."""
        config_file.set_value('/controller_server', 'controller_frequency', 15.0)
        result = config_file.to_yaml_string()
        # Both inline lists must remain on a single line
        assert '[/local_costmap/costmap' in result
        assert '["FollowPath"]' in result

    def test_blank_lines_preserved(self, config_file: ConfigFile) -> None:
        """Blank lines between parameters are kept."""
        config_file.set_value('/controller_server', 'controller_frequency', 15.0)
        result = config_file.to_yaml_string()
        # There must be at least one blank line inside ros__parameters
        assert '\n\n' in result

    def test_bool_value_preserved(self, config_file: ConfigFile) -> None:
        """Boolean values survive the round-trip as Python True/False.

        ruamel.yaml 0.19+ serialises YAML booleans as canonical 'true'/'false'
        (YAML 1.2), so we assert value semantics rather than casing.
        """
        config_file.set_value('/controller_server', 'controller_frequency', 15.0)
        # Value must still read back as Python True
        val = config_file.get_value('/controller_server', 'use_realtime_priority')
        assert val is True
        # And the serialised form is a valid YAML boolean (either casing)
        result = config_file.to_yaml_string()
        assert 'true' in result.lower()

    def test_set_value_takes_effect(self, config_file: ConfigFile) -> None:
        """The modified value actually appears in the serialised output."""
        config_file.set_value('/controller_server', 'controller_frequency', 99.5)
        result = config_file.to_yaml_string()
        assert '99.5' in result


# ---------------------------------------------------------------------------
# Basic load / save tests (non-round-trip)
# ---------------------------------------------------------------------------

class TestLoadSave:
    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        cf = ConfigFile(str(tmp_path / 'missing.yaml'))
        with pytest.raises(FileNotFoundError):
            cf.load()

    def test_load_invalid_yaml_raises(self, tmp_path: Path) -> None:
        bad = tmp_path / 'bad.yaml'
        bad.write_text(': : :\n  bad: [unclosed', encoding='utf-8')
        cf = ConfigFile(str(bad))
        with pytest.raises(ValueError, match='Failed to parse YAML'):
            cf.load()

    def test_get_set_value_roundtrip(self, config_file: ConfigFile) -> None:
        config_file.set_value('/controller_server', 'controller_frequency', 42.0)
        assert config_file.get_value('/controller_server', 'controller_frequency') == 42.0

    def test_is_dirty_after_set(self, config_file: ConfigFile) -> None:
        assert not config_file.is_dirty
        config_file.set_value('/controller_server', 'controller_frequency', 1.0)
        assert config_file.is_dirty

    def test_save_creates_backup(self, config_file: ConfigFile, tmp_path: Path) -> None:
        config_file.set_value('/controller_server', 'controller_frequency', 5.0)
        config_file.save()
        assert (tmp_path / 'nav2_params.yaml.bak').exists()

    def test_get_node_names(self, config_file: ConfigFile) -> None:
        assert '/controller_server' in config_file.get_node_names()

    def test_get_all_params_for_node(self, config_file: ConfigFile) -> None:
        params = config_file.get_all_params_for_node('/controller_server')
        assert 'controller_frequency' in params

    def test_get_modified_params(self, config_file: ConfigFile) -> None:
        config_file.set_value('/controller_server', 'controller_frequency', 7.0)
        modified = config_file.get_modified_params()
        names = [p for _, p, _ in modified]
        assert 'controller_frequency' in names
