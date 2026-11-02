import json
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import importlib  # noqa: E402
import Capstone2.prototype4.matlab_literals as matlab_literals  # noqa: E402
import Capstone2.prototype4.value_formats as value_formats  # noqa: E402
import Capstone2.prototype4.variable_transfer_v2 as variable_transfer_v2  # noqa: E402
for _module in (matlab_literals, value_formats, variable_transfer_v2):
    importlib.reload(_module)  # Rhino keeps old modules in memory
from Capstone2.prototype4.variable_transfer_v2 import transfer_data, valid_name, valid_value  # noqa: E402

# Persistent folder (not %TEMP%, which Windows may clean up).
WORK_DIR = os.path.join(os.path.expanduser("~"), "CapstoneGH")
os.makedirs(WORK_DIR, exist_ok=True)

DEFAULT_CONFIG_PATH = os.path.join(WORK_DIR, "transfer_config.json")
SOURCE_FILE = os.path.join(WORK_DIR, "grasshopper_variables.txt")
# The Grasshopper values exactly as received (before any conversion), so the GUI
# can show them and re-convert when the formats change.
RAW_FILE = os.path.join(WORK_DIR, "grasshopper_raw.json")
# The client's own value formats (1 | 2 | 3 -> [1 2 3] ...). Edited in the GUI.
FORMATS_FILE = os.path.join(WORK_DIR, "variable_formats.json")

MODE_TO_BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


# ----------------------------------------------------------------- helpers
def values_per_name(values, n_names):
    """Turn whatever Grasshopper hands over into ONE item per name.

    Accepts a flat list (one value per name), a list of lists, or a Grasshopper
    data tree: one branch per variable. A branch with one item is a single value,
    a branch with several items is a vector; paths like {2;0},{2;1} (same first
    index) are the rows of a matrix. Values may be numbers, text, true/false or
    points.
    """
    if hasattr(values, "Branches"):                      # Grasshopper DataTree
        paths = [tuple(p.Indices) for p in values.Paths]
        branches = [list(br) for br in values.Branches]
        if len(branches) == 1 and n_names != 1 and len(branches[0]) == n_names:
            return list(branches[0])                     # plain list: 1 value per name
        groups = {}
        for path, br in zip(paths, branches):
            groups.setdefault(path[0] if path else 0, []).append(br)
        return [(grp[0][0] if len(grp[0]) == 1 else grp[0]) if len(grp) == 1
                else [list(b) for b in grp]
                for grp in groups.values()]
    if isinstance(values, str):
        values = [values]
    values = list(values or [])
    if any(isinstance(v, (list, tuple)) for v in values):
        return values
    if len(values) != n_names and n_names == 1:
        return [values]                                  # one name, many values: a vector
    return values


def plain_pairs(names, values):
    """GH names/values -> ({name: plain python value}, skipped). Nothing is converted yet."""
    names = [str(n).strip() for n in (names or [])]
    items = values_per_name(values, len(names))
    if len(names) != len(items):
        raise ValueError(
            "Names and Values must match: %d names but %d values/branches. "
            "For vectors give each variable its own branch (Values on Tree Access)."
            % (len(names), len(items)))
    plain, skipped = {}, []
    for n, item in zip(names, items):
        if not valid_name(n):
            skipped.append("%s (invalid name)" % (n or "<blank>"))
            continue
        try:
            plain[n] = value_formats.to_plain(item)
        except ValueError as e:
            skipped.append("%s (%s)" % (n, e))
    return plain, skipped


def _short(text, limit=60):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 3] + "..."


def render_pairs(plain, rules=None):
    """{name: plain value} -> ({name: MATLAB text}, skipped, {name: format used})."""
    out, skipped, used = {}, [], {}
    for n, v in plain.items():
        try:
            text, rule_name = value_formats.convert(n, v, rules)
        except ValueError as e:
            skipped.append("%s (%s)" % (n, e))
            continue
        if not valid_value(text):                        # safety net, should not happen
            skipped.append("%s (could not be written as MATLAB: %s)" % (n, _short(text)))
            continue
        out[n] = text
        if rule_name:
            used[n] = rule_name
    return out, skipped, used


def clean_pairs(names, values):
    """GH names/values -> ({name: MATLAB text}, skipped), using the saved formats."""
    plain, skipped = plain_pairs(names, values)
    out, bad, _ = render_pairs(plain, value_formats.load_rules(FORMATS_FILE))
    return out, skipped + bad


