#!/usr/bin/env python3
"""Offline tests for builders.lib.primus_output_network (no TouchDesigner)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builders.lib.primus_output_network import (  # noqa: E402
    default_sampling_rows,
    normalize_profile,
    safe_name,
)


def test_safe_name():
    assert safe_name("A15") == "A15"
    assert safe_name("primus-a!") == "primus_a_"
    assert safe_name("") == "device"


def test_normalize_profile_defaults():
    row = normalize_profile({})
    assert row["ip"] == "192.168.8.166"
    assert row["bind_ip"] == "192.168.8.199"
    assert row["recv_mode"] == "split"
    assert row["a0_type"] == "small_grid"
    assert row["a1_type"] == "long_strip"
    assert row["active"] == "1"
    assert int(row["a0_virtual"]) == 1
    assert int(row["a1_virtual"]) == 72


def test_normalize_clamps_virtual():
    row = normalize_profile(
        {
            "a0_type": "small_grid",
            "a0_virtual": "999",
            "a1_type": "long_strip",
            "a1_virtual": "999",
            "recv_mode": "bogus",
        }
    )
    assert row["recv_mode"] == "split"
    assert int(row["a0_virtual"]) == 32
    assert int(row["a1_virtual"]) == 72
    assert row["a0_count"] == "32"
    assert row["a1_count"] == "72"


def test_sampling_rows():
    rows = dict(default_sampling_rows(0))
    assert "brightness" in rows
    assert rows["a0_sample_mode"] == "point"
    assert rows["a1_sample_mode"] == "hline"
    rows_b = dict(default_sampling_rows(1))
    assert float(rows_b["hue_shift"]) > 0


if __name__ == "__main__":
    test_safe_name()
    test_normalize_profile_defaults()
    test_normalize_clamps_virtual()
    test_sampling_rows()
    print("primus_output offline tests: OK")
