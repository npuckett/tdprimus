"""
Phase 2 - Dual-output ArtDmx with V4 virtual resolution.

Supports:
  recv_mode=split     -> univ base = A0, univ base+1 = A1 (two packets)
  recv_mode=combined  -> one packet [A0 virt][A1 virt] on base univ

Default for live workshop devices stuck in split after Phase 1: split.
Also pushes ArtOutputConfig + ArtVirtualResolution (+ receive config) on build.

Preferred:
  python3 builders/td_remote.py build 2 --recv-mode split
  python3 builders/td_remote.py build 2 --recv-mode combined
"""

from __future__ import annotations

import json
import socket
import sys
import time
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
    from builders.lib.output_types import (
        COMBINED_RECEIVE_MAX_PIXELS,
        default_virtual,
        physical_pixels,
        validate_combined,
    )
    from builders.lib.packets import (
        ARTNET_PORT,
        build_art_dmx,
        build_output_config,
        build_receive_config,
        build_virtual_resolution,
    )
    from builders.lib.td_builder import (
        create_child,
        ensure_base,
        init_device_table,
        place,
        prepare_build,
        set_par,
        td_op,
    )
except ImportError:
    COMBINED_RECEIVE_MAX_PIXELS = 170
    default_virtual = physical_pixels = validate_combined = None
    ARTNET_PORT = 6454
    build_art_dmx = None


PARENT_PATH = "/project1"
BASE_NAME = "primus_phase2"


def _rgb_for_pattern(pattern: str, i: int, n_pixels: int, level: int = 64):
    level = max(0, min(255, int(level)))
    if n_pixels <= 0:
        return (0, 0, 0)
    if pattern == "solid_red":
        return (level, 0, 0)
    if pattern == "solid_green":
        return (0, level, 0)
    if pattern == "solid_blue":
        return (0, 0, level)
    if pattern == "solid_cyan":
        return (0, level, level)
    if pattern == "solid_magenta":
        return (level, 0, level)
    if pattern == "solid_yellow":
        return (level, level, 0)
    if pattern == "index_white":
        return (level, level, level) if i == 0 else (0, 0, 0)
    third = max(1, n_pixels // 3)
    if i < third:
        return (level, 0, 0)
    if i < 2 * third:
        return (0, level, 0)
    return (0, 0, level)


def _port_bytes(n_virtual: int, pattern: str, level: int) -> bytes:
    if n_virtual <= 0:
        return b""
    out = bytearray()
    for i in range(n_virtual):
        r, g, b = _rgb_for_pattern(pattern, i, n_virtual, level=level)
        out.extend((r & 0xFF, g & 0xFF, b & 0xFF))
    return bytes(out)


def _udp_send(ip: str, packet: bytes) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (ip, ARTNET_PORT))
        return True
    except OSError as exc:
        print(f"[phase2] UDP send failed: {exc}")
        return False
    finally:
        sock.close()


def _push_device_config(ip: str, mode: str, base_u: int, v0: int, v1: int, a0_type: str, a1_type: str):
    """Best-effort vendor opcode pushes (may be ignored by older firmware)."""
    ok = True
    for label, pkt in (
        ("ArtOutputConfig", build_output_config([a0_type, a1_type])),
        ("ArtVirtualResolution", build_virtual_resolution([v0, v1])),
        ("ArtReceiveConfig", build_receive_config(mode, base_u)),
    ):
        if _udp_send(ip, pkt):
            print(f"[phase2] pushed {label} ({len(pkt)}B) -> {ip}")
        else:
            ok = False
        time.sleep(0.05)
    return ok


