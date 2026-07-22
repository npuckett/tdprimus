"""
Shared PrimusOutput network builder — Phase-5 sampler/UDP path for packaging.

Creates profile / sampling / link tables, demo fallback TOPs, In TOP media
inputs, artnet_cook sender, and strip previews inside a Base COMP.
"""

from __future__ import annotations

from builders.lib.output_types import default_virtual, physical_pixels
from builders.lib.td_builder import create_child, place, set_par

PROFILE_COLS = (
    "name",
    "active",
    "ip",
    "bind_ip",
    "universe",
    "recv_mode",
    "a0_type",
    "a0_count",
    "a0_virtual",
    "a1_type",
    "a1_count",
    "a1_virtual",
    "group",
)

DEVICE_LOOKS = (
    {
        "a0_u": ".35",
        "a0_v": ".35",
        "a1_u": ".0",
        "a1_v": ".35",
        "a1_u1": "1",
        "a1_v1": ".35",
        "hue_shift": "0",
    },
    {
        "a0_u": ".75",
        "a0_v": ".75",
        "a1_u": ".0",
        "a1_v": ".75",
        "a1_u1": "1",
        "a1_v1": ".75",
        "hue_shift": ".45",
    },
)

OUTPUT_TYPE_NAMES = [
    "none",
    "short_strip",
    "long_strip",
    "grid",
    "small_grid",
    "extra_long_strip",
]
OUTPUT_TYPE_LABELS = [
    "Off",
    "Short Strip",
    "Long Strip",
    "Grid 8x8",
    "Grid 8x4",
    "Extra Long Strip",
]
SAMPLE_MODE_NAMES = ["fit", "roi_fit", "hline", "vline", "line", "point"]

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

_FRAME_COOK = r'''
def onFrameStart(frame):
    root = me.parent()
    for name in (
        "demo_a0", "demo_a1",
        "a0_media1", "a0_media2", "a1_media1", "a1_media2",
        "artnet_cook",
    ):
        top = root.op(name)
        if top is None:
            continue
        try:
            top.cook(force=True)
        except Exception:
            pass
    # Refresh compact UI status from link table.
    try:
        link = root.op("link")
        status = root.op("ui/status")
        if link is not None and status is not None:
            def cell(key, default=""):
                try:
                    return str(link[key, 1].val)
                except Exception:
                    return default
            status.text = "state=%s  sends=%s  media=%s%sip=%s  bind=%s  err=%s" % (
                cell("state", "?"),
                cell("sends", "0"),
                cell("media", "demo"),
                chr(10),
                cell("ip", ""),
                cell("bind_ip", ""),
                cell("last_error", "")[:48],
            )
    except Exception:
        pass
'''

