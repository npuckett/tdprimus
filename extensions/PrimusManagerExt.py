"""PrimusManagerExt — discovery table + device replication."""


class PrimusManagerExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Rescan(self):
        c = self.ownerComp.op("controls")
        if c:
            c["rescan", 1] = 1

    def RebuildDevices(self):
        devices = self.ownerComp.op("devices")
        container = self.ownerComp.op("device_container")
        template = self.ownerComp.op("device_template")
        if not devices or not container or not template:
            print("[PrimusManager] missing devices/container/template")
            return
        for child in list(container.children):
            child.destroy()
        for r in range(1, devices.numRows):
            name = devices[r, "name"].val
            safe = (
                "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name)
                or f"dev{r}"
            )
            copy = container.copy(template, name=safe)
            try:
                copy.par.Ip = devices[r, "ip"].val
                copy.par.Universe = int(devices[r, "universe"].val or 0)
                copy.par.Recvmode = devices[r, "recv_mode"].val or "combined"
                copy.par.A0type = devices[r, "a0_type"].val
                copy.par.A1type = devices[r, "a1_type"].val
                copy.par.A0virtual = int(devices[r, "a0_virtual"].val or 1)
                copy.par.A1virtual = int(devices[r, "a1_virtual"].val or 1)
                copy.par.Devicename = name
                copy.par.display = True
                copy.allowCooking = True
            except Exception as e:
                print("[PrimusManager] param bind", e)
        print(f"[PrimusManager] replicated {devices.numRows - 1} devices")
