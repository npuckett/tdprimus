"""
One-time installer: creates /project1/PrimusControl + /project1/PrimusBridge.

In Textport (recommended - clears stale builders.* from earlier failed runs):

    for k in list(sys.modules):
        if k == 'builders' or k.startswith('builders.'):
            del sys.modules[k]
    exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
    install()

Or from the shell (prints the same snippet):

    python3 builders/td_remote.py install

After install, drive builds from Cursor/shell:

    python3 builders/td_remote.py build 1
"""

from __future__ import annotations

import importlib
import sys


def _bootstrap():
    try:
        root = project.folder  # noqa: F821
    except NameError:
        root = None
    if root and root not in sys.path:
        sys.path.insert(0, root)


def _purge_builders():
    """Drop cached builders.* so the next import matches disk."""
    for key in list(sys.modules):
        if key == "builders" or key.startswith("builders."):
            del sys.modules[key]


_bootstrap()

_EXT = r'''
"""PrimusControlExt - pulse-driven phase runners (reloads builders.* each build)."""

import sys


class PrimusControlExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp
        self._ensure_path()

    def _ensure_path(self):
        try:
            root = project.folder
        except Exception:
            root = None
        if root and root not in sys.path:
            sys.path.insert(0, root)

    def _settings(self):
        table = self.ownerComp.op("settings")
        out = {}
        if table is None:
            return out
        for r in range(1, table.numRows):
            out[table[r, 0].val.strip()] = table[r, 1].val.strip()
        return out

    def Build(self, phase):
        self._ensure_path()
        import importlib
        import sys

        # Never `from ... import reload_builders` on a possibly-stale module -
        # purge first, then import fresh from disk.
        for key in list(sys.modules):
            if key == "builders" or key.startswith("builders."):
                del sys.modules[key]
        importlib.invalidate_caches()
        import builders.lib.td_builder as tb

        if hasattr(tb, "reload_builders"):
            tb = tb.reload_builders()
        prepare_build = tb.prepare_build
        from builders.run_phase import kwargs_for_phase, run_phase

        td_ns = {"op": op, "project": project}  # noqa: F821
        try:
            td_ns["me"] = me  # noqa: F821
        except Exception:
            pass
        prepare_build(td_ns)
        settings = self._settings()
        kw = kwargs_for_phase(int(phase), settings)
        return run_phase(int(phase), td_namespace=td_ns, **kw)

    def Buildphase1(self, _par=None):
        return self.Build(1)

    def Buildphase2(self, _par=None):
        return self.Build(2)

    def Buildphase3(self, _par=None):
        return self.Build(3)

    def Buildphase4(self, _par=None):
        return self.Build(4)

    def Buildphase5(self, _par=None):
        return self.Build(5)

    def Buildphase6(self, _par=None):
        return self.Build(6)

    def Buildphase7(self, _par=None):
        return self.Build(7)

    def Buildphase8(self, _par=None):
        return self.Build(8)

    def Buildphase9(self, _par=None):
        return self.Build(9)

    def Blackout(self, on=True):
        """Best-effort: set blackout on known phase bases."""
        op_fn = op  # noqa: F821
        for name in (
            "primus_phase1",
            "primus_phase2",
            "primus_phase3",
            "primus_phase4",
            "primus_phase5",
            "primus_phase6",
        ):
            base = op_fn(f"/project1/{name}")
            if base is None:
                continue
            ctrl = base.op("controls")
            if ctrl is None:
                continue
            for key in ("blackout", "blackout_all"):
                try:
                    for r in range(1, ctrl.numRows):
                        if ctrl[r, 0].val == key:
                            ctrl[r, 1] = 1 if on else 0
                except Exception:
                    pass
'''

_PARAM_EXEC = r'''
# Wire custom pulse parameters to extension methods

def onOffToOn(par):
    ext = parent().ext
    name = par.name
    mapping = {
        "Buildphase1": 1,
        "Buildphase2": 2,
        "Buildphase3": 3,
        "Buildphase4": 4,
        "Buildphase5": 5,
        "Buildphase6": 6,
        "Buildphase7": 7,
        "Buildphase8": 8,
        "Buildphase9": 9,
    }
    if name in mapping:
        print(f"[PrimusControl] Build phase {mapping[name]}")
        ext.Build(mapping[name])
    elif name == "Blackouton":
        ext.Blackout(True)
    elif name == "Blackoutoff":
        ext.Blackout(False)
'''

