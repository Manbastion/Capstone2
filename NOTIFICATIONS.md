# HabSim completion notifications

This addition alerts a user when MATLAB has finished and its exported results
have been read back. It can also report a failed or timed-out run. The default is
a desktop alert; phone alerts are optional and disabled until configured.

Based on the repository's 12 October 2026 update, commit `0bbce6a`.

## Quick start

1. Use this updated project copy. Keep its folder structure intact.
2. Start the transfer GUI with `python3 main.py` on macOS or your usual Python
   command on Windows.
3. Click **Notifications…**, leave **Enable notifications** and **Show a desktop
   alert** selected, and click **Test notification**. This saves the settings and
   sends a test through the channels you selected.
4. Confirm that an alert actually appears. A successful submission means the
   operating system/service accepted the request; it does not prove the user saw it.
5. For a single MATLAB script, choose **After each MATLAB run**. This also covers
   a long loop contained entirely inside that script: the alert happens after
   the script and result loading finish, not on each internal iteration.
6. Update the Grasshopper component code as described below, then run your model.

Settings can also be opened separately:

```bash
python3 notification_settings.py
```

Only ordinary Python with Tkinter is needed for the settings window. The
notification backend has no Tkinter dependency and works inside Rhino's Python.
There are no additional pip packages to install.

## Update the Grasshopper blocks

The repository has two integration folders and older scripts at its root. This
feature hooks the newest integration:

`grasshopper_integration (2)/grasshopper_integration/`

Use its `grasshopper_blocks/block1_gui_config.py`, `block2_transfer_variables.py`
and `block3_run_matlab.py`. Paste each script into the corresponding **Python 3
Script** component in Rhino 8, retaining the inputs and outputs described in that
file. Set `Repo` to the project root containing `main.py`, `habsim_notifications.py`
and `notification_settings.py`. The updated scripts locate the nested integration
folder themselves. There is no need to flatten or move its files.

An existing `.gh` definition stores a copy of each script. Downloading new Python
files alone does not update that embedded copy. The binary `.gh` files have not
been rewritten by this change.

For a normal single-run workflow, no additional notification component is needed:
Block 3 calls the updated bridge, which queues the alert after reading results.
The same hook works whether Block 3 uses its optional external `PythonExe` input
or runs the bridge inside Rhino. The child process does not send a second alert.

Block 3 now also offers optional Boolean outputs **Done** and **Failed**. Add
them if useful. **Done** refers to one MATLAB invocation, not necessarily the end
of an outer Grasshopper loop. The original Names, Values and Status outputs keep
their existing roles.

The standalone GUI's Transfer button only copies variables. It does not run the
model, and it retains its existing transfer confirmation. Do not use that short
transfer as the signal that a whole simulation has completed. The older root
`02_run_matlab.py` and `run_matlab_import_python_v2.py` are not hooked by this change;
use the current Block 3 or the final-loop block below.

## Notify once at the end of a whole Grasshopper loop

Use this option when Grasshopper invokes MATLAB repeatedly—for example, once per
candidate layout—and you only want an alert after the final iteration.

1. In **Notifications…**, choose **Only at the end of the whole loop**, then save.
   This suppresses automatic per-run alerts.
2. Create another Python 3 Script component and paste
   `grasshopper_blocks/block4_notify_finished.py` from the newest integration.
3. Configure its inputs and outputs:

| Input | Type / access | What to connect |
| --- | --- | --- |
| Repo | str / Item | Same project-root path as the other blocks. |
| Done | bool / Item | True only after the **outer loop** and final result handling finish. |
| Failed | bool / Item, optional | A terminal failure signal. Block 3's Failed output can report MATLAB failure. Defaults to False. |
| Enabled | bool / Item, optional | Defaults to True. Set False to disable this component. |
| ElapsedSeconds | float / Item, optional | Measured total loop duration; leave empty if unavailable. |

| Output | Meaning |
| --- | --- |
| Triggered | True for the solution that queues an alert; not proof of delivery. |
| Status | Armed, queued/submitted, disabled, or a notification problem. |

4. Solve once with **Done=False** and **Failed=False** to arm the component before
   starting the loop. When one becomes True, it triggers once. Leaving it True
   across further recomputes does not send more alerts. Reset both to False before
   the next run.

The block deliberately ignores a saved True signal when a definition is first
opened. Disabling and re-enabling it also requires a fresh False state before the
next completion. If both signals are True, it reports failure.

Connect the actual final signal from your loop controller. Do not connect a
per-iteration Done pulse: the notification block cannot infer how many iterations
remain. In whole-loop mode, wire Failed as well if the loop can stop before Done.
The repository does not expose a single universal outer-loop controller, so this
connection is made in the user's definition.

## Desktop behaviour

| Computer | Alert |
| --- | --- |
| macOS | A Notification Centre message using the built-in AppleScript notification command; optional Glass sound. |
| Windows | A small native popup in a separate process. It dismisses after about 15 seconds, or when the user clicks OK. Optional system sound. |
| Linux | A desktop notification if `notify-send` and a desktop notification service are installed. Sound depends on the desktop. |

Example: **HabSim - MATLAB run complete** — “MATLAB run finished after 3m 12s.
8 result variable(s) loaded. Your results are ready on the computer.”

