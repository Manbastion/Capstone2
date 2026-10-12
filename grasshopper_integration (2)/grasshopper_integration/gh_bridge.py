"""gh_bridge.py - glue between Grasshopper and your existing Capstone2 code.

Lives in the Capstone2 repo folder next to variable_transfer_v2.py.
Has NO Grasshopper/Rhino imports, and does NOT import tkinter, so it is safe
to import inside Rhino and can be tested from a normal terminal.
Written for Python 3.9 (Rhino 8's CPython) - no `match` statements.

How it fits together
--------------------
* The Grasshopper variables (Names/Values) are written to a small SOURCE file
  (grasshopper_variables.txt). The connected MATLAB .m file is the DESTINATION.
  That is exactly what the standalone GUI does with its two file pickers.
* The GUI block opens gui.py's window (see gh_gui.py) on those two files and
  saves its state (mode, selection, links, renames) to one JSON "config" file.
* The Transfer block re-writes the source file from the live GH values and
  applies the saved config, so the GUI choices are used on every run.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# Support the checked-in nested layout as well as the older flat installation.
for parent in Path(HERE).parents:
    if (parent / "variable_transfer_v2.py").is_file():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

from variable_transfer_v2 import transfer_data, valid_name, valid_value  # noqa: E402
from habsim_notifications import notify_completion  # noqa: E402

# Persistent folder (not %TEMP%, which Windows may clean up).
WORK_DIR = os.path.join(os.path.expanduser("~"), "CapstoneGH")
os.makedirs(WORK_DIR, exist_ok=True)

DEFAULT_CONFIG_PATH = os.path.join(WORK_DIR, "transfer_config.json")
SOURCE_FILE = os.path.join(WORK_DIR, "grasshopper_variables.txt")

MODE_TO_BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


# ----------------------------------------------------------------- helpers
def clean_pairs(names, values):
    """Pair up GH names/values. Skips pairs that aren't valid scalar numbers."""
    names = [str(n).strip() for n in (names or [])]
    values = [str(v).strip() for v in (values or [])]
    if len(names) != len(values):
        raise ValueError(
            "Names and Values must be the same length (got %d names, %d values)."
            % (len(names), len(values)))
    out, skipped = {}, []
    for n, v in zip(names, values):
        if valid_name(n) and valid_value(v):
            out[n] = v
        else:
            skipped.append(n or "<blank>")
    return out, skipped


def load_config(config_path):
    """Return the saved GUI state dict, or None if there isn't one."""
    if not config_path or not os.path.isfile(config_path):
        return None
    try:
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def compose_renames(old_renames, changes):
    """Keep track of renames made in the config window.

    old_renames: {gh_name: name_currently_in_source_file}
    changes:     the GUI's source_changes {name_in_source_file: {"name":..,"value":..}}
    Returns the updated {gh_name: current_name} (only entries that differ).
    """
    current_to_gh = {cur: gh for gh, cur in (old_renames or {}).items()}
    renames = dict(old_renames or {})
    for current, change in (changes or {}).items():
        gh_name = current_to_gh.get(current, current)
        new_name = str(change["name"]).strip()
        if new_name != gh_name:
            renames[gh_name] = new_name
        else:
            renames.pop(gh_name, None)
    return renames


def write_source_file(names, values, renames=None, path=SOURCE_FILE):
    """Write GH variables as 'name = value;' lines (the format read_variables parses).

    Applies any renames saved from the config window so saved links still match.
    Returns (pairs_written, skipped_names).
    """
    pairs, skipped = clean_pairs(names, values)
    renames = renames or {}
    final = {}
    for n, v in pairs.items():
        new = renames.get(n, n)
        if new in final:
            raise ValueError("Two Grasshopper variables map to the name %r." % new)
        final[new] = v
    with open(path, "w", encoding="utf-8") as f:
        for n, v in final.items():
            f.write("%s = %s;\n" % (n, v))
    return final, skipped


def _check_dest(dest_file):
    if not dest_file or not os.path.isfile(dest_file):
        raise ValueError("MATLAB file not found: %s" % dest_file)


def _same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


# --------------------------------------------------------------------- GUI
def launch_config_gui(names, values, dest_file, python_exe="python",
                      config_path=DEFAULT_CONFIG_PATH):
    """Open the full Transfer window in a separate process (does not block GH).

    Source = the live GH variables, destination = dest_file (the .m file).
    """
    _check_dest(dest_file)
    config = load_config(config_path) or {}
    final, _ = write_source_file(names, values, config.get("renames"))
    if not final:
        raise ValueError("No valid numeric GH variables to configure.")
    gui_script = os.path.join(HERE, "gh_gui.py")
    subprocess.Popen([python_exe, gui_script, SOURCE_FILE,
                      os.path.abspath(dest_file), config_path])
    return config_path


