# Workshop status — checkpoint after Phase 9 v1

**Date:** 2026-07-21  
**Branch:** `main` (local)  
**Stopped at:** Phase 9 PrimusOutput + PrimusManager packaged and hardware-verified on macOS; Phase 8 remote config still deferred; cue packaging deferred.

## Where we are

| Phase | Status | Notes |
|-------|--------|-------|
| 0–4 | Done earlier | Protocol → generative sampling |
| **5 Multi-device** | **Working** | Dual ArtDmx, reconnect, distinct looks |
| **6 Cues** | **Working** | Cue deck UI + shell; OSC map ready, not show-tested |
| **7 Discovery** | **Working** | ArtPoll finds both workshop nodes |
| 8 Remote cfg | Not started | Deferred |
| **9 Components** | **Working (v1)** | PrimusManager + PrimusOutput; cues not packaged |

Live stack options:

```text
# Packaged (Phase 9)
test_media / show TOPs → PrimusOutput × N → ArtDmx
                              ↑
                         PrimusManager

# Legacy workshop (Phases 5–7)
SharedMedia → primus_a / primus_b ← primus_phase6
primus_phase7 · PrimusControl + PrimusBridge
```

## Workshop LAN

| Role | Value |
|------|--------|
| Mac bind IP | `192.168.8.199` (wired, often `en4`) |
| Device A (A15) | `192.168.8.166` — split, fw **3.13** |
| Device B (A13) | `192.168.8.164` — split, fw **3.13** |
| Default brightness | `0.1` on each Output `sampling` table |
| Manager brightness scale | `1.0` (multiply onto per-Output brightness) |
| Receive mode | **split** |

## Everyday commands

```bash
# Health
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py ping

# Packaged COMPs (preferred for new show wiring)
python3 builders/td_remote.py build 9
python3 builders/td_remote.py manager rescan
python3 builders/td_remote.py recover --phase 9

# Legacy Phase 5–7
python3 builders/td_remote.py recover          # rebuild Phase 5
python3 builders/td_remote.py build 5
python3 builders/td_remote.py build 6         # cue deck
python3 builders/td_remote.py build 7         # discovery COMP

# Cues (still Phase 6)
python3 builders/td_remote.py go
python3 builders/td_remote.py go --goto 3
python3 builders/td_remote.py go --blackout 1

# Discovery
python3 builders/td_remote.py discover --offline
python3 builders/td_remote.py manager rescan   # into PrimusManager/devices
```

## Verified Phase 9 (2026-07-21)

- `build 9` → Manager + `outputs/primus_a` + `primus_b`, ArtDmx live (`link.state=ok`, climbing sends)
- `primus_a` media `wired/demo` via generative test TOP; `primus_b` stays `demo/demo` (independent)
- `manager rescan` → 2 Primus / 0 other on workshop LAN
- `recover --phase 9` green after preflight
- Offline: packets / sample_media / primus_output / selftest OK
- Cue packaging deferred; Phase 8 deferred
- Manual `.tox` export remains operator step (`tox/README.md`)

## Operator guides

| Doc | Use |
|-----|-----|
| [USING_PRIMUS_CONTROL.md](USING_PRIMUS_CONTROL.md) | Primary TD + CLI guide |
| [WORKFLOW.md](WORKFLOW.md) | Install Bridge, build loop, troubleshooting |
| [phase5_multidevice_test.md](phase5_multidevice_test.md) | Dual-device hardware checks |
| [phase6_test.md](phase6_test.md) | Cue deck |
| [phase7_test.md](phase7_test.md) | Discovery |
| [phase9_test.md](phase9_test.md) | Packaged PrimusOutput / Manager gates |

## Known hard lessons (do not regress)

1. Wrong NIC / L2 flap → mute or lossy ArtDmx; always `preflight` / correct `bind_ip`.
2. Config after device reset is one-shot unless refreshed — senders re-push ~every 5s; use `recover` after reconnect.
3. Sender cook must be forced (`frame_cook`); `cookalways` alone was unreliable.
4. SharedMedia / demo can freeze → LEDs lit but not animated; force-cook demo media.
5. Dual devices need distinct sources/geometry or they look identical.
6. Phase 9 silences Phase 1–5 senders on build so only packaged Outputs own the wire.

## Intentionally deferred

- Phase 8 remote device configuration  
- Cue engine packaging into Phase 9  
- OSC show-control soak test  
- Committed `.tox` binaries (manual export only)  
- Full Windows hardware soak (preflight NIC/ping helpers are portable)  
- Push to `origin` (local commits only unless asked)

## Resume checklist

1. TD open, `.toe` saved in repo root, PrimusBridge alive (`td_remote.py ping`).
2. `preflight --bridge` green on `192.168.8.199` + device IP.
3. `build 9` or `recover --phase 9` for packaged Outputs; or `recover` / `build 5`+`6` for legacy stack.
4. Optional: `manager rescan` or `discover --offline`.
5. Next build work: Phase 8 remote config and/or cue packaging when ready.