# Phase-9 sender: sync custom pars, resolve Manager globals, prefer wired In TOPs.
_SENDER_CALLBACKS = r'''
def onGetCookLevel(scriptOp):
    try: return CookLevel.ALWAYS
    except Exception: return 3

def _cell(table, key, default=""):
    try:
        value = table[key, 1]
        return value.val if hasattr(value, "val") else value
    except Exception: return default

def _set_cell(table, key, value):
    if table is None: return
    for row in range(1, table.numRows):
        if table[row, 0].val == key:
            table[row, 1] = str(value)
            return
    table.appendRow([key, str(value)])

def _set_link(root, rows):
    link = root.op("link")
    if link is None: return
    try:
        link.clear(); link.appendRow(["param", "value"])
        for key, value in rows: link.appendRow([str(key), str(value)])
    except Exception: pass

def _par(root, name, default=None):
    try:
        return getattr(root.par, name).eval()
    except Exception:
        return default

def _find_manager(root):
    """Locate PrimusManager: explicit path, sibling, parent, or nearby COMP."""
    path = str(_par(root, "Managerpath", "") or "").strip()
    if path:
        try:
            m = op(path)
            if m is not None and m.op("devices") is not None:
                return m
        except Exception:
            pass
    parent = root.parent()
    if parent is not None:
        m = parent.op("PrimusManager")
        if m is not None:
            return m
        # Sibling scan: any COMP with devices + Bindip (drop-in shows).
        try:
            for child in parent.children:
                if child is root or not getattr(child, "isCOMP", False):
                    continue
                if child.op("devices") is not None and hasattr(child.par, "Bindip"):
                    return child
        except Exception:
            pass
        grand = parent.parent()
        if grand is not None:
            m = grand.op("PrimusManager")
            if m is not None:
                return m
    try:
        m = op("/project1/primus_phase9/PrimusManager")
        if m is not None:
            return m
    except Exception:
        pass
    return None

def _manager(root):
    """Resolve Manager and write Managerpath back when auto-found."""
    m = _find_manager(root)
    if m is None:
        return None
    try:
        cur = str(_par(root, "Managerpath", "") or "").strip()
        if not cur or cur != m.path:
            root.par.Managerpath = m.path
    except Exception:
        pass
    return m

def _valid_type(value, fallback):
    v = str(value or "").strip().lower()
    if v in ("none", "short_strip", "long_strip", "grid", "small_grid", "extra_long_strip"):
        return v
    return fallback

def _valid_mode(value, fallback="split"):
    v = str(value or "").strip().lower()
    if v in ("split", "combined"):
        return v
    return fallback

def _valid_sample(value, fallback):
    v = str(value or "").strip().lower()
    if v in ("fit", "roi_fit", "hline", "vline", "line", "point"):
        return v
    return fallback

def _sync_pars(root, profile, sample, scriptOp):
    """Copy Custom Parameters into profile/sampling tables when present."""
    if _par(root, "Ip", None) is None:
        return
    _set_cell(profile, "ip", _par(root, "Ip", ""))
    _set_cell(profile, "name", _par(root, "Devicename", root.name))
    _set_cell(profile, "universe", int(_par(root, "Universe", 0) or 0))
    # Ignore broken menu defaults like name0/name1 when menuNames failed to bind.
    _set_cell(profile, "recv_mode", _valid_mode(_par(root, "Recvmode", "split"), str(_cell(profile, "recv_mode", "split") or "split")))
    _set_cell(profile, "a0_type", _valid_type(_par(root, "A0type", "small_grid"), str(_cell(profile, "a0_type", "small_grid") or "small_grid")))
    _set_cell(profile, "a1_type", _valid_type(_par(root, "A1type", "long_strip"), str(_cell(profile, "a1_type", "long_strip") or "long_strip")))
    _set_cell(profile, "a0_virtual", int(_par(root, "A0virtual", 1) or 1))
    _set_cell(profile, "a1_virtual", int(_par(root, "A1virtual", 72) or 72))
    active = _par(root, "Active", True)
    _set_cell(profile, "active", "1" if active else "0")
    local_bind = str(_par(root, "Bindip", "") or "").strip()
    if local_bind:
        _set_cell(profile, "bind_ip", local_bind)
    # Local brightness (Look page) → sampling table
    bright = _par(root, "Brightness", None)
    if bright is not None:
        try:
            _set_cell(sample, "brightness", max(0.0, min(1.0, float(bright))))
        except Exception:
            pass
    hue = _par(root, "Hueshift", None)
    if hue is not None:
        try:
            _set_cell(sample, "hue_shift", float(hue))
        except Exception:
            pass
    _set_cell(sample, "a0_sample_mode", _valid_sample(_par(root, "A0samplemode", "point"), "point"))
    _set_cell(sample, "a1_sample_mode", _valid_sample(_par(root, "A1samplemode", "hline"), "hline"))
    # Per-output media slot (A0 and A1 each have their own media1/media2 inputs).
    for prefix, pname, default_slot in (
        ("a0", "A0media", "media1"),
        ("a1", "A1media", "media1"),
    ):
        table_slot = str(_cell(sample, prefix + "_media_slot", default_slot) or default_slot).lower()
        if table_slot not in ("demo", "media1", "media2"):
            table_slot = default_slot
        choice = str(_par(root, pname, table_slot) or table_slot).strip().lower()
        if choice not in ("demo", "media1", "media2"):
            choice = table_slot
        _set_cell(sample, prefix + "_media_slot", choice)
    geom = {
        "a0": ("A0u", "A0v", "A0u1", "A0v1", "A0roiu", "A0roiv", "A0roiw", "A0roih"),
        "a1": ("A1u", "A1v", "A1u1", "A1v1", "A1roiu", "A1roiv", "A1roiw", "A1roih"),
    }
    keys = ("u", "v", "u1", "v1", "roi_u", "roi_v", "roi_w", "roi_h")
    for prefix, pnames in geom.items():
        for key, pname in zip(keys, pnames):
            val = _par(root, pname, None)
            if val is not None:
                _set_cell(sample, f"{prefix}_{key}", val)
    blackout = _par(root, "Blackout", False)
    _set_cell(sample, "blackout", "1" if blackout else "0")
    if scriptOp is not None and bool(_par(root, "Pushconfig", False)):
        scriptOp.store("force_config", True)

def _has_upstream(top, ignore_names=()):
    """True when TOP has a meaningful upstream (not only an empty inTOP)."""
    if top is None:
        return False
    ignore = set(ignore_names)
    try:
        for src in list(top.inputs or []):
            if src is None:
                continue
            if src.name in ignore:
                continue
            return True
    except Exception:
        pass
    try:
        for conn in top.inputConnectors:
            for c in list(getattr(conn, "connections", None) or []):
                owner = getattr(c, "owner", None) or getattr(c, "op", None)
                if owner is not None and owner.name not in ignore:
                    return True
    except Exception:
        pass
    return False

def _comp_input_wired(root, index=0):
    """True when parent COMP input connector has an outside wire."""
    try:
        cons = root.inputConnectors
        if index < len(cons) and cons[index].connections:
            return True
    except Exception:
        pass
    return False

def _slot_has_signal(root, prefix, slot_name):
    """True if a0/a1 media1|media2 COMP input is wired or null has non-in upstream."""
    idx = {
        ("a0", "media1"): 0,
        ("a0", "media2"): 1,
        ("a1", "media1"): 2,
        ("a1", "media2"): 3,
    }.get((prefix, slot_name))
    if idx is None:
        return False
    if _comp_input_wired(root, idx):
        return True
    slot = root.op("%s_%s" % (prefix, slot_name))
    inn = root.op("in%d" % (idx + 1))
    ignore = set()
    if inn is not None:
        ignore.add(inn.name)
    return _has_upstream(slot, ignore_names=tuple(ignore))

def _media_top(root, prefix):
    """Resolve A0/A1 sample TOP from that output's own media1/media2 inputs."""
    demo = root.op("demo_" + prefix)
    final = root.op(prefix + "_media")
    default_slot = "media1"
    choice = default_slot
    try:
        sample = root.op("sampling")
        choice = str(_cell(sample, prefix + "_media_slot", default_slot) or default_slot).lower()
    except Exception:
        pass
    if choice not in ("demo", "media1", "media2"):
        choice = default_slot
    par_name = "A0media" if prefix == "a0" else "A1media"
    try:
        raw = _par(root, par_name, None)
        if raw is not None:
            cand = str(raw).strip().lower()
            if cand in ("demo", "media1", "media2"):
                choice = cand
    except Exception:
        pass
    if choice == "demo":
        sample_src = demo
        label = "demo"
    else:
        # Dedicated ops: a0_media1 / a0_media2 / a1_media1 / a1_media2
        sample_src = root.op("%s_%s" % (prefix, choice)) or demo
        label = "%s_%s" % (prefix, choice)
    if final is not None and sample_src is not None:
        try:
            cur = final.inputs[0] if final.inputs else None
            if cur != sample_src:
                final.inputConnectors[0].connect(sample_src)
        except Exception:
            pass
    try:
        root.store(prefix + "_media_label", label)
    except Exception:
        pass
    return sample_src or final or demo

def onCook(scriptOp):
    import socket, struct, time, json
    from pathlib import Path
    root = scriptOp.parent()
    profile, sample = root.op("profile"), root.op("sampling")
    if profile is None or sample is None:
        scriptOp.clear(); return
    _sync_pars(root, profile, sample, scriptOp)
    mgr = _manager(root)
    if mgr is not None:
        try:
            bind = str(mgr.par.Bindip.eval()).strip()
            if bind:
                _set_cell(profile, "bind_ip", bind)
        except Exception: pass
        try:
            fps = float(mgr.par.Sendfps.eval())
            if fps > 0:
                _set_cell(sample, "send_fps", fps)
        except Exception: pass
    else:
        local_bind = str(_par(root, "Bindip", "") or "").strip()
        if not local_bind and not str(_cell(profile, "bind_ip", "")).strip():
            _set_link(root, [
                ("state", "no_manager"),
                ("last_error", "set Managerpath or Bindip override"),
            ])
            scriptOp.clear(); return
    if str(_cell(profile, "active", "0")) != "1":
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
        b = max(0., min(1., float(brightness)))
        if b >= 0.999: return payload
        if b <= 0.001: return bytes(len(payload))
        return bytes(max(0, min(255, int(c * b + .5))) for c in payload)
    def hue_shift(payload, shift):
        s = float(shift) % 1.0
        if s < 1e-6 or not payload: return payload
        out = bytearray()
        step = int(round(s * 3)) % 3
        for i in range(0, len(payload) - 2, 3):
            rgbv = [payload[i], payload[i + 1], payload[i + 2]]
            out.extend([rgbv[step % 3], rgbv[(step + 1) % 3], rgbv[(step + 2) % 3]])
        if len(payload) % 3: out.extend(payload[-(len(payload) % 3):])
        return bytes(out)
    def brightness():
        raw = str(_cell(sample, "brightness", "")).strip()
        local = clamp(number("brightness", .1)) if raw != "" else clamp(integer(sample, "level", 26) / 255.)
        scale = 1.0
        if mgr is not None:
            try: scale = clamp(float(mgr.par.Brightness.eval()))
            except Exception: pass
        return clamp(local * scale)
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
            print("[PrimusOutput]", root.name, reason, "(retry in %.1fs)" % delay)
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
    mgr_blackout = False
    if mgr is not None:
        try:
            ctrl = mgr.op("controls")
            mgr_blackout = str(_cell(ctrl, "blackout_all", "0")) == "1"
        except Exception: pass
    blackout = str(_cell(sample, "blackout", "0")) == "1" or mgr_blackout
    identify_until = float(scriptOp.fetch("identify_until", 0))
    identifying = now < identify_until
    a0_top = _media_top(root, "a0")
    a1_top = _media_top(root, "a1")
    for top in (a0_top, a1_top):
        if top is not None:
            try: top.cook(force=True)
            except Exception: pass
    gain = 0. if blackout else brightness()
    shift = number("hue_shift", 0)
    try:
        if identifying:
            a0 = dim(bytes([255, 255, 255]) * v0, 1.0) if v0 else b""
            a1 = dim(bytes([255, 255, 255]) * v1, 1.0) if v1 else b""
        else:
            a0 = dim(hue_shift(rgb(a0_top.numpyArray() if a0_top else None, v0, "a0"), shift), gain) if v0 else b""
            a1 = dim(hue_shift(rgb(a1_top.numpyArray() if a1_top else None, v1, "a1"), shift), gain) if v1 else b""
    except Exception as exc:
        print("[PrimusOutput] sample failed:", exc); a0, a1 = bytes(v0 * 3), bytes(v1 * 3)
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
        print("[PrimusOutput]", root.name, "recovered →", ip)
        scriptOp.store("log_reason", "")
    def _is_wired(prefix):
        try:
            return str(root.fetch(prefix + "_media_label", "demo")).startswith("media")
        except Exception:
            return False
    media_src = "identify" if identifying else (
        (str(root.fetch("a0_media_label", "demo")) + "/" + str(root.fetch("a1_media_label", "demo")))
    )
    _set_link(root, [
        ("state", "ok"), ("ip", ip), ("bind_ip", bind_ip), ("recv_mode", mode),
        ("a0_virtual", v0), ("a1_virtual", v1), ("brightness", round(gain, 3)),
        ("sends", sends), ("reconnects", scriptOp.fetch("reconnects", 0)),
        ("media", media_src),
        ("last_config_age", round(now - float(scriptOp.fetch("last_config_t", now)), 2)),
        ("last_error", ""),
    ])
    if sends == 1 or sends % 30 == 0:
        payload = {
            "phase": 9, "device": root.name, "live": True, "ip": ip, "bind_ip": bind_ip or None,
            "recv_mode": mode, "a0_virtual": v0, "a1_virtual": v1, "brightness": gain,
            "sends": sends, "reconnects": int(scriptOp.fetch("reconnects", 0)),
            "media": media_src,
            "a0_first_rgb": list(a0[:3]), "a1_first_rgb": list(a1[:3]),
            "last_error": "",
        }
        try:
            folder = Path(project.folder, "builders")
            folder.joinpath(".td_phase9_diag.json").write_text(json.dumps(payload, indent=2) + "\n")
            folder.joinpath(".td_phase9_diag_%s.json" % root.name).write_text(
                json.dumps(payload, indent=2) + "\n"
            )
        except Exception: pass
        if sends == 1:
            print("[PrimusOutput]", root.name, "live ArtDmx →", ip, mode, media_src)
    scriptOp.clear()
'''


def safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name) or "device"


def normalize_profile(raw: dict | None) -> dict:
    """Normalize a receiver profile dict (offline-safe)."""
    raw = raw or {}
    row = {key: str(raw.get(key, "")) for key in PROFILE_COLS}
    row["name"] = row["name"] or "PrimusOutput"
    row["active"] = (
        "1"
        if str(raw.get("active", "1")).lower() in ("1", "true", "yes", "on", "")
        else "0"
    )
    mode = row["recv_mode"].lower()
    row["recv_mode"] = mode if mode in ("split", "combined") else "split"
    for prefix in ("a0", "a1"):
        typ = row[f"{prefix}_type"]
        if typ not in OUTPUT_TYPE_NAMES:
            typ = "small_grid" if prefix == "a0" else "long_strip"
        row[f"{prefix}_type"] = typ
        row[f"{prefix}_count"] = str(physical_pixels(typ))
        try:
            virtual = int(float(row[f"{prefix}_virtual"] or default_virtual(typ)))
        except (TypeError, ValueError):
            virtual = default_virtual(typ)
        row[f"{prefix}_virtual"] = str(max(0, min(virtual, physical_pixels(typ))))
    if not row["ip"]:
        row["ip"] = "192.168.8.166"
    if not row["bind_ip"]:
        row["bind_ip"] = "192.168.8.199"
    if not row["universe"]:
        row["universe"] = "0"
    if not row["group"]:
        row["group"] = "default"
    return row


