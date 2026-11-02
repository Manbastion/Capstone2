"""Run a prepared model and publish a fresh export, then send completion alerts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from grasshopper_components.matlab_runner import _matlab_string, _resolve_executable, _validate_workspace
from habsim_notifications import notify_completion, settings_path
from habsim_runtime import external_environment, find_matlab


def export_source(script, destination, save_type):
    """All helper variables live outside the model's base workspace."""
    source = """function habsim_prototype_job()
evalin('base', 'clearvars');
evalin('base', RUN_EXPRESSION);
names = evalin('base', 'who');
results = struct();
for k = 1:numel(names)
    results.(names{k}) = evalin('base', names{k});
end
EXPORT_BODY
end
"""
    if save_type == "csv":
        export = "writetable(struct2table(results), EXPORT_PATH);"
    else:
        export = """fid = fopen(EXPORT_PATH, 'w', 'n', 'UTF-8');
if fid < 0
    error('HabSim:WriteFailed', 'Cannot write the export.');
end
closeFile = onCleanup(@() fclose(fid));
"""
        if save_type == "json":
            export += "fprintf(fid, '%s', jsonencode(results));"
        else:
            export += """for k = 1:numel(names)
    fprintf(fid, '%s = %s\\n', names{k}, mat2str(results.(names{k})));
end"""
    return source.replace("RUN_EXPRESSION", _matlab_string("run({})".format(_matlab_string(script)))).replace(
        "EXPORT_BODY", export.replace("EXPORT_PATH", _matlab_string(destination)))


def _matlab_executable():
    override = os.environ.get("HABSIM_MATLAB_EXE")
    if override:
        return _resolve_executable(override)
    path = settings_path().with_name("client_settings.json")
    if path.is_file():
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("matlab", "")
        except (OSError, ValueError, AttributeError):
            value = ""
        if value:
            return _resolve_executable(value)
    return _resolve_executable(find_matlab() or "matlab")


def full_run(output_file, save_type, matlab_exe=None, notify=True):
    started = time.monotonic()
    success = False
    count = None
    try:
        script = Path(output_file).expanduser().resolve()
        save_type = str(save_type).lower()
        if save_type not in ("json", "csv", "txt"):
            raise ValueError("SaveType must be json, csv or txt.")
        if not script.is_file() or script.suffix.lower() != ".m":
            raise ValueError("Choose an existing MATLAB .m script.")
        if script.with_suffix(".p").exists():
            raise ValueError("A same-name .p file would override this .m script.")
        executable = _resolve_executable(matlab_exe) if matlab_exe else _matlab_executable()
        # Keep the log and wrapper for diagnosis. Each attempt gets a new folder.
        folder = Path(tempfile.mkdtemp(prefix="habsim_run_", dir=str(script.parent)))
        exported = folder / ("matlab_output_variables." + save_type)
        (folder / "habsim_prototype_job.m").write_text(
            export_source(script, exported, save_type), encoding="utf-8")
        command = [executable] + (["-wait"] if os.name == "nt" else [])
        command += ["-sd", str(script.parent), "-batch",
                    "addpath({}); habsim_prototype_job".format(_matlab_string(folder))]
        print("MATLAB running. Log:", folder / "matlab.log", flush=True)
        with (folder / "matlab.log").open("wb") as log:
            subprocess.run(command, cwd=str(script.parent), env=external_environment(),
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if not exported.is_file():
            raise ValueError("MATLAB exited without exporting results. See " + str(folder / "matlab.log"))
        if save_type == "json":
            count = len(_validate_workspace(exported))
        destination = script.parent / exported.name
        # Only a successful, fresh export replaces the previous result.
        os.replace(exported, destination)
        success = True
        print("Done. Output:", destination, flush=True)
        return str(destination)
    finally:
        if notify:
            try:
                receipt = notify_completion(success=success, elapsed_seconds=time.monotonic() - started,
                                            variable_count=count if success else None)
                receipt.wait(45)  # CLI must not exit while daemon delivery threads are still working.
                print("Notifications:", receipt.result["status"], flush=True)
            except Exception:
                # Alert failure must never turn a good calculation into a bad one.
                pass
