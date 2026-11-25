# Notifications: the simple setup

Use the existing Grasshopper/MATLAB workflow. There is no app to build and no
separate notification program to keep running.

## Client: first time

1. Use the complete updated project folder supplied by the team.
2. Open **Launch_Notifications.bat** on Windows or **Launch_Notifications.command**
   on Mac. You need standalone Python with Tkinter, which the transfer GUI also
   uses. If missing, install Python 3.13 with Tcl/Tk from python.org once.
3. Leave **Enable notifications** and **Show a desktop alert** selected.
4. Choose **After each MATLAB run**, click **Save settings**, then **Test desktop**.
   Confirm the popup appears. Close settings after the test finishes.
5. Run MATLAB through the team's existing Grasshopper component as usual.
   Leave Rhino and its runner open until completion. An alert is attempted when
   the MATLAB script finishes successfully or fails.

After this, just run your normal workflow. Settings are remembered for your
computer account. No separate launcher is needed each time.

For a batch, choose **Only at the end of the whole loop** and save. The supplied
multi-run controller then sends one alert on final completion or failure.
**After each MATLAB run** instead sends an alert after each iteration.
Deliberate Stop/cancel does not send a batch failure alert.

## Optional phone alerts

1. Install the **ntfy** app on the phone.
2. In settings, enable phone alerts and click **Generate topic**.
3. Subscribe on the phone to the exact server/topic shown in settings.
4. Save and click **Test phone**. Check actual receipt on the phone.

Desktop-only alerts need no phone app or network. Phone alerts need internet.
Keep a public server's generated topic private. `submitted` confirms an attempt
was accepted; it does not prove a notification was visible.

## If settings do not open

The Windows launcher keeps errors visible and saves them in
`%USERPROFILE%\CapstoneGH\notification_startup.log`. Send that error to the team.
Alternatively, from the project root run:

```powershell
py -3.13 -E notification_settings.py
```

On Mac, use a current python.org Python rather than Xcode's Python. The existing
Mac launcher tries the python.org installation first.

## Team: what is connected

This update reuses the earlier `habsim_notifications.py` transport and
`notification_settings.py` window. It restores a settings-only Windows launcher;
`Launch_HabSim.bat` remains a separate optional standalone model app.

`habsim_completion.py` adds a small hook to the existing `full_run()` in
`prototype4`, `prototype5`, and the multi-run folder. It honours saved preferences,
handles failure, and waits for queued alerts before the CLI can exit. A missing
MATLAB completion marker or a nonzero batch process exit is treated as failure.
The runner does not need model output variables or JSON export to send an alert.

The multi-run state helper emits whole-loop alerts only at a persisted terminal
transition. Transfer failure is included; a deliberate stop is silent. Scope
filtering prevents a per-run alert and whole-loop alert for the same preference.

Keep the root shared files with the prototype folders. The hook finds the root
without a hard-coded checkout name. Prototype GUI Notifications buttons now
locate the shared settings window too. Existing `gh_matlab_run.py` helpers are
updated to clean inherited Python environment variables before external launch.

No notification-specific Grasshopper ports or new notification block are needed
for these runners. The team's existing definition must already call the matching
`run_matlab.py` / `full_run()` from the updated folder. An unrelated custom runner
will not inherit the hook. Restart Rhino after replacing backend files.

## Verification before handover

Run the notification tests without real alerts:

```powershell
py -3.13 -m unittest discover -s tests -p "test_simple_notifications.py" -v
py -3.13 -m unittest discover -s tests -p "test_notifications.py" -v
```

Then confirm on the target computer: settings test popup, successful MATLAB run
alert, failed MATLAB run alert, and (if used) one final alert for a two-iteration
batch with whole-loop scope selected. Verify the actual phone if enabled.

This update concerns notification integration. The formula-transfer and History
issues identified in the technical review remain separate and are not fixed here.

## Review status

Prepared against main `dd73038`. All 11 new integration tests and the 20 existing
notification-service tests passed on Linux with mocked MATLAB/desktop/phone
operations. Updated modules pass Python 3.9 syntax. The complete repository
suite still has the seven pre-existing failures/errors described in the
technical review (moved files and obsolete prototype paths). Native Windows/Mac
launch and actual MATLAB/device acceptance still need checking.

To publish, copy the contents of `UPDATE_FILES` from the handover ZIP into an
up-to-date repository checkout, preserving folders. Commit the replacements on
a feature branch and push normally. The GitHub connection denied branch writes
with HTTP 403, so this update has not been uploaded automatically.
