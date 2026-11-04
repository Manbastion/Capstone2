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
    """Update only the two paths needed to launch the existing MATLAB runner.

    The user's MATLAB script remains responsible for its own output and
    saving behaviour.
    """ 
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

    matlab_done   True once the MATLAB launcher and MATLAB process have exited
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
        self.started = self._start
        self._end = None

        if os.path.exists(self.marker):
            os.remove(self.marker)

        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        env = dict(os.environ)
        env["CAPSTONE_AUTO_CLOSE"] = "1"
        for key in list(env):
            if key.upper() in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
                               "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONNOUSERSITE",
                               "__PYVENV_LAUNCHER__", "VIRTUAL_ENV"):
                env.pop(key)
        self._proc = subprocess.Popen(
            [python_exe or "python", self.script_path],
            cwd=os.path.dirname(self.script_path),
            creationflags=flags, env=env)

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
        # Wait for the launcher process to exit, not just the marker file.
        # The MATLAB command writes the marker immediately before `exit`; the
        # Python launcher then waits for MATLAB's process to finish. Waiting
        # for this process prevents iteration N+1 starting while MATLAB N is
        # still shutting down.
        while self._proc.poll() is None:
            time.sleep(0.5)
        status = self._read_marker()
        if status is None:
            status = 0 if self._proc.returncode == 0 else (self._proc.returncode or 1)
        self.matlab_status = status
        self.matlab_done = True
        self.returncode = self._proc.returncode
        self._end = time.time()
        self.running = False
        self._notify()
