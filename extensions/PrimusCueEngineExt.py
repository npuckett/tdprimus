"""PrimusCueEngineExt — GO / Goto for cue table."""


class PrimusCueEngineExt:
    def __init__(self, ownerComp):
        self.ownerComp = ownerComp

    def Go(self):
        c = self.ownerComp.op("controls")
        if c:
            c["go", 1] = 1

    def Goto(self, cue_number):
        cues = self.ownerComp.op("cues")
        state = self.ownerComp.op("cue_state")
        if not cues or not state:
            return
        for r in range(1, cues.numRows):
            if cues[r, "cue"].val == str(cue_number):
                state["cue_index", 1] = r - 1
                self.Go()
                return
        print(f"[PrimusCueEngine] cue {cue_number} not found")
