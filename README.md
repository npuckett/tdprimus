# tdprimus

TouchDesigner integration for PrimusV3/V4 Art-Net receivers. The current
milestone is one-device, media-agnostic sampling: select any TOP, sample it
into per-output RGB payloads, and package those bytes as Primus ArtDmx.

## Start here

[`handoffs/USING_PRIMUS_CONTROL.md`](handoffs/USING_PRIMUS_CONTROL.md) is the
primary TouchDesigner-facing guide. It covers the installed control/bridge
COMPs, rebuilding, network settings, Phase 4 media wiring and sampling, and
the tables and viewers used during a show.

Other useful references:

- [`handoffs/WORKFLOW.md`](handoffs/WORKFLOW.md): build/test loop and recovery.
- [`handoffs/phase4_test.md`](handoffs/phase4_test.md): Phase 4 hardware test.
- [`handoffs/multi_output_organization.md`](handoffs/multi_output_organization.md):
  practical design direction for the next multi-output phase.
- [`protocol/PrimusV3_ArtNet_Reference.md`](protocol/PrimusV3_ArtNet_Reference.md):
  packet and firmware protocol reference.

## Current architecture

```text
selected TOP → Phase 4 sampler → RGB byte payload → ArtDmx → Primus receiver
                         ↑
                  controls Table DAT
```

`/project1/PrimusControl` starts phase builds; `/project1/PrimusBridge` accepts
commands from `builders/td_remote.py` and reloads the builder code in the open
`.toe`. Phase 4 owns two output branches, `a0` and `a1`, and supports demo,
movie, and external TOP sources per branch.

## Repository layout

| Path | Purpose |
|---|---|
| [`builders/`](builders/) | Phase builders, remote CLI, packet helpers, offline checks |
| [`extensions/`](extensions/) | Sources synced into the installed Bridge/component workflow |
| [`handoffs/`](handoffs/) | Primary operating guide, test handoffs, and next-phase notes |
| [`protocol/`](protocol/) | PrimusV3/V4 Art-Net reference |
| [`tox/`](tox/) | Instructions for manually exporting TD Palette components |

The builder scripts are the source of truth. `.toe` and `.tox` files are
TouchDesigner-generated artifacts and are intentionally not required to rebuild
the system.

## Offline checks

```bash
python3 builders/test_packets_offline.py
python3 builders/td_remote.py selftest
```

Canonical firmware and protocol context live in the sibling `PrimusV3/V4`
source tree, not V5.
