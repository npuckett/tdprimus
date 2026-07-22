# tdprimus

TouchDesigner integration for PrimusV3/V4 Art-Net receivers.

**Checkpoint (2026-07-21):** Phases **5–7** are working on the workshop LAN
(dual-device ArtDmx, cue deck, ArtPoll discovery). Phase **8+** not started.
See [`handoffs/STATUS.md`](handoffs/STATUS.md) for the full “where things are”
snapshot.

## Start here

1. [`handoffs/STATUS.md`](handoffs/STATUS.md) — current workshop state & resume checklist  
2. [`handoffs/USING_PRIMUS_CONTROL.md`](handoffs/USING_PRIMUS_CONTROL.md) — TD + CLI operator guide  
3. [`handoffs/WORKFLOW.md`](handoffs/WORKFLOW.md) — install Bridge, build/test loop, recovery  

Protocol reference: [`protocol/PrimusV3_ArtNet_Reference.md`](protocol/PrimusV3_ArtNet_Reference.md).

## Current architecture

```text
SharedMedia ──► Phase 5 per-device sampler/sender ──► ArtDmx ──► Primus
                      ▲
               Phase 6 cue deck (GO / Goto / Blackout)
Phase 7 ArtPoll ──► devices table (Phase-5-shaped inventory)
```

| Phase | What | Shell |
|-------|------|--------|
| 5 Multi-device | Dual receivers, reconnect, SharedMedia | `td_remote.py build 5` / `recover` |
| 6 Cues | Cue UI + OSC-ready map (UDP 7000) | `build 6` then `go` / `--goto` / `--blackout` |
| 7 Discovery | ArtPoll → `devices` | `build 7` then `discover` |

Workshop defaults: bind `192.168.8.199`, devices `.166` (A15) + `.164` (A13),
**split** mode, sampling brightness **0.1**.

`/project1/PrimusControl` starts phase builds; `/project1/PrimusBridge` accepts
`builders/td_remote.py` commands and reloads builder code in the open `.toe`.

## Repository layout

| Path | Purpose |
|---|---|
| [`builders/`](builders/) | Phase builders, remote CLI, packet helpers, offline checks |
| [`extensions/`](extensions/) | Sources synced into the installed Bridge/component workflow |
| [`handoffs/`](handoffs/) | Operator guide, STATUS, phase test handoffs |
| [`protocol/`](protocol/) | PrimusV3/V4 Art-Net reference |
| [`tox/`](tox/) | Instructions for manually exporting TD Palette components |

Builder scripts are the source of truth. `.toe` / `.tox` artifacts are not
required to rebuild the system.

## Offline checks

```bash
python3 builders/test_packets_offline.py
python3 builders/td_remote.py selftest
```

Canonical firmware and protocol context live in the sibling `PrimusV3/V4`
source tree, not V5.