Alerts are submitted in background threads, so acknowledging a popup or waiting
for the phone service does not delay the Grasshopper component returning its
results. The existing MATLAB runner itself remains synchronous: Rhino may still
appear busy while MATLAB executes. This feature does not make that run asynchronous.

Keep Rhino/Python running until delivery has been attempted. These are convenience
alerts, not a persistent message queue; exiting immediately or losing power can
prevent delivery. Background attempts have timeouts and are not retried.

On macOS, if a test is submitted but invisible, check notification permissions
for the application attributed to the AppleScript alert, and check Focus settings.
Windows managed-device policies may restrict PowerShell or Windows Script Host;
the notification history will record delivery errors. Do not weaken those policies
to use this feature—ask the device administrator or use an allowed channel.

## Optional phone alerts

Phone delivery uses [ntfy](https://ntfy.sh/), a notification app/service. It is an
app notification, not SMS. No phone number is entered or stored by HabSim.

1. Install the ntfy app on the phone and allow notifications.
2. Open the HabSim **Notifications…** settings and select **Send alerts to my
   subscribed phone topic**.
3. Leave Server as `https://ntfy.sh` for the public service, or enter your team's
   approved HTTPS ntfy server. Enter the server only, not a topic URL.
4. Click **Generate topic** to make a random topic name, or enter your team's
   existing topic. Subscribe to the same server and topic in the phone app.
5. Click **Test notification** and confirm that the phone receives it. If using
   an iPhone, test with the phone locked too. Check the app/server setup if delivery
   is delayed.

Public topics are readable by anyone who knows their name. A random topic reduces
guessing but is not access control. For sensitive deployments, use a protected
topic or your team's approved service. Only generic status, elapsed time and
result count are sent: no model filenames, local paths, variable values or raw
MATLAB error messages are included.

Protected topics can use a publishing token supplied in the environment variable
`HABSIM_NTFY_TOKEN` before Rhino/Python starts. Subscribe with the required
credentials in the phone app too. The settings file does not save tokens. On a
Mac, setting a variable in Terminal does not automatically add it to an already
running Rhino instance; have the project team configure the launch environment.

The public service's availability, permissions and quotas apply. HabSim makes
one HTTPS publishing attempt per alert and records whether the service accepted
it. No live phone alerts were sent while developing or testing this addition.

## Troubleshooting and recent alerts

**Notifications… → Recent alerts** shows the last 20 recorded attempts, including
whether each selected channel was submitted or returned an error. A failed
notification does not turn a successful calculation into a failed calculation.
MATLAB errors still appear in the normal component Status output.

| Issue | Check |
| --- | --- |
| No alert after a MATLAB run | Enable notifications and a delivery channel; select run mode; ensure the component uses the newest bridge. |
| Alerts after every iteration | Select whole-loop mode and connect only the outer loop's final signal to Block 4. |
| No whole-loop alert | Solve with Done/Failed False first; make sure the final signal becomes True and the block recomputes. |
| A failed loop never alerts | Wire the terminal failure signal to Failed; enable failure alerts. |
| Test says disabled | Enable notifications and at least one delivery channel. |
| Phone service returns HTTP 401/403 | Check the token, publishing permissions, server and topic. |
| Phone service returns HTTP 429 | The service rate limit was reached. Check loop mode and service quotas before testing again. |
| Phone unavailable but desktop works | Check internet/app permissions. Channels are attempted independently. |
| No GUI window | Use normal Python with Tkinter for `notification_settings.py`; Rhino's embedded Python need not have Tkinter. |
| Settings appear different on another machine | Settings are local to the operating-system user, not stored in the shared repo. |

Local files are stored in `~/CapstoneGH/` (on Windows, under the user's home
folder):

- `notification_settings.json`: preferences and phone server/topic; no token.
- `notifications.log`: generic delivery outcomes, rotating at approximately 256 KiB.

For automated tests, `HABSIM_NOTIFICATION_SETTINGS` can point to a different
settings file. The log is written beside that file.

## What changed and how it was checked

- Added `habsim_notifications.py`, shared settings and nonblocking delivery.
- Added `notification_settings.py` and the GUI's Notifications button.
- Hooked the newest `gh_bridge.run_matlab()` after result parsing, with a failure
  path for MATLAB, timeout and missing-output errors.
- Added the optional final-loop component with a completion latch.
- Updated the newest blocks to find their checked-in nested integration folder
  from Repo, and forwarded custom timeouts to the external Python runner.

Run the automated checks from the project root:

```bash
python3 -m unittest discover -s tests -v
```

Tests cover completion/failure ordering, script restoration, missing output,
timeouts, repeated GH signals, disabled settings, nonblocking delivery, phone
request construction and isolation of delivery failures. All notification
transports and MATLAB execution are simulated; no messages are sent by the tests.

Actual macOS/Windows notifications, phone receipt, the settings window and the
full Rhino/MATLAB workflow still need a local smoke test. Start with **Test
notification**, then a short MATLAB example, then one complete real loop.

API references: [Apple desktop notifications](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html),
[Microsoft timed popup example](https://learn.microsoft.com/en-us/office/vba/excel/concepts/controls-dialogboxes-forms/automatically-dismiss-a-message-box),
[ntfy JSON publishing and authentication](https://docs.ntfy.sh/publish/),
and [ntfy phone subscriptions](https://docs.ntfy.sh/subscribe/phone/).
