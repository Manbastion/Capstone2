#! python 3
"""RUN MATLAB
When the multi-run controller is active, this component waits for the MATLAB
completion marker, reports the result to the controller,
and automatically closes each run_matlab.py console before the next iteration.

INPUTS
  Repo        str   item  - project folder containing the helper modules
  RunScript   str   item  - full path to run_matlab.py
  MatlabFile  str   item  - MATLAB script to execute
  MATLABRoot  str   item  - MATLAB installation root (the value returned by matlabroot)
  PythonExe   str   item  - Python executable. Empty = "python".
  Trigger     bool  item  - trigger from Transfer Variables MATLAB or Transfer Variables CSV

OUTPUTS
  Ready       bool  - True once MATLAB has completed successfully
  Status      str
"""
import sys
import os
import threading
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

comp = ghenv.Component
key = "HabSimRunScript_" + str(comp.InstanceGuid)
Ready, Status = False, "Idle. Waiting for Trigger."
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
        controller = sc.sticky.get("HabSimMultiRunController")
        if controller is not None:
            controller.ExpireSolution(True)
        else:
            comp.ExpireSolution(True)

    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(on_ui_thread))
    except Exception:
        pass

try:
    if not Repo or not os.path.isdir(str(Repo)):
        raise ValueError("Repo must be the project folder containing the Python files.")
    if Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib
    import Capstone2.old.HabSim_Integration_Multirun_History_AutoDetect.HabSim_Integration.gh_bridge as gh_bridge
    importlib.reload(gh_bridge)

    state = None
    try:
        import Capstone2.old.HabSim_Integration_Multirun_History_AutoDetect.HabSim_Integration.multirun as multirun
        importlib.reload(multirun)
        state = multirun.load_state()
    except Exception:
        multirun = None

    run = sc.sticky.get(key)
    was_on = sc.sticky.get(key + "_trigger", False)
    # Once a batch has ended, a fresh trigger can start
    # an ordinary single run. Multi-run controller itself is low after completion/error.
    multi_session = bool(state and state.get("status") == "running") or bool(
        state and state.get("status") in ("error", "complete") and not (Trigger and not was_on))
    multi_active = bool(state and state.get("status") == "running")
    sc.sticky[key + "_trigger"] = bool(Trigger)

    if multi_session:
        if multi_active and Trigger and not was_on:
            if run is not None and getattr(run, "running", False):
                note = "Already running. Waiting for the current MATLAB run. "
            else:
                if not RunScript:
                    raise ValueError("RunScript is empty. Connect the full path to run_matlab.py.")
                if not MatlabFile:
                    raise ValueError("MatlabFile is empty. Connect the MATLAB script path.")
                if not MATLABRoot:
                    raise ValueError("MATLABRoot is empty. Connect the MATLAB installation root.")
                import Capstone2.old.HabSim_Integration_Multirun_History_AutoDetect.HabSim_Integration.gh_matlab_run as gh_matlab_run
                importlib.reload(gh_matlab_run)
                gh_matlab_run.update_script_settings(
                    str(RunScript), str(MatlabFile), str(MATLABRoot))
                if state is not None:
                    state["matlab_output_marker"] = os.path.join(
                        os.path.dirname(os.path.abspath(str(MatlabFile))),
                        "matlab_output_folder.txt")
                    multirun.save_state(state)
                holder = {
                    "run": None,
                    "completion_reported": False,
                    "lock": threading.Lock()
                }

                def _multi_changed():
                    # ScriptRun's watcher runs on a background thread. The
                    # callback is attached after construction, then checked
                    # immediately to cover a run that finished very quickly.
                    with holder["lock"]:
                        current = holder.get("run")
                        if (current is None or not current.matlab_done
                                or holder["completion_reported"]):
                            return
                        holder["completion_reported"] = True
                        return_code = current.matlab_status

                    if multirun.finish_iteration(return_code):
                        # One controller wake-up is enough to recompute the
                        # downstream chain; two independent expirations can
                        # race the next Run pulse.
                        _wake_controller()

                run = gh_matlab_run.ScriptRun(
                    str(RunScript),
                    str(PythonExe) if PythonExe else "python",
                    str(MatlabFile),
                    on_change=None
                )
                holder["run"] = run
                run.on_change = _multi_changed
                sc.sticky[key] = run
                if run.matlab_done:
                    _multi_changed()

        if run is not None and hasattr(run, "matlab_done"):
            Ready = bool(run.matlab_done and run.matlab_status == 0)
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
        # Single-run behaviour.
        if Trigger and not was_on:
            if run is not None and run.running:
                note = "Already running. Waiting for the current MATLAB run. "
            else:
                if not RunScript:
                    raise ValueError("RunScript is empty. Connect the full path to run_matlab.py.")
                if not MatlabFile:
                    raise ValueError("MatlabFile is empty. Connect the MATLAB script path.")
                if not MATLABRoot:
                    raise ValueError("MATLABRoot is empty. Connect the MATLAB installation root.")
                import Capstone2.old.HabSim_Integration_Multirun_History_AutoDetect.HabSim_Integration.gh_matlab_run as gh_matlab_run
                importlib.reload(gh_matlab_run)
                gh_matlab_run.update_script_settings(
                    str(RunScript), str(MatlabFile), str(MATLABRoot))
                # Normal single-run mode has no multi-run completion
                # callback or holder. Refresh this component when it finishes.
                run = gh_matlab_run.ScriptRun(
                    str(RunScript),
                    str(PythonExe) if PythonExe else "python",
                    str(MatlabFile),
                    on_change=_recompute
                )
                sc.sticky[key] = run

        if run is not None and hasattr(run, "matlab_done"):
            Ready = bool(run.matlab_done and run.matlab_status == 0)
            
            if run.matlab_done:
                if run.matlab_status == 0:
                    Status = "MATLAB completed successfully."
                else:
                    Status = "MATLAB failed with status %s." % run.matlab_status
            else:
                Status = "Running MATLAB (%d s so far)..." % run.elapsed

        Status = note + Status

except Exception as error:
    Ready = False
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
