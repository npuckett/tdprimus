#!/usr/bin/env python3
"""Offline unit checks for packet builders (no TouchDesigner required)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from builders.lib.output_types import validate_combined  # noqa: E402
from builders.lib.packets import (  # noqa: E402
    ARTNET_HEADER,
    OPCODE_ADDRESS,
    OPCODE_DMX,
    OPCODE_OUTPUT_CONFIG,
    OPCODE_POLL,
    OPCODE_RECEIVE_CONFIG,
    OPCODE_VIRTUAL_RESOLUTION,
    build_art_address,
    build_art_dmx,
    build_art_poll,
    build_output_config,
    build_receive_config,
    build_virtual_resolution,
    parse_pv3cap1,
)
from builders.lib.serpentine import serpentine_pixel_order  # noqa: E402


def _opcode(pkt: bytes) -> int:
    return struct.unpack("<H", pkt[8:10])[0]


def test_poll():
    pkt = build_art_poll()
    assert pkt[:8] == ARTNET_HEADER
    assert _opcode(pkt) == OPCODE_POLL
    assert len(pkt) == 14


def test_dmx_even_pad():
    pkt = build_art_dmx(0, bytes([1, 2, 3]))  # odd -> pad
    assert _opcode(pkt) == OPCODE_DMX
    length = struct.unpack(">H", pkt[16:18])[0]
    assert length == 4
    assert pkt[18:22] == b"\x01\x02\x03\x00"


def test_address():
    pkt = build_art_address("PrimusTest")
    assert len(pkt) == 107
    assert _opcode(pkt) == OPCODE_ADDRESS
    assert pkt[14:24] == b"PrimusTest"


def test_configs():
    assert _opcode(build_output_config(["small_grid", "long_strip"])) == OPCODE_OUTPUT_CONFIG
    pkt = build_receive_config("combined", 5)
    assert _opcode(pkt) == OPCODE_RECEIVE_CONFIG
    assert pkt[12] == 1
    assert struct.unpack("<H", pkt[13:15])[0] == 5
    pkt = build_virtual_resolution([1, 72])
    assert _opcode(pkt) == OPCODE_VIRTUAL_RESOLUTION
    assert struct.unpack("<H", pkt[13:15])[0] == 1
    assert struct.unpack("<H", pkt[15:17])[0] == 72


def test_caps_parse():
    report = "#0001 [0123] OK|PV3CAP1|F:RIOHBMS|B:v31|IP:D|U:C:0|0:4:0:1|1:2:0:72"
    caps = parse_pv3cap1(report)
    assert caps["known"]
    assert caps["receive_mode"] == "combined"
    assert caps["base_universe"] == 0
    assert caps["ports"][0]["type_id"] == 4
    assert caps["ports"][0]["virtual"] == 1
    assert caps["rename"] and caps["receive_config"]


def test_combined_guard():
    ok, total, _ = validate_combined(122, 122)
    assert not ok and total == 244
    ok, total, _ = validate_combined(1, 72)
    assert ok and total == 73


def test_serpentine():
    order = serpentine_pixel_order(4, 2)
    assert order == [0, 1, 2, 3, 7, 6, 5, 4]


def main():
    tests = [
        test_poll,
        test_dmx_even_pad,
        test_address,
        test_configs,
        test_caps_parse,
        test_combined_guard,
        test_serpentine,
    ]
    for t in tests:
        t()
        print(f"OK {t.__name__}")
    print(f"All {len(tests)} checks passed.")


if __name__ == "__main__":
    main()
