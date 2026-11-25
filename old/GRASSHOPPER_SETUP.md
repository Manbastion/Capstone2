# Current Grasshopper component setup

Use root component source files and the included **grasshopper_components/**
folder. The older `grasshopper_integration (2)` folder is no longer required.
Existing .gh files embed old code: re-paste the current source to upgrade them.

## Prepare

1. Follow README to verify Test desktop and, if enabled, Test phone outside Rhino.
2. Find your MATLAB executable by entering `fullfile(matlabroot, 'bin', 'matlab')`
   in MATLAB on Mac, or `fullfile(matlabroot, 'bin', 'matlab.exe')` on Windows.
3. Copy `examples/notification_demo/workflow_inputs.py` and `workflow_demo.m` to a
   working folder and create an empty `runs` subfolder there.
4. In Rhino 8, enter **Grasshopper**. Start a new definition and place **Python 3
   Script** components; do not use IronPython 2.
5. For each component, paste the corresponding root .py file into its editor,
   replacing the template. Use Script Mode with the supplied top-level code.
6. Zoom in to see +/- port controls. Name ports exactly as below, set type hints
   and Item/List Access by right-clicking each input, and keep normal marshalling.

Use Panels for full paths **without surrounding quotes**. Repo is the local
project root containing main.py and habsim_notifications.py, not the GitHub URL
or the sample folder. Mark optional unconnected inputs Optional when needed.

## 01 — Transfer Variables

Source: `01_transfer_variables.py`.

| Input | Type / access | Supply |
| --- | --- | --- |
| Repo | str / Item | Project root. |
| SourceFile | str / Item | Full path to the working workflow_inputs.py. |
| DestinationFile | str / Item | Full path to the working workflow_demo.m. |
| SourceNames | str / List | Four separate items: v0, a, t_final, dt. |
| DestinationNames | str / List | Same names in corresponding order. |
| Apply | bool / Item | Button. |

Outputs: **Preview, TransferredFile, Ready, BackupPath, Status**.

Inspect Preview with Apply=False, then press Apply once. A .bak copy is saved
and the four inputs become 12, 2, 20 and 5. The successful TransferredFile remains
after release, until relevant inputs change on a later component solution.

Each List input needs one flat branch. A names Panel must supply separate items,
not one multiline string; turn off Multiline Data if needed and Flatten the
input. A Button must be observed False before True; saved True toggles do not
execute on loading.

The adapter uses the current transfer backend for supported text/JSON inputs,
plus explicit two-column CSV headed `name,value`. It supports current input
strings/arrays, rejects duplicate input assignments/mappings and keeps a full
backup. Grasshopper backups are separate from the desktop GUI's History.

## 02 — Run MATLAB

Source: `02_run_matlab.py`.

| Input | Type / access | Supply |
| --- | --- | --- |
| Repo | str / Item | Project root. |
| MatlabExe | str / Item | Full MATLAB executable path, or matlab if Rhino finds it on PATH. |
| ScriptFile | str / Item | Transfer.TransferredFile, or a script path for a run-only test. |
| OutputNames | str / List | Four items: t, v, s, final_displacement. |
| OutputFolder | str / Item | Full path to the existing runs folder. |
| Run | bool / Item | Start Button. |
| Check | bool / Item | Separate Button to refresh displayed results/status. |
| Cancel | bool / Item | Separate Button to stop this job. |
| TimeoutSeconds | float / Item | 600 for the demo. |

Outputs: **ResultsFile, CSVFile, Done, Running, LogFile, Status**.
Optional extra outputs: **Failed, NotificationStatus**.

Connect Status to a Panel. Press Run once. MATLAB starts in the background and
Grasshopper returns immediately. Press Check to refresh the canvas, or attach a
one-second timer to this component. The worker sends the alert independently
of Check; results still need a solution to refresh on the canvas.

After validated success, Done=True and result paths become available. A new
run, failure, timeout or changed input signature hides previous result paths on
the next solution. Another Run press while active does not start another job.
Cancel stops this job, not other MATLAB sessions. Keep Rhino open until completion
or cancel before closing.

A new job folder contains request.json, a wrapper, matlab.log, results.json,
results.csv, a completion marker and calculation status. The wrapper does not
append code to the original script. It executes a MATLAB script in the base
workspace and exports requested finite numeric scalars/vectors. Use a driver
script if your model is a function. Required model dependencies/toolboxes must
be available to MATLAB.

For an untransferred demo, final_displacement is 50. After transferring the supplied
inputs it is 640. Both can test run completion, but use 640 for the reference case.

## 03 — Load Variables Back

Source: `03_read_results.py`.

| Input | Type / access | Supply |
| --- | --- | --- |
| Repo | str / Item | Project root. |
| FilePath | str / Item | Run MATLAB.ResultsFile. |
| Variable | str / Item | s or final_displacement. |
| Load | bool / Item | Run MATLAB.Done. |
| Refresh | bool / Item | Separate Button for re-reading an external file. |

Outputs: **Names, Values, Status**. Scalars are one-item numeric lists; vectors
are numeric lists. Load=False clears old values. Use separate loaders for several
variables. Expected s: `[0, 85, 220, 405, 640]`; t: `[0, 5, 10, 15, 20]`.
Connect these numbers to geometry/plotting components as needed.

## Optional 00 — Notification settings

Source: `00_notification_settings.py`.

Inputs, all Item: **Repo** (str), **PythonExe** (str), **Open** (bool Button).
Output: **Status**.

PythonExe must be an external Python with working Tkinter. A Mac example is
`/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13`; on Windows
use the full standalone Python executable path. This is not Rhino's embedded
Python. Press Open; settings starts separately. Repeated presses do not launch
another window while the launched settings process is active.

This component is optional: the standalone settings launcher configures the
same preferences without a Grasshopper settings component.

## Optional 04 — Notify once after the outer loop

Source: `04_notify_loop_finished.py`. Choose **Only at the end of the whole loop**
in settings to suppress automatic per-MATLAB alerts.

Inputs, all Item:

| Input | Type | Supply |
| --- | --- | --- |
| Repo | str | Project root. |
| Done | bool | True only when the outer loop and final processing finish. |
| Failed | optional bool | Terminal failure signal; Run MATLAB.Failed can report a MATLAB failure. |
| Enabled | optional bool | Default True. |
| ElapsedSeconds | optional float | Measured total duration; leave empty if unknown. |

Outputs: **Triggered, Status**.

Solve with Done=False and Failed=False to arm. The next terminal True queues one
alert and remains latched across recomputes. Reset both to False before the next
run. An initial saved True is ignored. Wire the actual final signal from your
loop controller, not every iteration's Done. There is no universal outer-loop
controller supplied by this repository.

## Save a client definition

After verifying reference results and alerts, save the prepared .gh file for the
client. The team should configure local paths on that machine. The definition
does not embed support modules, MATLAB or notification preferences. Paths must
change on another machine.

The binary GH Workspace.gh is not automatically rewritten by this update. Follow
this guide to update its components or build a fresh definition, then save it.
