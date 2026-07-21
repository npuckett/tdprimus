# Handoff 6 — cue system over Phase 5

Builder: [`builders/phase6_cues.py`](../builders/phase6_cues.py)

Phase 6 does **not** send ArtDmx itself. It drives
`/project1/primus_phase5` device COMPs: source select (`demo`/`alt`/`movie`/`ext`),
`brightness`, `hue_shift`, and `blackout`. Untargeted devices keep their last look.

Requires Phase 5 already built (workshop: `primus_a` `.166` + `primus_b` `.164`).

```bash
python3 builders/td_remote.py build 6
python3 builders/td_remote.py go          # advance one cue
```

Or Textport: `op('/project1/primus_phase6/controls')['go',1]=1`

## Cue columns

| Column | Meaning |
|--------|---------|
| `cue` | Cue number label |
| `targets` | `*` / `group:NAME` / `primus_a` (comma-separated) |
| `a0_content` / `a1_content` | `demo` \| `alt` \| `movie` \| `ext` \| `black` |
| `brightness` | 0..1 packed dim |
| `hue_shift` | Channel rotate for distinct looks |
| `blackout` | `1` zeros matched devices |
| `fade` | Reserved (not yet a Cross TOP fade) |
| `notes` | Free text |

Default list: (1) all demo → (2) all alt+hue → (3) only A → (4) only B → (5) blackout.

## Checklist

- [ ] `build 6` succeeds only when Phase 5 exists
- [ ] First cue applied at build; both devices show cue-1 look
- [ ] `td_remote.py go` advances; `cue_state.cue_number` / `last_applied` update
- [ ] Cue 3 changes only `primus_a`; `primus_b` holds prior look
- [ ] Cue 4 changes only `primus_b`
- [ ] Cue 5 blacks both
- [ ] GO wraps from last cue back to cue 1

## Reply template

```
Handoff 6: PASS / FAIL
GO targeting: OK / FAIL
Notes: …
```
