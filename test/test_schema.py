# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

"""Tests for nav2_params.json schema loading and correctness."""

import json
import os
import re
import sys
from pathlib import Path

import pytest

# Allow importing from the source tree without colcon install
SRC_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SRC_ROOT))

from nav2_config.types.params import Nav2ParamDef, ParamRange, load_schema

SCHEMA_PATH = SRC_ROOT / "nav2_config" / "schema" / "nav2_params.json"
PLUGINS_PATH = SRC_ROOT / "nav2_config" / "schema" / "plugins.json"

VALID_TYPES = {"double", "int", "bool", "string", "string_array", "double_array", "int_array"}
KNOWN_NODES = {
    "controller_server",
    "planner_server",
    "amcl",
    "bt_navigator",
    "local_costmap",
    "global_costmap",
    "smoother_server",
    "velocity_smoother",
    "behavior_server",
    "waypoint_follower",
    "map_server",
    "map_saver",
    "collision_monitor",
    "docking_server",
    "following_server",
    "loopback_simulator",
    "route_server",
    "keepout_costmap_filter_info_server",
    "speed_costmap_filter_info_server",
    "keepout_filter_mask_server",
    "speed_filter_mask_server",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def raw_params() -> list[dict]:
    """Load raw JSON before parsing so we can test the JSON itself."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def parsed_params() -> list[Nav2ParamDef]:
    """Load and parse the schema via the public API."""
    # Override ament lookup to use the source tree during testing
    os.environ.setdefault("_NAV2_CONFIG_TEST", "1")
    return load_schema()


@pytest.fixture(scope="module")
def raw_plugins() -> dict:
    with open(PLUGINS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Schema file structure
# ---------------------------------------------------------------------------


def test_schema_file_exists():
    assert SCHEMA_PATH.exists(), f"nav2_params.json not found at {SCHEMA_PATH}"


def test_schema_is_valid_json(raw_params):
    assert isinstance(raw_params, list), "nav2_params.json must be a JSON array"


def test_schema_minimum_param_count(raw_params):
    count = len(raw_params)
    assert count >= 150, f"Expected >= 150 parameters, found {count}"


def test_plugins_file_exists():
    assert PLUGINS_PATH.exists(), f"plugins.json not found at {PLUGINS_PATH}"


# ---------------------------------------------------------------------------
# Per-entry required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_required_fields_present(entry: dict):
    required = {"node", "param", "type", "default", "description"}
    missing = required - entry.keys()
    assert not missing, f"Missing fields {missing} in entry {entry.get('param')}"


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_type_is_valid(entry: dict):
    assert entry["type"] in VALID_TYPES, (
        f"Param '{entry['param']}' has unknown type '{entry['type']}'. "
        f"Valid types: {VALID_TYPES}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_node_is_known(entry: dict):
    assert entry["node"] in KNOWN_NODES, (
        f"Param '{entry['param']}' references unknown node '{entry['node']}'. "
        f"Known nodes: {KNOWN_NODES}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_param_name_is_valid_ros2_identifier(entry: dict):
    """``param`` (and any explicit ``ros2_name``) must be a well-formed ROS 2
    parameter name: a non-empty string of dot-separated identifier characters
    with no whitespace.

    A ROS 2 parameter name is one or more identifier segments drawn from
    ``[A-Za-z0-9_]`` joined by single dots — it never contains spaces, and
    never has a leading/trailing dot or an empty segment. The effective
    live-lookup key
    is ``ros2_name or param`` (``Nav2ParamDef.__post_init__``), and
    ``param_client.fetch_node_params`` binds schema entries to running values by
    testing that key for membership in the node's reported names
    (``d.ros2_name in existing_names``, param_client.py). A stray leading/trailing
    space or an interior space — the kind of copy-paste slip
    ``test_required_fields_present`` (presence only) and the uniqueness guards
    cannot catch — would silently fail that set membership, so the param would
    never bind and would always render as its schema default. This guards the
    *shape* of the name so every entry stays bindable.
    """
    # Anchored, per-segment pattern: one or more identifier segments
    # ([A-Za-z0-9_]+) joined by single dots, with no leading/trailing dot and
    # no empty segment. A flat character class like ``^[A-Za-z0-9_.]+$`` would
    # also accept malformed names such as ``controller.`` (trailing dot),
    # ``.foo`` (leading dot) or ``a..b`` (empty segment) — none of which is a
    # valid ROS 2 parameter name, and each would fail the same
    # ``ros2_name in existing_names`` set membership in
    # ``param_client.fetch_node_params`` that the whitespace slip does, so the
    # param would never bind to its live value. This narrows the check to the
    # real dotted-identifier grammar.
    name_re = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
    param = entry.get("param")
    assert isinstance(param, str) and param.strip(), (
        f"Param name must be a non-empty string, got {param!r}"
    )
    assert name_re.match(param), (
        f"Param '{param}' is not a valid ROS 2 parameter name "
        f"(expected dot-separated [A-Za-z0-9_] segments, no whitespace, "
        f"no leading/trailing dot, no empty segment)"
    )
    ros2_name = entry.get("ros2_name")
    if ros2_name is not None:
        assert isinstance(ros2_name, str) and name_re.match(ros2_name), (
            f"Param '{param}' has an ros2_name that is not a valid ROS 2 "
            f"parameter name: {ros2_name!r}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_description_is_non_empty(entry: dict):
    assert entry.get("description", "").strip(), (
        f"Param '{entry['param']}' has an empty description"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_hot_reload_is_bool(entry: dict):
    assert "hot_reload" in entry, f"Param '{entry['param']}' missing hot_reload field"
    assert isinstance(entry["hot_reload"], bool), (
        f"Param '{entry['param']}' hot_reload must be bool, got {type(entry['hot_reload'])}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_impact_is_non_empty(entry: dict):
    """Every param must ship a genuine tuning 'impact' note — it is the schema's core value."""
    assert (entry.get("impact") or "").strip(), (
        f"Param '{entry['param']}' has an empty impact note"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_impact_differs_from_description(entry: dict):
    """The tuning ``impact`` note must not merely restate the ``description``.

    ``description`` answers *what the param is*; ``impact`` answers *what happens
    when you change it* — the tuning trade-off that is the whole reason this
    schema exists over the raw Nav2 docs. Both surface in the GUI as separate
    fields, so an entry whose ``impact`` is a verbatim copy of its ``description``
    ships an empty-of-value tuning note that ``test_impact_is_non_empty`` cannot
    catch (a non-blank copy passes that check). Comparison is on the stripped,
    case-folded text so a whitespace/casing-only difference still counts as a
    duplicate. Keep the two fields genuinely distinct.
    """
    description = (entry.get("description") or "").strip().casefold()
    impact = (entry.get("impact") or "").strip().casefold()
    assert impact != description, (
        f"Param '{entry['param']}' has an impact note identical to its "
        f"description; impact must describe the tuning trade-off, not restate "
        f"what the param is"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_prose_fields_end_with_terminal_punctuation(entry: dict):
    """``description`` and ``impact`` must read as complete sentences.

    Both fields render as prose in the GUI details pane, and every entry in the
    schema today ends them with sentence-terminating punctuation. A field that
    stops mid-sentence usually signals a truncated or accidentally clipped note
    (e.g. a trailing clause dropped during editing) — a class of defect that the
    non-empty and differs-from-description guards cannot catch. Accept the common
    terminators plus a closing bracket/quote/percent that legitimately ends a
    clause (e.g. "...within [0, 1].", "...set to 100%").
    """
    terminators = (".", "!", "?", ")", "]", '"', "%")
    for field_name in ("description", "impact"):
        text = (entry.get(field_name) or "").strip()
        if not text:
            continue  # emptiness is caught by the dedicated non-empty guards
        assert text.endswith(terminators), (
            f"Param '{entry['param']}' {field_name} does not end with terminal "
            f"punctuation (looks truncated): ...{text[-40:]!r}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_prose_fields_have_no_surrounding_whitespace(entry: dict):
    """``description`` and ``impact`` must carry no leading/trailing whitespace.

    Both fields render as prose in the GUI details pane, so stray padding prints
    as a blank gap before/after the text. More importantly, the surrounding
    guards all ``.strip()`` the value before inspecting it — ``test_impact_is_non_empty``,
    ``test_impact_differs_from_description`` and
    ``test_prose_fields_end_with_terminal_punctuation`` would each silently accept
    a note like ``"...wider horizon.  "`` whose trailing whitespace hides the real
    end of the sentence (and would let a genuinely truncated note masquerade as
    terminated once the clipped tail happens to be whitespace). This mirrors
    ``test_unit_has_no_surrounding_whitespace`` for the prose fields: require the
    stored text to equal its stripped form so what the schema ships is exactly
    what renders. Emptiness itself is left to the dedicated non-empty guards.
    """
    for field_name in ("description", "impact"):
        text = entry.get(field_name)
        if not isinstance(text, str) or text == "":
            continue
        assert text == text.strip(), (
            f"Param '{entry['param']}' {field_name} has leading/trailing "
            f"whitespace; it renders verbatim in the GUI and would hide the real "
            f"sentence end from the stripping guards: ...{text[-40:]!r}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_plugin_specific_is_bool(entry: dict):
    assert isinstance(entry.get("plugin_specific"), bool), (
        f"Param '{entry['param']}' plugin_specific must be bool, "
        f"got {type(entry.get('plugin_specific')).__name__}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_plugin_field_consistency(entry: dict):
    """plugin_specific and plugin must agree: both set or both unset."""
    if entry.get("plugin_specific"):
        assert entry.get("plugin"), (
            f"Param '{entry['param']}' is plugin_specific but has no plugin name"
        )
    else:
        assert not entry.get("plugin"), (
            f"Param '{entry['param']}' names plugin '{entry.get('plugin')}' "
            f"but plugin_specific is false"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_plugin_name_has_no_surrounding_whitespace(entry: dict):
    """A ``plugin`` name, when present, must carry no leading/trailing whitespace.

    ``param_panel._CategorySection.apply_plugin_filter`` shows a plugin-specific
    row only when ``defn.plugin == plugin`` (param_panel.py) — an *exact* string
    comparison against the currently selected plugin. The selected value comes
    from the live node's reported plugin class, not from this field, so a padded
    schema value like ``"DWB "`` can never equal the trimmed selection ``"DWB"``:
    the row would be silently hidden whenever its own plugin is chosen, i.e. the
    param disappears from exactly the view where it belongs.
    ``test_plugin_field_consistency`` only checks that a plugin name is *truthy*
    when ``plugin_specific`` is set (``" DWB "`` passes), so it never catches the
    padding. This is the ``plugin`` mirror of
    ``test_tags_have_no_surrounding_whitespace`` and
    ``test_unit_has_no_surrounding_whitespace``: store the plugin name trimmed.
    """
    plugin = entry.get("plugin")
    if plugin is None:
        return  # absence is valid; consistency with plugin_specific is guarded elsewhere
    if not isinstance(plugin, str):
        return  # non-string plugin is caught by test_plugin_field_consistency's truthiness
    assert plugin == plugin.strip() and plugin.strip(), (
        f"Param '{entry['param']}' has plugin name {plugin!r} with leading/trailing "
        f"whitespace (or whitespace-only); apply_plugin_filter compares it with "
        f"'==' against the trimmed selected plugin, so any padding silently hides "
        f"the row from its own plugin view — store the trimmed form"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_unit_is_string(entry: dict):
    """unit must always be a string ('' for unitless params, never null/absent).

    Nav2ParamDef declares ``unit: str``; a JSON null slips through
    ``data.get("unit", "")`` as None and violates that contract downstream
    (e.g. param_row passes ``defn.unit`` on as a string).
    """
    assert "unit" in entry, f"Param '{entry['param']}' missing unit field (use \"\" for unitless)"
    assert isinstance(entry["unit"], str), (
        f"Param '{entry['param']}' unit must be a string, got {type(entry['unit']).__name__}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_compound_unit_only_on_array_type(entry: dict):
    """A comma-separated (compound) unit may only appear on an array-typed param.

    A few params take a fixed-length vector whose elements carry different units,
    so the schema encodes them as a per-element, comma-separated string — e.g.
    ``velocity_smoother.max_velocity`` is a ``double_array`` of ``[vx, vy, vtheta]``
    with unit ``"m/s, m/s, rad/s"``. The comma count mirrors the element count. On
    a scalar param a comma in the unit would be meaningless (a scalar has a single
    unit), so it almost certainly signals a typo or a type/unit mismatch. This
    guards that correspondence: if the unit lists multiple comma-separated parts,
    the declared type must be one of the ``*_array`` types.
    """
    unit = entry.get("unit", "")
    if isinstance(unit, str) and "," in unit:
        assert entry["type"] in ARRAY_ELEMENT_TYPE, (
            f"Param '{entry['param']}' has a compound unit {unit!r} but non-array "
            f"type {entry['type']!r}; comma-separated per-element units are only "
            f"valid on array types ({sorted(ARRAY_ELEMENT_TYPE)})"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_bool_param_has_no_unit(entry: dict):
    """A ``bool``-typed param must not carry a physical ``unit``.

    A boolean is a flag — it has no magnitude, so a unit like ``"s"`` or ``"m"``
    on a bool param is meaningless and almost certainly a copy-paste slip from a
    neighbouring numeric entry. The GUI renders the unit as a suffix label beside
    the input (param_row passes ``defn.unit`` through verbatim), so a stray unit
    would print next to a checkbox. ``test_compound_unit_only_on_array_type``
    guards the array side of the type/unit correspondence and
    ``test_unit_is_string`` guards the field's type; this guards the scalar-bool
    side, where *any* non-empty unit is wrong (unlike ``string`` params such as
    ``collision_monitor.points``, whose value legitimately encodes metres). The
    unit must be the empty string for every boolean flag.
    """
    if entry.get("type") != "bool":
        return
    unit = entry.get("unit", "")
    assert isinstance(unit, str) and not unit.strip(), (
        f"Param '{entry['param']}' is type bool but carries unit {unit!r}; a "
        f"boolean flag has no physical unit (use \"\")"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_unit_has_no_surrounding_whitespace(entry: dict):
    """A non-empty ``unit`` must carry no leading/trailing (or whitespace-only) padding.

    ``ParamSlider`` renders ``defn.unit`` verbatim into a QLabel of fixed width
    32px placed immediately after the spinbox (param_slider.py ``_build_ui``:
    ``unit_label = QLabel(unit); unit_label.setFixedWidth(32)``), and that label
    is created only ``if unit`` — so the label's content is the raw string with no
    trimming. A unit like ``" m"`` or ``"m "`` would therefore render misaligned
    inside that narrow fixed-width cell, and a *whitespace-only* unit such as
    ``"  "`` is truthy enough to spawn a blank label yet carries no information.
    The existing unit guards miss both cases: ``test_unit_is_string`` only checks
    the field's type, ``test_compound_unit_only_on_array_type`` only fires when a
    comma is present, and ``test_bool_param_has_no_unit`` only covers bool params
    (its ``not unit.strip()`` check would reject ``"  "`` for a bool but a numeric
    slider param slips through). Requiring ``unit == unit.strip()`` closes both the
    padding and the whitespace-only holes for every type at once. Use ``""`` for a
    unitless param.
    """
    unit = entry.get("unit", "")
    if not isinstance(unit, str) or unit == "":
        return  # type is guarded by test_unit_is_string; "" is the unitless form
    assert unit == unit.strip(), (
        f"Param '{entry['param']}' unit {unit!r} has leading/trailing whitespace "
        f"(or is whitespace-only); it renders verbatim in a fixed-width label, so "
        f"use the trimmed form (or \"\" if unitless)"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_compound_unit_segment_count_matches_array_default(entry: dict):
    """A compound (comma-separated) unit must have one segment per array element.

    ``test_compound_unit_only_on_array_type`` asserts that a comma-bearing unit
    only appears on an ``*_array`` type, and its docstring promises that "the
    comma count mirrors the element count" — but nothing actually enforces that
    correspondence. A compound unit encodes a *per-element* label (e.g.
    ``velocity_smoother.max_velocity`` is ``[vx, vy, vtheta]`` with unit
    ``"m/s, m/s, rad/s"``: three values, three units), so if the unit lists a
    different number of segments than the default vector has elements, one of the
    two is wrong — a dropped element, a stray comma, or a mismatched type/unit
    edit. This closes that gap: when the unit is compound *and* the default is a
    concrete list, the segment count (split on commas) must equal the default's
    length. Scalar-defaulted params (no concrete vector to measure against) are
    left to ``test_compound_unit_only_on_array_type``.
    """
    unit = entry.get("unit", "")
    default = entry.get("default")
    if not (isinstance(unit, str) and "," in unit and isinstance(default, list)):
        return
    segments = unit.split(",")
    assert len(segments) == len(default), (
        f"Param '{entry['param']}' has a compound unit {unit!r} with "
        f"{len(segments)} comma-separated segment(s) but its default vector "
        f"{default} has {len(default)} element(s); a per-element unit must carry "
        f"exactly one label per array element"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_are_non_empty_strings(entry: dict):
    tags = entry.get("tags")
    assert isinstance(tags, list), f"Param '{entry['param']}' tags must be a list"
    for tag in tags:
        assert isinstance(tag, str) and tag.strip(), (
            f"Param '{entry['param']}' has an empty or non-string tag: {tag!r}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_are_non_empty(entry: dict):
    """Every entry must carry at least one tag.

    ``param_row.matches_search`` adds ``any(q in tag.lower() for tag in
    defn.tags)`` to its match test (param_row.py) — tags are a curated,
    cross-cutting search vector (e.g. ``"safety"``, ``"performance"``) that the
    param name/description/category often do not contain. An entry that ships an
    empty ``tags`` list silently loses that recall path, so a user searching by a
    concept keyword would never surface it even though the param is conceptually a
    match. ``test_tags_are_non_empty_strings`` only validates the *elements* of the
    list (an empty list passes its element loop vacuously); this guards the list
    itself so every param stays tag-searchable, mirroring how
    ``test_impact_is_non_empty`` protects the schema's other core-value field.
    """
    tags = entry.get("tags")
    assert isinstance(tags, list) and tags, (
        f"Param '{entry['param']}' must have at least one tag "
        f"(tags feed param_row search); got {tags!r}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_have_no_duplicates(entry: dict):
    """Tags on a single entry must be unique.

    Tags drive search/filtering in the GUI; a repeated tag adds no filtering
    value and reads as a copy-paste slip when authoring an entry. Comparing on
    the stripped, case-folded form also catches near-duplicates like
    ``"Safety"`` vs ``"safety"`` that would otherwise render as two chips.
    """
    tags = entry.get("tags") or []
    normalised = [t.strip().casefold() for t in tags if isinstance(t, str)]
    assert len(normalised) == len(set(normalised)), (
        f"Param '{entry['param']}' has duplicate tags: {tags}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_have_no_surrounding_whitespace(entry: dict):
    """A tag must carry no leading/trailing (or whitespace-only) padding.

    ``test_tags_have_no_duplicates`` normalises every tag with
    ``.strip().casefold()`` before comparing, so the schema already treats
    ``"safety"`` and ``" safety "`` as the *same* tag — i.e. the intended stored
    form is the trimmed one, and a padded variant only escapes the duplicate
    guard when it happens to be the lone spelling of that concept. The element
    guard ``test_tags_are_non_empty_strings`` then lets it through, because
    ``" safety ".strip()`` is still truthy. This closes that gap for the single
    surviving case: require each tag to equal its stripped form so what the schema
    stores is exactly the canonical token the duplicate guard already assumes, and
    a whitespace-only tag (``"  "``) — truthy under ``.strip()``'s truthiness check
    but carrying no searchable text for ``param_row.matches_search``'s
    ``q in tag.lower()`` — is rejected rather than silently shipped. This is the
    tags mirror of ``test_unit_has_no_surrounding_whitespace``,
    ``test_prose_fields_have_no_surrounding_whitespace`` and
    ``test_enum_options_have_no_surrounding_whitespace``; store every tag trimmed.
    """
    tags = entry.get("tags") or []
    for tag in tags:
        if not isinstance(tag, str):
            continue  # element type is guarded by test_tags_are_non_empty_strings
        assert tag == tag.strip() and tag.strip(), (
            f"Param '{entry['param']}' has a tag {tag!r} with leading/trailing "
            f"whitespace (or whitespace-only); tags are normalised by strip() in "
            f"the duplicate guard and searched verbatim, so store the trimmed form"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_tags_are_lowercase(entry: dict):
    """A tag must be stored in its case-folded (lowercase) form.

    ``test_tags_have_no_duplicates`` compares tags on their ``.strip().casefold()``
    form, so the schema's canonical stored spelling of a tag is the case-folded
    one — yet that guard only *fires* when two spellings of the same concept
    coexist on one entry (e.g. ``"MPPI"`` alongside ``"mppi"``). A tag that ships
    as the lone, upper-/mixed-case spelling of its concept (``"MPPI"`` with no
    ``"mppi"`` present) passes the duplicate guard vacuously and the element guard
    ``test_tags_are_non_empty_strings`` (``"MPPI"`` is a truthy string), so it
    slips through. ``param_row.matches_search`` already lowercases every tag for
    matching (``q in tag.lower()``), so a stored capital buys nothing for search
    and only risks two entries tagging the same concept with different casing —
    one ``"MPPI"``, one ``"mppi"`` — which the casefolding duplicate guard would
    *not* flag across entries, fragmenting a would-be shared search vector. This
    requires each tag to already equal its case-folded form so what the schema
    stores is exactly the normalized token the duplicate guard assumes, mirroring
    ``test_category_is_canonical_format``'s lowercase rule for categories. All 296
    distinct tags in the schema already satisfy this.
    """
    tags = entry.get("tags") or []
    for tag in tags:
        if not isinstance(tag, str):
            continue  # element type is guarded by test_tags_are_non_empty_strings
        assert tag == tag.casefold(), (
            f"Param '{entry['param']}' has a tag {tag!r} that is not lowercase; "
            f"store the case-folded form {tag.casefold()!r} (tags are casefolded "
            f"by the duplicate guard and lowercased for search, so a stored "
            f"capital only risks a cross-entry case mismatch)"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_ros2_name_is_non_empty_string_when_present(entry: dict):
    """An explicit ``ros2_name`` must be a non-empty string.

    ``param_client.fetch_node_params`` intersects the schema against the names
    the running node actually reports using ``ros2_name`` — it builds
    ``ros2_names = [d.ros2_name for d in node_defs if d.ros2_name in existing_names]``
    and then looks up each live value by ``d.ros2_name`` (param_client.py). A
    JSON ``null`` slips through ``data.get("ros2_name", data["param"])`` as
    ``None`` (the default only applies when the key is absent), and a non-string
    (e.g. a number) is passed through verbatim; either one fails the
    ``in existing_names`` set membership silently, so the param would never bind
    to its live value and would always render as its schema default. ``from_dict``
    only falls back to ``param`` when the value is falsy (``__post_init__``), so a
    truthy non-string would survive — reject it here. Omit the key entirely to get
    the correct ``param`` fallback.
    """
    if "ros2_name" not in entry:
        return
    value = entry["ros2_name"]
    assert isinstance(value, str) and value.strip(), (
        f"Param '{entry['param']}' ros2_name must be a non-empty string when set, "
        f"got {value!r}; omit the key to fall back to the param name"
    )


# The closed set of follow-up actions understood by the app. Keep in sync with
# the ``post_set_action`` docstring in nav2_config/types/params.py and the
# dispatch in node.py. A typo here (e.g. "restart_stak") would silently be
# treated as "no action", so the value must come from this vocabulary.
VALID_POST_SET_ACTIONS = {
    None,
    "clear_costmaps",
    "load_map",
    "nomotion_update",
    "restart_stack",
    "restart_node",
    "restart_controller",
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_post_set_action_is_valid(entry: dict):
    """post_set_action must be null or one of the known follow-up actions.

    The value is dispatched by string comparison in node.py; an unrecognised
    string is silently ignored, so the change would appear to take effect while
    its required service call / restart notification never fires.
    """
    action = entry.get("post_set_action")
    assert action in VALID_POST_SET_ACTIONS, (
        f"Param '{entry['param']}' has unknown post_set_action {action!r}; "
        f"expected null or one of {sorted(a for a in VALID_POST_SET_ACTIONS if a)}"
    )


# A post_set_action that only takes effect after a restart is logically
# incompatible with a live hot-reload: the value cannot both apply immediately
# and require the owning node/stack/controller to be restarted first.
RESTART_POST_SET_ACTIONS = {"restart_stack", "restart_node", "restart_controller"}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_hot_reload_not_contradicted_by_restart_action(entry: dict):
    """A ``hot_reload: true`` param must not carry a restart ``post_set_action``.

    ``post_set_action`` values ``restart_stack``/``restart_node``/
    ``restart_controller`` all document (types/params.py) that the new value does
    *not* take effect until the owning stack/node/controller is restarted —
    ``restart_stack`` even suppresses the auto-apply and only emits
    ``restart_suggested`` (node.py). ``hot_reload`` asserts the opposite: the
    change applies live. A param claiming both would tell the GUI it reloaded hot
    while the value silently sits inert until a restart, so the two must not
    coexist.
    """
    if entry.get("post_set_action") in RESTART_POST_SET_ACTIONS:
        assert entry.get("hot_reload") is not True, (
            f"Param '{entry['param']}' has post_set_action "
            f"'{entry.get('post_set_action')}' (needs a restart to apply) but is "
            f"marked hot_reload: true; a restart-gated value cannot reload live"
        )


# Node-scoped follow-up actions: ``node._run_post_set_action`` dispatches each of
# these against the *running node's own* service (node.py: ``clear_costmaps(node_name)``,
# ``load_map(map_url, node_name)``, ``nomotion_update(node_name)``), and
# ``restart_controller`` is only meaningful for the controller plugin host. So each
# may only sit on a node that actually exposes the corresponding service:
#   - clear_costmaps  -> the costmap nodes that expose clear_entirely_* services
#   - load_map        -> nav2_map_server instances that expose a load_map service
#     (map_server proper plus the two filter-mask servers, which are MapServer nodes)
#   - nomotion_update -> AMCL's /request_nomotion_update service only
#   - restart_controller -> the controller_server, which hosts the controller plugin
# ``restart_stack``/``restart_node`` are deliberately omitted: they are generic
# (any node/stack can be restarted) and carry no per-node service dependency.
ACTION_ALLOWED_NODES = {
    "clear_costmaps": {"local_costmap", "global_costmap"},
    "load_map": {"map_server", "keepout_filter_mask_server", "speed_filter_mask_server"},
    "nomotion_update": {"amcl"},
    "restart_controller": {"controller_server"},
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_node_scoped_post_set_action_matches_node(entry: dict):
    """A node-scoped ``post_set_action`` must sit on a node that exposes its service.

    ``node._run_post_set_action`` dispatches the follow-up against the *running
    node's own* service, passing the live ``node_name`` straight through:
    ``clear_costmaps(node_name)``, ``load_map(map_url, node_name)`` and
    ``nomotion_update(node_name)`` (node.py). Those services only exist on the
    nodes that host them — the ``clear_entirely_*`` services live on the costmap
    nodes, ``load_map`` on ``nav2_map_server`` instances (``map_server`` and the two
    filter-mask servers, which are MapServer nodes), and ``/request_nomotion_update``
    on AMCL. ``restart_controller`` likewise only makes sense on ``controller_server``,
    the node that reads the controller plugin at configure time. If one of these
    actions were attached to a param on the wrong node, the set would appear to
    succeed while the follow-up fired a service the node cannot answer — a silent
    no-op that ``test_post_set_action_is_valid`` (which only checks the action is a
    known string) cannot catch. This guards the action→node binding so each stays on
    a node that can actually honour it. ``restart_stack``/``restart_node`` are generic
    (no per-node service dependency) and are intentionally not constrained here.
    """
    action = entry.get("post_set_action")
    allowed = ACTION_ALLOWED_NODES.get(action)
    if allowed is None:
        return  # action is None, generic, or validated by test_post_set_action_is_valid
    assert entry["node"] in allowed, (
        f"Param '{entry['param']}' on node '{entry['node']}' has post_set_action "
        f"'{action}', but that action is dispatched against the node's own service "
        f"and is only valid on {sorted(allowed)}; on '{entry['node']}' it would fire "
        f"a service the node does not expose (a silent no-op)"
    )


# ---------------------------------------------------------------------------
# Default value type matching
# ---------------------------------------------------------------------------


TYPE_PYTHON_MAP = {
    "double": float,
    "int": int,
    "bool": bool,
    "string": str,
    "string_array": list,
    "double_array": list,
    "int_array": list,
}

# Expected Python element type for each array param type. bool is deliberately
# excluded from the numeric arrays even though it subclasses int.
ARRAY_ELEMENT_TYPE = {
    "string_array": (str,),
    "double_array": (int, float),
    "int_array": (int,),
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_default_type_matches_declared_type(entry: dict):
    declared = entry["type"]
    default = entry["default"]
    expected_py_type = TYPE_PYTHON_MAP.get(declared)

    if expected_py_type is None:
        return  # Unknown type tested elsewhere

    # JSON numbers: "double" may have an int default (e.g., 20 for 20.0) — accept both
    if declared == "double":
        assert isinstance(default, (int, float)), (
            f"Param '{entry['param']}' declared double but default is {type(default)}"
        )
    else:
        assert isinstance(default, expected_py_type), (
            f"Param '{entry['param']}' declared {declared} but default is {type(default).__name__}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_scalar_default_is_not_bool(entry: dict):
    """A scalar ``int``/``double`` default must not be a JSON boolean.

    ``test_default_type_matches_declared_type`` checks ``isinstance(default, int)``
    for numeric scalars, but ``bool`` subclasses ``int`` so a stray ``true``/``false``
    default slips through — the same trap the array test explicitly guards against
    (see ``test_array_default_elements_match_type``). A bool where a number is
    expected would flow into the slider/numeric set-path as ``0``/``1`` and mis-render
    the param, so reject it here to keep the scalar and array checks symmetric.
    """
    if entry["type"] not in ("int", "double"):
        return
    assert not isinstance(entry["default"], bool), (
        f"Param '{entry['param']}' declared {entry['type']} but default is a bool "
        f"({entry['default']!r}); use a numeric literal"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_array_default_elements_match_type(entry: dict):
    """Array-typed params must default to a list whose elements match the scalar type.

    ``bool`` is rejected for the numeric arrays even though it subclasses ``int``,
    so a stray ``true`` in a ``double_array``/``int_array`` default is caught.
    """
    declared = entry["type"]
    elem_types = ARRAY_ELEMENT_TYPE.get(declared)
    if elem_types is None:
        return
    default = entry["default"]
    assert isinstance(default, list), (
        f"Param '{entry['param']}' declared {declared} but default is "
        f"{type(default).__name__}, not a list"
    )
    numeric = declared in ("double_array", "int_array")
    for i, value in enumerate(default):
        if numeric and isinstance(value, bool):
            raise AssertionError(
                f"Param '{entry['param']}' {declared} default has a bool at index {i}"
            )
        assert isinstance(value, elem_types), (
            f"Param '{entry['param']}' {declared} default has "
            f"{type(value).__name__} at index {i}, expected "
            f"{'/'.join(t.__name__ for t in elem_types)}"
        )


# ---------------------------------------------------------------------------
# Range consistency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_is_object_when_present(entry: dict):
    """A ``range``, when present, must be a JSON object (dict), never a list/scalar.

    ``Nav2ParamDef.from_dict`` builds ``ParamRange`` from ``range.get("min")`` /
    ``range.get("max")`` / ``range.get("options")`` (nav2_config/types/params.py) —
    the ``.get`` calls presuppose a mapping. Nearly every range guard in this suite
    reaches for ``range.get(...)`` too: ``test_range_min_less_than_max`` and
    ``test_numeric_default_within_range`` call it unconditionally, so a ``range``
    that was authored as a JSON array (e.g. ``[0.0, 1.0]`` instead of
    ``{"min": 0.0, "max": 1.0}``) or a bare scalar would raise an opaque
    ``AttributeError: 'list' object has no attribute 'get'`` mid-test rather than a
    clear schema-shape failure — while the guards that *do* defend with
    ``isinstance(raw_range, dict)`` (``test_range_has_only_known_keys``) would
    silently skip it. This asserts the container shape up front so a malformed
    ``range`` surfaces as a legible error pointing at the offending param. A missing
    or null ``range`` is valid (the param simply has no bounds/options) and is left
    to the dedicated guards.
    """
    raw_range = entry.get("range")
    if raw_range is None:
        return  # absence of a range is valid; nothing to constrain
    assert isinstance(raw_range, dict), (
        f"Param '{entry['param']}' range must be a JSON object with min/max/options "
        f"keys, got {type(raw_range).__name__} ({raw_range!r}); the ParamRange "
        f"parser and every range guard call range.get(...), which only works on a "
        f"mapping"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_min_less_than_max(entry: dict):
    raw_range = entry.get("range")
    if not raw_range:
        return
    mn = raw_range.get("min")
    mx = raw_range.get("max")
    if mn is not None and mx is not None:
        assert mn < mx, (
            f"Param '{entry['param']}' has range min ({mn}) >= max ({mx})"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_default_within_range(entry: dict):
    """Default values for numeric params should be within their declared range."""
    raw_range = entry.get("range")
    if not raw_range:
        return
    if entry["type"] not in ("double", "int"):
        return
    mn = raw_range.get("min")
    mx = raw_range.get("max")
    default = entry["default"]
    if mn is not None:
        assert default >= mn, (
            f"Param '{entry['param']}' default {default} < range min {mn}"
        )
    if mx is not None:
        assert default <= mx, (
            f"Param '{entry['param']}' default {default} > range max {mx}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_range_bounds_are_numeric(entry: dict):
    """A numeric range's min/max bounds must themselves be numbers.

    ``ParamRange`` feeds these into the slider widget and into the
    ``min < max`` / default-within-range comparisons above. A stray string
    bound (e.g. ``"0.0"``) would raise a ``TypeError`` at comparison time or
    silently mis-clamp the slider, so bounds must be real numbers. ``bool`` is
    rejected even though it subclasses ``int``.
    """
    raw_range = entry.get("range")
    if not raw_range:
        return
    for key in ("min", "max"):
        value = raw_range.get(key)
        if value is None:
            continue
        assert not isinstance(value, bool) and isinstance(value, (int, float)), (
            f"Param '{entry['param']}' range {key} must be a number, "
            f"got {type(value).__name__} ({value!r})"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_int_range_bounds_are_integers(entry: dict):
    """An ``int``-typed param's ``range.min``/``range.max`` must be whole numbers.

    ``ParamSlider`` builds its integer path from these bounds (param_slider.py):
    with ``is_int=True`` the QSpinBox uses ``setMinimum(int(self._min))`` /
    ``setMaximum(int(self._max))`` — so a fractional bound like ``0.5`` is
    silently truncated to ``0`` and the declared limit is lost. Worse,
    ``_pos_to_value`` returns ``self._min + pos``: a fractional ``min`` makes the
    slider emit non-integer values (``0.5``, ``1.5`` …) for a param the schema
    declares as ``int``, which the integer set-path cannot faithfully represent.
    ``test_numeric_range_bounds_are_numeric`` only checks the bounds are numbers;
    this narrows that for int params so a stray float bound surfaces at test time.
    ``bool`` is rejected even though it subclasses ``int``.
    """
    if entry["type"] != "int":
        return
    raw_range = entry.get("range")
    if not isinstance(raw_range, dict):
        return
    for key in ("min", "max"):
        value = raw_range.get(key)
        if value is None:
            continue
        assert not isinstance(value, bool) and isinstance(value, int), (
            f"Param '{entry['param']}' is type int but range {key} is "
            f"{type(value).__name__} ({value!r}); use a whole-number bound "
            f"(fractional bounds are truncated by the int ParamSlider)"
        )


# The only keys ``ParamRange.from_dict`` reads out of a ``range`` object
# (nav2_config/types/params.py). Any other key in the JSON is silently dropped
# during parsing.
VALID_RANGE_KEYS = {"min", "max", "options"}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_has_only_known_keys(entry: dict):
    """A ``range`` object may only contain the keys ParamRange understands.

    ``Nav2ParamDef.from_dict`` builds ``ParamRange`` from exactly
    ``range.get("min")``, ``range.get("max")`` and ``range.get("options")``
    (nav2_config/types/params.py); any other key is silently ignored. So a
    typo'd bound (e.g. ``"maximum"``, ``"mn"``) or an unsupported concept (e.g.
    ``"step"``) would parse without error while the intended constraint never
    reaches the slider/dropdown — the param would render as if that bound were
    absent. Reject stray keys here so the mistake surfaces at test time.
    """
    raw_range = entry.get("range")
    if not isinstance(raw_range, dict):
        return
    extra = set(raw_range) - VALID_RANGE_KEYS
    assert not extra, (
        f"Param '{entry['param']}' range has unrecognised key(s) {sorted(extra)}; "
        f"only {sorted(VALID_RANGE_KEYS)} are read by ParamRange (others are "
        f"silently dropped during parsing)"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_declares_at_least_one_constraint(entry: dict):
    """A ``range`` object, when present, must declare at least one of min/max/options.

    ``Nav2ParamDef.from_dict`` only builds a ``ParamRange`` when ``raw_range`` is
    truthy (nav2_config/types/params.py: ``if raw_range:``), then reads exactly
    ``min``/``max``/``options`` out of it. A range that carries none of those three
    meaningful keys — either an empty object ``{}`` or one where all three are
    explicitly ``null`` — is pure noise: the empty-object form is falsy and parses
    to ``range=None`` (so the author's intent to bound the param is silently lost),
    while the all-null form constructs a ``ParamRange`` whose every field is ``None``
    and which therefore constrains nothing in the slider/dropdown yet still reads as
    a "has a range" entry. ``test_range_is_object_when_present`` and
    ``test_range_has_only_known_keys`` both accept these shapes, so neither catches
    the mistake. Require a present range to actually say something so a stripped or
    typo'd range (e.g. the bounds were meant to be ``min``/``max`` but got dropped)
    surfaces at test time instead of rendering as an unbounded free-form input.
    """
    raw_range = entry.get("range")
    if raw_range is None:
        return  # absence of a range is valid; nothing to constrain
    if not isinstance(raw_range, dict):
        return  # shape is enforced by test_range_is_object_when_present
    has_constraint = any(
        raw_range.get(key) is not None for key in ("min", "max", "options")
    )
    assert has_constraint, (
        f"Param '{entry['param']}' declares a range object with no meaningful "
        f"min/max/options ({raw_range!r}); either give it a real bound/options list "
        f"or drop the range entirely (an empty or all-null range constrains nothing "
        f"and is silently discarded or ignored by ParamRange)"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_numeric_range_bounds_only_on_scalar_numeric_type(entry: dict):
    """A numeric ``range.min``/``range.max`` may only appear on scalar ``double``/``int`` params.

    ``param_row._make_input_widget`` only builds a ``ParamSlider`` when
    ``defn.type in ('double', 'int')`` *and* both ``range.min`` and ``range.max``
    are set (param_row.py). For any other type — ``bool``, ``string``, or the
    array types (which have no slider path) — the min/max bounds are silently
    ignored and the param falls through to a free-form ``ParamInput`` text box,
    so the declared range never constrains the value the user can enter. This is
    the numeric mirror of ``test_enum_options_only_on_string_type``: keep bounds
    on the types that can actually honour them.
    """
    raw_range = entry.get("range") or {}
    if raw_range.get("min") is None and raw_range.get("max") is None:
        return
    assert entry["type"] in ("double", "int"), (
        f"Param '{entry['param']}' is type '{entry['type']}' but defines a numeric "
        f"range.min/range.max; slider bounds are only honoured on scalar double/int "
        f"params (other types render as a free-form ParamInput that ignores the range)"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_valid_and_contain_default(entry: dict):
    """Discrete ``range.options`` must be a non-empty list of non-empty strings,
    and a string default must be one of those options.

    ``param_select.ParamSelect`` populates a QComboBox from ``range.options``;
    if the schema default is absent from that list the widget opens on a value
    the dropdown cannot represent, so the two must stay in sync.
    """
    raw_range = entry.get("range")
    if not raw_range or "options" not in raw_range:
        return
    options = raw_range["options"]
    assert isinstance(options, list) and options, (
        f"Param '{entry['param']}' range.options must be a non-empty list"
    )
    for opt in options:
        assert isinstance(opt, str) and opt.strip(), (
            f"Param '{entry['param']}' has an empty or non-string option: {opt!r}"
        )
    default = entry.get("default")
    if isinstance(default, str):
        assert default in options, (
            f"Param '{entry['param']}' default {default!r} is not among its "
            f"range.options {options}"
        )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_have_no_duplicates(entry: dict):
    """``range.options`` must not repeat a value.

    ``param_select.ParamSelect`` adds every option to its QComboBox verbatim, so
    a duplicated entry produces two identical rows in the dropdown. Beyond the
    cosmetic clutter, selecting "the" value becomes ambiguous and index-based
    logic can land on the wrong row, so the discrete choices must be distinct.
    This is the enum mirror of ``test_tags_have_no_duplicates``.
    """
    raw_range = entry.get("range")
    if not raw_range or not isinstance(raw_range.get("options"), list):
        return
    options = raw_range["options"]
    duplicates = sorted({opt for opt in options if options.count(opt) > 1})
    assert not duplicates, (
        f"Param '{entry['param']}' range.options contains duplicate value(s) "
        f"{duplicates}; each discrete choice must appear once"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_only_on_string_type(entry: dict):
    """``range.options`` may only appear on ``string``-typed params.

    ``param_row._make_input_widget`` dispatches on options *before* the numeric
    slider branch: any param carrying ``range.options`` becomes a ``ParamSelect``
    dropdown (param_row.py), and ``ParamSelect`` emits/returns the raw option
    *string* (its ``value_changed`` signal is typed ``str`` and ``get_value``
    returns ``currentText()``). If a ``double``/``int``/``bool`` param were given
    options it would silently render as a string dropdown whose selections the
    numeric/bool set-path cannot faithfully convert, so options must stay on
    string params only.
    """
    raw_range = entry.get("range")
    if not raw_range or raw_range.get("options") is None:
        return
    assert entry["type"] == "string", (
        f"Param '{entry['param']}' is type '{entry['type']}' but defines "
        f"range.options; discrete options are only supported on string params "
        f"(they render as a string ParamSelect dropdown)"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_range_options_and_bounds_are_mutually_exclusive(entry: dict):
    """A ``range`` must not carry both ``options`` and a numeric ``min``/``max``.

    ``param_row._make_input_widget`` tests ``defn.range.options`` *before* the
    numeric slider branch (param_row.py): the first ``if`` builds a ``ParamSelect``
    dropdown and returns, so the ``min``/``max`` slider branch below it is never
    reached. An entry that declares both would therefore render as a dropdown and
    silently discard its declared bounds — the two are alternative widget
    representations, never combined. Reject the overlap here so the intent (enum
    *or* slider) is unambiguous at authoring time. This is the range-object mirror
    of the type-guard tests ``test_enum_options_only_on_string_type`` and
    ``test_numeric_range_bounds_only_on_scalar_numeric_type``.
    """
    raw_range = entry.get("range")
    if not isinstance(raw_range, dict):
        return
    if raw_range.get("options") is None:
        return
    has_bound = raw_range.get("min") is not None or raw_range.get("max") is not None
    assert not has_bound, (
        f"Param '{entry['param']}' range defines both options and min/max; a param "
        f"is rendered as either a ParamSelect dropdown (options) or a ParamSlider "
        f"(min/max), never both — the options branch wins and the bounds are dropped"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_enum_options_have_no_surrounding_whitespace(entry: dict):
    """A ``range.options`` value must carry no leading/trailing whitespace.

    ``param_select.ParamSelect`` adds each option verbatim to its QComboBox
    (``addItems(options)``) and ``get_value`` returns ``currentText()`` unchanged,
    so a padded option like ``" GridBased"`` would both render misaligned in the
    dropdown and be written back to the live param with its padding intact. It is
    also matched by equality against the schema ``default`` in
    ``test_enum_options_valid_and_contain_default``: a default stored trimmed but
    an option stored padded (or vice versa) would silently fail the
    default-in-options contract. ``test_enum_options_valid_and_contain_default``
    only checks each option is non-empty (``opt.strip()`` is truthy for ``" x "``),
    so padding slips through it. This is the enum-option mirror of
    ``test_unit_has_no_surrounding_whitespace`` and
    ``test_prose_fields_have_no_surrounding_whitespace``; store every option in its
    trimmed form.
    """
    raw_range = entry.get("range")
    if not isinstance(raw_range, dict) or not isinstance(raw_range.get("options"), list):
        return
    for opt in raw_range["options"]:
        if not isinstance(opt, str):
            continue  # type is guarded by test_enum_options_valid_and_contain_default
        assert opt == opt.strip(), (
            f"Param '{entry['param']}' range option {opt!r} has leading/trailing "
            f"whitespace; options render verbatim in the ParamSelect dropdown and "
            f"are matched by equality to the default, so store the trimmed form"
        )


# ---------------------------------------------------------------------------
# Parsed dataclass tests
# ---------------------------------------------------------------------------


def test_load_schema_returns_list(parsed_params):
    assert isinstance(parsed_params, list)
    assert len(parsed_params) > 0


def test_load_schema_returns_nav2paramdef(parsed_params):
    for p in parsed_params:
        assert isinstance(p, Nav2ParamDef), f"Expected Nav2ParamDef, got {type(p)}"


def test_parsed_param_range_type(parsed_params):
    for p in parsed_params:
        if p.range is not None:
            assert isinstance(p.range, ParamRange), (
                f"Param '{p.param}' range should be ParamRange, got {type(p.range)}"
            )


def test_parsed_param_tags_are_list(parsed_params):
    for p in parsed_params:
        assert isinstance(p.tags, list), f"Param '{p.param}' tags must be a list"


def test_all_nodes_covered(parsed_params):
    """Every node in ``KNOWN_NODES`` must have at least one parameter.

    ``KNOWN_NODES`` is the closed set of Nav2 lifecycle nodes the schema claims
    to cover (``test_node_is_known`` also rejects any entry whose ``node`` is not
    in it). This guards the other direction: that none of those nodes is left
    with *zero* parameters — a node that silently dropped out of the schema would
    render as an empty section in the GUI. The expected count is ``len(KNOWN_NODES)``
    rather than a hardcoded number so adding a node to the set cannot leave this
    docstring stale.
    """
    covered = {p.node for p in parsed_params}
    missing = KNOWN_NODES - covered
    assert not missing, f"These Nav2 nodes have no parameters in the schema: {missing}"


def test_node_param_uniqueness(parsed_params):
    """Each (node, param) pair must be unique."""
    seen: set[tuple[str, str]] = set()
    for p in parsed_params:
        key = (p.node, p.param)
        assert key not in seen, f"Duplicate (node, param): {key}"
        seen.add(key)


def test_effective_ros2_name_unique_per_node(parsed_params):
    """Each node's effective ``ros2_name`` (explicit ``ros2_name`` or the ``param``
    fallback) must be unique.

    ``param_client.fetch_node_params`` binds schema entries to live values by
    ``ros2_name``: it builds ``ros2_names = [d.ros2_name for d in node_defs if
    d.ros2_name in existing_names]`` and then keys the fetched values by that same
    ``ros2_name`` (param_client.py). If two entries under one node resolve to the
    same ``ros2_name`` — e.g. one param sets an explicit ``ros2_name`` that equals
    another param's bare name — both rows would read back the *same* live value and
    a set/undo on one would silently target the other. ``test_node_param_uniqueness``
    only guards the display-side ``(node, param)`` key, so the ROS-facing name needs
    its own check. ``Nav2ParamDef.__post_init__`` already falls back to ``param``
    when ``ros2_name`` is falsy, so ``p.ros2_name`` here is the effective name.
    """
    seen: dict[tuple[str, str], str] = {}
    for p in parsed_params:
        key = (p.node, p.ros2_name)
        assert key not in seen, (
            f"Node '{p.node}' has two params resolving to the same live "
            f"ros2_name '{p.ros2_name}': '{seen[key]}' and '{p.param}'; "
            f"they would bind to the same value on the running node"
        )
        seen[key] = p.param


# ---------------------------------------------------------------------------
# Category taxonomy consistency
# ---------------------------------------------------------------------------


# Near-duplicate category spellings that fragment the GUI grouping: the param
# panel builds one collapsible section per distinct ``category`` string
# (param_panel.py groups by ``definition.category``), so a singular/plural or
# noun/gerund split of the same concept renders as two separate sections. Map
# each known alias to its canonical form and forbid the alias from reappearing.
CATEGORY_ALIASES = {
    "sensors": "sensor",
    "filtering": "filter",
    "debugging": "debug",
}


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_category_is_non_empty_string(entry: dict):
    """Every param must carry a non-empty string ``category``.

    ``param_panel`` groups rows by ``definition.category`` (param_panel.py builds
    one ``_CategorySection`` per distinct value) and the section header renders it
    via ``category.replace("_", " ").title()``. A ``None`` category would raise
    ``AttributeError`` on that ``.replace`` call, and an empty string would produce
    a blank, unlabelled section. ``Nav2ParamDef`` also declares ``category: str``,
    so the raw JSON must honour that contract rather than relying on the
    ``data.get("category", "general")`` fallback in ``load_schema``.
    """
    category = entry.get("category")
    assert isinstance(category, str) and category.strip(), (
        f"Param '{entry['param']}' must have a non-empty string category, "
        f"got {category!r}"
    )


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_category_uses_canonical_spelling(entry: dict):
    """Categories must use the canonical spelling, not a known duplicate alias.

    Two spellings of the same concept (e.g. 'sensor' and 'sensors') split the
    parameter panel into two sections for what is logically one group.
    """
    category = entry.get("category")
    assert category not in CATEGORY_ALIASES, (
        f"Param '{entry['param']}' uses non-canonical category '{category}'; "
        f"use '{CATEGORY_ALIASES.get(category)}' instead"
    )


# Canonical category form: lowercase, words joined by single underscores
# (e.g. ``critic_weights``, ``goal_tolerance``). Every one of the schema's
# existing categories already matches this.
_CATEGORY_FORMAT = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)*")


@pytest.mark.parametrize("entry", [pytest.param(e, id=f"{e.get('node','?')}.{e.get('param','?')}") for e in json.loads(SCHEMA_PATH.read_text())])
def test_category_is_canonical_format(entry: dict):
    """A ``category`` must be lowercase ``snake_case`` (no spaces, no capitals).

    ``param_panel`` groups rows by the *raw* ``definition.category`` string
    (param_panel.py: ``categories.setdefault(pv.definition.category, [])``) but
    the section header is rendered through ``category.replace("_", " ").title()``
    (``_CategorySection._update_header``). So two categories that differ only in
    case or in whitespace-vs-underscore — e.g. ``"Safety"`` vs ``"safety"``, or
    ``"critic weights"`` vs ``"critic_weights"`` — form two *separate*
    collapsible sections yet collapse to the *same* visible header
    (``"Safety"``, ``"Critic Weights"``), so the panel shows what looks like one
    group duplicated. ``test_category_uses_canonical_spelling`` only guards a
    hand-listed set of singular/plural aliases; this guards the textual form
    itself so a stray capital or space can never silently fragment a group.
    """
    category = entry.get("category")
    if not isinstance(category, str):
        return  # non-string categories are caught by test_category_is_non_empty_string
    assert _CATEGORY_FORMAT.fullmatch(category), (
        f"Param '{entry['param']}' category {category!r} is not canonical "
        f"lowercase snake_case; use e.g. 'critic_weights' (a stray capital or "
        f"space fragments the param panel's grouping vs an otherwise-identical "
        f"category)"
    )


# ---------------------------------------------------------------------------
# Plugins JSON structure
# ---------------------------------------------------------------------------


def test_plugins_json_top_level_keys(raw_plugins):
    expected_keys = {"planners", "controllers", "costmap_layers", "recovery_behaviors", "smoothers"}
    assert set(raw_plugins.keys()) == expected_keys, (
        f"plugins.json top-level keys mismatch. Got: {set(raw_plugins.keys())}"
    )


def test_plugins_planner_count(raw_plugins):
    assert len(raw_plugins["planners"]) >= 4, "Expected at least 4 global planners"


def test_plugins_controller_count(raw_plugins):
    assert len(raw_plugins["controllers"]) >= 3, "Expected at least 3 controllers"


def test_plugins_layer_count(raw_plugins):
    assert len(raw_plugins["costmap_layers"]) >= 4, "Expected at least 4 costmap layers"


@pytest.mark.parametrize("category", ["planners", "controllers", "costmap_layers", "recovery_behaviors", "smoothers"])
def test_plugin_entries_have_required_fields(raw_plugins, category):
    required = {"name", "plugin_class", "category", "description", "when_to_use"}
    for plugin in raw_plugins[category]:
        missing = required - plugin.keys()
        assert not missing, (
            f"Plugin '{plugin.get('name', '?')}' in {category} missing fields: {missing}"
        )


def test_plugin_classes_are_non_empty(raw_plugins):
    for category, plugins in raw_plugins.items():
        for plugin in plugins:
            assert plugin["plugin_class"].strip(), (
                f"Plugin '{plugin.get('name')}' has empty plugin_class"
            )
