# Handoff 9 — PrimusOutput + PrimusManager

Builder: [`builders/phase9_components.py`](../builders/phase9_components.py)  
Shared sender: [`builders/lib/primus_output_network.py`](../builders/lib/primus_output_network.py)

Packages the Phase 5 ArtDmx path into drop-in COMPs. **Cue deck is deferred** (use Phase 6).

## Architecture

```text
Show TOPs ──wire──► PrimusOutput
                      A0: a0_media1 / a0_media2  (COMP inputs 1–2)
                      A1: a1_media1 / a1_media2  (COMP inputs 3–4)
                         ──ArtDmx──► Primus
                         ▲
              PrimusManager (Bindip / Sendfps / Brightness / Rescan)
```

- One **PrimusOutput** per Primus receiver (A0 + A1 on that COMP).
- Each strip has its own media inputs — not a shared media1..media4 pool.
- Media page: **A0 Source** / **A1 Source** = `demo | media1 | media2` (scoped to that strip).
- Unwired slots fall back to animated demos.
- **PrimusManager** holds shared send settings and optional ArtPoll Rescan / Createoutputs.

## Gate 0 — Offline

```bash
python3 builders/test_packets_offline.py
python3 builders/test_sample_media_offline.py
python3 builders/test_primus_output_offline.py
python3 builders/td_remote.py selftest
```

Expect: all OK.

## Gate 1 — Builder installs

TD open, `.toe` in repo root, PrimusBridge installed.

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py build 9
python3 builders/td_remote.py status
```

Expect:

- `.td_result.json` `ok: true`
- `/project1/primus_phase9/PrimusManager`
- `/project1/primus_phase9/primus_a` and `primus_b` (live Outputs, siblings of Manager)
- `/project1/primus_phase9/PrimusManager/PrimusOutput` (template, inactive, for Create/Sync / .tox)
- `/project1/primus_phase9/PrimusMediaBus` (optional demo generators → each Output's four strip inputs)
- Each live Output has `ui` panel (A0/A1 source + send viewers, status DAT)

## Gate 2 — Fallback media (no wiring)

Workshop: Manager `Bindip=192.168.8.199`, `Brightness=0.1`; outputs A15 `.166` and A13 `.164`, split mode.

Hardware: both units show animated demo (not frozen).

Check:

- Each output `link` table: `state=ok`, climbing `sends`
- `builders/.td_phase9_diag.json` updates with `live: true`

## Gate 3 — TD media routing (core goal)

1. Create a Noise / Ramp / Movie File In TOP.
2. Wire into `primus_a` COMP input 1 (`a0_media1`) and/or input 3 (`a1_media1`).
3. On the Media page, set A0 Source / A1 Source to `media1` (or `media2`).
4. LEDs track the wired TOP; diag `media` shows labels like `a0_media1/a1_media1`.
5. Disconnect — falls back to demo without rebuilding.

## Gate 4 — Two independent Outputs

Distinct wired media on `primus_a` vs `primus_b`. Confirm no cross-talk.  
Manager Brightness scale dims both; `controls.blackout_all=1` (or Ext `BlackoutAll`) blacks both.

## Gate 5 — Manager Rescan

Pulse **Rescan** on PrimusManager (or Ext `Rescan()`).

Expect: `devices` table lists both Primus nodes; Status mentions count; optional `builders/.td_phase9_discover.json`.

Pulse **Create / Sync Outputs** twice:

- First pulse: creates any missing Outputs from `devices` (or updates Device pars on existing).
- Second pulse: `created=0 updated=N` — existing Outputs and their media wiring must remain.

## Gate 6 — Recover / bind

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py build 9
```

After NIC flap: correct Bindip → `link.state=ok`; wrong Bindip → bind_fail / mute (same lesson as Phase 5).

```bash
python3 builders/td_remote.py recover --phase 9
```

## Gate 7 — `.tox` export smoke

See [`tox/README.md`](../tox/README.md).

1. Save `PrimusManager` → `tox/PrimusManager.tox`
2. Save template `PrimusOutput` → `tox/PrimusOutput.tox` (confirm `ui` panel viewers present)
3. Save `PrimusMediaBus` → `tox/PrimusMediaBus.tox`
4. Fresh empty `.toe` (no builders rebuild): drop Manager + Outputs only → Bindip → wire TOP → `link.state=ok`
5. Optional: drop MediaBus and wire outs into Output inputs

Binaries stay gitignored; builders remain source of truth.

## Shell helpers

```bash
python3 builders/td_remote.py manager rescan
python3 builders/td_remote.py manager create_outputs
python3 builders/td_remote.py recover --phase 9
```

Diag files: `builders/.td_phase9_diag.json` (last writer) and
`builders/.td_phase9_diag_primus_a.json` / `_primus_b.json`.

## PASS / FAIL (2026-07-21 workshop)

| Gate | Result | Notes |
|------|--------|-------|
| 0 Offline | PASS | packets, sample_media, primus_output, selftest |
| 1 Build 9 | PASS | Manager + primus_a/b; `.td_result.json` ok |
| 2 Fallback demo | PASS | primus_b `media=demo/demo`, animated RGB, sends climb |
| 3 Wired media | PASS | primus_a `media=wired/demo` via test_media/ext_a0 |
| 4 Dual outputs | PASS | Independent looks; A wired / B demo |
| 5 Rescan | PASS | `manager rescan` → 2 Primus, 0 other |
| 6 Recover/bind | PASS | `recover --phase 9` after preflight |
| 7 tox smoke | MANUAL | Export per `tox/README.md` (operator step) |
