# Using Primus from TouchDesigner

This is the operating guide for the current PrimusV3/V4 TouchDesigner setup.
The validated milestone is **Phase 4**: one receiver, two independently
sampled outputs (`a0` and `a1`), and split or combined ArtDmx packaging.

## Architecture

```text
PrimusControl / td_remote.py
            ↓ build request
       PrimusBridge
            ↓ reloads builders from disk
   /project1/primus_phase4
            ↓
 per-output source → sampler → ArtDmx → Primus receiver
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
