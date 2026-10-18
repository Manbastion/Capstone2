# Desktop and phone notifications

Updated 17 October 2026. Phone alerts use **ntfy**, sometimes pronounced “notify”.
They are app push notifications, not SMS. Desktop use requires no ntfy account.

## Settings and first test

Open **Notifications…** in the transfer GUI, run `notification_settings.py`, or
use the platform launcher from README. Preferences are local to this OS user
and shared with Grasshopper on the same computer.

| Setting | Effect |
| --- | --- |
| Enable notifications | Master switch for all channels. |
| Show a desktop alert | Mac Notification Centre, Windows timed popup, or Linux notify-send. |
| Play a desktop sound | Request a desktop sound; phone sound is controlled by the phone/app. |
| Also alert when processing fails | Include launch errors, MATLAB failure, invalid output and timeout. Deliberate Cancel does not send a failure alert. |
| After each MATLAB run | Notify after successful exit and validated export, or failure. |
| Only at the end of the whole loop | Suppress per-run alerts; use component 04's final signal. |

Enable the desktop channel, then click **Test desktop**. Confirm the visible
alert and sound, then inspect **Recent alerts**. Tests save the settings first
and honour the master/channel switches. **Test phone** never enables an opted-out
phone channel. Separate tests make a channel failure easier to diagnose.

On Mac, if submitted but invisible, check **System Settings → Notifications**,
Focus and sound settings. macOS controls attribution/permission for AppleScript
alerts. Windows uses a separate PowerShell process for a native popup; it closes
after about 15 seconds or when acknowledged. Managed devices may restrict the
notification tools: use an allowed channel or ask the administrator.

## Set up a phone

1. Install **ntfy** from the phone's app store and allow notifications.
2. In HabSim settings, enable **Send alerts to my subscribed phone topic**.
3. Use Server `https://ntfy.sh`, or the team's approved HTTPS ntfy server. Enter
   the server root, not a URL already containing the topic.
4. Click **Generate topic**. Keep using that random topic once subscribed.
5. Click **Copy subscription URL**. In the phone app add the same server/topic.
   For example, a URL `https://ntfy.sh/habsim-example` means server
   `https://ntfy.sh` and topic `habsim-example`. Use your generated name, not this
   example, for a real subscription.
6. Save settings and click **Test phone**. Confirm arrival on the phone.
7. Repeat with the phone locked. Check **Recent alerts** if no alert arrives.

Only generic status, elapsed time and result count are sent. No model paths,
variable values or raw MATLAB errors are sent. The delivery log omits topic/server
credentials and raw service error bodies.

Public topics are readable by anyone who knows the name. A random name reduces
guessing but is not access control. Use a protected topic or an approved server
when required. Service availability, quotas and device permissions still apply.

### Protected topics

The publisher reads `HABSIM_NTFY_TOKEN` from its process environment. It is never
saved in the settings JSON or repository. Configure the required subscription
credentials in the phone app too. Example temporary test commands:

```bash
# macOS: replace the placeholder locally
export HABSIM_NTFY_TOKEN='YOUR_PUBLISHING_TOKEN'
python3 habsim_notifications.py --test --channel phone
```

```powershell
# Windows PowerShell: replace the placeholder locally
$env:HABSIM_NTFY_TOKEN = 'YOUR_PUBLISHING_TOKEN'
py -3 habsim_notifications.py --test --channel phone
```

An already-running Rhino, or Rhino opened separately from Finder/Start, does not
inherit environment changes made later in Terminal. Start Rhino from that
configured environment for protected-topic runs. On Mac, after closing Rhino,
one option is launching its executable from the configured Terminal:

```bash
"/Applications/Rhino 8.app/Contents/MacOS/Rhinoceros" &
```

Use the actual installation path. On Windows, launch Rhino's executable from
the configured PowerShell. Have the team prepare this for the client if needed.
Do not put tokens in shared Panels, screenshots, scripts or Git commits.

