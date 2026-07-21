"""Art-Net / Primus vendor packet builders - mirror V4 sender/artnet.py."""

from __future__ import annotations

import struct

from .output_types import TYPE_TO_ID

ARTNET_HEADER = b"Art-Net\x00"
ARTNET_VERSION = 14
ARTNET_PORT = 6454

OPCODE_POLL = 0x2000
OPCODE_POLLREPLY = 0x2100
OPCODE_DMX = 0x5000
OPCODE_ADDRESS = 0x6000
OPCODE_OUTPUT_CONFIG = 0x8100
OPCODE_RECEIVE_CONFIG = 0x8110
OPCODE_VIRTUAL_RESOLUTION = 0x8130
OPCODE_IP_CONFIG = 0x8200

NODE_CAPS_PREFIX = "PV3CAP1"


def _header(opcode: int) -> bytearray:
    pkt = bytearray()
    pkt += ARTNET_HEADER
    pkt += struct.pack("<H", opcode)
    pkt += struct.pack(">H", ARTNET_VERSION)
    return pkt


def build_art_poll() -> bytes:
    pkt = _header(OPCODE_POLL)
    pkt += bytes([0x00, 0x00])
    return bytes(pkt)


def build_art_dmx(universe: int, rgb_data: bytes, sequence: int = 1) -> bytes:
    data = rgb_data
    if len(data) % 2 != 0:
        data = data + b"\x00"
    pkt = _header(OPCODE_DMX)
    pkt.append(sequence & 0xFF)
    pkt.append(0)
    pkt += struct.pack("<H", int(universe) & 0xFFFF)
    pkt += struct.pack(">H", len(data))
    pkt += data
    return bytes(pkt)


def build_art_address(short_name: str) -> bytes:
    pkt = bytearray(107)
    pkt[0:8] = ARTNET_HEADER
    struct.pack_into("<H", pkt, 8, OPCODE_ADDRESS)
    struct.pack_into(">H", pkt, 10, ARTNET_VERSION)
    pkt[12] = 0x7F
    pkt[13] = 0
    name_bytes = short_name.encode("ascii", errors="replace")[:17]
    pkt[14 : 14 + len(name_bytes)] = name_bytes
    for i in range(96, 104):
        pkt[i] = 0x7F
    pkt[104] = 0x7F
    pkt[106] = 0x00
    return bytes(pkt)


def build_output_config(output_type_keys: list[str]) -> bytes:
    num = len(output_type_keys)
    pkt = bytearray(13 + num)
    pkt[0:8] = ARTNET_HEADER
    struct.pack_into("<H", pkt, 8, OPCODE_OUTPUT_CONFIG)
    struct.pack_into(">H", pkt, 10, ARTNET_VERSION)
    pkt[12] = num
    for i, key in enumerate(output_type_keys):
        pkt[13 + i] = TYPE_TO_ID.get(key, 0)
    return bytes(pkt)


def build_receive_config(receive_mode: str, base_universe: int) -> bytes:
    mode_id = 1 if receive_mode == "combined" else 0
    pkt = bytearray(15)
    pkt[0:8] = ARTNET_HEADER
    struct.pack_into("<H", pkt, 8, OPCODE_RECEIVE_CONFIG)
    struct.pack_into(">H", pkt, 10, ARTNET_VERSION)
    pkt[12] = mode_id
    struct.pack_into("<H", pkt, 13, int(base_universe) & 0xFFFF)
    return bytes(pkt)


def build_virtual_resolution(virtual_counts: list[int]) -> bytes:
    num = len(virtual_counts)
    pkt = bytearray(13 + (num * 2))
    pkt[0:8] = ARTNET_HEADER
    struct.pack_into("<H", pkt, 8, OPCODE_VIRTUAL_RESOLUTION)
    struct.pack_into(">H", pkt, 10, ARTNET_VERSION)
    pkt[12] = num
    for i, count in enumerate(virtual_counts):
        struct.pack_into("<H", pkt, 13 + (i * 2), int(count) & 0xFFFF)
    return bytes(pkt)


def build_ip_config(
    mode: int,
    static_ip: str | None = None,
    gateway: str | None = None,
    subnet: str | None = None,
) -> bytes:
    """mode: 0=DHCP, 1=static."""
    pkt = bytearray(25)
    pkt[0:8] = ARTNET_HEADER
    struct.pack_into("<H", pkt, 8, OPCODE_IP_CONFIG)
    struct.pack_into(">H", pkt, 10, ARTNET_VERSION)
    pkt[12] = mode
    if mode == 1:
        if not (static_ip and gateway and subnet):
            raise ValueError("static IP mode requires ip, gateway, and subnet")
        for i, octet in enumerate(_ipv4_octets(static_ip)):
            pkt[13 + i] = octet
        for i, octet in enumerate(_ipv4_octets(gateway)):
            pkt[17 + i] = octet
        for i, octet in enumerate(_ipv4_octets(subnet)):
            pkt[21 + i] = octet
    return bytes(pkt)


