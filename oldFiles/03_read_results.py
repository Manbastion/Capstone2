"""Rhino 8 Python 3: Load Variables Back.
Inputs: Repo, FilePath, Variable, Load, Refresh
Outputs: Names, Values, Status
Connect Run MATLAB.ResultsFile to FilePath and Run MATLAB.Done to Load.
"""
import importlib.util
from pathlib import Path
import scriptcontext as sc
from Grasshopper.Kernel import GH_RuntimeMessageLevel


def load_module(repo, filename):
    path = Path(str(repo)).expanduser().resolve() / "grasshopper_components" / filename
    if not path.is_file():
        raise ValueError("Repo must point to Capstone2 with grasshopper_components installed.")
    spec = importlib.util.spec_from_file_location("capstone_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

Names, Values, Status = [], [], ""
try:
    refresh_trigger = Refresh
    if not bool(Load):
        Status = "Waiting for successful MATLAB output. Load=False clears previous values."
    else:
        bridge = load_module(Repo, "bridge.py")
        Names, Values = bridge.read_result(Repo, FilePath, Variable)
        Status = ("Loaded {} value(s) from {}.".format(len(Values), Variable)
                  if str(Variable or "").strip() else "Choose a variable from Names.")
except Exception as error:
    Names, Values = [], []
    Status = str(error)
    ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Error, Status)
