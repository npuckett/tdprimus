"""PrimusDeviceExt — attach as Extension on Primus Device COMP."""


class PrimusDeviceExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def PushRename(self):
        name = self.ownerComp.par.Devicename.eval()
        ip = self.ownerComp.par.Ip.eval()
        self._send_action(ip, "rename", name)

    def PushVirtualResolution(self):
        ip = self.ownerComp.par.Ip.eval()
        v0 = int(self.ownerComp.par.A0virtual.eval())
        v1 = int(self.ownerComp.par.A1virtual.eval())
        self._send_action(ip, "virtual_resolution", str(v0), str(v1))

    def PushReceiveConfig(self):
        ip = self.ownerComp.par.Ip.eval()
        mode = self.ownerComp.par.Recvmode.eval()
        univ = int(self.ownerComp.par.Universe.eval())
        self._send_action(ip, "receive_config", mode, str(univ))

    def PushOutputConfig(self):
        ip = self.ownerComp.par.Ip.eval()
        self._send_action(
            ip,
            "output_config",
            self.ownerComp.par.A0type.eval(),
            self.ownerComp.par.A1type.eval(),
        )

    def Identify(self):
        ip = self.ownerComp.par.Ip.eval()
        univ = int(self.ownerComp.par.Universe.eval())
        self._send_action(ip, "identify", str(univ), "73")

    def Blackout(self, on=True):
        ctrl = self.ownerComp.op("controls")
        if ctrl:
            ctrl["blackout", 1] = 1 if on else 0

    def _send_action(self, ip, action, arg1="", arg2="", arg3="", arg4=""):
        mgr = self.ownerComp.parent()
        push = mgr.op("push") if mgr else None
        controls = mgr.op("controls") if mgr else None
        if push is None:
            print("[PrimusDevice] no manager push table")
            return
        if push.numRows < 1:
            return
        if push.numRows == 1:
            push.appendRow([ip, action, arg1, arg2, arg3, arg4])
        else:
            push[1, "ip"] = ip
            push[1, "action"] = action
            push[1, "arg1"] = arg1
            push[1, "arg2"] = arg2
            push[1, "arg3"] = arg3
            push[1, "arg4"] = arg4
        if controls:
            controls["push", 1] = 1
