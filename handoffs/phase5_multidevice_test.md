# Handoff 5 - Multi-device

Builder: [`builders/phase5_multidevice.py`](../builders/phase5_multidevice.py)

Deferred until Phase 4 generative is validated on one device.

```bash
python3 builders/td_remote.py build 5
```

Edit `primus_phase5/devices` IPs for two receivers, then rebuild.

## Checklist

- [ ] Two devices show independent content (no cross-talk)
- [ ] Different universes / IPs respected
- [ ] Add a third row → rebuild → new Base COMP appears
- [ ] Remove a row → rebuild → chain removed
- [ ] Blackout all / per-device blackout

## Reply template

```
Handoff 5: PASS / FAIL
Notes: …
```
