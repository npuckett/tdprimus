"""Phase 5 — table-driven, simultaneous Phase-4-style Primus outputs."""

from __future__ import annotations

import json
import socket
import sys
import time


def _bootstrap():
    try:
        root = project.folder  # noqa: F821
    except NameError:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)


_bootstrap()

from builders.lib.output_types import default_virtual, physical_pixels, validate_combined  # noqa: E402
from builders.lib.packets import build_output_config, build_receive_config, build_virtual_resolution  # noqa: E402
from builders.lib.td_builder import create_child, ensure_base, place, prepare_build, set_par, td_op  # noqa: E402

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase5"
DEVICE_COLS = (
    "name", "active", "ip", "bind_ip", "universe", "recv_mode",
    "a0_type", "a0_count", "a0_virtual", "a1_type", "a1_count", "a1_virtual",
    "a0_source", "a1_source", "group",
)
DEFAULT_ROWS = [
    {"name": "primus_a", "active": "1", "ip": "192.168.8.166", "bind_ip": "192.168.8.199",
     "universe": "0", "recv_mode": "split", "a0_type": "small_grid", "a0_count": "32",
     "a0_virtual": "1", "a1_type": "long_strip", "a1_count": "72", "a1_virtual": "72",
     "a0_source": "demo", "a1_source": "demo", "group": "default"},
    {"name": "primus_b", "active": "1", "ip": "192.168.8.164", "bind_ip": "192.168.8.199",
     "universe": "0", "recv_mode": "split", "a0_type": "small_grid", "a0_count": "32",
     "a0_virtual": "1", "a1_type": "long_strip", "a1_count": "72", "a1_virtual": "72",
     # Distinct SharedMedia bus so the second receiver is visually different.
     "a0_source": "alt", "a1_source": "alt", "group": "default"},
]

_GRADIENT_CALLBACKS = r'''
def onCook(scriptOp):
    import numpy as np
    w, h = max(64, int(scriptOp.par.resolutionw)), max(16, int(scriptOp.par.resolutionh))
    t = absTime.seconds * float(scriptOp.fetch("speed", .25))
    phase = float(scriptOp.fetch("phase", 0))
    x = (np.arange(w, dtype=np.float32) / w + t + phase) % 1.0
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
    count = max(1, len(payload) // 3)
    arr = np.zeros((1, count, 4), dtype=np.float32)
    for i in range(min(count, len(payload) // 3)):
        arr[0, i, :3] = [payload[i * 3] / 255., payload[i * 3 + 1] / 255., payload[i * 3 + 2] / 255.]
    arr[:, :, 3] = 1
    scriptOp.copyNumpyArray(arr)
'''

# Script CHOP/TOP cookalways is unreliable across TD builds. Frame-start
# force-cook keeps ArtDmx and demo gradients alive without open viewers.
_FRAME_COOK = r'''
def onFrameStart(frame):
    sender = me.parent().op("artnet_cook")
    if sender is None:
        return
    try:
        sender.cook(force=True)
    except Exception:
        pass
'''

_MEDIA_FRAME_COOK = r'''
def onFrameStart(frame):
    parent = me.parent()
    for name in ("bus_a0_demo", "bus_a1_demo", "bus_a0_alt", "bus_a1_alt"):
        top = parent.op(name)
        if top is None:
            continue
        try:
            top.cook(force=True)
        except Exception:
            pass
'''

# Per-device default look so two receivers sharing the bus are obviously distinct.
_DEVICE_LOOKS = (
    {  # primus_a / index 0 — demo bus, mid-line sample
        "a0_u": ".35", "a0_v": ".35", "a1_u": ".0", "a1_v": ".35",
        "a1_u1": "1", "a1_v1": ".35", "hue_shift": "0",
    },
    {  # primus_b / index 1 — alt bus, opposite line + hue rotate
        "a0_u": ".75", "a0_v": ".75", "a1_u": ".0", "a1_v": ".75",
        "a1_u1": "1", "a1_v1": ".75", "hue_shift": ".45",
    },
)

