# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

#!/usr/bin/env python3
"""Live integration test: compare nav2_params.json schema against running Nav2 nodes.

Usage:
    cd ~/ros2_ws/src/nav2_config
    python3 test/test_live_params.py

Produces three categories per node:
  MATCHED     — param is in schema AND live on node (value read successfully)
  SCHEMA ONLY — param is in schema but not found on live node (wrong name or optional)
  LIVE ONLY   — param exists on live node but not in schema (we're missing coverage)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parent.parent
SCHEMA_PATH = REPO_ROOT / "nav2_config" / "schema" / "nav2_params.json"

# Import the authoritative node spec registry so this file stays in sync automatically.
sys.path.insert(0, str(REPO_ROOT))
from nav2_config.core.node_discovery import NAV2_NODE_SPECS  # noqa: E402

# Build a root-namespace path → display name mapping from NAV2_NODE_SPECS.
# Self-namespaced nodes (costmaps) use the /<bn>/<bn> path form.
NAV2_NODES: dict[str, str] = {
    (f"/{bn}/{bn}" if spec.self_namespaced else f"/{bn}"): spec.display_name
    for bn, spec in NAV2_NODE_SPECS.items()
}

# Skip these meta-params that every node has — not Nav2-specific, not in schema
_SKIP_PARAM_PREFIXES = (
    "qos_overrides.",
    "/bond_",
    "bond_",
)


# ---------------------------------------------------------------------------
# ROS2 CLI helpers
# ---------------------------------------------------------------------------

def _ros2(args: list[str], timeout: int = 8) -> str | None:
    """Run a ros2 CLI command and return stdout, or None on failure."""
    cmd = ["ros2"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def list_live_params(node_path: str) -> list[str] | None:
    """Return parameter names from a live ROS2 node, or None if unreachable."""
    out = _ros2(["param", "list", node_path])
    if out is None:
        return None
    params = []
    for line in out.splitlines():
        name = line.strip()
        if not name:
            continue
        if any(name.startswith(pfx) for pfx in _SKIP_PARAM_PREFIXES):
            continue
        params.append(name)
    return params


def get_live_value(node_path: str, param_name: str) -> tuple[bool, Any]:
    """Fetch a single parameter value from the live node.

    Retries once after a 1 s delay to handle transient service timeouts
    during rapid sequential parameter reads.

    Returns (success: bool, value: Any).
    """
    for attempt in range(2):
        out = _ros2(["param", "get", node_path, param_name])
        if out is not None:
            # ros2 param get output: "<Type> value is: <value>"
            # e.g. "Double value is: 20.0" or "Boolean value is: True"
            stripped = out.strip()
            if ":" not in stripped:
                return False, stripped
            _, raw_val = stripped.split(":", 1)
            return True, raw_val.strip()
        if attempt == 0:
            time.sleep(1.0)
    return False, None


# ---------------------------------------------------------------------------
# Schema loader
# ---------------------------------------------------------------------------

def load_schema() -> dict[str, dict[str, dict[str, Any]]]:
    """Load nav2_params.json into {bare_node: {ros2_name: entry}}.

    ros2_name defaults to param when not set in the JSON (matches the
    convention in Nav2ParamDef.__post_init__).
    """
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        raw: list[dict[str, Any]] = json.load(f)

    result: dict[str, dict[str, dict[str, Any]]] = {}
    for entry in raw:
        bare_node = entry["node"]
        ros2_name = entry.get("ros2_name") or entry["param"]
        result.setdefault(bare_node, {})[ros2_name] = entry
    return result


# ---------------------------------------------------------------------------
# Per-node comparison
# ---------------------------------------------------------------------------

def _bare_node(node_path: str) -> str:
    """'/local_costmap/local_costmap' -> 'local_costmap'."""
    return node_path.rstrip("/").rsplit("/", 1)[-1]


def compare_node(
    node_path: str,
    display_name: str,
    schema_by_node: dict[str, dict[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Compare live params against schema for one node."""
    bare = _bare_node(node_path)
    schema_params: dict[str, dict[str, Any]] = schema_by_node.get(bare, {})

    live_params = list_live_params(node_path)
    if live_params is None:
        return {
            "node": node_path,
            "display": display_name,
            "reachable": False,
            "matched": [],
            "schema_only": [],
            "live_only": [],
        }

    live_set = set(live_params)
    schema_set = set(schema_params.keys())

    matched_names = sorted(live_set & schema_set)
    schema_only_names = sorted(schema_set - live_set)
    live_only_names = sorted(live_set - schema_set)

    # For each MATCHED param, try to read the value
    matched: list[dict[str, Any]] = []
    for name in matched_names:
        ok, value = get_live_value(node_path, name)
        matched.append({
            "name": name,
            "read_ok": ok,
            "value": value,
            "schema_type": schema_params[name].get("type", "?"),
            "hot_reload": schema_params[name].get("hot_reload", True),
        })

    return {
        "node": node_path,
        "display": display_name,
        "reachable": True,
        "matched": matched,
        "schema_only": schema_only_names,
        "live_only": live_only_names,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_W = 80  # line width for separators

def _sep(char: str = "─") -> str:
    return char * _W


def _color(text: str, code: str) -> str:
    """ANSI colour wrap when stdout is a terminal."""
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _green(t: str) -> str:  return _color(t, "32")
def _yellow(t: str) -> str: return _color(t, "33")
def _red(t: str) -> str:    return _color(t, "31")
def _cyan(t: str) -> str:   return _color(t, "36")
def _bold(t: str) -> str:   return _color(t, "1")


def print_node_report(r: dict[str, Any]) -> None:
    matched = r["matched"]
    schema_only = r["schema_only"]
    live_only = r["live_only"]

    print()
    print(_sep("═"))
    status = _green("● ONLINE") if r["reachable"] else _red("○ OFFLINE")
    print(f"  {_bold(r['display'])}  {r['node']}  {status}")
    print(_sep("─"))

    if not r["reachable"]:
        print("  Node not running — skipping.")
        return

    # ---- MATCHED ----
    read_ok_count = sum(1 for m in matched if m["read_ok"])
    print(f"  {_green('MATCHED')}   {len(matched):3d} params  "
          f"(read OK: {read_ok_count}/{len(matched)})")
    if matched:
        col_w = max(len(m["name"]) for m in matched) + 2
        for m in matched:
            ok_marker = _green("✓") if m["read_ok"] else _red("✗")
            hr_marker = "" if m["hot_reload"] else _yellow(" [restart]")
            val_str = str(m["value"])[:40] if m["value"] is not None else "—"
            print(f"    {ok_marker}  {m['name']:<{col_w}}  "
                  f"{_cyan(m['schema_type']):<8}  {val_str}{hr_marker}")

    # ---- SCHEMA ONLY ----
    print()
    print(f"  {_yellow('SCHEMA ONLY')}  {len(schema_only):3d} params  "
          "(in schema but not on live node)")
    if schema_only:
        for name in schema_only:
            print(f"    - {name}")

    # ---- LIVE ONLY ----
    print()
    print(f"  {_red('LIVE ONLY')}   {len(live_only):3d} params  "
          "(on live node but not in schema)")
    if live_only:
        for name in live_only:
            print(f"    + {name}")


def print_summary(results: list[dict[str, Any]]) -> None:
    """Print the overall summary table."""
    print()
    print(_sep("═"))
    print(_bold("  SUMMARY TABLE"))
    print(_sep("─"))
    hdr = f"  {'Node':<28}  {'Status':<8}  {'Matched':>7}  {'ReadOK':>6}  {'SchOnly':>7}  {'LiveOnly':>8}"
    print(hdr)
    print(_sep("─"))

    total_matched = total_read_ok = total_schema_only = total_live_only = 0

    for r in results:
        if not r["reachable"]:
            status = _red("OFFLINE")
            row = f"  {r['display']:<28}  {status:<18}  {'—':>7}  {'—':>6}  {'—':>7}  {'—':>8}"
        else:
            matched = len(r["matched"])
            read_ok = sum(1 for m in r["matched"] if m["read_ok"])
            schema_only = len(r["schema_only"])
            live_only = len(r["live_only"])

            total_matched += matched
            total_read_ok += read_ok
            total_schema_only += schema_only
            total_live_only += live_only

            read_ok_str = _green(str(read_ok)) if read_ok == matched else _red(str(read_ok))
            status = _green("ONLINE ")

            row = (
                f"  {r['display']:<28}  {status:<18}  "
                f"{matched:>7}  {read_ok_str:>15}  "
                f"{schema_only:>7}  {live_only:>8}"
            )
        print(row)

    print(_sep("─"))
    print(f"  {'TOTAL':<28}  {'':8}  {total_matched:>7}  "
          f"{total_read_ok:>6}  {total_schema_only:>7}  {total_live_only:>8}")
    print(_sep("═"))


# ---------------------------------------------------------------------------
# Set-param roundtrip helpers
# ---------------------------------------------------------------------------

def set_live_value(
    node_path: str,
    param_name: str,
    value_str: str,
    retries: int = 1,
    retry_delay: float = 2.0,
) -> tuple[bool, str]:
    """Set a parameter value via ``ros2 param set``.

    Retries up to *retries* additional times on timeout so that transient
    service saturation does not turn into a hard failure.

    Returns ``(success, message)`` where *message* is the raw CLI output.
    """
    for attempt in range(1 + retries):
        out = _ros2(["param", "set", node_path, param_name, value_str], timeout=12)
        if out is not None:
            stripped = out.strip()
            if stripped:
                return "Set parameter successful" in stripped, stripped
            # ros2 param set exits 0 with empty stdout when the service call
            # times out internally — treat this as a retryable failure.
        if attempt < retries:
            time.sleep(retry_delay)
    return False, "CLI call failed or timed out"


def _parse_cli_value(raw: str, schema_type: str) -> Any:
    """Parse a raw value string from ``ros2 param get`` to a Python native type."""
    s = raw.strip()
    try:
        if schema_type == "bool":
            return s.lower() in ("true", "1", "yes")
        if schema_type == "int":
            return int(float(s))   # float() first handles "10.0" from some nodes
        if schema_type == "double":
            return float(s)
    except (ValueError, TypeError):
        pass
    return s  # fallback: keep as string


def _pick_test_value(
    schema_type: str,
    current_str: str,
    schema_entry: dict[str, Any],
) -> str | None:
    """Choose a test value that is different from *current_str* and within range.

    Returns a string ready for ``ros2 param set``, or ``None`` if no safe
    test value can be determined (type not testable, or range too tight).
    """
    current = _parse_cli_value(current_str, schema_type)
    if current is None:
        return None

    if schema_type == "bool":
        return "false" if current else "true"

    if schema_type in ("int", "double"):
        r = schema_entry.get("range") or {}
        mn: float | None = r.get("min")
        mx: float | None = r.get("max")

        if schema_type == "int":
            for candidate in (int(current) + 1, int(current) - 1):
                if mn is not None and candidate < mn:
                    continue
                if mx is not None and candidate > mx:
                    continue
                return str(candidate)
            return None

        # double — 5% nudge, minimum 0.1 units, bounded by available range
        unconstrained_delta = max(abs(current) * 0.05, 0.1)
        for sign in (1, -1):
            # Cap delta so we stay within range
            if sign == 1 and mx is not None:
                available = mx - current
            elif sign == -1 and mn is not None:
                available = current - mn
            else:
                available = float("inf")
            if available <= 0:
                continue
            delta = min(unconstrained_delta, available * 0.5)
            if delta < 1e-15:
                continue
            candidate = current + sign * delta
            if abs(candidate - current) < 1e-15:
                continue
            if mn is not None and candidate < mn:
                continue
            if mx is not None and candidate > mx:
                continue
            return repr(candidate)
        return None

    # string / string_array / unknown — not safely testable
    return None


def _values_match(verify_str: str, expected_str: str, schema_type: str) -> bool:
    """Return True if *verify_str* (from ``ros2 param get``) matches *expected_str*."""
    v = verify_str.strip()
    e = expected_str.strip()

    if schema_type == "double":
        try:
            return abs(float(v) - float(e)) < 1e-4
        except ValueError:
            return v == e

    if schema_type == "int":
        try:
            return int(float(v)) == int(float(e))
        except ValueError:
            return v == e

    if schema_type == "bool":
        return (v.lower() in ("true", "1")) == (e.lower() in ("true", "1"))

    return v == e


def set_param_roundtrip(
    node_path: str,
    param_name: str,
    schema_type: str,
    schema_entry: dict[str, Any],
) -> dict[str, Any]:
    """GET → SET(test_value) → VERIFY → RESTORE roundtrip for one parameter.

    Decision rules:
    - Failed GET in step 1 → SKIP (no restore attempt needed)
    - SET returns failure → FAIL (restore still attempted via finally)
    - SET returns success but value unchanged → SILENT_REJECT
    - All OK → PASS (RESTORE_FAIL if restore itself fails)

    Returns a dict with keys: node, param, status, detail, original_value, test_value.
    """
    result: dict[str, Any] = {
        "node": node_path,
        "param": param_name,
        "status": "UNKNOWN",
        "detail": "",
        "original_value": None,
        "test_value": None,
    }

    # ── Step 1: read original value ──────────────────────────────────────────
    get_ok, original_str = get_live_value(node_path, param_name)
    if not get_ok:
        result["status"] = "SKIP"
        result["detail"] = "Cannot read original value"
        return result

    result["original_value"] = original_str

    # Normalise original value for restoration.
    # - booleans: ros2 param set wants lowercase "true"/"false"
    # - doubles: ros2 param set rejects scientific notation (e.g. "1e-10")
    #   so format as plain decimal to avoid "Wrong parameter type" errors.
    if schema_type == "bool":
        restore_str = "true" if original_str.strip().lower() in ("true", "1") else "false"
    elif schema_type == "double":
        try:
            fval = float(original_str)
            # Format without scientific notation; strip trailing zeros after "."
            # Strip trailing zeros but keep at least one decimal place so
            # ros2 param set doesn't treat the value as an INTEGER literal.
            # e.g.  2.0 -> "2.0"  (not "2"),  3.14 -> "3.14",  1e-10 -> "0.0000000001"
            s = f"{fval:.15f}".rstrip("0")
            restore_str = s if not s.endswith(".") else s + "0"
        except ValueError:
            restore_str = original_str.strip()
    else:
        restore_str = original_str.strip()

    test_val = _pick_test_value(schema_type, original_str, schema_entry)
    if test_val is None:
        result["status"] = "SKIP"
        result["detail"] = (
            f"No safe test value for type={schema_type!r}, current={original_str!r}"
        )
        return result

    result["test_value"] = test_val

    # ── Steps 2-3: SET + VERIFY, always followed by RESTORE ─────────────────
    try:
        set_ok, set_msg = set_live_value(node_path, param_name, test_val)

        if not set_ok:
            result["status"] = "FAIL"
            result["detail"] = f"SET rejected by node: {set_msg}"
            return result

        # SET claimed success — verify the value actually changed.
        # One retry handles the case where the node is briefly busy in its
        # on_set_parameters_callback and the immediate GET times out.
        verify_ok, verify_str = get_live_value(node_path, param_name)
        if not verify_ok:
            time.sleep(1.0)
            verify_ok, verify_str = get_live_value(node_path, param_name)

        if not verify_ok:
            result["status"] = "FAIL"
            result["detail"] = "SET accepted but cannot re-read value to verify (2 attempts)"
            return result

        if not _values_match(verify_str, test_val, schema_type):
            result["status"] = "SILENT_REJECT"
            result["detail"] = (
                f"SET returned success but value is still {verify_str!r} "
                f"(expected {test_val!r})"
            )
            return result

        result["status"] = "PASS"
        result["detail"] = f"{original_str!r} → {test_val!r} ✓"

    finally:
        # Always restore the original value regardless of what happened above.
        # Retry up to 3× with increasing delays — the service may be briefly
        # saturated from the preceding SET call.
        restore_ok, restore_msg = set_live_value(
            node_path, param_name, restore_str, retries=3, retry_delay=3.0
        )
        if not restore_ok:
            result["detail"] += f" | RESTORE FAILED: {restore_msg}"
            if result["status"] == "PASS":
                result["status"] = "RESTORE_FAIL"

    return result


# ---------------------------------------------------------------------------
# Roundtrip test runner
# ---------------------------------------------------------------------------

_TESTABLE_TYPES: frozenset[str] = frozenset({"double", "int", "bool"})


def run_roundtrip_tests(
    schema_by_node: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Run :func:`set_param_roundtrip` for every hot-reload param on every live node.

    Only tests params that:
    - Exist on the live node
    - Have ``hot_reload: true`` in the schema
    - Have a testable type (double, int, bool)
    """
    all_results: list[dict[str, Any]] = []

    for node_path, display_name in NAV2_NODES.items():
        bare = _bare_node(node_path)
        schema_params = schema_by_node.get(bare, {})

        live_params = list_live_params(node_path)
        if live_params is None:
            continue   # node offline

        live_set = set(live_params)
        print(f"\n  Roundtrip: {display_name} ({node_path})")

        for param_name, entry in sorted(schema_params.items()):
            if param_name not in live_set:
                continue
            if not entry.get("hot_reload", True):
                continue
            schema_type = entry.get("type", "")
            if schema_type not in _TESTABLE_TYPES:
                continue

            res = set_param_roundtrip(node_path, param_name, schema_type, entry)
            all_results.append(res)
            # Brief pause so the node's parameter service isn't saturated by
            # rapid back-to-back requests.
            time.sleep(0.3)

            status = res["status"]
            if status == "PASS":
                marker = _green("PASS")
            elif status == "SKIP":
                marker = _yellow("SKIP")
            elif status == "SILENT_REJECT":
                marker = _red("SILENT_REJECT")
            else:
                marker = _red(status)

            print(f"    {marker:<20}  {param_name:<40}  {res['detail']}")

    return all_results


# ---------------------------------------------------------------------------
# Roundtrip summary
# ---------------------------------------------------------------------------

def print_roundtrip_summary(results: list[dict[str, Any]]) -> None:
    """Print a summary table for the roundtrip test results."""
    counts: Counter[str] = Counter(r["status"] for r in results)

    total   = len(results)
    passed  = counts.get("PASS", 0)
    skipped = counts.get("SKIP", 0)
    failed  = counts.get("FAIL", 0) + counts.get("RESTORE_FAIL", 0)
    silent  = counts.get("SILENT_REJECT", 0)

    print()
    print(_sep("═"))
    print(_bold("  ROUNDTRIP TEST SUMMARY"))
    print(_sep("─"))
    print(f"  Total tested   : {total}")
    print(f"  {_green('PASS')}           : {passed}")
    print(f"  {_yellow('SKIP')}           : {skipped}  (no safe test value or unreadable)")
    print(f"  {_red('FAIL')}           : {failed}")
    print(f"  {_red('SILENT_REJECT')}: {silent}  (SET accepted but value unchanged)")
    print(_sep("─"))

    bad = [r for r in results if r["status"] not in ("PASS", "SKIP")]
    if bad:
        print(_red("\n  FAILURES:"))
        for r in bad:
            print(f"    [{r['status']}]  {r['node']}  {r['param']}")
            print(f"              {r['detail']}")

    non_skip = total - skipped
    if failed == 0 and silent == 0 and non_skip > 0:
        print(_green(f"\n  ✓  All {non_skip} non-skipped roundtrip tests passed.\n"))
    elif non_skip == 0:
        print(_yellow("\n  ⚠  No params were testable (all skipped).\n"))
    else:
        print(_red(f"\n  ✗  {failed + silent} roundtrip test(s) failed — see above.\n"))

    print(_sep("═"))


# ---------------------------------------------------------------------------
# Exit code logic
# ---------------------------------------------------------------------------

def _check_pass(results: list[dict[str, Any]]) -> bool:
    """Return True if all reachable nodes have 100% read success on matched params."""
    for r in results:
        if not r["reachable"]:
            continue
        for m in r["matched"]:
            if not m["read_ok"]:
                return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    # ── Phase 1: Schema vs live comparison ───────────────────────────────────
    print(_bold("\nnav2_config — Live Parameter Verification"))
    print(f"Schema: {SCHEMA_PATH}")
    print(f"Nodes:  {len(NAV2_NODES)}")

    schema_by_node = load_schema()
    results: list[dict[str, Any]] = []

    for node_path, display_name in NAV2_NODES.items():
        print(f"\n  Checking {display_name} ({node_path}) ...", end="", flush=True)
        r = compare_node(node_path, display_name, schema_by_node)
        results.append(r)
        if r["reachable"]:
            n_matched = len(r["matched"])
            n_read_ok = sum(1 for m in r["matched"] if m["read_ok"])
            print(f" matched={n_matched} read_ok={n_read_ok} "
                  f"schema_only={len(r['schema_only'])} "
                  f"live_only={len(r['live_only'])}")
        else:
            print(" OFFLINE")

    for r in results:
        print_node_report(r)

    print_summary(results)

    phase1_ok = _check_pass(results)
    if phase1_ok:
        print(_green("\n  ✓  All matched parameters read successfully.\n"))
    else:
        print(_red("\n  ✗  Some matched parameters could NOT be read — see above.\n"))

    # ── Phase 2: Set / verify / restore roundtrip tests ──────────────────────
    print(_bold("\nnav2_config — Set/Verify/Restore Roundtrip Tests"))
    print("Testing every hot_reload param (double, int, bool) on every live node.")
    print("Each param: read original → set test value → verify → restore original.\n")

    rt_results = run_roundtrip_tests(schema_by_node)
    print_roundtrip_summary(rt_results)

    rt_counts: Counter[str] = Counter(r["status"] for r in rt_results)
    phase2_ok = (
        rt_counts.get("FAIL", 0) == 0
        and rt_counts.get("RESTORE_FAIL", 0) == 0
        and rt_counts.get("SILENT_REJECT", 0) == 0
    )

    return 0 if (phase1_ok and phase2_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
