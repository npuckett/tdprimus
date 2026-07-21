# TouchDesigner ↔ PrimusV3 Integration — Project Plan

**Source system:** `socialbodylab/PrimusV3`, V4 tree (canonical, `V4/sender/artnet.py` + `V4/Arduino/primusV3_receiver/`)
**Goal:** Drive PrimusV3 receiver nodes directly from TouchDesigner — content, cueing, and device management — using built-in TD nodes wherever possible, with custom Python reserved for the narrow set of things TD has no built-in operator for.

---

## 1. Guiding principle

Everything here is plain UDP to port 6454. TD's built-in **DMX Out CHOP** handles standard ArtDmx. TD's built-in **UDP Out DAT / UDP In DAT** can send and receive *any* raw bytes, including PrimusV3's custom opcodes — so almost none of this actually requires a Script/Execute DAT with Python `socket`. Python is reserved for:

- Constructing custom packet byte layouts (a Python DAT callback triggered by a UDP Out DAT, not a raw socket)
- Parsing incoming discovery/telemetry packets (a Python DAT callback on a UDP In DAT)
- Any logic too stateful for expressions/CHOPs (cue sequencing, table management)

This is the minimum unavoidable Python footprint — not a rejection of built-in tools, but the actual boundary of what those tools can do.

---

## 2. Build methodology — script-generated networks, not manual placement

Every network in this plan is delivered as a **TD Python builder script**, run once in TD's Textport (or via a DAT Execute), not built by hand node-by-node. This uses TD's real, documented scripting API — `op.create()`, `.par.<name>` for parameters, `.inputConnectors[i].connect()` for wiring, `.nodeX`/`.nodeY` for layout — which produces actual live, editable TD operators, not a mockup.

Why this is the delivery method for this project specifically:

- **Precision:** no risk of a resize dimension, universe number, or wire landing on the wrong input from a manual misclick.
- **Repeatability:** the same builder function can loop over the device table to instantiate one identical chain per device (directly relevant to Phase 4 below), rather than manually duplicating a network N times.
- **Inspectable:** the script is readable before it's run — you see exactly what will be created, then execute it, rather than trusting a black-box process.

Each phase below produces one such builder script as its deliverable. You run the script; you don't place nodes by hand at any point in this project.

---

## 3. Protocol reference (confirmed from source)

| Function | Opcode | Size | Notes |
|---|---|---|---|
| ArtDmx (pixel data) | `0x5000` | variable | standard Art-Net; DMX Out CHOP native |
| ArtPoll / ArtPollReply | `0x2000` / `0x2100` | standard | discovery; short_name @26–44, long_name @44–108, Node Report @108–172 |
| ArtAddress (rename) | `0x6000` | 107B | reuses real Art-Net opcode; unicast only |
| ArtOutputConfig | `0x8100` | 13+N | sets output type per port |
| ArtReceiveConfig | `0x8110` | 15B | split vs. combined universe mode, base universe |
| ArtVirtualResolution | `0x8130` | 13+2N | sets transported (virtual) pixel count per output |
| ArtIPConfig | `0x8200` | 25B | DHCP vs static, gateway, subnet |

Node Report capability tag: `PV3CAP1|F:<features>|B:<profile>|IP:<mode>|U:<S:0 or C:N>|<port>:<type>:<universe>:<virtualCount>...`

Full byte offsets are in the working notes from this conversation — pull these into a shared reference doc (Section 7) before implementation so packet-builder code has one source of truth.

---

## 4. Architecture

```
Device Table (Table DAT)          ← self-populated via discovery, editable
   name, ip, universe, recv_mode, a0_type/count/virtual, a1_type/count/virtual, group

Content Layer (TOPs)              ← per-output generative/media content
   resized to CURRENT virtual pixel count, not physical count

Routing/Cue Layer (Switch/Cross TOPs + Table DAT)
   cue table drives which content feeds which device/output, crossfade timing, group targeting

Transport Layer (Merge CHOP → DMX Out CHOP, one per device, combined-universe layout)

Management Layer (UDP Out/In DAT + Python callbacks)
   discovery, rename, output-config, receive-mode, virtual-resolution, IP-config
```

---

## 5. Phased plan

