"""PrimusCueEngineExt — GO / Goto / Blackout for Phase 6 cue deck."""


class PrimusCueEngineExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def _api(self):
        ns = {"op": op, "project": project}  # noqa: F821
        api = self.ownerComp.op("cue_api")
        if api is None:
            raise RuntimeError("cue_api missing — rebuild Phase 6")
        exec(api.text, ns)
        return ns

    def Go(self):
        return self._api()["go"](self.ownerComp, source="ext")

    def Goto(self, cue_number):
        return self._api()["goto"](cue_number, self.ownerComp, source="ext")

    def Blackout(self, on=True):
        return self._api()["blackout"](bool(on), self.ownerComp, source="ext")
