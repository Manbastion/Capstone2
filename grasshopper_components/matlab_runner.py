"""Non-blocking MATLAB batch execution; no Rhino, Tkinter or Engine dependency.

Each job owns a new folder. Result paths become available only after both a
successful process exit and validated, freshly exported numeric results.
"""
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

# This module is loaded by path from Rhino, whose sys.path need not contain Repo.
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from habsim_notifications import notify_completion


def _path(value):
    if value is None or not str(value).strip():
        raise ValueError("Supply a full path.")
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        raise ValueError("Use full, absolute paths.")
    return path.resolve()


def _matlab_string(value):
    text = str(value).replace("\\", "/")
    if any(c in text for c in ("\r", "\n", "\0")):
        raise ValueError("Paths cannot contain line breaks or NUL characters.")
    return "'" + text.replace("'", "''") + "'"


def _output_names(names):
    names = [str(n).strip() for n in (names or [])]
    if not names or len(set(names)) != len(names):
        raise ValueError("OutputNames must be a non-empty list of unique variable names.")
    if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", n) for n in names):
        raise ValueError("OutputNames must contain simple MATLAB variable names, not expressions.")
    return names


def request_signature(matlab_exe, script_file, names, output_folder, timeout_seconds):
    """A changed script/input setting invalidates the previous result on canvas."""
    script = _path(script_file)
    request = {
        "matlab_exe": str(matlab_exe), "script_file": str(script),
        "output_names": _output_names(names), "output_folder": str(_path(output_folder)),
        "timeout_seconds": float(timeout_seconds),
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    }
    return json.dumps(request, sort_keys=True)


def wrapper_source(script, names, directory, job_id):
    """Keep export variables in a function workspace, isolated from user script."""
    run_expression = "run({})".format(_matlab_string(script))
    names_literal = "{" + ", ".join(_matlab_string(n) for n in names) + "}"
    return """function capstone_job_entry()
% Generated adapter. The selected user script is executed in the base workspace.
% This wrapper does not append export code to the original script.
evalin('base', 'clearvars');
evalin('base', RUN_EXPRESSION);
names = OUTPUT_NAMES;
results = struct();
for k = 1:numel(names)
    name = names{k};
    if ~isvarname(name) || ~evalin('base', ['exist(''' name ''',''var'')'])
        error('Capstone:MissingVariable', 'Requested output is missing: %s', name);
    end
    value = evalin('base', name);
    if ~isnumeric(value) || ~isreal(value) || ~(isvector(value) || isempty(value)) || any(~isfinite(value(:)))
        error('Capstone:UnsupportedOutput', 'Output %s must be a finite real numeric scalar or vector.', name);
    end
    results.(name) = reshape(double(full(value)), 1, []);
end
fid = fopen(RESULTS_PATH, 'w', 'n', 'UTF-8');
if fid < 0
    error('Capstone:WriteFailed', 'Cannot create results JSON.');
end
closeFile = onCleanup(@() fclose(fid));
fprintf(fid, '%s', jsonencode(results));
clear closeFile;
fid = fopen(COMPLETE_PATH, 'w');
if fid < 0
    error('Capstone:WriteFailed', 'Cannot create completion marker.');
end
closeFile = onCleanup(@() fclose(fid));
fprintf(fid, '%s', JOB_ID);
clear closeFile;
end
""".replace("RUN_EXPRESSION", _matlab_string(run_expression)).replace(
        "OUTPUT_NAMES", names_literal).replace(
        "RESULTS_PATH", _matlab_string(directory / "results.json")).replace(
        "COMPLETE_PATH", _matlab_string(directory / "completed.txt")).replace(
        "JOB_ID", _matlab_string(job_id))


def _resolve_executable(value):
    value = str(value or "matlab").strip()
    expanded = Path(value).expanduser()
    if expanded.is_absolute():
        if not expanded.is_file():
            raise ValueError("MATLAB executable not found: " + str(expanded))
        return str(expanded)
    executable = shutil.which(value)
    if not executable:
        raise ValueError("MATLAB is not on PATH. Set MatlabExe to its full executable path.")
    return executable


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate result key: " + key)
        result[key] = value
    return result


def _validate_results(path, names):
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json)
    if not isinstance(data, dict) or set(data) != set(names):
        raise ValueError("Results must contain exactly the requested output variables.")
    for name, value in data.items():
        values = value if isinstance(value, list) else [value]
        for item in values:
            if isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item):
                raise ValueError("Output {} must contain finite real numbers in a flat list.".format(name))
    return data


def _write_csv(data, path, names):
    columns = [data[name] if isinstance(data[name], list) else [data[name]] for name in names]
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(names)
    for i in range(max((len(column) for column in columns), default=0)):
        writer.writerow([column[i] if i < len(column) else "" for column in columns])
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(stream.getvalue())