def _ipv4_octets(dotted: str) -> list[int]:
    parts = dotted.strip().split(".")
    if len(parts) != 4:
        raise ValueError(f"invalid IPv4: {dotted!r}")
    return [int(p) & 0xFF for p in parts]


def parse_art_poll_reply(raw: bytes) -> dict | None:
    if len(raw) < 44 or raw[:8] != ARTNET_HEADER:
        return None
    opcode = struct.unpack("<H", raw[8:10])[0]
    if opcode != OPCODE_POLLREPLY:
        return None
    ip = "{}.{}.{}.{}".format(raw[10], raw[11], raw[12], raw[13])
    short_name = raw[26:44].split(b"\x00")[0].decode("ascii", errors="replace")
    long_name = raw[44:108].split(b"\x00")[0].decode("ascii", errors="replace")
    node_report = raw[108:172].split(b"\x00")[0].decode("ascii", errors="replace")
    num_ports = raw[173] if len(raw) > 173 else 0
    sw_out = []
    for i in range(min(num_ports, 4)):
        if len(raw) > 190 + i:
            sw_out.append(raw[190 + i])  # low nibble only - do not trust for univ>=16
    fw = None
    if len(raw) > 17:
        fw = f"{raw[16]}.{raw[17]}"
    caps = parse_pv3cap1(node_report)
    return {
        "ip": ip,
        "short_name": short_name,
        "long_name": long_name,
        "node_report": node_report,
        "num_ports": num_ports,
        "sw_out": sw_out,
        "firmware_version": fw,
        "capabilities": caps,
        "is_primus": NODE_CAPS_PREFIX in node_report or "primusv3" in long_name.lower(),
    }


def parse_pv3cap1(node_report: str) -> dict:
    caps = {
        "known": False,
        "features": "",
        "board": "unknown",
        "ip_mode": "unknown",
        "static_ip": None,
        "gateway": None,
        "subnet": None,
        "receive_mode": None,
        "base_universe": None,
        "ports": [],  # list of {port, type_id, universe, virtual}
        "rename": False,
        "hello": False,
        "ip_config": False,
        "output_config": False,
        "receive_config": False,
        "battery": False,
        "show_info": False,
    }
    if not node_report or NODE_CAPS_PREFIX not in node_report:
        return caps
    # Strip Art-Net status prefix if present: "#0001 [NNNN] OK|..."
    blob = node_report
    if "|" in blob:
        # Keep from PV3CAP1 onward
        idx = blob.find(NODE_CAPS_PREFIX)
        if idx >= 0:
            blob = blob[idx:]
    parts = blob.split("|")
    caps["known"] = True
    for part in parts:
        if part.startswith("F:"):
            features = part[2:]
            caps["features"] = features
            caps["rename"] = "R" in features
            caps["hello"] = "H" in features
            caps["ip_config"] = "I" in features
            caps["output_config"] = "O" in features
            caps["receive_config"] = "M" in features
            caps["battery"] = "B" in features
            caps["show_info"] = "S" in features
        elif part.startswith("B:"):
            caps["board"] = part[2:].strip() or "unknown"
        elif part.startswith("IP:"):
            vals = part[3:].split(":")
            mode = (vals[0] or "").strip().upper()
            if mode == "D":
                caps["ip_mode"] = "dhcp"
            elif mode == "S":
                caps["ip_mode"] = "static"
                if len(vals) >= 4:
                    caps["static_ip"] = vals[1]
                    caps["gateway"] = vals[2]
                    caps["subnet"] = vals[3]
        elif part.startswith("U:"):
            # U:C:0 or U:S:0
            bits = part.split(":")
            if len(bits) >= 3:
                caps["receive_mode"] = "combined" if bits[1] == "C" else "split"
                try:
                    caps["base_universe"] = int(bits[2])
                except ValueError:
                    pass
        else:
            # port:type:univ:virt  or  port:type:univ (truncated)
            bits = part.split(":")
            if len(bits) >= 3 and bits[0].isdigit():
                entry = {
                    "port": int(bits[0]),
                    "type_id": int(bits[1]),
                    "universe": int(bits[2]),
                    "virtual": int(bits[3]) if len(bits) > 3 else None,
                }
                caps["ports"].append(entry)
    return caps


def bytes_to_td_hex(data: bytes) -> str:
    """Format for UDP Out DAT sendBytes / Table DAT hex columns."""
    return " ".join(f"{b:02X}" for b in data)
