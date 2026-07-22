"""
Phase 9 — PrimusOutput + PrimusManager packaging (no cue deck).

Builds drop-in Base COMPs with Custom Parameters and the Phase-5 ArtDmx path.
Export to .tox is documented in tox/README.md (manual TD export).

    exec(open(f'{project.folder}/builders/phase9_components.py').read())
    build()

Or: python3 builders/td_remote.py build 9
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

from builders.lib.primus_output_network import (  # noqa: E402
    OUTPUT_TYPE_LABELS,
    OUTPUT_TYPE_NAMES,
    SAMPLE_MODE_NAMES,
    build_output_network,
    normalize_profile,
    safe_name,
)
from builders.lib.td_builder import (  # noqa: E402
    create_child,
    ensure_base,
    place,
    prepare_build,
    set_par,
    td_op,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase9"
DEFAULT_BIND_IP = "192.168.8.199"

DEVICE_COLS = (
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
    "a0_source",
    "a1_source",
    "group",
    "short_name",
    "firmware",
)

DEFAULT_OUTPUTS = [
    {
        "name": "primus_a",
        "active": "1",
        "ip": "192.168.8.166",
        "bind_ip": DEFAULT_BIND_IP,
        "universe": "0",
        "recv_mode": "split",
        "a0_type": "small_grid",
        "a0_virtual": "1",
        "a1_type": "long_strip",
        "a1_virtual": "72",
        "group": "default",
    },
    {
        "name": "primus_b",
        "active": "1",
        "ip": "192.168.8.164",
        "bind_ip": DEFAULT_BIND_IP,
        "universe": "0",
        "recv_mode": "split",
        "a0_type": "small_grid",
        "a0_virtual": "1",
        "a1_type": "long_strip",
        "a1_virtual": "72",
        "group": "default",
    },
]

# Embedded Extension sources (also mirrored in extensions/).
_OUTPUT_EXT = Path(__file__).resolve().parents[1].joinpath(
    "extensions", "PrimusOutputExt.py"
).read_text(encoding="utf-8")

_MANAGER_EXT = Path(__file__).resolve().parents[1].joinpath(
    "extensions", "PrimusManagerExt.py"
).read_text(encoding="utf-8")

_MANAGER_API = r'''
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

def _ensure_path():
    import sys
    try:
        root = project.folder
    except Exception:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)
    return root

def _reload_discover():
    import importlib, sys
    _ensure_path()
    for key in list(sys.modules):
        if key == "builders" or key.startswith("builders."):
            del sys.modules[key]
    importlib.invalidate_caches()
    from builders.discover_device import discover, enrich
    return discover, enrich

def _type_defaults(ports):
    by_port = {p.get("port"): p for p in (ports or [])}
    def one(idx, fallback_type, fallback_virt):
        p = by_port.get(idx) or {}
        typ = p.get("type") or fallback_type
        if isinstance(typ, str) and typ.startswith("id:"):
            typ = fallback_type
        phys = {"none":0,"short_strip":30,"long_strip":72,"grid":64,"small_grid":32,"extra_long_strip":122}.get(typ, 0)
        virt = p.get("virtual")
        if virt is None:
            virt = fallback_virt
        return typ, phys, int(virt)
    a0t, a0c, a0v = one(0, "small_grid", 1)
    a1t, a1c, a1v = one(1, "long_strip", 72)
    return a0t, a0c, a0v, a1t, a1c, a1v

def _safe_name(short_name, used):
    base = "".join(c if c.isalnum() or c == "_" else "_" for c in (short_name or "node")) or "node"
    if base[0].isdigit():
        base = "n_" + base
    name = base
    n = 2
    while name in used:
        name = "%s_%d" % (base, n)
        n += 1
    used.add(name)
    return name

def rescan(root=None, source="api"):
    root = root or me.parent()
    controls = root.op("controls")
    devices = root.op("devices")
    status = root.op("status")
    bind_ip = ""
    try:
        bind_ip = str(root.par.Bindip.eval()).strip()
    except Exception:
        bind_ip = str(_cell(controls, "bind_ip", "192.168.8.199")).strip()
    try:
        timeout = float(_cell(controls, "timeout", "2"))
    except Exception:
        timeout = 2.0
    _set_cell(status, "state", "scanning")
    _set_cell(status, "bind_ip", bind_ip)
    _set_cell(status, "last_source", source)
    print("[PrimusManager] ArtPoll bind=%s timeout=%.1fs (%s)" % (bind_ip, timeout, source))
    try:
        discover, enrich = _reload_discover()
        nodes = discover(timeout=timeout, bind_ip=bind_ip or None)
    except Exception as exc:
        print("[PrimusManager] discover failed:", exc)
        _set_cell(status, "state", "error")
        _set_cell(status, "last_error", str(exc))
        try:
            root.par.Status = "error: " + str(exc)[:60]
        except Exception:
            pass
        return False

    while devices.numRows > 1:
        devices.deleteRow(1)
    used_names = set()
    primus_n = 0
    other_n = 0
    cols = [devices[0, c].val for c in range(devices.numCols)]
    for raw in nodes:
        node = enrich(raw)
        if not node.get("is_primus"):
            other_n += 1
            continue
        primus_n += 1
        a0t, a0c, a0v, a1t, a1c, a1v = _type_defaults(node.get("ports"))
        mode = node.get("receive_mode") or "split"
        univ = node.get("base_universe")
        if univ is None:
            univ = 0
        short = node.get("short_name") or node.get("ip")
        name = _safe_name(short, used_names)
        row = {
            "name": name,
            "active": "1",
            "ip": node.get("ip", ""),
            "bind_ip": bind_ip,
            "universe": str(univ),
            "recv_mode": mode,
            "a0_type": a0t,
            "a0_count": str(a0c),
            "a0_virtual": str(a0v),
            "a1_type": a1t,
            "a1_count": str(a1c),
            "a1_virtual": str(a1v),
            "a0_source": "ext",
            "a1_source": "ext",
            "group": "default",
            "short_name": short,
            "firmware": str(node.get("firmware_version") or ""),
        }
        devices.appendRow([str(row.get(c, "")) for c in cols])
    msg = "found %d Primus, %d other" % (primus_n, other_n)
    _set_cell(status, "state", "ok")
    _set_cell(status, "last_error", "")
    _set_cell(status, "primus", primus_n)
    _set_cell(status, "other", other_n)
    try:
        root.par.Status = msg
    except Exception:
        pass
    print("[PrimusManager]", msg)
    try:
        from pathlib import Path
        import json, time
        Path(project.folder, "builders", ".td_phase9_discover.json").write_text(
            json.dumps({
                "phase": 9, "bind_ip": bind_ip, "primus": primus_n, "other": other_n,
                "ts": time.time(),
            }, indent=2) + "\n"
        )
    except Exception:
        pass
    return True

def _apply_device_row(comp, devices, r, mgr_path, place=False, index=0):
    """Refresh Device pars on an Output from a devices table row."""
    name = devices[r, "name"].val
    try:
        comp.par.Ip = devices[r, "ip"].val
        comp.par.Universe = int(devices[r, "universe"].val or 0)
        comp.par.Recvmode = devices[r, "recv_mode"].val or "split"
        comp.par.A0type = devices[r, "a0_type"].val
        comp.par.A1type = devices[r, "a1_type"].val
        comp.par.A0virtual = int(devices[r, "a0_virtual"].val or 1)
        comp.par.A1virtual = int(devices[r, "a1_virtual"].val or 1)
        comp.par.Devicename = name
        comp.par.Managerpath = mgr_path
        comp.par.Active = str(devices[r, "active"].val) in ("1", "true", "True")
        comp.par.display = True
        comp.allowCooking = True
        if place:
            comp.nodeX = 400 + (index % 3) * 400
            comp.nodeY = -(index // 3) * 350
    except Exception as e:
        print("[PrimusManager] param bind", e)

def create_outputs(root=None):
    """Add-missing / sync Outputs as siblings of PrimusManager (never destroy)."""
    root = root or me.parent()  # PrimusManager
    parent = root.parent()  # primus_phase9
    devices = root.op("devices")
    template = root.op("PrimusOutput") or (parent.op("PrimusOutput") if parent else None)
    if not devices or parent is None or template is None:
        print("[PrimusManager] missing devices / parent / PrimusOutput template")
        return 0
    mgr_path = root.path
    created = 0
    updated = 0
    skipped = 0
    for r in range(1, devices.numRows):
        name = devices[r, "name"].val
        safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name) or ("out%d" % r)
        existing = parent.op(safe)
        if existing is not None and existing.isCOMP and existing.op("artnet_cook") is not None:
            _apply_device_row(existing, devices, r, mgr_path, place=False)
            updated += 1
            continue
        if existing is not None:
            # Name collision with a non-Output COMP — leave it alone.
            skipped += 1
            print("[PrimusManager] skip %s (name taken, not a PrimusOutput)" % safe)
            continue
        copy = parent.copy(template, name=safe)
        _apply_device_row(copy, devices, r, mgr_path, place=True, index=created + updated)
        created += 1
    msg = "created=%d updated=%d skipped=%d" % (created, updated, skipped)
    print("[PrimusManager] sync outputs under %s — %s" % (parent.path, msg))
    try:
        root.par.Status = msg
    except Exception:
        pass
    return created
'''

_MANAGER_EXECUTE = r'''
def onFrameStart(frame):
    root = me.parent()
    controls = root.op("controls")
    if controls is None:
        return
    # Sync Bindip into controls for discover helpers
    try:
        bind = str(root.par.Bindip.eval()).strip()
        for row in range(1, controls.numRows):
            if controls[row, 0].val == "bind_ip":
                controls[row, 1] = bind
                break
    except Exception:
        pass
    # Shell bridge: builders/.td_manager_cmd.json {"cmd":"rescan"|"create_outputs"}
    try:
        from pathlib import Path
        import json
        cmd_path = Path(project.folder) / "builders" / ".td_manager_cmd.json"
        if cmd_path.exists():
            raw = cmd_path.read_text(encoding="utf-8").strip()
            if raw and raw != "{}":
                data = json.loads(raw)
                action = (data.get("cmd") or "").lower()
                api = root.op("manager_api")
                if action == "rescan" and api is not None:
                    api.module.rescan(root, source="shell")
                elif action in ("create_outputs", "createoutputs") and api is not None:
                    api.module.create_outputs(root)
                try:
                    cmd_path.write_text("{}", encoding="utf-8")
                except Exception:
                    pass
    except Exception as exc:
        print("[PrimusManager] shell cmd:", exc)
    rescan_flag = "0"
    create_flag = "0"
    for row in range(1, controls.numRows):
        if controls[row, 0].val == "rescan":
            rescan_flag = controls[row, 1].val
        elif controls[row, 0].val == "create_outputs":
            create_flag = controls[row, 1].val
    api = root.op("manager_api")
    if rescan_flag == "1":
        for row in range(1, controls.numRows):
            if controls[row, 0].val == "rescan":
                controls[row, 1] = "0"
                break
        if api is not None:
            try:
                api.module.rescan(root, source="pulse")
            except Exception as exc:
                print("[PrimusManager] rescan error:", exc)
    if create_flag == "1":
        for row in range(1, controls.numRows):
            if controls[row, 0].val == "create_outputs":
                controls[row, 1] = "0"
                break
        if api is not None:
            try:
                api.module.create_outputs(root)
            except Exception as exc:
                print("[PrimusManager] create_outputs error:", exc)
'''

def _add_custom_pars(comp, specs, page_name="Primus"):
    """specs: list of (style, name, default, label, extras_dict)."""
    page = None
    try:
        page = comp.appendCustomPage(page_name)
    except Exception:
        for p in comp.customPages:
            if p.name == page_name:
                page = p
                break
    if page is None:
        print(f"[phase9] could not create custom page {page_name!r} on {comp}")
        return
    for style, name, default, label, extras in specs:
        extras = extras or {}
        try:
            if style == "header":
                try:
                    page.appendHeader(name if name else label, label=label or name)
                except Exception:
                    pass
                continue
            if style == "str":
                p = page.appendStr(name, label=label)
                p.val = default
            elif style == "int":
                p = page.appendInt(name, label=label)
                p.val = default
            elif style == "float":
                p = page.appendFloat(name, label=label)
                p.val = default
                if "min" in extras:
                    try:
                        p.min = extras["min"]
                        p.normMin = extras["min"]
                    except Exception:
                        pass
                if "max" in extras:
                    try:
                        p.max = extras["max"]
                        p.normMax = extras["max"]
                        p.clampMax = True
                    except Exception:
                        pass
            elif style == "menu":
                p = page.appendMenu(name, label=label)
                names = list(extras.get("names") or [])
                labels = list(extras.get("labels") or names)
                try:
                    p.menuNames = names
                    p.menuLabels = labels
                except Exception:
                    try:
                        p.menuNames = tuple(names)
                        p.menuLabels = tuple(labels)
                    except Exception as e2:
                        print(f"[phase9] menu {name} names: {e2}")
                try:
                    if default in names:
                        p.val = default
                    elif default in labels:
                        p.val = names[labels.index(default)]
                    else:
                        p.val = names[0] if names else default
                except Exception as e3:
                    print(f"[phase9] menu {name} val: {e3}")
            elif style == "pulse":
                p = page.appendPulse(name, label=label)
            elif style == "toggle":
                p = page.appendToggle(name, label=label)
                p.val = default
            else:
                continue
        except Exception as e:
            print(f"[phase9] par {name}: {e}")


def _type_menu():
    return {"names": OUTPUT_TYPE_NAMES, "labels": OUTPUT_TYPE_LABELS}


def _media_slot_menu(default="demo"):
    # Per strip: demo fallback or that strip's own media1 / media2 inputs.
    names = ["demo", "media1", "media2"]
    labels = ["Demo fallback", "Media 1", "Media 2"]
    return {"names": names, "labels": labels, "default": default}


def _attach_ext(comp, dat_name, text):
    ext_dat = create_child(comp, "textDAT", dat_name)
    place(ext_dat, 0, 400)
    ext_dat.text = text
    try:
        comp.par.extension1 = ext_dat
        comp.par.promoteextension1 = True
    except Exception as e:
        print(f"[phase9] attach {dat_name}: {e}")
    return ext_dat


def _build_output_template(parent, profile=None, look_index=0, as_template=True):
    name = "PrimusOutput" if as_template else safe_name((profile or {}).get("name", "PrimusOutput"))
    existing = parent.op(name)
    if existing is not None and as_template:
        try:
            existing.destroy()
        except Exception:
            pass
    tmpl = create_child(parent, "baseCOMP", name)
    place(tmpl, 400 if as_template else 0, -100 if as_template else 0)

    row = normalize_profile(profile)
    # --- Device page ---
    _add_custom_pars(
        tmpl,
        [
            ("toggle", "Active", 1 if row["active"] == "1" else 0, "Active", {}),
            ("str", "Ip", row["ip"], "IP", {}),
            ("str", "Devicename", row["name"], "Device Name", {}),
            ("int", "Universe", int(row["universe"] or 0), "Universe", {}),
            (
                "menu",
                "Recvmode",
                row["recv_mode"] or "split",
                "Receive Mode",
                {"names": ["split", "combined"], "labels": ["Split", "Combined"]},
            ),
            ("menu", "A0type", row["a0_type"], "A0 Type", _type_menu()),
            ("menu", "A1type", row["a1_type"], "A1 Type", _type_menu()),
            ("int", "A0virtual", int(row["a0_virtual"] or 1), "A0 Virtual Px", {}),
            ("int", "A1virtual", int(row["a1_virtual"] or 72), "A1 Virtual Px", {}),
            ("str", "Managerpath", "", "Manager Path", {}),
            ("str", "Bindip", "", "Bind IP Override", {}),
        ],
        page_name="Device",
    )
    # --- Media page ---
    _add_custom_pars(
        tmpl,
        [
            (
                "menu",
                "A0media",
                "media1",
                "A0 Source",
                _media_slot_menu("media1"),
            ),
            (
                "menu",
                "A1media",
                "media1",
                "A1 Source",
                _media_slot_menu("media1"),
            ),
        ],
        page_name="Media",
    )
    # --- Look page ---
    _add_custom_pars(
        tmpl,
        [
            ("float", "Brightness", 0.1, "Brightness", {"min": 0.0, "max": 1.0}),
            ("float", "Hueshift", 0.0 if look_index % 2 == 0 else 0.45, "Hue Shift", {"min": 0.0, "max": 1.0}),
            ("toggle", "Blackout", 0, "Blackout", {}),
            (
                "menu",
                "A0samplemode",
                "point",
                "A0 Sample Mode",
                {"names": SAMPLE_MODE_NAMES, "labels": SAMPLE_MODE_NAMES},
            ),
            (
                "menu",
                "A1samplemode",
                "hline",
                "A1 Sample Mode",
                {"names": SAMPLE_MODE_NAMES, "labels": SAMPLE_MODE_NAMES},
            ),
            ("float", "A0u", 0.35, "A0 U", {"min": 0.0, "max": 1.0}),
            ("float", "A0v", 0.35, "A0 V", {"min": 0.0, "max": 1.0}),
            ("float", "A1u", 0.0, "A1 U", {"min": 0.0, "max": 1.0}),
            ("float", "A1v", 0.35, "A1 V", {"min": 0.0, "max": 1.0}),
            ("float", "A1u1", 1.0, "A1 U1", {"min": 0.0, "max": 1.0}),
            ("float", "A1v1", 0.35, "A1 V1", {"min": 0.0, "max": 1.0}),
        ],
        page_name="Look",
    )
    # --- Actions page ---
    _add_custom_pars(
        tmpl,
        [
            ("pulse", "Pushconfig", None, "Push Config", {}),
            ("pulse", "Identify", None, "Identify (white)", {}),
        ],
        page_name="Actions",
    )

    build_output_network(tmpl, row, look_index=look_index)
    _attach_ext(tmpl, "PrimusOutputExt", _OUTPUT_EXT)

    if as_template:
        try:
            tmpl.par.display = True
            tmpl.allowCooking = True
        except Exception:
            pass
    return tmpl


def _build_media_bus(root, name: str = "PrimusMediaBus"):
    """Self-contained four-out generative bus (optional .tox / workshop helper)."""
    bus = create_child(root, "baseCOMP", name)
    place(bus, -500, 0)
    readme = create_child(bus, "textDAT", "README")
    place(readme, 0, 200)
    readme.text = (
        "PrimusMediaBus — optional demo sources for PrimusOutput.\n"
        "Export as tox/PrimusMediaBus.tox for Palette demos.\n"
        "Show content should wire directly into Output inputs 1–4.\n\n"
        "outs → Output slots:\n"
        "  out1  noise           → a0_media1\n"
        "  out2  gradient        → a0_media2\n"
        "  out3  solid wash      → a1_media1\n"
        "  out4  alt gradient    → a1_media2\n"
    )

    # media1 — noise
    try:
        m1 = create_child(bus, "noiseTOP", "gen1")
        set_par(m1, type="sparse", period=4)
    except Exception:
        m1 = create_child(bus, "scriptTOP", "gen1")
        cb = create_child(bus, "textDAT", "gen1_cb")
        from builders.lib.primus_output_network import _GRADIENT_CALLBACKS

        cb.text = _GRADIENT_CALLBACKS
        set_par(m1, callbacks=cb.path, cookalways=True)
        m1.store("speed", 0.55)
        m1.store("phase", 0.0)
    place(m1, 0, 100)

    # media2 — gradient
    from builders.lib.primus_output_network import _GRADIENT_CALLBACKS, _force_res

    m2_cb = create_child(bus, "textDAT", "gen2_cb")
    m2_cb.text = _GRADIENT_CALLBACKS
    m2 = create_child(bus, "scriptTOP", "gen2")
    place(m2, 0, -20)
    set_par(m2, callbacks=m2_cb.path, cookalways=True)
    _force_res(m2, 512, 96)
    m2.store("speed", 0.28)
    m2.store("phase", 0.15)

    # media3 — solid / slow pulse via constant + level expression fallback
    try:
        m3 = create_child(bus, "constantTOP", "gen3")
        set_par(m3, colorr=0.2, colorg=0.6, colorb=1.0)
    except Exception:
        m3 = create_child(bus, "scriptTOP", "gen3")
        cb3 = create_child(bus, "textDAT", "gen3_cb")
        cb3.text = _GRADIENT_CALLBACKS
        set_par(m3, callbacks=cb3.path, cookalways=True)
        m3.store("speed", 0.05)
        m3.store("phase", 0.7)
    place(m3, 0, -140)

    # media4 — alt gradient
    m4_cb = create_child(bus, "textDAT", "gen4_cb")
    m4_cb.text = _GRADIENT_CALLBACKS
    m4 = create_child(bus, "scriptTOP", "gen4")
    place(m4, 0, -260)
    set_par(m4, callbacks=m4_cb.path, cookalways=True)
    _force_res(m4, 512, 96)
    m4.store("speed", 0.42)
    m4.store("phase", 0.55)

    outs = []
    for i, src, y in (
        (1, m1, 100),
        (2, m2, -20),
        (3, m3, -140),
        (4, m4, -260),
    ):
        null = create_child(bus, "nullTOP", f"out{i}")
        place(null, 220, y)
        try:
            null.inputConnectors[0].connect(src)
            null.viewer = True
        except Exception:
            pass
        # COMP output connector for Palette wiring.
        try:
            out_op = bus.op(f"comp_out{i}") or create_child(bus, "outTOP", f"comp_out{i}")
            place(out_op, 400, y)
            out_op.inputConnectors[0].connect(null)
        except Exception:
            pass
        outs.append(null)

    frame = create_child(bus, "executeDAT", "frame_cook")
    place(frame, 0, 280)
    frame.text = (
        "def onFrameStart(frame):\n"
        "    parent = me.parent()\n"
        "    for name in ('gen1', 'gen2', 'gen3', 'gen4'):\n"
        "        top = parent.op(name)\n"
        "        if top is None: continue\n"
        "        try: top.cook(force=True)\n"
        "        except Exception: pass\n"
    )
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(frame.par, flag).val = True
        except Exception:
            pass
    set_par(frame, framestart=True, active=True)
    try:
        bus.par.display = True
        bus.allowCooking = True
    except Exception:
        pass
    return bus, outs


def _init_devices(table, rows):
    table.clear()
    table.appendRow(list(DEVICE_COLS))
    for row in rows:
        norm = normalize_profile(row)
        # Expand to DEVICE_COLS (includes source/firmware extras)
        full = {c: "" for c in DEVICE_COLS}
        full.update(norm)
        full["a0_source"] = str(row.get("a0_source", "ext"))
        full["a1_source"] = str(row.get("a1_source", "ext"))
        full["short_name"] = str(row.get("short_name", norm["name"]))
        full["firmware"] = str(row.get("firmware", ""))
        table.appendRow([str(full.get(c, "")) for c in DEVICE_COLS])


def _silence_prior_senders():
    """Stop earlier phase ArtDmx cooks so Phase 9 owns the wire during tests."""
    for name in (
        "primus_phase1",
        "primus_phase2",
        "primus_phase3",
        "primus_phase4",
        "primus_phase5",
    ):
        try:
            base = td_op(f"/project1/{name}")
            if base is None:
                continue
            # Phase 5: mute each device sender
            for child in list(base.children):
                if not child.isCOMP:
                    continue
                sender = child.op("artnet_cook")
                if sender is not None:
                    set_par(sender, cookalways=False)
                frame = child.op("frame_cook")
                if frame is not None:
                    set_par(frame, active=False)
            sender = base.op("artnet_cook")
            if sender is not None:
                set_par(sender, cookalways=False)
            print(f"[phase9] silenced {name}")
        except Exception as exc:
            print(f"[phase9] could not silence {name}: {exc}")


def build(parent_path: str = PARENT_PATH, **_ignored):
    prepare_build(globals())
    _silence_prior_senders()
    root = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(root, 0, -1100)

    # --- Manager ---
    mgr = create_child(root, "baseCOMP", "PrimusManager")
    place(mgr, 0, 0)
    _add_custom_pars(
        mgr,
        [
            ("str", "Bindip", DEFAULT_BIND_IP, "Bind IP", {}),
            ("float", "Sendfps", 30.0, "Send FPS", {"min": 1.0, "max": 60.0}),
            ("str", "Status", "idle", "Status", {}),
        ],
        page_name="Network",
    )
    _add_custom_pars(
        mgr,
        [
            ("float", "Brightness", 1.0, "Brightness Scale", {"min": 0.0, "max": 1.0}),
            ("pulse", "Blackoutall", None, "Blackout All", {}),
        ],
        page_name="Master",
    )
    _add_custom_pars(
        mgr,
        [
            ("pulse", "Rescan", None, "Rescan Network", {}),
            ("pulse", "Createoutputs", None, "Create / Sync Outputs", {}),
        ],
        page_name="Discovery",
    )

    devices = create_child(mgr, "tableDAT", "devices")
    place(devices, 0, 200)
    _init_devices(devices, DEFAULT_OUTPUTS)

    controls = create_child(mgr, "tableDAT", "controls")
    place(controls, 220, 200)
    controls.clear()
    controls.appendRow(["param", "value"])
    controls.appendRow(["bind_ip", DEFAULT_BIND_IP])
    controls.appendRow(["timeout", "2"])
    controls.appendRow(["rescan", "0"])
    controls.appendRow(["create_outputs", "0"])
    controls.appendRow(["blackout_all", "0"])

    status = create_child(mgr, "tableDAT", "status")
    place(status, 440, 200)
    status.clear()
    status.appendRow(["param", "value"])
    status.appendRow(["state", "idle"])
    status.appendRow(["bind_ip", DEFAULT_BIND_IP])
    status.appendRow(["last_error", ""])
    status.appendRow(["primus", "0"])
    status.appendRow(["other", "0"])

    api = create_child(mgr, "textDAT", "manager_api")
    place(api, 0, 400)
    api.text = _MANAGER_API

    exec_dat = create_child(mgr, "executeDAT", "manager_exec")
    place(exec_dat, 220, 400)
    exec_dat.text = _MANAGER_EXECUTE
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(exec_dat.par, flag).val = True
        except Exception:
            pass
    set_par(exec_dat, framestart=True, active=True)

    # Pulses Rescan / Createoutputs are handled by promoted PrimusManagerExt methods.
    # manager_exec also polls controls.rescan / create_outputs as a backup.

    # Template lives on the Manager for Createoutputs / .tox export (inactive).
    template = _build_output_template(mgr, DEFAULT_OUTPUTS[0], look_index=0, as_template=True)
    try:
        template.par.Managerpath = mgr.path
        template.par.Active = False
        template.par.display = False
        template.allowCooking = False
    except Exception:
        pass

    _attach_ext(mgr, "PrimusManagerExt", _MANAGER_EXT)

    # Live Outputs as siblings of Manager — visible at /project1/primus_phase9/
    live_outputs = []
    for index, row in enumerate(DEFAULT_OUTPUTS):
        name = safe_name(row["name"])
        copy = root.copy(template, name=name)
        place(copy, 400 + (index % 2) * 450, -(index // 2) * 50)
        try:
            copy.par.Ip = row["ip"]
            copy.par.Devicename = row["name"]
            copy.par.Universe = int(row["universe"])
            copy.par.Recvmode = row["recv_mode"]
            copy.par.A0type = row["a0_type"]
            copy.par.A1type = row["a1_type"]
            copy.par.A0virtual = int(row["a0_virtual"])
            copy.par.A1virtual = int(row["a1_virtual"])
            copy.par.Managerpath = mgr.path
            copy.par.Active = True
            copy.par.display = True
            copy.allowCooking = True
            # Each Output owns A0 media1/2 and A1 media1/2; default A0→media1, A1→media2.
            try:
                copy.par.A0media = "media1"
                copy.par.A1media = "media2"
                if index == 1:
                    copy.par.Hueshift = 0.45
            except Exception:
                pass
            sample = copy.op("sampling")
            if sample is not None:
                for r in range(1, sample.numRows):
                    key = sample[r, 0].val
                    if key == "a0_media_slot":
                        sample[r, 1] = "media1"
                    elif key == "a1_media_slot":
                        sample[r, 1] = "media2"
                    elif key == "hue_shift" and index == 1:
                        sample[r, 1] = "0.45"
        except Exception as e:
            print(f"[phase9] seed output {name}: {e}")
        live_outputs.append(copy)

    # MediaBus out1..4 → each Output's a0_media1, a0_media2, a1_media1, a1_media2.
    wire_note = "unwired"
    slot_names = ("a0_media1", "a0_media2", "a1_media1", "a1_media2")
    try:
        bus, bus_outs = _build_media_bus(root)
        for out in live_outputs:
            sample = out.op("sampling")
            if sample is not None:
                for r in range(1, sample.numRows):
                    if sample[r, 0].val == "a0_media_slot":
                        sample[r, 1] = "media1"
                    elif sample[r, 0].val == "a1_media_slot":
                        sample[r, 1] = "media2"
            try:
                out.par.A0media = "media1"
                out.par.A1media = "media2"
            except Exception:
                pass
            for i, src in enumerate(bus_outs):
                slot = out.op(slot_names[i])
                if slot is None:
                    continue
                sel_name = f"bus_sel_{slot_names[i]}"
                sel = out.op(sel_name)
                if sel is None:
                    try:
                        sel = create_child(out, "selectTOP", sel_name)
                    except Exception:
                        sel = None
                if sel is not None:
                    place(sel, -400, 160 - i * 120)
                    try:
                        set_par(sel, top=src.path)
                    except Exception:
                        try:
                            sel.par.top = src.path
                        except Exception:
                            pass
                    try:
                        slot.inputConnectors[0].connect(sel)
                    except Exception:
                        pass
                else:
                    try:
                        slot.inputConnectors[0].connect(src)
                    except Exception:
                        pass
        wire_note = (
            f"PrimusMediaBus {bus.path}/out1..4 → each Output "
            "a0_media1/a0_media2/a1_media1/a1_media2 via selectTOPs"
        )
        print("[phase9]", wire_note)
    except Exception as exc:
        wire_note = f"PrimusMediaBus wire skipped: {exc}"
        print(f"[phase9] {wire_note}")

    readme = create_child(root, "textDAT", "README")
    place(readme, -300, 200)
    readme.text = (
        "Phase 9 — PrimusManager + PrimusOutput + PrimusMediaBus\n\n"
        "Visible at this level:\n"
        "  PrimusManager     — Network / Master / Discovery\n"
        "  primus_a / _b     — live Outputs (siblings)\n"
        "  PrimusMediaBus    — optional demo generators (out1..out4)\n\n"
        "Each PrimusOutput: inputs 1–2 → A0, 3–4 → A1.\n"
        "Create / Sync Outputs adds missing devices; never destroys wiring.\n"
        "Export tox: PrimusManager + PrimusOutput + PrimusMediaBus\n"
        "See tox/README.md · handoffs/primus_system_map.md\n"
    )

    try:
        folder = Path(project.folder) / "builders"  # noqa: F821
        (folder / ".td_phase9_build.json").write_text(
            json.dumps(
                {
                    "phase": 9,
                    "manager": mgr.path,
                    "template": template.path,
                    "outputs": [c.path for c in live_outputs],
                    "mediabus": "/project1/primus_phase9/PrimusMediaBus",
                    "test_media": wire_note,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[phase9] could not write build summary: {exc}")

    out_names = [c.name for c in live_outputs]
    print(f"[phase9] built {root.path}")
    print(f"[phase9] Manager={mgr.path} outputs={out_names} (siblings at phase root)")
    print(f"[phase9] test_media: {wire_note}")
    print("[phase9] Wire show TOPs → PrimusOutput inputs 1–4 (a0/a1 media1/2)")
    return f"{root.path} manager={mgr.path} outputs={out_names} {wire_note}"
