#! python 3
"""BLOCK 3 - RUN MATLAB
Runs the .m file, then reads back every numeric variable it produced.

INPUTS
  Repo        str   item  - path to your Capstone2 folder
  MatlabFile  str   item  - wire from Transfer block's MatlabFile_Out
  MatlabExe   str   item  - OPTIONAL, full path to matlab.exe if "matlab"
                            isn't on PATH
  PythonExe   str   item  - OPTIONAL. If set, run_matlab_gh.py runs as its own
                            python process; if empty it runs inside Grasshopper.
  Run         bool  item  - Button / Toggle. MATLAB runs when True.

OUTPUTS
  Names   str list  - output variable names
  Values  list      - output values (floats; matrices come back as text like "[1 2;3 4]")
  Status  str
  Done    bool      - OPTIONAL output: this MATLAB run and result loading succeeded
  Failed  bool      - OPTIONAL output: this MATLAB run failed

NOTE: Grasshopper freezes while MATLAB runs. That's normal.
Completion notifications are configured with the GUI's Notifications button.
For a whole Grasshopper loop, use Block 4 with the OUTER loop's final signal.
"""
import sys
from pathlib import Path
import Grasshopper as gh

Names, Values, Status = [], [], "Idle. Set Run = True."
Done, Failed = False, False
try:
    if Run:
        if not MatlabFile:
            raise ValueError("MatlabFile is empty - did the Transfer block fail?")
        root = Path(str(Repo)).expanduser().resolve()
        integration = root / "grasshopper_integration (2)" / "grasshopper_integration"
        for folder in (root, integration):
            if folder.is_dir() and str(folder) not in sys.path:
                sys.path.insert(0, str(folder))
        import importlib, gh_bridge
        importlib.reload(gh_bridge)

        Names, Values = gh_bridge.run_matlab(
            str(MatlabFile), str(MatlabExe) if MatlabExe else "matlab",
            python_exe=str(PythonExe) if PythonExe else None)
        Status = "MATLAB finished. %d variable(s) read." % len(Names)
        Done = True
except Exception as e:
    Names, Values = [], []
    Failed = True
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