def format_value(item):
    """One value -> MATLAB text (built-in rules only), or None if it can't be sent."""
    try:
        return value_formats.convert("x", item)[0]
    except ValueError:
        return None


def save_raw(plain, path=RAW_FILE):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plain, f)
    except (OSError, TypeError, ValueError):
        pass


def load_raw(path=RAW_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


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


def render_source(renames=None, path=SOURCE_FILE, plain=None, skipped=None):
    """Convert the Grasshopper values with the saved formats and write the source file.

    Lines look like  name = value;  in MATLAB syntax. Applies renames saved from
    the config window so saved links still match. Returns (pairs_written, skipped).
    """
    plain = load_raw() if plain is None else plain
    texts, bad, _ = render_pairs(plain, value_formats.load_rules(FORMATS_FILE))
    skipped = list(skipped or []) + bad
    renames = renames or {}
    final = {}
    for n, v in texts.items():
        new = renames.get(n, n)
        if new in final:
            raise ValueError("Two Grasshopper variables map to the name %r." % new)
        final[new] = v
    with open(path, "w", encoding="utf-8") as f:
        for n, v in final.items():
            f.write("%s = %s;\n" % (n, v))
    return final, skipped


def write_source_file(names, values, renames=None, path=SOURCE_FILE):
    """Save the live GH values, convert them, and write the source file.

    Returns (pairs_written, skipped_names).
    """
    plain, skipped = plain_pairs(names, values)
    save_raw(plain)
    return render_source(renames, path, plain, skipped)


def _check_dest(dest_file):
    if not dest_file or not os.path.isfile(dest_file):
        raise ValueError("MATLAB file not found: %s" % dest_file)


def _same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))



def _clean_env():
    """Environment for launching an EXTERNAL python from inside Rhino.

    Rhino sets PYTHONHOME / PYTHONPATH etc. for its own embedded Python. If
    they are passed on, the external python loads Rhino's standard library and
    crashes (e.g. 'SRE module mismatch'). Remove them.
    """
    env = dict(os.environ)
    for key in list(env):
        if key.upper() in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
                           "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
                           "__PYVENV_LAUNCHER__", "VIRTUAL_ENV"):
            env.pop(key)
    return env

LAST_STATUS_FILE = os.path.join(WORK_DIR, "last_gui_status.txt")