### Phase 1 — Baseline transport (built-in only)
- [ ] One test device, split-universe mode, single output type.
- [ ] TOP → Resize → TOP to CHOP → Reorder/Rename → DMX Out CHOP (Art-Net) → confirm correct color/channel mapping against a known pattern (e.g. red/green/blue thirds of the strip).
- [ ] Confirm serpentine row handling for grid types if applicable.
- **Deliverable:** a Python builder script that generates the full chain (built-in ops only) and confirms correct color/channel mapping when run.

### Phase 2 — Multi-output, combined-universe devices (built-in only)
- [ ] Reconfigure test device to combined receive mode (this can be done once via the firmware upload flag `--receivemode combined --universe N` for the test build, so Phase 2 doesn't yet depend on Phase 5's remote config).
- [ ] Two content branches (A0, A1) → Merge CHOP (A0 channels, then A1 channels, in order) → single DMX Out CHOP.
- [ ] Verify total channel count per device stays under 512; flag any output-type pairing that would overflow (e.g. two Extra Long Strip outputs = 732ch) as a design constraint, not a runtime branch.
- **Deliverable:** builder script extended to generate both output branches and the merge/transport stage for one device, one universe, confirmed against Eos-side expectations.

### Phase 3 — Virtual resolution awareness (built-in only)
- [ ] Add `virtual_pixels` column to the device table (manually populated for now).
- [ ] Make the Resize TOP's target dimension a live expression referencing the table row's virtual pixel count for that output, rather than a fixed size per output type.
- [ ] Test: confirm sending fewer values than physical count produces the expected block/solid-color behavior on real hardware, and that the `small_grid` default (virtual = 1) is either accounted for or explicitly overridden in the table.
- **Deliverable:** builder script updated so generated Resize TOPs reference table-driven expressions for virtual pixel count, verified against firmware behavior.

### Phase 4 — Multi-device scaling (built-in only)
- [ ] Extend device table to N rows (hand-entered for now).
- [ ] Templated/cloned network (Base COMP or Container per device) instancing the Phase 1–3 pipeline per row, parametrized from the table — this is the point where a **Replicator DAT** (built-in) becomes worth using to auto-build one device chain per table row, still no custom Python beyond replicator expressions.
- **Deliverable:** builder script loops over the device table and generates one full chain per row — adding/removing a table row and re-running the script adds/removes a device chain, with no manual network editing.

### Phase 5 — Cue system (built-in, some Python for sequencing logic)
- [ ] Cue Table DAT: cue number, target device(s)/group(s), content assignment per output, fade time.
- [ ] Switch/Select TOP per device-output choosing active content source; Cross TOP or ramp-driven Composite for crossfades.
- [ ] GO logic: a DAT Execute (small, targeted Python — this is sequencing logic, not protocol code) watches for cue advance and updates Switch indices / triggers ramp CHOPs; untargeted devices hold last state.
- **Deliverable:** builder script generates the Switch/Cross TOPs and cue-table wiring; a runnable cue list driving group/per-device targeting and crossfades, entirely TD-native content and transport underneath.

### Phase 6 — Discovery (requires Python — no built-in equivalent)
- [ ] UDP In DAT bound to 6454; Python callback parses ArtPollReply per the byte offsets in Section 2, extracting name/IP/profile/receive-mode/per-output type-universe-virtualCount tuples from the Node Report capability tag.
- [ ] Populate/refresh the device table automatically from parsed replies rather than hand-entry.
- [ ] ArtPoll send on a timer or manual "rescan" button (UDP Out DAT, small fixed packet — negligible Python).
- **Deliverable:** builder script creates the UDP In DAT and its parser callback; device table self-populates and refreshes from the network, feeding directly into Phases 1–5's table-driven pipeline.