def default_sampling_rows(look_index: int = 0) -> list[tuple[str, str]]:
    look = DEVICE_LOOKS[look_index % len(DEVICE_LOOKS)]
    rows = [
        ("brightness", "0.1"),
        ("hue_shift", look["hue_shift"]),
        ("send_fps", "30"),
        ("blackout", "0"),
        ("config_refresh_s", "5"),
    ]
    for prefix, default_mode in (("a0", "point"), ("a1", "hline")):
        rows += [
            (f"{prefix}_sample_mode", default_mode),
            (f"{prefix}_u", look.get(f"{prefix}_u", ".5")),
            (f"{prefix}_v", look.get(f"{prefix}_v", ".5")),
            (f"{prefix}_u1", look.get(f"{prefix}_u1", "1")),
            (f"{prefix}_v1", look.get(f"{prefix}_v1", ".5")),
            (f"{prefix}_roi_u", "0"),
            (f"{prefix}_roi_v", "0"),
            (f"{prefix}_roi_w", "1"),
            (f"{prefix}_roi_h", "1"),
        ]
    return rows


def _table(parent, name, rows, x, y):
    node = create_child(parent, "tableDAT", name)
    place(node, x, y)
    node.clear()
    node.appendRow(["param", "value"])
    for row in rows:
        node.appendRow(list(row))
    return node


