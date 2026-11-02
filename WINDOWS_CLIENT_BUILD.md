# Team handover: the simpler Windows client

The recommended first handover is **one extracted app folder**, a prepared model,
and [CLIENT_START_HERE.md](CLIENT_START_HERE.md). The client should not install
Python, build the app, paste component code, or edit file paths inside scripts.

This change supplies the app source and Windows build process. A Windows
executable exists only after the build below succeeds. The source ZIP is not
itself the client-ready executable.

## Build it on your Windows computer

Use the complete project containing `habsim_client.py` and this document.
Install Python 3.13 with Tcl/Tk once on the **team's build computer**.
Open Terminal in that project folder and run:

```powershell
py -3.13 tools/build_windows_client.py
```

The script creates a separate `.venv-build`, installs pinned PyInstaller 6.16.0,
builds a folder containing Python/Tk, and runs the packaged executable's GUI
startup check. It produces:

```text
dist\HabSimClient-Windows.zip
```

The check opens the app's widgets and verifies bundled resources. It **does not
run MATLAB or send notifications**. A nonzero build exit or failed check means
there is no verified package to hand over. Run this command on Windows; Linux
and Mac builds do not produce a native Windows executable.

## Or build through GitHub Actions

Push these changes to a feature branch. **Build Windows client** runs for changes
to its listed app files. Open the repository's **Actions** tab, select that
workflow and the run for your commit, and wait for a green build. Under
**Artifacts**, download **HabSimClient-Windows**. Extract the artifact download
to obtain the inner `HabSimClient-Windows.zip`.

After this workflow is on the default branch, **Run workflow** can also start it
manually. This workflow uploads a build artifact; it does not publish a GitHub
Release or merge any code.

## Test the exact app folder before handing it over

On Windows, extract the package into a new folder, preferably also check a
machine/user account without Python on PATH, and record:

1. `HabSimClient.exe` opens without a terminal. Close/reopen it successfully.
2. Configure desktop alerts and **After each MATLAB run**. Test and visually
   confirm the popup. Configure/test the client's chosen phone channel too.
3. Click **Use demo**, then **Run MATLAB**. With the supplied unmodified demo,
   `results.json` contains `final_displacement: 50`; one completion notification
   per enabled channel is attempted. The older transfer smoke test expects
   **640** because it changes the demo inputs first. Those are different tests.
4. Run a prepared copy of the real model. Check the expected results with the
   person responsible for the model. Confirm receipt on the actual devices.
5. Check a failing script such as `error('HabSim acceptance test');`. It must show
   **Failed**, offer the log and never present a previous result as this run's
   successful output. With failure alerts enabled, confirm the failure alert.
6. Check **Cancel run** using a disposable script containing `pause(60); x=1;`.
   The owned job must stop and report **Cancelled**, without a success alert.
7. Close/reopen the app and confirm file locations and notification preferences
   persist. Moving the app folder must not lose those per-user preferences.

A real-model run checks integration; passing Python tests alone cannot prove
that MATLAB licences/toolboxes, Rhino components or phone delivery work.

## If the client needs Grasshopper

Choose and test **one** definition; the repository contains two generations.

| Workflow | Code and setup |
| --- | --- |
| Existing notification-enabled components | Root `00_...` to `04_...` and [GRASSHOPPER_SETUP.md](GRASSHOPPER_SETUP.md). `02_run_matlab.py` produces validated numeric JSON and CSV. |
| Prototype 4 | `prototype4 - (current version)/grasshopper_blocks/` and its `SETUP_GUIDE.md`. The new loader isolates these imports from the older root backend. Its `run_matlab.py` now uses saved MATLAB location/discovery and sends completion alerts. |

**Updating `.py` files does not update code embedded in an existing `.gh` file.**
The team must paste the matching updated block scripts into its Rhino 8 Python 3
components once, configure inputs for the client's computer, and save the `.gh`
file. The existing binary `.gh` in this repository has not been rebuilt by this
change. Keep the script component's reserved `out` output intact and add the
named outputs after it. Check that the Grasshopper solver is enabled.

For Prototype 4, `Repo` accepts the project root or its Prototype 4 subfolder.
`RunScript` must be that version's `run_matlab.py`. Restart Rhino when switching
between different project copies so its cached modules cannot mix versions.
Its external GUI/run blocks still require a standalone Python with Tkinter;
the bundled launcher is **not** a general-purpose `python.exe` to wire into
`PythonExe`. The app fallback avoids that setup, but does not replace live
Grasshopper input transfer or geometry updates.

Set MATLAB's location once by running the launcher, choosing the program and
starting a demo. Prototype 4 reads that saved location, or uses
`HABSIM_MATLAB_EXE` / automatic discovery. Root `02_run_matlab.py` continues to
use its own `MatlabExe` input. All versions use the same notification preferences
for the current Windows account.

Prototype 4 now exports from a separate wrapper rather than editing the model
and deleting generic `vars.mat` / `vars.txt` files. JSON is preferred; CSV still
requires workspace values compatible with MATLAB `struct2table`, and TXT uses
`mat2str`. Test the required format on the real model. Its visible script
console remains open until Enter is pressed.

For an outer Grasshopper loop, test the actual final-loop signal and use
`04_notify_loop_finished.py` with **Only at the end of the whole loop**. The
standalone launcher deliberately asks for **After each MATLAB run** because it
does not know when an external loop is complete.

## Source fallback and troubleshooting

For team testing before packaging, double-click **Launch_HabSim.bat**. It first
looks for a built app, then probes Python 3.13, Python 3 and `python` for Tkinter.
Missing Python produces instructions and a window that stays open.
**Launch_Notifications.bat** opens just the settings through this same launcher.
Alternatively:

```powershell
py -3.13 -E habsim_client.py
```

Logs: `%USERPROFILE%\CapstoneGH\launcher.log` and `client_startup.log`; each run's
folder also contains `matlab.log`. An overridden `HABSIM_NOTIFICATION_SETTINGS`
changes the app/settings log location. Do not commit local settings, logs,
tokens, model results, `dist`, or `.venv-build`.

Automated source checks:

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.13 tools/check_rhino_syntax.py
py -3.13 habsim_client.py --self-test startup-check.json
```

The source tests use fake or mocked processes for MATLAB and mocked network
delivery. The GUI check needs a desktop session. The Windows build workflow
runs the same GUI/resource check on the **packaged** executable.

Packaging references: [PyInstaller operating mode](https://pyinstaller.org/en/stable/operating-mode.html)
and [launching external programs](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application).

## Publish these changes from the supplied source package

The handover ZIP includes a complete source folder and `client-easy-start.patch`.
To use it with your existing Git clone, first make sure `git status` shows no
uncommitted work. In that clone's Windows terminal, run:

```powershell
git switch main
git pull --ff-only
git switch -c feature/client-easy-start
git apply --check "C:\path\to\client-easy-start.patch"
git apply "C:\path\to\client-easy-start.patch"
git add .
git commit -m "Simplify Windows client startup and repair Prototype 4 integration"
git push -u origin feature/client-easy-start
```

Replace the patch path with its actual extracted location. If the check reports
a conflict, stop and resolve it before applying; do not force it. Open a pull
request and inspect the test/build results before merging. The prepared patch
is based on main commit `f08e07d`. An app connection returning GitHub HTTP 403
cannot publish it; the terminal commands use your own normal GitHub access.
