"""Completion alerts for MATLAB runs and final Grasshopper loop signals.

Python 3.9+, standard library only. No Rhino or Tkinter imports.
Phone delivery is opt-in; messages contain no model data, paths or error text.
"""
import base64
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from urllib import error, parse, request

DEFAULTS = {
    "enabled": True,
    "desktop": True,
    "sound": True,
    "phone": False,
    "failures": True,
    "scope": "run",
    "server": "https://ntfy.sh",
    "topic": "",
}
_LOG_LOCK = threading.Lock()


def settings_path():
    override = os.environ.get("HABSIM_NOTIFICATION_SETTINGS")
    return Path(override).expanduser() if override else Path.home() / "CapstoneGH" / "notification_settings.json"


def validate_settings(values):
    if not isinstance(values, dict):
        raise ValueError("Notification settings must be a JSON object.")
    result = dict(DEFAULTS)
    result.update({key: value for key, value in values.items() if key in DEFAULTS})
    for key in ("enabled", "desktop", "sound", "phone", "failures"):
        if not isinstance(result[key], bool):
            raise ValueError("%s must be true or false." % key)
    if result["scope"] not in ("run", "loop"):
        raise ValueError("Choose notifications after a MATLAB run or after the whole loop.")
    for key in ("server", "topic"):
        if not isinstance(result[key], str):
            raise ValueError("%s must be text." % key)
        result[key] = result[key].strip()
    result["server"] = result["server"].rstrip("/")
    if result["phone"]:
        url = parse.urlsplit(result["server"])
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")):
            raise ValueError("Enter the HTTPS server address only, such as https://ntfy.sh.")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", result["topic"]):
            raise ValueError("The phone topic needs 1–64 letters, numbers, underscores or hyphens.")
    return result


def load_settings(path=None):
    path = Path(path) if path is not None else settings_path()
    if not path.exists():
        return dict(DEFAULTS)
    with path.open(encoding="utf-8") as stream:
        return validate_settings(json.load(stream))


def save_settings(values, path=None):
    values = validate_settings(values)
    path = Path(path) if path is not None else settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replacement avoids reading half a configuration from Grasshopper.
    fd, name = tempfile.mkstemp(prefix=".notification-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(values, stream, indent=2)
            stream.write("\n")
        os.replace(name, str(path))
    finally:
        if os.path.exists(name):
            os.remove(name)
    return path


def _duration(seconds):
    if seconds is None:
        return ""
    seconds = float(seconds)
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError("Elapsed time must be a finite, non-negative number.")
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return ("%dh %dm %ds" % (hours, minutes, seconds) if hours else
            "%dm %ds" % (minutes, seconds) if minutes else "%ds" % seconds)


def notification_text(success, scope, elapsed_seconds=None, variable_count=None):
    if scope == "test":
        return "HabSim test notification", "Notifications are set up. You can return to your work."
    subject = "MATLAB run" if scope == "run" else "Processing loop"
    elapsed = _duration(elapsed_seconds)
    if success:
        title = "HabSim - %s complete" % subject
        body = "%s finished%s." % (subject, " after " + elapsed if elapsed else "")
        if variable_count is not None:
            body += " %d result variable(s) loaded." % int(variable_count)
        body += " Your results are ready on the computer."
    else:
        title = "HabSim - %s needs attention" % subject
        body = "%s stopped%s. Check the Status message or run log on your computer." % (
            subject, " after " + elapsed if elapsed else "")
    return title, body


def _desktop(title, body, sound):
    if sys.platform == "darwin":
        # Text is passed as argv, never interpolated into executable AppleScript.
        script = '''on run argv
    if item 3 of argv is "yes" then
        display notification (item 2 of argv) with title (item 1 of argv) sound name "Glass"
    else
        display notification (item 2 of argv) with title (item 1 of argv)
    end if
end run'''
        subprocess.run(["osascript", "-e", script, title, body, "yes" if sound else "no"],
                       capture_output=True, check=True, timeout=10)
    elif sys.platform == "win32":
        # A timed native popup runs in its own process; MATLAB/GH never wait for OK.
        # Base64 is data quoting, not an execution-policy override.
        payload = base64.b64encode(json.dumps([title, body]).encode("utf-8")).decode("ascii")
        script = "$p = ConvertFrom-Json ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s'))); " % payload
        if sound:
            script += "[System.Media.SystemSounds]::Asterisk.Play(); "
        script += "$w = New-Object -ComObject WScript.Shell; $null = $w.Popup($p[1], 15, $p[0], 4096)"
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                       capture_output=True, check=True, timeout=25,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        cmd = ["notify-send", "--app-name=HabSim", "--expire-time=15000"]
        if not sound:
            cmd.append("--hint=boolean:suppress-sound:true")
        subprocess.run(cmd + ["--", title, body], capture_output=True, check=True, timeout=10)


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward a phone token or topic to a different address.
        return None


def _phone(title, body, settings):
    data = json.dumps({"topic": settings["topic"], "title": title,
                       "message": body, "tags": ["information_source"]}).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    token = os.environ.get("HABSIM_NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = request.Request(settings["server"] + "/", data=data, headers=headers, method="POST")
    opener = request.build_opener(_NoRedirect())
    with opener.open(req, timeout=10) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError("Phone service did not accept the notification.")


def _error_message(exc):
    # No exception bodies, URLs, tokens, file paths or model contents in the log.
    if isinstance(exc, error.HTTPError):
        return "Phone service returned HTTP %s; check topic permissions and server settings." % exc.code
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return "Notification attempt timed out."
    if isinstance(exc, FileNotFoundError):
        return "Desktop notification tool is unavailable on this computer."
    return "%s; check notification settings and permissions." % type(exc).__name__


def _record(result):
    try:
        path = settings_path().with_name("notifications.log")
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), **result}
        with _LOG_LOCK:
            if path.exists() and path.stat().st_size > 256 * 1024:
                os.replace(str(path), str(path.with_suffix(".log.1")))
            with path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry) + "\n")
    except Exception:
        pass  # Logging must never change a simulation's outcome.


