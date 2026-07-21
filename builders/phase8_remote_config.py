"""
Phase 8 - Remote device management (vendor opcodes via UDP Out).

    exec(open(f'{project.folder}/builders/phase8_remote_config.py').read())
    build()

Edit `push` table row for a device IP and action, set controls.push=1.
Re-poll verify is left as a manual rescan (wire to phase6 or built-in poll).
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

from builders.lib.packets import (  # noqa: E402
    ARTNET_PORT,
    build_art_address,
    build_art_poll,
    build_ip_config,
    build_output_config,
    build_receive_config,
    build_virtual_resolution,
    bytes_to_td_hex,
)
from builders.lib.td_builder import (  # noqa: E402
    prepare_build,
    clear_children,
    ensure_base,
    init_device_table,
    place,
    set_par,
)

PARENT_PATH = "/project1"
BASE_NAME = "primus_phase8"

_PUSH_EXECUTE = r'''
import struct
import sys

def onTableChange(dat):
    try:
        if int(dat['push', 1]) != 1:
            return
    except Exception:
        return
    dat['push', 1] = 0
    root = dat.parent()
    # Ensure builders.lib importable
    try:
        folder = project.folder
        if folder not in sys.path:
            sys.path.insert(0, folder)
    except Exception:
        pass
    from builders.lib.packets import (
        build_art_address, build_output_config, build_receive_config,
        build_virtual_resolution, build_ip_config, build_art_poll,
    )

    push = root.op('push')
    if push is None or push.numRows < 2:
        print('[phase7] no push row')
        return
    # columns: ip, action, arg1, arg2, arg3, arg4
    ip = push[1, 'ip'].val.strip()
    action = push[1, 'action'].val.strip().lower()
    a1 = push[1, 'arg1'].val.strip()
    a2 = push[1, 'arg2'].val.strip()
    a3 = push[1, 'arg3'].val.strip()
    a4 = push[1, 'arg4'].val.strip()
    if not ip or not action:
        print('[phase7] ip and action required')
        return

    try:
        pkt = _build(action, a1, a2, a3, a4,
                     build_art_address, build_output_config, build_receive_config,
                     build_virtual_resolution, build_ip_config)
    except Exception as e:
        print('[phase7] build failed:', e)
        return

    udp = root.op('udp_out')
    if udp is None:
        print('[phase7] missing udp_out')
        return
    try:
        udp.par.address = ip
    except Exception:
        pass
    try:
        udp.sendBytes(pkt)
        print(f'[phase7] sent {action} ({len(pkt)} bytes) -> {ip}')
    except Exception as e:
        try:
            udp.send(pkt.decode('latin1'))
            print(f'[phase7] sent {action} via send() -> {ip}')
        except Exception as e2:
            print('[phase7] send failed', e, e2)
            return

    # Optional verify: send ArtPoll after short delay note
    if int(dat['autopoll_after', 1] or 0) == 1:
        poll = build_art_poll()
        try:
            udp.par.address = '255.255.255.255'
            udp.sendBytes(poll)
            print('[phase7] ArtPoll broadcast for verify')
        except Exception as e:
            print('[phase7] autopoll failed', e)

def _build(action, a1, a2, a3, a4, build_art_address, build_output_config,
           build_receive_config, build_virtual_resolution, build_ip_config):
    if action == 'rename':
        return build_art_address(a1)
    if action == 'output_config':
        # arg1,arg2 = type keys for A0,A1
        return build_output_config([a1 or 'none', a2 or 'none'])
    if action == 'receive_config':
        # arg1=split|combined  arg2=base universe
        return build_receive_config(a1 or 'combined', int(a2 or 0))
    if action == 'virtual_resolution':
        return build_virtual_resolution([int(a1 or 1), int(a2 or 1)])
    if action == 'ip_config':
        # arg1=dhcp|static  arg2=ip arg3=gw arg4=subnet
        if (a1 or 'dhcp').lower() == 'dhcp':
            return build_ip_config(0)
        return build_ip_config(1, a2, a3, a4)
    if action == 'identify':
        # Identify = temporary solid white via ArtDmx - built in identify helper
        # For protocol-only phase, send a short white ArtDmx frame (universe from arg1)
        from builders.lib.packets import build_art_dmx
        univ = int(a1 or 0)
        n = int(a2 or 73)  # default badge+collar virtual-ish
        return build_art_dmx(univ, bytes([255, 255, 255]) * n)
    raise ValueError(f'unknown action {action!r}')
'''


def build(parent_path: str = PARENT_PATH):
    prepare_build(globals())
    base = ensure_base(parent_path, BASE_NAME, recreate=True)

    devices = base.create(tableDAT, "devices")
    place(devices, 0, 300)
    init_device_table(devices, [])

    push = base.create(tableDAT, "push")
    place(push, 250, 300)
    push.clear()
    push.appendRow(["ip", "action", "arg1", "arg2", "arg3", "arg4"])
    push.appendRow(
        ["192.168.1.100", "rename", "PrimusTest", "", "", ""]
    )

    controls = base.create(tableDAT, "controls")
    place(controls, 500, 300)
    controls.clear()
    controls.appendRow(["param", "value"])
    controls.appendRow(["push", "0"])
    controls.appendRow(["autopoll_after", "1"])

    examples = base.create(textDAT, "examples")
    place(examples, 0, 100)
    examples.text = _EXAMPLES

    # Prebuilt packet hex dump for offline inspection
    samples = base.create(tableDAT, "packet_samples")
    place(samples, 250, 100)
    samples.clear()
    samples.appendRow(["action", "hex", "len"])
    for label, pkt in (
        ("rename", build_art_address("PrimusTest")),
        ("receive_combined_0", build_receive_config("combined", 0)),
        ("virtual_1_72", build_virtual_resolution([1, 72])),
        ("output_sg_ls", build_output_config(["small_grid", "long_strip"])),
        ("ip_dhcp", build_ip_config(0)),
        ("poll", build_art_poll()),
    ):
        samples.appendRow([label, bytes_to_td_hex(pkt), str(len(pkt))])

    udp_out = base.create(udpoutDAT, "udp_out")
    place(udp_out, 500, 100)
    set_par(udp_out, port=ARTNET_PORT, protocol="udp", address="192.168.1.100")

    push_exec = base.create(executeDAT, "push_execute")
    place(push_exec, 750, 100)
    push_exec.text = _PUSH_EXECUTE
    try:
        push_exec.par.dat = controls.path
        push_exec.par.tablechange = True
    except Exception:
        pass

    warn = base.create(textDAT, "WARNINGS")
    place(warn, 0, 500)
    warn.text = (
        "WARNINGS\n"
        "- ArtAddress (rename) uses real Art-Net opcode 0x6000 - UNICAST only; "
        "do not broadcast on mixed Art-Net LANs.\n"
        "- ArtIPConfig reboots the device after NVS write.\n"
        "- After any push, re-poll (autopoll_after=1) and confirm devices table / PrimusCentral.\n"
    )

    info = base.create(textDAT, "README")
    place(info, 250, 500)
    info.text = (
        "Phase 8 remote config\n"
        "Fill `push` row -> set controls.push=1.\n"
        "Actions: rename | output_config | receive_config | virtual_resolution | "
        "ip_config | identify\n"
        "See handoffs/phase7_test.md and examples DAT."
    )
    print(f"[phase7] built {base.path}")
    return base


_EXAMPLES = """Push table examples (edit row 1):

ip              action               arg1        arg2        arg3           arg4
192.168.1.100   rename               NewName
192.168.1.100   output_config        small_grid  long_strip
192.168.1.100   receive_config       combined    0
192.168.1.100   receive_config       split       0
192.168.1.100   virtual_resolution   1           72
192.168.1.100   virtual_resolution   32          72
192.168.1.100   ip_config            dhcp
192.168.1.100   ip_config            static      192.168.1.50 192.168.1.1   255.255.255.0
192.168.1.100   identify             0           73
"""
