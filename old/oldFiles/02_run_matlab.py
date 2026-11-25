"""Rhino 8 Python 3: Run MATLAB asynchronously.
Inputs: Repo, MatlabExe, ScriptFile, OutputNames (List), OutputFolder,
        Run, Check, Cancel, TimeoutSeconds
Outputs: ResultsFile, CSVFile, Done, Running, LogFile, Status
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

ResultsFile, CSVFile, Done, Running, LogFile, Status = "", "", False, False, "", ""
try:
    bridge = load_module(Repo, "bridge.py")
    runner = load_module(Repo, "matlab_runner.py")
    key = ("CapstoneMatlabV2", str(ghenv.Component.InstanceGuid))
    job_key = key + ("job",)
    run_pressed = bridge.button_edge(sc.sticky, key + ("run",), Run)
    cancel_pressed = bridge.button_edge(sc.sticky, key + ("cancel",), Cancel)
    check_trigger = Check
    timeout = 600 if TimeoutSeconds is None else TimeoutSeconds
    executable = str(MatlabExe or "matlab")
    job = sc.sticky.get(job_key)
    was_running = bool(job and runner.job_status(job)["state"] == "Running")
    if cancel_pressed and was_running:
        runner.cancel_job(job)
    if run_pressed and not was_running and not cancel_pressed:
        # Clear the previous success before validating a new launch request.
        sc.sticky.pop(job_key, None)
        job = runner.start_job(executable, ScriptFile, OutputNames, OutputFolder, timeout)
        sc.sticky[job_key] = job
    if job:
        snapshot = runner.job_status(job)
        Running = snapshot["state"] == "Running"
        LogFile = snapshot["log_file"]
        Status = "{} ({:.1f}s): {}".format(snapshot["state"], snapshot["elapsed_seconds"], snapshot["message"])
        try:
            current = runner.request_signature(executable, ScriptFile, OutputNames, OutputFolder, timeout)
        except Exception:
            current = None
        if current != job["signature"]:
            Status += " Inputs changed: outputs hidden until a new run with these inputs succeeds."
        elif snapshot["state"] == "Succeeded":
            ResultsFile, CSVFile, Done = snapshot["results_file"], snapshot["csv_file"], True
        if run_pressed and was_running:
            Status += " A job is already running; another job was not started."
        if snapshot["state"] in ("Failed", "Timed out"):
            ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Error, Status)
    else:
        Status = "Ready. Press Run once. Use Check to refresh status or Cancel to stop this job."
except Exception as error:
    ResultsFile, CSVFile, Done = "", "", False
    Status = str(error)
    ghenv.Component.AddRuntimeMessage(GH_RuntimeMessageLevel.Error, Status)
