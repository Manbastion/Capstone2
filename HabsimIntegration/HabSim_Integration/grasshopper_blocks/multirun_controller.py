#! python 3
"""MULTIRUN CONTROLLER

INPUTS
  Repo       str   item
  Names      str   list
  Values     no hint TREE
  Names_1    str   list
  Values_1   no hint TREE
  ...
  Names_10   str   list
  Values_10  no hint TREE
  EntwinedNames  no hint TREE
  EntwinedValues no hint TREE
  PythonExe  str   item
  Open       bool  item
  Stop       bool  item
  SavePath   str   item  optional JSON file path or folder

OUTPUTS
  Trigger    bool  item
  Iteration  int   item
  Status     str
"""

import os
import sys
import time
import threading
import System
import Rhino
import Grasshopper as gh
import scriptcontext as sc

Trigger, Iteration, Status = False, 0, "Idle. Press Open to configure a multi-run."
comp = ghenv.Component
key = "HabSimMultiRun_" + str(comp.InstanceGuid)

Trigger = False


def _expire_on_ui():
    try:
        Rhino.RhinoApp.InvokeOnUiThread(
            System.Action(lambda: comp.ExpireSolution(True))
        )
    except Exception:
        pass


def _schedule_next():
    try:
        doc = comp.OnPingDocument()
        if doc is not None:
            delegate = gh.Kernel.GH_Document.GH_ScheduleDelegate(
                lambda _doc: comp.ExpireSolution(False)
            )
            doc.ScheduleSolution(10, delegate)
    except Exception:
        pass


def _watch_gui_start(state_path):
    deadline = time.time() + 7200
    while time.time() < deadline:
        state = multirun.load_state(state_path)

        if state and state.get("status") == "queued":
            _expire_on_ui()
            return

        if state and state.get("status") in (
            "complete", "error", "cancelled"
        ):
            return

        time.sleep(0.4)


def _input_connected(input_name):
    """Check whether a named Grasshopper input has a wire."""
    for param in comp.Params.Input:
        if param.NickName == input_name or param.Name == input_name:
            return param.SourceCount > 0
    return False

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

    # Stop button
    if Stop and not was_stop:
        if multirun.request_stop():
            Status = (
                "Stop requested. The current MATLAB iteration will finish, "
                "then the batch will stop."
            )

    # Open button
    if Open and not was_open:

        # Read the baseline variables.
        plain, skipped = gh_bridge.plain_pairs(Names, Values)

        if skipped:
            raise ValueError(
                "Some connected baseline variables cannot be used: %s"
                % "; ".join(skipped)
            )

        if not plain:
            raise ValueError(
                "Connect at least one variable through Names and Values."
            )

        # Read optional Entwine inputs.
        entwined_names_connected = _input_connected("EntwinedNames")
        entwined_values_connected = _input_connected("EntwinedValues")

        if entwined_names_connected != entwined_values_connected:
            raise ValueError(
                "EntwinedNames and EntwinedValues must both be connected."
            )

        iteration_overrides = []

        if entwined_names_connected:
            entwined_names = globals().get("EntwinedNames")
            entwined_values = globals().get("EntwinedValues")

            import multirun_entwine
            importlib.reload(multirun_entwine)
            iteration_overrides = multirun_entwine.entwine_iteration_overrides(
                entwined_names,
                entwined_values,
                plain,
                gh_bridge.plain_pairs
            )

        # Read optional per-iteration variable pairs.
        for i in range(1, 11):
            names_input = "Names_%d" % i
            values_input = "Values_%d" % i

            names_connected = _input_connected(names_input)
            values_connected = _input_connected(values_input)

            # Neither input connected: no additional overrides.
            if not names_connected and not values_connected:
                continue

            # Both inputs must be connected.
            if names_connected != values_connected:
                raise ValueError(
                    "%s and %s must both be connected."
                    % (names_input, values_input)
                )

            names_data = globals().get(names_input)
            values_data = globals().get(values_input)

            pairs, pair_skipped = gh_bridge.plain_pairs(
                names_data, values_data
            )

            if pair_skipped:
                raise ValueError(
                    "Invalid variables in %s / %s: %s"
                    % (names_input, values_input, "; ".join(pair_skipped))
                )

            if not pairs:
                raise ValueError(
                    "%s and %s are connected, but contain no valid variables."
                    % (names_input, values_input)
                )

            unknown = [
                name for name in pairs
                if name not in plain
            ]

            if unknown:
                raise ValueError(
                    "%s contains variables not present in the baseline "
                    "Names input: %s"
                    % (names_input, ", ".join(unknown))
                )

            # Expand the iteration list if necessary.
            while len(iteration_overrides) < i:
                iteration_overrides.append({})

            # Merge with Entwine overrides if both methods are used.
            existing = iteration_overrides[i - 1]

            duplicates = [
                name for name in pairs
                if name in existing
            ]

            if duplicates:
                raise ValueError(
                    "%s duplicates variables already supplied for "
                    "iteration %d: %s"
                    % (names_input, i, ", ".join(duplicates))
                )

            existing.update(pairs)

        # Remove unused trailing slots, while preserving gaps.
        while iteration_overrides and not iteration_overrides[-1]:
            iteration_overrides.pop()
        multirun.launch_gui(
            list(plain.keys()),
            list(plain.values()),
            str(PythonExe) if PythonExe else "python",
            iteration_overrides=iteration_overrides,
            save_path=str(SavePath) if SavePath else None
        )

        watch_key = key + "_watching"
        sc.sticky[watch_key] = True

        thread = threading.Thread(
            target=_watch_gui_start,
            args=(multirun.STATE_PATH,),
            name="multirun-gui-watch"
        )
        thread.daemon = True
        thread.start()

        Status = (
            "Multi-run editor opened. Enter the values and click "
            "Run iterations."
        )

    sc.sticky["HabSimMultiRunController"] = comp

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

                    Status = state["error"]

                else:
                    Trigger = True
                    from datetime import datetime
                    state["iteration_started_at"] = datetime.now().isoformat(timespec="seconds")

                    Status = "Starting iteration %d of %d." % (
                        index + 1, total
                    )

                    state["phase"] = "waiting"
                    state["pulse_off_done"] = False
                    multirun.save_state(state)

                    _schedule_next()

        elif status == "complete":
            Status = (
                "Complete. Successfully ran %d iteration(s)." % total
            )
            Iteration = total

        elif status in ("error", "cancelled"):
            Status = state.get("error") or (
                "Multi-run %s." % status
            )

        else:
            Status = "Multi-run is %s." % status

except Exception as error:
    Status = "ERROR: %s" % error

    try:
        ghenv.Component.AddRuntimeMessage(
            gh.Kernel.GH_RuntimeMessageLevel.Error,
            Status
        )
    except Exception:
        pass