# Handoff 5 — multi-device sampled outputs

Builder: [`builders/phase5_multidevice.py`](../builders/phase5_multidevice.py)

Phase 5 creates one independent Phase-4-style sampler/sender COMP for every
row in `primus_phase5/devices`.

```bash
python3 builders/td_remote.py preflight --bridge
python3 builders/td_remote.py recover          # after a reconnect
# or: python3 builders/td_remote.py build 5
# replace profiles: python3 builders/td_remote.py build 5 --devices devices.json
```

Workshop defaults (both active, **split**, `brightness=0.1`, bind `192.168.8.199`):

| Row | IP | Node |
|-----|-----|------|
| `primus_a` | `192.168.8.166` | A15 |
| `primus_b` | `192.168.8.164` | A13 |

Build summary: `builders/.td_phase5_build.json` (`devices`, `active`).
Live send: `builders/.td_phase5_diag.json` + `primus_a/link`.

## Stability behavior

- `frame_cook` force-cooks sender + SharedMedia demos every frame.
- Socket recreate + config re-push after bind/send failure; config refresh ~5s.
- `sampling.brightness` (0..1) dims packed ArtDmx after sampling.

## Checklist

### Single-device stability

- [x] `preflight --bridge` green
- [x] `recover` / `build 5` succeeds with no config/bind failure
- [x] `primus_a/link.state=ok` and `sends` climbing
- [x] Device/NIC reconnect recovers without staying mute
- [x] Animated demo on hardware (A0 flood + A1 strip motion)
- [x] `sampling.brightness` dims packed output
- [ ] `sampling.blackout=1` / `controls.blackout_all=1` (operator spot-check)

### Multi-device table (one physical receiver)

- [x] Add third inactive row (`primus_c`) → rebuild → three COMPs, only `primus_a` active
- [x] Remove row → rebuild → COMP removed; `primus_a` keeps sending
- [x] Restore default two-row table (`primus_b` inactive scaffold)

### Second physical receiver

- [x] `primus_b` @ `192.168.8.164` (`A13`), `active=1`, rebuild; both active in `.td_phase5_build.json`
- [ ] Confirm independent content / no cross-talk on hardware (`primus_a`=demo, `primus_b`=alt + different sample line / hue)
- [ ] Combined ≤170 (keep workshop on **split** until trusted)

## Status

```
Handoff 5: PASS (single-device + dual active profiles)
primus_a 192.168.8.166 (A15) + primus_b 192.168.8.164 (A13)
Notes: confirm both LEDs animate independently; stay on split; blackout spot-check still open
```
