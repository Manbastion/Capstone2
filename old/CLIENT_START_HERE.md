# HabSim: start here (Windows client)

Your team should give you **HabSimClient-Windows.zip**, built and checked on
Windows. This is different from GitHub's **Download ZIP**, which contains source
code. The client app includes Python and its window toolkit. You still need a
licensed MATLAB installation and the toolboxes required by your model.

## First time

1. Right-click **HabSimClient-Windows.zip** and choose **Extract All**.
2. Open the extracted **HabSimClient** folder. Keep all its contents together,
   including **_internal**. Double-click **HabSimClient.exe**.
3. Click **Notification settings / Test**. Enable notifications and desktop
   alerts. Choose **After each MATLAB run**, then **Save settings**.
4. Click **Test desktop** and confirm that a popup appears on this computer.
   Wait for the test to finish before closing the settings window.
5. For phone alerts, install the **ntfy** app. In settings, enable phone alerts,
   click **Generate topic**, and subscribe to that exact server and topic in
   the phone app. Save, click **Test phone**, and check the actual phone.
   A `submitted` status means the request was accepted; check the alert yourself.
6. The app tries to find MATLAB automatically. If **MATLAB program** is empty or
   wrong, click **Browse…** and select your installed `matlab.exe`, usually under
   `C:\Program Files\MATLAB\R20xxX\bin`.
7. Click **Use demo**, then **Run MATLAB**. Keep HabSim open until it finishes.
   Click **Open results**. Open `results.json` with Notepad: the unmodified demo's
   `final_displacement` should be **50**. Confirm your chosen alerts arrived.

Ask your team for help if any of those steps fails; the demo checks the connection
before you use your real model. Phone topics on a public server are readable by
anyone who knows the topic. Use the generated random topic and keep it private.

## Your normal run

1. Open **HabSimClient.exe**.
2. Next to **MATLAB script**, click **Browse…** and choose the `.m` file prepared
   by your team. Keep the model's supporting files in their original locations.
3. Choose a **Results folder**, or keep the default.
4. Click **Run MATLAB**. You can do other work while it runs; leave HabSim open.
5. When it finishes, an alert is attempted using your saved preferences. The
   app shows whether MATLAB succeeded and whether alert delivery was submitted.
6. Click **Open results** to see the files for that attempt.

The app remembers these choices. You do not need to configure notifications
again unless you change them. You do not need VS Code, a terminal, or Grasshopper
for this standalone run.

**Time limit** defaults to 1,440 minutes (24 hours). Set a larger limit if your
team expects a longer calculation. **Cancel run** stops the MATLAB job started
by this app; it does not close a separate MATLAB session you opened yourself.

## What this app runs

It runs the selected MATLAB script with its folder as the working directory.
After MATLAB finishes, it exports the remaining base-workspace variables into
a new `results.json`. It also keeps a `matlab.log` for each attempt. It does not
append code to your script. Your own script can still write its normal output
files; ask the team where those files go.

The script should run without prompts and leave variables MATLAB can convert
to JSON (numbers, arrays, structs, strings and logical values). MATLAB's JSON
conversion can change types/shapes and converts non-finite numbers to `null`;
the JSON file is an interchange format, not a full MATLAB workspace backup.

The app runs an **already prepared script**. It does not transfer new Grasshopper
slider values, run a Grasshopper loop, or update Rhino geometry. If you need that
workflow, use the Grasshopper file your team has configured and tested for you.
Opening notification settings alone does not attach alerts to an arbitrary
existing Grasshopper component.

## If something goes wrong

| What you see | What to do |
| --- | --- |
| A `.bat` window flashes and closes | Use the team's built `HabSimClient.exe`. A source-code download still needs Python. |
| App cannot find MATLAB | Browse to the installed `matlab.exe`. The team can find it in MATLAB with `fullfile(matlabroot, 'bin', 'matlab.exe')`. |
| `Failed` or `Timed out` | Click **Open run log**. Send the error text to your team. It may identify a missing toolbox, licence issue, model error or export problem. |
| MATLAB succeeded but no alert appeared | Open settings; enable the required channel, save and test it. Select **After each MATLAB run**. Check the phone's notification permissions and matching topic. |
| App does not open | Share the exact Windows error and `%USERPROFILE%\CapstoneGH\client_startup.log`, if it exists. Keep the whole extracted app folder together. |

Your preferences are stored under `%USERPROFILE%\CapstoneGH`, so they belong to
your Windows account. Share logs with your project team only: MATLAB logs may
include model information. Completion messages sent to the phone contain no
model values or file paths.
