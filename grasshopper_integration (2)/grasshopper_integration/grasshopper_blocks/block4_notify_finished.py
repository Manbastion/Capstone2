#! python 3
"""BLOCK 4 - LOOP FINISHED NOTIFICATION (optional)

Use notification settings -> Only at the end of the whole loop.
Connect the OUTER loop's final signal, not the completion of each iteration.

INPUTS (all Item Access)
  Repo            str    Capstone2 project root
  Done            bool   True only when the whole loop and result loading finish
  Failed          bool   OPTIONAL, final loop failure signal (default False)
  Enabled         bool   OPTIONAL, default True
  ElapsedSeconds  float  OPTIONAL, measured total duration; leave empty if unknown

OUTPUTS
  Triggered       bool   True on the solution that queues an alert (not delivery)
  Status          str    What happened; Recent alerts shows delivery attempts

First solve with Done=False and Failed=False to arm. A terminal signal fires
once, even if Grasshopper recomputes with it still True. Reset both to False
before the next run. Opening a saved definition with True does not notify.
"""
import sys
import scriptcontext as sc
import Grasshopper as gh
from pathlib import Path

Triggered, Status = False, "Waiting for the loop."
try:
    root = str(Path(str(Repo)).expanduser().resolve())
    if root not in sys.path:
        sys.path.insert(0, root)
    import habsim_notifications as alerts
    key = ("HabSimLoopNotification", str(ghenv.Component.InstanceGuid))
    state = sc.sticky.setdefault(key, {})
    enabled = globals().get("Enabled")
    if enabled is not None and not bool(enabled):
        state.clear()
        Status = "Notifications disabled for this component."
    else:
        event = alerts.completion_transition(state, Done, globals().get("Failed", False))
        if event:
            receipt = alerts.notify_completion(success=event == "success", scope="loop",
                                               elapsed_seconds=globals().get("ElapsedSeconds"))
            state["receipt"] = receipt
            Triggered = receipt.queued
        receipt = state.get("receipt")
        if state.get("phase") == "armed":
            state.pop("receipt", None)
            Status = "Armed. Waiting for the whole loop to finish."
        elif receipt is not None:
            Status = "Notification %s. See Notifications > Recent alerts for details." % receipt.result["status"]
        else:
            Status = "Set Done and Failed to False to arm before the next loop."
except Exception as error:
    Status = "Notification error: %s" % error
    ghenv.Component.AddRuntimeMessage(gh.Kernel.GH_RuntimeMessageLevel.Warning, Status)
