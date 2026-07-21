"""
Phase 5 - Multi-device scaling.

Builds one Base COMP per devices-table row, each with a Phase-3-style chain.

    exec(open(f'{project.folder}/builders/phase5_multidevice.py').read())
    build()

Edit `primus_phase5/devices`, then re-run build() to add/remove device chains.
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

from builders.lib.output_types import (  # noqa: E402
    OUTPUT_TYPES,
    default_virtual,
    layout_of,
    physical_pixels,
    resize_dims_for,
    validate_combined,
)
from builders.lib.serpentine import serpentine_rgb_reorder_indices  # noqa: E402
from builders.lib.td_builder import (  # noqa: E402
    prepare_build,
    clear_children,
    connect,
    ensure_base,
    init_device_table,
    place,
    set_par,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase5"

DEFAULT_ROWS = [
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

_PATTERN = r'''
def onCook(scriptOp):
    try:
        import numpy as np
        w = max(1, scriptOp.width)
        h = max(1, scriptOp.height)
        arr = np.zeros((h, w, 4), dtype=np.float32)
        if w == 1 and h == 1:
            arr[0, 0] = (1, 0, 0, 1)
        else:
            third = max(1, w // 3)
            arr[:, :third] = (1, 0, 0, 1)
            arr[:, third:2*third] = (0, 1, 0, 1)
            arr[:, 2*third:] = (0, 0, 1, 1)
        scriptOp.copyNumpyArray(arr)
    except Exception:
        pass
'''


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in name) or "device"


def _branch(comp, name, type_key, virtual, x0, y0):
    if physical_pixels(type_key) <= 0 or int(virtual) <= 0:
        null = comp.create(constantCHOP, f"{name}_empty")
        place(null, x0, y0)
        return null, 0
    v = int(virtual)
    w, h = resize_dims_for(type_key, v)
    pattern = comp.create(scriptTOP, f"{name}_pattern")
    place(pattern, x0, y0)
    pattern.par.resolutionw = 1 if v <= 1 else max(w * 3, 3)
    pattern.par.resolutionh = max(h, 1)
    pattern.text = _PATTERN
    pattern.par.cookalways = True
    try:
        resize = comp.create(resolutionTOP, f"{name}_resize")
    except Exception:
        resize = comp.create(transformTOP, f"{name}_resize")
    place(resize, x0 + 200, y0)
    set_par(resize, resolutionw=w, resolutionh=h)
    connect(pattern, resize)
    t2c = comp.create(topToCHOP, f"{name}_t2c")
    place(t2c, x0 + 400, y0)
    set_par(t2c, output="R G B")
    connect(resize, t2c)
    shuffle = comp.create(shuffleCHOP, f"{name}_shuf")
    place(shuffle, x0 + 600, y0)
    set_par(shuffle, method="sequencechannelsbysamples")
    connect(t2c, shuffle)
    last = shuffle
    if layout_of(type_key) == "grid" and v >= physical_pixels(type_key):
        cols, rows = OUTPUT_TYPES[type_key]["grid_size"]
        indices = serpentine_rgb_reorder_indices(cols, rows)
        reorder = comp.create(reorderCHOP, f"{name}_serp")
        place(reorder, x0 + 800, y0)
        set_par(reorder, order=" ".join(f"chan{i+1}" for i in indices))
        connect(shuffle, reorder)
        last = reorder
    return last, v * 3


def _build_device_comp(parent, row, index):
    name = _safe_name(row["name"])
    # destroy existing
    existing = parent.op(name)
    if existing:
        existing.destroy()
    comp = parent.create(baseCOMP, name)
    place(comp, (index % 4) * 300, -((index // 4) * 250))

    a0t, a1t = row["a0_type"], row["a1_type"]
    v0, v1 = int(row["a0_virtual"]), int(row["a1_virtual"])
    ok, total, msg = validate_combined(v0, v1)
    if row.get("recv_mode") == "combined" and not ok:
        err = comp.create(textDAT, "ERROR")
        err.text = msg
        print(f"[phase4] SKIP {name}: {msg}")
        return comp

    a0, n0 = _branch(comp, "a0", a0t, v0, 0, 100)
    a1, n1 = _branch(comp, "a1", a1t, v1, 0, -200)
    merge = comp.create(mergeCHOP, "merge_ab")
    place(merge, 1200, 0)
    connect(a0, merge, 0)
    connect(a1, merge, 1)

    black = comp.create(patternCHOP, "blackout_vals")
    place(black, 1000, -400)
    set_par(black, type="const", const=0, length=max(3, n0 + n1), channels=1)
    black_shuf = comp.create(shuffleCHOP, "blackout_shuf")
    place(black_shuf, 1200, -400)
    set_par(black_shuf, method="sequencechannelsbysamples")
    connect(black, black_shuf)

    switch = comp.create(switchCHOP, "out_switch")
    place(switch, 1400, 0)
    connect(merge, switch, 0)
    connect(black_shuf, switch, 1)

    ctrl = comp.create(tableDAT, "controls")
    place(ctrl, 0, 300)
    ctrl.clear()
    ctrl.appendRow(["param", "value"])
    ctrl.appendRow(["blackout", "0"])
    try:
        switch.par.index.expr = f"int(op('{ctrl.path}')['blackout',1])"
    except Exception:
        pass

    dmx = comp.create(dmxoutCHOP, "dmx_out")
    place(dmx, 1600, 0)
    set_par(
        dmx,
        interface="artnet",
        netaddress=row["ip"],
        universe=int(row["universe"]),
        rate=30,
    )
    connect(switch, dmx)

    meta = comp.create(tableDAT, "meta")
    place(meta, 200, 300)
    meta.clear()
    for k, v in row.items():
        meta.appendRow([k, str(v)])
    print(f"[phase4] device {name} ip={row['ip']} univ={row['universe']} ({msg})")
    return comp


def build(parent_path: str = PARENT_PATH, rows=None):
    prepare_build(globals())
    base = ensure_base(parent_path, BASE_NAME)
    # Preserve devices table if present
    devices = base.op("devices")
    if devices is None:
        devices = base.create(tableDAT, "devices")
        place(devices, 0, 400)
        init_device_table(devices, rows or DEFAULT_ROWS)
    else:
        # If empty header-only and rows provided, refill
        if devices.numRows <= 1 and rows:
            init_device_table(devices, rows)

    # Clear device comps only
    for child in list(base.children):
        if child.name not in ("devices", "controls", "README", "all_blackout"):
            if child.isCOMP:
                child.destroy()

    # Global blackout
    gctrl = base.op("controls")
    if gctrl is None:
        gctrl = base.create(tableDAT, "controls")
        place(gctrl, 200, 400)
        gctrl.clear()
        gctrl.appendRow(["param", "value"])
        gctrl.appendRow(["blackout_all", "0"])

    # Read rows
    data_rows = []
    for r in range(1, devices.numRows):
        data_rows.append({devices[0, c].val: devices[r, c].val for c in range(devices.numCols)})

    for i, row in enumerate(data_rows):
        comp = _build_device_comp(base, row, i)
        # Bind per-device blackout to OR of local and global
        try:
            sw = comp.op("out_switch")
            local = comp.op("controls")
            sw.par.index.expr = (
                f"1 if int(op('{gctrl.path}')['blackout_all',1]) else "
                f"int(op('{local.path}')['blackout',1])"
            )
        except Exception:
            pass

    info = base.op("README") or base.create(textDAT, "README")
    place(info, 0, 600)
    info.text = (
        "Phase 5 multi-device\n"
        "Edit `devices` table rows, re-run build().\n"
        "controls.blackout_all=1 blacks all devices.\n"
        "Per-device controls.blackout=1 for one unit.\n"
        "See handoffs/phase4_test.md"
    )
    print(f"[phase4] built {len(data_rows)} device chain(s) under {base.path}")
    return base
