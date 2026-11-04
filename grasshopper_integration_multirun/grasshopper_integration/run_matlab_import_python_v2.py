"""Run a MATLAB script (or a script that calls Simulink) and wait for it to finish.

No data is saved or exported. The .m file is never modified.

When the script returns, a small marker file (MARKER_NAME) is written next to
the .m file containing 0 (ok) or 1 (the script errored). The Grasshopper block
watches for that file so it can tell "MATLAB finished" apart from "this Python
window is still open".
"""
import os
import subprocess
import time

MARKER_NAME = "matlab_run_done.txt"  # keep identical to gh_matlab_run.py


def _q(text):
    """Escape a string for use inside a single-quoted MATLAB string."""
    return text.replace("'", "''")


def _read_marker(path):
    """Return the int in the marker file, or None if it isn't complete yet."""
    try:
        with open(path, "r") as f:
            text = f.read().strip()
        return int(text) if text else None
    except (OSError, ValueError):
        return None


def full_run(m_file, headless=True):
    """Run m_file in MATLAB and block until it has finished.

    headless=True  : (default) `matlab -batch`, no desktop. MATLAB's output
                     prints in this window and MATLAB exits when the script
                     returns, so figures are not shown.
    headless=False : normal MATLAB desktop, figures stay open. The MATLAB
                     window is left open afterwards - close it yourself.

    Returns 0 on success, non-zero on failure.
    """
    m_file = os.path.abspath(m_file)
    folder = os.path.dirname(m_file)
    marker = os.path.join(folder, MARKER_NAME)

    if os.path.exists(marker):
        os.remove(marker)

    statement = (
        "try, run('{m}'); ms_status = 0; "
        "catch ME, disp(getReport(ME)); ms_status = 1; end; "
        "fid = fopen('{k}', 'w'); fprintf(fid, '%d', ms_status); fclose(fid);"
    ).format(m=_q(m_file), k=_q(marker))

    if headless:
        cmd = ["matlab", "-batch", statement + " exit(ms_status);"]
    else:
        # -wait keeps the launcher process alive for as long as MATLAB is open.
        cmd = ["matlab", "-nosplash", "-wait", "-r", statement]

    print("MATLAB running...")
    try:
        proc = subprocess.Popen(cmd, cwd=folder)
    except FileNotFoundError:
        print("Could not start MATLAB: 'matlab' was not found on PATH.")
        return 1

    status = None
    while status is None:
        status = _read_marker(marker)
        if status is not None:
            break
        if proc.poll() is not None:
            # MATLAB closed. Check the marker one last time.
            status = _read_marker(marker)
            if status is None:
                # No marker: the script probably called exit/quit itself.
                status = 0 if proc.returncode == 0 else (proc.returncode or 1)
            break
        time.sleep(0.5)

    if headless:
        proc.wait()

    if status == 0:
        print("MATLAB file run complete.")
        if not headless and proc.poll() is None:
            print("The MATLAB window has been left open. Close it when you are done.")
    else:
        print("MATLAB reported an error (status %s). See the message above." % status)
    return status