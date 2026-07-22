# Using Primus from TouchDesigner

This is the operating guide for the current PrimusV3/V4 TouchDesigner setup.
The current multi-output milestone is **Phase 5**: table-driven receivers,
each with two independently sampled outputs (`a0` and `a1`) and split or
combined ArtDmx packaging.

## Architecture

```text
PrimusControl / td_remote.py
            ↓ build request
       PrimusBridge
            ↓ reloads builders from disk
   /project1/primus_phase5
            ↓
 SharedMedia → per-device samplers → ArtDmx → Primus receivers
```

- **`/project1/PrimusControl`** is the small control COMP. Its `settings` Table
  DAT holds build-time defaults and its custom pulses call a phase builder.
- **`/project1/PrimusBridge`** is the file-command bridge. It polls
  `builders/.td_cmd.json`, reloads `builders.*` so disk edits are fresh, builds
  the requested phase, then writes `builders/.td_result.json`.
- **Phase COMPs** such as `/project1/primus_phase4` are the generated,
  show-facing networks. Rebuilding Phase 4 recreates its COMP; make durable
  source material outside it and wire it in again after a rebuild.

Phase 4 configures the receiver then sends RGB ArtDmx bytes directly from its
`artnet_cook` Script CHOP. It does not use a TD DMX Out CHOP.

Phase 5 keeps that direct sender per receiver profile. Its `devices` Table DAT
contains transport settings (`ip`, `bind_ip`, universe, mode, output types,
virtual counts, and `active`); each generated receiver COMP has a separate
`sampling` Table DAT for source geometry, brightness, rate, and blackout.

## Install and rebuild

Save the open `.toe` under the repository root so `project.folder` resolves to
this checkout. In TouchDesigner's Textport, run once per `.toe`:

```python
exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
install()
```

This creates `/project1/PrimusControl` and `/project1/PrimusBridge`. If an old
session reports stale `builders` imports, purge them before rerunning `install()`:

```python
for k in list(sys.modules):
    if k == "builders" or k.startswith("builders."):
        del sys.modules[k]
exec(open(f'{project.folder}/builders/install_control_panel.py', encoding="utf-8").read())
install()
```

Leave TD running, then build from Terminal/Cursor:

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py ping
python3 builders/td_remote.py build 4 \
  --ip 192.168.8.166 --universe 0 \
  --a0-type small_grid --a1-type long_strip \
  --a0-virtual 1 --a1-virtual 72 \
  --recv-mode split --level 64 --bind-ip 192.168.8.199
python3 builders/td_remote.py status
```

`td_remote.py install` only prints the Textport snippet; it does not install
from the shell. The panel is useful for local operation: edit
`PrimusControl/settings`, then pulse **Build Phase 4** or run
`op("/project1/PrimusControl").ext.Build(4)`. Prefer the CLI during development
because its result and traceback are written to `.td_result.json`.

## Network and receiver configuration

| Setting | Meaning |
|---|---|
| `device_ip` / CLI `--ip` | Receiver's Art-Net destination IP. `ip` is retained as a compatibility alias. |
| `bind_ip` / CLI `--bind-ip` | Local wired-NIC IP for the UDP socket, for example `192.168.8.199`. Leave empty to let macOS choose a route. |
| `universe` | Base Art-Net universe. |
| `recv_mode` | `split` sends A0 to `universe` and A1 to `universe + 1`; `combined` joins A0+A1 into the base universe. |
| `a0_type`, `a1_type` | Physical receiver output types: `none`, `short_strip` (30), `long_strip` (72), `grid` (64), `small_grid` (32), or `extra_long_strip` (122). |
| `a0_virtual`, `a1_virtual` | RGB sample counts sent to each physical output; each is clamped to its type's physical pixel count. |

In combined mode the two virtual counts must total no more than 170. Split mode
uses separate ArtDmx universes. The receiver's virtual-resolution feature
requires firmware **3.11+** for live use (the workshop receiver was tested on
3.13). If Art-Net leaves through the wrong adapter, use `bind_ip` or configure
the relevant TD/network interface to the wired NIC.

## Phase 4 media and sampling

Each output has the same media branch:

```text
a*_demo ─┐
a*_movie_in ─ switch (`a*_select`) ─ a*_media ─ sampler
a*_ext ──┘
```

Set these rows in `primus_phase4/controls`:

| Control | Meaning |
|---|---|
| `a*_src` | `0` demo gradient, `1` Movie File In, `2` external TOP. |
| `a*_movie` | File path used when source is `1`. |
| `a*_sample_mode` | `fit`, `roi_fit`, `hline`, `vline`, `line`, or `point`. |
| `a*_u`, `a*_v` | Normalized point/line anchor. |
| `a*_u1`, `a*_v1` | Normalized second endpoint for `line`. |
| `a*_roi_u`, `a*_roi_v`, `a*_roi_w`, `a*_roi_h` | Normalized sampling ROI. |
| `a*_virtual` | Number of RGB points sampled for this output. |
| `level`, `send_fps`, `blackout` | Peak level 0–255, send rate, and zero-output switch. |

All sampling coordinates are normalized `0..1` and are evaluated against the
selected TOP's numpy image orientation. Sampling is nearest-neighbour:

- `point` repeats the single location for every virtual pixel.
- `hline` travels left-to-right at `v`; `vline` travels top-to-bottom at `u`.
- `line` travels from `(u, v)` to `(u1, v1)`.
- `fit` and `roi_fit` currently produce a one-dimensional horizontal strip
  across the active ROI.

### Typical show workflows

**One-color / flood A0:** set `a0_virtual=1`, use `a0_sample_mode=point`, and
move `a0_u`/`a0_v`. The one sampled RGB value drives the configured A0 output.

**Map a movie across A1:** set `a1_src=1`, put an absolute movie path in
`a1_movie`, set `a1_virtual=72`, and use `a1_sample_mode=hline` or `line`.

**Use a live external TOP:** wire any TOP into `a0_ext` or `a1_ext`, set the
matching `a*_src=2`, then select a sample mode. The external TOP must be wired
again after a Phase 4 rebuild because that generated COMP is recreated.

**Sample a particular line or ROI:** set `hline` plus `a*_v`, `vline` plus
`a*_u`, or `line` plus both endpoints. For a cropped strip, set ROI values and
use `roi_fit`; `fit` also uses the active ROI in the current sampler.

## What to watch in the network

- `a0_media` / `a1_media`: the selected TOP used by the sampler.
- `a0_viz_src` / `a1_viz_src`: viewers for the selected source.
- `a0_viz_send` / `a1_viz_send`: nearest-filtered 1×N previews of the final
  sampled RGB bytes after `level`; these are the best preflight check.
- `devices`: one-row current device profile in Phase 4.
- `controls`: live source, geometry, virtual-resolution, rate, and blackout
  values.
- `artnet_cook`: sender, diagnostics, and cached payloads.

For a hardware-specific verification sequence, use
[`phase4_test.md`](phase4_test.md). For the build/test loop and error recovery,
use [`WORKFLOW.md`](WORKFLOW.md).

## Phase 5 multi-device media

Build it with:

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py build 5
python3 builders/td_remote.py build 6   # cue deck UI + OSC on port 7000
```

