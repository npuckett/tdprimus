# Workshop status — checkpoint after Phase 7

**Date:** 2026-07-21  
**Branch:** `main` (local; Phase 8 not started)  
**Stopped at:** Phase 7 Discovery verified; Phase 8 remote config deferred by choice.

## Where we are

| Phase | Status | Notes |
|-------|--------|-------|
| 0–4 | Done earlier | Protocol → generative sampling |
| **5 Multi-device** | **Working** | Dual ArtDmx, reconnect, distinct looks |
| **6 Cues** | **Working** | Cue deck UI + shell; OSC map ready, not show-tested |
| **7 Discovery** | **Working** | ArtPoll finds both workshop nodes |
| 8 Remote cfg | Not started | Next when ready |
| 9 Components | Not started | |

Live stack in TD (typical):

```text
SharedMedia → primus_a / primus_b (Phase 5 ArtDmx)
                    ↑
              primus_phase6 (cues)
primus_phase7 (ArtPoll → devices table)
PrimusControl + PrimusBridge (td_remote)
```

## Workshop LAN

| Role | Value |
|------|--------|
| Mac bind IP | `192.168.8.199` (wired, often `en4`) |
| Device A (A15) | `192.168.8.166` — split, fw **3.13** |
| Device B (A13) | `192.168.8.164` — split, fw **3.13** |
| Default brightness | `0.1` on each device `sampling` table |
| Receive mode | **split** (stay on this for workshop) |

Phase 5 default profile keeps both active with different media (`demo` vs `alt`) so the two units do not look identical.

## Everyday commands

```bash
# Health
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py ping

# Live look (after NIC/device flap)
python3 builders/td_remote.py recover          # rebuild Phase 5 + harden
python3 builders/td_remote.py build 5
python3 builders/td_remote.py build 6         # cue deck
python3 builders/td_remote.py build 7         # discovery COMP

# Cues
python3 builders/td_remote.py go
python3 builders/td_remote.py go --goto 3
python3 builders/td_remote.py go --blackout 1

# Discovery
python3 builders/td_remote.py discover
python3 builders/td_remote.py discover --offline
```

## Verified Phase 6 cues (edit live in `primus_phase6/cues`)

| Cue | Intent |
|-----|--------|
| 1 | Both devices → `demo` |
| 2 | Both → `alt` + hue |
| 3 | Split: A=`demo`, B=`alt` |
| 4 | Blackout |

UI: `/project1/primus_phase6` → **Cue** page (GO / Goto / Blackout).  
OSC (UDP **7000**): `/primus/cue/go`, `/goto`, `/blackout` — wired but not exercised in this workshop session.

## Verified Phase 7 discover (2026-07-21)

`td_remote.py discover` → **2 Primus, 0 other**:

- A15 `.166` — small_grid + long_strip, split, fw 3.13  
- A13 `.164` — same geometry, split, fw 3.13  

Results: `primus_phase7/devices` table and `builders/.td_phase7_discover.json`.  
Discovery uses short-lived Python ArtPoll (same as `discover_device.py`) so it does not hold UDP 6454 against Phase 5 senders.

## Operator guides

| Doc | Use |
|-----|-----|
| [USING_PRIMUS_CONTROL.md](USING_PRIMUS_CONTROL.md) | Primary TD + CLI guide |
| [WORKFLOW.md](WORKFLOW.md) | Install Bridge, build loop, troubleshooting |
| [phase5_multidevice_test.md](phase5_multidevice_test.md) | Dual-device hardware checks |
| [phase6_test.md](phase6_test.md) | Cue deck |
| [phase7_test.md](phase7_test.md) | Discovery |

## Known hard lessons (do not regress)

1. Wrong NIC / L2 flap → mute or lossy ArtDmx; always `preflight` / correct `bind_ip`.
2. Config after device reset is one-shot unless refreshed — Phase 5 re-pushes ~every 5s; use `recover` after reconnect.
3. Sender cook must be forced (`frame_cook`); `cookalways` alone was unreliable.
4. SharedMedia demo can freeze → LEDs lit but not animated; force-cook demo/alt media.
5. Dual devices need distinct sources/geometry or they look identical.

## Intentionally deferred

- Phase 8 remote device configuration  
- OSC show-control soak test  
- Auto-import discovered `devices` rows into Phase 5 without a rebuild  
- Push to `origin` (local commits only unless asked)

## Resume checklist

1. TD open, `.toe` saved in repo root, PrimusBridge alive (`td_remote.py ping`).
2. `preflight --bridge` green on `192.168.8.199` + both IPs.
3. `recover` or `build 5` + `build 6` if looks are dark/stale.
4. Optional: `build 7` + `discover` to refresh the inventory table.
5. Next build work: Phase 8 (`phase8_test.md`) when ready.
