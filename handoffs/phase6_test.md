# Handoff 6 — Cue Deck (UI + OSC-ready)

Builder: [`builders/phase6_cues.py`](../builders/phase6_cues.py)

Phase 6 is a **cue deck** on top of Phase 5. It does not send ArtDmx. GO / Goto /
Blackout change Phase 5 device looks. The same actions are exposed for future
show control over **OSC**.

Requires Phase 5 (`primus_a` + `primus_b`).

```bash
python3 builders/td_remote.py build 6
```

## How to use (UI)

1. Select `/project1/primus_phase6` in the network.
2. Open the **Cue** parameter page:
   - **GO** — advance to the next cue
   - **Cue #** + **Goto** — jump to that cue number
   - **Blackout** / **Restore** — hard all-device blackout (not a list step)
3. Watch **Status** on that page, or the `status` / `cue_state` tables.
4. Edit the `cues` table to change looks/targets.

## OSC map (network show control)

UDP port **7000** by default (`Cue.Oscport`). Same API as the panel:

| Address | Args | Action |
|---------|------|--------|
| `/primus/cue/go` | — | Next cue |
| `/primus/cue/goto` | `int` cue number | Jump to cue |
| `/primus/cue/blackout` | `0` or `1` | Restore / blackout all |

Example (from another machine on the LAN):

```bash
# requires oscsend / similar
oscsend 192.168.8.199 7000 /primus/cue/go
oscsend 192.168.8.199 7000 /primus/cue/goto i 3
oscsend 192.168.8.199 7000 /primus/cue/blackout i 1
```

Panel, OSC, and shell all call `cue_api` — add new show-control messages there.

## Shell

```bash
python3 builders/td_remote.py go
python3 builders/td_remote.py go --goto 3
python3 builders/td_remote.py go --blackout 1
python3 builders/td_remote.py go --blackout 0
```

## Default cues (4)

| # | Look |
|---|------|
| 1 | **Both same** → `demo` |
| 2 | **Both same** → `alt` + hue |
| 3 | **Different** → A `demo`, B `alt` (content `split`) |
| 4 | **Both blackout** → wraps to 1 |

## Checklist

- [ ] `build 6` OK with Phase 5 present
- [ ] Cue page **GO** advances looks on hardware
- [ ] Cue 3 shows different looks on A vs B at the same time
- [ ] Cue 4 / **Blackout** blacks both; **Restore** recovers
- [ ] OSC `/primus/cue/go` advances (when a sender is available)
- [ ] `td_remote.py go --goto 4` blacks both

## Reply template

```
Handoff 6: PASS / FAIL
UI: OK / FAIL
OSC smoke: OK / SKIP / FAIL
Notes: …
```
