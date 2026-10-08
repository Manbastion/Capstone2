#! python 3
"""BLOCK 2 - TRANSFER VARIABLES
Writes the Grasshopper values into the MATLAB .m file.

INPUTS
  Repo        str   item  - path to your Capstone2 folder
  Names       str   list  - GH variable names
  Values      float list  - GH variable values
  MatlabFile  str   item  - the MATLAB .m file to write into
  Config      str   item  - OPTIONAL, from the GUI block. If empty, variables
                            with the SAME NAME as one in the .m file are overwritten.
  Run         bool  item  - Button / Toggle. Transfer happens when True.

OUTPUTS
  MatlabFile_Out  str  - same path, but ONLY after a successful transfer
                         (wire this to the Run MATLAB block so it waits)
  Report          str list - what changed
  Status          str
"""
import sys
import Grasshopper as gh

MatlabFile_Out, Report, Status = None, [], "Idle. Set Run = True."
try:
    if Run:
        if Repo and Repo not in sys.path:
            sys.path.insert(0, str(Repo))
        import importlib, gh_bridge
        importlib.reload(gh_bridge)

        Report, skipped = gh_bridge.transfer(Names, Values, str(MatlabFile),
                                             str(Config) if Config else None)
        MatlabFile_Out = str(MatlabFile)
        Status = "Transfer complete."
        if skipped:
            Status += " Skipped (not numeric): " + ", ".join(skipped)
except Exception as e:
    MatlabFile_Out = None
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
