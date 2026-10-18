# Grasshopper–HabSim variable transfer and notifications

This prototype transfers inputs into a MATLAB script, runs it from Grasshopper,
and loads numeric results back. Desktop and optional **ntfy phone notifications**
alert the user when processing finishes or fails.

Start with a desktop notification test below: it does not require Rhino or MATLAB.
See [NOTIFICATIONS.md](NOTIFICATIONS.md) for phone setup and delivery behaviour,
[GRASSHOPPER_SETUP.md](GRASSHOPPER_SETUP.md) for the components, and
[TESTING.md](TESTING.md) for verification and real-device acceptance checks.

## Requirements

| Task | Required software |
| --- | --- |
| Transfer GUI / notification settings | Standalone Python 3.10+ with Tkinter; Python 3.13 recommended. |
| Desktop alert | A logged-in macOS/Windows desktop; Linux can use notify-send. |
| Phone alert | Internet and the ntfy iOS/Android app subscribed to your topic. |
| Full workflow | Rhino 8 Python 3 Script components and licensed MATLAB supporting -batch (R2019a+), including required model toolboxes. |

The backend and adapters use Python 3.9-compatible syntax for Rhino. A separate
Python installation is used for Tkinter windows. VS Code is an optional editor.
Runtime code uses the standard library; requirements.txt is intentionally empty.
No MATLAB Engine or extra pip packages are needed.

Use the **complete project version containing this README**, keeping its folder
structure. An older main-branch download may not include notification features
until the feature branch is merged.

## macOS setup