_BRIDGE_EXEC = r'''
"""PrimusBridge - poll builders/.td_cmd.json and write builders/.td_result.json."""

import json
import sys
import time
import traceback
from pathlib import Path

_LAST_CHECK = 0.0
_POLL_INTERVAL = 0.5


def _root():
    return Path(project.folder)


def _cmd_path():
    return _root() / "builders" / ".td_cmd.json"


def _result_path():
    return _root() / "builders" / ".td_result.json"


def _ensure_path():
    root = str(_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _write_result(payload):
    payload = dict(payload)
    payload.setdefault("ts", time.time())
    path = _result_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _clear_cmd():
    path = _cmd_path()
    try:
        if path.exists():
            path.unlink()
    except Exception:
        try:
            path.write_text("{}", encoding="utf-8")
        except Exception:
            pass


def _settings_from_control():
    table = op("/project1/PrimusControl/settings")
    out = {}
    if table is None:
        return out
    for r in range(1, table.numRows):
        out[table[r, 0].val.strip()] = table[r, 1].val.strip()
    return out


def _merge_settings(cmd):
    settings = _settings_from_control()
    # CLI keys -> settings table keys
    if cmd.get("ip") is not None:
        settings["ip"] = str(cmd["ip"])
    if cmd.get("device_ip") is not None:
        settings["ip"] = str(cmd["device_ip"])
    if cmd.get("universe") is not None:
        settings["universe"] = str(cmd["universe"])
    if cmd.get("a0_type") is not None:
        settings["a0_type"] = str(cmd["a0_type"])
    if cmd.get("a1_type") is not None:
        settings["a1_type"] = str(cmd["a1_type"])
    if cmd.get("a0_virtual") is not None:
        settings["a0_virtual"] = str(cmd["a0_virtual"])
    if cmd.get("a1_virtual") is not None:
        settings["a1_virtual"] = str(cmd["a1_virtual"])
    if cmd.get("recv_mode") is not None:
        settings["recv_mode"] = str(cmd["recv_mode"])
    if cmd.get("pattern") is not None:
        settings["pattern"] = str(cmd["pattern"])
    # Apply overrides back onto the settings table when present
    table = op("/project1/PrimusControl/settings")
    if table is not None:
        for key in (
            "ip",
            "universe",
            "a0_type",
            "a1_type",
            "a0_virtual",
            "a1_virtual",
            "recv_mode",
            "pattern",
        ):
            if key not in settings:
                continue
            found = False
            for r in range(1, table.numRows):
                if table[r, 0].val.strip() == key:
                    table[r, 1] = settings[key]
                    found = True
                    break
            if not found:
                table.appendRow([key, settings[key]])
    return settings


def _handle(cmd):
    _ensure_path()
    cmd_id = cmd.get("id")
    action = (cmd.get("cmd") or cmd.get("action") or "build").lower()
    phase = int(cmd.get("phase", 1))

    if action in ("ping", "status"):
        _write_result(
            {
                "ok": True,
                "id": cmd_id,
                "phase": None,
                "error": None,
                "traceback": None,
                "message": "pong",
            }
        )
        return

    if action == "inspect":
        try:
            parent = op("/project1")  # noqa: F821
            kids = []
            if parent is not None:
                for c in parent.children:
                    kids.append(
                        {
                            "name": c.name,
                            "path": c.path,
                            "type": c.type if hasattr(c, "type") else type(c).__name__,
                            "nodeX": getattr(c, "nodeX", None),
                            "nodeY": getattr(c, "nodeY", None),
                        }
                    )
            phase3 = op("/project1/primus_phase3")  # noqa: F821
            info = {
                "ok": True,
                "id": cmd_id,
                "phase": None,
                "error": None,
                "traceback": None,
                "message": f"/project1 has {len(kids)} children",
                "children": kids,
                "primus_phase3": None
                if phase3 is None
                else {
                    "path": phase3.path,
                    "nodeX": phase3.nodeX,
                    "nodeY": phase3.nodeY,
                    "children": [c.name for c in phase3.children],
                },
            }
            _write_result(info)
        except Exception as exc:
            _write_result(
                {
                    "ok": False,
                    "id": cmd_id,
                    "phase": None,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                    "message": "inspect failed",
                }
            )
        return

    if action != "build":
        _write_result(
            {
                "ok": False,
                "id": cmd_id,
                "phase": phase,
                "error": f"unknown cmd: {action}",
                "traceback": None,
                "message": "unsupported command",
            }
        )
        return

    try:
        import importlib

        for key in list(sys.modules):
            if key == "builders" or key.startswith("builders."):
                del sys.modules[key]
        importlib.invalidate_caches()
        import builders.lib.td_builder as tb

        if hasattr(tb, "reload_builders"):
            tb = tb.reload_builders()
        prepare_build = tb.prepare_build
        from builders.run_phase import kwargs_for_phase, run_phase

        td_ns = {"op": op, "project": project}  # noqa: F821
        try:
            td_ns["me"] = me  # noqa: F821
        except Exception:
            pass
        prepare_build(td_ns)
        settings = _merge_settings(cmd)
        kw = kwargs_for_phase(phase, settings)
        result = run_phase(phase, td_namespace=td_ns, **kw)
        msg = f"phase {phase} ok"
        if result is not None:
            msg = f"{msg}: {result!r}"
        _write_result(
            {
                "ok": True,
                "id": cmd_id,
                "phase": phase,
                "error": None,
                "traceback": None,
                "message": msg,
            }
        )
        print(f"[PrimusBridge] {msg}")
    except Exception as exc:
        tb_txt = traceback.format_exc()
        _write_result(
            {
                "ok": False,
                "id": cmd_id,
                "phase": phase,
                "error": str(exc),
                "traceback": tb_txt,
                "message": f"phase {phase} failed",
            }
        )
        print(f"[PrimusBridge] phase {phase} FAILED: {exc}")
        print(tb_txt)


def onFrameStart(frame):
    global _LAST_CHECK
    now = time.time()
    if now - _LAST_CHECK < _POLL_INTERVAL:
        return
    _LAST_CHECK = now

    path = _cmd_path()
    if not path.exists():
        return
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw or raw == "{}":
            return
        cmd = json.loads(raw)
    except Exception as exc:
        _write_result(
            {
                "ok": False,
                "id": None,
                "phase": None,
                "error": f"bad cmd file: {exc}",
                "traceback": traceback.format_exc(),
                "message": "cmd parse failed",
            }
        )
        _clear_cmd()
        return

    # Clear before handling so a crash does not re-run forever
    _clear_cmd()
    if not isinstance(cmd, dict) or not cmd:
        return
    _handle(cmd)
'''


