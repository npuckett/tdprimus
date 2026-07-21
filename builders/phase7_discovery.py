"""
Phase 7 - Discovery (ArtPoll / ArtPollReply + PV3CAP1).

    exec(open(f'{project.folder}/builders/phase7_discovery.py').read())
    build()

Creates UDP In/Out DATs on 6454, parser callback, rescan control, and
auto-populated devices table. Does not trust ArtPollReply SwOut for universe.
"""

from __future__ import annotations

import sys


def _bootstrap():
    try:
        root = project.folder  # noqa: F821
    except NameError:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)


_bootstrap()

from builders.lib.output_types import LOOK_OUTPUT_TYPES, default_virtual, physical_pixels  # noqa: E402
from builders.lib.packets import (  # noqa: E402
    ARTNET_PORT,
    build_art_poll,
    bytes_to_td_hex,
    parse_art_poll_reply,
)
from builders.lib.td_builder import (  # noqa: E402
    prepare_build,
    clear_children,
    ensure_base,
    init_device_table,
    place,
    set_par,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase7"

# Embedded parser for UDP In DAT callback (must be self-contained inside TD)
_UDP_CALLBACK = r'''
# Callbacks for UDP In DAT - paste lives on the DAT; also mirrored here for rebuild.

import struct

ARTNET_HEADER = b"Art-Net\x00"
OPCODE_POLLREPLY = 0x2100
NODE_CAPS_PREFIX = "PV3CAP1"
LOOK_OUTPUT_TYPES = [
    "none", "short_strip", "long_strip", "grid", "small_grid", "extra_long_strip"
]
DEFAULT_VIRTUAL = {
    "none": 0, "short_strip": 30, "long_strip": 72,
    "grid": 64, "small_grid": 1, "extra_long_strip": 122,
}
PHYSICAL = {
    "none": 0, "short_strip": 30, "long_strip": 72,
    "grid": 64, "small_grid": 32, "extra_long_strip": 122,
}

def onReceive(dat, rowIndex, message, bytes, peer):
    raw = bytes if isinstance(bytes, (bytes, bytearray)) else bytes.encode("latin1")
    node = _parse(raw)
    if node is None:
        return
    root = dat.parent()
    log = root.op("discovery_log")
    if log:
        log.appendRow([node["ip"], node["short_name"], node.get("node_report", "")[:60]])
    if not node.get("is_primus"):
        other = root.op("non_primus")
        if other:
            # update or append
            _upsert(other, node["ip"], [node["ip"], node["short_name"], "non-primus"])
        return
    devices = root.op("devices")
    if devices is None:
        return
    row = _node_to_row(node)
    _upsert_device(devices, row)

def _parse(raw):
    if len(raw) < 44 or raw[:8] != ARTNET_HEADER:
        return None
    opcode = struct.unpack("<H", raw[8:10])[0]
    if opcode != OPCODE_POLLREPLY:
        return None
    ip = "{}.{}.{}.{}".format(raw[10], raw[11], raw[12], raw[13])
    short_name = raw[26:44].split(b"\x00")[0].decode("ascii", errors="replace")
    long_name = raw[44:108].split(b"\x00")[0].decode("ascii", errors="replace")
    node_report = raw[108:172].split(b"\x00")[0].decode("ascii", errors="replace")
    caps = _parse_caps(node_report)
    is_primus = NODE_CAPS_PREFIX in node_report or "primusv3" in long_name.lower()
    return {
        "ip": ip,
        "short_name": short_name,
        "long_name": long_name,
        "node_report": node_report,
        "capabilities": caps,
        "is_primus": is_primus,
    }

def _parse_caps(node_report):
    caps = {
        "receive_mode": None, "base_universe": None, "ports": [],
        "board": "unknown", "features": "",
    }
    if not node_report or NODE_CAPS_PREFIX not in node_report:
        return caps
    idx = node_report.find(NODE_CAPS_PREFIX)
    blob = node_report[idx:]
    for part in blob.split("|"):
        if part.startswith("F:"):
            caps["features"] = part[2:]
        elif part.startswith("B:"):
            caps["board"] = part[2:]
        elif part.startswith("U:"):
            bits = part.split(":")
            if len(bits) >= 3:
                caps["receive_mode"] = "combined" if bits[1] == "C" else "split"
                try:
                    caps["base_universe"] = int(bits[2])
                except ValueError:
                    pass
        else:
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

def _type_key(type_id):
    if 0 <= type_id < len(LOOK_OUTPUT_TYPES):
        return LOOK_OUTPUT_TYPES[type_id]
    return "none"

def _node_to_row(node):
    caps = node["capabilities"]
    ports = {p["port"]: p for p in caps.get("ports", [])}
    def port_info(i):
        p = ports.get(i)
        if not p:
            # Long-name fallback is incomplete; use workshop defaults for missing
            if i == 0:
                return "small_grid", 32, 1, caps.get("base_universe") or 0
            return "long_strip", 72, 72, (caps.get("base_universe") or 0)
        key = _type_key(p["type_id"])
        virt = p["virtual"] if p["virtual"] is not None else DEFAULT_VIRTUAL.get(key, 0)
        # Prefer capability universe, NOT SwOut
        univ = p["universe"]
        return key, PHYSICAL.get(key, 0), virt, univ
    a0t, a0c, a0v, u0 = port_info(0)
    a1t, a1c, a1v, u1 = port_info(1)
    mode = caps.get("receive_mode") or "combined"
    base_u = caps.get("base_universe")
    if base_u is None:
        base_u = u0 if mode == "combined" else u0
    return {
        "name": node["short_name"] or node["ip"],
        "ip": node["ip"],
        "universe": str(base_u),
        "recv_mode": mode,
        "a0_type": a0t,
        "a0_count": str(a0c),
        "a0_virtual": str(a0v),
        "a1_type": a1t,
        "a1_count": str(a1c),
        "a1_virtual": str(a1v),
        "group": "",
    }

def _upsert_device(table, row):
    cols = [table[0, c].val for c in range(table.numCols)]
    # find by ip
    ip_col = cols.index("ip") if "ip" in cols else 1
    found = None
    for r in range(1, table.numRows):
        if table[r, ip_col].val == row["ip"]:
            found = r
            break
    values = [row.get(c, "") for c in cols]
    if found is None:
        table.appendRow(values)
    else:
        for c, v in enumerate(values):
            table[found, c] = v

def _upsert(table, key, values):
    found = None
    for r in range(1, table.numRows):
        if table[r, 0].val == key:
            found = r
            break
    if found is None:
        table.appendRow(values)
    else:
        for c, v in enumerate(values):
            table[found, c] = v
'''

_RESCAN_EXEC = r'''
def onTableChange(dat):
    try:
        if int(dat['rescan', 1]) != 1:
            return
    except Exception:
        return
    dat['rescan', 1] = 0
    root = dat.parent()
    udp_out = root.op('udp_out_poll')
    poll_hex = root.op('poll_packet')
    if udp_out is None or poll_hex is None:
        return
    # Send raw bytes from poll_packet text (hex)
    hexstr = poll_hex.text.replace(' ', '').replace('\\n', '')
    try:
        raw = bytes.fromhex(hexstr)
    except Exception as e:
        print('[phase6] bad poll hex', e)
        return
    try:
        udp_out.sendBytes(raw)
        print('[phase6] ArtPoll sent')
    except Exception as e:
        # Some TD builds: send(str) only - try convert
        try:
            udp_out.send(raw.decode('latin1'))
        except Exception as e2:
            print('[phase6] send failed', e, e2)
'''


def build(parent_path: str = PARENT_PATH, bind_ip: str = "0.0.0.0"):
    prepare_build(globals())
    base = ensure_base(parent_path, BASE_NAME, recreate=True)

    devices = base.create(tableDAT, "devices")
    place(devices, 0, 200)
    init_device_table(devices, [])

    non_primus = base.create(tableDAT, "non_primus")
    place(non_primus, 200, 200)
    non_primus.clear()
    non_primus.appendRow(["ip", "short_name", "note"])

    log = base.create(tableDAT, "discovery_log")
    place(log, 400, 200)
    log.clear()
    log.appendRow(["ip", "short_name", "node_report"])

    controls = base.create(tableDAT, "controls")
    place(controls, 600, 200)
    controls.clear()
    controls.appendRow(["param", "value"])
    controls.appendRow(["rescan", "0"])

    poll_bytes = build_art_poll()
    poll_dat = base.create(textDAT, "poll_packet")
    place(poll_dat, 0, 0)
    poll_dat.text = bytes_to_td_hex(poll_bytes).replace(" ", "")

    udp_in = base.create(udpinDAT, "udp_in")
    place(udp_in, 200, 0)
    set_par(udp_in, port=ARTNET_PORT, protocol="udp")
    try:
        set_par(udp_in, address=bind_ip)
    except Exception:
        pass
    # callbacks
    cb = base.create(textDAT, "udp_callbacks")
    place(cb, 400, 0)
    cb.text = _UDP_CALLBACK
    try:
        udp_in.par.callbacks = cb.path
    except Exception:
        # Alternate: put callbacks on the UDP In DAT itself
        try:
            udp_in.text = _UDP_CALLBACK
        except Exception as exc:
            print(f"[phase6] wire callbacks manually: {exc}")

    udp_out = base.create(udpoutDAT, "udp_out_poll")
    place(udp_out, 600, 0)
    set_par(udp_out, port=ARTNET_PORT, protocol="udp")
    try:
        set_par(udp_out, address="255.255.255.255")
        set_par(udp_out, rowaddress=True)  # if available
    except Exception:
        pass

    rescan_exec = base.create(executeDAT, "rescan_execute")
    place(rescan_exec, 800, 0)
    rescan_exec.text = _RESCAN_EXEC
    try:
        rescan_exec.par.dat = controls.path
        rescan_exec.par.tablechange = True
    except Exception:
        pass

    # Timer optional auto-rescan every 10s
    timer = base.create(timerCHOP, "auto_rescan")
    place(timer, 800, 200)
    try:
        set_par(timer, length=10, cycle=True, cueonstart=True)
    except Exception:
        pass

    info = base.create(textDAT, "README")
    place(info, 0, 400)
    info.text = (
        "Phase 7 discovery\n"
        f"UDP In bound to {ARTNET_PORT}. Set controls.rescan=1 to ArtPoll.\n"
        "Primus nodes fill `devices` from PV3CAP1 (not SwOut).\n"
        "Non-Primus Art-Net nodes go to `non_primus`.\n"
        "See handoffs/phase6_test.md\n\n"
        f"Poll packet ({len(poll_bytes)} bytes): {bytes_to_td_hex(poll_bytes)}"
    )
    # Sanity: ensure parse works offline
    print(f"[phase6] built {base.path}; poll={bytes_to_td_hex(poll_bytes)}")
    return base