1. Install a current Python 3.13 from [python.org](https://www.python.org/downloads/macos/).
   Open its downloaded .pkg and finish installation. Keep Xcode's Python intact.
2. Open Terminal, type `cd ` including the space, drag the project folder from
   Finder into Terminal, then press Return. This selects the folder containing
   main.py and habsim_notifications.py.
3. Check the standalone interpreter:

   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -m tkinter
   ```

   A small window should open. Close it.
4. Open settings:

   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 notification_settings.py
   ```

   Alternatively, double-click **Launch_Notifications.command** in Finder.
5. Enable notifications and desktop alerts, choose **After each MATLAB run**,
   and click **Test desktop**. Confirm an alert appears.
6. Open the transfer GUI:

   ```bash
   /Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 main.py
   ```

The GUI's **Notifications…** button opens the same settings. If installing a
series other than 3.13, use its actual interpreter path.

**macOS 26 / “have instead 16” crash:** Xcode's Python 3.9/Tk can abort when opening
windows. Use the python.org interpreter above. To identify a Python command:

```bash
python3 -c "import sys; print(sys.executable)"
```

## Windows setup

1. Install Python 3.13 from [python.org](https://www.python.org/downloads/windows/),
   including Tcl/Tk and IDLE if offered.
2. Open Terminal in the extracted project folder, or use `cd` with its quoted path.
3. Run these checks:

   ```powershell
   py -3 --version
   py -3 -m tkinter
   ```

4. Close the test window, then open settings with `py -3 notification_settings.py`,
   or double-click **Launch_Notifications.bat**.
5. Enable the desktop channel and click **Test desktop**. A timed popup should
   appear. Start the transfer GUI with `py -3 main.py`.

If `py` is unavailable but your correct `python` command works, substitute it
for `py -3`. Local file paths and preferences must be configured on each machine.

## Check or test without a GUI

From the project root, use your chosen interpreter:

```bash
python habsim_notifications.py --check
python habsim_notifications.py --test --channel desktop
python habsim_notifications.py --test --channel phone
```

On Mac use the full Python 3.13 path above if needed; on Windows use `py -3`.
`--check` sends nothing and does not import Tkinter. Tests honour enabled channels.
Test exit codes: 0 submitted, 2 disabled, 1 failed/incomplete. Diagnostic check
returns 2 if settings are invalid. Submitted does not prove an alert was visible.

## A real MATLAB test before Grasshopper

This synthetic demo transfers known inputs, runs MATLAB, validates output and
writes a local evidence file. Its expected final displacement is **640**:

```bash
python tools/smoke_test_matlab.py --matlab "/full/path/to/matlab" --notify
```

Choose **After each MATLAB run** in settings first. Omit `--notify` to test only
the calculation. A Mac executable might be
`/Applications/MATLAB_R2025b.app/bin/matlab`; Windows might use
`C:\Program Files\MATLAB\R2025b\bin\matlab.exe`. Use the installed version.
Find it in MATLAB with `fullfile(matlabroot, 'bin', 'matlab')` on Mac or
`fullfile(matlabroot, 'bin', 'matlab.exe')` on Windows.

This checks the connection with simple motion equations, not a production HabSim
model. Confirm desktop/phone receipt visually; evidence records publishing status.

## Transfer GUI

1. Make a working copy of the destination file.
2. Choose source and destination; use **Include Variables** for a controlled subset.
3. In **Configure Transfer**, select rows and review their destination links.
   Double-click Transfer checkmarks to select rows, destination names to change
   links, or source names/values to edit them. Destinations must be unique.
4. Save configuration, click **Transfer**, review confirmation and accept.
5. Inspect the destination. **History** stores before/after values, supports
   reverting destination values, and **Export Values…** to JSON/TXT/CSV.

Files, mode and mappings are restored between GUI sessions. Transfer copies
values; it does not run MATLAB or trigger a simulation-completion alert.

Try `examples/notification_demo/workflow_inputs.py` and a **copy** of
`workflow_demo.m`. Link v0, a, t_final and dt to their same names. Their values
become 12, 2, 20 and 5; a subsequent MATLAB run produces final displacement 640.

## Supported values and matching

Assignment text supports numbers, quoted strings, simple arrays/matrices and
MATLAB bracket expressions. Examples:

```text
speed = 12.5
status = "ready"
point = [1, 2]
labels = ["x", "y"]
```

Plain text such as `status = ready` is quoted for MATLAB; `point = 1, 2` becomes
`[1, 2]`. Calculation expressions such as `v0 + a*t` are not transferable literals.
JSON sources may be simple variable objects or History exports. Although the GUI
picker lists CSV, the current GUI backend does not parse arbitrary CSV input.
The Grasshopper adapter additionally accepts the documented two-column
`name,value` CSV. Existing destination assignments are required.

Fuzzy scores measure name similarity, not units or scientific equivalence.
Review suggested links. Bands: Very high 90%+, High 80%+, Medium 65%+, Low 50%+,
Very low below 50%.

Inputs may contain supported strings/arrays; the **MATLAB result exporter and
loader support finite real numeric scalars and vectors**. Nested structs,
matrices and the complete production HabSim schema need an output adapter.

## Grasshopper integration

Use the root source files **01_transfer_variables.py**, **02_run_matlab.py** and
**03_read_results.py**, plus their included **grasshopper_components/** support
folder. Component 02 runs MATLAB in the background and requests one alert after
validated export, failure or timeout. A Check press is not needed to send it.

Optional **00_notification_settings.py** opens settings with external Python.
Optional **04_notify_loop_finished.py** sends one alert for an outer loop's final
signal; whole-loop mode suppresses per-run alerts. Follow
[GRASSHOPPER_SETUP.md](GRASSHOPPER_SETUP.md) for exact ports and wiring.

Existing .gh definitions embed their own code: **re-paste the current component
source when upgrading**. The October 12 `grasshopper_integration (2)` instructions
are superseded by the current root components. The legacy
`run_matlab_import_python*.py` scripts are not hooked to the new notifier.

## Tests

```bash
python -m unittest discover -s tests -v
python tools/check_rhino_syntax.py
```

Tests use no external services, real desktop alerts or MATLAB. They include an
actual local HTTPS publish/receipt test, fake-process failure/timeout/cancel
checks and component state checks. The included GitHub Actions workflow targets
macOS, Windows and Ubuntu; it has not run until the branch is uploaded and Actions
executes it. See [TESTING.md](TESTING.md) for real-device acceptance checks.
