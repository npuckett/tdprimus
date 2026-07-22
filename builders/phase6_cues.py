"""Phase 6 — cue deck UI + OSC-ready control over Phase 5 looks."""

from __future__ import annotations

import json
import sys


def _bootstrap():
    try:
        root = project.folder  # noqa: F821
    except NameError:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)


_bootstrap()

from builders.lib.td_builder import (  # noqa: E402
    create_child,
    ensure_base,
    place,
    prepare_build,
    set_par,
    td_op,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase6"
PHASE5_PATH = "/project1/primus_phase5"
DEFAULT_OSC_PORT = 7000

CUE_COLS = (
    "cue", "targets", "a0_content", "a1_content",
    "brightness", "hue_shift", "blackout", "fade", "notes",
)

# Four cues: same / same-other / different-per-device / blackout.
# Content "split" = each device keeps a distinct look (see _DEVICE_SPLIT).
DEFAULT_CUES = [
    {
        "cue": "1", "targets": "*",
        "a0_content": "demo", "a1_content": "demo",
        "brightness": "0.1", "hue_shift": "0", "blackout": "0",
        "fade": "0", "notes": "BOTH same → demo",
    },
    {
        "cue": "2", "targets": "*",
        "a0_content": "alt", "a1_content": "alt",
        "brightness": "0.1", "hue_shift": "0.45", "blackout": "0",
        "fade": "0", "notes": "BOTH same → alt + hue",
    },
    {
        "cue": "3", "targets": "*",
        "a0_content": "split", "a1_content": "split",
        "brightness": "0.1", "hue_shift": "0", "blackout": "0",
        "fade": "0", "notes": "DIFFERENT: A=demo, B=alt",
    },
    {
        "cue": "4", "targets": "*",
        "a0_content": "black", "a1_content": "black",
        "brightness": "0", "hue_shift": "0", "blackout": "1",
        "fade": "0", "notes": "BOTH blackout",
    },
]

# Shared runtime API: panel pulses, OSC, and shell all call these.
_CUE_API = r'''
def _cell(table, key, default=""):
    try:
        value = table[key, 1]
        return value.val if hasattr(value, "val") else value
    except Exception:
        return default

def _set_cell(table, key, value):
    if table is None:
        return
    for row in range(1, table.numRows):
        if table[row, 0].val == key:
            table[row, 1] = str(value)
            return
    table.appendRow([key, str(value)])

def _match(targets, name, group):
    targets = (targets or "*").strip()
    if targets in ("*", ""):
        return True
    for part in targets.split(","):
        part = part.strip()
        if part.startswith("group:"):
            if group == part.split(":", 1)[1]:
                return True
        elif part == name:
            return True
    return False

def _phase5():
    return op("/project1/primus_phase5")

def _root():
    return op("/project1/primus_phase6")

# Per-device looks when cue content is "split" (same cue, different output).
_DEVICE_SPLIT = {
    "primus_a": {"a0": "demo", "a1": "demo", "hue_shift": 0.0, "brightness": 0.1},
    "primus_b": {"a0": "alt", "a1": "alt", "hue_shift": 0.45, "brightness": 0.1},
}

def _apply_source(dcomp, media, prefix, key):
    key = (key or "demo").strip().lower()
    black = key == "black"
    if black:
        key = "demo"
    if key not in ("demo", "alt", "movie", "ext"):
        key = "demo"
    profile = dcomp.op("profile")
    _set_cell(profile, prefix + "_source", key)
    sel = dcomp.op(prefix + "_source")
    if sel is not None and media is not None:
        try:
            sel.par.top = media.path + "/bus_" + prefix + "_" + key
        except Exception as exc:
            print("[phase6] source select failed:", prefix, exc)
    return black

def _sync_panel(root):
    state = root.op("cue_state")
    status = root.op("status")
    if state is None or status is None:
        return
    pairs = [
        ("cue", _cell(state, "cue_number", "?")),
        ("applied", _cell(state, "last_applied", "")),
        ("error", _cell(state, "last_error", "")),
        ("source", "panel / OSC / shell"),
    ]
    status.clear()
    status.appendRow(["param", "value"])
    for key, value in pairs:
        status.appendRow([key, value])
    try:
        root.par.Cuenumber = int(float(_cell(state, "cue_number", "1")))
    except Exception:
        pass
    try:
        root.par.Status = "cue %s → %s" % (
            _cell(state, "cue_number", "?"),
            _cell(state, "last_applied", ""),
        )
    except Exception:
        pass

def apply_cue_row(root, row, source="api"):
    p5 = _phase5()
    if p5 is None:
        print("[phase6] primus_phase5 missing — build Phase 5 first")
        _set_cell(root.op("cue_state"), "last_error", "primus_phase5 missing")
        _sync_panel(root)
        return False
    devices = p5.op("devices")
    media = p5.op("SharedMedia")
    cues = root.op("cues")
    if devices is None or cues is None or row < 1 or row >= cues.numRows:
        return False
    targets = cues[row, "targets"].val.strip()
    a0c = cues[row, "a0_content"].val.strip().lower()
    a1c = cues[row, "a1_content"].val.strip().lower()
    try:
        brightness = max(0.0, min(1.0, float(cues[row, "brightness"].val)))
    except Exception:
        brightness = 0.1
    try:
        hue_shift = float(cues[row, "hue_shift"].val)
    except Exception:
        hue_shift = 0.0
    cue_black = str(cues[row, "blackout"].val).strip() in ("1", "true", "yes", "on")
    split_mode = a0c == "split" or a1c == "split"
    applied = []
    for r in range(1, devices.numRows):
        cols = {devices[0, c].val: c for c in range(devices.numCols)}
        def col(key, default=""):
            c = cols.get(key)
            return devices[r, c].val if c is not None else default
        name, group, active = col("name"), col("group", "default"), col("active", "1")
        if active != "1" or not _match(targets, name, group):
            continue
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name) or "device"
        dcomp = p5.op(safe)
        if dcomp is None:
            continue
        sample = dcomp.op("sampling")
        dev_a0, dev_a1 = a0c, a1c
        dev_brightness, dev_hue = brightness, hue_shift
        if split_mode:
            look = _DEVICE_SPLIT.get(safe) or _DEVICE_SPLIT.get(name) or {
                "a0": "demo", "a1": "demo", "hue_shift": 0.0, "brightness": 0.1,
            }
            dev_a0, dev_a1 = look["a0"], look["a1"]
            dev_brightness = float(look.get("brightness", brightness))
            dev_hue = float(look.get("hue_shift", hue_shift))
        b0 = _apply_source(dcomp, media, "a0", dev_a0)
        b1 = _apply_source(dcomp, media, "a1", dev_a1)
        blackout = 1 if (cue_black or (b0 and b1)) else 0
        _set_cell(sample, "blackout", blackout)
        _set_cell(sample, "brightness", 0.0 if blackout else dev_brightness)
        _set_cell(sample, "hue_shift", dev_hue)
        applied.append(safe)
    state = root.op("cue_state")
    _set_cell(state, "cue_index", row)
    _set_cell(state, "cue_number", cues[row, "cue"].val)
    _set_cell(state, "last_applied", ",".join(applied) if applied else "(none)")
    _set_cell(state, "last_error", "")
    _set_cell(state, "last_source", source)
    print("[phase6] %s applied cue %s → %s" % (source, cues[row, "cue"].val, applied))
    _sync_panel(root)
    return True

def go(root=None, source="go"):
    root = root or _root()
    cues = root.op("cues")
    state = root.op("cue_state")
    if cues is None or state is None or cues.numRows < 2:
        return False
    try:
        last = int(float(_cell(state, "cue_index", "0")))
    except Exception:
        last = 0
    next_row = last + 1
    if next_row >= cues.numRows:
        next_row = 1
    return apply_cue_row(root, next_row, source=source)

def goto(cue_number, root=None, source="goto"):
    root = root or _root()
    cues = root.op("cues")
    if cues is None:
        return False
    want = str(cue_number).strip()
    for row in range(1, cues.numRows):
        if cues[row, "cue"].val.strip() == want:
            return apply_cue_row(root, row, source=source)
    _set_cell(root.op("cue_state"), "last_error", "cue %s not found" % want)
    _sync_panel(root)
    print("[phase6] cue", want, "not found")
    return False

def blackout(on=True, root=None, source="blackout"):
    """Hard blackout all active Phase 5 devices (not a cue list step)."""
    root = root or _root()
    p5 = _phase5()
    controls = root.op("controls")
    _set_cell(controls, "blackout_all", "1" if on else "0")
    if p5 is None:
        return False
    devices = p5.op("devices")
    if devices is None:
        return False
    cols = {devices[0, c].val: c for c in range(devices.numCols)}
    applied = []
    for r in range(1, devices.numRows):
        name = devices[r, cols["name"]].val if "name" in cols else ""
        active = devices[r, cols["active"]].val if "active" in cols else "1"
        if active != "1":
            continue
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name) or "device"
        dcomp = p5.op(safe)
        if dcomp is None:
            continue
        sample = dcomp.op("sampling")
        _set_cell(sample, "blackout", "1" if on else "0")
        if not on:
            # restore a safe dim when leaving blackout
            _set_cell(sample, "brightness", "0.1")
        applied.append(safe)
    _set_cell(root.op("cue_state"), "last_applied", ",".join(applied))
    _set_cell(root.op("cue_state"), "last_source", source)
    _set_cell(root.op("cue_state"), "last_error", "blackout" if on else "")
    _sync_panel(root)
    print("[phase6] %s blackout=%s → %s" % (source, on, applied))
    return True

def handle_osc(address, args, root=None):
    """
    OSC map (UDP, default port 7000):
      /primus/cue/go
      /primus/cue/goto   <int cue number>
      /primus/cue/blackout <0|1>
    """
    root = root or _root()
    addr = (address or "").rstrip("/")
    args = list(args or [])
    if addr.endswith("/go") or addr == "/primus/cue/go":
        return go(root, source="osc")
    if addr.endswith("/goto") or addr == "/primus/cue/goto":
        n = args[0] if args else _cell(root.op("controls"), "goto_cue", "1")
        return goto(n, root, source="osc")
    if addr.endswith("/blackout") or addr == "/primus/cue/blackout":
        on = True if not args else bool(int(float(args[0])))
        return blackout(on, root, source="osc")
    print("[phase6] unknown OSC", address, args)
    return False
'''

_GO_EXECUTE = r'''
def onTableChange(dat):
    _drain_controls(dat.parent())

def onFrameEnd(frame):
    root = me.parent()
    _drain_controls(root)
    _poll_shell_cmd(root)

def _api():
    # Load shared API from sibling textDAT
    ns = {"op": op, "project": project}
    exec(op("/project1/primus_phase6/cue_api").text, ns)
    return ns

def _drain_controls(root):
    controls = root.op("controls")
    if controls is None:
        return
    api = _api()
    try:
        if int(float(api["_cell"](controls, "go", "0"))) == 1:
            api["_set_cell"](controls, "go", "0")
            api["go"](root, source="controls")
    except Exception as exc:
        print("[phase6] go failed:", exc)
    try:
        goto_cue = str(api["_cell"](controls, "goto_cue", "")).strip()
        goto_pulse = int(float(api["_cell"](controls, "goto", "0")))
        if goto_pulse == 1 and goto_cue:
            api["_set_cell"](controls, "goto", "0")
            api["goto"](goto_cue, root, source="controls")
    except Exception as exc:
        print("[phase6] goto failed:", exc)
    try:
        if int(float(api["_cell"](controls, "blackout_pulse", "0"))) == 1:
            api["_set_cell"](controls, "blackout_pulse", "0")
            on = int(float(api["_cell"](controls, "blackout_all", "0"))) == 1
            api["blackout"](on, root, source="controls")
    except Exception as exc:
        print("[phase6] blackout failed:", exc)

def _poll_shell_cmd(root):
    try:
        from pathlib import Path
        import json
        path = Path(project.folder) / "builders" / ".td_cue_cmd.json"
        if not path.exists():
            return
        raw = path.read_text(encoding="utf-8").strip()
        if not raw or raw == "{}":
            return
        path.write_text("{}\n", encoding="utf-8")
        data = json.loads(raw)
        api = _api()
        cmd = (data.get("cmd") or "").lower()
        if cmd == "go":
            api["go"](root, source="shell")
        elif cmd == "goto":
            api["goto"](data.get("cue", 1), root, source="shell")
        elif cmd == "blackout":
            api["blackout"](bool(data.get("on", True)), root, source="shell")
    except Exception as exc:
        print("[phase6] cue cmd failed:", exc)
'''

_CUE_EXT = r'''
"""Promoted extension: Cue page pulses call these methods by name."""

class CueDeckExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _api(self):
        ns = {"op": op, "project": project}
        exec(self.ownerComp.op("cue_api").text, ns)
        return ns

    def Go(self, _par=None):
        return self._api()["go"](self.ownerComp, source="panel")

    def Goto(self, _par=None):
        n = int(self.ownerComp.par.Cuenumber)
        return self._api()["goto"](n, self.ownerComp, source="panel")

    def Blackout(self, _par=None):
        self.ownerComp.op("controls")["blackout_all", 1] = "1"
        return self._api()["blackout"](True, self.ownerComp, source="panel")

    def Restore(self, _par=None):
        self.ownerComp.op("controls")["blackout_all", 1] = "0"
        return self._api()["blackout"](False, self.ownerComp, source="panel")
'''

_PARAM_EXEC = r'''
# Fallback if extension promote is unavailable
def onOffToOn(par):
    root = parent()
    api_ns = {"op": op, "project": project}
    exec(root.op("cue_api").text, api_ns)
    name = par.name
    if name == "Go":
        api_ns["go"](root, source="panel")
    elif name == "Goto":
        api_ns["goto"](int(root.par.Cuenumber), root, source="panel")
    elif name == "Blackout":
        root.op("controls")["blackout_all", 1] = "1"
        api_ns["blackout"](True, root, source="panel")
    elif name == "Restore":
        root.op("controls")["blackout_all", 1] = "0"
        api_ns["blackout"](False, root, source="panel")
'''

_OSC_CALLBACKS = r'''
def onReceiveOSC(dat, rowIndex, message, bytes, peer):
    """TD oscinDAT callback — keep addresses stable for show control."""
    try:
        # message formats vary; prefer structured args when available
        address = message
        args = []
        if isinstance(message, (list, tuple)):
            address = message[0] if message else ""
            args = list(message[1:])
        root = op("/project1/primus_phase6")
        ns = {"op": op, "project": project}
        exec(root.op("cue_api").text, ns)
        # Also try parsing "addr arg1 arg2" text form
        if isinstance(address, str) and " " in address and not args:
            parts = address.split()
            address, args = parts[0], parts[1:]
        ns["handle_osc"](str(address), args, root)
    except Exception as exc:
        print("[phase6] OSC receive failed:", exc)
'''


def _table(parent, name, rows, x, y):
    node = create_child(parent, "tableDAT", name)
    place(node, x, y)
    node.clear()
    node.appendRow(["param", "value"])
    for key, value in rows:
        node.appendRow([key, value])
    return node


def _init_cues(table, rows):
    table.clear()
    table.appendRow(list(CUE_COLS))
    for row in rows:
        table.appendRow([str(row.get(col, "")) for col in CUE_COLS])


def _add_cue_pars(base):
    try:
        page = base.appendCustomPage("Cue")
    except Exception:
        page = base.customPages[0] if getattr(base, "customPages", None) else None
    if page is None:
        return
    specs = [
        ("pulse", "Go", "GO — next cue"),
        ("int", "Cuenumber", "Cue #"),
        ("pulse", "Goto", "Goto cue #"),
        ("pulse", "Blackout", "Blackout all"),
        ("pulse", "Restore", "Restore from blackout"),
        ("str", "Status", "Status"),
        ("int", "Oscport", "OSC UDP port"),
    ]
    for kind, name, label in specs:
        try:
            if kind == "pulse":
                page.appendPulse(name, label=label)
            elif kind == "int":
                p = page.appendInt(name, label=label)
                if name == "Cuenumber":
                    p.val = 1
                    p.normMin = 1
                    p.normMax = 99
                    p.min = 1
                    p.max = 99
                elif name == "Oscport":
                    p.val = DEFAULT_OSC_PORT
                    p.min = 1
                    p.max = 65535
            elif kind == "str":
                p = page.appendStr(name, label=label)
                p.val = "ready"
        except Exception as exc:
            print(f"[phase6] custom par {name}: {exc}")


def _wire_osc(base, port):
    """Create OSC input bound to the stable /primus/cue/* address map."""
    osc_base = create_child(base, "baseCOMP", "osc")
    place(osc_base, 900, 200)
    readme = create_child(osc_base, "textDAT", "README")
    readme.text = (
        "OSC show-control map (UDP):\n"
        f"  port {port} (change Cue.Oscport + rebuild, or edit oscin)\n"
        "  /primus/cue/go\n"
        "  /primus/cue/goto <int>\n"
        "  /primus/cue/blackout <0|1>\n"
        "Panel GO/Goto/Blackout call the same cue_api as OSC.\n"
    )
    cb = create_child(osc_base, "textDAT", "osc_callbacks")
    cb.text = _OSC_CALLBACKS
    # Prefer oscinDAT; fall back to naming variants across TD builds.
    osc_in = None
    for kind in ("oscinDAT", "oscInDAT", "oscin"):
        try:
            osc_in = create_child(osc_base, kind, "osc_in")
            break
        except Exception:
            continue
    if osc_in is None:
        print("[phase6] WARN: could not create oscinDAT — panel/shell still work")
        return osc_base
    place(osc_in, 0, 0)
    for key, value in (("port", port), ("protocol", "udp"), ("active", True)):
        try:
            set_par(osc_in, **{key: value})
        except Exception:
            try:
                getattr(osc_in.par, key).val = value
            except Exception:
                pass
    try:
        set_par(osc_in, callbacks=cb.path)
    except Exception:
        try:
            osc_in.par.callbacks = cb.path
        except Exception:
            pass
    # Some builds use execute-style callback text on the DAT itself.
    try:
        if hasattr(osc_in, "text") and not getattr(osc_in.par, "callbacks", None):
            osc_in.text = _OSC_CALLBACKS
    except Exception:
        pass
    return osc_base


def build(parent_path=PARENT_PATH, **_ignored):
    """Build Phase 6 cue deck (panel + OSC) driving Phase 5."""
    prepare_build(globals())
    p5 = td_op(PHASE5_PATH)
    if p5 is None:
        raise RuntimeError("build Phase 5 first — Phase 6 drives /project1/primus_phase5")

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 400, -700)
    _add_cue_pars(base)

    api = create_child(base, "textDAT", "cue_api")
    place(api, 0, 600)
    api.text = _CUE_API

    cues = create_child(base, "tableDAT", "cues")
    place(cues, 0, 400)
    _init_cues(cues, DEFAULT_CUES)

    state = _table(
        base,
        "cue_state",
        [
            ("cue_index", "0"),
            ("cue_number", "0"),
            ("last_applied", ""),
            ("last_error", ""),
            ("last_source", ""),
        ],
        220,
        400,
    )
    controls = _table(
        base,
        "controls",
        [
            ("go", "0"),
            ("goto", "0"),
            ("goto_cue", "1"),
            ("blackout_all", "0"),
            ("blackout_pulse", "0"),
            ("osc_port", str(DEFAULT_OSC_PORT)),
            ("osc_enabled", "1"),
        ],
        440,
        400,
    )
    status = _table(
        base,
        "status",
        [("cue", "0"), ("applied", ""), ("error", ""), ("source", "build")],
        660,
        400,
    )

    go_dat = create_child(base, "executeDAT", "go_execute")
    place(go_dat, 880, 400)
    go_dat.text = _GO_EXECUTE
    for flag in ("tablechange", "tableChange", "frameend", "frameEnd", "active"):
        try:
            getattr(go_dat.par, flag).val = True
        except Exception:
            pass
    try:
        go_dat.par.dat = controls.path
    except Exception:
        pass
    set_par(go_dat, active=True)

    ext_dat = create_child(base, "textDAT", "CueDeckExt")
    place(ext_dat, 880, 560)
    ext_dat.text = _CUE_EXT
    try:
        base.par.extension1 = ext_dat
        base.par.promoteextension1 = True
    except Exception as exc:
        print(f"[phase6] extension wire: {exc}")

    # Optional parexec / execute fallback for environments without promote.
    pex = None
    for kind in ("parexecDAT", "executeDAT"):
        try:
            pex = create_child(base, kind, "param_exec")
            break
        except Exception:
            continue
    if pex is not None:
        place(pex, 880, 700)
        pex.text = _PARAM_EXEC
        try:
            set_par(pex, opexecute=True)
            pex.par.parms = "Go Goto Blackout Restore"
        except Exception:
            try:
                pex.par.par = base.path
            except Exception as exc:
                print(f"[phase6] param_exec wire: {exc}")

    devices = create_child(base, "tableDAT", "devices_ref")
    place(devices, 0, 200)
    src = p5.op("devices")
    if src is not None:
        try:
            devices.clear()
            for r in range(src.numRows):
                devices.appendRow([src[r, c].val for c in range(src.numCols)])
        except Exception:
            pass

    osc_port = DEFAULT_OSC_PORT
    try:
        osc_port = int(base.par.Oscport)
    except Exception:
        pass
    _wire_osc(base, osc_port)

    info = create_child(base, "textDAT", "README")
    place(info, 220, 200)
    info.text = (
        "Phase 6 — Cue Deck (Phase 5 transport)\n\n"
        "UI: select /project1/primus_phase6 → Cue page\n"
        "  GO          next cue\n"
        "  Cue # + Goto jump to cue number\n"
        "  Blackout / Restore\n\n"
        "OSC (UDP port %d) — same actions for show control:\n"
        "  /primus/cue/go\n"
        "  /primus/cue/goto <n>\n"
        "  /primus/cue/blackout <0|1>\n\n"
        "Shell: python3 builders/td_remote.py go\n"
        "       python3 builders/td_remote.py go --goto 3\n"
        "Edit the `cues` table for looks/targets.\n"
        % osc_port
    )

    # Apply cue 1 at build.
    try:
        ns = {"op": op, "project": project}  # noqa: F821
        exec(_CUE_API, ns)
        ns["apply_cue_row"](base, 1, source="build")
    except Exception as exc:
        print(f"[phase6] initial cue apply deferred: {exc}")

    summary = {
        "phase": 6,
        "phase5": PHASE5_PATH,
        "cues": cues.numRows - 1,
        "path": base.path,
        "osc_port": osc_port,
        "osc": ["/primus/cue/go", "/primus/cue/goto", "/primus/cue/blackout"],
    }
    try:
        from pathlib import Path

        Path(project.folder, "builders", ".td_phase6_build.json").write_text(  # noqa: F821
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        pass
    print(f"[phase6] built {base.path} cues={summary['cues']} OSC udp/{osc_port}")
    return f"{base.path} cues={summary['cues']} osc={osc_port}"


def go(base_path: str = f"{PARENT_PATH}/{BASE_NAME}"):
    """Textport helper: pulse GO."""
    prepare_build(globals())
    root = op(base_path)  # noqa: F821
    root.op("controls")["go", 1] = 1
