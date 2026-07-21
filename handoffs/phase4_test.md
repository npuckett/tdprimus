# Handoff 4 — media sampling → Primus ArtDmx

Builder: [`builders/phase4_generative.py`](../builders/phase4_generative.py)

Phase 4 packages samples from any TOP into RGB ArtDmx for one Primus device.
It preserves split/combined sending, local `bind_ip`, and live virtual
resolution changes.

## Build

```bash
python3 builders/td_remote.py build 4 \
  --recv-mode split --a0-virtual 1 --a1-virtual 72 \
  --level 64 --bind-ip 192.168.8.199
```

## Connect media

Per output, set `controls.a0_src` / `controls.a1_src`:

- `0` — animated demo gradient
- `1` — Movie File In; place an optional file path in `a0_movie` / `a1_movie`
- `2` — wire **any TOP** to `a0_ext` / `a1_ext`

`a0_media` / `a1_media` are the selected fields actually sampled. Their
`*_viz_src` viewers show the source; `*_viz_send` viewers show the exact
1×N RGB payload strip after sampling and brightness.

## Sample geometry controls

All coordinates are normalized `0..1`, with origin at the TOP's lower/upper
orientation as TouchDesigner supplies its numpy image.

| Control | Purpose |
|---|---|
| `a*_sample_mode` | `fit`, `roi_fit`, `hline`, `vline`, `line`, or `point` |
| `a*_u`, `a*_v` | point / horizontal / vertical line anchor |
| `a*_u1`, `a*_v1` | second endpoint for `line` |
| `a*_roi_u`, `a*_roi_v`, `a*_roi_w`, `a*_roi_h` | normalized sample ROI |
| `a*_virtual` | RGB sample count sent to that output |
| `send_fps`, `level`, `blackout` | transport rate, peak brightness, and zero output |

Mode mapping: `point` repeats one location; `hline` travels left→right at
`v`; `vline` travels top→bottom at `u`; `line` runs `(u,v)` to `(u1,v1)`;
`fit` maps the sample strip across the full frame (or an intentionally
non-default ROI); `roi_fit` maps across the ROI.

## Checklist

- [ ] A1 defaults to demo + `hline`, and `a1_viz_send` is a 72-pixel moving strip.
- [ ] A0 defaults to demo + `point`, and its `virt=1` device output floods.
- [ ] Set `a1_src=2`, wire a TOP to `a1_ext`, and confirm `a1_viz_src` changes.
- [ ] Change `a1_sample_mode` / ROI / line values; confirm `a1_viz_send` and LEDs follow.
- [ ] Set `a1_src=1` and a valid `a1_movie` path; confirm movie sampling works.

## Reply template

```text
Handoff 4: PASS / FAIL
external TOP sampling: OK / FAIL
movie sampling: OK / FAIL
geometry / ROI mapping: OK / FAIL
Notes: …
```
