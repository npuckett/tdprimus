"""PrimusDeviceExt — legacy name. Phase 9 uses PrimusOutputExt instead."""


class PrimusDeviceExt:
    """Compatibility stub. Prefer attaching PrimusOutputExt on PrimusOutput COMPs."""

    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Blackout(self, on=True):
        try:
            self.ownerComp.par.Blackout = 1 if on else 0
        except Exception:
            pass

    def PushConfig(self):
        sender = self.ownerComp.op("artnet_cook")
        if sender is not None:
            sender.store("force_config", True)

    def Identify(self, seconds=2.0):
        sender = self.ownerComp.op("artnet_cook")
        if sender is None:
            return
        import time

        sender.store("identify_until", time.time() + float(seconds))
