"""Helpers for Block 3 (run MATLAB). Put this file next to gh_bridge.py in
the same folder. It replaces update_script_settings and ScriptRun from
gh_bridge for this block, so gh_bridge.py itself does not need to change.
"""
import os
import re
import subprocess
import threading
import time

MARKER_NAME = "matlab_run_done.txt"  # keep identical to run_matlab_import_python_v2.py


def update_script_settings(script_path, capstone_folder, matlab_file):
    """Rewrite CAPSTONE_FOLDER and MATLAB_FILE at the top of run_matlab.py.
    Nothing else in the file is touched. Returns True if the file changed."""
    with open(script_path, "r", encoding="utf-8") as f:
        text = f.read()
    new = text
    for name, value in (("CAPSTONE_FOLDER", capstone_folder),
                        ("MATLAB_FILE", matlab_file)):
        pattern = re.compile(r'^(%s\s*=\s*)r?"[^"\n]*"' % name, re.M)
        new, n = pattern.subn(lambda m, v=value: m.group(1) + 'r"%s"' % v, new, count=1)
        if n == 0:
            raise ValueError("Could not find a '%s = r\"...\"' line in %s" % (name, script_path))
    if new != text:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(new)
        return True
    return False


class ScriptRun:
    """Launches run_matlab.py in its own console window and watches it.

    matlab_done   True once MATLAB has finished the .m file (marker file seen)
    matlab_status 0 = ok, non-zero = the MATLAB script errored (None until done)
    running       True while the Python window is still open
    returncode    exit code of run_matlab.py once it has closed
    """

    def __init__(self, script_path, python_exe, matlab_file, on_change=None):
        self.script_path = os.path.abspath(script_path)
        self.marker = os.path.join(os.path.dirname(os.path.abspath(matlab_file)), MARKER_NAME)
        self.on_change = on_change
        self.matlab_done = False
        self.matlab_status = None
        self.running = True
        self.returncode = None
        self._start = time.time()
        self._end = None

        if os.path.exists(self.marker):
            os.remove(self.marker)

        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        self._proc = subprocess.Popen(
            [python_exe, self.script_path],
            cwd=os.path.dirname(self.script_path),
            creationflags=flags)

        threading.Thread(target=self._watch, daemon=True).start()

    @property
    def elapsed(self):
        return int((self._end or time.time()) - self._start)

    def _notify(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass

    def _read_marker(self):
        try:
            with open(self.marker, "r") as f:
                text = f.read().strip()
            return int(text) if text else None
        except (OSError, ValueError):
            return None

    def _check_marker(self):
        if self.matlab_done:
            return
        status = self._read_marker()
        if status is not None:
            self.matlab_status = status
            self.matlab_done = True
            self._notify()

    def _watch(self):
        while True:
            self._check_marker()
            rc = self._proc.poll()
            if rc is not None:
                self._check_marker()
                self.returncode = rc
                self._end = time.time()
                self.running = False
                self._notify()
                return
            time.sleep(0.5)