def save_last_status(text):
    """Remember what the last Open press did (a Button resets right after)."""
    try:
        with open(LAST_STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def load_last_status():
    try:
        with open(LAST_STATUS_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


# --------------------------------------------------------------------- GUI
def launch_config_gui(names, values, dest_file, python_exe="python",
                      config_path=DEFAULT_CONFIG_PATH):
    """Open the full Transfer window in a separate process (does not block GH).

    Source = the live GH variables, destination = dest_file (the .m file).
    """
    _check_dest(dest_file)
    config = load_config(config_path) or {}
    final, skipped = write_source_file(names, values, config.get("renames"))
    if not final:
        raise ValueError("No valid GH variables to configure. Rejected: %s"
                         % (", ".join(skipped) or "none were supplied"))
    gui_script = os.path.join(HERE, "gh_gui.py")
    python_exe = python_exe or "python"

    # Send the GUI's errors to a log file instead of a console window that
    # vanishes, and hide the console on Windows.
    log_path = os.path.join(WORK_DIR, "gui_error.log")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with open(log_path, "w", encoding="utf-8") as log:
        try:
            proc = subprocess.Popen(
                [python_exe, gui_script, SOURCE_FILE,
                 os.path.abspath(dest_file), config_path],
                stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                cwd=HERE, creationflags=flags, env=_clean_env())
        except OSError as e:
            raise RuntimeError(
                "Could not start Python (%r): %s. Put the full path to python.exe "
                "in the PythonExe input." % (python_exe, e))

    # If it dies within a couple of seconds it crashed: report why.
    try:
        proc.wait(timeout=2.5)
    except subprocess.TimeoutExpired:
        return config_path  # still running = the window is open
    with open(log_path, encoding="utf-8", errors="replace") as f:
        detail = f.read().strip()
    hint = ""
    if "tkinter" in detail:
        hint = (" -> This Python has no tkinter. Reinstall Python from python.org "
                "with 'tcl/tk and IDLE' ticked, or point PythonExe at one that has it.")
    elif not detail:
        hint = (" -> No error text. 'python' may be the Microsoft Store shortcut; "
                "put the full path to python.exe in PythonExe.")
    raise RuntimeError("GUI closed immediately (exit code %s). %s%s"
                       % (proc.returncode, detail[-1200:], hint))


# ---------------------------------------------------------------- transfer
def matlab_is_running(matlab_file, max_age=3600):
    """True while a Run MATLAB job is using this file (ignores a stale lock)."""
    lock = os.path.abspath(matlab_file) + ".running"
    try:
        return time.time() - os.path.getmtime(lock) < max_age
    except OSError:
        return False


def transfer(names, values, dest_file, config_path=None):
    """GH variables -> MATLAB .m file. Returns (report_lines, skipped_names)."""
    _check_dest(dest_file)
    if matlab_is_running(dest_file):
        raise RuntimeError("MATLAB is still running this file. Wait for Run MATLAB "
                           "to finish (or Cancel it) before transferring.")
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
        raise ValueError("No valid GH variables were supplied. Rejected: %s"
                         % (", ".join(skipped) or "none were supplied"))

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
        from Capstone2.prototype4.history import record_transfer
        record_transfer(SOURCE_FILE, dest_file, mode_name, selected,
                        result["transferred"], result["changes"],
                        result["mappings"])
    except Exception as e:  # tkinter missing, read-only folder, ...
        notes.append("note: history not recorded (%s)" % e)

    lines = ["%s -> %s : %s -> %s" % (c["source"], d, _short(c["before"]), _short(c["after"]))
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


def run_matlab(matlab_file, matlab_exe="matlab", timeout=600, python_exe=None):
    """Run the .m file via run_matlab_gh.py. Returns (names, values).

    python_exe=None  -> run in this process (no extra python needed)
    python_exe=path  -> run run_matlab_gh.py as a separate python process
    """
    if not matlab_file or not os.path.isfile(matlab_file):
        raise ValueError("MATLAB file not found: %s" % matlab_file)
    matlab_file = os.path.abspath(matlab_file)

    if python_exe:
        proc = subprocess.run([python_exe, RUN_SCRIPT, matlab_file, matlab_exe],
                              capture_output=True, text=True, timeout=timeout + 30,
                              env=_clean_env())
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip()[-1500:])
        out_file = proc.stdout.strip().splitlines()[-1]
    else:
        import run_matlab_gh
        out_file = run_matlab_gh.run(matlab_file, matlab_exe, timeout)
    return read_results(out_file)


class MatlabJob(object):
    """Runs MATLAB on a background thread so Grasshopper stays responsive.

    state: 'running' -> 'done' | 'error' | 'cancelled'
    After 'done': .names / .values.  After 'error': .error (text).
    on_done() is called (from the background thread) when it finishes - the
    Grasshopper block uses it to ask the component to recompute.
    """

    def __init__(self, matlab_file, matlab_exe="matlab", timeout=600, on_done=None):
        self.matlab_file = os.path.abspath(matlab_file)
        self.matlab_exe = matlab_exe or "matlab"
        self.timeout = timeout
        self.on_done = on_done
        self.state = "running"
        self.names, self.values, self.error = [], [], ""
        self.started = time.time()
        self.finished = None
        self._proc = None
        self._cancelled = False
        self._thread = threading.Thread(target=self._work, name="capstone-matlab")
        self._thread.daemon = True

    @property
    def running(self):
        return self.state == "running"

    @property
    def elapsed(self):
        return (self.finished or time.time()) - self.started

    def start(self):
        self._thread.start()
        return self

    def cancel(self):
        self._cancelled = True
        if self._proc is not None:
            import run_matlab_gh
            run_matlab_gh.kill_tree(self._proc)

    def _set_proc(self, proc):
        self._proc = proc
        if self._cancelled:             # cancelled before MATLAB had started
            import run_matlab_gh
            run_matlab_gh.kill_tree(proc)

    def _work(self):
        try:
            import run_matlab_gh
            out_file = run_matlab_gh.run(self.matlab_file, self.matlab_exe,
                                         self.timeout, on_start=self._set_proc)
            self.names, self.values = read_results(out_file)
            self.state = "done"
        except Exception as e:
            if self._cancelled:
                self.state, self.error = "cancelled", "Cancelled."
            else:
                self.state, self.error = "error", str(e)
        finally:
            self.finished = time.time()
            if self.on_done:
                try:
                    self.on_done()
                except Exception:
                    pass


def _array_values(x):
    """JSON array -> list of floats, or list of lists (matrix). null -> NaN."""
    def f(v):
        return float("nan") if v is None else float(v)
    if x and all(isinstance(r, list) for r in x):
        return [[f(v) for v in r] for r in x]
    return [f(v) for v in x]


def to_branches(values):
    """Values from run_matlab -> [(path, [items])] for building a Grasshopper tree.

    scalar -> {i} one item;  vector -> {i} n items;  matrix -> {i;row} per row.
    """
    out = []
    for i, v in enumerate(values):
        if isinstance(v, list) and v and isinstance(v[0], list):
            for r, row in enumerate(v):
                out.append(((i, r), list(row)))
        elif isinstance(v, list):
            out.append(((i,), list(v)))
        else:
            out.append(((i,), [v]))
    return out


def flatten_json(obj, prefix="", out=None):
    """{'meteorite': {'IL': 1}} -> {'meteorite.IL': 1.0}. Returns an ordered dict."""
    out = {} if out is None else out
    if isinstance(obj, dict):
        for key, val in obj.items():
            flatten_json(val, prefix + "." + key if prefix else key, out)
    elif isinstance(obj, list) and obj and all(isinstance(i, dict) for i in obj):
        for i, item in enumerate(obj, 1):           # struct array
            flatten_json(item, "%s(%d)" % (prefix, i), out)
    elif isinstance(obj, list):
        out[prefix] = _array_values(obj)
    elif isinstance(obj, bool):
        out[prefix] = 1.0 if obj else 0.0
    elif isinstance(obj, (int, float)):
        out[prefix] = float(obj)
    elif obj is None:
        out[prefix] = float("nan")
    else:
        out[prefix] = str(obj)
    return out


def read_results(out_file):
    """Read MATLAB's exported variables.

    Prefers matlab_output_variables.json (handles structs like meteorite.IL);
    falls back to the .txt file."""
    json_file = os.path.splitext(out_file)[0] + ".json"
    if os.path.isfile(json_file):
        try:
            with open(json_file, encoding="utf-8") as f:
                flat = flatten_json(json.load(f))
            if flat:
                return list(flat.keys()), list(flat.values())
        except (OSError, ValueError):
            pass  # fall back to the text file
    return _read_txt_results(out_file)


def _parse_text_value(raw):
    """'5' -> 5.0 ; '[1 2 3]' -> [1.0, 2.0, 3.0] ; '[1 2;3 4]' -> [[1,2],[3,4]]."""
    if _SCALAR.match(raw):
        return float(raw)
    if raw.startswith("[") and raw.endswith("]"):
        try:
            rows = [[float(t) for t in r.replace(",", " ").split()]
                    for r in raw[1:-1].split(";")]
            return rows[0] if len(rows) == 1 else rows
        except ValueError:
            pass
    return raw


def _read_txt_results(out_file):
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
            values.append(_parse_text_value(raw))
    return names, values


# ------------------------------------------------- run YOUR run_matlab.py script
# The block does not contain its own copy of the script. It rewrites the three
# settings lines in your run_matlab.py (CAPSTONE_FOLDER, MATLAB_FILE, SAVE_TYPE)
# from the block's inputs, then opens the script in its own console window.
SAVE_TYPES = ("json", "csv", "txt")


def output_file_for(matlab_file, save_type):
    """Where the script writes its results: next to the .m file."""
    return os.path.join(os.path.dirname(os.path.abspath(matlab_file)),
                        "matlab_output_variables." + save_type.lower())


def _abs(path):
    """Absolute path; Windows (C:\\..., \\\\server\\...) paths are kept as they are."""
    path = str(path).strip().strip('"').strip("'")
    if re.match(r"^[A-Za-z]:[\\/]", path) or path.startswith("\\\\"):
        return path
    return os.path.abspath(path)


def _py_raw(value, what):
    """Text for a Python raw string literal r"..." holding a Windows path."""
    value = str(value).strip().strip('"').strip("'")
    if not value:
        raise ValueError("%s is empty." % what)
    if '"' in value or "\n" in value or "\r" in value:
        raise ValueError("%s contains a character that can't be written: %r" % (what, value))
    if value.endswith("\\"):               # a raw string can't end in a backslash
        value = value[:-1] + "/" if len(value) <= 3 else value[:-1]
    return 'r"%s"' % value


def update_script_settings(script_path, capstone_folder, matlab_file, save_type):
    """Rewrite CAPSTONE_FOLDER / MATLAB_FILE / SAVE_TYPE in the user's script.

    Only those three assignment lines change (the trailing comment, line
    endings and everything else are kept). Returns the names that changed.
    """
    if not script_path or not os.path.isfile(script_path):
        raise ValueError("run_matlab.py not found: %s" % script_path)
    for label, value in (("CapstoneFolder", capstone_folder), ("MatlabFile", matlab_file)):
        if not str(value or "").strip().strip("\"'"):
            raise ValueError("%s is empty." % label)
    save_type = str(save_type or "").strip().lower()
    if save_type not in SAVE_TYPES:
        raise ValueError("SaveType must be one of %s (got %r)." % (", ".join(SAVE_TYPES), save_type))

    wanted = [
        ("CAPSTONE_FOLDER", _py_raw(_abs(capstone_folder), "CapstoneFolder")),
        ("MATLAB_FILE", _py_raw(_abs(matlab_file), "MatlabFile")),
        ("SAVE_TYPE", '"%s"' % save_type),
    ]
    with open(script_path, encoding="utf-8", newline="") as f:
        text = f.read()

    changed = []
    for name, literal in wanted:
        pattern = re.compile(r"^(%s[ \t]*=[ \t]*)(?:[rRuU]?(?:\"[^\"\r\n]*\"|'[^'\r\n]*'))(?P<rest>[^\r\n]*)(?=\r?\n|\Z)"
                             % name, re.M)
        m = pattern.search(text)
        if not m:
            raise ValueError("Could not find a line like  %s = r\"...\"  in %s"
                             % (name, os.path.basename(script_path)))
        new_line = m.group(1) + literal + m.group("rest")
        if new_line != m.group(0):
            text = text[:m.start()] + new_line + text[m.end():]
            changed.append(name)
    if changed:
        tmp = script_path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, script_path)
    return changed


# Runs the user's script exactly as `python run_matlab.py` would, but if it crashes
# the window stays open and shows the error (otherwise Windows closes it instantly).
_LAUNCH_WRAPPER = (
    "import runpy, sys, traceback\n"
    "p = sys.argv[1]\n"
    "sys.argv = [p]\n"
    "try:\n"
    "    runpy.run_path(p, run_name='__main__')\n"
    "except SystemExit:\n"
    "    raise\n"
    "except BaseException:\n"
    "    traceback.print_exc()\n"
    "    try:\n"
    "        input('\\nrun_matlab.py stopped with the error above. Press ENTER to close this window.')\n"
    "    except EOFError:\n"
    "        pass\n"
    "    sys.exit(1)\n"
)


class ScriptRun(object):
    """Your run_matlab.py running in its own window; Grasshopper doesn't wait for it."""

    def __init__(self, script_path, python_exe, matlab_file, save_type, on_change=None, _stdin=None):
        self.script_path = os.path.abspath(script_path)
        self.output_file = output_file_for(matlab_file, save_type)
        self.started = time.time()
        self.on_change = on_change
        self.proc = subprocess.Popen(
            [python_exe or "python", "-c", _LAUNCH_WRAPPER, self.script_path],
            cwd=os.path.dirname(self.script_path), env=_clean_env(), stdin=_stdin,
            # a visible console, because the script ends with input("Press ENTER...")
            creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        t = threading.Thread(target=self._watch, name="capstone-run-script")
        t.daemon = True
        t.start()

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def _watch(self):
        """Tell the caller when the output file appears, and again when the script exits."""
        announced = False
        while self.proc.poll() is None:
            if not announced and self.output_ready:
                announced = True
                self._notify()
            time.sleep(0.5)
        self._notify()

    @property
    def running(self):
        return self.proc.poll() is None

    @property
    def returncode(self):
        return self.proc.poll()

    @property
    def elapsed(self):
        return time.time() - self.started

    @property
    def output_ready(self):
        """True once the script wrote its output file AFTER this run started."""
        try:
            return os.path.getmtime(self.output_file) >= self.started - 2
        except OSError:
            return False
