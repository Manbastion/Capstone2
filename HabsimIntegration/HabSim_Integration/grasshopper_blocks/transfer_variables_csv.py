#! python 3
"""TRANSFER VARIABLES CSV

Updates mapped CSV cells using the current iteration's values.

Inputs: Repo, Names, Values, CSVFile, Mapping, TriggerIn
Outputs: Trigger, Report, Status
"""

import os
import sys
import Grasshopper as gh

Trigger, Report, Status = False, [], "Waiting for Trigger."

try:
    if not Repo or not os.path.isdir(str(Repo)):
        raise ValueError("Repo must be the project folder containing the Python files.")
    if not CSVFile or not os.path.isfile(str(CSVFile)):
        raise ValueError("CSVFile must point to an existing CSV file.")
    if Repo not in sys.path:
        sys.path.insert(0, str(Repo))

    import importlib
    import gh_bridge
    import csv_cells
    importlib.reload(gh_bridge)
    importlib.reload(csv_cells)

    values, skipped = gh_bridge.plain_pairs(Names, Values)
    try:
        import multirun
        importlib.reload(multirun)
        state = multirun.load_state()
        overrides = multirun.current_overrides(state) if state else None
    except (ImportError, OSError, ValueError):
        overrides = None

    if overrides:
        values.update(overrides)

    if TriggerIn:
        Report, _ = csv_cells.transfer_cells(str(CSVFile), Mapping or [], values)
        Trigger = True
        count = len([line for line in Report if not line.startswith("note:")])
        Status = "CSV updated: %d cell(s). Trigger sent." % count
        if skipped:
            Status += " Skipped variables: " + "; ".join(skipped)
    else:
        Report = csv_cells.preview(str(CSVFile), Mapping or [], values)
        Status = "Mapping check complete: %d cell(s) found." % len(Report)

except Exception as error:
    Trigger, Report = False, []
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
