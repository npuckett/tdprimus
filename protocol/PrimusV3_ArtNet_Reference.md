# PrimusV3 Art-Net Protocol Reference (V4)

Canonical source: `PrimusV3/V4` (`sender/artnet.py`, `Arduino/primusV3_receiver/`).
Firmware: **3.13.0**. Capability tag: **PV3CAP1**. Ignore V5.

All packets are UDP to port **6454**. ArtDmx is standard Art-Net; other Primus opcodes are vendor-defined (except ArtAddress `0x6000`, which reuses the real Art-Net opcode — unicast only).

---

## Common header (all packets)

| Offset | Size | Field | Endian |
|--------|------|-------|--------|
| 0–7 | 8 | `"Art-Net\0"` | — |
| 8–9 | 2 | Opcode | LE |
| 10–11 | 2 | Protocol version (= 14) | BE |

---

## Opcodes

| Name | Opcode | Notes |
|------|--------|-------|
| ArtPoll | `0x2000` | Discovery request |
| ArtPollReply | `0x2100` | Discovery response |
| ArtDmx | `0x5000` | Pixel RGB payload |
| ArtAddress | `0x6000` | Rename short name (unicast) |
| ArtOutputConfig | `0x8100` | Set output types per port |
| ArtReceiveConfig | `0x8110` | Split/combined + base universe |
| ArtVirtualResolution | `0x8130` | Virtual pixel count per port |
| ArtIPConfig | `0x8200` | DHCP / static IP (reboots) |
| ArtShowInfo | `0x8210` | Show metadata (optional for TD) |

---

## ArtDmx `0x5000`

| Offset | Size | Field | Endian |
|--------|------|-------|--------|
| 12 | 1 | Sequence (1…255 wrap; 0 also accepted) | — |
| 13 | 1 | Physical (= 0) | — |
| 14–15 | 2 | Universe (full 16-bit) | LE |
| 16–17 | 2 | Length | BE |
| 18+ | N | RGB payload (`ARTNET_DATA_OFFSET = 18`) | — |

- Payload is **RGB** (firmware converts to NeoPixel wire order).
- Primus sender pads odd length with `0x00` to even. TD DMX Out usually sends 512 — fine.
- Receiver ignores packets for non-matching universes; clamps length to UDP size.
- Max UDP accepted: 600 bytes (`MAX_UDP_PACKET`).

---

## ArtPoll `0x2000` (14 bytes)

| Offset | Field |
|--------|-------|
| 0–11 | Common header |
| 12–13 | TalkToMe / Priority = `0x00, 0x00` |

Broadcast and/or unicast to known IPs on 6454.

---

## ArtPollReply `0x2100` (239 bytes typical)

| Offset | Field |
|--------|-------|
| 10–13 | Device IP |
| 14–15 | Port 6454 LE |
| 16–17 | FW major/minor BE |
| 18–19 | NetSwitch / SubSwitch = 0 |
| 20–21 | OEM `0xFFFF` BE |
| 23 | Status1 `0xD0` |
| 24–25 | ESTA `0x0000` LE |
| 26–43 | Short name (≤17 + NUL) |
| 44–107 | Long name |
| 108–171 | Node Report (64-byte hard limit) — see PV3CAP1 |
| 172–173 | NumPorts BE |
| 174–177 | PortTypes (`0xC0` if active) |
| **190–193** | **SwOut = `universe & 0x0F` only** — do not trust for univ ≥ 16 |
| 200 | Style = StNode |
| 201–206 | MAC |
| 207–210 | BindIP |
| 212 | Status2 `0x08` |

---

## ArtAddress `0x6000` (107 bytes)

| Offset | Field |
|--------|-------|
| 12 | NetSwitch = `0x7F` (no change) |
| 13 | BindIndex = 0 |
| 14–31 | ShortName ≤17 ASCII |
| 96–103 | Command bytes = `0x7F` |
| 104 | `0x7F` |
| 106 | `0x00` |

Receiver requires `len >= 107`. Unicast only. Real Art-Net opcode — avoid broadcasting on mixed Art-Net LANs.

---

## ArtOutputConfig `0x8100` (13 + N)

| Offset | Field |
|--------|-------|
| 12 | `num_outputs` |
| 13+i | type enum uint8 per port |

