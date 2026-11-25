"""Helpers for launching and monitoring MATLAB runs."""
import os
import re
import subprocess
import threading
import time

MARKER_NAME = "matlab_run_done.txt"  # keep identical to run_matlab_import_python_v2.py


def update_script_settings(script_path, matlab_file, matlab_root):
    """Configure the launcher with the paths supplied by Grasshopper."""
    if not script_path or not os.path.isfile(script_path):
        raise ValueError("RunScript was not found: %s" % script_path)

    settings = {
        "MATLAB_FILE": os.path.abspath(str(matlab_file)),
        "MATLAB_ROOT": os.path.abspath(str(matlab_root)),
    }
    if not settings["MATLAB_FILE"] or not os.path.isfile(settings["MATLAB_FILE"]):
        raise ValueError("MatlabFile does not exist: %s" % settings["MATLAB_FILE"])
    if not settings["MATLAB_ROOT"] or not os.path.isdir(settings["MATLAB_ROOT"]):
        raise ValueError("MATLAB Root folder does not exist: %s" % settings["MATLAB_ROOT"])

    with open(script_path, "r", encoding="utf-8") as stream:
        original = stream.read()
    updated = original
    for name, value in settings.items():
        pattern = re.compile(r"^(%s\s*=\s*)[^\r\n]*" % name, re.M)
        updated, count = pattern.subn(
            lambda match, path=value: match.group(1) + repr(path),
            updated, count=1
        )
        if not count:
            raise ValueError("Could not find %s setting in %s." % (name, script_path))

    if updated != original:
        temporary = script_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            stream.write(updated)
        os.replace(temporary, script_path)
    return updated != original


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
        env["HABSIM_AUTO_CLOSE"] = "1"
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
