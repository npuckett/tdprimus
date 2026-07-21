"""
Standalone Primus device discovery (no TouchDesigner).

ArtPoll -> ArtPollReply: firmware version, PV3CAP1 caps, reported virtual counts.
Optional --probe-virt pushes ArtVirtualResolution and re-polls to see if it stuck.

Virtual send resolution requires firmware 3.11+. Repo V4 source is 3.13.0.

  python3 builders/discover_device.py
  python3 builders/discover_device.py --ip 192.168.8.166 --probe-virt 1,24
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from builders.lib.output_types import LOOK_OUTPUT_TYPES  # noqa: E402
from builders.lib.packets import (  # noqa: E402
    ARTNET_PORT,
    build_art_poll,
    build_output_config,
    build_receive_config,
    build_virtual_resolution,
    parse_art_poll_reply,
)

VIRTUAL_RES_MIN = (3, 11)
REPO_FIRMWARE = (3, 13, 0)


def _parse_ver(text: str | None):
    if not text:
        return None
    parts = []
    for p in str(text).strip().split("."):
        if not p.isdigit():
            break
        parts.append(int(p))
    return tuple(parts) if parts else None


def _ver_ge(ver, minimum) -> bool:
    if ver is None:
        return False
    a = list(ver) + [0, 0, 0]
    b = list(minimum) + [0, 0, 0]
    return tuple(a[:3]) >= tuple(b[:3])


def _fmt_ver(ver) -> str:
    if ver is None:
        return "unknown"
    return ".".join(str(x) for x in ver)


def _local_ips_on_subnet(target_ip: str) -> list[str]:
    """Return local IPv4s that share the /24 of target_ip (best-effort via ifconfig)."""
    import re
    import subprocess

    try:
        text = subprocess.check_output(["ifconfig"], text=True)
    except Exception:
        return []
    parts = target_ip.split(".")
    if len(parts) != 4:
        return []
    prefix = ".".join(parts[:3]) + "."
    found = []
    for m in re.finditer(r"inet (" + re.escape(prefix) + r"\d+)", text):
        ip = m.group(1)
        if ip != target_ip and ip not in found:
            found.append(ip)
    return found


def discover(
    timeout: float = 2.0,
    target_ip: str | None = None,
    bind_ip: str | None = None,
) -> list[dict]:
    """
    Art-Net nodes reply to the *source port* of the poll. Primus firmware
    answers on UDP 6454, so we must bind (iface, 6454) on the device subnet
    — ephemeral binds often get no replies even when ArtDmx send works.
    """
    candidates = []
    if bind_ip:
        candidates.append(bind_ip)
    if target_ip:
        candidates.extend(_local_ips_on_subnet(target_ip))
    candidates.append("0.0.0.0")

    last_err = None
    sock = None
    bound = None
    for ip in candidates:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind((ip, ARTNET_PORT))
            sock = s
            bound = s.getsockname()
            break
        except OSError as exc:
            last_err = exc
            s.close()
            # Fall back to ephemeral on this IP
            try:
                s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                s2.bind((ip, 0))
                sock = s2
                bound = s2.getsockname()
                break
            except OSError:
                continue

    if sock is None:
        raise OSError(f"could not bind UDP for ArtPoll: {last_err}")

    print(f"[discover] bound {bound}")
    sock.settimeout(0.25)
    poll = build_art_poll()
    destinations = ["255.255.255.255"]
    if target_ip:
        destinations = [target_ip, target_ip.rsplit(".", 1)[0] + ".255", "255.255.255.255"]
    for dest in destinations:
        try:
            sock.sendto(poll, (dest, ARTNET_PORT))
        except OSError as exc:
            print(f"[discover] send to {dest} failed: {exc}", file=sys.stderr)

    nodes: dict[str, dict] = {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            raw, _addr = sock.recvfrom(1024)
        except socket.timeout:
            continue
        except OSError:
            break
        parsed = parse_art_poll_reply(raw)
        if not parsed:
            continue
        ip = parsed["ip"]
        if target_ip and ip != target_ip:
            continue
        nodes[ip] = parsed
    sock.close()
    return list(nodes.values())


def enrich(node: dict) -> dict:
    caps = node.get("capabilities") or {}
    fw = _parse_ver(node.get("firmware_version"))
    # Prefer V: token if present in report (some builds)
    report = node.get("node_report") or ""
    for part in report.split("|"):
        if part.startswith("V:") and len(part) > 2:
            fw = _parse_ver(part[2:]) or fw
            break

    ports = []
    for p in caps.get("ports") or []:
        tid = p.get("type_id")
        type_key = (
            LOOK_OUTPUT_TYPES[tid]
            if isinstance(tid, int) and 0 <= tid < len(LOOK_OUTPUT_TYPES)
            else f"id:{tid}"
        )
        ports.append(
            {
                "port": p.get("port"),
                "type": type_key,
                "universe": p.get("universe"),
                "virtual": p.get("virtual"),
            }
        )

    supports_virt = _ver_ge(fw, VIRTUAL_RES_MIN)
    # Pre-3.11 NodeReport uses port:type:univ only (no 4th virtual field).
    ports_have_virt = any(p.get("virtual") is not None for p in ports)
    if ports and not ports_have_virt:
        supports_virt = False
    out_cfg = bool(caps.get("output_config"))
    return {
        "ip": node.get("ip"),
        "short_name": node.get("short_name"),
        "long_name": node.get("long_name"),
        "node_report": report,
        "firmware_version": _fmt_ver(fw),
        "firmware_tuple": list(fw) if fw else None,
        "virtual_resolution_required": f"{VIRTUAL_RES_MIN[0]}.{VIRTUAL_RES_MIN[1]}+",
        "virtual_resolution_supported": supports_virt,
        "needs_firmware_update_for_virt": (not supports_virt),
        "node_report_has_virtual_fields": ports_have_virt,
        "repo_source_firmware": ".".join(str(x) for x in REPO_FIRMWARE),
        "pv3cap1": bool(caps.get("known")),
        "features": caps.get("features"),
        "board": caps.get("board"),
        "receive_mode": caps.get("receive_mode"),
        "base_universe": caps.get("base_universe"),
        "output_config_capability": out_cfg,
        "ports": ports,
        "is_primus": node.get("is_primus"),
    }


def probe_virt(ip: str, counts: list[int], settle: float = 0.4) -> dict:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(build_output_config(["small_grid", "long_strip"]), (ip, ARTNET_PORT))
        time.sleep(0.05)
        sock.sendto(build_receive_config("split", 0), (ip, ARTNET_PORT))
        time.sleep(0.05)
        sock.sendto(build_virtual_resolution(counts), (ip, ARTNET_PORT))
    finally:
        sock.close()
    time.sleep(settle)
    after = discover(timeout=1.5, target_ip=ip)
    enriched = enrich(after[0]) if after else None
    reported = None
    if enriched:
        reported = [p.get("virtual") for p in enriched.get("ports") or []]
    # Pre-3.11 reports have no 4th virt field — treat as unsupported
    has_virt_fields = bool(reported) and any(v is not None for v in reported)
    stuck = (
        reported == counts
        if has_virt_fields and all(v is not None for v in reported)
        else False
    )
    return {
        "pushed_virtual": counts,
        "reported_virtual_after": reported,
        "report_includes_virtual_fields": has_virt_fields,
        "virtual_push_confirmed": stuck,
        "node_after": enriched,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Discover Primus firmware / virtual-res capability")
    ap.add_argument("--ip", default="192.168.8.166", help="Target device IP (also broadcasts)")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument(
        "--probe-virt",
        default=None,
        help="Push ArtVirtualResolution then re-poll, e.g. 1,24",
    )
    ap.add_argument(
        "--bind",
        default=None,
        help="Local IP to bind for ArtPoll (default: auto-detect on device subnet :6454)",
    )
    ap.add_argument(
        "--out",
        default=str(ROOT / "builders" / ".td_discover.json"),
        help="Write JSON report path",
    )
    args = ap.parse_args(argv)

    print(f"[discover] ArtPoll for {args.ip} (timeout={args.timeout}s)...")
    nodes = discover(timeout=args.timeout, target_ip=args.ip, bind_ip=args.bind)
    if not nodes:
        print("[discover] no reply; retrying without IP filter...")
        nodes = discover(timeout=args.timeout, target_ip=None, bind_ip=args.bind)
        nodes = [n for n in nodes if n.get("ip") == args.ip] or nodes

    report = {
        "target_ip": args.ip,
        "found": len(nodes),
        "nodes": [enrich(n) for n in nodes],
        "notes": [
            "Firmware 3.11+ required for ArtVirtualResolution (0x8130).",
            "If virt=1 only lights the first physical LED, device virtual count "
            "is still >1 (short ArtDmx zero-pads; upsample uses stored virt).",
            f"V4 Arduino source in repo is {_fmt_ver(REPO_FIRMWARE)}.",
        ],
    }

    if args.probe_virt:
        counts = [int(x.strip()) for x in args.probe_virt.split(",")]
        print(f"[discover] probing ArtVirtualResolution {counts} -> {args.ip}")
        before = report["nodes"][0] if report["nodes"] else None
        probe = probe_virt(args.ip, counts)
        report["probe"] = {"before": before, **probe}

    Path(args.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"[discover] wrote {args.out}")

    if not report["nodes"]:
        print("[discover] FAIL: no ArtPollReply (check Ethernet / IP)", file=sys.stderr)
        return 2

    node = next((n for n in report["nodes"] if n["ip"] == args.ip), report["nodes"][0])
    print()
    print("=== verdict ===")
    print(f"device:   {node['ip']}  {node.get('short_name')}")
    print(f"firmware: {node['firmware_version']}  (need {node['virtual_resolution_required']} for virt)")
    print(f"virt OK:  {node['virtual_resolution_supported']}")
    print(f"update?:  {node['needs_firmware_update_for_virt']}")
    print(f"recv:     {node.get('receive_mode')} base={node.get('base_universe')}")
    print(f"ports:    {node.get('ports')}")
    if report.get("probe"):
        print(f"probe:    pushed {report['probe']['pushed_virtual']} -> "
              f"reported {report['probe']['reported_virtual_after']} "
              f"confirmed={report['probe']['virtual_push_confirmed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