Type IDs must match firmware `OutputType` / `LOOK_OUTPUT_TYPES` index (below).

---

## ArtReceiveConfig `0x8110` (15 bytes)

| Offset | Field |
|--------|-------|
| 12 | mode: `0` = split, `1` = combined |
| 13–14 | base universe LE |

---

## ArtVirtualResolution `0x8130` (13 + 2N)

| Offset | Field |
|--------|-------|
| 12 | `num_outputs` |
| 13+2i | virtual pixel count uint16 LE per port |

Clamped on device: `1 … pixelCount`. `0` restores type default.

---

## ArtIPConfig `0x8200` (25 bytes)

| Offset | Field |
|--------|-------|
| 12 | mode: `0` = DHCP, `1` = static |
| 13–16 | static IP |
| 17–20 | gateway |
| 21–24 | subnet |

Both modes **write NVS and reboot**.

---

## Output types

| Enum | Key | Name | Physical px | Layout | Default virtual |
|------|-----|------|-------------|--------|-----------------|
| 0 | `none` | Off | 0 | none | 0 |
| 1 | `short_strip` | Short Strip | 30 | linear | 30 |
| 2 | `long_strip` | Long Strip | 72 | linear | 72 |
| 3 | `grid` | Grid 8×8 | 64 | grid 8×8 | 64 |
| 4 | `small_grid` | Grid 8×4 | 32 | grid 8×4 | **1** |
| 5 | `extra_long_strip` | Extra Long Strip | 122 | linear | 122 |

Workshop defaults: A0 = `small_grid`, A1 = `long_strip`.
`MAX_LEDS_PER_PORT = 122`.

---

## Receive modes

**Firmware default: Combined** (`DEFAULT_RECEIVE_MODE = RECEIVE_MODE_COMBINED`).

| Mode | Universes | ArtDmx layout |
|------|-----------|---------------|
| Split (`0`) | `base`, `base+1`, … per active port | One packet per output |
| Combined (`1`) | All ports share `base` | One packet: A0 bytes then A1 bytes |

**Combined max:** 170 **virtual** pixels → 510 channels (fits one universe).

Upsample on device: physical index `p` maps to virtual `v = (p * virtualCount) / physical`.

---

## PV3CAP1 Node Report

Format (truncated at 64 chars; features first, port tuples last):

```
#0001 [NNNN] OK|PV3CAP1|F:<flags>|B:<board>|IP:<mode…>|U:<S|C>:<base>[|port:type:univ:virt…]
```

| Token | Meaning |
|-------|---------|
| `F:RIOHBMS` | R=rename I=IP O=output H=hello B=battery M=receive-mode S=show-info |
| `B:v1` / `v2` / `v31` | Board profile |
| `IP:D` or `IP:S:a.b.c.d:gw:mask` | DHCP / static |
| `U:S:N` / `U:C:N` | Split/Combined + base universe |
| `p:t:u:v` | Port, type id, universe, virtual pixels |

**Gotcha:** Long static IP + 2 ports often truncates port tuples. Merge with Long Name fallback when parsing.

---

## Serpentine / grids

- Firmware writes buffer → LED **linearly** after virtual expand.
- PrimusCentral sender always applies serpentine for grids (odd rows reversed).
- TD must reverse odd rows for grid types to match PrimusCentral looks.

---

## Blackout / stale frames

- Receiver **holds last frame** when ArtDmx stops (`CONNECTION_TIMEOUT` only clears `outputActive`).
- TD must send explicit all-zero ArtDmx for blackout / “off” cues.
- PrimusCentral keepalive sends zeros while connected so telemetry (UDP 6455) keeps working. Telemetry is optional for TD.

---

## Combined packing example

Default badge+collar, combined, base 0, virtual `[1, 72]`:

- Universe **0**
- Bytes `0–2`: badge (1 px → upsampled across 32 LEDs)
- Bytes `3–218`: collar 72×RGB
- Total 219 bytes (sender may pad to 220)

Split with same virtuals: univ 0 = 3 bytes (badge), univ 1 = 216 bytes (collar).

---

## Illegal combined pairings (physical stand-in)

Any pair whose **virtual** sum > 170 is rejected by firmware `validateReceiveMode`.
Example: two `extra_long_strip` at full virtual (122+122=244) — illegal.
Two full `grid` (64+64=128) — OK.