_SEND_EXEC = r'''
def onFrameStart(frame):
    root = me.parent()
    ctrl = root.op("controls")
    meta = root.op("meta")
    if ctrl is None or meta is None:
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
    import socket

    try:
        ip = ctrl["ip", 1].val.strip()
        universe = int(ctrl["universe", 1])
        level = int(ctrl["level", 1])
        blackout = int(ctrl["blackout", 1]) == 1
        mode = (ctrl["recv_mode", 1].val.strip() or "split").lower()
        v0 = int(meta["a0_virtual", 1])
        v1 = int(meta["a1_virtual", 1])
        p0 = ctrl["a0_pattern", 1].val.strip() or "solid_red"
        p1 = ctrl["a1_pattern", 1].val.strip() or "thirds"
    except Exception as e:
        print("[phase2 send] controls read failed", e)
        return

    seq = (frame % 255) + 1
    a0 = _port(v0, p0, level) if not blackout else bytes(v0 * 3)
    a1 = _port(v1, p1, level) if not blackout else bytes(v1 * 3)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if mode == "combined":
            pkt = build_art_dmx(universe, a0 + a1, sequence=seq)
            sock.sendto(pkt, (ip, ARTNET_PORT))
        else:
            # split: A0 on base, A1 on base+1
            if v0 > 0:
                sock.sendto(build_art_dmx(universe, a0, sequence=seq), (ip, ARTNET_PORT))
            if v1 > 0:
                sock.sendto(build_art_dmx(universe + 1, a1, sequence=seq), (ip, ARTNET_PORT))
    except Exception as e:
        print("[phase2 send] UDP failed", e)
    finally:
        sock.close()

def _port(n, pattern, level):
    out = bytearray()
    level = max(0, min(255, int(level)))
    third = max(1, n // 3) if n else 1
    for i in range(n):
        if pattern == "solid_red":
            rgb = (level, 0, 0)
        elif pattern == "solid_green":
            rgb = (0, level, 0)
        elif pattern == "solid_blue":
            rgb = (0, 0, level)
        elif pattern == "solid_cyan":
            rgb = (0, level, level)
        elif pattern == "solid_magenta":
            rgb = (level, 0, level)
        elif pattern == "solid_yellow":
            rgb = (level, level, 0)
        elif pattern == "index_white":
            rgb = (level, level, level) if i == 0 else (0, 0, 0)
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


def _silence_phase1():
    try:
        p1 = td_op("/project1/primus_phase1")
        if p1 is None:
            return
        ctrl = p1.op("controls")
        if ctrl is None:
            return
        for r in range(1, ctrl.numRows):
            if ctrl[r, 0].val == "active":
                ctrl[r, 1] = "0"
                print("[phase2] silenced primus_phase1 (active=0)")
                return
    except Exception as exc:
        print(f"[phase2] could not silence phase1: {exc}")


def build(
    parent_path: str = PARENT_PATH,
    device_ip: str = "192.168.8.166",
    universe: int = 0,
    a0_type: str = "small_grid",
    a1_type: str = "long_strip",
    a0_virtual: int = None,
    a1_virtual: int = None,
    a0_pattern: str = "solid_red",
    a1_pattern: str = "thirds",
    level: int = 64,
    recv_mode: str = "split",
):
    prepare_build(globals())
    _silence_phase1()

    mode = (recv_mode or "split").lower()
    if mode not in ("split", "combined"):
        raise ValueError(f"recv_mode must be split|combined, got {mode!r}")

    # Virtual counts: default to V4 type defaults (small_grid=1, long_strip=72)
    v0 = default_virtual(a0_type) if a0_virtual is None else int(a0_virtual)
    v1 = default_virtual(a1_type) if a1_virtual is None else int(a1_virtual)
    v0 = max(0, min(v0, physical_pixels(a0_type)))
    v1 = max(0, min(v1, physical_pixels(a1_type)))

    if mode == "combined":
        ok, total, msg = validate_combined(v0, v1)
        if not ok:
            raise ValueError(f"{msg} (A0 virt={v0} + A1 virt={v1})")
    else:
        total = v0 + v1
        ok, msg = True, "split ok"

    level = max(0, min(255, int(level)))
    ip = device_ip
    univ = int(universe)

    # Push config from this Python process (more reliable than TD udpout alone)
    _push_device_config(ip, mode, univ, v0, v1, a0_type, a1_type)
    time.sleep(0.1)

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 0, -400)

    row = {
        "name": "test",
        "ip": ip,
        "universe": str(univ),
        "recv_mode": mode,
        "a0_type": a0_type,
        "a0_count": str(physical_pixels(a0_type)),
        "a0_virtual": str(v0),
        "a1_type": a1_type,
        "a1_count": str(physical_pixels(a1_type)),
        "a1_virtual": str(v1),
        "group": "default",
    }
    devices = create_child(base, "tableDAT", "devices")
    place(devices, 0, 200)
    init_device_table(devices, [row])

    meta = create_child(base, "tableDAT", "meta")
    place(meta, 200, 200)
    meta.clear()
    meta.appendRow(["param", "value"])
    for k, v in (
        ("a0_type", a0_type),
        ("a1_type", a1_type),
        ("a0_virtual", str(v0)),
        ("a1_virtual", str(v1)),
        ("a0_physical", str(physical_pixels(a0_type))),
        ("a1_physical", str(physical_pixels(a1_type))),
        ("combined_virtual_total", str(total)),
        ("combined_max", str(COMBINED_RECEIVE_MAX_PIXELS)),
        ("recv_mode", mode),
        ("a1_universe", str(univ if mode == "combined" else univ + 1)),
    ):
        meta.appendRow([k, v])

    ctrl = create_child(base, "tableDAT", "controls")
    place(ctrl, 400, 200)
    ctrl.clear()
    ctrl.appendRow(["param", "value"])
    for k, v in (
        ("active", "1"),
        ("blackout", "0"),
        ("level", str(level)),
        ("a0_pattern", a0_pattern),
        ("a1_pattern", a1_pattern),
        ("a0_virtual", str(v0)),
        ("a1_virtual", str(v1)),
        ("ip", ip),
        ("universe", str(univ)),
        ("recv_mode", mode),
    ):
        ctrl.appendRow([k, v])

    # Keep a udpout around for inspection; frame sender uses Python socket
    udp = create_child(base, "udpoutDAT", "udp_out")
    place(udp, 0, 0)
    set_par(udp, port=ARTNET_PORT, protocol="udp", address=ip)

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

    a0 = _port_bytes(v0, a0_pattern, level)
    a1 = _port_bytes(v1, a1_pattern, level)
    sent = True
    if mode == "combined":
        pkt = build_art_dmx(univ, a0 + a1, sequence=1)
        sent = _udp_send(ip, pkt) and sent
        packets = [{"universe": univ, "payload_len": len(a0) + len(a1)}]
    else:
        packets = []
        if v0 > 0:
            pkt0 = build_art_dmx(univ, a0, sequence=1)
            sent = _udp_send(ip, pkt0) and sent
            packets.append({"universe": univ, "payload_len": len(a0)})
        if v1 > 0:
            pkt1 = build_art_dmx(univ + 1, a1, sequence=1)
            sent = _udp_send(ip, pkt1) and sent
            packets.append({"universe": univ + 1, "payload_len": len(a1)})

    diag = {
        "phase": 2,
        "ip": ip,
        "recv_mode": mode,
        "universe_base": univ,
        "a0_type": a0_type,
        "a1_type": a1_type,
        "a0_virtual": v0,
        "a1_virtual": v1,
        "a0_pattern": a0_pattern,
        "a1_pattern": a1_pattern,
        "level": level,
        "packets": packets,
        "immediate_send": sent,
        "a0_first_rgb": list(a0[0:3]) if a0 else None,
        "a1_first_rgb": list(a1[0:3]) if a1 else None,
    }
    try:
        folder = Path(project.folder)  # noqa: F821
    except Exception:
        folder = Path(__file__).resolve().parents[1]
    diag_path = folder / "builders" / ".td_phase2_diag.json"
    diag_path.write_text(json.dumps(diag, indent=2) + "\n", encoding="utf-8")

    info = create_child(base, "textDAT", "README")
    place(info, 0, 400)
    info.text = (
        f"Phase 2 - {mode} ArtDmx + V4 virtual resolution\n"
        f"A0 {a0_type} virt={v0} ({a0_pattern}) / A1 {a1_type} virt={v1} ({a1_pattern})\n"
        f"universes: {packets}\n"
        "controls.recv_mode = split|combined\n"
        "See handoffs/phase2_test.md\n"
    )

    print(f"[phase2] built {base.path} mode={mode} A0={v0} A1={v1} send={sent}")
    if not sent:
        raise RuntimeError("phase2 UDP ArtDmx send failed")
    return base
