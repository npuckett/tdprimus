"""PrimusOutputExt — attach as Extension on PrimusOutput COMP."""


class PrimusOutputExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Blackout(self, on=True):
        try:
            self.ownerComp.par.Blackout = 1 if on else 0
        except Exception:
            sample = self.ownerComp.op("sampling")
            if sample:
                for row in range(1, sample.numRows):
                    if sample[row, 0].val == "blackout":
                        sample[row, 1] = "1" if on else "0"
                        return

    def Pushconfig(self):
        """Pulse handler + API: force config re-push on next cook."""
        sender = self.ownerComp.op("artnet_cook")
        if sender is not None:
            sender.store("force_config", True)
            print("[PrimusOutput]", self.ownerComp.name, "force config")

    def PushConfig(self):
        self.Pushconfig()

    def Identify(self, seconds=2.0):
        """Pulse handler + API: flash solid white ArtDmx briefly."""
        sender = self.ownerComp.op("artnet_cook")
        if sender is None:
            print("[PrimusOutput] no artnet_cook")
            return
        import time

        try:
            sec = float(seconds)
        except Exception:
            sec = 2.0
        # Pulse callbacks may pass the Par object as the first arg.
        if not isinstance(seconds, (int, float, str)):
            sec = 2.0
        sender.store("identify_until", time.time() + sec)
        sender.store("force_config", True)
        print("[PrimusOutput]", self.ownerComp.name, "identify %.1fs" % sec)
