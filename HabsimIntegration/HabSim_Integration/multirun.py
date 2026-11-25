"""Shared state and helpers for sequential Grasshopper -> MATLAB iterations.

Compatible with Rhino 8's embedded Python 3.9+.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime

try:
    import gh_bridge
    WORK_DIR = gh_bridge.WORK_DIR
except Exception:
    WORK_DIR = os.path.join(os.path.expanduser("~"), "HabSim")
    os.makedirs(WORK_DIR, exist_ok=True)

STATE_PATH = os.path.join(WORK_DIR, "multirun_state.json")
INITIAL_PATH = os.path.join(WORK_DIR, "multirun_initial.json")
GUI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "multirun_gui.py")
HISTORY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.json")


def _atomic_json(path, data):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix="multirun_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        # Grasshopper components and the editor can access this state file
        # close together. Windows may briefly deny replacement while another
        # process is closing a handle, so retry transient sharing/access errors.
        last_error = None
        for attempt in range(20):
            try:
                os.replace(temp_path, path)
                last_error = None
                break
            except PermissionError as error:
                last_error = error
                time.sleep(0.1)
        if last_error is not None:
            raise last_error
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


def load_state(path=STATE_PATH):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def save_state(data, path=STATE_PATH):
    _atomic_json(path, data)


def launch_gui(
    names,
    values,
    python_exe="python",
    state_path=STATE_PATH,
    iteration_overrides=None,
    save_path=None
):
    """Launch the multi-run editor with optional per-iteration overrides."""

    if len(names) != len(values):
        raise ValueError(
            "Names and Values must have the same number of entries."
        )

    initial = {
        str(name): value
        for name, value in zip(names, values)
    }

    # Store the numbered inputs as per-iteration overrides.
    overrides = iteration_overrides or []

    for i, row in enumerate(overrides):
        if not isinstance(row, dict):
            raise ValueError(
                "Iteration %d overrides must be a variable/value dictionary."
                % (i + 1)
            )

        unknown = [name for name in row if name not in initial]

        if unknown:
            raise ValueError(
                "Iteration %d contains unknown variables: %s"
                % (i + 1, ", ".join(unknown))
            )

    _atomic_json(
        INITIAL_PATH,
        {
            "variables": initial,
            "iteration_overrides": overrides,
            "save_path": str(save_path).strip() if save_path else ""
        }
    )

    try:
        os.remove(state_path)
    except OSError:
        pass

    env = dict(os.environ)

    for key in list(env):
        if key.upper() in (
            "PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
            "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
            "__PYVENV_LAUNCHER__", "VIRTUAL_ENV"
        ):
            env.pop(key)

    log_path = os.path.join(
        WORK_DIR, "multirun_gui_error.log"
    )

    try:
        with open(log_path, "w", encoding="utf-8") as log:
            subprocess.Popen(
                [
                    python_exe or "python",
                    GUI_PATH,
                    INITIAL_PATH,
                    state_path
                ],
                cwd=os.path.dirname(GUI_PATH),
                stdout=log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                ),
                env=env
            )

    except OSError as error:
        raise RuntimeError(
            "Could not start the multi-run GUI: %s" % error
        )


def current_overrides(state=None, path=STATE_PATH):
    state = state if state is not None else load_state(path)
    if not state or state.get("status") != "running":
        return None
    iterations = state.get("iterations") or []
    index = int(state.get("index", 0))
    if index < 0 or index >= len(iterations):
        return None
    values = iterations[index]
    if not isinstance(values, dict):
        raise ValueError("Multi-run iteration %d is not a variable/value object." % (index + 1))
    return values


def _read_matlab_output_folder(state):
    marker = state.get("matlab_output_marker")
    if not marker:
        return ""
    try:
        with open(marker, "r", encoding="utf-8") as stream:
            folder = stream.read().strip()
        return folder if folder and os.path.isdir(folder) else ""
    except OSError:
        return ""


def _save_batch_record(state):
    """Append a batch record to shared history and save its standalone JSON."""
    if state.get("history_record_saved"):
        return
    records = state.setdefault("iteration_records", [])
    batch = {
        "id": state.get("batch_id") or uuid.uuid4().hex,
        "record_type": "multirun",
        "timestamp": state.get("started_at") or datetime.now().isoformat(timespec="seconds"),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "status": state.get("status", "unknown"),
        "total_iterations": len(state.get("iterations", [])),
        "baseline": state.get("baseline", {}),
        "iterations": records,
        "error": state.get("error", ""),
    }
    # Explicit Grasshopper path takes precedence; otherwise use MATLAB's
    # discovered output folder, then the existing history directory.
    target = (state.get("save_path") or "").strip()
    if not target:
        target = _read_matlab_output_folder(state)
        if target:
            target = os.path.join(target, "multirun_history.json")
    if not target:
        target = HISTORY_PATH
    elif os.path.isdir(target):
        target = os.path.join(os.path.abspath(target), "multirun_history.json")
    else:
        target = os.path.abspath(target)
        if not target.lower().endswith(".json"):
            target += ".json"

    # A custom path receives a standalone batch JSON. The default history
    # destination is already the shared list and must not be overwritten.
    if os.path.abspath(target) != os.path.abspath(HISTORY_PATH):
        _atomic_json(target, batch)

    # Merge into the existing transfer history without breaking older records.
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as stream:
            history = json.load(stream)
        if not isinstance(history, list):
            history = []
    except (OSError, ValueError):
        history = []
    history.insert(0, batch)
    _atomic_json(HISTORY_PATH, history[:500])
    state["history_record_saved"] = True
    state["history_json_path"] = target


def finish_iteration(return_code, path=STATE_PATH):
    """Record MATLAB completion and advance to the next iteration."""
    state = load_state(path)

    if not state or state.get("status") != "running":
        return False

    if state.get("iteration_done"):
        return False

    state["iteration_done"] = True
    state["last_return_code"] = int(return_code)
    state["last_finished"] = time.time()
    index = int(state.get("index", 0))
    rows = state.get("iterations") or []
    current = rows[index] if 0 <= index < len(rows) else {}
    baseline = state.get("baseline") or {}
    changed = {name: value for name, value in current.items()
               if name not in baseline or value != baseline.get(name)}
    state.setdefault("iteration_records", []).append({
        "iteration": index + 1,
        "started_at": state.get("iteration_started_at", ""),
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "return_code": int(return_code),
        "status": "success" if int(return_code) == 0 else "failed",
        "values": dict(current),
        "changed_variables": changed,
        "matlab_output_folder": _read_matlab_output_folder(state),
    })

    # Stop the batch if MATLAB failed.
    if int(return_code) != 0:
        state["status"] = "error"
        state["error"] = "MATLAB returned status %s on iteration %d." % (
            return_code, int(state.get("index", 0)) + 1)
        save_state(state, path)
        try:
            _save_batch_record(state)
            save_state(state, path)
        except Exception as error:
            state["history_save_error"] = str(error)
            save_state(state, path)
        _notify_batch_terminal(state)
        return True

    # Stop after the current iteration if Stop was pressed.
    if state.get("stop_requested"):
        state["status"] = "cancelled"
        state["error"] = "Multi-run stopped after the current iteration."
        save_state(state, path)
        try:
            _save_batch_record(state)
            save_state(state, path)
        except Exception as error:
            state["history_save_error"] = str(error)
            save_state(state, path)
        return True

    # Advance to the next iteration.
    next_index = int(state.get("index", 0)) + 1
    iterations = state.get("iterations") or []

    if next_index >= len(iterations):
        state["status"] = "complete"
    else:
        state["index"] = next_index
        state["phase"] = "pulse_on"
        state["iteration_done"] = False
        state["pulse_off_done"] = False

    save_state(state, path)
    if state.get("status") in ("complete", "error", "cancelled"):
        try:
            _save_batch_record(state)
            save_state(state, path)
        except Exception as error:
            state["history_save_error"] = str(error)
            save_state(state, path)
        _notify_batch_terminal(state)
    return True


def _notify_batch_terminal(state):
    """Send one whole-loop alert on successful completion or failure.

    The notification module filters this by the user's saved scope, so
    per-run mode remains handled by the MATLAB runner decorator.
    """
    try:
        from habsim_completion import notify_batch
        notify_batch(state)
    except Exception:
        # Notifications must never interrupt or fail a simulation batch.
        pass


def request_stop(path=STATE_PATH):
    """Request cancellation. An active MATLAB iteration is allowed to finish."""
    state = load_state(path)
    if not state or state.get("status") not in ("queued", "running"):
        return False
    if state.get("status") == "queued":
        state["status"] = "cancelled"
        state["error"] = "Stopped by user before the first iteration started."
        try:
            _save_batch_record(state)
        except Exception as error:
            state["history_save_error"] = str(error)
    else:
        state["stop_requested"] = True
        state["error"] = "Stop requested. Waiting for the current MATLAB iteration to finish."
    save_state(state, path)
    return True


def fail_transfer(error, path=STATE_PATH):
    state = load_state(path)
    if not state or state.get("status") != "running":
        return
    state["status"] = "error"
    state["error"] = "Transfer failed on iteration %d: %s" % (
        int(state.get("index", 0)) + 1, error)
    save_state(state, path)
    try:
        _save_batch_record(state)
        save_state(state, path)
    except Exception as save_error:
        state["history_save_error"] = str(save_error)
        save_state(state, path)
    _notify_batch_terminal(state)