### iPhone and self-hosted servers

A self-hosted ntfy server may need upstream configuration for instant iOS push;
this is a server setting, not a HabSim setting. See the
[official iOS server setup](https://docs.ntfy.sh/config/#ios-instant-notifications).
If accepted alerts arrive only when opening the app, check device permissions,
Focus/battery settings, subscriptions and the server's phone push configuration.

## How delivery works

1. A background worker watches MATLAB's process independently of Check presses.
2. Exit code 0 is followed by checking the job's export marker and numeric JSON,
   then writing CSV. Missing or invalid export makes the run fail.
3. A terminal job queues one notification request. Repeated Check presses or
   terminal updates do not queue more alerts.
4. Desktop/phone channels are attempted in parallel. Delivery does not pause
   returning results, and a failed alert cannot change the calculation outcome.
5. ntfy publishing requires HTTPS and a valid JSON publishing receipt. Explicit
   temporary rejection (HTTP 429/502/503/504) is retried at most twice with short,
   bounded delays. Long Retry-After values are reported for a later manual retry.
   Network connection loss is not retried automatically: acceptance may already
   have happened. Exactly-once external delivery is not guaranteed.

For an outer loop, component 04 arms on Done=False and Failed=False. A terminal
True triggers once and stays latched until reset. A saved initial True is ignored.
Failure takes precedence if both signals are True. Connect the actual final
signal; a per-iteration pulse does not identify the final iteration.

Keep Rhino/Python open until attempts complete. There is no persistent queue
that survives shutdown or a lost network. CLI/settings tests wait for an attempt;
the calculation itself does not wait for notification delivery.

## Understand the result

| Status | Meaning |
| --- | --- |
| queued | Background attempt is running. |
| submitted | Selected channels accepted the request; confirm actual display/receipt. |
| partial | One channel submitted while another failed. |
| delivery issue | No successful submission, or unreadable/invalid settings. |
| disabled | Master switch, channel, outcome filter or scope prevented sending. |

CLI results include phone attempt count and message ID after a valid receipt.
**Recent alerts** lists the most recent 20 attempts. The log rotates around 256 KiB.
Under `~/CapstoneGH/` (the user's home folder on either OS), local files are:

- `notification_settings.json`: preferences and server/topic, no token.
- `notifications.log` and `.log.1`: generic attempt outcomes.

`HABSIM_NOTIFICATION_SETTINGS` or CLI `--settings-file` selects another local
settings file and log directory. Disabled events do not fill the log every iteration.

## Troubleshooting

| Problem | Check |
| --- | --- |
| macOS 26 / “have instead 16” | Use standalone python.org Python for Tk windows; README has exact commands. |
| Desktop submitted but invisible | Check notification attribution, permissions, Focus and sound settings. |
| Phone says disabled | Enable master switch and phone channel, then save. |
| HTTP 401/403 | Publishing token, topic permissions, and Rhino's launch environment. |
| HTTP 429 | Wait; use whole-loop mode to reduce messages. |
| Unexpected publishing receipt | Server root must be ntfy, not a login/proxy page returning HTTP 200. |
| Phone submitted but no alert | Exact server/topic subscription, locked-screen permissions and server push setup. |
| Alert only after Check | Install the updated current runner and re-paste component source. |
| Too many loop alerts | Use whole-loop mode and the outer loop's final signal. |
| Failed loop never alerts | Wire Failed and enable failure alerts. |

References: [ntfy publishing/authentication](https://docs.ntfy.sh/publish/),
[phone subscriptions](https://docs.ntfy.sh/subscribe/phone/),
[Apple notifications](https://developer.apple.com/library/archive/documentation/LanguagesUtilities/Conceptual/MacAutomationScriptingGuide/DisplayNotifications.html),
[Microsoft timed popup](https://learn.microsoft.com/en-us/office/vba/excel/concepts/controls-dialogboxes-forms/automatically-dismiss-a-message-box).
