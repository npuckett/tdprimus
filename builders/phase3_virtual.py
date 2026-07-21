"""
Phase 3 - Live virtual resolution (correct V4 semantics).

Virtual resolution is the count of RGB triplets we send per output.
The receiver upsamples those values across physical LEDs:
  virt=1  -> one color fills the whole output
  virt=N  -> N colors spread across physical pixels

Flow each frame:
  1. Read controls.a0_virtual / a1_virtual
  2. If changed, push ArtVirtualResolution to the device
  3. Send ArtDmx with exactly that many RGB values (split: univ base / base+1)

Uses a cook-always Script CHOP (not only Execute DAT) so live edits actually run.
Firmware hold-last-frame made earlier table edits look like no-ops when the
frame callback was not firing.

Preferred:
  python3 builders/td_remote.py build 3 --recv-mode split \\
    --a0-virtual 32 --a1-virtual 72 --level 64
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
BASE_NAME = "primus_phase3"

# Self-contained sender: no builders imports (avoids per-frame import failures).
# Lives in a Text DAT wired to scriptCHOP.par.callbacks.
#
# Important: do NOT push ArtOutputConfig / ArtReceiveConfig from the cook loop.
# ArtVirtualResolution triggers NVS save + ArtPollReply on device - push only
# when virt counts change, debounced. Do not rewrite devices table every frame
# (that locks the TD UI while you edit).
_SCRIPT_CHOP = r'''
def onGetCookLevel(scriptOp):
    try:
        return CookLevel.ALWAYS
    except Exception:
        return 3


def onCook(scriptOp):
    root = scriptOp.parent()
    ctrl = root.op("controls")
    if ctrl is None:
        scriptOp.clear()
        return

    try:
        if int(_cell(ctrl, "active")) != 1:
            scriptOp.clear()
            return
    except Exception:
        scriptOp.clear()
        return

    import socket
    import struct
    import time

    ARTNET_PORT = 6454
    HEADER = b"Art-Net\x00"
    # Cap ArtDmx rate (~30 fps) even if TD cooks faster
    SEND_INTERVAL = 1.0 / 30.0
    # Debounce virt pushes so rapid table edits do not spam NVS
    VIRT_DEBOUNCE = 0.35

    def art_dmx(universe, payload, sequence=1):
        data = bytes(payload)
        if len(data) % 2 == 1:
            data = data + b"\x00"
        pkt = bytearray()
        pkt += HEADER
        pkt += struct.pack("<H", 0x5000)
        pkt += struct.pack(">H", 14)
        pkt += bytes([int(sequence) & 0xFF, 0])
        pkt += struct.pack("<H", int(universe) & 0xFFFF)
        pkt += struct.pack(">H", len(data))
        pkt += data
        return bytes(pkt)

    def art_virtual(counts):
        num = len(counts)
        pkt = bytearray(13 + num * 2)
        pkt[0:8] = HEADER
        struct.pack_into("<H", pkt, 8, 0x8130)
        struct.pack_into(">H", pkt, 10, 14)
        pkt[12] = num
        for i, c in enumerate(counts):
            struct.pack_into("<H", pkt, 13 + i * 2, int(c) & 0xFFFF)
        return bytes(pkt)

    def port_bytes(n, pattern, level, blackout):
        n = max(0, int(n))
        if n <= 0:
            return b""
        if blackout:
            return bytes(n * 3)
        level = max(0, min(255, int(level)))
        out = bytearray()
        third = max(1, n // 3)
        for i in range(n):
            if pattern == "solid_red":
                rgb = (level, 0, 0)
            elif pattern == "solid_green":
                rgb = (0, level, 0)
            elif pattern == "solid_blue":
                rgb = (0, 0, level)
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

    try:
        ip = str(_cell(ctrl, "ip")).strip()
        universe = int(_cell(ctrl, "universe"))
        level = int(_cell(ctrl, "level"))
        blackout = int(_cell(ctrl, "blackout")) == 1
        mode = str(_cell(ctrl, "recv_mode") or "split").strip().lower()
        v0 = max(0, int(_cell(ctrl, "a0_virtual")))
        v1 = max(0, int(_cell(ctrl, "a1_virtual")))
        p0 = str(_cell(ctrl, "a0_pattern") or "thirds").strip()
        p1 = str(_cell(ctrl, "a1_pattern") or "thirds").strip()
        a0_type = str(_cell(ctrl, "a0_type") or "small_grid").strip()
        a1_type = str(_cell(ctrl, "a1_type") or "long_strip").strip()
        phys = {"small_grid": 32, "long_strip": 72, "short_strip": 30,
                "grid": 64, "extra_long_strip": 122, "none": 0}
        v0 = min(v0, phys.get(a0_type, v0))
        v1 = min(v1, phys.get(a1_type, v1))
    except Exception as e:
        print("[phase3] controls read failed:", e)
        scriptOp.clear()
        return

    if mode == "combined" and (v0 + v1) > 170:
        if int(scriptOp.fetch("cook_n", 0)) % 120 == 0:
            print("[phase3] combined virt total", v0 + v1, "> 170 - skip")
        scriptOp.clear()
        return

    now = time.time()
    cook_n = int(scriptOp.fetch("cook_n", 0)) + 1
    scriptOp.store("cook_n", cook_n)

    sock = scriptOp.fetch("udp_sock", None)
    if sock is None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        scriptOp.store("udp_sock", sock)

    # Queue virt push on change; send after debounce (NVS-safe)
    pending = scriptOp.fetch("pending_virt", None)
    last_pushed = scriptOp.fetch("virt_key", None)
    desired = (v0, v1)
    if desired != last_pushed:
        if pending != desired:
            scriptOp.store("pending_virt", desired)
            scriptOp.store("pending_virt_t", now)
            pending = desired
        ready_t = float(scriptOp.fetch("pending_virt_t", now))
        if pending == desired and (now - ready_t) >= VIRT_DEBOUNCE:
            try:
                sock.sendto(art_virtual([v0, v1]), (ip, ARTNET_PORT))
                scriptOp.store("virt_key", desired)
                scriptOp.store("last_virt_push", [v0, v1])
                scriptOp.store("pending_virt", None)
                # Sync devices only when virt actually pushed
                devices = root.op("devices")
                if devices is not None:
                    devices["a0_virtual", 1] = str(v0)
                    devices["a1_virtual", 1] = str(v1)
            except Exception as e:
                print("[phase3] ArtVirtualResolution push failed:", e)

    last_send = float(scriptOp.fetch("last_send_t", 0.0))
    if (now - last_send) < SEND_INTERVAL:
        scriptOp.clear()
        return
    scriptOp.store("last_send_t", now)

    a0 = port_bytes(v0, p0, level, blackout)
    a1 = port_bytes(v1, p1, level, blackout)
    seq = (cook_n % 255) + 1
    packets = []
    try:
        if mode == "combined":
            sock.sendto(art_dmx(universe, a0 + a1, seq), (ip, ARTNET_PORT))
            packets.append({"universe": universe, "payload_len": len(a0) + len(a1)})
        else:
            if v0 > 0:
                sock.sendto(art_dmx(universe, a0, seq), (ip, ARTNET_PORT))
                packets.append({"universe": universe, "payload_len": len(a0)})
            if v1 > 0:
                sock.sendto(art_dmx(universe + 1, a1, seq), (ip, ARTNET_PORT))
                packets.append({"universe": universe + 1, "payload_len": len(a1)})
    except Exception as e:
        print("[phase3] UDP failed:", e)
        try:
            scriptOp.store("udp_sock", None)
            sock.close()
        except Exception:
            pass
        scriptOp.clear()
        return

    # Rare diag heartbeat (avoid disk thrash)
    if cook_n % 90 == 0:
        try:
            import json
            from pathlib import Path
            diag = {
                "phase": 3,
                "live": True,
                "cook_n": cook_n,
                "ip": ip,
                "recv_mode": mode,
                "a0_virtual": v0,
                "a1_virtual": v1,
                "a0_pattern": p0,
                "a1_pattern": p1,
                "level": level,
                "blackout": blackout,
                "packets": packets,
                "last_virt_push": scriptOp.fetch("last_virt_push", None),
            }
            Path(project.folder, "builders", ".td_phase3_diag.json").write_text(
                json.dumps(diag, indent=2) + "\n", encoding="utf-8"
            )
        except Exception:
            pass

    scriptOp.clear()


def _cell(table, key):
    cell = table[key, 1]
    try:
        return cell.val
    except Exception:
        return cell
'''


def _silence_prior():
    for name in ("primus_phase1", "primus_phase2"):
        try:
            node = td_op(f"/project1/{name}")
            if node is None:
                continue
            ctrl = node.op("controls")
            if ctrl is None:
                continue
            for r in range(1, ctrl.numRows):
                if ctrl[r, 0].val == "active":
                    ctrl[r, 1] = "0"
                    print(f"[phase3] silenced {name} (active=0)")
                    break
            # Also stop any script CHOP cookalways if present
            sch = node.op("artnet_cook")
            if sch is not None:
                try:
                    sch.par.cookalways = False
                except Exception:
                    pass
        except Exception as exc:
            print(f"[phase3] could not silence {name}: {exc}")


def _udp_send(ip: str, packet: bytes) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(packet, (ip, ARTNET_PORT))
        return True
    except OSError as exc:
        print(f"[phase3] UDP send failed: {exc}")
        return False
    finally:
        sock.close()


def _port_bytes(n_virtual: int, pattern: str, level: int) -> bytes:
    if n_virtual <= 0:
        return b""
    level = max(0, min(255, int(level)))
    out = bytearray()
    third = max(1, n_virtual // 3)
    for i in range(n_virtual):
        if pattern == "solid_red":
            rgb = (level, 0, 0)
        elif pattern == "solid_green":
            rgb = (0, level, 0)
        elif pattern == "solid_blue":
            rgb = (0, 0, level)
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


def build(
    parent_path: str = PARENT_PATH,
    device_ip: str = "192.168.8.166",
    universe: int = 0,
    a0_type: str = "small_grid",
    a1_type: str = "long_strip",
    a0_virtual: int = None,
    a1_virtual: int = None,
    a0_pattern: str = "thirds",
    a1_pattern: str = "thirds",
    level: int = 64,
    recv_mode: str = "split",
):
    prepare_build(globals())
    _silence_prior()

    mode = (recv_mode or "split").lower()
    if mode not in ("split", "combined"):
        raise ValueError(f"recv_mode must be split|combined, got {mode!r}")

    if a0_virtual is None:
        v0 = physical_pixels(a0_type) if mode == "split" else default_virtual(a0_type)
    else:
        v0 = int(a0_virtual)
    if a1_virtual is None:
        v1 = physical_pixels(a1_type) if mode == "split" else default_virtual(a1_type)
    else:
        v1 = int(a1_virtual)

    v0 = max(0, min(v0, physical_pixels(a0_type)))
    v1 = max(0, min(v1, physical_pixels(a1_type)))

    if mode == "combined":
        ok, total, msg = validate_combined(v0, v1)
        if not ok:
            raise ValueError(f"{msg} (A0 virt={v0} + A1 virt={v1})")
    else:
        total = v0 + v1
        msg = "split ok"

    level = max(0, min(255, int(level)))
    ip = device_ip
    univ = int(universe)

    # Push output types + receive mode + virtual before first ArtDmx
    for label, pkt in (
        ("ArtOutputConfig", build_output_config([a0_type, a1_type])),
        ("ArtReceiveConfig", build_receive_config(mode, univ)),
        ("ArtVirtualResolution", build_virtual_resolution([v0, v1])),
    ):
        if _udp_send(ip, pkt):
            print(f"[phase3] pushed {label}")
        time.sleep(0.05)

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    # Keep clear of PrimusControl (0,0) / PrimusBridge (400,0)
    place(base, 0, -400)
    try:
        siblings = [c.name for c in td_op(parent_path).children]
        print(f"[phase3] /project1 children: {siblings}")
    except Exception:
        pass

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
        ("a0_physical", str(physical_pixels(a0_type))),
        ("a1_physical", str(physical_pixels(a1_type))),
        ("combined_max", str(COMBINED_RECEIVE_MAX_PIXELS)),
        ("semantics", "virt=N means send N RGB; device upsamples to physical"),
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
        ("a0_type", a0_type),
        ("a1_type", a1_type),
        ("ip", ip),
        ("universe", str(univ)),
        ("recv_mode", mode),
    ):
        ctrl.appendRow([k, v])

    # Primary live sender: Script CHOP + callbacks DAT (cooks every frame)
    cb = create_child(base, "textDAT", "artnet_callbacks")
    place(cb, 0, 0)
    cb.text = _SCRIPT_CHOP

    cook = create_child(base, "scriptCHOP", "artnet_cook")
    place(cook, 200, 0)
    try:
        cook.par.callbacks = cb
    except Exception:
        try:
            set_par(cook, callbacks=cb.path)
        except Exception as exc:
            print(f"[phase3] callbacks wire failed: {exc}")
    # If TD auto-docked a different callbacks DAT, overwrite that too
    try:
        docked = cook.par.callbacks.eval()
        if docked is not None and hasattr(docked, "text"):
            docked.text = _SCRIPT_CHOP
    except Exception:
        pass
    try:
        cook.cook(force=True)
    except Exception as exc:
        print(f"[phase3] force cook: {exc}")

    # Immediate first frame from build process
    a0 = _port_bytes(v0, a0_pattern, level)
    a1 = _port_bytes(v1, a1_pattern, level)
    sent = True
    packets = []
    if mode == "combined":
        sent = _udp_send(ip, build_art_dmx(univ, a0 + a1, 1)) and sent
        packets.append({"universe": univ, "payload_len": len(a0) + len(a1)})
    else:
        if v0 > 0:
            sent = _udp_send(ip, build_art_dmx(univ, a0, 1)) and sent
            packets.append({"universe": univ, "payload_len": len(a0)})
        if v1 > 0:
            sent = _udp_send(ip, build_art_dmx(univ + 1, a1, 1)) and sent
            packets.append({"universe": univ + 1, "payload_len": len(a1)})

    diag = {
        "phase": 3,
        "live": False,
        "ip": ip,
        "recv_mode": mode,
        "a0_virtual": v0,
        "a1_virtual": v1,
        "a0_pattern": a0_pattern,
        "a1_pattern": a1_pattern,
        "level": level,
        "packets": packets,
        "immediate_send": sent,
        "note": "edit controls.a0_virtual / a1_virtual; expect upsample not zero-pad",
    }
    try:
        folder = Path(project.folder)  # noqa: F821
    except Exception:
        folder = Path(__file__).resolve().parents[1]
    (folder / "builders" / ".td_phase3_diag.json").write_text(
        json.dumps(diag, indent=2) + "\n", encoding="utf-8"
    )

    info = create_child(base, "textDAT", "README")
    place(info, 0, 400)
    info.text = (
        "Phase 3 - live virtual resolution\n"
        "Edit controls.a0_virtual / a1_virtual (NOT just devices).\n"
        "virt=N => send N RGB values; device spreads them across physical LEDs.\n"
        "virt=1 => entire output one color.\n"
        f"Current: A0={v0} ({a0_pattern}) A1={v1} ({a1_pattern}) mode={mode}\n"
        "See handoffs/phase3_test.md\n"
    )

    print(f"[phase3] built {base.path} mode={mode} A0={v0} A1={v1} send={sent}")
    if not sent:
        raise RuntimeError("phase3 UDP ArtDmx send failed")
    return base
