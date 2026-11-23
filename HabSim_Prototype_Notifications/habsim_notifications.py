"""Completion alerts for MATLAB runs and final Grasshopper loop signals.

Python 3.9+, standard library only. No Rhino or Tkinter imports.
Phone delivery is opt-in; messages contain no model data, paths or error text.
"""
import base64
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
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
_PHONE_ATTEMPTS = 3
_MAX_RETRY_DELAY = 5


class NotificationError(Exception):
    """A user-readable delivery error containing no private service response."""


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
        try:
            url.port
        except ValueError:
            raise ValueError("The phone server has an invalid port.") from None
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
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        raise ValueError("Elapsed time must be a finite, non-negative number.") from None
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
            if isinstance(variable_count, bool) or not isinstance(variable_count, int) or variable_count < 0:
                raise ValueError("Result count must be a non-negative integer.")
            body += " %d result variable(s) exported." % variable_count
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
    opener = request.build_opener(_NoRedirect())
    for attempt in range(1, _PHONE_ATTEMPTS + 1):
        req = request.Request(settings["server"] + "/", data=data, headers=headers, method="POST")
        try:
            with opener.open(req, timeout=10) as response:
                if not 200 <= response.status < 300:
                    raise NotificationError("Phone service did not accept the notification.")
                try:
                    payload = json.loads(response.read(65537).decode("utf-8"))
                except (ValueError, UnicodeError):
                    raise NotificationError("The server returned an unexpected response; check the ntfy server address.") from None
                if (not isinstance(payload, dict) or payload.get("event") != "message"
                        or payload.get("topic") != settings["topic"]
                        or not isinstance(payload.get("id"), str) or not payload["id"]
                        or len(payload["id"]) > 128):
                    raise NotificationError("The server did not return a valid ntfy publishing receipt.")
                return {"attempts": attempt, "message_id": payload["id"]}
        except error.HTTPError as exc:
            # Retry explicit transient rejection only. A connection loss may
            # occur after acceptance, so it is not retried automatically.
            if exc.code not in (429, 502, 503, 504) or attempt == _PHONE_ATTEMPTS:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                delay = float(retry_after) if retry_after else 2 ** (attempt - 1)
            except ValueError:
                raise exc  # Unknown server instructions: let the user retry later.
            if not math.isfinite(delay) or not 0 <= delay <= _MAX_RETRY_DELAY:
                raise
            exc.close()
            time.sleep(delay)


def _error_message(exc):
    # No exception bodies, URLs, tokens, file paths or model contents in the log.
    if isinstance(exc, NotificationError):
        return str(exc)
    if isinstance(exc, error.HTTPError):
        advice = {401: "check the publishing token", 403: "check token and topic permissions",
                  404: "check the ntfy server address", 429: "rate limit reached; wait before retrying"}
        return "Phone service returned HTTP %s; %s." % (exc.code, advice.get(exc.code, "try again later"))
    if isinstance(exc, error.URLError):
        return "Cannot reach the phone service; check internet access and the HTTPS server."
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
                      scope="run", settings=None, only_channel=None):
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
        if only_channel not in (None, "desktop", "phone"):
            raise ValueError("Choose the desktop or phone test channel.")
        if (not config["enabled"] or (scope != "test" and scope != config["scope"])
                or (scope != "test" and not success and not config["failures"])):
            delivery.result = {"status": "disabled", "channels": {},
                               "reason": "Notifications, this outcome, or this run/loop scope are disabled in settings."}
            delivery.done.set()
            return delivery
        if not any(config[name] and only_channel in (None, name) for name in ("desktop", "phone")):
            delivery.result = {"status": "disabled", "channels": {},
                               "reason": "Enable the selected delivery channel in notification settings first."}
            delivery.done.set()
            return delivery
        title, body = notification_text(success, scope, elapsed_seconds, variable_count)

        def work():
            channels = {}
            details = {}

            def attempt(name, fn):
                try:
                    metadata = fn()
                    if metadata:
                        details[name] = metadata
                    channels[name] = "submitted"
                except Exception as exc:
                    channels[name] = _error_message(exc)

            jobs = []
            if config["desktop"] and only_channel in (None, "desktop"):
                jobs.append(("desktop", lambda: _desktop(title, body, config["sound"])))
            if config["phone"] and only_channel in (None, "phone"):
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
                status = ("submitted" if all(value == "submitted" for value in channels.values())
                          else "partial" if "submitted" in channels.values() else "delivery issue")
                delivery.result = {"status": status, "title": title, "channels": channels, "details": details}
                _record(delivery.result)
                delivery.done.set()

        delivery.queued = True
        threading.Thread(target=work, daemon=True).start()
    except Exception as exc:
        delivery.queued = False
        detail = str(exc) if isinstance(exc, ValueError) else _error_message(exc)
        # Validation messages above are controlled text; JSON errors can reveal
        # fragments of a malformed private settings file, so keep those generic.
        if isinstance(exc, json.JSONDecodeError):
            detail = "Saved settings are not valid JSON. Open Notifications and save them again."
        delivery.result = {"status": "delivery issue", "channels": {"settings": detail}}
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


def diagnostics():
    """Local configuration check. No network requests and no secret/token output."""
    result = {"python": sys.version.split()[0], "python_executable": sys.executable,
              "platform": sys.platform, "settings_file": str(settings_path()),
              "token_available": bool(os.environ.get("HABSIM_NTFY_TOKEN", "").strip()),
              "tkinter_module_available": importlib.util.find_spec("tkinter") is not None}
    try:
        config = load_settings()
        result.update(settings_valid=True, enabled=config["enabled"], desktop=config["desktop"],
                      phone=config["phone"], scope=config["scope"], topic_configured=bool(config["topic"]))
    except (OSError, ValueError):
        result.update(settings_valid=False, problem="Open notification settings and save a valid configuration.")
    if sys.platform == "darwin" and "/Xcode.app/" in sys.executable:
        result["advice"] = "Use python.org Python 3.13 or newer for GUI windows; Xcode's Python can abort in Tk on macOS 26."
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="HabSim desktop and ntfy phone notifications (no Tkinter needed).")
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Check configuration without sending anything")
    action.add_argument("--test", action="store_true", help="Send a test through enabled channels")
    parser.add_argument("--channel", choices=("desktop", "phone"), help="Test only one enabled channel")
    parser.add_argument("--settings-file", help="Use a particular local settings JSON file")
    args = parser.parse_args(argv)
    if args.settings_file:
        os.environ["HABSIM_NOTIFICATION_SETTINGS"] = str(Path(args.settings_file).expanduser().resolve())
    if args.check:
        result = diagnostics()
        print(json.dumps(result, indent=2))
        return 0 if result["settings_valid"] else 2
    receipt = notify_completion(scope="test", only_channel=args.channel)
    result = receipt.wait(45)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "submitted" else 2 if result["status"] == "disabled" else 1


if __name__ == "__main__":
    sys.exit(main())
