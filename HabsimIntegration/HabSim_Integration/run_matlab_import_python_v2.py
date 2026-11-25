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
OUTPUT_FOLDER_MARKER = "matlab_output_folder.txt"


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


from habsim_completion import notify_run as _habsim_notify_run


@_habsim_notify_run
def full_run(m_file, m_path, headless=True):
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
    output_marker = os.path.join(folder, OUTPUT_FOLDER_MARKER)
    try:
        os.remove(output_marker)
    except OSError:
        pass

    if os.path.exists(marker):
        os.remove(marker)

    # Keep a harmless default for scripts that expect Output_Folder, but do
    # not rely on that variable name when discovering the actual output folder.
    output_folder = os.path.join(folder, 'HabSim_Output')
    statement = (
        "try, if ~exist('Output_Folder','var') || isempty(Output_Folder), "
        "Output_Folder = '{o}'; end; "
        "if ~exist(Output_Folder,'dir'), mkdir(Output_Folder); end; "
        "catch, end; "
        "ms_run_started = now; "
        "try, run('{m}'); ms_status = 0; "
        "catch ME, disp(getReport(ME)); ms_status = 1; end; "
        # Inspect every base-workspace char/string scalar. A candidate must be
        # an existing directory whose directory timestamp changed during this run.
        "ms_output_candidate = ''; ms_output_latest = ms_run_started - 5/86400; "
        "try, ms_vars = whos; "
        "for ms_i = 1:numel(ms_vars), ms_name = ms_vars(ms_i).name; "
        "if any(strcmp(ms_name, {{'ms_output_candidate','ms_output_latest','ms_vars','ms_i','ms_name','ms_value','ms_path','ms_info','ms_dates'}})), continue; end; "
        "ms_value = eval(ms_name); ms_path = ''; "
        "if ischar(ms_value) && isrow(ms_value), ms_path = strtrim(ms_value); "
        "elseif isstring(ms_value) && isscalar(ms_value), ms_path = strtrim(char(ms_value)); end; "
        "if ~isempty(ms_path) && isfolder(ms_path), ms_info = dir(ms_path); "
        "if ~isempty(ms_info), ms_dates = [ms_info.datenum]; ms_latest = max(ms_dates); "
        "if ms_latest >= ms_output_latest, ms_output_latest = ms_latest; ms_output_candidate = ms_path; end; "
        "end; end; end; catch, end; "
        "try, outfid = fopen('{of}', 'w'); if outfid >= 0, fprintf(outfid, '%s', ms_output_candidate); fclose(outfid); end; catch, end; "
        "fid = fopen('{k}', 'w'); fprintf(fid, '%d', ms_status); fclose(fid);"
    ).format(m=_q(m_file), k=_q(marker), of=_q(output_marker), o=_q(output_folder.replace('\\','/')))

    if headless:
        cmd = [m_path, "-batch", statement + " exit(ms_status);"]
    else:
        # -wait keeps the launcher process alive for as long as MATLAB is open.
        cmd = [m_path, "-nosplash", "-wait", "-r", statement]

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