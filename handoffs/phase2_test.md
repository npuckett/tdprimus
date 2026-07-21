# Handoff 2 - Dual-output (A0 + A1) + V4 virtual counts

Builder: [`builders/phase2_combined.py`](../builders/phase2_combined.py)

## Status (2026-07-21)

**PASS — split mode** on `192.168.8.166`:

| Output | Pattern | Result |
|--------|---------|--------|
| A0 badge (`small_grid`, virt **32**) | solid red `@64` | OK — full badge, no green tail |
| A1 collar (`long_strip`, virt **72**) | RGB thirds `@64` | OK |

Transport: two ArtDmx packets — univ `base` = A0, univ `base+1` = A1.

**Blocked — combined mode:** `ArtReceiveConfig` / `ArtVirtualResolution` pushes from TD do not change device behavior. Combined single-universe send still paints A0-only at virt≈32 (red + 7 green, collar dark). Revisit with serial / ArtPollReply `U:C:` vs `U:S:` (Phase 6/7).

## Prerequisite

Device is currently in **split**. Prefer `--recv-mode split` until remote receive-mode stick is confirmed.

```bash
# Validated workshop command
python3 builders/td_remote.py build 2 \
  --recv-mode split \
  --a0-virtual 32 --a1-virtual 72 \
  --a0-pattern solid_red --a1-pattern thirds \
  --level 64

# Combined (fails until receive mode sticks)
python3 builders/td_remote.py build 2 --recv-mode combined \
  --a0-virtual 1 --a1-virtual 72 --level 64
```

## What it sends

| `recv_mode` | Universes | Payload |
|-------------|-----------|---------|
| `split` | `base`, `base+1` | A0 virt×3, then A1 virt×3 |
| `combined` | `base` only | `[A0][A1]` concatenated, total virt ≤170 |

| Control (`primus_phase2/controls`) | Role |
|------------------------------------|------|
| `recv_mode` | `split` / `combined` |
| `a0_virtual` / `a1_virtual` | transported pixel counts |
| `a0_pattern` / `a1_pattern` | per-output test pattern |
| `level` | peak 0–255 (default 64) |
| `blackout` / `active` | zeros / per-frame UDP |

Diagnostics: `builders/.td_phase2_diag.json`

## Checklist

- [x] Split: badge solid red, collar thirds, no bleed (virt 32 + 72)
- [ ] Combined: one univ, A0 then A1 by virtual counts
- [ ] Badge solid when `a0_virtual=1` (upsample) after virt push sticks
- [ ] Raising `a0_virtual` adds spatial detail on badge
- [ ] `blackout=1` clears both
- [ ] Illegal combined virt total >170 refused at build

## Reply template

```
Handoff 2: PASS / FAIL
mode: split / combined
A0: OK / FAIL
A1: OK / FAIL
bleed: none / observed
Notes: …
```
