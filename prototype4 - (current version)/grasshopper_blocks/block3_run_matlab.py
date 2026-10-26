#! python 3
"""BLOCK 3 - RUN MATLAB  (opens YOUR run_matlab.py)
Takes the three settings from this block's inputs, writes them into the top of
your run_matlab.py (CAPSTONE_FOLDER, MATLAB_FILE, SAVE_TYPE - nothing else in
the file is changed), then opens that script in its own window.
Grasshopper stays usable while it runs.

INPUTS
  Repo            str   item  - path to your Capstone2 folder (where gh_bridge.py is)
  RunScript       str   item  - full path to your run_matlab.py
  CapstoneFolder  str   item  - OPTIONAL. Folder that contains
                                run_matlab_import_python_v2.py. Empty = the Repo folder.
  MatlabFile      str   item  - the .m file (wire from Transfer block's MatlabFile_Out)
  SaveType        str   item  - "json", "csv" or "txt". Empty = "json".
  PythonExe       str   item  - OPTIONAL. Full path to a Python 3.10+ python.exe.
                                Empty = "python".
  Run             bool  item  - Button / Toggle. A run starts when this turns True.

OUTPUTS
  OutputFile  str   - path of matlab_output_variables.<SaveType>, once MATLAB has written it
  Ready       bool  - True once the output file has been written by this run
  Status      str

The script's window stays open until you press ENTER in it (your script ends
with input(...)). The results are ready BEFORE that - Ready turns True as soon
as MATLAB has written the file.
"""
import sys
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

comp = ghenv.Component
key = "CapstoneRunScript_" + str(comp.InstanceGuid)

OutputFile, Ready, Status = None, False, "Idle. Press Run."
note = ""


def _recompute():
    """Called from a background thread when the output appears / the script exits."""
    def on_ui_thread():
        comp.ExpireSolution(True)
    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(on_ui_thread))
    except Exception:
        pass  # worst case: press F5 to refresh


try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib, Capstone2.prototype4.gh_bridge as gh_bridge
    importlib.reload(gh_bridge)

    run = sc.sticky.get(key)

    # Start a run only when Run turns True (a Toggle left on won't loop forever).
    was_on = sc.sticky.get(key + "_run", False)
    sc.sticky[key + "_run"] = bool(Run)
    if Run and not was_on:
        if run is not None and run.running:
            note = "Already running (see its window); close it or press ENTER there first. "
        else:
            if not RunScript:
                raise ValueError("RunScript is empty - give the full path to run_matlab.py.")
            if not MatlabFile:
                raise ValueError("MatlabFile is empty - has the Transfer block finished?")
            capstone = str(CapstoneFolder) if CapstoneFolder else str(Repo)
            changed = gh_bridge.update_script_settings(
                str(RunScript), capstone, str(MatlabFile), str(SaveType) if SaveType else "json")
            run = gh_bridge.ScriptRun(
                str(RunScript), str(PythonExe) if PythonExe else "python",
                str(MatlabFile), str(SaveType) if SaveType else "json",
                on_change=_recompute)
            sc.sticky[key] = run

    if run is not None:
        Ready = run.output_ready
        OutputFile = run.output_file if Ready else None
        if run.running and Ready:
            Status = "MATLAB finished - output is ready. Press ENTER in the script's window to close it."
        elif run.running:
            Status = "Running run_matlab.py (%d s so far)... a window has opened." % run.elapsed
        elif run.returncode == 0:
            Status = "Finished. Output: %s" % run.output_file
        else:
            Status = ("The script stopped with exit code %s and no output was written. "
                      "The error was shown in its window; run run_matlab.py yourself "
                      "(VS Code or Command Prompt) to see it again." % run.returncode)
            if Ready:
                Status = "The script exited with code %s, but the output file was written." % run.returncode
    Status = note + Status
except Exception as e:
    OutputFile, Ready = None, False
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
