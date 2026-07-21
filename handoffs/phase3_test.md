# Handoff 3 - Live virtual resolution

Builder: [`builders/phase3_virtual.py`](../builders/phase3_virtual.py)

## Firmware gate (2026-07-21)

Live ArtPoll of `192.168.8.166` (`A15`):

| Field | Value |
|-------|-------|
| Firmware | **3.7** |
| Required for virtual res | **3.11+** |
| Repo V4 source | 3.13.0 |
| NodeReport | `PV3CAP1\|0:4:0\|1:2:1\|…` — **no** 4th virtual field |
| ArtVirtualResolution probe | does **not** stick |

**Update the receiver** before Phase 3 upsample tests. Until then, `a0_virtual=1` only lights the first LED (device still maps ArtDmx as physical-length).

```bash
python3 builders/discover_device.py --ip 192.168.8.166 --probe-virt 1,24
```

After updating to **3.13**: virtual pushes work. If TD/UI or the node stalls after a few edits, rebuild Phase 3 — older builds spam config opcodes / rewrite the devices table every frame (NVS + UI lock). Current build debounces virt pushes (~0.35s) and only sends ArtDmx ~30 fps.

## Semantics (V4, firmware 3.11+)


**Virtual resolution** = how many RGB values we send for an output. The receiver **upsamples** those across the physical LEDs.

| Virtual | What you send | What you see |
|--------:|---------------|--------------|
| 1 | 1 RGB | Entire output that one color |
| 24 on a 72px strip | 24 RGB | Blockier / chunky pattern |
| 72 | 72 RGB | Full spatial detail |

Short ArtDmx without updating device virtual is **not** the same (firmware zero-pads to the stored virt count). Phase 3 pushes `ArtVirtualResolution` whenever the table values change.

## Build

```bash
python3 builders/td_remote.py build 3 \
  --recv-mode split \
  --a0-virtual 32 --a1-virtual 72 \
  --a0-pattern thirds --a1-pattern thirds \
  --level 64
```

Edit **`/project1/primus_phase3/controls`** (param/value table), not only `devices`.

| Edit | Expected |
|------|----------|
| `a0_virtual` = `1`, `a0_pattern` = `solid_red` | Whole badge solid dim red |
| `a0_virtual` = `32`, pattern `thirds` | RGB thirds on badge |
| `a1_virtual` = `6`, pattern `thirds` | Very blocky thirds on collar |
| `a1_virtual` = `72` | Fine thirds on collar |
| `blackout` = `1` | Both dark |

Confirm live cook: `builders/.td_phase3_diag.json` should show `"live": true` and update `a0_virtual` / `a1_virtual` when you edit.

## Checklist

- [x] Firmware 3.13+ (ArtPoll) — virtual resolution supported
- [x] thirds / solid at live virt counts look correct
- [x] `a0_virtual=1` + solid_red -> full badge one color (upsample)
- [x] changing `a1_virtual` changes collar blockiness (not just a dark tail)
- [x] diag `live: true` tracks table edits (debounced virt push)
- [ ] `blackout=1` clears both (spot-check if not already)
- [ ] Combined virt total >170 refused when `recv_mode=combined`

## Reply template

```
Handoff 3: PASS / FAIL
upsample virt=1: OK / FAIL
blockier collar: OK / FAIL
live diag: OK / FAIL
Notes: …
```
