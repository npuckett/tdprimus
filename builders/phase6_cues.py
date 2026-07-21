"""Phase 6 — cue table + GO driving Phase 5 device sampling/sources."""

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

CUE_COLS = (
    "cue", "targets", "a0_content", "a1_content",
    "brightness", "hue_shift", "blackout", "fade", "notes",
)

# Workshop defaults match Phase 5 dual-device names/groups.
DEFAULT_CUES = [
    {
        "cue": "1", "targets": "*",
        "a0_content": "demo", "a1_content": "demo",
        "brightness": "0.1", "hue_shift": "0", "blackout": "0",
        "fade": "0", "notes": "all → demo bus (same family)",
    },
    {
        "cue": "2", "targets": "*",
        "a0_content": "alt", "a1_content": "alt",
        "brightness": "0.1", "hue_shift": "0.45", "blackout": "0",
        "fade": "0", "notes": "all → alt bus + hue",
    },
    {
        "cue": "3", "targets": "primus_a",
        "a0_content": "demo", "a1_content": "demo",
        "brightness": "0.1", "hue_shift": "0", "blackout": "0",
        "fade": "0", "notes": "only A15 → demo",
    },
    {
        "cue": "4", "targets": "primus_b",
        "a0_content": "alt", "a1_content": "alt",
        "brightness": "0.15", "hue_shift": "0.45", "blackout": "0",
        "fade": "0", "notes": "only A13 → alt",
    },
    {
        "cue": "5", "targets": "*",
        "a0_content": "black", "a1_content": "black",
        "brightness": "0", "hue_shift": "0", "blackout": "1",
        "fade": "0", "notes": "blackout both",
    },
]

SOURCE_KEYS = ("demo", "alt", "movie", "ext")

