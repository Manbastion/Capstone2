"""Rhino 8 Python 3: Transfer Variables.
Inputs: Repo, SourceFile, DestinationFile, SourceNames (List), DestinationNames (List), Apply
Outputs: Preview, TransferredFile, Ready, BackupPath, Status
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

Preview, TransferredFile, Ready, BackupPath, Status = [], "", False, "", ""
try:
    bridge = load_module(Repo, "bridge.py")
    key = ("CapstoneTransferV2", str(ghenv.Component.InstanceGuid))
    action_key = key + ("button",)
    last_key = key + ("last",)
    do_apply = bridge.button_edge(sc.sticky, action_key, Apply)
    if do_apply:
        sc.sticky.pop(last_key, None)
    Preview, backup, report = bridge.transfer(
        Repo, SourceFile, DestinationFile, SourceNames, DestinationNames, apply=do_apply)
    signature = bridge.transfer_signature(SourceFile, DestinationFile, SourceNames, DestinationNames)
    if do_apply:
        sc.sticky[last_key] = {"signature": signature, "backup": backup}
    last = sc.sticky.get(last_key)
    Ready = bool(last and last["signature"] == signature)
    if Ready:
        TransferredFile = str(bridge.absolute_file(DestinationFile))
        BackupPath = last["backup"]
        Status = "Transfer complete. TransferredFile is ready for Run MATLAB."
    else:
        Status = "Preview only. Review mappings, then press Apply."
except Exception as error:
    Preview, TransferredFile, Ready, BackupPath = [], "", False, ""
    Status = str(error)
    ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Error, Status)