_SENDER_CALLBACKS = r'''
def onGetCookLevel(scriptOp):
    try: return CookLevel.ALWAYS
    except Exception: return 3

def _cell(table, key, default=""):
    try:
        value = table[key, 1]
        return value.val if hasattr(value, "val") else value
    except Exception: return default

def _set_link(root, rows):
    link = root.op("link")
    if link is None: return
    try:
        link.clear(); link.appendRow(["param", "value"])
        for key, value in rows: link.appendRow([str(key), str(value)])
    except Exception: pass

def onCook(scriptOp):
    import socket, struct, time, json
    from pathlib import Path
    root = scriptOp.parent()
    profile, sample = root.op("profile"), root.op("sampling")
    if profile is None or sample is None or str(_cell(profile, "active", "0")) != "1":
        _set_link(root, [("state", "inactive"), ("last_error", scriptOp.fetch("last_error", ""))])
        scriptOp.clear(); return
    def integer(table, key, default):
        try: return int(float(_cell(table, key, default)))
        except Exception: return default
    def number(key, default):
        try: return float(_cell(sample, key, default))
        except Exception: return default
    def clamp(x): return max(0., min(1., float(x)))
    def dmx(universe, payload, sequence):
        data = bytes(payload) + (b"\0" if len(payload) % 2 else b"")
        return b"Art-Net\0" + struct.pack("<H", 0x5000) + struct.pack(">H", 14) + bytes([sequence & 255, 0]) + struct.pack("<H", universe & 65535) + struct.pack(">H", len(data)) + data
    def virt(counts):
        pkt = bytearray(17); pkt[:8] = b"Art-Net\0"; struct.pack_into("<H", pkt, 8, 0x8130); struct.pack_into(">H", pkt, 10, 14); pkt[12] = 2
        struct.pack_into("<H", pkt, 13, counts[0]); struct.pack_into("<H", pkt, 15, counts[1]); return bytes(pkt)
    def out_cfg(types):
        ids = {"none":0,"short_strip":1,"long_strip":2,"grid":3,"small_grid":4,"extra_long_strip":5}
        pkt = bytearray(15); pkt[:8] = b"Art-Net\0"; struct.pack_into("<H", pkt, 8, 0x8100); struct.pack_into(">H", pkt, 10, 14); pkt[12] = 2
        pkt[13] = ids.get(types[0], 0); pkt[14] = ids.get(types[1], 0); return bytes(pkt)
    def recv_cfg(mode, universe):
        pkt = bytearray(15); pkt[:8] = b"Art-Net\0"; struct.pack_into("<H", pkt, 8, 0x8110); struct.pack_into(">H", pkt, 10, 14)
        pkt[12] = 1 if mode == "combined" else 0; struct.pack_into("<H", pkt, 13, universe & 65535); return bytes(pkt)
    def rgb(arr, n, prefix):
        """Sample media to full 0..255 RGB; brightness is applied after packing."""
        if arr is None or n <= 0: return bytes(max(0, n) * 3)
        try: h, w = int(arr.shape[0]), int(arr.shape[1]); as_byte = float(arr[:, :, :3].max()) > 1.5
        except Exception: return bytes(n * 3)
        mode = str(_cell(sample, prefix + "_sample_mode", "hline")).lower()
        u, v = clamp(number(prefix + "_u", .5)), clamp(number(prefix + "_v", .5))
        u1, v1 = clamp(number(prefix + "_u1", 1)), clamp(number(prefix + "_v1", .5))
        ru, rv = clamp(number(prefix + "_roi_u", 0)), clamp(number(prefix + "_roi_v", 0))
        rw, rh = min(max(1e-6, number(prefix + "_roi_w", 1)), 1-ru), min(max(1e-6, number(prefix + "_roi_h", 1)), 1-rv)
        out = bytearray()
        def emit(x, y):
            pix = arr[min(h-1,max(0,int(clamp(y)*(h-1)+.5))), min(w-1,max(0,int(clamp(x)*(w-1)+.5)))]
            mul = 1.0 if as_byte else 255.0
            out.extend(max(0,min(255,int(float(pix[c])*mul + .5))) for c in range(3))
        for i in range(n):
            t = .5 if n == 1 else i / float(n-1)
            if mode == "point": x, y = u, v
            elif mode == "vline": x, y = ru + u*rw, rv + t*rh
            elif mode == "line": x, y = u + (u1-u)*t, v + (v1-v)*t
            elif mode in ("fit", "roi_fit"): x, y = ru + t*rw, rv + .5*rh
            else: x, y = ru + t*rw, rv + v*rh
            emit(x, y)
        return bytes(out)
    def dim(payload, brightness):
        """Master attenuator on packed bytes (0=off, 1=full). Dim-focused safety control."""
        b = max(0., min(1., float(brightness)))
        if b >= 0.999: return payload
        if b <= 0.001: return bytes(len(payload))
        return bytes(max(0, min(255, int(c * b + .5))) for c in payload)
    def hue_shift(payload, shift):
        """Rotate packed RGB hue so devices can look distinct from the same media family."""
        s = float(shift) % 1.0
        if s < 1e-6 or not payload: return payload
        out = bytearray()
        # Cheap channel rotate by thirds of the hue circle.
        step = int(round(s * 3)) % 3
        for i in range(0, len(payload) - 2, 3):
            rgb = [payload[i], payload[i + 1], payload[i + 2]]
            out.extend([rgb[step % 3], rgb[(step + 1) % 3], rgb[(step + 2) % 3]])
        if len(payload) % 3: out.extend(payload[-(len(payload) % 3):])
        return bytes(out)
    def brightness():
        # Prefer 0..1 brightness; fall back to legacy level 0..255.
        raw = str(_cell(sample, "brightness", "")).strip()
        if raw != "": return clamp(number("brightness", .1))
        return clamp(integer(sample, "level", 26) / 255.)
    def drop_sock(reason):
        """Close UDP, back off, and rate-limit Textport spam while host is down."""
        sock = scriptOp.fetch("udp_sock", None)
        try:
            if sock: sock.close()
        except Exception: pass
        scriptOp.store("udp_sock", None); scriptOp.store("udp_bind", None)
        scriptOp.store("config_key", None); scriptOp.store("force_config", True)
        scriptOp.store("last_error", reason)
        fails = int(scriptOp.fetch("fail_streak", 0)) + 1
        scriptOp.store("fail_streak", fails)
        scriptOp.store("reconnects", int(scriptOp.fetch("reconnects", 0)) + 1)
        # Exponential backoff: 0.5 → 1 → 2 → 4 → 8s (cap).
        delay = min(8.0, 0.5 * (2 ** min(fails - 1, 4)))
        scriptOp.store("retry_after", time.time() + delay)
        # Print first failure, then at most once every 10s for the same reason.
        last_reason = str(scriptOp.fetch("log_reason", ""))
        last_log_t = float(scriptOp.fetch("log_t", 0))
        now_log = time.time()
        if reason != last_reason or (now_log - last_log_t) >= 10.0:
            print("[phase5]", root.name, reason, "(retry in %.1fs)" % delay)
            scriptOp.store("log_reason", reason)
            scriptOp.store("log_t", now_log)
    ip, bind_ip = str(_cell(profile, "ip", "")).strip(), str(_cell(profile, "bind_ip", "")).strip()
    mode, universe = str(_cell(profile, "recv_mode", "split")).lower(), integer(profile, "universe", 0)
    a0_type, a1_type = str(_cell(profile, "a0_type", "small_grid")), str(_cell(profile, "a1_type", "long_strip"))
    types = {"small_grid":32, "long_strip":72, "short_strip":30, "grid":64, "extra_long_strip":122, "none":0}
    v0 = max(0, min(integer(profile, "a0_virtual", 1), types.get(a0_type, 0)))
    v1 = max(0, min(integer(profile, "a1_virtual", 72), types.get(a1_type, 0)))
    if not ip or (mode == "combined" and v0 + v1 > 170):
        _set_link(root, [("state", "skip"), ("last_error", "invalid profile")])
        scriptOp.clear(); return
    now, fps = time.time(), max(1., number("send_fps", 30))
    if now < float(scriptOp.fetch("retry_after", 0)): scriptOp.clear(); return
    if now - float(scriptOp.fetch("last_send_t", 0)) < 1. / fps: scriptOp.clear(); return
    scriptOp.store("last_send_t", now)
    sock = scriptOp.fetch("udp_sock", None)
    if sock is None or scriptOp.fetch("udp_bind", None) != bind_ip:
        try:
            if sock: sock.close()
        except Exception: pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if bind_ip:
            try: sock.bind((bind_ip, 0))
            except OSError as exc:
                drop_sock("bind failed: " + str(exc))
                _set_link(root, [("state", "bind_fail"), ("bind_ip", bind_ip), ("last_error", scriptOp.fetch("last_error", "")), ("reconnects", scriptOp.fetch("reconnects", 0))])
                scriptOp.clear(); return
        scriptOp.store("udp_sock", sock); scriptOp.store("udp_bind", bind_ip)
        scriptOp.store("force_config", True); scriptOp.store("last_error", "")
    config_key = (a0_type, a1_type, mode, universe, v0, v1)
    refresh_s = max(2., number("config_refresh_s", 5))
    need_config = (
        bool(scriptOp.fetch("force_config", True))
        or scriptOp.fetch("config_key", None) != config_key
        or now - float(scriptOp.fetch("last_config_t", 0)) >= refresh_s
    )
    if need_config:
        try:
            sock.sendto(out_cfg((a0_type, a1_type)), (ip, 6454))
            sock.sendto(recv_cfg(mode, universe), (ip, 6454))
            sock.sendto(virt((v0, v1)), (ip, 6454))
            scriptOp.store("config_key", config_key); scriptOp.store("last_config_t", now)
            scriptOp.store("force_config", False); scriptOp.store("last_error", "")
        except Exception as exc:
            drop_sock("config send failed: " + str(exc))
            _set_link(root, [("state", "config_fail"), ("ip", ip), ("last_error", scriptOp.fetch("last_error", "")), ("reconnects", scriptOp.fetch("reconnects", 0))])
            scriptOp.clear(); return
    blackout = str(_cell(sample, "blackout", "0")) == "1" or str(_cell(root.parent().op("controls"), "blackout_all", "0")) == "1"
    # Pull a fresh frame; SharedMedia demos may not cook unless forced.
    for name in ("a0_source", "a1_source", "a0_media", "a1_media"):
        top = root.op(name)
        if top is not None:
            try: top.cook(force=True)
            except Exception: pass
    gain = 0. if blackout else brightness()
    shift = number("hue_shift", 0)
    try:
        a0 = dim(hue_shift(rgb(root.op("a0_media").numpyArray(), v0, "a0"), shift), gain) if v0 else b""
        a1 = dim(hue_shift(rgb(root.op("a1_media").numpyArray(), v1, "a1"), shift), gain) if v1 else b""
    except Exception as exc:
        print("[phase5] sample failed:", exc); a0, a1 = bytes(v0 * 3), bytes(v1 * 3)
    scriptOp.store("a0_rgb", a0); scriptOp.store("a1_rgb", a1); scriptOp.store("brightness", gain)
    seq = (int(scriptOp.fetch("sequence", 0)) % 255) + 1; scriptOp.store("sequence", seq)
    try:
        if mode == "combined": sock.sendto(dmx(universe, a0 + a1, seq), (ip, 6454))
        else:
            if v0: sock.sendto(dmx(universe, a0, seq), (ip, 6454))
            if v1: sock.sendto(dmx(universe + 1, a1, seq), (ip, 6454))
    except Exception as exc:
        drop_sock("ArtDmx send failed: " + str(exc))
        _set_link(root, [("state", "send_fail"), ("ip", ip), ("last_error", scriptOp.fetch("last_error", "")), ("reconnects", scriptOp.fetch("reconnects", 0))])
        scriptOp.clear(); return
    sends = int(scriptOp.fetch("sends", 0)) + 1; scriptOp.store("sends", sends)
    prev_err = str(scriptOp.fetch("last_error", "") or "")
    fail_streak = int(scriptOp.fetch("fail_streak", 0))
    scriptOp.store("last_ok_t", now); scriptOp.store("last_error", "")
    scriptOp.store("fail_streak", 0)
    if fail_streak > 0 or prev_err:
        print("[phase5]", root.name, "recovered →", ip)
        scriptOp.store("log_reason", "")
    _set_link(root, [
        ("state", "ok"), ("ip", ip), ("bind_ip", bind_ip), ("recv_mode", mode),
        ("a0_virtual", v0), ("a1_virtual", v1), ("brightness", round(gain, 3)),
        ("sends", sends), ("reconnects", scriptOp.fetch("reconnects", 0)),
        ("last_config_age", round(now - float(scriptOp.fetch("last_config_t", now)), 2)),
        ("last_error", ""),
    ])
    if sends == 1 or sends % 30 == 0:
        try:
            Path(project.folder, "builders", ".td_phase5_diag.json").write_text(json.dumps({
                "phase": 5, "device": root.name, "live": True, "ip": ip, "bind_ip": bind_ip or None,
                "recv_mode": mode, "a0_virtual": v0, "a1_virtual": v1, "brightness": gain,
                "sends": sends, "reconnects": int(scriptOp.fetch("reconnects", 0)),
                "a0_first_rgb": list(a0[:3]), "a1_first_rgb": list(a1[:3]),
                "last_error": "",
            }, indent=2) + "\n")
        except Exception: pass
        if sends == 1:
            print("[phase5]", root.name, "live ArtDmx →", ip, "split" if mode != "combined" else "combined")
    scriptOp.clear()
'''