_GO_EXECUTE = r'''
def onTableChange(dat):
    _maybe_go(dat)

def onFrameEnd(frame):
    # Also poll so shell/agents can pulse go without relying on table callbacks.
    root = me.parent()
    controls = root.op("controls")
    if controls is not None:
        _maybe_go(controls)
    _poll_shell_cmd(root)

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
        if (data.get("cmd") or "").lower() == "go":
            controls = root.op("controls")
            if controls is not None:
                controls["go", 1] = 1
    except Exception as exc:
        print("[phase6] cue cmd failed:", exc)

def _maybe_go(dat):
    try:
        go = int(float(dat["go", 1]))
    except Exception:
        return
    if go != 1:
        return
    dat["go", 1] = 0
    _advance(dat.parent())

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

def _apply_cue(root, row):
    p5 = _phase5()
    if p5 is None:
        print("[phase6] primus_phase5 missing — build Phase 5 first")
        _set_cell(root.op("cue_state"), "last_error", "primus_phase5 missing")
        return
    devices = p5.op("devices")
    media = p5.op("SharedMedia")
    cues = root.op("cues")
    if devices is None or cues is None:
        return
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
    applied = []
    for r in range(1, devices.numRows):
        # devices table is column-header style from Phase 5
        cols = {devices[0, c].val: c for c in range(devices.numCols)}
        def col(key, default=""):
            c = cols.get(key)
            if c is None:
                return default
            return devices[r, c].val
        name = col("name")
        group = col("group", "default")
        active = col("active", "1")
        if active != "1":
            continue
        if not _match(targets, name, group):
            continue
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name) or "device"
        dcomp = p5.op(safe)
        if dcomp is None:
            print("[phase6] missing device COMP", safe)
            continue
        sample = dcomp.op("sampling")
        b0 = _apply_source(dcomp, media, "a0", a0c)
        b1 = _apply_source(dcomp, media, "a1", a1c)
        blackout = 1 if (cue_black or (b0 and b1)) else 0
        _set_cell(sample, "blackout", blackout)
        _set_cell(sample, "brightness", 0.0 if blackout else brightness)
        _set_cell(sample, "hue_shift", hue_shift)
        applied.append(safe)
    state = root.op("cue_state")
    _set_cell(state, "last_applied", ",".join(applied) if applied else "(none)")
    _set_cell(state, "last_error", "")
    print("[phase6] applied cue row", row, "→", applied)

def _advance(root):
    cues = root.op("cues")
    state = root.op("cue_state")
    if cues is None or state is None or cues.numRows < 2:
        return
    try:
        # cue_index stores last applied table row (1..n-1); 0 means none yet.
        last = int(float(_cell(state, "cue_index", "0")))
    except Exception:
        last = 0
    next_row = last + 1
    if next_row >= cues.numRows:
        next_row = 1
    _set_cell(state, "cue_index", next_row)
    _set_cell(state, "cue_number", cues[next_row, "cue"].val)
    _apply_cue(root, next_row)
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


def build(parent_path=PARENT_PATH, **_ignored):
    """Build Phase 6 cue engine that drives an existing Phase 5 network."""
    prepare_build(globals())
    p5 = td_op(PHASE5_PATH)
    if p5 is None:
        raise RuntimeError("build Phase 5 first — Phase 6 drives /project1/primus_phase5")

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 400, -700)

    cues = create_child(base, "tableDAT", "cues")
    place(cues, 0, 400)
    _init_cues(cues, DEFAULT_CUES)

    state = _table(
        base,
        "cue_state",
        [("cue_index", "0"), ("cue_number", "0"), ("last_applied", ""), ("last_error", "")],
        220,
        400,
    )
    controls = _table(
        base,
        "controls",
        [("go", "0"), ("blackout_all", "0")],
        440,
        400,
    )

    go_dat = create_child(base, "executeDAT", "go_execute")
    place(go_dat, 660, 400)
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

    # Mirror Phase 5 device names for operator reference (not the live transport table).
    devices = create_child(base, "tableDAT", "devices_ref")
    place(devices, 0, 200)
    src = p5.op("devices")
    if src is not None:
        devices.text = src.text if hasattr(src, "text") else ""
        try:
            devices.clear()
            for r in range(src.numRows):
                devices.appendRow([src[r, c].val for c in range(src.numCols)])
        except Exception:
            pass

    info = create_child(base, "textDAT", "README")
    place(info, 220, 200)
    info.text = (
        "Phase 6 — cues over Phase 5\n"
        "Requires /project1/primus_phase5.\n"
        "Advance: set controls.go = 1  (or Textport: op('/project1/primus_phase6/controls')['go',1]=1)\n"
        "targets: * | group:NAME | deviceName (comma-separated).\n"
        "a0_content / a1_content: demo | alt | movie | ext | black\n"
        "brightness 0..1, hue_shift, blackout apply to matched Phase 5 device COMPs.\n"
        "Untargeted devices keep their last look.\n"
    )

    # Apply cue 1 immediately so the network matches the cue list start.
    try:
        ns = {"op": op, "me": go_dat, "project": project}  # noqa: F821
        exec(_GO_EXECUTE, ns)
        ns["_apply_cue"](base, 1)
        for row in range(1, state.numRows):
            key = state[row, 0].val
            if key == "cue_index":
                state[row, 1] = "1"
            elif key == "cue_number":
                state[row, 1] = str(cues[1, "cue"].val)
    except Exception as exc:
        print(f"[phase6] initial cue apply deferred: {exc}")

    summary = {
        "phase": 6,
        "phase5": PHASE5_PATH,
        "cues": cues.numRows - 1,
        "path": base.path,
    }
    try:
        from pathlib import Path

        Path(project.folder, "builders", ".td_phase6_build.json").write_text(  # noqa: F821
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        pass
    print(f"[phase6] built {base.path} ({summary['cues']} cues) → drives {PHASE5_PATH}")
    return f"{base.path} cues={summary['cues']}"


def go(base_path: str = f"{PARENT_PATH}/{BASE_NAME}"):
    """Textport helper: pulse GO."""
    prepare_build(globals())
    root = op(base_path)  # noqa: F821
    root.op("controls")["go", 1] = 1
