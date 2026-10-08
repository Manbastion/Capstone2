#! python 3
"""BLOCK 3 - RUN MATLAB
Runs the .m file, then reads back every numeric variable it produced.

INPUTS
  Repo        str   item  - path to your Capstone2 folder
  MatlabFile  str   item  - wire from Transfer block's MatlabFile_Out
  MatlabExe   str   item  - OPTIONAL, full path to matlab.exe if "matlab"
                            isn't on PATH
  Run         bool  item  - Button / Toggle. MATLAB runs when True.

OUTPUTS
  Names   str list  - output variable names
  Values  list      - output values (floats; matrices come back as text like "[1 2;3 4]")
  Status  str

NOTE: Grasshopper freezes while MATLAB runs. That's normal.
"""
import sys
import Grasshopper as gh

Names, Values, Status = [], [], "Idle. Set Run = True."
try:
    if Run:
        if not MatlabFile:
            raise ValueError("MatlabFile is empty - did the Transfer block fail?")
        if Repo and Repo not in sys.path:
            sys.path.insert(0, str(Repo))
        import importlib, gh_bridge
        importlib.reload(gh_bridge)

        Names, Values = gh_bridge.run_matlab(
            str(MatlabFile), str(MatlabExe) if MatlabExe else "matlab")
        Status = "MATLAB finished. %d variable(s) read." % len(Names)
except Exception as e:
    Names, Values = [], []
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
