# Notification verification and release checks

Prepared 17 October 2026 against main commit `b324d66` plus this feature's changes.

## Verified automatically

```bash
python -m unittest discover -s tests -v
python tools/check_rhino_syntax.py
```

At preparation, **55 tests passed on Linux with Python 3.12.14**, including an
actual localhost HTTPS server test. The Rhino Python 3.9 syntax check passed.
There were no real desktop alerts or external phone messages in these checks.

| Area | Evidence covered |
| --- | --- |
| Configuration | Atomic save/load, opt-in controls, valid HTTPS server/topic, no token persistence. |
| Phone transport | Real local TLS/HTTP request, JSON root endpoint, bearer header, valid receipt parsing. |
| Service errors | Authentication rejection, incorrect response, transient retry, retry exhaustion, long Retry-After and connection loss. |
| Desktop adapters | Mac arguments and Windows popup command construction/quoting; no native display in CI. |
| Delivery | Nonblocking operation, parallel channels, partial failure and redacted logs. |
| MATLAB boundary | Fake process success, failure, timeout, missing marker, invalid output, cancellation and unchanged source. |
| Alert timing | Success after validated export, without Check; repeat terminal updates do not notify again. |
| Loop component | Saved True ignored, False arms, final True triggers once, reset and failure signal. |
| Bridge | Current backend transfer, mapping/backup, CSV/JSON result loading and stale-output clearing. |

The GitHub Actions workflow targets Python 3.10/3.13 on macOS, Windows and Ubuntu.
**Those remote runs are pending until the branch is uploaded and Actions runs.**
The fake-process fixtures are POSIX scripts, so those tests skip on Windows;
Windows command construction and platform-independent tests still run there.
Actual MATLAB execution is not claimed by the fake-process tests.

## Device acceptance before client handover

These checks require the target Mac/Windows desktop and the receiving phone.
No device confirmation has been recorded for this release yet.

1. **Desktop:** open settings, enable desktop, press Test desktop. Record whether
   the alert appeared and sound worked. “Submitted” alone is insufficient.
2. **Phone:** configure the generated topic, subscribe, press Test phone. Confirm
   receipt while the phone is unlocked, then locked.
3. **MATLAB reference run:** choose After each MATLAB run, then use your actual
   MATLAB executable path:

   ```bash
   python tools/smoke_test_matlab.py --matlab "/path/to/matlab" --notify
   ```

   Confirm final_displacement=640, generated CSV/JSON and an alert. The tool writes
   smoke_test_evidence.json in the run folder. Check the device yourself too.
4. **Failure:** in a separate copy of a working MATLAB script, add
   `error('HabSim:TestFailure', 'Deliberate test failure');`. Run it through
   component 02 with failure alerts enabled. Expect Failed, no exposed result
   path and one failure alert. Remove the added line afterwards.
5. **Timeout/cancel:** use a temporary script containing `pause(30); x = 1;`,
   request output x and set TimeoutSeconds=2. Expect a timeout failure alert.
   Repeat with a longer timeout and press Cancel: expect Cancelled and no failure
   alert. Other MATLAB sessions must remain unaffected.
6. **Whole loop:** select whole-loop mode. Arm component 04 with False signals;
   run several iterations and confirm no per-run alerts. Send final Done=True
   once. Expect one alert despite repeated recomputes. Reset, then test Failed.
7. **Disabled and network error:** disable the master switch and verify no alert.
   For a phone-only test with the network disconnected, expect a delivery issue;
   the calculation must remain successful and its exported files intact.

Record the device, OS, Python, Rhino and MATLAB versions, settings scope, visible
outcome and relevant evidence/log entry. Remove tokens/topic credentials and
private model data before sharing evidence.

## Submission evidence template

| Check | Device/version | Actual outcome | Evidence | Verified by/date |
| --- | --- | --- | --- | --- |
| Mac desktop | Pending | Pending | Pending | Pending |
| Windows desktop | Pending | Pending | Pending | Pending |
| Phone unlocked/locked | Pending | Pending | Pending | Pending |
| Real MATLAB result 640 | Pending | Pending | Pending | Pending |
| Failure/timeout/cancel | Pending | Pending | Pending | Pending |
| One final loop alert | Pending | Pending | Pending | Pending |

Keep these pending entries honest: a server receipt confirms publishing, not
handset display. Complete the target-device checks before describing the release
as fully accepted by the client.
