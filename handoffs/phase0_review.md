# Handoff 0 — Protocol reference review

No TouchDesigner run required. Review [`protocol/PrimusV3_ArtNet_Reference.md`](../protocol/PrimusV3_ArtNet_Reference.md).

## Checklist

- [ ] Output types and physical counts match your rig
- [ ] Workshop defaults (A0=`small_grid`, A1=`long_strip`) match what you will test with — or note your A0/A1 types below
- [ ] OK to start Phase 1 in **split + single output**, then switch the test device to **combined** for Phase 2 (firmware flash flag or later remote config)
- [ ] Confirmed `small_grid` default virtual=1 is expected on your badges
- [ ] Confirmed firmware holds last frame (explicit blackout required) — accepted

## Your notes

| Item | Value |
|------|-------|
| Test device A0 type | |
| Test device A1 type | |
| Preferred Phase 1 universe | |
| Device IP (if known) | |
| Split OK for Phase 1? (Y/N) | |

## Reply template

```
Handoff 0: PASS / FAIL
A0/A1 types: …
Phase 1 split OK: Y/N
Notes: …
```