### Cue deck (Phase 6)

Select `/project1/primus_phase6` → **Cue** page: **GO**, **Cue #** + **Goto**,
**Blackout** / **Restore**. Same actions over OSC UDP `7000`:

- `/primus/cue/go`
- `/primus/cue/goto <n>`
- `/primus/cue/blackout <0|1>`

Shell: `python3 builders/td_remote.py go` / `--goto N` / `--blackout 1`.

### Discovery (Phase 7)

```bash
python3 builders/td_remote.py build 7
python3 builders/td_remote.py discover
# or without TD: python3 builders/td_remote.py discover --offline
```

Select `/project1/primus_phase7` → **Discovery** → **Rescan**. Results land in
the `devices` table (Phase-5-shaped rows) and `builders/.td_phase7_discover.json`.

`preflight` confirms the wired `bind_ip` is on this Mac and the receiver
answers ping. Phase 5 fails the build (sticky in `.td_result.json`) if
config/bind UDP cannot be sent, instead of succeeding with a mute wire.

After a Thunderbolt/device reconnect when LEDs stay dark:

```bash
python3 builders/td_remote.py recover
```

Each device COMP has a `link` table (`state`, `sends`, `reconnects`,
`last_error`) and a `frame_cook` Execute DAT that force-cooks the sender every
frame. Healthy live send shows `link.state=ok` and climbing
`builders/.td_phase5_diag.json` `sends`. The sender recreates its UDP socket
after bind/send failures and re-pushes output/receive/virtual config about
every 5s (`sampling.config_refresh_s`) so a post-reset receiver is
reconfigured without a manual rebuild.

Per-device packing dim: edit `primus_a/sampling` → `brightness` (**0..1**,
default `0.1`). It scales the packed ArtDmx bytes after sampling, so full-white
media can still be brought down safely. `0` is off; `1` is full. Legacy `level`
(0–255) is still honored if `brightness` is absent.

The generated `/project1/primus_phase5/SharedMedia` COMP holds the shared,
durable demo/movie/external TOP bus. Wire show TOPs to `bus_a0_ext` or
`bus_a1_ext`, set the respective `a*_source` field in the device row to `ext`,
then rebuild. `demo`, `alt`, `movie`, and `ext` are valid source keys. `demo` and `alt` are
phase-shifted gradients so two receivers can look distinct while sharing the bus.

The first default row is active for `192.168.8.166` / `192.168.8.199` in split
mode. The `primus_b` row is disabled safely until a second receiver IP is
assigned and `active=1`. For profile JSON supplied from the shell, use
`td_remote.py build 5 --devices devices.json`. See
[`phase5_multidevice_test.md`](phase5_multidevice_test.md) for verification.

## Packaged COMPs (Phase 9)

Phase 9 packages the Phase 5 ArtDmx path into drop-in COMPs (cue deck deferred).
System map: [`primus_system_map.md`](primus_system_map.md).

```text
Show TOPs ──wire──► PrimusOutput (in1–4 → A0/A1 media) ──ArtDmx──► Primus
                         ▲
              PrimusManager (Bindip / Sendfps / Brightness / Rescan / Sync)
```

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py build 9
python3 builders/td_remote.py manager rescan
python3 builders/td_remote.py manager create_outputs
python3 builders/td_remote.py recover --phase 9
```

- **PrimusManager** — shared bind IP, send FPS, brightness scale, Rescan, **Create / Sync Outputs** (add-missing; never destroys wiring).
- **PrimusOutput** — one per receiver. Inputs **1–2** → A0 media1/2, **3–4** → A1 media1/2. Unwired slots use demos. Compact `ui` panel shows sources + send strips.
- **Managerpath** — set explicitly, or leave blank to auto-find a sibling Manager.
- **PrimusMediaBus** — optional demo generators; export as third `.tox`.
- Live health: Output `link` / `ui/status` + `builders/.td_phase9_diag_<name>.json`.
- Export `.tox`: see [`tox/README.md`](../tox/README.md). Tests: [`phase9_test.md`](phase9_test.md).

Cues remain Phase 6 (`td_remote.py go`) until a later packaging pass.