def _import_td_builder():
    """
    Import builders.lib.td_builder fresh from disk.

    TouchDesigner keeps sys.modules across Textport runs. A stale module that
    predates create_child/reload_builders will break `from ... import create_child`.
    Always purge first, then import - do not rely on attributes of the stale copy.
    """
    _bootstrap()
    importlib.invalidate_caches()
    _purge_builders()
    import builders.lib.td_builder as tb

    if hasattr(tb, "reload_builders"):
        return tb.reload_builders()
    return tb


def _wire_file_sync(parent, name: str, rel_path: str, x: int, y: int):
    """Best-effort Text DAT synced to a repo file (Cursor edits reload in TD)."""
    from builders.lib.td_builder import create_child, place, set_par

    try:
        root = project.folder  # noqa: F821
    except Exception:
        root = None
    dat = create_child(parent, "textDAT", name)
    place(dat, x, y)
    if root:
        full = f"{root}/{rel_path}"
        try:
            set_par(dat, file=full)
        except Exception:
            pass
        for flag in ("syncfile", "loadonstart", "write"):
            try:
                getattr(dat.par, flag).val = True
            except Exception:
                pass
        try:
            dat.par.file = full
            if hasattr(dat.par, "syncfile"):
                dat.par.syncfile = True
        except Exception:
            pass
    return dat


def _install_bridge(parent):
    from builders.lib.td_builder import create_child, place, set_par

    existing = parent.op("PrimusBridge")
    if existing:
        existing.destroy()

    bridge = create_child(parent, "baseCOMP", "PrimusBridge")
    place(bridge, 400, 0)

    poll = create_child(bridge, "executeDAT", "cmd_poll")
    place(poll, 0, 200)
    poll.text = _BRIDGE_EXEC
    for flag in ("framestart", "frameStart", "active"):
        try:
            getattr(poll.par, flag).val = True
        except Exception:
            pass
    try:
        set_par(poll, framestart=True, active=True)
    except Exception:
        pass

    # Optional: sync extension sources so Cursor edits are visible in TD
    _wire_file_sync(bridge, "PrimusManagerExt", "extensions/PrimusManagerExt.py", 200, 200)
    _wire_file_sync(bridge, "PrimusDeviceExt", "extensions/PrimusDeviceExt.py", 400, 200)
    _wire_file_sync(bridge, "PrimusCueEngineExt", "extensions/PrimusCueEngineExt.py", 600, 200)

    readme = create_child(bridge, "textDAT", "README")
    place(readme, 0, 400)
    readme.text = (
        "PrimusBridge\n\n"
        "Polls:  <project.folder>/builders/.td_cmd.json  (~0.5s)\n"
        "Writes: <project.folder>/builders/.td_result.json\n\n"
        "From shell / Cursor:\n"
        "  python3 builders/td_remote.py build 1\n"
        "  python3 builders/td_remote.py status\n"
    )
    print(f"[install] created {bridge.path} (watches builders/.td_cmd.json)")
    return bridge


