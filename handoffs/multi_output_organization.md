# Multi-output organization direction

This note describes the Phase 5 multi-output design after the Phase 4 sampling
checkpoint. It is not an implementation plan for a new protocol.

## What exists now

Phase 4 is the content-to-packet reference: one generated COMP has two
independent media selectors (`a0`/`a1`), their own sampling controls, and one
direct UDP ArtDmx sender with `bind_ip`, universe, types, virtual counts, and
receive mode.

Phase 5 implements that path for every active row in `primus_phase5/devices`:

```text
name, active, ip, bind_ip, universe, recv_mode,
a0_type, a0_count, a0_virtual, a1_type, a1_count, a1_virtual,
a0_source, a1_source, group
```

Each row gets a Phase-4-style sampler/sender COMP. Durable demo/movie/external
TOPs live in `SharedMedia` outside the generated receiver COMPs. Rebuilds
replace receiver COMPs while preserving the media bus. Workshop default is
**split** mode; stay on split until remote receive-mode config is trusted.

Build and gate the wire with:

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py build 5
```

## Structure

```text
SharedMedia COMP                   devices Table DAT
  movie / camera / NDI TOPs          one row per receiver
       │                                      │
       └──── source references ───────┐       │
                                      ▼       ▼
                         PrimusOutput COMP (one per row)
                         source select → A0/A1 samplers
                         → virtual payloads → ArtDmx sender
```

1. Keep **device settings per row**, not in content controls (`bind_ip`,
   `a0_source` / `a1_source`, types, virtual counts, `active`).
2. One **output COMP per receiver row** with Phase 4 sampling, payload preview,
   receive config, and direct UDP ArtDmx.
3. Put stable movie/camera/NDI/external TOPs in **SharedMedia** outside
   generated device COMPs so show wiring survives rebuilds.
4. Keep **content controls per output** in each COMP's `sampling` table
   (geometry, level, rate, blackout). A wider cue-friendly content table can
   come later.
5. Keep **transport constraints with the profile**: validate virtual counts
   against output type and combined total (≤170). In split mode, A1 uses base
   universe + 1.
6. Operator panel pages (`Device Profiles`, `Media Bus`, `Output Sampling`)
   remain a later packaging step once the builder network is stable.
7. Package as `.tox` only after the builder network is stable:
   `PrimusManager.tox`, `PrimusOutput.tox`, optional `PrimusMediaBus.tox`.
   Keep builders/extensions as source; do not require `.tox` binaries in git.

## Tradeoffs

- **Sampler per receiver/output** scales cleanly and lets every output have
  independent geometry, virtual resolution, level, and media. It costs more
  TOP cooks and duplicate sampling work.
- **Shared media bus** prevents duplicate decoders and keeps media wiring
  durable, but requires a clear source-key convention and explicit fallback
  when a referenced TOP is absent.
- **One wide table** is easy for operators and CSV import; a separate content
  table is less repetitive and better for per-output animation/cues.
- **Direct UDP sender per device** matches Phase 4 and allows per-device
  `bind_ip`; bind/config UDP failures now fail the Phase 5 build so they land
  in `.td_result.json` instead of a silent mute wire.

## Suggested next boundary

Single-device stability and inactive-row table add/remove are validated
(Handoff 5). Next hardware step: assign `primus_b` a real second receiver IP,
set `active=1`, rebuild, confirm independent content with no cross-talk. Cue
work stays Phase 6 until that second-receiver check passes.
