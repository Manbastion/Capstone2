#! python 3
"""BLOCK 2 - TRANSFER VARIABLES"""

import sys
import Grasshopper as gh

MatlabFile_Out, RunMATLAB, Report, Status = None, False, [], "Block 2 received Run = False."

try:
    if Run:
        Status = "BLOCK 2 RECEIVED RUN = TRUE"

        if Repo and Repo not in sys.path:
            sys.path.insert(0, str(Repo))

        import importlib, gh_bridge
        importlib.reload(gh_bridge)

        import multirun
        importlib.reload(multirun)

        state = multirun.load_state()
        overrides = multirun.current_overrides(state) if state else None

        Report, skipped = gh_bridge.transfer(
            Names,
            Values,
            str(MatlabFile),
            str(Config) if Config else None,
            overrides=overrides
        )

        MatlabFile_Out = str(MatlabFile)
        RunMATLAB = True
        Status = "Transfer complete. MATLAB trigger sent."

        if skipped:
            Status += " Skipped: " + "; ".join(skipped)

except Exception as e:
    MatlabFile_Out, RunMATLAB = None, False
    Status = "ERROR: %s" % e

    try:
        import multirun
        multirun.fail_transfer(e)

        import Rhino, System, scriptcontext as sc
        controller = sc.sticky.get("CapstoneMultiRunController")

        if controller is not None:
            Rhino.RhinoApp.InvokeOnUiThread(
                System.Action(lambda: controller.ExpireSolution(True))
            )

    except Exception:
        pass

    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status
    )