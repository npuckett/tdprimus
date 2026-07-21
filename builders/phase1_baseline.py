"""
Phase 1 - Baseline Primus transport.

Sends ArtDmx via UDP Out DAT using builders.lib.packets (bypasses DMX Out CHOP
quirks). Pattern is progressive wire-order; no serpentine.

Preferred: python3 builders/td_remote.py build 1 --pattern index_white
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _bootstrap():
    try:
        root = project.folder  # noqa: F821
    except NameError:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)


_bootstrap()

try:
    from builders.lib.output_types import physical_pixels
    from builders.lib.packets import ARTNET_PORT, build_art_dmx
    from builders.lib.td_builder import (
        create_child,
        ensure_base,
        init_device_table,
        place,
        prepare_build,
        set_par,
    )
except ImportError:
    physical_pixels = None
    ARTNET_PORT = 6454
    build_art_dmx = None


PARENT_PATH = "/project1"
BASE_NAME = "primus_phase1"

DEFAULT_DEVICE = {
    "name": "test",
    "ip": "192.168.8.166",
    "universe": "0",
    "recv_mode": "split",
    "a0_type": "small_grid",
    "a0_count": "32",
    "a0_virtual": "32",
    "a1_type": "none",
    "a1_count": "0",
    "a1_virtual": "0",
    "group": "default",
}


def _rgb_for_pattern(pattern: str, i: int, n_pixels: int, level: int = 64):
    """level is peak channel value 0-255 (default 64 ~= 25% for comfortable viewing)."""
    level = max(0, min(255, int(level)))
    if pattern == "solid_red":
        return (level, 0, 0)
    if pattern == "solid_green":
        return (0, level, 0)
    if pattern == "solid_blue":
        return (0, 0, level)
    if pattern == "index_white":
        return (level, level, level) if i == 0 else (0, 0, 0)
    if pattern == "rows":
        row = i // 8
        return [
            (level, 0, 0),
            (0, level, 0),
            (0, 0, level),
            (level, level, level),
        ][min(row, 3)]
    third = max(1, n_pixels // 3)
    if i < third:
        return (level, 0, 0)
    if i < 2 * third:
        return (0, level, 0)
    return (0, 0, level)


def _payload_bytes(n_pixels: int, pattern: str, blackout: bool, level: int = 64) -> bytes:
    if blackout:
        return bytes(n_pixels * 3)
    out = bytearray()
    for i in range(n_pixels):
        r, g, b = _rgb_for_pattern(pattern, i, n_pixels, level=level)
        out.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(out)


_SEND_EXEC = r'''
# Frame-start sender: build ArtDmx and UDP-unicast to the device.

def onFrameStart(frame):
    root = me.parent()
    ctrl = root.op("controls")
    meta = root.op("meta")
    udp = root.op("udp_out")
    if ctrl is None or meta is None or udp is None:
        return
    try:
        if int(ctrl["active", 1]) != 1:
            return
    except Exception:
        return

    import sys
    folder = project.folder
    if folder and folder not in sys.path:
        sys.path.insert(0, folder)
    for key in list(sys.modules):
        if key == "builders" or key.startswith("builders."):
            del sys.modules[key]
    from builders.lib.packets import build_art_dmx, ARTNET_PORT

    try:
        ip = ctrl["ip", 1].val.strip()
        universe = int(ctrl["universe", 1])
        pattern = ctrl["pattern", 1].val.strip() or "thirds"
        n_pixels = int(meta["n_pixels", 1])
        blackout = int(ctrl["blackout", 1]) == 1
        try:
            level = int(ctrl["level", 1])
        except Exception:
            level = 64
    except Exception as e:
        print("[phase1 send] controls read failed", e)
        return

    if blackout:
        rgb = bytes(n_pixels * 3)
    else:
        rgb = _make_rgb(pattern, n_pixels, level)

    pkt = build_art_dmx(universe, rgb, sequence=(frame % 255) + 1)
    try:
        udp.par.address = ip
        udp.par.port = ARTNET_PORT
    except Exception:
        pass
    try:
        udp.sendBytes(pkt)
    except Exception:
        try:
            udp.send(pkt.decode("latin1"))
        except Exception as e:
            print("[phase1 send] UDP failed", e)

def _make_rgb(pattern, n_pixels, level=64):
    out = bytearray()
    level = max(0, min(255, int(level)))
    third = max(1, n_pixels // 3)
    for i in range(n_pixels):
        if pattern == "solid_red":
            rgb = (level, 0, 0)
        elif pattern == "solid_green":
            rgb = (0, level, 0)
        elif pattern == "solid_blue":
            rgb = (0, 0, level)
        elif pattern == "index_white":
            rgb = (level, level, level) if i == 0 else (0, 0, 0)
        elif pattern == "rows":
            row = i // 8
            rgb = [
                (level, 0, 0),
                (0, level, 0),
                (0, 0, level),
                (level, level, level),
            ][min(row, 3)]
        else:
            if i < third:
                rgb = (level, 0, 0)
            elif i < 2 * third:
                rgb = (0, level, 0)
            else:
                rgb = (0, 0, level)
        out.extend(rgb)
    return bytes(out)
'''


def build(
    parent_path: str = PARENT_PATH,
    device_ip: str = None,
    universe: int = 0,
    output_type: str = "small_grid",
    pattern: str = "thirds",
    level: int = 64,
    netinterface: str = "",
):
    prepare_build(globals())
    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 0, -400)

    n_px = physical_pixels(output_type)
    ip = device_ip or DEFAULT_DEVICE["ip"]
    univ = int(universe)
    level = max(0, min(255, int(level)))

    row = dict(DEFAULT_DEVICE)
    row["a0_type"] = output_type
    row["a0_count"] = str(n_px)
    row["a0_virtual"] = str(n_px)
    row["universe"] = str(univ)
    row["ip"] = ip

    devices = create_child(base, "tableDAT", "devices")
    place(devices, 0, 200)
    init_device_table(devices, [row])

    meta = create_child(base, "tableDAT", "meta")
    place(meta, 200, 200)
    meta.clear()
    meta.appendRow(["param", "value"])
    meta.appendRow(["n_pixels", str(n_px)])
    meta.appendRow(["output_type", output_type])

    ctrl = create_child(base, "tableDAT", "controls")
    place(ctrl, 400, 200)
    ctrl.clear()
    ctrl.appendRow(["param", "value"])
    ctrl.appendRow(["active", "1"])
    ctrl.appendRow(["blackout", "0"])
    ctrl.appendRow(["pattern", pattern])
    ctrl.appendRow(["level", str(level)])
    ctrl.appendRow(["ip", ip])
    ctrl.appendRow(["universe", str(univ)])

    udp = create_child(base, "udpoutDAT", "udp_out")
    place(udp, 0, 0)
    set_par(udp, port=ARTNET_PORT, protocol="udp", address=ip)
    try:
        set_par(udp, rowaddress=False)
    except Exception:
        pass

    sender = create_child(base, "executeDAT", "artnet_send")
    place(sender, 200, 0)
    sender.text = _SEND_EXEC
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(sender.par, flag).val = True
        except Exception:
            pass
    try:
        set_par(sender, framestart=True, active=True)
    except Exception:
        pass

    rgb = _payload_bytes(n_px, pattern, blackout=False, level=level)
    pkt = build_art_dmx(univ, rgb, sequence=1)
    try:
        udp.par.address = ip
        udp.sendBytes(pkt)
        sent = True
    except Exception as exc:
        try:
            udp.send(pkt.decode("latin1"))
            sent = True
        except Exception as exc2:
            sent = False
            print(f"[phase1] immediate send failed: {exc} / {exc2}")

    diag = {
        "pattern": pattern,
        "level": level,
        "ip": ip,
        "universe": univ,
        "n_pixels": n_px,
        "payload_len": len(rgb),
        "packet_len": len(pkt),
        "immediate_send": sent,
        "first_pixel_rgb": list(rgb[0:3]) if rgb else None,
        "artnet_port": ARTNET_PORT,
    }
    try:
        folder = Path(project.folder)  # noqa: F821
    except Exception:
        folder = Path(__file__).resolve().parents[1]
    diag_path = folder / "builders" / ".td_phase1_diag.json"
    diag_path.write_text(json.dumps(diag, indent=2) + "\n", encoding="utf-8")

    info = create_child(base, "textDAT", "README")
    place(info, 0, 400)
    info.text = (
        "Phase 1 - UDP ArtDmx sender (not DMX Out CHOP)\n"
        f"pattern={pattern} level={level}/255 ip={ip} univ={univ} px={n_px}\n"
        "controls.active=1 enables per-frame send.\n"
        "controls.blackout=1 sends zeros.\n"
        "controls.level sets peak 0-255 (default 64).\n"
        "patterns: index_white | solid_red | solid_green | solid_blue | thirds | rows\n"
    )

    print(f"[phase1] built {base.path} pattern={pattern} level={level} send={sent}")
    if not sent:
        raise RuntimeError("phase1 UDP ArtDmx immediate send failed - check udpoutDAT")
    return base
