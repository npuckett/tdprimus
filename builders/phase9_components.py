"""
Phase 9 - Custom components (Primus Device / Manager / Cue Engine).

Builds Base COMPs with Custom Parameters and Extension class stubs.
Export to .tox is documented in tox/README.md (must be done inside TD).

    exec(open(f'{project.folder}/builders/phase9_components.py').read())
    build()
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
BASE_NAME = "primus_phase9"

_DEVICE_EXT = r'''
"""PrimusDevice extension - methods for config push / identify."""

class PrimusDeviceExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def PushRename(self):
        name = self.ownerComp.par.Devicename.eval()
        ip = self.ownerComp.par.Ip.eval()
        self._send_action(ip, "rename", name)

    def PushVirtualResolution(self):
        ip = self.ownerComp.par.Ip.eval()
        v0 = int(self.ownerComp.par.A0virtual.eval())
        v1 = int(self.ownerComp.par.A1virtual.eval())
        self._send_action(ip, "virtual_resolution", str(v0), str(v1))

    def PushReceiveConfig(self):
        ip = self.ownerComp.par.Ip.eval()
        mode = self.ownerComp.par.Recvmode.eval()
        univ = int(self.ownerComp.par.Universe.eval())
        self._send_action(ip, "receive_config", mode, str(univ))

    def PushOutputConfig(self):
        ip = self.ownerComp.par.Ip.eval()
        self._send_action(
            ip, "output_config",
            self.ownerComp.par.A0type.eval(),
            self.ownerComp.par.A1type.eval(),
        )

    def Identify(self):
        ip = self.ownerComp.par.Ip.eval()
        univ = int(self.ownerComp.par.Universe.eval())
        self._send_action(ip, "identify", str(univ), "73")

    def Blackout(self, on=True):
        ctrl = self.ownerComp.op("controls")
        if ctrl:
            ctrl["blackout", 1] = 1 if on else 0

    def _send_action(self, ip, action, arg1="", arg2="", arg3="", arg4=""):
        mgr = self.ownerComp.parent()
        push = mgr.op("push") if mgr else None
        controls = mgr.op("controls") if mgr else None
        if push is None:
            print("[PrimusDevice] no manager push table")
            return
        # Ensure header
        if push.numRows < 1:
            return
        if push.numRows == 1:
            push.appendRow([ip, action, arg1, arg2, arg3, arg4])
        else:
            push[1, "ip"] = ip
            push[1, "action"] = action
            push[1, "arg1"] = arg1
            push[1, "arg2"] = arg2
            push[1, "arg3"] = arg3
            push[1, "arg4"] = arg4
        if controls:
            controls["push", 1] = 1
'''

_MANAGER_EXT = r'''
class PrimusManagerExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Rescan(self):
        c = self.ownerComp.op("controls")
        if c:
            c["rescan", 1] = 1

    def RebuildDevices(self):
        """Replicate Primus Device comps from devices table."""
        devices = self.ownerComp.op("devices")
        container = self.ownerComp.op("device_container")
        template = self.ownerComp.op("device_template")
        if not devices or not container or not template:
            print("[PrimusManager] missing devices/container/template")
            return
        # Clear existing replicas
        for child in list(container.children):
            child.destroy()
        for r in range(1, devices.numRows):
            name = devices[r, "name"].val
            safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name) or f"dev{r}"
            copy = container.copy(template, name=safe)
            try:
                copy.par.Ip = devices[r, "ip"].val
                copy.par.Universe = int(devices[r, "universe"].val or 0)
                copy.par.Recvmode = devices[r, "recv_mode"].val or "combined"
                copy.par.A0type = devices[r, "a0_type"].val
                copy.par.A1type = devices[r, "a1_type"].val
                copy.par.A0virtual = int(devices[r, "a0_virtual"].val or 1)
                copy.par.A1virtual = int(devices[r, "a1_virtual"].val or 1)
                copy.par.Devicename = name
                copy.par.display = True
                copy.allowCooking = True
            except Exception as e:
                print("[PrimusManager] param bind", e)
        print(f"[PrimusManager] replicated {devices.numRows - 1} devices")
'''

_CUE_EXT = r'''
class PrimusCueEngineExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Go(self):
        c = self.ownerComp.op("controls")
        if c:
            c["go", 1] = 1

    def Goto(self, cue_number):
        cues = self.ownerComp.op("cues")
        state = self.ownerComp.op("cue_state")
        if not cues or not state:
            return
        for r in range(1, cues.numRows):
            if cues[r, "cue"].val == str(cue_number):
                state["cue_index", 1] = r - 1  # go() advances +1
                self.Go()
                return
        print(f"[PrimusCueEngine] cue {cue_number} not found")
'''


def _add_custom_pars(comp, specs):
    """specs: list of (style, name, default, label, extras_dict)."""
    page = None
    try:
        page = comp.appendCustomPage("Primus")
    except Exception:
        # Already exists
        for p in comp.customPages:
            if p.name == "Primus":
                page = p
                break
    if page is None:
        print(f"[phase8] could not create custom page on {comp}")
        return
    for style, name, default, label, extras in specs:
        try:
            if style == "str":
                p = page.appendStr(name, label=label)
                p.val = default
            elif style == "int":
                p = page.appendInt(name, label=label)
                p.val = default
            elif style == "float":
                p = page.appendFloat(name, label=label)
                p.val = default
            elif style == "menu":
                p = page.appendMenu(name, label=label)
                p.menuNames = extras.get("names", [])
                p.menuLabels = extras.get("labels", p.menuNames)
                p.val = default
            elif style == "pulse":
                p = page.appendPulse(name, label=label)
            elif style == "toggle":
                p = page.appendToggle(name, label=label)
                p.val = default
            else:
                continue
        except Exception as e:
            # Parameter may already exist
            print(f"[phase8] par {name}: {e}")


def _build_device_template(parent):
    tmpl = parent.create(baseCOMP, "device_template")
    place(tmpl, 0, 0)
    _add_custom_pars(
        tmpl,
        [
            ("str", "Ip", "192.168.1.100", "IP", {}),
            ("str", "Devicename", "Primus", "Device Name", {}),
            ("int", "Universe", 0, "Universe", {}),
            (
                "menu",
                "Recvmode",
                "combined",
                "Receive Mode",
                {"names": ["combined", "split"], "labels": ["Combined", "Split"]},
            ),
            (
                "menu",
                "A0type",
                "small_grid",
                "A0 Type",
                {
                    "names": [
                        "none",
                        "short_strip",
                        "long_strip",
                        "grid",
                        "small_grid",
                        "extra_long_strip",
                    ],
                    "labels": [
                        "Off",
                        "Short Strip",
                        "Long Strip",
                        "Grid 8x8",
                        "Grid 8x4",
                        "Extra Long Strip",
                    ],
                },
            ),
            (
                "menu",
                "A1type",
                "long_strip",
                "A1 Type",
                {
                    "names": [
                        "none",
                        "short_strip",
                        "long_strip",
                        "grid",
                        "small_grid",
                        "extra_long_strip",
                    ],
                    "labels": [
                        "Off",
                        "Short Strip",
                        "Long Strip",
                        "Grid 8x8",
                        "Grid 8x4",
                        "Extra Long Strip",
                    ],
                },
            ),
            ("int", "A0virtual", 1, "A0 Virtual Px", {}),
            ("int", "A1virtual", 72, "A1 Virtual Px", {}),
            ("pulse", "Pushrename", None, "Push Rename", {}),
            ("pulse", "Pushvirtual", None, "Push Virtual Res", {}),
            ("pulse", "Pushrecv", None, "Push Receive Mode", {}),
            ("pulse", "Pushoutput", None, "Push Output Types", {}),
            ("pulse", "Identify", None, "Identify (white)", {}),
            ("toggle", "Blackout", 0, "Blackout", {}),
        ],
    )

    # Minimal internal transport stub (1px solid -> dmx)
    color = tmpl.create(constantTOP, "color")
    place(color, 0, -200)
    set_par(color, colorr=1, colorg=1, colorb=1)
    try:
        resize = tmpl.create(resolutionTOP, "resize")
    except Exception:
        resize = tmpl.create(transformTOP, "resize")
    place(resize, 200, -200)
    set_par(resize, resolutionw=1, resolutionh=1)
    connect(color, resize)
    t2c = tmpl.create(topToCHOP, "t2c")
    place(t2c, 400, -200)
    set_par(t2c, output="R G B")
    connect(resize, t2c)
    shuf = tmpl.create(shuffleCHOP, "shuf")
    place(shuf, 600, -200)
    set_par(shuf, method="sequencechannelsbysamples")
    connect(t2c, shuf)
    dmx = tmpl.create(dmxoutCHOP, "dmx_out")
    place(dmx, 800, -200)
    set_par(dmx, interface="artnet", rate=30)
    try:
        dmx.par.netaddress.expr = "parent().par.Ip"
        dmx.par.universe.expr = "parent().par.Universe"
    except Exception:
        pass
    connect(shuf, dmx)

    ctrl = tmpl.create(tableDAT, "controls")
    place(ctrl, 0, -400)
    ctrl.clear()
    ctrl.appendRow(["param", "value"])
    ctrl.appendRow(["blackout", "0"])

    ext_dat = tmpl.create(textDAT, "PrimusDeviceExt")
    place(ext_dat, 200, -400)
    ext_dat.text = _DEVICE_EXT
    try:
        tmpl.par.extension1 = ext_dat
        tmpl.par.promoteextension1 = True
    except Exception:
        # Alternate extension attach
        try:
            tmpl.extensions = [ext_dat]
        except Exception as e:
            print(f"[phase8] attach device ext: {e}")

    # Hide template by default
    try:
        tmpl.par.display = False
        tmpl.allowCooking = False
    except Exception:
        pass
    return tmpl


def build(parent_path: str = PARENT_PATH):
    prepare_build(globals())
    root = ensure_base(parent_path, BASE_NAME, recreate=True)

    # --- Manager ---
    mgr = root.create(baseCOMP, "PrimusManager")
    place(mgr, 0, 0)
    _add_custom_pars(
        mgr,
        [
            ("pulse", "Rescan", None, "Rescan Network", {}),
            ("pulse", "Rebuild", None, "Rebuild Devices", {}),
        ],
    )
    devices = mgr.create(tableDAT, "devices")
    place(devices, 0, 200)
    init_device_table(devices, [])
    controls = mgr.create(tableDAT, "controls")
    place(controls, 200, 200)
    controls.clear()
    controls.appendRow(["param", "value"])
    controls.appendRow(["rescan", "0"])
    controls.appendRow(["push", "0"])
    push = mgr.create(tableDAT, "push")
    place(push, 400, 200)
    push.clear()
    push.appendRow(["ip", "action", "arg1", "arg2", "arg3", "arg4"])
    push.appendRow(["", "", "", "", "", ""])

    container = mgr.create(baseCOMP, "device_container")
    place(container, 0, -100)
    tmpl = _build_device_template(mgr)
    place(tmpl, 400, -100)

    # Discovery stubs (UDP) - reuse phase6 pattern lightly
    from builders.lib.packets import ARTNET_PORT, build_art_poll, bytes_to_td_hex

    poll_dat = mgr.create(textDAT, "poll_packet")
    poll_dat.text = bytes_to_td_hex(build_art_poll()).replace(" ", "")
    place(poll_dat, 600, 200)
    udp_in = mgr.create(udpinDAT, "udp_in")
    place(udp_in, 600, 0)
    set_par(udp_in, port=ARTNET_PORT)
    udp_out = mgr.create(udpoutDAT, "udp_out")
    place(udp_out, 800, 0)
    set_par(udp_out, port=ARTNET_PORT, address="255.255.255.255")

    mgr_ext = mgr.create(textDAT, "PrimusManagerExt")
    place(mgr_ext, 0, 400)
    mgr_ext.text = _MANAGER_EXT
    try:
        mgr.par.extension1 = mgr_ext
        mgr.par.promoteextension1 = True
    except Exception as e:
        print(f"[phase8] manager ext: {e}")

    # --- Cue Engine ---
    cues = root.create(baseCOMP, "PrimusCueEngine")
    place(cues, 600, 0)
    _add_custom_pars(
        cues,
        [
            ("int", "Cuenumber", 1, "Cue Number", {}),
            ("pulse", "Go", None, "GO", {}),
        ],
    )
    cue_table = cues.create(tableDAT, "cues")
    place(cue_table, 0, 200)
    init_cue_table(
        cue_table,
        [
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
                "targets": "*",
                "a0_content": "black",
                "a1_content": "black",
                "fade": "0.3",
                "notes": "blackout",
            },
        ],
    )
    cue_state = cues.create(tableDAT, "cue_state")
    place(cue_state, 200, 200)
    cue_state.clear()
    cue_state.appendRow(["param", "value"])
    cue_state.appendRow(["cue_index", "0"])
    cue_controls = cues.create(tableDAT, "controls")
    place(cue_controls, 400, 200)
    cue_controls.clear()
    cue_controls.appendRow(["param", "value"])
    cue_controls.appendRow(["go", "0"])
    cue_ext = cues.create(textDAT, "PrimusCueEngineExt")
    place(cue_ext, 0, 400)
    cue_ext.text = _CUE_EXT
    try:
        cues.par.extension1 = cue_ext
        cues.par.promoteextension1 = True
    except Exception as e:
        print(f"[phase8] cue ext: {e}")

    readme = root.create(textDAT, "README")
    place(readme, 0, 600)
    readme.text = (
        "Phase 9 components\n\n"
        "PrimusManager: Rescan / RebuildDevices; owns devices table + replicas.\n"
        "device_template: Custom Pars + PrimusDeviceExt methods.\n"
        "PrimusCueEngine: Go / Goto.\n\n"
        "Export each as .tox - see tox/README.md\n"
        "Handoff: handoffs/phase8_test.md"
    )

    # Copy extension sources into repo extensions/ is done by files on disk
    print(f"[phase8] built {root.path}")
    print("[phase8] Next: export PrimusManager / device_template / PrimusCueEngine to tox/")
    return root