def _force_res(top, width, height):
    set_par(top, outputresolution="custom", resolutionw=width, resolutionh=height)


def _ensure_demo(comp, prefix, speed, phase, x, y):
    cb_name = f"demo_{prefix}_cb"
    cb = comp.op(cb_name) or create_child(comp, "textDAT", cb_name)
    place(cb, x, y + 80)
    cb.text = _GRADIENT_CALLBACKS
    demo = comp.op(f"demo_{prefix}") or create_child(comp, "scriptTOP", f"demo_{prefix}")
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


def build_output_network(comp, profile: dict | None = None, look_index: int = 0):
    """
    Populate a Base COMP with PrimusOutput internals (tables, media, sender).

    Media contract (per physical output):
      - A0: ``a0_media1``, ``a0_media2`` (COMP inputs 1–2)
      - A1: ``a1_media1``, ``a1_media2`` (COMP inputs 3–4)
      - ``A0media`` / ``A1media`` select demo | media1 | media2 for that strip only.
    """
    row = normalize_profile(profile)
    profile_rows = [(key, row.get(key, "")) for key in PROFILE_COLS]
    _table(comp, "profile", profile_rows, 0, 300)
    sampling_rows = default_sampling_rows(look_index)
    sampling_rows += [("a0_media_slot", "media1"), ("a1_media_slot", "media1")]
    _table(comp, "sampling", sampling_rows, 220, 300)
    _table(
        comp,
        "link",
        [("state", "starting"), ("last_error", ""), ("reconnects", "0"), ("sends", "0")],
        440,
        300,
    )

    # Dedicated media inputs per strip: A0 → in1/in2, A1 → in3/in4.
    slot_layout = (
        ("a0", "media1", "in1", 160),
        ("a0", "media2", "in2", 40),
        ("a1", "media1", "in3", -80),
        ("a1", "media2", "in4", -200),
    )
    for prefix, slot, in_name, y in slot_layout:
        op_name = f"{prefix}_{slot}"
        try:
            inn = comp.op(in_name) or create_child(comp, "inTOP", in_name)
            place(inn, -200, y)
        except Exception:
            inn = None
        media = comp.op(op_name) or create_child(comp, "nullTOP", op_name)
        place(media, 0, y)
        try:
            media.viewer = True
        except Exception:
            pass
        if inn is not None:
            try:
                media.inputConnectors[0].connect(inn)
            except Exception:
                pass
        viz = create_child(comp, "resolutionTOP", f"{op_name}_viz")
        place(viz, 160, y)
        _force_res(viz, 120, 40)
        try:
            viz.inputConnectors[0].connect(media)
            viz.viewer = True
        except Exception:
            pass

    demo_a0 = _ensure_demo(comp, "a0", 0.20, 0.0 if look_index % 2 == 0 else 0.5, 360, 160)
    demo_a1 = _ensure_demo(comp, "a1", 0.33, 0.0 if look_index % 2 == 0 else 0.5, 360, -80)

    for prefix, demo, y in (("a0", demo_a0, 100), ("a1", demo_a1, -100)):
        out = comp.op(f"{prefix}_media") or create_child(comp, "nullTOP", f"{prefix}_media")
        place(out, 560, y)
        try:
            out.inputConnectors[0].connect(demo)
            out.viewer = True
        except Exception:
            pass
        viz = create_child(comp, "resolutionTOP", f"{prefix}_viz_src")
        place(viz, 740, y)
        _force_res(viz, 240, 70)
        try:
            viz.inputConnectors[0].connect(out)
            viz.viewer = True
        except Exception:
            pass

    callbacks = create_child(comp, "textDAT", "artnet_callbacks")
    place(callbacks, 560, -40)
    callbacks.text = _SENDER_CALLBACKS
    sender = create_child(comp, "scriptCHOP", "artnet_cook")
    place(sender, 560, 0)
    set_par(sender, callbacks=callbacks.path, cookalways=True)

    frame = create_child(comp, "executeDAT", "frame_cook")
    place(frame, 560, 120)
    frame.text = _FRAME_COOK
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(frame.par, flag).val = True
        except Exception:
            pass
    set_par(frame, framestart=True, active=True)

    for prefix, y in (("a0", -280), ("a1", -380)):
        strip_cb = create_child(comp, "textDAT", f"{prefix}_strip_cb")
        place(strip_cb, 0, y + 40)
        strip_cb.text = _STRIP_CALLBACKS
        strip = create_child(comp, "scriptTOP", f"{prefix}_strip")
        place(strip, 0, y)
        set_par(strip, callbacks=strip_cb.path, cookalways=True)
        _force_res(strip, 72, 1)
        strip.store("prefix", prefix)
        viz = create_child(comp, "resolutionTOP", f"{prefix}_viz_send")
        place(viz, 180, y)
        _force_res(viz, 240, 50)
        try:
            viz.inputConnectors[0].connect(strip)
            viz.par.filtertype = "nearest"
            viz.viewer = True
        except Exception:
            pass

    # Compact monitor panel (viewers + link status). Control stays on custom pages.
    ui = comp.op("ui") or create_child(comp, "containerCOMP", "ui")
    place(ui, 900, 100)
    try:
        ui.par.w = 520
        ui.par.h = 420
        ui.par.display = True
        ui.par.nodeviewer = True
    except Exception:
        pass

    viewer_specs = (
        ("view_a0", "../a0_media", 0, 160, "A0 source"),
        ("view_a1", "../a1_media", 280, 160, "A1 source"),
        ("view_a0_send", "../a0_viz_send", 0, 40, "A0 send"),
        ("view_a1_send", "../a1_viz_send", 280, 40, "A1 send"),
    )
    for name, top_path, x, y, _label in viewer_specs:
        sel = ui.op(name)
        if sel is None:
            try:
                sel = create_child(ui, "selectTOP", name)
            except Exception:
                sel = None
        if sel is None:
            continue
        place(sel, x, y)
        try:
            set_par(sel, top=top_path)
        except Exception:
            try:
                sel.par.top = top_path
            except Exception:
                pass
        try:
            sel.viewer = True
        except Exception:
            pass

    status = ui.op("status") or create_child(ui, "textDAT", "status")
    place(status, 0, -80)
    status.text = "state=starting  sends=0  media=demo\nip=  bind=  err="

    guide = ui.op("GUIDE") or create_child(ui, "textDAT", "GUIDE")
    place(guide, 0, -200)
    guide.text = (
        "PrimusOutput monitor\n"
        "Top: A0/A1 selected sources · Bottom: send strip previews\n"
        "status DAT mirrors link table each frame.\n\n"
        "COMP inputs 1–2 → A0 media1/2 · 3–4 → A1 media1/2\n"
        "Pages: Device | Media | Look | Actions\n"
        "Empty Managerpath auto-finds sibling PrimusManager.\n"
    )

    readme = comp.op("README") or create_child(comp, "textDAT", "README")
    place(readme, 900, 300)
    readme.text = (
        "PrimusOutput — production drop-in (one per Primus receiver).\n"
        "A0: a0_media1, a0_media2 (inputs 1–2)\n"
        "A1: a1_media1, a1_media2 (inputs 3–4)\n"
        "Media page: demo | media1 | media2 per strip.\n"
        "Set Managerpath or leave blank to auto-find PrimusManager.\n"
        "Works without MediaBus — unwired slots use demo gradients.\n"
    )
    return comp
