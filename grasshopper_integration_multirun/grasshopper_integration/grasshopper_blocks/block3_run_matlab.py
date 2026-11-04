#! python 3
"""BLOCK 3 - RUN MATLAB
Normal use is unchanged. When Block 0's multi-run controller is active, this
block waits for the MATLAB completion marker, reports the result to Block 0,
and automatically closes each run_matlab.py console before the next iteration.

INPUTS
  Repo            str   item  - project folder containing gh_bridge.py
  RunScript       str   item  - full path to run_matlab.py
  CapstoneFolder  str   item  - OPTIONAL folder containing run_matlab_import_python_v2.py
  MatlabFile      str   item  - wire from Block 2's MatlabFile_Out
  PythonExe       str   item  - Python 3.10+ executable. Empty = "python".
  Run             bool  item  - wire Block 2's RunMATLAB output here

OUTPUTS
  OutputFile  str   - result file path after MATLAB completes
  Ready       bool  - True once MATLAB has completed successfully
  Status      str
"""
import sys
import os
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

comp = ghenv.Component
key = "CapstoneRunScript_" + str(comp.InstanceGuid)
OutputFile, Ready, Status = None, False, "Idle. Press Run."
note = ""


def _recompute():
    def on_ui_thread():
        comp.ExpireSolution(True)
    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(on_ui_thread))
    except Exception:
        pass

def _wake_controller():
    def on_ui_thread():
        controller = sc.sticky.get("CapstoneMultiRunController")
        if controller is not None:
            controller.ExpireSolution(True)

    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(on_ui_thread))
    except Exception:
        pass

try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib
    import gh_bridge
    importlib.reload(gh_bridge)

    state = None
    try:
        import multirun
        importlib.reload(multirun)
        state = multirun.load_state()
    except Exception:
        multirun = None

    run = sc.sticky.get(key)
    was_on = sc.sticky.get(key + "_run", False)
    # Once a batch has ended, a fresh manual Run button press can still start
    # an ordinary single run. Block 0 itself is low after completion/error.
    multi_session = bool(state and state.get("status") == "running") or bool(
        state and state.get("status") in ("error", "complete") and not (Run and not was_on))
    multi_active = bool(state and state.get("status") == "running")
    sc.sticky[key + "_run"] = bool(Run)

    if multi_session:
        if multi_active and Run and not was_on:
            if run is not None and getattr(run, "running", False):
                note = "Already running. Waiting for the current MATLAB run. "
            else:
                if not RunScript:
                    raise ValueError("RunScript is empty - give the full path to run_matlab.py.")
                if not MatlabFile:
                    raise ValueError("MatlabFile is empty - has the Transfer block finished?")
                capstone = str(CapstoneFolder) if CapstoneFolder else str(Repo)
                import gh_matlab_run
                importlib.reload(gh_matlab_run)
                gh_matlab_run.update_script_settings(
                    str(RunScript), capstone, str(MatlabFile))
                holder = {"completion_reported": False}

                def _multi_changed():
                    current = holder.get("run")

                    if (current is not None
                            and current.matlab_done
                            and not holder["completion_reported"]):

                        holder["completion_reported"] = True

                        if multirun.finish_iteration(current.matlab_status):
                            _recompute()
                            _wake_controller()

                run = gh_matlab_run.ScriptRun(
                    str(RunScript), str(PythonExe) if PythonExe else "python",
                    str(MatlabFile), on_change=_multi_changed)
                holder["run"] = run
                sc.sticky[key] = run

        if run is not None and hasattr(run, "matlab_done"):
            Ready = bool(run.matlab_done and run.matlab_status == 0)
            OutputFile = None
            if run.matlab_done and run.matlab_status != 0:
                Status = "MATLAB failed with status %s on this iteration." % run.matlab_status
            elif run.matlab_done:
                Status = "MATLAB completed. Multi-run controller is advancing."
            else:
                Status = "Running MATLAB for iteration %d of %d (%d s)..." % (
                    int(state.get("index", 0)) + 1,
                    len(state.get("iterations", [])), run.elapsed)
        elif state.get("status") == "complete":
            Status = "Multi-run complete."
        elif state.get("status") == "error":
            Status = state.get("error") or "Multi-run stopped after an error."
        else:
            Status = "Waiting for the multi-run controller to start MATLAB."
        Status = note + Status

    else:
        # Original single-run behaviour.
        if Run and not was_on:
            if run is not None and run.running:
                note = "Already running (see its window); close it or press ENTER there first. "
            else:
                if not RunScript:
                    raise ValueError("RunScript is empty - give the full path to run_matlab.py.")
                if not MatlabFile:
                    raise ValueError("MatlabFile is empty - has the Transfer block finished?")
                capstone = str(CapstoneFolder) if CapstoneFolder else str(Repo)
                import gh_matlab_run
                importlib.reload(gh_matlab_run)
                gh_matlab_run.update_script_settings(
                    str(RunScript), capstone, str(MatlabFile))
                run = gh_bridge.ScriptRun(
                    str(RunScript), str(PythonExe) if PythonExe else "python",
                    str(MatlabFile), on_change=_recompute)
                sc.sticky[key] = run

        if run is not None and not hasattr(run, "matlab_done"):
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
except Exception as error:
    OutputFile, Ready = None, False
    Status = "ERROR: %s" % error
    try:
        if multirun is not None:
            multirun.finish_iteration(1)
            _recompute()
    except Exception:
        pass
    try:
        ghenv.Component.AddRuntimeMessage(gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
    except Exception:
        pass
