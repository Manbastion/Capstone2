"""Shared startup helpers. No GUI, Rhino, or MATLAB imports."""
import ctypes
import os
from pathlib import Path
import shutil
import sys


def external_environment():
    """Do not give external tools Rhino's Python or a bundle's library paths."""
    env = dict(os.environ)
    for key in list(env):
        if key.upper() in ("PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE",
                           "PYTHONSTARTUP", "PYTHONUSERBASE", "__PYVENV_LAUNCHER__",
                           "VIRTUAL_ENV"):
            env.pop(key)
    if getattr(sys, "frozen", False):
        for key in ("LD_LIBRARY_PATH", "LIBPATH"):
            original = env.pop(key + "_ORIG", None)
            env.pop(key, None)
            if original is not None:
                env[key] = original
    return env


def prepare_frozen_process():
    """Call once in the standalone app, after importing its GUI dependencies.

    PyInstaller alters Windows' DLL search directory. External MATLAB and
    PowerShell must use the system search order, not bundled Python DLLs.
    Never change the DLL directory of the Rhino host process.
    """
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        if not ctypes.windll.kernel32.SetDllDirectoryW(None):
            raise OSError("Could not reset the DLL search path for external programs.")


def find_matlab():
    """Best-effort discovery; the user can always choose another executable."""
    on_path = shutil.which("matlab")
    if on_path:
        return str(Path(on_path).resolve())
    candidates = []
    if sys.platform == "win32":
        for key in ("ProgramW6432", "ProgramFiles"):
            folder = Path(os.environ.get(key, r"C:\Program Files")) / "MATLAB"
            candidates.extend(folder.glob("R*/bin/matlab.exe"))
    elif sys.platform == "darwin":
        candidates.extend(Path("/Applications").glob("MATLAB_R*.app/bin/matlab"))
    else:
        candidates.extend(Path("/usr/local/MATLAB").glob("R*/bin/matlab"))
    return str(sorted(candidates, reverse=True)[0]) if candidates else ""
