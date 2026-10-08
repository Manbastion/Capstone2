"""gh_bridge.py - glue between Grasshopper and your existing Capstone2 code.

Lives in the Capstone2 repo folder next to variable_transfer_v2.py.
Has NO Grasshopper/Rhino imports, so it can be tested from a normal terminal.
Written for Python 3.9 (Rhino 8's CPython) - no `match` statements.
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from variable_transfer_v2 import transfer_data, valid_name, valid_value  # noqa: E402

# Everything the blocks create goes in one scratch folder.
WORK_DIR = os.path.join(tempfile.gettempdir(), "capstone_gh")
os.makedirs(WORK_DIR, exist_ok=True)

DEFAULT_CONFIG_PATH = os.path.join(WORK_DIR, "transfer_config.json")
GH_VARS_JSON = os.path.join(WORK_DIR, "gh_variables.json")


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


def write_gh_variables_file(names, values, path):
    """Write GH variables as 'name = value;' lines (the format your parser reads)."""
    pairs, skipped = clean_pairs(names, values)
    with open(path, "w", encoding="utf-8") as f:
        for n, v in pairs.items():
            f.write("%s = %s;\n" % (n, v))
    return pairs, skipped


# --------------------------------------------------------------------- GUI
def launch_config_gui(names, values, dest_file, python_exe="python",
                      config_path=DEFAULT_CONFIG_PATH):
    """Open the tkinter config window in a separate process (does not block GH)."""
    pairs, _ = clean_pairs(names, values)
    if not pairs:
        raise ValueError("No valid numeric GH variables to configure.")
    if not os.path.isfile(dest_file):
        raise ValueError("MATLAB file not found: %s" % dest_file)
    with open(GH_VARS_JSON, "w", encoding="utf-8") as f:
        json.dump(pairs, f)
    gui_script = os.path.join(HERE, "gh_config_gui.py")
    subprocess.Popen([python_exe, gui_script, GH_VARS_JSON, dest_file, config_path])
    return config_path


def load_config(config_path):
    """Return the saved GUI config dict, or None if there isn't one."""
    if not config_path or not os.path.isfile(config_path):
        return None
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- transfer
def transfer(names, values, dest_file, config_path=None):
    """GH variables -> MATLAB .m file. Returns (report_lines, skipped_names)."""
    if not os.path.isfile(dest_file):
        raise ValueError("MATLAB file not found: %s" % dest_file)

    source, skipped = write_gh_variables_file(
        names, values, os.path.join(WORK_DIR, "gh_source.txt"))
    if not source:
        raise ValueError("No valid numeric GH variables were supplied.")
    source_file = os.path.join(WORK_DIR, "gh_source.txt")

    config = load_config(config_path)
    if config:
        # Apply any edits the user made inside the GUI (renames / new values).
        for old, change in (config.get("source_changes") or {}).items():
            if old in source:
                del source[old]
            source[change["name"]] = change["value"]
        result = transfer_data(
            source_file, dest_file, mode="include",
            selected_variables=config.get("selected", []),
            source_variables=source, mappings=config.get("mappings", {}))
    else:
        # No GUI config: overwrite same-name variables, ignore everything else.
        result = transfer_data(source_file, dest_file, mode="everything",
                               source_variables=source)

    lines = ["%s -> %s : %s -> %s" % (c["source"], d, c["before"], c["after"])
             for d, c in result["changes"].items()]
    if not lines:
        lines = ["(no values changed)"]
    for m in result["missing_in_destination"]:
        lines.append("warning: '%s' not found in MATLAB file" % m)
    return lines, skipped


# ------------------------------------------------------------------ MATLAB
# Appended to the script for the run only, then removed again.
_EXPORT_BLOCK = r"""
% ---- capstone_gh export (temporary) ----
gh_export_file = fullfile(pwd, 'matlab_output_variables.txt');
gh_names = who;
gh_fid = fopen(gh_export_file, 'w');
for gh_i = 1:numel(gh_names)
    gh_n = gh_names{gh_i};
    if strncmp(gh_n, 'gh_', 3), continue; end
    try
        fprintf(gh_fid, '%s = %s\n', gh_n, mat2str(eval(gh_n)));
    catch
    end
end
fclose(gh_fid);
"""

_LINE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$")
_SCALAR = re.compile(r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$")


def run_matlab(matlab_file, matlab_exe="matlab", timeout=600):
    """Run the .m file with an export block appended. Returns (names, values)."""
    if not os.path.isfile(matlab_file):
        raise ValueError("MATLAB file not found: %s" % matlab_file)
    folder = os.path.dirname(os.path.abspath(matlab_file))
    script = os.path.splitext(os.path.basename(matlab_file))[0]
    out_file = os.path.join(folder, "matlab_output_variables.txt")
    if os.path.exists(out_file):
        os.remove(out_file)

    with open(matlab_file, encoding="utf-8", newline="") as f:
        original = f.read()
    try:
        with open(matlab_file, "w", encoding="utf-8", newline="") as f:
            f.write(original + "\n" + _EXPORT_BLOCK)
        # cd into the script's folder so it is found and outputs land beside it
        cmd = [matlab_exe, "-batch", "cd('%s'); %s" % (folder.replace("'", "''"), script)]
        proc = subprocess.run(cmd, cwd=folder, capture_output=True,
                              text=True, timeout=timeout)
    finally:
        with open(matlab_file, "w", encoding="utf-8", newline="") as f:
            f.write(original)  # always restore, even on failure

    if proc.returncode != 0:
        raise RuntimeError("MATLAB failed:\n" + (proc.stderr or proc.stdout)[-1500:])
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
