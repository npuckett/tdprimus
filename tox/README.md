# Primus TouchDesigner Components (`.tox`)

Phase 9 builds live Base COMPs inside a `.toe`. Export them here so shows can
drag them from a Palette — no builders rebuild required at show time.

## Components (v1)

| COMP | Filename | Role |
|------|----------|------|
| `PrimusManager` | `PrimusManager.tox` | Bind IP, send FPS, master brightness, Rescan, Create/Sync Outputs |
| `PrimusOutput` | `PrimusOutput.tox` | One per Primus receiver; TOP inputs → ArtDmx |
| `PrimusMediaBus` | `PrimusMediaBus.tox` | **Optional** demo generators (out1–out4) |

Cue deck is **not** packaged in v1 (use Phase 6).

## Media contract (PrimusOutput)

| COMP input | Internal null | Strip |
|-----------:|---------------|-------|
| 1 | `a0_media1` | A0 |
| 2 | `a0_media2` | A0 |
| 3 | `a1_media1` | A1 |
| 4 | `a1_media2` | A1 |

Media page: **A0 Source** / **A1 Source** = `demo | media1 | media2` (per strip).  
Unwired slots fall back to animated demos. Show content wires **directly** into
Output inputs — MediaBus is optional.

## Create / Sync Outputs

On PrimusManager → Discovery → **Create / Sync Outputs**:

- Creates missing Outputs from the `devices` table
- Updates Device params on existing Outputs with matching names
- **Never destroys** existing Outputs (wiring is preserved)
- Status reports `created=N updated=M skipped=K`

Remove unused Outputs manually.

## Export steps (inside TouchDesigner)

1. Build Phase 9:

```bash
python3 builders/td_remote.py build 9
```

2. Under `/project1/primus_phase9/`:
   - Select **PrimusManager** → Right-click → **Save Component…** → `tox/PrimusManager.tox`
   - Dive into **PrimusManager** → select inactive template **PrimusOutput** → **Save Component…** → `tox/PrimusOutput.tox`
   - Select **PrimusMediaBus** → **Save Component…** → `tox/PrimusMediaBus.tox`
   - Live workshop nodes `primus_a` / `primus_b` sit beside the Manager (siblings).

3. Palette: Preferences → Palette → add folder pointing at `tdprimus/tox` → Refresh Folder.

## Fresh-project smoke test

1. New empty `.toe` (not the workshop file).
2. Drop `PrimusManager.tox` → set **Bindip** to your wired NIC.
3. Drop one `PrimusOutput.tox` per Primus receiver → set IP, types, virtual, recv mode.
4. Leave **Managerpath** blank (auto-finds sibling Manager) or set it explicitly.
5. Wire any generative / movie TOP into Output inputs 1–4; set Media page sources.
6. Confirm LEDs track media; check `link` table / UI status `state=ok`.
7. Optional: drop `PrimusMediaBus.tox` and wire outs into Output inputs for demos.

## Brightness stack

`Output.Brightness × Manager.Brightness` (both 0–1).  
Manager **Blackout All** or Output **Blackout** forces dark.

## Note

`.tox` binaries are created only from TD (not by repo scripts).  
Keep large binaries out of git if needed; builders remain the source of truth.
Re-export after meaningful builder changes.
