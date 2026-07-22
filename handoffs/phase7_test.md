# Handoff 7 — Discovery (ArtPoll)

Builder: [`builders/phase7_discovery.py`](../builders/phase7_discovery.py)

Phase 7 finds Primus receivers on the Art-Net LAN and fills a **Phase-5-shaped**
`devices` table (IP, types, virt, recv mode, bind_ip, etc.).

It uses the same Python ArtPoll path as
[`builders/discover_device.py`](../builders/discover_device.py) (bind wired NIC
`:6454`) so it does not fight Phase 5’s ArtDmx senders with a permanent UDP In.

```bash
python3 builders/td_remote.py build 7 --bind-ip 192.168.8.199
python3 builders/td_remote.py discover
# or offline (no TD COMP):
python3 builders/td_remote.py discover --offline
```

## UI

Select `/project1/primus_phase7` → **Discovery** page → **Rescan**.

| Node | Role |
|------|------|
| `devices` | Primus nodes (import-friendly for Phase 5) |
| `non_primus` | Other Art-Net replies |
| `discovery_log` | Raw short log of replies |
| `status` | `primus` / `other` counts, errors |
| `controls.bind_ip` | Local NIC (default `192.168.8.199`) |

## Checklist

- [x] `build 7` succeeds
- [x] Rescan / `td_remote.py discover` finds workshop A15 `.166` and A13 `.164`
- [x] `devices` rows include IP, recv_mode, a0/a1 types, firmware
- [ ] Universe comes from PV3CAP1 (not ArtPollReply SwOut) — confirm in TD `devices` table
- [ ] Phase 5 ArtDmx still runs after a rescan (no stuck bind on 6454)

## Reply template

```
Handoff 7: PASS / FAIL
Nodes found: …
Notes: …
```