def _stop_process(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        # Stop only this job's process tree; never terminate other MATLAB sessions.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=10, creationflags=subprocess.CREATE_NO_WINDOW, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=2)


def _finish(job, state, message, return_code=None):
    snapshot = {
        "state": state, "message": message, "return_code": return_code,
        "elapsed_seconds": round(time.monotonic() - job["started"], 2),
        "log_file": str(job["directory"] / "matlab.log"),
        "job_directory": str(job["directory"]),
        "results_file": str(job["directory"] / "results.json") if state == "Succeeded" else "",
        "csv_file": str(job["directory"] / "results.csv") if state == "Succeeded" else "",
    }
    with job["lock"]:
        # A terminal job cannot finish twice, even if a cancellation races exit.
        if job.get("snapshot", {}).get("state") in ("Succeeded", "Failed", "Timed out", "Cancelled"):
            return
        job["snapshot"] = snapshot
    try:
        (job["directory"] / "status.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    except OSError:
        # Failure to persist a status note must not change a completed process.
        pass
    if job.get("notify", True) and state in ("Succeeded", "Failed", "Timed out"):
        try:
            job["notification"] = notify_completion(
                success=state == "Succeeded", elapsed_seconds=snapshot["elapsed_seconds"],
                variable_count=len(job["names"]) if state == "Succeeded" else None)
        except Exception:
            # Even an unavailable notifier must not alter exported results/status.
            pass


def _monitor(job):
    process = job["process"]
    try:
        while process.poll() is None:
            if job["cancel"].is_set():
                _stop_process(process)
                _finish(job, "Cancelled", "This MATLAB job was cancelled.", process.poll())
                return
            if time.monotonic() - job["started"] > job["timeout"]:
                _stop_process(process)
                _finish(job, "Timed out", "MATLAB exceeded TimeoutSeconds; see the log.", process.poll())
                return
            job["cancel"].wait(0.1)
        code = process.returncode
        if job["cancel"].is_set():
            _finish(job, "Cancelled", "This MATLAB job was cancelled.", code)
            return
        if code != 0:
            _finish(job, "Failed", "MATLAB exited with code {}; see LogFile.".format(code), code)
            return
        marker = job["directory"] / "completed.txt"
        if not marker.is_file() or marker.read_text().strip() != job["job_id"]:
            raise ValueError("MATLAB exited without the expected export completion marker.")
        result = _validate_results(job["directory"] / "results.json", job["names"])
        _write_csv(result, job["directory"] / "results.csv", job["names"])
        _finish(job, "Succeeded", "MATLAB finished; validated JSON and CSV are ready.", code)
    except Exception as error:
        try:
            _stop_process(process)
        except Exception:
            pass
        _finish(job, "Failed", str(error), process.poll())


def start_job(matlab_exe, script_file, names, output_folder, timeout_seconds=600, notify=True):
    started = time.monotonic()
    try:
        return _start_job(matlab_exe, script_file, names, output_folder, timeout_seconds, notify)
    except Exception:
        if notify:
            try:
                notify_completion(success=False, elapsed_seconds=time.monotonic() - started)
            except Exception:
                pass
        raise


def _start_job(matlab_exe, script_file, names, output_folder, timeout_seconds, notify):
    executable = _resolve_executable(matlab_exe)
    script, directory_root = _path(script_file), _path(output_folder)
    names = _output_names(names)
    if not script.is_file() or script.suffix.lower() != ".m":
        raise ValueError("ScriptFile must point to an existing .m script.")
    if script.with_suffix(".p").exists():
        raise ValueError("A same-name .p file would override this .m script in MATLAB; choose an unambiguous script.")
    if not directory_root.is_dir():
        raise ValueError("Create OutputFolder before running MATLAB.")
    timeout = float(timeout_seconds)
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("TimeoutSeconds must be a positive finite number.")
    signature = request_signature(matlab_exe, script, names, directory_root, timeout)
    # Validate paths before creating the job folder.
    _matlab_string(script)
    _matlab_string(directory_root)
    job_id = uuid.uuid4().hex
    directory = Path(tempfile.mkdtemp(prefix="capstone_run_", dir=str(directory_root)))
    (directory / "capstone_job_entry.m").write_text(
        wrapper_source(script, names, directory, job_id), encoding="utf-8")
    request = json.loads(signature)
    request.update(job_id=job_id, executable=executable)
    (directory / "request.json").write_text(json.dumps(request, indent=2), encoding="utf-8")
    command = [executable]
    if os.name == "nt":
        command.append("-wait")
    command += ["-sd", str(script.parent), "-batch",
                "addpath({}); capstone_job_entry".format(_matlab_string(directory))]
    kwargs = {"cwd": str(directory), "stdin": subprocess.DEVNULL,
              "stderr": subprocess.STDOUT, "shell": False}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    with (directory / "matlab.log").open("wb") as logfile:
        process = subprocess.Popen(command, stdout=logfile, **kwargs)
    job = {"process": process, "directory": directory, "names": names,
           "job_id": job_id, "signature": signature, "started": time.monotonic(),
           "timeout": timeout, "cancel": threading.Event(), "lock": threading.Lock(),
           "notify": bool(notify), "notification": None}
    _finish(job, "Running", "MATLAB is running. Press Check to refresh the canvas.")
    worker = threading.Thread(target=_monitor, args=(job,), daemon=True, name="CapstoneMatlabJob")
    job["worker"] = worker
    worker.start()
    return job


def job_status(job):
    with job["lock"]:
        result = dict(job["snapshot"])
    if result["state"] == "Running":
        result["elapsed_seconds"] = round(time.monotonic() - job["started"], 2)
    receipt = job.get("notification")
    result["notification_status"] = receipt.result["status"] if receipt is not None else "not requested"
    return result


def cancel_job(job):
    job["cancel"].set()
