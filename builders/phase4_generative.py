"""
Phase 4 - media sampling and Primus ArtDmx packaging.

Each output selects demo gradient, Movie File In, or an external TOP.  The
selected field is sampled geometrically (point, line, ROI, or fit) into RGB
triplets and sent via the Phase 3 virtual-resolution ArtDmx path.

    python3 builders/td_remote.py build 4 --recv-mode split \
      --a0-virtual 1 --a1-virtual 72 --level 64 --bind-ip 192.168.8.199
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
    from builders.lib.output_types import default_virtual, physical_pixels, validate_combined
    from builders.lib.packets import (
        ARTNET_PORT,
        build_art_dmx,
        build_output_config,
        build_receive_config,
        build_virtual_resolution,
    )
    from builders.lib.td_builder import (
        create_child, ensure_base, init_device_table, place, prepare_build, set_par, td_op,
    )
except ImportError:
    ARTNET_PORT = 6454


PARENT_PATH = "/project1"
BASE_NAME = "primus_phase4"


# Self-contained to avoid import/path failures in TD Script CHOP callbacks.
_SENDER_CALLBACKS = r'''
def onGetCookLevel(scriptOp):
    try:
        return CookLevel.ALWAYS
    except Exception:
        return 3


def _cell(table, key, default=""):
    try:
        value = table[key, 1]
        return value.val if hasattr(value, "val") else value
    except Exception:
        return default


def onCook(scriptOp):
    import socket, struct, time
    root = scriptOp.parent()
    ctrl = root.op("controls")
    if ctrl is None or str(_cell(ctrl, "active", "0")) != "1":
        scriptOp.clear()
        return

    def clamp(x):
        return max(0.0, min(1.0, float(x)))

    def number(key, default):
        try:
            return float(_cell(ctrl, key, default))
        except Exception:
            return default

    def integer(key, default):
        try:
            return int(float(_cell(ctrl, key, default)))
        except Exception:
            return default

    def art_dmx(universe, payload, sequence):
        data = bytes(payload)
        if len(data) % 2:
            data += b"\x00"
        return (b"Art-Net\x00" + struct.pack("<H", 0x5000) +
                struct.pack(">H", 14) + bytes([sequence & 255, 0]) +
                struct.pack("<H", universe & 0xffff) +
                struct.pack(">H", len(data)) + data)

    def art_virtual(counts):
        pkt = bytearray(13 + len(counts) * 2)
        pkt[:8] = b"Art-Net\x00"
        struct.pack_into("<H", pkt, 8, 0x8130)
        struct.pack_into(">H", pkt, 10, 14)
        pkt[12] = len(counts)
        for i, count in enumerate(counts):
            struct.pack_into("<H", pkt, 13 + i * 2, int(count) & 0xffff)
        return bytes(pkt)

    def sample(arr, n, prefix, level):
        """Nearest-neighbour media sampler; returns n RGB bytes."""
        n = max(0, int(n))
        if n == 0 or arr is None:
            return bytes(n * 3)
        try:
            h, w = int(arr.shape[0]), int(arr.shape[1])
            if h < 1 or w < 1 or int(arr.shape[2]) < 3:
                return bytes(n * 3)
            as_byte = float(arr[:, :, :3].max()) > 1.5
        except Exception:
            return bytes(n * 3)
        mode = str(_cell(ctrl, prefix + "_sample_mode", "hline")).strip().lower()
        u, v = clamp(number(prefix + "_u", 0.0)), clamp(number(prefix + "_v", .5))
        u1, v1 = clamp(number(prefix + "_u1", 1.0)), clamp(number(prefix + "_v1", .5))
        ru, rv = clamp(number(prefix + "_roi_u", 0.0)), clamp(number(prefix + "_roi_v", 0.0))
        rw, rh = max(1e-6, number(prefix + "_roi_w", 1.0)), max(1e-6, number(prefix + "_roi_h", 1.0))
        rw, rh = min(rw, 1.0 - ru), min(rh, 1.0 - rv)
        scale = max(0, min(255, int(level))) / 255.0
        out = bytearray()

        def t_at(i):
            return .5 if n == 1 else i / float(n - 1)
        def emit(x, y):
            xi = min(w - 1, max(0, int(clamp(x) * (w - 1) + .5)))
            yi = min(h - 1, max(0, int(clamp(y) * (h - 1) + .5)))
            pix = arr[yi, xi]
            mul = scale if as_byte else 255.0 * scale
            out.extend(max(0, min(255, int(float(pix[c]) * mul))) for c in range(3))

        if mode == "point":
            for _ in range(n): emit(u, v)
        elif mode == "vline":
            for i in range(n): emit(ru + u * rw, rv + t_at(i) * rh)
        elif mode == "line":
            for i in range(n):
                t = t_at(i); emit(u + (u1 - u) * t, v + (v1 - v) * t)
        elif mode in ("fit", "roi_fit"):
            # Phase 4 uses a one-dimensional output lattice by default.
            for i in range(n): emit(ru + t_at(i) * rw, rv + .5 * rh)
        else:  # hline and unknown modes
            for i in range(n): emit(ru + t_at(i) * rw, rv + v * rh)
        return bytes(out)

    ip = str(_cell(ctrl, "device_ip", _cell(ctrl, "ip", ""))).strip()
    bind_ip = str(_cell(ctrl, "bind_ip", "")).strip()
    universe = integer("universe", 0)
    level = integer("level", 64)
    fps = max(1.0, number("send_fps", 30.0))
    mode = str(_cell(ctrl, "recv_mode", "split")).strip().lower()
    types = {"small_grid": 32, "long_strip": 72, "short_strip": 30, "grid": 64, "extra_long_strip": 122, "none": 0}
    a0_type, a1_type = str(_cell(ctrl, "a0_type", "small_grid")), str(_cell(ctrl, "a1_type", "long_strip"))
    v0 = max(0, min(integer("a0_virtual", 1), types.get(a0_type, 9999)))
    v1 = max(0, min(integer("a1_virtual", 72), types.get(a1_type, 9999)))
    if not ip or (mode == "combined" and v0 + v1 > 170):
        scriptOp.clear()
        return

    # Drive selection and movie paths live from controls.
    for prefix in ("a0", "a1"):
        source = max(0, min(2, integer(prefix + "_src", 0)))
        switch, movie = root.op(prefix + "_select"), root.op(prefix + "_movie_in")
        try: switch.par.index = source
        except Exception: pass
        try: movie.par.file = str(_cell(ctrl, prefix + "_movie", ""))
        except Exception: pass

    now = time.time()
    last = float(scriptOp.fetch("last_send_t", 0.0))
    if now - last < 1.0 / fps:
        scriptOp.clear()
        return
    scriptOp.store("last_send_t", now)
    sock = scriptOp.fetch("udp_sock", None)
    if sock is None or scriptOp.fetch("udp_bind", None) != bind_ip:
        try:
            if sock: sock.close()
        except Exception: pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if bind_ip:
            try: sock.bind((bind_ip, 0))
            except OSError as exc: print("[phase4] bind_ip failed:", exc)
        scriptOp.store("udp_sock", sock); scriptOp.store("udp_bind", bind_ip)

    desired, pushed = (v0, v1), scriptOp.fetch("virt_key", None)
    pending = scriptOp.fetch("pending_virt", None)
    if desired != pushed:
        if pending != desired:
            scriptOp.store("pending_virt", desired); scriptOp.store("pending_virt_t", now)
        elif now - float(scriptOp.fetch("pending_virt_t", now)) >= .35:
            try:
                sock.sendto(art_virtual(desired), (ip, 6454))
                scriptOp.store("virt_key", desired); scriptOp.store("pending_virt", None)
            except Exception as exc: print("[phase4] virtual send failed:", exc)

    blackout = str(_cell(ctrl, "blackout", "0")) == "1"
    try:
        a0 = bytes(v0 * 3) if blackout else sample(root.op("a0_media").numpyArray(), v0, "a0", level)
        a1 = bytes(v1 * 3) if blackout else sample(root.op("a1_media").numpyArray(), v1, "a1", level)
    except Exception as exc:
        print("[phase4] media sample failed:", exc); a0, a1 = bytes(v0 * 3), bytes(v1 * 3)
    scriptOp.store("a0_rgb", a0); scriptOp.store("a1_rgb", a1)
    sequence = (int(scriptOp.fetch("sequence", 0)) % 255) + 1
    scriptOp.store("sequence", sequence)
    packets = []
    try:
        if mode == "combined":
            sock.sendto(art_dmx(universe, a0 + a1, sequence), (ip, 6454))
            packets.append({"universe": universe, "payload_len": len(a0) + len(a1)})
        else:
            if v0: sock.sendto(art_dmx(universe, a0, sequence), (ip, 6454)); packets.append({"universe": universe, "payload_len": len(a0)})
            if v1: sock.sendto(art_dmx(universe + 1, a1, sequence), (ip, 6454)); packets.append({"universe": universe + 1, "payload_len": len(a1)})
    except Exception as exc: print("[phase4] ArtDmx send failed:", exc)
    if sequence % 90 == 0:
        try:
            from pathlib import Path
            import json
            Path(project.folder, "builders", ".td_phase4_diag.json").write_text(json.dumps({
                "phase": 4, "live": True, "ip": ip, "bind_ip": bind_ip or None,
                "recv_mode": mode, "a0_virtual": v0, "a1_virtual": v1, "level": level,
                "a0_mode": _cell(ctrl, "a0_sample_mode"), "a1_mode": _cell(ctrl, "a1_sample_mode"),
                "packets": packets, "a0_first_rgb": list(a0[:3]), "a1_first_rgb": list(a1[:3]),
            }, indent=2) + "\n")
        except Exception: pass
    scriptOp.clear()
'''

_GRADIENT_CALLBACKS = r'''
def onCook(scriptOp):
    import numpy as np
    w, h = max(64, int(scriptOp.par.resolutionw)), max(16, int(scriptOp.par.resolutionh))
    t = absTime.seconds * float(scriptOp.fetch("speed", .25))
    x = (np.arange(w, dtype=np.float32) / w + t) % 1.0
    arr = np.zeros((h, w, 4), dtype=np.float32)
    arr[:, :, 0] = .5 + .5 * np.sin(6.283 * (x + .00))
    arr[:, :, 1] = .5 + .5 * np.sin(6.283 * (x + .33))
    arr[:, :, 2] = .5 + .5 * np.sin(6.283 * (x + .66))
    arr[:, :, 3] = 1
    scriptOp.copyNumpyArray(arr)
'''

_STRIP_CALLBACKS = r'''
def onCook(scriptOp):
    import numpy as np
    prefix = scriptOp.fetch("prefix", "a0")
    sender = scriptOp.parent().op("artnet_cook")
    payload = sender.fetch(prefix + "_rgb", b"") if sender else b""
    n = max(1, len(payload) // 3)
    arr = np.zeros((1, n, 4), dtype=np.float32)
    for i in range(min(n, len(payload) // 3)):
        arr[0, i, :3] = [payload[i * 3] / 255., payload[i * 3 + 1] / 255., payload[i * 3 + 2] / 255.]
    arr[:, :, 3] = 1
    scriptOp.copyNumpyArray(arr)
'''


def _udp_send(ip, packet, bind_ip=None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if bind_ip:
            sock.bind((bind_ip, 0))
        sock.sendto(packet, (ip, ARTNET_PORT))
        return True
    except OSError as exc:
        print(f"[phase4] UDP send failed: {exc}")
        return False
    finally:
        sock.close()


def _force_res(top, width, height):
    for key, value in (("outputresolution", "custom"), ("resolution", "custom")):
        try:
            setattr(top.par, key, value)
            break
        except Exception:
            pass
    for key, value in (("resolutionw", width), ("resolutionh", height)):
        try:
            setattr(top.par, key, value)
        except Exception:
            pass


def _viewer(base, name, source, x, y, width=360, height=80, nearest=False):
    node = create_child(base, "resolutionTOP", name)
    place(node, x, y)
    _force_res(node, width, height)
    try:
        node.inputConnectors[0].connect(source)
        if nearest:
            node.par.filtertype = "nearest"
        node.viewer = True
    except Exception:
        pass
    return node


def _media_branch(base, prefix, x, y, speed):
    grad_cb = create_child(base, "textDAT", f"{prefix}_demo_cb")
    grad_cb.text = _GRADIENT_CALLBACKS
    place(grad_cb, x, y + 120)
    demo = create_child(base, "scriptTOP", f"{prefix}_demo")
    place(demo, x, y)
    set_par(demo, callbacks=grad_cb.path)
    _force_res(demo, 512, 96)
    demo.store("speed", speed)

    movie = create_child(base, "moviefileinTOP", f"{prefix}_movie_in")
    place(movie, x + 180, y)
    external = create_child(base, "nullTOP", f"{prefix}_ext")
    place(external, x + 360, y)
    select = create_child(base, "switchTOP", f"{prefix}_select")
    place(select, x + 560, y)
    for index, source in enumerate((demo, movie, external)):
        try:
            select.inputConnectors[index].connect(source)
        except Exception:
            pass
    media = create_child(base, "nullTOP", f"{prefix}_media")
    place(media, x + 740, y)
    try:
        media.inputConnectors[0].connect(select)
        media.viewer = True
    except Exception:
        pass
    _viewer(base, f"{prefix}_viz_src", media, x + 920, y, 360, 90)

    strip_cb = create_child(base, "textDAT", f"{prefix}_strip_cb")
    strip_cb.text = _STRIP_CALLBACKS
    strip = create_child(base, "scriptTOP", f"{prefix}_strip")
    place(strip, x + 920, y - 140)
    set_par(strip, callbacks=strip_cb.path)
    _force_res(strip, 72, 1)
    strip.store("prefix", prefix)
    _viewer(base, f"{prefix}_viz_send", strip, x + 1100, y - 140, 360, 90, nearest=True)


def _silence_prior():
    for name in ("primus_phase1", "primus_phase2", "primus_phase3"):
        try:
            ctrl = td_op(f"/project1/{name}").op("controls")
            ctrl["active", 1] = "0"
        except Exception:
            pass


def build(
    parent_path=PARENT_PATH, device_ip="192.168.8.166", universe=0,
    a0_type="small_grid", a1_type="long_strip", a0_virtual=None, a1_virtual=None,
    level=64, recv_mode="split", bind_ip="192.168.8.199", **_ignored,
):
    prepare_build(globals())
    _silence_prior()
    mode = (recv_mode or "split").lower()
    if mode not in ("split", "combined"):
        raise ValueError("recv_mode must be split|combined")
    v0 = default_virtual(a0_type) if a0_virtual is None else int(a0_virtual)
    v1 = default_virtual(a1_type) if a1_virtual is None else int(a1_virtual)
    v0, v1 = max(0, min(v0, physical_pixels(a0_type))), max(0, min(v1, physical_pixels(a1_type)))
    if mode == "combined" and not validate_combined(v0, v1)[0]:
        raise ValueError("combined virtual resolution exceeds 170")
    level, bind_ip = max(0, min(255, int(level))), (bind_ip or "").strip()
    for label, packet in (
        ("ArtOutputConfig", build_output_config([a0_type, a1_type])),
        ("ArtReceiveConfig", build_receive_config(mode, int(universe))),
        ("ArtVirtualResolution", build_virtual_resolution([v0, v1])),
    ):
        _udp_send(device_ip, packet, bind_ip or None)
        print(f"[phase4] pushed {label}")
        time.sleep(.05)

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 0, -400)
    devices = create_child(base, "tableDAT", "devices")
    place(devices, 0, 400)
    init_device_table(devices, [{"name": "test", "ip": device_ip, "universe": str(universe),
        "recv_mode": mode, "a0_type": a0_type, "a0_count": str(physical_pixels(a0_type)),
        "a0_virtual": str(v0), "a1_type": a1_type, "a1_count": str(physical_pixels(a1_type)),
        "a1_virtual": str(v1), "group": "default"}])
    controls = create_child(base, "tableDAT", "controls")
    place(controls, 250, 400)
    controls.appendRow(["param", "value"])
    values = [
        ("active", "1"), ("blackout", "0"), ("device_ip", device_ip), ("ip", device_ip),
        ("bind_ip", bind_ip), ("universe", str(universe)), ("recv_mode", mode),
        ("level", str(level)), ("send_fps", "30"), ("a0_type", a0_type), ("a1_type", a1_type),
        ("a0_virtual", str(v0)), ("a1_virtual", str(v1)),
    ]
    for prefix, virt, sample_mode in (("a0", v0, "point"), ("a1", v1, "hline")):
        values += [
            (prefix + "_src", "0"), (prefix + "_movie", ""), (prefix + "_sample_mode", sample_mode),
            (prefix + "_u", "0.5"), (prefix + "_v", "0.5"), (prefix + "_u1", "1.0"), (prefix + "_v1", "0.5"),
            (prefix + "_roi_u", "0"), (prefix + "_roi_v", "0"), (prefix + "_roi_w", "1"), (prefix + "_roi_h", "1"),
        ]
    for row in values:
        controls.appendRow(row)
    _media_branch(base, "a0", 0, 180, .20)
    _media_branch(base, "a1", 0, -180, .33)
    callbacks = create_child(base, "textDAT", "artnet_callbacks")
    callbacks.text = _SENDER_CALLBACKS
    place(callbacks, 0, 600)
    sender = create_child(base, "scriptCHOP", "artnet_cook")
    place(sender, 220, 600)
    set_par(sender, callbacks=callbacks.path)
    try:
        sender.cook(force=True)
    except Exception as exc:
        print("[phase4] first sender cook:", exc)
    _udp_send(device_ip, build_art_dmx(int(universe), bytes(max(3, v0 * 3)), 1), bind_ip or None)
    _udp_send(device_ip, build_art_dmx(int(universe) + 1, bytes(max(3, v1 * 3)), 1), bind_ip or None)
    folder = Path(project.folder) if "project" in globals() else Path(__file__).resolve().parents[1]
    (folder / "builders" / ".td_phase4_diag.json").write_text(json.dumps({
        "phase": 4, "live": False, "ip": device_ip, "bind_ip": bind_ip or None,
        "recv_mode": mode, "a0_virtual": v0, "a1_virtual": v1, "level": level,
        "note": "sample any TOP through a*_ext; controls select source and geometry",
    }, indent=2) + "\n", encoding="utf-8")
    readme = create_child(base, "textDAT", "README")
    place(readme, 500, 600)
    readme.text = (
        "Phase 4 — media sampling → Primus ArtDmx\n"
        "Wire any TOP to a0_ext or a1_ext; set a*_src=2.  a*_src: 0 demo, 1 movie, 2 ext.\n"
        "Set a*_sample_mode: fit, roi_fit, hline, vline, line, point.  "
        "Use u/v/u1/v1 and roi_u/roi_v/roi_w/roi_h (all normalized 0..1).\n"
        "a*_viz_src is selected media; a*_viz_send is the RGB payload strip.\n"
    )
    print(f"[phase4] built {base.path}: media sampler A0={v0} A1={v1} {mode}")
    return base
