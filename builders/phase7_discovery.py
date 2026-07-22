"""Phase 7 — ArtPoll discovery into a Phase-5-compatible devices table."""

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

from builders.lib.packets import ARTNET_PORT, build_art_poll, bytes_to_td_hex  # noqa: E402
from builders.lib.td_builder import (  # noqa: E402
    create_child,
    ensure_base,
    place,
    prepare_build,
    set_par,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase7"
DEFAULT_BIND_IP = "192.168.8.199"

# Match Phase 5 profile columns so discovered rows can be copied forward.
DEVICE_COLS = (
    "name", "active", "ip", "bind_ip", "universe", "recv_mode",
    "a0_type", "a0_count", "a0_virtual", "a1_type", "a1_count", "a1_virtual",
    "a0_source", "a1_source", "group", "short_name", "firmware",
)

_DISCOVER_API = r'''
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

def _root():
    return op("/project1/primus_phase7")

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

def _safe_name(short_name, ip, used):
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

def _upsert_device(table, row, cols):
    ip_col = cols.index("ip")
    found = None
    for r in range(1, table.numRows):
        if table[r, ip_col].val == row["ip"]:
            found = r
            break
    values = [str(row.get(c, "")) for c in cols]
    if found is None:
        table.appendRow(values)
    else:
        for c, v in enumerate(values):
            table[found, c] = v

def rescan(root=None, source="api"):
    """ArtPoll on the wired bind_ip; fill devices / non_primus / log."""
    root = root or _root()
    controls = root.op("controls")
    devices = root.op("devices")
    non_primus = root.op("non_primus")
    log = root.op("discovery_log")
    status = root.op("status")
    bind_ip = str(_cell(controls, "bind_ip", "192.168.8.199")).strip()
    try:
        timeout = float(_cell(controls, "timeout", "2"))
    except Exception:
        timeout = 2.0
    _set_cell(status, "state", "scanning")
    _set_cell(status, "bind_ip", bind_ip)
    _set_cell(status, "last_source", source)
    print("[phase7] ArtPoll bind=%s timeout=%.1fs (%s)" % (bind_ip, timeout, source))
    try:
        discover, enrich = _reload_discover()
        nodes = discover(timeout=timeout, bind_ip=bind_ip or None)
    except Exception as exc:
        print("[phase7] discover failed:", exc)
        _set_cell(status, "state", "error")
        _set_cell(status, "last_error", str(exc))
        return False

    cols = [devices[0, c].val for c in range(devices.numCols)]
    # Clear data rows; keep header
    while devices.numRows > 1:
        devices.deleteRow(1)
    if non_primus is not None:
        while non_primus.numRows > 1:
            non_primus.deleteRow(1)
    if log is not None:
        while log.numRows > 1:
            log.deleteRow(1)

    used_names = set()
    primus_n = 0
    other_n = 0
    for raw in nodes:
        node = enrich(raw)
        if log is not None:
            log.appendRow([
                node.get("ip", ""),
                node.get("short_name", ""),
                (node.get("node_report") or "")[:80],
            ])
        if not node.get("is_primus"):
            other_n += 1
            if non_primus is not None:
                non_primus.appendRow([
                    node.get("ip", ""),
                    node.get("short_name", ""),
                    "non-primus",
                ])
            continue
        primus_n += 1
        a0t, a0c, a0v, a1t, a1c, a1v = _type_defaults(node.get("ports"))
        mode = node.get("receive_mode") or "split"
        univ = node.get("base_universe")
        if univ is None:
            univ = 0
        short = node.get("short_name") or node.get("ip")
        name = _safe_name(short, node.get("ip"), used_names)
        # Alternate demo/alt sources so two found devices look distinct if imported to Phase 5.
        src = "demo" if primus_n == 1 else "alt"
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
            "a0_source": src,
            "a1_source": src,
            "group": "discovered",
            "short_name": short,
            "firmware": node.get("firmware_version") or "",
        }
        _upsert_device(devices, row, cols)

    _set_cell(status, "state", "ok")
    _set_cell(status, "primus", str(primus_n))
    _set_cell(status, "other", str(other_n))
    _set_cell(status, "last_error", "")
    try:
        root.par.Status = "%d Primus, %d other" % (primus_n, other_n)
    except Exception:
        pass
    try:
        from pathlib import Path
        import json
        summary = {
            "phase": 7,
            "bind_ip": bind_ip,
            "primus": primus_n,
            "other": other_n,
            "devices": [
                {cols[c]: devices[r, c].val for c in range(len(cols))}
                for r in range(1, devices.numRows)
            ],
        }
        Path(project.folder, "builders", ".td_phase7_discover.json").write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:
        print("[phase7] could not write summary:", exc)
    print("[phase7] found %d Primus, %d other" % (primus_n, other_n))
    return True
'''

_RESCAN_EXEC = r'''
def onTableChange(dat):
    _maybe_rescan(dat.parent())

def onFrameEnd(frame):
    root = me.parent()
    _maybe_rescan(root)
    _poll_shell(root)

def _api():
    ns = {"op": op, "project": project}
    exec(op("/project1/primus_phase7/discover_api").text, ns)
    return ns

def _maybe_rescan(root):
    controls = root.op("controls")
    if controls is None:
        return
    api = _api()
    try:
        if int(float(api["_cell"](controls, "rescan", "0"))) == 1:
            api["_set_cell"](controls, "rescan", "0")
            api["rescan"](root, source="controls")
    except Exception as exc:
        print("[phase7] rescan failed:", exc)

def _poll_shell(root):
    try:
        from pathlib import Path
        import json
        path = Path(project.folder) / "builders" / ".td_discover_cmd.json"
        if not path.exists():
            return
        raw = path.read_text(encoding="utf-8").strip()
        if not raw or raw == "{}":
            return
        path.write_text("{}\n", encoding="utf-8")
        data = json.loads(raw)
        if (data.get("cmd") or "").lower() in ("rescan", "discover"):
            _api()["rescan"](root, source="shell")
    except Exception as exc:
        print("[phase7] discover cmd failed:", exc)
'''

_EXT = r'''
class DiscoveryExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _api(self):
        ns = {"op": op, "project": project}
        exec(self.ownerComp.op("discover_api").text, ns)
        return ns

    def Rescan(self, _par=None):
        return self._api()["rescan"](self.ownerComp, source="panel")
'''


def _table(parent, name, rows, x, y):
    node = create_child(parent, "tableDAT", name)
    place(node, x, y)
    node.clear()
    node.appendRow(["param", "value"])
    for key, value in rows:
        node.appendRow([key, value])
    return node


def _init_devices(table):
    table.clear()
    table.appendRow(list(DEVICE_COLS))


def _add_pars(base):
    try:
        page = base.appendCustomPage("Discovery")
    except Exception:
        page = base.customPages[0] if getattr(base, "customPages", None) else None
    if page is None:
        return
    try:
        page.appendPulse("Rescan", label="Rescan network")
    except Exception as exc:
        print(f"[phase7] Rescan pulse: {exc}")
    try:
        p = page.appendStr("Bindip", label="Bind IP")
        p.val = DEFAULT_BIND_IP
    except Exception:
        pass
    try:
        p = page.appendStr("Status", label="Status")
        p.val = "idle"
    except Exception:
        pass


def build(parent_path=PARENT_PATH, bind_ip=DEFAULT_BIND_IP, **_ignored):
    """Build Phase 7 discovery deck (ArtPoll → devices table)."""
    prepare_build(globals())
    bind_ip = (bind_ip or DEFAULT_BIND_IP).strip()

    base = ensure_base(parent_path, BASE_NAME, recreate=True)
    place(base, 800, -700)
    _add_pars(base)
    try:
        base.par.Bindip = bind_ip
    except Exception:
        pass

    api = create_child(base, "textDAT", "discover_api")
    place(api, 0, 400)
    api.text = _DISCOVER_API

    devices = create_child(base, "tableDAT", "devices")
    place(devices, 0, 200)
    _init_devices(devices)

    non_primus = create_child(base, "tableDAT", "non_primus")
    place(non_primus, 250, 200)
    non_primus.clear()
    non_primus.appendRow(["ip", "short_name", "note"])

    log = create_child(base, "tableDAT", "discovery_log")
    place(log, 500, 200)
    log.clear()
    log.appendRow(["ip", "short_name", "node_report"])

    controls = _table(
        base,
        "controls",
        [
            ("rescan", "0"),
            ("bind_ip", bind_ip),
            ("timeout", "2"),
        ],
        750,
        200,
    )
    status = _table(
        base,
        "status",
        [
            ("state", "idle"),
            ("bind_ip", bind_ip),
            ("primus", "0"),
            ("other", "0"),
            ("last_error", ""),
            ("last_source", ""),
        ],
        750,
        400,
    )

    poll_bytes = build_art_poll()
    poll_dat = create_child(base, "textDAT", "poll_packet")
    place(poll_dat, 0, 0)
    poll_dat.text = bytes_to_td_hex(poll_bytes).replace(" ", "")

    # Reference UDP Out only (Python discovery owns the bind — avoids fighting ArtDmx).
    udp_out = create_child(base, "udpoutDAT", "udp_out_poll")
    place(udp_out, 250, 0)
    set_par(udp_out, port=ARTNET_PORT, protocol="udp")
    try:
        set_par(udp_out, address="255.255.255.255")
    except Exception:
        pass

    rescan_exec = create_child(base, "executeDAT", "rescan_execute")
    place(rescan_exec, 500, 0)
    rescan_exec.text = _RESCAN_EXEC
    for flag in ("tablechange", "tableChange", "frameend", "frameEnd", "active"):
        try:
            getattr(rescan_exec.par, flag).val = True
        except Exception:
            pass
    try:
        rescan_exec.par.dat = controls.path
    except Exception:
        pass
    set_par(rescan_exec, active=True)

    ext_dat = create_child(base, "textDAT", "DiscoveryExt")
    place(ext_dat, 750, 0)
    ext_dat.text = _EXT
    try:
        base.par.extension1 = ext_dat
        base.par.promoteextension1 = True
    except Exception as exc:
        print(f"[phase7] extension wire: {exc}")

    info = create_child(base, "textDAT", "README")
    place(info, 0, 600)
    info.text = (
        "Phase 7 — Discovery\n\n"
        "Select this COMP → Discovery page → Rescan.\n"
        f"Uses Python ArtPoll (bind {bind_ip}:6454) via builders/discover_device.py.\n"
        "Primus replies fill `devices` (Phase 5 column layout).\n"
        "Non-Primus Art-Net nodes go to `non_primus`.\n\n"
        "Shell: python3 builders/td_remote.py discover\n"
        "Offline: python3 builders/discover_device.py --bind 192.168.8.199\n"
        "Do not trust ArtPollReply SwOut for universe — PV3CAP1 only.\n"
    )

    # Auto-scan once at build.
    try:
        ns = {"op": op, "project": project}  # noqa: F821
        exec(_DISCOVER_API, ns)
        ns["rescan"](base, source="build")
    except Exception as exc:
        print(f"[phase7] initial scan deferred: {exc}")

    summary = {
        "phase": 7,
        "path": base.path,
        "bind_ip": bind_ip,
        "artnet_port": ARTNET_PORT,
    }
    try:
        from pathlib import Path

        Path(project.folder, "builders", ".td_phase7_build.json").write_text(  # noqa: F821
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
    except Exception:
        pass
    print(f"[phase7] built {base.path} bind={bind_ip}")
    return f"{base.path} bind={bind_ip}"
