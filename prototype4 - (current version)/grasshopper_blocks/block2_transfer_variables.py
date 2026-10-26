#! python 3
"""BLOCK 2 - TRANSFER VARIABLES
Writes the Grasshopper values into the MATLAB .m file.

INPUTS
  Repo        str   item  - path to your Capstone2 folder
  Names       str   list  - GH variable names
  Values      (no type hint) TREE - one BRANCH per variable, in the same order
                            as Names. Numbers, text, true/false and points are all
                            fine. 1 item in a branch = one value, several items =
                            a vector/list (e.g. a time series). Set Tree Access
                            and leave the type hint EMPTY (a 'float' hint would
                            reject text). Your own formats (e.g. 1 | 2 | 3 ->
                            [1 2 3]) are set up in the GUI: Value Formats...
  MatlabFile  str   item  - the MATLAB .m file to write into
  Config      str   item  - OPTIONAL, from the GUI block. Uses the mode, selection,
                            links and renames you saved in the GUI window.
                            If empty, variables with the SAME NAME as one in the
                            .m file are overwritten.
  Run         bool  item  - Button / Toggle. Transfer happens when True.

OUTPUTS
  MatlabFile_Out  str  - same path, but ONLY after a successful transfer
                         (wire this to the Run MATLAB block so it waits)
  Report          str list - what changed (also logged to the GUI's History)
  Status          str
"""
import sys
import Grasshopper as gh

MatlabFile_Out, Report, Status = None, [], "Idle. Set Run = True."
try:
    if Run:
        if Repo and Repo not in sys.path:
            sys.path.insert(0, str(Repo))
        import importlib, Capstone2.prototype4.gh_bridge as gh_bridge
        importlib.reload(gh_bridge)

        Report, skipped = gh_bridge.transfer(Names, Values, str(MatlabFile),
                                             str(Config) if Config else None)
        MatlabFile_Out = str(MatlabFile)
        Status = "Transfer complete."
        if skipped:
            Status += " Skipped: " + "; ".join(skipped)
except Exception as e:
    MatlabFile_Out = None
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