def _safe_name(name):
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name) or "device"


def _table(parent, name, rows, x, y):
    node = create_child(parent, "tableDAT", name)
    place(node, x, y)
    node.appendRow(["param", "value"])
    for row in rows:
        node.appendRow(row)
    return node


def _force_res(top, width, height):
    set_par(top, outputresolution="custom", resolutionw=width, resolutionh=height)


def _ensure_bus_top(media, prefix, kind, speed, phase, x, y):
    """Create or refresh a Script TOP bus source (demo / alt)."""
    name = f"bus_{prefix}_{kind}"
    cb_name = f"{name}_cb"
    cb = media.op(cb_name) or create_child(media, "textDAT", cb_name)
    cb.text = _GRADIENT_CALLBACKS
    demo = media.op(name) or create_child(media, "scriptTOP", name)
    place(demo, x, y)
    set_par(demo, callbacks=cb.path, cookalways=True)
    _force_res(demo, 512, 96)
    demo.store("speed", speed)
    demo.store("phase", phase)
    try:
        demo.cook(force=True)
    except Exception:
        pass
    return demo


def _ensure_media_frame_cook(media):
    """Keep demo/alt gradients cooking even when SharedMedia survives a rebuild."""
    # Primary demos (phase 0) and alt demos (phase-shifted, different speeds).
    _ensure_bus_top(media, "a0", "demo", .20, 0.0, 0, 100)
    _ensure_bus_top(media, "a1", "demo", .33, 0.0, 0, -160)
    _ensure_bus_top(media, "a0", "alt", .45, 0.5, 0, -40)
    _ensure_bus_top(media, "a1", "alt", .12, 0.5, 0, -300)
    for prefix, x in (("a0", 200), ("a1", 200)):
        if media.op(f"bus_{prefix}_movie") is None:
            place(create_child(media, "moviefileinTOP", f"bus_{prefix}_movie"), x, 100 if prefix == "a0" else -160)
        if media.op(f"bus_{prefix}_ext") is None:
            place(create_child(media, "nullTOP", f"bus_{prefix}_ext"), x + 200, 100 if prefix == "a0" else -160)
    frame = media.op("frame_cook")
    if frame is None:
        frame = create_child(media, "executeDAT", "frame_cook")
        place(frame, 0, 280)
    frame.text = _MEDIA_FRAME_COOK
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(frame.par, flag).val = True
        except Exception:
            pass
    set_par(frame, framestart=True, active=True)
    return frame


