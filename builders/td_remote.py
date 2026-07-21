#!/usr/bin/env python3
"""
Drive TouchDesigner Primus builds from the shell / Cursor (no Textport paste).

Requires a one-time Textport install (see `install` command). After that:

    python3 builders/td_remote.py build 1
    python3 builders/td_remote.py build 1 --ip 192.168.8.166 --universe 0 --a0-type small_grid
    python3 builders/td_remote.py status
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDERS = ROOT / "builders"
CMD_PATH = BUILDERS / ".td_cmd.json"
RESULT_PATH = BUILDERS / ".td_result.json"
KWARGS_PATH = BUILDERS / ".td_build_kwargs.json"

DEFAULT_IP = "192.168.8.166"
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
    if phase < 1 or phase > 8:
        print(f"error: phase must be 1-8, got {phase}", file=sys.stderr)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remote-control TouchDesigner Primus phase builds via files."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_install = sub.add_parser("install", help="Print one-time Textport install snippet")
    p_install.set_defaults(func=cmd_install)

    p_build = sub.add_parser("build", help="Queue a phase build for PrimusBridge")
    p_build.add_argument("phase", type=int, help="Phase number 1-8")
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

    p_self = sub.add_parser(
        "selftest", help="Dry-run write/read cmd+result JSON without TouchDesigner"
    )
    p_self.set_defaults(func=cmd_selftest)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
