# TouchDesigner Primus — Working Workflow

Verified workflow for building and testing PrimusV3 networks from this repo without pasting phase scripts into Textport.

## Prerequisites

- TouchDesigner open with a `.toe` **saved in this repo root** (`project.folder` → `tdprimus`)
- Primus receiver on the Art-Net LAN (defaults below)
- Shell / Cursor working directory = repo root

| Setting | Default |
|---------|---------|
| Device IP | `192.168.8.166` |
| Universe | `0` |
| Phase 1 mode | **split**, single output |
| A0 type | `small_grid` |
| A1 type (later phases) | `long_strip` |

Thunderbolt Ethernet: TD uses the OS stack. Only set the DMX Out / UDP network interface if Art-Net leaves on the wrong adapter.

---

## Where commands run

| Place | Use for |
|-------|---------|
| **Textport** (inside TD) | Only the one-time `install()` Python below |
| **Terminal / Cursor** (macOS shell) | `python3 builders/td_remote.py …` — ping, build, status |

`python3 builders/td_remote.py ping` is a **shell** command. Pasting it into Textport causes `SyntaxError`.

---

## One-time install (Textport only)

Do this once per `.toe` (or after a TD upgrade if Bridge is missing / dead):

```python
exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
install()
```

If you previously hit stale-import errors (`create_child` missing), purge first:

```python
for k in list(sys.modules):
    if k == 'builders' or k.startswith('builders.'):
        del sys.modules[k]
exec(open(f'{project.folder}/builders/install_control_panel.py', encoding='utf-8').read())
install()
```

Expected: `/project1/PrimusControl` and `/project1/PrimusBridge` exist. Leave TD running. Save the `.toe`.

Print the same snippet from **Terminal**:

```bash
python3 builders/td_remote.py install
```

---

## Everyday builds (Terminal / Cursor — not Textport)

Leave TD running. From the repo root in **Terminal**:

```bash
# Bridge alive?
python3 builders/td_remote.py ping

# Wired NIC + device reachability (run before Phase 4/5 hardware work)
python3 builders/td_remote.py preflight --bridge

# After a NIC/device flap (device reconnected but dark): preflight + rebuild
python3 builders/td_remote.py recover

# Phase N (1-8)
python3 builders/td_remote.py build 1

# Explicit device args (Phase 1-3)
python3 builders/td_remote.py build 1 --ip 192.168.8.166 --universe 0 --a0-type small_grid

# Last result
python3 builders/td_remote.py status
```

### What happens

```
td_remote.py          PrimusBridge (in TD)           disk
    |                        |                         |
    |-- write .td_cmd.json ->|                         |
    |                        |-- reload builders.*     |
    |                        |-- run phase build()     |
    |                        |-- write .td_result.json |
    |<-- poll / print -------|                         |
```

| File | Role |
|------|------|
| [`builders/.td_cmd.json`](../builders/.td_cmd.json) | Command from CLI → TD (cleared after handling) |
| [`builders/.td_result.json`](../builders/.td_result.json) | Result for CLI / agent: `{ok, phase, error, traceback, message, ts}` |

Builders always **purge and re-import** `builders.*` before running so Textport never keeps a stale module.

### Optional UI

`/project1/PrimusControl`:

- Edit `settings` table (ip, universe, a0_type, …)
- Pulse **Build Phase N**, or `op('/project1/PrimusControl').ext.Build(1)`

Prefer the CLI when iterating from Cursor so errors land in `.td_result.json`.

---

## Phase loop (handoff model)

1. **Build** the phase via `td_remote.py build N`
2. **You** run hardware checks in [`handoffs/phaseN_*.md`](./)
3. **Reply** with the handoff template (PASS/FAIL + notes)
4. We fix if needed, then advance

| Phase | Command | Handoff |
|-------|---------|---------|
| 0 Protocol | _(docs only)_ | [phase0_review.md](phase0_review.md) |
| 1 Baseline | `td_remote.py build 1` | [phase1_test.md](phase1_test.md) |
| 2 Combined | `td_remote.py build 2` | [phase2_test.md](phase2_test.md) |
| 3 Virtual | `td_remote.py build 3` | [phase3_test.md](phase3_test.md) |
| 4 Generative | `td_remote.py build 4` | [phase4_test.md](phase4_test.md) |
| 5 Multi-device | `td_remote.py build 5` | [phase5_multidevice_test.md](phase5_multidevice_test.md) |
| 6 Cues | `td_remote.py build 6` | [phase6_test.md](phase6_test.md) |
| 7 Discovery | `td_remote.py build 7` | [phase7_test.md](phase7_test.md) |
| 8 Remote cfg | `td_remote.py build 8` | [phase8_test.md](phase8_test.md) |
| 9 Components | Run `phase9_components.py` in TD Textport | [phase9_test.md](phase9_test.md) |

Phase 1 stays **split** (single output). Phase 2 dual-output is validated in **split**. Phase 3 live virtual requires firmware **3.11+** (workshop device on **3.13**). Phase 4 samples any selected TOP (demo, Movie File In, or a wired external TOP) by point/line/ROI/fit geometry. Phase 5 applies that sampler/sender path independently to every active `devices` profile row and feeds it from `SharedMedia`; use `td_remote.py build 5` / `recover`, then edit profile rows or pass `--devices devices.json`. **Handoff 5** workshop profile: `primus_a` `192.168.8.166` + `primus_b` `192.168.8.164` (both active, split). Confirm independent LED content before Phase 6 cues. `td_remote.py` currently accepts Phase 1–8; Phase 9 is invoked directly in TD as its builder header shows.

---

## Agent / Cursor error loop

After a failed build:

```bash
python3 builders/td_remote.py status
# or
cat builders/.td_result.json
```

Fix code on disk → `build N` again. No Textport paste required unless PrimusBridge was deleted.

---

## Offline sanity (no TD)

```bash
python3 builders/test_packets_offline.py
python3 builders/test_sample_media_offline.py
python3 builders/td_remote.py selftest
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `td_remote` times out | TD not running, Bridge missing, or `.toe` not in repo root — re-run `install()` |
| `create_child` ImportError | Stale `sys.modules` — purge + `install()` snippet above |
| `preflight` FAIL bind_ip | `en4` (or wired NIC) lost `192.168.8.199` — reattach Thunderbolt Ethernet / renew DHCP |
| `preflight` FAIL ping | Device off, wrong LAN, or L2 broken — do not build until ICMP (or ArtPoll) works |
| Phase 5 `config/bind failed` | Build still creates samplers but fails loud in `.td_result.json` — fix `bind_ip` / NIC, then `recover` |
| Device reconnected but dark | Config was one-shot; run `recover`. Live sender now re-pushes config every ~5s and recreates UDP on send fail |
| Stops updating / ~10s blackouts | Check `primus_a/link.state` and `.td_phase5_diag.json` `sends` climbing; ensure `artnet_cook` cookalways |
| `link.state=bind_fail` / `send_fail` | NIC flap or stale socket — sender retries with backoff; if stuck, `preflight` then `recover` |
| No light on device | Run `preflight`, check `link` table, IP/universe, `bind_ip`, split vs combined, only Phase 5 sending |
| Last frame stuck lit | Firmware holds last ArtDmx — set blackout / send zeros |
| Wrong NIC | Bind UDP with `--bind-ip 192.168.8.199` (Phase 4) or the row's `bind_ip` (Phase 5) |