### Phase 7 — Remote device management (requires Python — no built-in equivalent)
- [ ] Packet builders for ArtAddress (rename), ArtOutputConfig, ArtReceiveConfig, ArtVirtualResolution, ArtIPConfig, mirroring the byte layouts already confirmed in `artnet.py`.
- [ ] UI (simple Container/Table-driven panel) to edit a device row and push the corresponding config packet via UDP Out DAT.
- [ ] Re-poll after a config change to confirm the device applied it (mirrors `sync_device_name_to_receiver`'s verify-and-retry pattern in the reference sender).
- **Deliverable:** builder script creates the UDP Out DAT(s), packet-builder callbacks, and management panel; TD can rename, retype, reconfigure universes/virtual-resolution, and set static IP on devices directly — full parity with the web sender's device-management role.

---

### Phase 8 — Custom components (firm long-term goal, post-testing)

Not a Python custom-op / SDK effort — TD's own **Component-based custom operators** (Base COMP + Custom Parameters + Extensions), wrapping the built-in ops from Phases 1–7 rather than duplicating their functionality. Sequenced to start once Phases 1–4 have been tested and it's clear which parameters actually need exposing.

- [ ] **Primus Device component** — one instance per physical device. Internally the Phase 1–3 chain (Resize → TOP to CHOP → Merge → DMX Out CHOP); externally a single node with Custom Parameters: IP, receive mode (split/combined dropdown), A0/A1 type (dropdown constrained to the real firmware type list), virtual pixel count (slider bounded by expression to the physical count for the selected type), and pulse buttons for rename/config-push/identify (flash solid white to locate the physical unit).
- [ ] **Primus Manager component** — owns discovery (UDP In DAT) and the device table; uses a **Replicator COMP** to auto-instantiate one Primus Device component per discovered/known row, so the network stays live-synced to the table (device joins/leaves → component appears/disappears) rather than requiring a re-run of a builder script.
- [ ] **Primus Cue Engine component** — wraps the Phase 5 cue table, GO logic, and crossfade machinery behind cue-number/GO parameters, feeding each Device component's content selection.
- [ ] Protocol code (packet builders, discovery parser) moved from loose Execute DATs into a proper **Extension** (Python class) attached to each component, exposing methods like `device.pushRename()` / `device.pushVirtualResolution()` rather than scattered scripts.
- [ ] Export stable components as `.tox` files into a custom Palette folder, so future projects/shows start from dragging in a "Primus Device" node and setting an IP, rather than rerunning builder scripts.

**Deliverable:** a small palette of reusable, parameter-driven TD components that make the system usable by dragging in nodes and filling in fields — the "friendly interface" end state — while still sitting entirely on top of built-in TD operators underneath.

---

## 6. Where Python is unavoidable in the *protocol* (summary)

(Note: this is distinct from Section 2 — every network here, including the built-in-node phases, is still delivered via Python builder scripts. This table is specifically about which *capabilities* have no built-in TD operator at all, versus which are built-in ops assembled by script.)

| Capability | Built-in enough? | Why / why not |
|---|---|---|
| ArtDmx send | Yes | DMX Out CHOP |
| Content generation, resize, merge | Yes | TOPs/CHOPs |
| Cue targeting, crossfades | Yes | Switch/Cross TOPs + Table DAT, minimal Execute DAT for sequencing |
| Multi-device scaling | Yes | Replicator DAT |
| Discovery (ArtPollReply parsing) | No | Byte-level parsing of a variable capability tag; no built-in TD op decodes this |
| Config packets (rename/output/receive-mode/virtual-res/IP) | No | Custom opcodes; UDP Out DAT sends bytes but building them needs a Python callback |

---

## 7. Risks / open items to verify before/while building

- **Universe overflow:** confirm whether the firmware/sender already guards against a combined-mode pairing that exceeds 512 channels, or whether this needs to be enforced by not pairing two large output types on one device.
- **`small_grid` virtual-resolution default:** defaults to virtual=1 (solid color) unlike every other output type — confirm this is desired or override at rig setup.
- **ArtAddress opcode reuse:** this is the real reserved Art-Net opcode; fine for unicast to a known IP, but worth confirming no other genuine Art-Net node lives on the same network before ever broadcasting it.
- **Blackout behavior:** confirm whether the firmware holds last frame indefinitely on stale/missing ArtDmx, or whether TD needs to explicitly send zeroed frames for "off" cue states.
- **Serpentine grid ordering:** confirm whether grid output types expect linear or serpentine pixel order from the sender (affects the Reorder step in Phase 1).

---

## 8. Before implementation

Compile the exact byte-offset tables (ArtDmx header, ArtPollReply fixed fields, each custom opcode's field layout) from `V4/sender/artnet.py` into a single reference doc/table inside the TD project (or a shared markdown file), so every packet-builder callback in Phases 6–7 references the same source rather than re-deriving offsets ad hoc.
