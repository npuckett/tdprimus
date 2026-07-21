"""
Phase 6 - Cue system.

Builds content bank, cue table, Switch/Cross per device-output, and GO logic.

    exec(open(f'{project.folder}/builders/phase5_cues.py').read())
    build()

Pulse controls.go = 1 (or run go()) to advance. Untargeted devices hold last look.
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

from builders.lib.td_builder import (  # noqa: E402
    prepare_build,
    clear_children,
    connect,
    ensure_base,
    init_cue_table,
    init_device_table,
    place,
    set_par,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase6"

DEFAULT_DEVICES = [
    {
        "name": "dev_a",
        "ip": "192.168.1.100",
        "universe": "0",
        "recv_mode": "combined",
        "a0_type": "small_grid",
        "a0_count": "32",
        "a0_virtual": "1",
        "a1_type": "long_strip",
        "a1_count": "72",
        "a1_virtual": "72",
        "group": "cast",
    },
    {
        "name": "dev_b",
        "ip": "192.168.1.101",
        "universe": "1",
        "recv_mode": "combined",
        "a0_type": "small_grid",
        "a0_count": "32",
        "a0_virtual": "1",
        "a1_type": "long_strip",
        "a1_count": "72",
        "a1_virtual": "72",
        "group": "cast",
    },
]

DEFAULT_CUES = [
    {
        "cue": "1",
        "targets": "*",
        "a0_content": "red",
        "a1_content": "red",
        "fade": "1.0",
        "notes": "all red",
    },
    {
        "cue": "2",
        "targets": "group:cast",
        "a0_content": "green",
        "a1_content": "blue",
        "fade": "2.0",
        "notes": "cast green/blue",
    },
    {
        "cue": "3",
        "targets": "dev_a",
        "a0_content": "thirds",
        "a1_content": "thirds",
        "fade": "0.5",
        "notes": "only A",
    },
    {
        "cue": "4",
        "targets": "*",
        "a0_content": "black",
        "a1_content": "black",
        "fade": "0.3",
        "notes": "blackout cue",
    },
]

CONTENT_COLORS = {
    "red": (1, 0, 0),
    "green": (0, 1, 0),
    "blue": (0, 0, 1),
    "black": (0, 0, 0),
    "white": (1, 1, 1),
    "thirds": None,  # special script
}

_GO_EXECUTE = r'''
# DAT Execute - watches controls table for go pulse / cue index

def onTableChange(dat):
    try:
        go = int(dat['go', 1])
    except Exception:
        return
    if go != 1:
        return
    dat['go', 1] = 0
    root = dat.parent()
    _advance(root)

def _advance(root):
    cues = root.op('cues')
    state = root.op('cue_state')
    devices = root.op('devices')
    if cues is None or state is None:
        return
    try:
        idx = int(state['cue_index', 1])
    except Exception:
        idx = 0
    # cues row 0 = header; data starts at 1; idx is 0-based into data
    next_idx = idx + 1
    if next_idx >= cues.numRows:
        next_idx = 1
    state['cue_index', 1] = next_idx
    state['cue_number', 1] = cues[next_idx, 'cue'].val
    _apply_cue(root, next_idx)

def _apply_cue(root, row):
    cues = root.op('cues')
    devices = root.op('devices')
    targets = cues[row, 'targets'].val.strip()
    a0c = cues[row, 'a0_content'].val.strip()
    a1c = cues[row, 'a1_content'].val.strip()
    try:
        fade = float(cues[row, 'fade'].val)
    except Exception:
        fade = 1.0
    content = root.op('content')
    # Map content name -> switch index
    names = [content[0, c].val for c in range(1, content.numCols)] if False else []
    # content bank uses named Constant TOPs; switch indices stored in content_index table
    idx_table = root.op('content_index')
    def content_index(name):
        for r in range(1, idx_table.numRows):
            if idx_table[r, 0].val == name:
                return int(idx_table[r, 1].val)
        return 0

    a0i = content_index(a0c)
    a1i = content_index(a1c)

    for r in range(1, devices.numRows):
        name = devices[r, 'name'].val
        group = devices[r, 'group'].val
        if not _match(targets, name, group):
            continue
        safe = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
        dcomp = root.op(safe)
        if dcomp is None:
            continue
        for port, idx in (('a0', a0i), ('a1', a1i)):
            sw = dcomp.op(f'{port}_switch')
            cross = dcomp.op(f'{port}_cross')
            if sw is not None:
                # Crossfade: set cross.b index / cross factor via timer
                sw.par.index = idx
            if cross is not None:
                try:
                    cross.par.cross = 0
                    # Kick a ramp CHOP if present
                    ramp = dcomp.op(f'{port}_fade')
                    if ramp is not None:
                        ramp.par.reset.pulse()
                        ramp.par.length = max(0.01, fade)
                except Exception:
                    pass
            # Black content also forces blackout path
            if (port == 'a0' and a0c == 'black') or (port == 'a1' and a1c == 'black'):
                if a0c == 'black' and a1c == 'black':
                    try:
                        dcomp.op('controls')['blackout', 1] = 1
                    except Exception:
                        pass
            else:
                try:
                    dcomp.op('controls')['blackout', 1] = 0
                except Exception:
                    pass

def _match(targets, name, group):
    if targets == '*' or targets == '':
        return True
    for part in targets.split(','):
        part = part.strip()
        if part.startswith('group:'):
            if group == part.split(':', 1)[1]:
                return True
        elif part == name:
            return True
    return False
'''

_THIRDS = r'''
def onCook(scriptOp):
    try:
        import numpy as np
        w = max(3, scriptOp.width)
        h = max(1, scriptOp.height)
        arr = np.zeros((h, w, 4), dtype=np.float32)
        t = w // 3
        arr[:, :t] = (1, 0, 0, 1)
        arr[:, t:2*t] = (0, 1, 0, 1)
        arr[:, 2*t:] = (0, 0, 1, 1)
        scriptOp.copyNumpyArray(arr)
    except Exception:
        pass
'''


def build(parent_path: str = PARENT_PATH):
    prepare_build(globals())
    base = ensure_base(parent_path, BASE_NAME, recreate=True)

    devices = base.create(tableDAT, "devices")
    place(devices, 0, 600)
    init_device_table(devices, DEFAULT_DEVICES)

    cues = base.create(tableDAT, "cues")
    place(cues, 200, 600)
    init_cue_table(cues, DEFAULT_CUES)

    state = base.create(tableDAT, "cue_state")
    place(state, 400, 600)
    state.clear()
    state.appendRow(["param", "value"])
    state.appendRow(["cue_index", "0"])
    state.appendRow(["cue_number", "0"])

    controls = base.create(tableDAT, "controls")
    place(controls, 600, 600)
    controls.clear()
    controls.appendRow(["param", "value"])
    controls.appendRow(["go", "0"])
    controls.appendRow(["blackout_all", "0"])

    # Content bank
    content = base.create(baseCOMP, "content_bank")
    place(content, 0, 300)
    idx_table = base.create(tableDAT, "content_index")
    place(idx_table, 800, 600)
    idx_table.clear()
    idx_table.appendRow(["name", "index"])
    for i, (cname, rgb) in enumerate(CONTENT_COLORS.items()):
        idx_table.appendRow([cname, str(i)])
        if rgb is None:
            top = content.create(scriptTOP, cname)
            top.text = _THIRDS
            top.par.resolutionw = 24
            top.par.resolutionh = 1
            top.par.cookalways = True
        else:
            top = content.create(constantTOP, cname)
            set_par(top, colorr=rgb[0], colorg=rgb[1], colorb=rgb[2])
        place(top, (i % 6) * 150, -((i // 6) * 150))

    # Per-device: switch between content tops (select via Switch TOP) -> stub transport note
    # Full pixel transport reuses phase4 pattern at reduced fidelity: solid color tops
    # fed into a simplified chain (constant color -> dmx via topToChop on 1px).
    for di, row in enumerate(DEFAULT_DEVICES):
        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in row["name"])
        dcomp = base.create(baseCOMP, safe)
        place(dcomp, (di % 3) * 350, -200 - (di // 3) * 300)

        for port in ("a0", "a1"):
            sw = dcomp.create(switchTOP, f"{port}_switch")
            place(sw, 0, 100 if port == "a0" else -100)
            # Wire all content tops into switch inputs
            for i, cname in enumerate(CONTENT_COLORS.keys()):
                src = content.op(cname)
                if src:
                    connect(src, sw, i)
            # Cross TOP for fade (A=previous held via feedback is complex; use cross 0->1)
            cross = dcomp.create(crossTOP, f"{port}_cross")
            place(cross, 200, 100 if port == "a0" else -100)
            connect(sw, cross, 0)
            connect(sw, cross, 1)  # same until feedback added
            # 1px resize for virtual-ish solid
            try:
                resize = dcomp.create(resolutionTOP, f"{port}_resize")
            except Exception:
                resize = dcomp.create(transformTOP, f"{port}_resize")
            place(resize, 400, 100 if port == "a0" else -100)
            virt = int(row[f"{port}_virtual"])
            set_par(resize, resolutionw=max(1, virt), resolutionh=1)
            connect(cross, resize)
            t2c = dcomp.create(topToCHOP, f"{port}_t2c")
            place(t2c, 600, 100 if port == "a0" else -100)
            set_par(t2c, output="R G B")
            connect(resize, t2c)
            shuf = dcomp.create(shuffleCHOP, f"{port}_shuf")
            place(shuf, 800, 100 if port == "a0" else -100)
            set_par(shuf, method="sequencechannelsbysamples")
            connect(t2c, shuf)

        merge = dcomp.create(mergeCHOP, "merge_ab")
        place(merge, 1000, 0)
        connect(dcomp.op("a0_shuf"), merge, 0)
        connect(dcomp.op("a1_shuf"), merge, 1)

        black = dcomp.create(patternCHOP, "blackout_vals")
        place(black, 1000, -250)
        n = (int(row["a0_virtual"]) + int(row["a1_virtual"])) * 3
        set_par(black, type="const", const=0, length=max(3, n), channels=1)
        black_shuf = dcomp.create(shuffleCHOP, "blackout_shuf")
        place(black_shuf, 1200, -250)
        set_par(black_shuf, method="sequencechannelsbysamples")
        connect(black, black_shuf)

        out_sw = dcomp.create(switchCHOP, "out_switch")
        place(out_sw, 1400, 0)
        connect(merge, out_sw, 0)
        connect(black_shuf, out_sw, 1)

        dctrl = dcomp.create(tableDAT, "controls")
        place(dctrl, 0, 250)
        dctrl.clear()
        dctrl.appendRow(["param", "value"])
        dctrl.appendRow(["blackout", "0"])
        try:
            out_sw.par.index.expr = (
                f"1 if int(op('{controls.path}')['blackout_all',1]) else "
                f"int(op('{dctrl.path}')['blackout',1])"
            )
        except Exception:
            pass

        dmx = dcomp.create(dmxoutCHOP, "dmx_out")
        place(dmx, 1600, 0)
        set_par(
            dmx,
            interface="artnet",
            netaddress=row["ip"],
            universe=int(row["universe"]),
            rate=30,
        )
        connect(out_sw, dmx)

    go_dat = base.create(executeDAT, "go_execute")
    place(go_dat, 1000, 600)
    go_dat.text = _GO_EXECUTE
    try:
        go_dat.par.dat = controls.path
        go_dat.par.tablechange = True
    except Exception:
        # Older TD: wire manually
        pass

    # Helper textDAT with go() callable instructions
    helpers = base.create(textDAT, "go_helper")
    place(helpers, 1200, 600)
    helpers.text = (
        "# In Textport:\n"
        f"op('{controls.path}')['go',1] = 1\n"
        "# or: op('/project1/primus_phase6').ext.go() if extension installed\n"
    )

    info = base.create(textDAT, "README")
    place(info, 0, 800)
    info.text = (
        "Phase 6 cues\n"
        "Set controls.go=1 to advance.\n"
        "targets: * | group:NAME | deviceName (comma-separated).\n"
        "Black cue forces per-device blackout zeros.\n"
        "See handoffs/phase5_test.md"
    )
    print(f"[phase5] built {base.path}")
    return base


def go(base_path: str = f"{PARENT_PATH}/{BASE_NAME}"):
    """Convenience for Textport: go()"""
    prepare_build(globals())
    root = op(base_path)
    root.op("controls")["go", 1] = 1
