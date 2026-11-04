#! python 3
"""BLOCK 0 - MULTI-RUN CONTROLLER
Place this before the existing Transfer Variables and Run MATLAB blocks.

INPUTS
  Repo       str   item  - project folder containing gh_bridge.py
  Names      str   list  - same variable names wired to Block 2
  Values     no hint TREE - same values wired to Block 2
  PythonExe  str   item  - Python with tkinter; empty = "python"
  Open       bool  item  - Button; opens the multi-run editor
  Stop       bool  item  - Button; stops after the current MATLAB iteration

OUTPUTS
  Run        bool  item  - wire to Block 2 Run only; Block 2 triggers Block 3
  Iteration  int   item  - current iteration number (1-based)
  Status     str   - progress / error message
  

The GUI writes iteration values to a shared state file. This block emits a
one-solution Run pulse for each iteration. Block 2 substitutes that iteration's
values; Block 3 starts MATLAB and signals this controller when the MATLAB
completion marker is written.
"""
import os
import sys
import time
import threading
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

Run, Iteration, Status = False, 0, "Idle. Press Open to configure a multi-run."
comp = ghenv.Component
key = "CapstoneMultiRun_" + str(comp.InstanceGuid)

Trigger = False

def _expire_on_ui():
    try:
        Rhino.RhinoApp.InvokeOnUiThread(System.Action(lambda: comp.ExpireSolution(True)))
    except Exception:
        pass


def _schedule_next():
    try:
        doc = comp.OnPingDocument()
        if doc is not None:
            delegate = gh.Kernel.GH_Document.GH_ScheduleDelegate(
                lambda _doc: comp.ExpireSolution(False))
            doc.ScheduleSolution(10, delegate)
    except Exception:
        # The next user-triggered solution will still pick up the saved state.
        pass


def _watch_gui_start(state_path):
    """Wake Grasshopper when the separate GUI writes its queued state."""
    deadline = time.time() + 7200
    while time.time() < deadline:
        state = multirun.load_state(state_path)
        if state and state.get("status") == "queued":
            _expire_on_ui()
            return
        if state and state.get("status") in ("complete", "error", "cancelled"):
            return
        time.sleep(0.4)


try:
    if Repo and Repo not in sys.path:
        sys.path.insert(0, str(Repo))
    import importlib
    import gh_bridge
    import multirun
    importlib.reload(gh_bridge)
    importlib.reload(multirun)

    was_open = sc.sticky.get(key + "_open", False)
    sc.sticky[key + "_open"] = bool(Open)
    was_stop = sc.sticky.get(key + "_stop", False)
    sc.sticky[key + "_stop"] = bool(Stop)
    if Stop and not was_stop:
        if multirun.request_stop():
            Status = "Stop requested. The current MATLAB iteration will finish, then the batch will stop."
    if Open and not was_open:
        plain, skipped = gh_bridge.plain_pairs(Names, Values)
        if skipped:
            raise ValueError("Some connected variables cannot be used: %s" % "; ".join(skipped))
        if not plain:
            raise ValueError("Connect at least one variable through Names and Values.")
        multirun.launch_gui(list(plain.keys()), list(plain.values()),
                            str(PythonExe) if PythonExe else "python")
        watch_key = key + "_watching"
        sc.sticky[watch_key] = True
        thread = threading.Thread(target=_watch_gui_start,
                                  args=(multirun.STATE_PATH,), name="capstone-multirun-gui-watch")
        thread.daemon = True
        thread.start()
        Status = "Multi-run editor opened. Enter the values and click Run iterations."

    sc.sticky["CapstoneMultiRunController"] = comp
    state = multirun.load_state()
    if state:
        status = state.get("status")
        index = int(state.get("index", 0))
        total = len(state.get("iterations", []))
        Iteration = min(index + 1, total) if total else 0

        if status == "queued":
            state["status"] = "running"
            state["phase"] = "pulse_on"
            state["iteration_done"] = False
            state["pulse_off_done"] = False
            multirun.save_state(state)
            status = "running"

        if status == "running":
            if state.get("phase") == "pulse_on":
                if state.get("stop_requested"):
                    state["status"] = "cancelled"
                    state["phase"] = "cancelled"
                    state["error"] = "Stopped before iteration started."
                    multirun.save_state(state)
                    Run = False
                    Status = state["error"]
                else:
                    # Emit the Run signal for this Grasshopper solution.
                    Run = True
                    Trigger = True
                    Status = "Starting iteration %d of %d." % (
                        index + 1, total
                    )

                    state["phase"] = "waiting"
                    state["pulse_off_done"] = False
                    multirun.save_state(state)

                    # Schedule a second solution to turn Run off.
                    _schedule_next()
        elif status == "complete":
            Run = False
            Status = "Complete. Successfully ran %d iteration(s)." % total
            Iteration = total
        elif status in ("error", "cancelled"):
            Run = False
            Status = state.get("error") or ("Multi-run %s." % status)
        else:
            Status = "Multi-run is %s." % status
except Exception as error:
    Run, Status = False, "ERROR: %s" % error
    try:
        ghenv.Component.AddRuntimeMessage(gh.Kernel.GH_RuntimeMessageLevel.Error, Status)
    except Exception:
        pass