def _shared_media(base):
    media = create_child(base, "baseCOMP", "SharedMedia")
    place(media, -900, 0)
    readme = create_child(media, "textDAT", "README")
    readme.text = (
        "Durable media bus. Source keys: demo, alt, movie, ext.\n"
        "Wire show TOPs into bus_a0_ext / bus_a1_ext.\n"
        "demo vs alt are phase-shifted gradients so two receivers can look distinct.\n"
        "frame_cook keeps Script TOPs animating."
    )
    _ensure_media_frame_cook(media)
    return media


def _source_select(comp, prefix, source_key, media, x, y):
    source = create_child(comp, "selectTOP", f"{prefix}_source")
    key = str(source_key or "demo").strip().lower()
    if key not in ("demo", "alt", "movie", "ext"):
        key = "demo"
    set_par(source, top=f"{media.path}/bus_{prefix}_{key}")
    place(source, x, y)
    out = create_child(comp, "nullTOP", f"{prefix}_media")
    place(out, x + 180, y)
    try:
        out.inputConnectors[0].connect(source); out.viewer = True
    except Exception:
        pass
    return out


def _build_device(base, row, index, media):
    name = _safe_name(row["name"])
    comp = create_child(base, "baseCOMP", name)
    place(comp, (index % 3) * 500, -300 - (index // 3) * 400)
    profile = _table(comp, "profile", [(key, str(row.get(key, ""))) for key in DEVICE_COLS], 0, 300)
    look = _DEVICE_LOOKS[index % len(_DEVICE_LOOKS)]
    sampling_rows = [
        # 0..1 master dim on packed RGB (after sample). Prefer lowering this over
        # trusting bright source media. Legacy `level` 0..255 still works if set alone.
        ("brightness", "0.1"),
        ("hue_shift", look["hue_shift"]),
        ("send_fps", "30"), ("blackout", "0"),
        # Debounced re-push of output/receive/virtual after NIC or device flaps.
        ("config_refresh_s", "5"),
    ]
    for prefix, default_mode in (("a0", "point"), ("a1", "hline")):
        sampling_rows += [
            (f"{prefix}_sample_mode", default_mode),
            (f"{prefix}_u", look.get(f"{prefix}_u", ".5")),
            (f"{prefix}_v", look.get(f"{prefix}_v", ".5")),
            (f"{prefix}_u1", look.get(f"{prefix}_u1", "1")),
            (f"{prefix}_v1", look.get(f"{prefix}_v1", ".5")),
            (f"{prefix}_roi_u", "0"), (f"{prefix}_roi_v", "0"),
            (f"{prefix}_roi_w", "1"), (f"{prefix}_roi_h", "1"),
        ]
    _table(comp, "sampling", sampling_rows, 220, 300)
    # Live transport health for operators / agents (updated by artnet_cook).
    _table(comp, "link", [("state", "starting"), ("last_error", ""), ("reconnects", "0")], 440, 300)
    a0 = _source_select(comp, "a0", row.get("a0_source"), media, 0, 100)
    a1 = _source_select(comp, "a1", row.get("a1_source"), media, 0, -100)
    for prefix, source, y in (("a0", a0, 100), ("a1", a1, -100)):
        viz = create_child(comp, "resolutionTOP", f"{prefix}_viz_src")
        place(viz, 400, y); _force_res(viz, 240, 70)
        try: viz.inputConnectors[0].connect(source); viz.viewer = True
        except Exception: pass
    callbacks = create_child(comp, "textDAT", "artnet_callbacks")
    callbacks.text = _SENDER_CALLBACKS
    sender = create_child(comp, "scriptCHOP", "artnet_cook")
    place(sender, 450, 0)
    # Best-effort; many TD builds ignore Script CHOP cookalways — frame_cook below
    # is the reliable always-on path.
    set_par(sender, callbacks=callbacks.path, cookalways=True)
    frame = create_child(comp, "executeDAT", "frame_cook")
    place(frame, 450, 120)
    frame.text = _FRAME_COOK
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(frame.par, flag).val = True
        except Exception:
            pass
    set_par(frame, framestart=True, active=True)
    for prefix, y in (("a0", -220), ("a1", -320)):
        strip_cb = create_child(comp, "textDAT", f"{prefix}_strip_cb")
        strip_cb.text = _STRIP_CALLBACKS
        strip = create_child(comp, "scriptTOP", f"{prefix}_strip")
        place(strip, 0, y)
        set_par(strip, callbacks=strip_cb.path, cookalways=True)
        _force_res(strip, 72, 1)
        strip.store("prefix", prefix)
        viz = create_child(comp, "resolutionTOP", f"{prefix}_viz_send")
        place(viz, 180, y); _force_res(viz, 240, 50)
        try:
            viz.inputConnectors[0].connect(strip); viz.par.filtertype = "nearest"; viz.viewer = True
        except Exception:
            pass
    return comp


def _as_int(value, fallback):
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_row(raw):
    row = {key: str(raw.get(key, "")) for key in DEVICE_COLS}
    row["name"] = row["name"] or "device"
    row["active"] = "1" if str(raw.get("active", "1")).lower() in ("1", "true", "yes", "on") else "0"
    row["recv_mode"] = row["recv_mode"].lower() if row["recv_mode"].lower() in ("split", "combined") else "split"
    for prefix in ("a0", "a1"):
        typ = row[f"{prefix}_type"] if row[f"{prefix}_type"] in ("none", "short_strip", "long_strip", "grid", "small_grid", "extra_long_strip") else "none"
        row[f"{prefix}_type"] = typ
        row[f"{prefix}_count"] = str(physical_pixels(typ))
        virtual = _as_int(row[f"{prefix}_virtual"], default_virtual(typ))
        row[f"{prefix}_virtual"] = str(max(0, min(virtual, physical_pixels(typ))))
    return row


def _send_config(row):
    """Push output/receive/virtual config. Raises OSError on bind/send failure."""
    if row["active"] != "1" or not row["ip"]:
        return
    v0, v1 = int(row["a0_virtual"]), int(row["a1_virtual"])
    if row["recv_mode"] == "combined" and not validate_combined(v0, v1)[0]:
        raise ValueError(f"{row['name']}: combined virtual total exceeds 170")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if row["bind_ip"]:
            sock.bind((row["bind_ip"], 0))
        for packet in (
            build_output_config([row["a0_type"], row["a1_type"]]),
            build_receive_config(row["recv_mode"], int(row["universe"])),
            build_virtual_resolution([v0, v1]),
        ):
            sock.sendto(packet, (row["ip"], 6454))
            time.sleep(.03)
    finally:
        sock.close()


def _init_devices(table, rows):
    table.clear()
    table.appendRow(DEVICE_COLS)
    for row in rows:
        table.appendRow([str(row.get(key, "")) for key in DEVICE_COLS])


def _read_devices(table):
    return [
        _normalize_row({table[0, col].val: table[row, col].val for col in range(table.numCols)})
        for row in range(1, table.numRows)
    ]


def _silence_prior():
    """Stop earlier phase senders so only this phase owns each receiver."""
    for name in ("primus_phase1", "primus_phase2", "primus_phase3", "primus_phase4"):
        try:
            base = td_op(f"/project1/{name}")
            if base is None:
                continue
            controls = base.op("controls")
            if controls is not None:
                for row in range(1, controls.numRows):
                    if controls[row, 0].val == "active":
                        controls[row, 1] = "0"
                        break
            sender = base.op("artnet_cook")
            if sender is not None:
                set_par(sender, cookalways=False)
        except Exception as exc:
            print(f"[phase5] could not silence {name}: {exc}")


def build(parent_path=PARENT_PATH, rows=None, device_rows_json=None, **_ignored):
    """Build all device rows; `device_rows_json` is a JSON list for CLI use."""
    prepare_build(globals())
    _silence_prior()
    if device_rows_json:
        rows = json.loads(device_rows_json) if isinstance(device_rows_json, str) else device_rows_json
    base = ensure_base(parent_path, BASE_NAME)
    place(base, 0, -700)
    devices = base.op("devices")
    if devices is None:
        devices = create_child(base, "tableDAT", "devices")
        place(devices, 0, 500)
        _init_devices(devices, [_normalize_row(row) for row in (rows or DEFAULT_ROWS)])
    elif rows is not None:
        # An explicit CLI list replaces profiles; an ordinary rebuild preserves
        # the operator-edited table.
        _init_devices(devices, [_normalize_row(row) for row in rows])
    elif tuple(devices[0, c].val for c in range(devices.numCols)) != DEVICE_COLS:
        # Upgrade the Phase-5 prototype table while retaining fields it shared
        # with the new profile schema.
        old_rows = [
            {devices[0, c].val: devices[r, c].val for c in range(devices.numCols)}
            for r in range(1, devices.numRows)
        ]
        _init_devices(devices, [_normalize_row(row) for row in old_rows])
    controls = base.op("controls") or _table(base, "controls", [("blackout_all", "0")], 250, 500)
    media = base.op("SharedMedia")
    if media is None:
        media = _shared_media(base)
    else:
        # Preserve wiring, but refresh demo callbacks + frame pulse after upgrades.
        _ensure_media_frame_cook(media)
    # Keep SharedMedia and profile tables intact so external TOP connections
    # survive a receiver-only rebuild.
    for child in list(base.children):
        if child.isCOMP and child.name != "SharedMedia":
            child.destroy()
    valid_rows = []
    for row in _read_devices(devices):
        v0, v1 = int(row["a0_virtual"]), int(row["a1_virtual"])
        if row["recv_mode"] == "combined" and not validate_combined(v0, v1)[0]:
            print(f"[phase5] SKIP {row['name']}: combined virtual total {v0 + v1} exceeds 170")
            continue
        valid_rows.append(row)
    config_errors = []
    for index, row in enumerate(valid_rows):
        _build_device(base, row, index, media)
        try:
            _send_config(row)
        except OSError as exc:
            msg = f"{row['name']}: {exc}"
            print(f"[phase5] config send failed for {msg}")
            config_errors.append(msg)
    info = base.op("README") or create_child(base, "textDAT", "README")
    place(info, 500, 500)
    info.text = (
        "Phase 5 — simultaneous table-driven sampler/senders.\n"
        "devices: receiver transport/profile rows; each active=1 row creates one output COMP.\n"
        "SharedMedia source keys: demo, alt, movie, ext. "
        "primus_a defaults to demo; primus_b to alt (phase-shifted).\n"
        "Each device COMP has profile (transport), sampling (geometry), and link (live health).\n"
        "Sender recreates UDP on bind/send failure, re-pushes config every "
        "sampling.config_refresh_s (default 5), and keeps cookalways on.\n"
        "Split mode sends A0 to universe and A1 to universe+1. Stay on split until trusted.\n"
        "Before hardware work: python3 builders/td_remote.py preflight --bridge\n"
        "After a device/NIC flap: python3 builders/td_remote.py recover\n"
    )
    active_n = sum(r["active"] == "1" for r in valid_rows)
    names = [_safe_name(r["name"]) for r in valid_rows]
    active_names = [_safe_name(r["name"]) for r in valid_rows if r["active"] == "1"]
    print(f"[phase5] built {len(valid_rows)} sampler output(s), {active_n} active: {names}")
    try:
        from pathlib import Path

        folder = Path(project.folder) / "builders"  # noqa: F821
        (folder / ".td_phase5_build.json").write_text(
            json.dumps(
                {
                    "phase": 5,
                    "devices": names,
                    "active": active_names,
                    "rows": [
                        {
                            "name": r["name"],
                            "active": r["active"],
                            "ip": r["ip"],
                            "bind_ip": r["bind_ip"],
                            "recv_mode": r["recv_mode"],
                        }
                        for r in valid_rows
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[phase5] could not write build summary: {exc}")
    if config_errors:
        raise RuntimeError(
            "phase5 config/bind failed (samplers built; ArtDmx may be mute): "
            + "; ".join(config_errors)
        )
    return f"{base.path} devices={names} active={active_names}"
