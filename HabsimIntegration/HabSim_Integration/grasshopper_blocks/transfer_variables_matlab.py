#! python 3
"""TRANSFER VARIABLES MATLAB

Inputs: Repo, Names, Values, MatlabFile, Config, TriggerIn
Outputs: Trigger, Report, Status
"""

import os
import sys
import Grasshopper as gh

Trigger, Report, Status = False, [], "Waiting for Trigger."

try:
    if TriggerIn:
        if not Repo or not os.path.isdir(str(Repo)):
            raise ValueError("Repo must be the project folder containing the Python files.")
        if not MatlabFile or not os.path.isfile(str(MatlabFile)):
            raise ValueError("MatlabFile must point to an existing MATLAB script.")
        if Repo not in sys.path:
            sys.path.insert(0, str(Repo))

        import importlib
        import gh_bridge
        import multirun
        importlib.reload(gh_bridge)
        importlib.reload(multirun)

        state = multirun.load_state()
        overrides = multirun.current_overrides(state) if state else None
        Report, skipped = gh_bridge.transfer(
            Names, Values, str(MatlabFile),
            str(Config) if Config else None,
            overrides=overrides
        )
        Trigger = True
        Status = "Variable transfer complete. Trigger sent."
        if skipped:
            Status += " Skipped: " + "; ".join(skipped)

except Exception as error:
    Trigger = False
    Status = "ERROR: %s" % error
    try:
        import multirun
        multirun.fail_transfer(error)
        import Rhino, System, scriptcontext as sc
        controller = sc.sticky.get("HabSimMultiRunController")
        if controller is not None:
            Rhino.RhinoApp.InvokeOnUiThread(
                System.Action(lambda: controller.ExpireSolution(True))
            )
    except Exception:
        pass
    try:
        ghenv.Component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Error, Status
        )
    except Exception:
        pass
