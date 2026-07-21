# Multi-output organization direction

This note describes the next practical step after the Phase 4 sampling
checkpoint. It is not an implementation plan for a new protocol.

## What exists now

Phase 4 is the correct content-to-packet reference: one generated COMP has two
independent media selectors (`a0`/`a1`), their own sampling controls, and one
sender that applies a single receiver profile (`device_ip`, `bind_ip`,
`universe`, types, virtual counts, and receive mode).

The existing Phase 5 `devices` Table DAT already has the useful receiver-profile
columns:

```text
name, ip, universe, recv_mode,
a0_type, a0_count, a0_virtual,
a1_type, a1_count, a1_virtual, group
```

However, Phase 5 currently creates Phase-3-style pattern/DMX Out chains. It
does not reuse the Phase 4 media sampler, its `a*_src` branches, or the direct
ArtDmx configuration/send path. Treat it as a device-table prototype, not as
the media-sampling multi-output design.

## Recommended structure

```text
SharedMedia COMP                   DeviceProfiles Table DAT
  movie / camera / NDI TOPs          one row per receiver
       │                                      │
       └──── source references ───────┐       │
                                      ▼       ▼
                         PrimusOutput COMP (one per row)
                         source select → A0/A1 samplers
                         → virtual payloads → ArtDmx sender
```

1. Keep **device settings per row**, not in content controls. Extend the
   existing `devices` schema with `bind_ip` (or use a global default), plus
   `a0_source`, `a1_source`, and named media-source keys if those are intended
   to persist with the device.
2. Make one reusable **PrimusOutput COMP** per receiver row. Its internal
   sampler should be the Phase 4 implementation: separate A0/A1 source
   selection, geometry, virtual count, payload preview, receive config, and
   direct UDP ArtDmx sender.
3. Put stable movie/camera/NDI/external TOPs in a **SharedMedia COMP** outside
   generated device COMPs. Device outputs should reference named bus TOPs,
   avoiding duplicated Movie File In decoders and preserving show wiring when
   device chains rebuild.
4. Keep **content controls per output**. Either add content columns to
   `devices` (simple and cue-friendly) or use a second `output_content` table
   keyed by `device_name` and port (`a0`/`a1`) (cleaner when many parameters
   are animated). Store source key, sample mode, endpoints, ROI, level, and
   enabled/blackout state there.
5. Keep **transport constraints with the profile**: validate each virtual count
   against its output type and validate the combined total (≤170) before
   sending. In split mode, A1 uses base universe + 1; make that visible in the
   per-device UI rather than asking operators to derive it.
6. Expose a single manager-facing panel: `Device Profiles`, `Media Bus`, and
   `Output Sampling` pages. Select a device row to edit its profile; show the
   selected output's `*_viz_src` and `*_viz_send` beside its geometry controls.
7. Package the reusable pieces as `.tox` only after the builder network is
   stable: `PrimusManager.tox` owns tables/replication, `PrimusOutput.tox`
   owns one receiver and its samplers, and an optional `PrimusMediaBus.tox`
   owns shared inputs. Keep builders/extensions as source and do not require
   `.tox` binaries in git.

## Tradeoffs

- **Sampler per receiver/output** scales cleanly and lets every output have
  independent geometry, virtual resolution, level, and media. It costs more
  TOP cooks and duplicate sampling work.
- **Shared media bus** prevents duplicate decoders and keeps media wiring
  durable, but requires a clear source-key convention and explicit fallback
  behavior when a referenced TOP is absent.
- **One wide table** is easy for operators and CSV import; a separate content
  table is less repetitive and better for per-output animation/cues. Start
  with profile rows plus a small content table once more than a few receivers
  need different mappings.
- **Direct UDP sender per device** matches Phase 4 and allows per-device
  `bind_ip`; a centralized sender reduces socket count but makes device-level
  diagnostics, rate limiting, and failures less isolated.

## Suggested next implementation boundary

First refactor the Phase 4 sampler into a reusable output component without
changing its one-device behavior. Then replace Phase 5's pattern branches with
one instance per device-table row and feed them from the shared media bus.
That preserves the validated Phase 4 packet path while making multiple
receivers simultaneous and independently configurable.