# ---------------------------------------------------------------- transfer
def transfer(names, values, dest_file, config_path=None):
    """GH variables -> MATLAB .m file. Returns (report_lines, skipped_names)."""
    _check_dest(dest_file)
    config = load_config(config_path)
    notes = []

    # A saved config only applies to the .m file it was made for.
    if config and config.get("destination") and not _same_file(
            config["destination"], dest_file):
        notes.append("note: saved config was made for a different MATLAB file - ignored")
        config = None

    renames = (config or {}).get("renames")
    final, skipped = write_source_file(names, values, renames)
    if not final:
        raise ValueError("No valid numeric GH variables were supplied.")

    if config and config.get("configured"):
        mode_name = config.get("mode", "All Variables")
        mode = MODE_TO_BACKEND.get(mode_name, "everything")
        selected = config.get("selected", [])
        mappings = config.get("mappings", {})
        if mode == "include" and not selected:
            raise ValueError("The saved config has no variables selected. "
                             "Open the GUI and save a configuration.")
        result = transfer_data(SOURCE_FILE, dest_file, mode, selected,
                               mappings=mappings)
    else:
        mode_name = "All Variables"
        selected = []
        # No saved config: overwrite same-name variables, ignore everything else.
        result = transfer_data(SOURCE_FILE, dest_file, "everything")
        notes.append("note: no saved GUI config - used same-name matching")

    # Same history log the standalone GUI writes (optional, never fatal).
    try:
        from history import record_transfer
        record_transfer(SOURCE_FILE, dest_file, mode_name, selected,
                        result["transferred"], result["changes"],
                        result["mappings"])
    except Exception as e:  # tkinter missing, read-only folder, ...
        notes.append("note: history not recorded (%s)" % e)

    lines = ["%s -> %s : %s -> %s" % (c["source"], d, c["before"], c["after"])
             for d, c in result["changes"].items()]
    if not lines:
        lines = ["(no values changed)"]
    for m in result["missing_in_destination"]:
        lines.append("warning: '%s' not found in MATLAB file" % m)
    return lines + notes, skipped


# ------------------------------------------------------------------ MATLAB
# The run itself lives in run_matlab_gh.py (your run-MATLAB script, made
# reusable). It can run inside this process, or as its own python process.
RUN_SCRIPT = os.path.join(HERE, "run_matlab_gh.py")

_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$")
_SCALAR = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")


def run_matlab(matlab_file, matlab_exe="matlab", timeout=600, python_exe=None,
               notify=True):
    """Run and read results, then queue one completion/failure alert.

    Notifications do not wait for delivery and cannot change the run outcome.
    For an outer loop, select 'whole loop' in notification settings and use
    Block 4's final signal. Per-run alerts are then suppressed automatically.
    """
    started = time.monotonic()
    try:
        names, values = _run_matlab(matlab_file, matlab_exe, timeout, python_exe)
    except Exception:
        if notify:
            notify_completion(success=False, elapsed_seconds=time.monotonic() - started)
        raise
    if notify:
        notify_completion(elapsed_seconds=time.monotonic() - started,
                          variable_count=len(names))
    return names, values


def _run_matlab(matlab_file, matlab_exe="matlab", timeout=600, python_exe=None):
    """Run the .m file via run_matlab_gh.py. Returns (names, values).

    python_exe=None  -> run in this process (no extra python needed)
    python_exe=path  -> run run_matlab_gh.py as a separate python process
    """
    if not matlab_file or not os.path.isfile(matlab_file):
        raise ValueError("MATLAB file not found: %s" % matlab_file)
    matlab_file = os.path.abspath(matlab_file)

    if python_exe:
        proc = subprocess.run([python_exe, RUN_SCRIPT, matlab_file, matlab_exe, str(timeout)],
                              capture_output=True, text=True, timeout=timeout + 30)
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip()[-1500:])
        lines = proc.stdout.strip().splitlines()
        if not lines:
            raise RuntimeError("MATLAB runner returned no output path.")
        out_file = lines[-1]
    else:
        import run_matlab_gh
        out_file = run_matlab_gh.run(matlab_file, matlab_exe, timeout)
    return read_results(out_file)


def read_results(out_file):
    """Parse 'name = value' lines. Scalars become floats, everything else stays text."""
    if not os.path.isfile(out_file):
        raise RuntimeError("MATLAB finished but wrote no output file.")
    names, values = [], []
    with open(out_file, encoding="utf-8") as f:
        for line in f:
            m = _LINE.match(line)
            if not m:
                continue
            names.append(m.group(1))
            raw = m.group(2)
            values.append(float(raw) if _SCALAR.match(raw) else raw)
    return names, values