def install(parent_path: str = "/project1"):
    tb = _import_td_builder()
    if not hasattr(tb, "create_child"):
        raise RuntimeError(
            "cannot import create_child from builders.lib.td_builder - "
            "stale module or wrong file. Confirm "
            f"{getattr(tb, '__file__', '?')} defines create_child, then retry."
        )

    create_child = tb.create_child
    place = tb.place
    prepare_build = tb.prepare_build
    set_par = tb.set_par
    td_op = tb.td_op

    prepare_build(globals())
    parent = td_op(parent_path)
    if parent is None:
        raise RuntimeError(f"missing {parent_path}")

    existing = parent.op("PrimusControl")
    if existing:
        existing.destroy()

    panel = create_child(parent, "baseCOMP", "PrimusControl")
    place(panel, 0, 0)

    try:
        page = panel.appendCustomPage("Primus")
    except Exception:
        page = panel.customPages[0]

    pulses = [
        ("Buildphase1", "Build Phase 1"),
        ("Buildphase2", "Build Phase 2"),
        ("Buildphase3", "Build Phase 3"),
        ("Buildphase4", "Build Phase 4"),
        ("Buildphase5", "Build Phase 5"),
        ("Buildphase6", "Build Phase 6"),
        ("Buildphase7", "Build Phase 7"),
        ("Buildphase8", "Build Phase 8"),
        ("Buildphase9", "Build Phase 9"),
        ("Blackouton", "Blackout On"),
        ("Blackoutoff", "Blackout Off"),
    ]
    for pname, label in pulses:
        try:
            page.appendPulse(pname, label=label)
        except Exception as e:
            print(f"[install] pulse {pname}: {e}")

    settings = create_child(panel, "tableDAT", "settings")
    place(settings, 0, 200)
    settings.clear()
    settings.appendRow(["param", "value"])
    for row in (
        ("ip", "192.168.8.166"),
        ("universe", "0"),
        ("a0_type", "small_grid"),
        ("a1_type", "long_strip"),
        ("a0_virtual", "1"),
        ("a1_virtual", "72"),
        ("recv_mode", "split"),
    ):
        settings.appendRow(list(row))

    ext_dat = create_child(panel, "textDAT", "PrimusControlExt")
    place(ext_dat, 200, 200)
    ext_dat.text = _EXT
    try:
        panel.par.extension1 = ext_dat
        panel.par.promoteextension1 = True
    except Exception as e:
        print(f"[install] extension wire: {e}")

    pex = create_child(panel, "executeDAT", "param_exec")
    try:
        pex.destroy()
        pex = create_child(panel, "parexecDAT", "param_exec")
    except Exception:
        pex = panel.op("param_exec") or create_child(panel, "executeDAT", "param_exec")
    place(pex, 400, 200)
    pex.text = _PARAM_EXEC
    try:
        set_par(pex, opexecute=True)
        pex.par.parms = "*"
    except Exception:
        try:
            pex.par.par = panel.path
        except Exception as e:
            print(f"[install] parexec wire: {e} - use ext.Build(1) from Textport")

    readme = create_child(panel, "textDAT", "README")
    place(readme, 0, 400)
    readme.text = (
        "PrimusControl\n\n"
        "Preferred (Cursor / shell):\n"
        "  python3 builders/td_remote.py build 1\n\n"
        "Panel fallback:\n"
        "  1. Edit `settings` (ip / universe / a0_type / ...)\n"
        "  2. Pulse Build Phase 1, or Textport:\n"
        "       op('/project1/PrimusControl').ext.Build(1)\n\n"
        "Bridge watches builders/.td_cmd.json -> .td_result.json\n"
        "Defaults: 192.168.8.166 univ 0 small_grid split.\n"
    )

    _install_bridge(parent)

    print(f"[install] created {panel.path}")
    print("[install] One-time Textport done. From now on use:")
    print("         python3 builders/td_remote.py build 1")
    return panel
