"""PrimusManagerExt — shared send settings, discovery, Create/Sync Outputs."""


class PrimusManagerExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Rescan(self, _par=None):
        """Pulse handler + API: ArtPoll into devices table."""
        api = self.ownerComp.op("manager_api")
        if api is not None:
            try:
                api.module.rescan(self.ownerComp, source="ext")
                return
            except Exception as exc:
                print("[PrimusManager] rescan via DAT failed:", exc)
        c = self.ownerComp.op("controls")
        if c:
            for row in range(1, c.numRows):
                if c[row, 0].val == "rescan":
                    c[row, 1] = "1"
                    return
            c.appendRow(["rescan", "1"])

    def Createoutputs(self, _par=None):
        """Pulse handler: add-missing / sync PrimusOutput siblings (never destroy)."""
        api = self.ownerComp.op("manager_api")
        if api is not None:
            try:
                api.module.create_outputs(self.ownerComp)
                return
            except Exception as exc:
                print("[PrimusManager] create_outputs via DAT failed:", exc)
        self._create_outputs_fallback()

    def CreateOutputs(self, _par=None):
        self.Createoutputs(_par)

    def Blackoutall(self, _par=None):
        """Pulse handler: blackout every Output that shares this Manager."""
        self.BlackoutAll(True)

    def BlackoutAll(self, on=True):
        c = self.ownerComp.op("controls")
        if c is None:
            return
        for row in range(1, c.numRows):
            if c[row, 0].val == "blackout_all":
                c[row, 1] = "1" if on else "0"
                return
        c.appendRow(["blackout_all", "1" if on else "0"])

    def _apply_device_row(self, comp, devices, r, mgr_path, place=False, index=0):
        name = devices[r, "name"].val
        try:
            comp.par.Ip = devices[r, "ip"].val
            comp.par.Universe = int(devices[r, "universe"].val or 0)
            comp.par.Recvmode = devices[r, "recv_mode"].val or "split"
            comp.par.A0type = devices[r, "a0_type"].val
            comp.par.A1type = devices[r, "a1_type"].val
            comp.par.A0virtual = int(devices[r, "a0_virtual"].val or 1)
            comp.par.A1virtual = int(devices[r, "a1_virtual"].val or 1)
            comp.par.Devicename = name
            comp.par.Managerpath = mgr_path
            comp.par.Active = str(devices[r, "active"].val) in ("1", "true", "True")
            comp.par.display = True
            comp.allowCooking = True
            if place:
                comp.nodeX = 400 + (index % 3) * 400
                comp.nodeY = -(index // 3) * 350
        except Exception as e:
            print("[PrimusManager] param bind", e)

    def _create_outputs_fallback(self):
        devices = self.ownerComp.op("devices")
        parent = self.ownerComp.parent()
        template = self.ownerComp.op("PrimusOutput") or (
            parent.op("PrimusOutput") if parent else None
        )
        if not devices or parent is None or template is None:
            print("[PrimusManager] missing devices / parent / PrimusOutput template")
            return
        mgr_path = self.ownerComp.path
        created = 0
        updated = 0
        skipped = 0
        for r in range(1, devices.numRows):
            name = devices[r, "name"].val
            safe = (
                "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
                or f"out{r}"
            )
            existing = parent.op(safe)
            if existing is not None and existing.isCOMP and existing.op("artnet_cook") is not None:
                self._apply_device_row(existing, devices, r, mgr_path, place=False)
                updated += 1
                continue
            if existing is not None:
                skipped += 1
                print("[PrimusManager] skip %s (name taken, not a PrimusOutput)" % safe)
                continue
            copy = parent.copy(template, name=safe)
            self._apply_device_row(
                copy, devices, r, mgr_path, place=True, index=created + updated
            )
            created += 1
        msg = f"created={created} updated={updated} skipped={skipped}"
        print(f"[PrimusManager] sync outputs under {parent.path} — {msg}")
        try:
            self.ownerComp.par.Status = msg
        except Exception:
            pass
