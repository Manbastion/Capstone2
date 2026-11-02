#! python 3
"""BLOCK 3 - RUN MATLAB  (opens YOUR run_matlab.py)
Takes the settings from this block's inputs, writes them into the top of
your run_matlab.py (CAPSTONE_FOLDER and MATLAB_FILE - nothing else in the
file is changed), then opens that script in its own window.
Grasshopper stays usable while it runs. No data is saved: the .m file is
simply run (including anything it does with Simulink).

INPUTS
  Repo            str   item  - path to your Capstone2 folder (where gh_bridge.py is)
  RunScript       str   item  - full path to your run_matlab.py
  CapstoneFolder  str   item  - OPTIONAL. Folder that contains
                                run_matlab_import_python_v2.py. Empty = the Repo folder.
  MatlabFile      str   item  - the .m file (wire from Transfer block's MatlabFile_Out)
  PythonExe       str   item  - OPTIONAL. Full path to a Python 3.10+ python.exe.
                                Empty = "python".
  Run             bool  item  - Button / Toggle. A run starts when this turns True.

OUTPUTS
  Ready   bool  - True once MATLAB has finished running the .m file without error
  Status  str

(The old SaveType input and OutputFile output are no longer used - you can
delete them from the component. Ready keeps its name so existing wires still work.)

HEADLESS (MATLAB window or not) is set inside run_matlab.py, not here.
The script's window stays open until you press ENTER in it. Ready turns
True as soon as MATLAB has finished, before that.
"""
import sys
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

comp = ghenv.Component
key = "CapstoneRunScript_" + str(comp.InstanceGuid)

Ready, Status = False, "Idle. Press Run."
note = ""


def _recompute():
    """Called from a background thread when MATLAB finishes / the script exits."""
    def on_ui_thread():
        comp.ExpireSolution(True)
    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(on_ui_thread))
    except Exception:
        pass  # worst case: press F5 to refresh


try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib, gh_matlab_run as gh_run
    importlib.reload(gh_run)

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
            gh_run.update_script_settings(str(RunScript), capstone, str(MatlabFile))
            run = gh_run.ScriptRun(
                str(RunScript), str(PythonExe) if PythonExe else "python",
                str(MatlabFile), on_change=_recompute)
            sc.sticky[key] = run

    if run is not None:
        Ready = bool(run.matlab_done and run.matlab_status == 0)
        if run.running and run.matlab_done and run.matlab_status == 0:
            Status = "MATLAB finished. Press ENTER in the script's window to close it."
        elif run.running and run.matlab_done:
            Status = "MATLAB reported an error. See the script's window for details."
        elif run.running:
            Status = "Running MATLAB (%d s so far)... a window has opened." % run.elapsed
        elif run.matlab_done and run.matlab_status == 0:
            Status = "Finished."
        elif run.matlab_done:
            Status = "MATLAB reported an error (see the script's window, or run run_matlab.py yourself to see it again)."
        elif run.returncode == 0:
            Status = "The script closed before MATLAB reported back. Check MATLAB ran."
        else:
            Status = ("The script stopped with exit code %s before MATLAB finished. "
                      "Run run_matlab.py yourself (VS Code or Command Prompt) to see the error."
                      % run.returncode)
    Status = note + Status
except Exception as e:
    Ready = False
    Status = "ERROR: %s" % e
    ghenv.Component.AddRuntimeMessage(
        gh.Kernel.GH_RuntimeMessageLevel.Error, Status)