class Delivery:
    """Background delivery receipt. 'submitted' does not guarantee a visible alert."""
    def __init__(self):
        self.done = threading.Event()
        self.queued = False
        self.result = {"status": "queued", "channels": {}}

    def wait(self, timeout=None):
        self.done.wait(timeout)
        return self.result


def notify_completion(success=True, elapsed_seconds=None, variable_count=None,
                      scope="run", settings=None):
    """Queue one alert, returning immediately. Never raises into a simulation.

    scope='run' hooks the MATLAB runner; scope='loop' hooks the final loop signal.
    Settings select one scope, preventing per-iteration alerts in loop mode.
    scope='test' bypasses only the scope/failure filters, not the enabled switch.
    """
    delivery = Delivery()
    try:
        config = validate_settings(settings) if settings is not None else load_settings()
        if scope not in ("run", "loop", "test"):
            raise ValueError("Invalid notification scope.")
        if (not config["enabled"] or (scope != "test" and scope != config["scope"])
                or (scope != "test" and not success and not config["failures"])):
            delivery.result = {"status": "disabled", "channels": {}}
            delivery.done.set()
            return delivery
        title, body = notification_text(success, scope, elapsed_seconds, variable_count)

        def work():
            channels = {}

            def attempt(name, fn):
                try:
                    fn()
                    channels[name] = "submitted"
                except Exception as exc:
                    channels[name] = _error_message(exc)

            jobs = []
            if config["desktop"]:
                jobs.append(("desktop", lambda: _desktop(title, body, config["sound"])))
            if config["phone"]:
                jobs.append(("phone", lambda: _phone(title, body, config)))
            # A Windows popup awaiting dismissal must not delay the phone alert.
            workers = [threading.Thread(target=attempt, args=job, daemon=True) for job in jobs]
            started = []
            try:
                for thread in workers:
                    thread.start()
                    started.append(thread)
            except Exception as exc:
                channels["worker"] = _error_message(exc)
            finally:
                for thread in started:
                    thread.join()
                status = ("disabled" if not jobs else "submitted"
                          if all(value == "submitted" for value in channels.values()) else "delivery issue")
                delivery.result = {"status": status, "title": title, "channels": channels}
                _record(delivery.result)
                delivery.done.set()

        delivery.queued = True
        threading.Thread(target=work, daemon=True).start()
    except Exception as exc:
        delivery.queued = False
        delivery.result = {"status": "delivery issue", "channels": {"settings": _error_message(exc)}}
        _record(delivery.result)
        delivery.done.set()
    return delivery


def completion_transition(state, done, failed=False):
    """Arm on False/False; fire once on completion, then latch until reset.

    Saved True inputs on opening a GH definition do not send a false alert.
    State is a plain dict suitable for scriptcontext.sticky across recomputes.
    """
    terminal = bool(done) or bool(failed)
    if not terminal:
        state["phase"] = "armed"
        return None
    if state.get("phase") == "armed":
        state["phase"] = "notified"
        return "failure" if failed else "success"
    state["phase"] = "notified"
    return None


if __name__ == "__main__":
    if sys.argv[1:] != ["--test"]:
        sys.exit("Use: python habsim_notifications.py --test\nSettings: python notification_settings.py")
    receipt = notify_completion(scope="test")
    print(json.dumps(receipt.wait(30), indent=2))
    sys.exit(0 if receipt.result["status"] in ("submitted", "disabled") else 1)
