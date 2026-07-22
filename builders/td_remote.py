#!/usr/bin/env python3
"""
Drive TouchDesigner Primus builds from the shell / Cursor (no Textport paste).

Requires a one-time Textport install (see `install` command). After that:

    python3 builders/td_remote.py preflight --bridge
    python3 builders/td_remote.py build 1
    python3 builders/td_remote.py build 1 --ip 192.168.8.166 --universe 0 --a0-type small_grid
    python3 builders/td_remote.py status
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDERS = ROOT / "builders"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
CMD_PATH = BUILDERS / ".td_cmd.json"
RESULT_PATH = BUILDERS / ".td_result.json"
KWARGS_PATH = BUILDERS / ".td_build_kwargs.json"

DEFAULT_IP = "192.168.8.166"
DEFAULT_BIND_IP = "192.168.8.199"
DEFAULT_UNIVERSE = 0
DEFAULT_A0 = "small_grid"
DEFAULT_A1 = "long_strip"
DEFAULT_TIMEOUT = 30.0

INSTALL_SNIPPET = """\
# One-time TEXTPORT install (TD must have this .toe open,
# saved under the tdprimus repo root so project.folder points here).
# Do NOT run shell commands like `python3 builders/td_remote.py ...` in Textport.
# Those belong in Terminal / Cursor.

exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
install()
"""


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2))


def cmd_install(_: argparse.Namespace) -> int:
    print(INSTALL_SNIPPET)
    print("# After install, leave TD running and use:")
    print("#   python3 builders/td_remote.py build 1")
    return 0


def _write_cmd(payload: dict) -> dict:
    BUILDERS.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload.setdefault("id", uuid.uuid4().hex)
    payload.setdefault("ts", time.time())
    CMD_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def _read_result() -> dict | None:
    if not RESULT_PATH.exists():
        return None
    try:
        raw = RESULT_PATH.read_text(encoding="utf-8").strip()
        if not raw:
            return None
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"bad result file: {exc}", "traceback": None}


def cmd_build(args: argparse.Namespace) -> int:
    phase = int(args.phase)
    if phase < 1 or phase > 9:
        print(f"error: phase must be 1-9, got {phase}", file=sys.stderr)
        return 2

    # Snapshot prior result id so we do not accept a stale file as success.
    prior = _read_result()
    prior_id = prior.get("id") if prior else None

    payload = _write_cmd(
        {
            "cmd": "build",
            "phase": phase,
            "ip": args.ip,
            "device_ip": args.ip,
            "universe": int(args.universe),
            "a0_type": args.a0_type,
            "a1_type": args.a1_type,
            "recv_mode": args.recv_mode,
            "pattern": args.pattern,
        }
    )
    sticky_body = {
        "phase": phase,
        "ip": args.ip,
        "device_ip": args.ip,
        "universe": int(args.universe),
        "a0_type": args.a0_type,
        "a1_type": args.a1_type,
        "recv_mode": args.recv_mode,
        "pattern": args.pattern,
        "level": int(args.level),
        "id": payload["id"],
        "ts": time.time(),
    }
    if getattr(args, "a0_virtual", None) is not None:
        sticky_body["a0_virtual"] = int(args.a0_virtual)
    if getattr(args, "a1_virtual", None) is not None:
        sticky_body["a1_virtual"] = int(args.a1_virtual)
    if getattr(args, "a0_pattern", None):
        sticky_body["a0_pattern"] = args.a0_pattern
    if getattr(args, "a1_pattern", None):
        sticky_body["a1_pattern"] = args.a1_pattern
    if getattr(args, "a0_source", None) is not None:
        sticky_body["a0_source"] = int(args.a0_source)
    if getattr(args, "a1_source", None) is not None:
        sticky_body["a1_source"] = int(args.a1_source)
    if getattr(args, "bind_ip", None):
        sticky_body["bind_ip"] = str(args.bind_ip)
    if getattr(args, "devices", None):
        supplied = str(args.devices)
        candidate = Path(supplied).expanduser()
        try:
            device_rows = (
                json.loads(candidate.read_text(encoding="utf-8"))
                if candidate.exists()
                else json.loads(supplied)
            )
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: --devices must be a JSON list or path to one: {exc}", file=sys.stderr)
            return 2
        if not isinstance(device_rows, list):
            print("error: --devices JSON must be a list of device-profile objects", file=sys.stderr)
            return 2
        sticky_body["device_rows_json"] = json.dumps(device_rows)
    KWARGS_PATH.write_text(json.dumps(sticky_body, indent=2) + "\n", encoding="utf-8")
    cmd_id = payload["id"]
    print(
        f"[td_remote] wrote {CMD_PATH.relative_to(ROOT)} "
        f"(phase={phase} id={cmd_id[:8]}...)"
    )
    print("[td_remote] waiting for PrimusBridge in TouchDesigner...")

    deadline = time.time() + float(args.timeout)
    while time.time() < deadline:
        result = _read_result()
        if result and result.get("id") == cmd_id:
            _print_result(result)
            return 0 if result.get("ok") else 1
        # Ignore stale result with different id
        if result and result.get("id") not in (None, prior_id, cmd_id):
            # Another command completed; keep waiting for ours
            pass
        time.sleep(0.25)

    print(
        f"[td_remote] TIMEOUT after {args.timeout}s - is TouchDesigner running "
        "with PrimusBridge installed?\n"
        f"  One-time Textport: python3 builders/td_remote.py install\n"
        f"  Cmd file still at: {CMD_PATH}"
        + (" (not consumed)" if CMD_PATH.exists() else " (consumed; check TD errors)"),
        file=sys.stderr,
    )
    stale = _read_result()
    if stale:
        print("[td_remote] last .td_result.json (may be stale):", file=sys.stderr)
        _print_json(stale)
    return 3


def _print_result(result: dict) -> None:
    ok = result.get("ok")
    phase = result.get("phase")
    msg = result.get("message") or ""
    status = "OK" if ok else "FAIL"
    print(f"[td_remote] {status} phase={phase} - {msg}")
    if not ok:
        err = result.get("error")
        if err:
            print(f"[td_remote] error: {err}", file=sys.stderr)
        tb = result.get("traceback")
        if tb:
            print(tb, file=sys.stderr)
    _print_json(result)


def cmd_status(_: argparse.Namespace) -> int:
    result = _read_result()
    if result is None:
        print(f"[td_remote] no result file at {RESULT_PATH}")
        print("Run a build first, or confirm PrimusBridge is installed in TD.")
        return 1
    _print_result(result)
    return 0 if result.get("ok") else 1


def cmd_selftest(_: argparse.Namespace) -> int:
    """Dry-run cmd/result file format without TouchDesigner."""
    BUILDERS.mkdir(parents=True, exist_ok=True)
    payload = {
        "cmd": "build",
        "phase": 1,
        "ip": DEFAULT_IP,
        "device_ip": DEFAULT_IP,
        "universe": DEFAULT_UNIVERSE,
        "a0_type": DEFAULT_A0,
        "a1_type": DEFAULT_A1,
        "recv_mode": "split",
        "id": "selftest-" + uuid.uuid4().hex[:8],
        "ts": time.time(),
    }
    CMD_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    loaded_cmd = json.loads(CMD_PATH.read_text(encoding="utf-8"))
    assert loaded_cmd["cmd"] == "build"
    assert loaded_cmd["phase"] == 1

    fake = {
        "ok": True,
        "id": payload["id"],
        "phase": 1,
        "error": None,
        "traceback": None,
        "message": "selftest ok (no TD)",
        "ts": time.time(),
    }
    RESULT_PATH.write_text(json.dumps(fake, indent=2) + "\n", encoding="utf-8")
    loaded = _read_result()
    assert loaded is not None
    assert loaded["id"] == payload["id"]
    assert loaded["ok"] is True

    # Clean cmd (bridge would delete it); leave a selftest result for status demos
    if CMD_PATH.exists():
        CMD_PATH.unlink()

    print("[td_remote] selftest OK - cmd/result JSON format verified")
    _print_json(loaded)
    return 0


def cmd_ping(args: argparse.Namespace) -> int:
    prior = _read_result()
    prior_id = prior.get("id") if prior else None
    payload = _write_cmd({"cmd": "ping"})
    cmd_id = payload["id"]
    print(f"[td_remote] ping id={cmd_id[:8]}...")
    deadline = time.time() + float(args.timeout)
    while time.time() < deadline:
        result = _read_result()
        if result and result.get("id") == cmd_id:
            _print_result(result)
            return 0 if result.get("ok") else 1
        if result and result.get("id") == prior_id:
            time.sleep(0.25)
            continue
        time.sleep(0.25)
    print("[td_remote] ping TIMEOUT - PrimusBridge not responding", file=sys.stderr)
    return 3


def _local_ipv4s() -> list[str]:
    """List host IPv4 addresses (macOS ifconfig / Windows ipconfig / Linux ip)."""
    system = platform.system()
    try:
        if system == "Windows":
            text = subprocess.check_output(["ipconfig"], text=True, errors="replace")
            # IPv4 Address. . . . . . . . . . . : 192.168.1.10
            return re.findall(
                r"(?:IPv4 Address|IP Address)[^\d]*(\d+\.\d+\.\d+\.\d+)",
                text,
                flags=re.IGNORECASE,
            )
        if system == "Linux":
            try:
                text = subprocess.check_output(
                    ["ip", "-4", "-o", "addr", "show"], text=True, errors="replace"
                )
                return re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", text)
            except Exception:
                pass
        text = subprocess.check_output(["ifconfig"], text=True, errors="replace")
        return re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", text)
    except Exception:
        return []


def _icmp_reachable(ip: str, count: int = 2) -> bool:
    """ICMP ping with platform-appropriate flags."""
    system = platform.system()
    if system == "Windows":
        cmd = ["ping", "-n", str(count), "-w", "2000", ip]
    else:
        # macOS/BSD: -W is milliseconds; Linux ping often uses -W seconds.
        # Prefer -W 2000 on Darwin; on Linux use -W 2.
        wait = "2000" if system == "Darwin" else "2"
        cmd = ["ping", "-c", str(count), "-W", wait, ip]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


def cmd_preflight(args: argparse.Namespace) -> int:
    """Check bind_ip is local and device IP answers ICMP before a build."""
    bind_ip = str(args.bind_ip or DEFAULT_BIND_IP).strip()
    device_ip = str(args.ip or DEFAULT_IP).strip()
    local = _local_ipv4s()
    ok = True

    print(f"[preflight] local IPv4: {', '.join(local) or '(none)'}")
    if bind_ip in local:
        print(f"[preflight] OK bind_ip {bind_ip} is on this host")
    else:
        print(
            f"[preflight] FAIL: bind_ip {bind_ip} not assigned to any local interface "
            "(Thunderbolt Ethernet may have lost its address)",
            file=sys.stderr,
        )
        ok = False

    if _icmp_reachable(device_ip):
        print(f"[preflight] OK ping {device_ip}")
    else:
        print(
            f"[preflight] FAIL: no ICMP reply from {device_ip} "
            "(device power / LAN / wrong subnet)",
            file=sys.stderr,
        )
        ok = False

    if getattr(args, "bridge", False):
        print("[preflight] checking PrimusBridge...")
        bridge_rc = cmd_ping(args)
        if bridge_rc != 0:
            ok = False
        else:
            print("[preflight] OK PrimusBridge")

    if ok:
        print(
            f"[preflight] PASS — safe to build "
            f"(e.g. python3 builders/td_remote.py build 5)"
        )
        return 0
    print(
        "[preflight] FAIL — fix network / device / Bridge before building",
        file=sys.stderr,
    )
    return 1


def cmd_discover(args: argparse.Namespace) -> int:
    """Ask Phase 7 to ArtPoll (or run offline discover_device if TD skip)."""
    if getattr(args, "offline", False):
        from builders.discover_device import discover, enrich

        bind = str(args.bind_ip or DEFAULT_BIND_IP)
        print(f"[td_remote] offline ArtPoll bind={bind}…")
        nodes = [enrich(n) for n in discover(timeout=float(args.timeout), bind_ip=bind)]
        primus = [n for n in nodes if n.get("is_primus")]
        print(f"[td_remote] found {len(primus)} Primus / {len(nodes)} total")
        for n in primus:
            print(f"  {n.get('ip')}  {n.get('short_name')}  fw={n.get('firmware_version')}  {n.get('receive_mode')}")
        out = BUILDERS / ".td_phase7_discover.json"
        out.write_text(
            json.dumps({"phase": 7, "offline": True, "bind_ip": bind, "nodes": primus}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return 0 if primus else 1

    cue_path = BUILDERS / ".td_discover_cmd.json"
    payload = {"cmd": "rescan", "id": uuid.uuid4().hex, "ts": time.time()}
    BUILDERS.mkdir(parents=True, exist_ok=True)
    cue_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[td_remote] discover → {cue_path.relative_to(ROOT)}")
    deadline = time.time() + float(args.timeout) + 3.0
    result_path = BUILDERS / ".td_phase7_discover.json"
    prior_mtime = result_path.stat().st_mtime if result_path.exists() else 0.0
    while time.time() < deadline:
        try:
            raw = cue_path.read_text(encoding="utf-8").strip()
            if raw in ("", "{}"):
                if result_path.exists() and result_path.stat().st_mtime >= prior_mtime:
                    data = json.loads(result_path.read_text(encoding="utf-8"))
                    print(
                        f"[td_remote] discover OK — "
                        f"{data.get('primus', '?')} Primus, {data.get('other', '?')} other"
                    )
                    _print_json(data)
                    return 0
        except Exception:
            pass
        time.sleep(0.2)
    print(
        "[td_remote] discover TIMEOUT — build Phase 7 first "
        "(python3 builders/td_remote.py build 7)",
        file=sys.stderr,
    )
    return 3


def cmd_go(args: argparse.Namespace) -> int:
    """Drive Phase 6 via builders/.td_cue_cmd.json (polled by primus_phase6)."""
    cue_path = BUILDERS / ".td_cue_cmd.json"
    if getattr(args, "blackout", None) is not None:
        payload = {
            "cmd": "blackout",
            "on": bool(args.blackout),
            "id": uuid.uuid4().hex,
            "ts": time.time(),
        }
        label = f"blackout={'on' if args.blackout else 'off'}"
    elif getattr(args, "goto", None) is not None:
        payload = {
            "cmd": "goto",
            "cue": int(args.goto),
            "id": uuid.uuid4().hex,
            "ts": time.time(),
        }
        label = f"goto {args.goto}"
    else:
        payload = {"cmd": "go", "id": uuid.uuid4().hex, "ts": time.time()}
        label = "go"
    BUILDERS.mkdir(parents=True, exist_ok=True)
    cue_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[td_remote] {label} → {cue_path.relative_to(ROOT)}")
    deadline = time.time() + float(args.timeout)
    while time.time() < deadline:
        if not cue_path.exists():
            print(f"[td_remote] {label} consumed")
            return 0
        try:
            raw = cue_path.read_text(encoding="utf-8").strip()
            if raw in ("", "{}"):
                print(f"[td_remote] {label} consumed")
                return 0
        except Exception:
            pass
        time.sleep(0.1)
    print(
        "[td_remote] TIMEOUT — is Phase 6 built with go_execute active?",
        file=sys.stderr,
    )
    return 3


def cmd_manager(args: argparse.Namespace) -> int:
    """Drive PrimusManager via builders/.td_manager_cmd.json (Phase 9)."""
    action = (args.action or "rescan").lower().replace("-", "_")
    if action in ("createoutputs", "create"):
        action = "create_outputs"
    if action not in ("rescan", "create_outputs"):
        print(f"error: manager action must be rescan or create_outputs, got {action}", file=sys.stderr)
        return 2
    path = BUILDERS / ".td_manager_cmd.json"
    payload = {"cmd": action, "id": uuid.uuid4().hex, "ts": time.time()}
    BUILDERS.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"[td_remote] manager {action} → {path.relative_to(ROOT)}")
    deadline = time.time() + float(args.timeout)
    result_path = BUILDERS / ".td_phase9_discover.json"
    prior_mtime = result_path.stat().st_mtime if result_path.exists() else 0.0
    while time.time() < deadline:
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if raw in ("", "{}"):
                if action == "rescan" and result_path.exists() and result_path.stat().st_mtime >= prior_mtime:
                    data = json.loads(result_path.read_text(encoding="utf-8"))
                    print(
                        f"[td_remote] manager rescan OK — "
                        f"{data.get('primus', '?')} Primus, {data.get('other', '?')} other"
                    )
                    _print_json(data)
                    return 0
                if action == "create_outputs":
                    print("[td_remote] manager create_outputs consumed")
                    return 0
                # rescan consumed but result not yet written
        except Exception:
            pass
        time.sleep(0.2)
    print(
        "[td_remote] manager TIMEOUT — build Phase 9 first "
        "(python3 builders/td_remote.py build 9)",
        file=sys.stderr,
    )
    return 3


def cmd_recover(args: argparse.Namespace) -> int:
    """After a NIC/device flap: preflight, then rebuild Phase 5 (or --phase)."""
    phase = int(getattr(args, "phase", 5) or 5)
    print(f"[recover] preflight then build phase {phase}...")
    pre = argparse.Namespace(
        ip=args.ip,
        bind_ip=args.bind_ip,
        bridge=True,
        timeout=args.timeout,
    )
    rc = cmd_preflight(pre)
    if rc != 0:
        print("[recover] aborted — fix network before rebuilding", file=sys.stderr)
        return rc
    build = argparse.Namespace(
        phase=phase,
        ip=args.ip,
        universe=DEFAULT_UNIVERSE,
        a0_type=DEFAULT_A0,
        a1_type=DEFAULT_A1,
        recv_mode="split",
        pattern="thirds",
        a0_virtual=1,
        a1_virtual=72,
        a0_source=None,
        a1_source=None,
        bind_ip=args.bind_ip,
        devices=None,
        a0_pattern="solid_red",
        a1_pattern="thirds",
        level=64,
        timeout=args.timeout,
    )
    rc = cmd_build(build)
    if rc == 0:
        if phase >= 9:
            print(
                "[recover] rebuild OK — watch PrimusOutput link.state=ok and "
                "builders/.td_phase9_diag_*.json (sends should climb)"
            )
        else:
            print(
                "[recover] rebuild OK — watch primus_a/link.state=ok and "
                "builders/.td_phase5_diag.json (sends should climb)"
            )
    return rc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remote-control TouchDesigner Primus phase builds via files."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Print one-time Textport install snippet")
    p_install.set_defaults(func=cmd_install)

    p_build = sub.add_parser("build", help="Queue a phase build for PrimusBridge")
    p_build.add_argument("phase", type=int, help="Phase number 1-9")
    p_build.add_argument("--ip", default=DEFAULT_IP, help=f"Device IP (default {DEFAULT_IP})")
    p_build.add_argument(
        "--universe", type=int, default=DEFAULT_UNIVERSE, help="Art-Net universe"
    )
    p_build.add_argument("--a0-type", dest="a0_type", default=DEFAULT_A0)
    p_build.add_argument("--a1-type", dest="a1_type", default=DEFAULT_A1)
    p_build.add_argument(
        "--recv-mode",
        dest="recv_mode",
        default="combined",
        help="Receive mode (default combined; Phase 1 is single-output regardless)",
    )
    p_build.add_argument("--a0-virtual", dest="a0_virtual", type=int, default=None)
    p_build.add_argument("--a1-virtual", dest="a1_virtual", type=int, default=None)
    p_build.add_argument(
        "--a0-source",
        dest="a0_source",
        type=int,
        default=None,
        help="Phase 4 A0 generator: 0=noise 1=ramp 2=solid",
    )
    p_build.add_argument(
        "--a1-source",
        dest="a1_source",
        type=int,
        default=None,
        help="Phase 4 A1 generator: 0=noise 1=ramp 2=solid",
    )
    p_build.add_argument(
        "--bind-ip",
        dest="bind_ip",
        default=None,
        help="Local NIC IP to bind UDP (wired), e.g. 192.168.8.199",
    )
    p_build.add_argument(
        "--devices",
        help="Phase 5: JSON profile list, or a path to a JSON file",
    )
    p_build.add_argument(
        "--a0-pattern",
        dest="a0_pattern",
        default="solid_red",
        help="Phase 2/3 A0 pattern (default solid_red)",
    )
    p_build.add_argument(
        "--a1-pattern",
        dest="a1_pattern",
        default="thirds",
        help="Phase 2/3 A1 pattern (default thirds)",
    )
    p_build.add_argument(
        "--pattern",
        default="thirds",
        choices=(
            "thirds",
            "rows",
            "solid_red",
            "solid_green",
            "solid_blue",
            "index_white",
        ),
        help="Phase 1 test pattern (default thirds)",
    )
    p_build.add_argument(
        "--level",
        type=int,
        default=64,
        help="Peak RGB level 0-255 (default 64)",
    )
    p_build.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Seconds to wait for result"
    )
    p_build.set_defaults(func=cmd_build)

    p_status = sub.add_parser("status", help="Read builders/.td_result.json")
    p_status.set_defaults(func=cmd_status)

    p_ping = sub.add_parser("ping", help="Ask PrimusBridge for a pong (TD must be running)")
    p_ping.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p_ping.set_defaults(func=cmd_ping)

    p_pre = sub.add_parser(
        "preflight",
        help="Verify bind_ip is local and device IP answers ping before building",
    )
    p_pre.add_argument("--ip", default=DEFAULT_IP, help=f"Device IP (default {DEFAULT_IP})")
    p_pre.add_argument(
        "--bind-ip",
        dest="bind_ip",
        default=DEFAULT_BIND_IP,
        help=f"Local NIC IP that must exist (default {DEFAULT_BIND_IP})",
    )
    p_pre.add_argument(
        "--bridge",
        action="store_true",
        help="Also ping PrimusBridge in TouchDesigner",
    )
    p_pre.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p_pre.set_defaults(func=cmd_preflight)

    p_disc = sub.add_parser(
        "discover",
        help="Phase 7 ArtPoll rescan (or --offline without TD)",
    )
    p_disc.add_argument(
        "--bind-ip",
        dest="bind_ip",
        default=DEFAULT_BIND_IP,
        help=f"Local NIC IP (default {DEFAULT_BIND_IP})",
    )
    p_disc.add_argument(
        "--offline",
        action="store_true",
        help="Run builders/discover_device.py in this shell (no Phase 7 COMP)",
    )
    p_disc.add_argument("--timeout", type=float, default=2.0)
    p_disc.set_defaults(func=cmd_discover)

    p_go = sub.add_parser("go", help="Phase 6 cue control (GO / goto / blackout)")
    p_go.add_argument("--goto", type=int, default=None, help="Jump to cue number")
    p_go.add_argument(
        "--blackout",
        type=int,
        choices=(0, 1),
        default=None,
        help="1=blackout all devices, 0=restore",
    )
    p_go.add_argument("--timeout", type=float, default=10.0)
    p_go.set_defaults(func=cmd_go)

    p_mgr = sub.add_parser(
        "manager",
        help="Phase 9 PrimusManager control (rescan / create_outputs)",
    )
    p_mgr.add_argument(
        "action",
        nargs="?",
        default="rescan",
        help="rescan | create_outputs (default rescan)",
    )
    p_mgr.add_argument("--timeout", type=float, default=10.0)
    p_mgr.set_defaults(func=cmd_manager)

    p_rec = sub.add_parser(
        "recover",
        help="Preflight then rebuild Phase 5 after a NIC/device reconnect",
    )
    p_rec.add_argument("--ip", default=DEFAULT_IP, help=f"Device IP (default {DEFAULT_IP})")
    p_rec.add_argument(
        "--bind-ip",
        dest="bind_ip",
        default=DEFAULT_BIND_IP,
        help=f"Local NIC IP (default {DEFAULT_BIND_IP})",
    )
    p_rec.add_argument(
        "--phase",
        type=int,
        default=5,
        help="Phase to rebuild after preflight (default 5)",
    )
    p_rec.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    p_rec.set_defaults(func=cmd_recover)

    p_self = sub.add_parser(
        "selftest", help="Dry-run write/read cmd+result JSON without TouchDesigner"
    )
    p_self.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
