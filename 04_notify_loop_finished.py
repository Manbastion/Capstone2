#! python 3
"""Notify once at the end of a whole Grasshopper loop.

Inputs (Item Access): Repo (str), Done (bool), Failed (optional bool),
    Enabled (optional bool, default True), ElapsedSeconds (optional float).
Outputs: Triggered (bool), Status (str).
Select 'whole loop' in notification settings. Use the OUTER loop's final signal.
Solve with Done/Failed=False first. Saved True signals do not trigger on load.
"""
from pathlib import Path
import sys
import scriptcontext as sc
from Grasshopper.Kernel import GH_RuntimeMessageLevel

Triggered, Status = False, "Waiting for the loop."
try:
    root = Path(str(Repo)).expanduser().resolve()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
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
    ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Warning, Status)
