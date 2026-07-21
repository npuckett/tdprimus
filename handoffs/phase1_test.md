# Handoff 1 — Baseline transport

Builder: [`builders/phase1_baseline.py`](../builders/phase1_baseline.py)

## Setup

1. Save a `.toe` inside the `tdprimus` repo root (so `project.folder` resolves) and leave TD running.
2. If you do not already have `PrimusControl` / `PrimusBridge`, install **once** in Textport:

```python
exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
install()
```

   Or print the same snippet from **Terminal** (not Textport): `python3 builders/td_remote.py install`

3. Build Phase 1 from **Terminal / Cursor** (preferred — no Textport):

```bash
python3 builders/td_remote.py build 1
# equivalent with explicit device defaults:
python3 builders/td_remote.py build 1 --ip 192.168.8.166 --universe 0 --a0-type small_grid
```

4. On failure, the CLI prints the traceback and writes `builders/.td_result.json`. Agents should read that file (`python3 builders/td_remote.py status`).

5. Receiver in **split** mode, single active output = `small_grid`.

Panel fallback (optional): confirm `PrimusControl/settings` then pulse **Build Phase 1**, or `op('/project1/PrimusControl').ext.Build(1)`.

## Checklist

- [ ] Network created under `/project1/primus_phase1`
- [ ] DMX Out Active, Art-Net, correct unicast IP + universe
- [ ] Red / green / blue thirds land on correct thirds of the strip (or grid)
- [ ] `controls` blackout=`1` clears the device to dark
- [ ] Blackout=`0` restores pattern
- [ ] (Grid only) serpentine matches physical wiring — note if flipped

## Reply template

```
Handoff 1: PASS / FAIL
output_type: …
thirds mapping: OK / swapped / offset by N px
serpentine: OK / needs flip / N/A
blackout: OK / FAIL
Notes: …
```
