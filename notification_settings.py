"""A small settings window, shared by the standalone GUI and Grasshopper GUI."""
import json
import secrets
import tkinter as tk
from tkinter import ttk, messagebox

from habsim_notifications import DEFAULTS, load_settings, save_settings, settings_path, notify_completion


class NotificationSettings(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("HabSim notifications")
        self.resizable(True, False)
        self.minsize(620, 450)
        self.pending = None
        self._poll = None
        warning = ""
        try:
            settings = load_settings()
        except (OSError, ValueError):
            settings = {**DEFAULTS, "enabled": False}
            warning = "Saved settings could not be read. Review and save them again."
        self.fields = {key: (tk.BooleanVar(self, value=value) if isinstance(value, bool)
                            else tk.StringVar(self, value=value)) for key, value in settings.items()}
        frame = ttk.Frame(self, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Know when your results are ready", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Checkbutton(frame, text="Enable notifications", variable=self.fields["enabled"]).pack(anchor="w", pady=(12, 4))
        ttk.Checkbutton(frame, text="Show a desktop alert", variable=self.fields["desktop"]).pack(anchor="w")
        ttk.Checkbutton(frame, text="Play a desktop sound (where supported)", variable=self.fields["sound"]).pack(anchor="w")
        ttk.Checkbutton(frame, text="Also alert me when processing fails", variable=self.fields["failures"]).pack(anchor="w")
        when = ttk.LabelFrame(frame, text="When to notify", padding=8)
        when.pack(fill="x", pady=12)
        ttk.Radiobutton(when, text="After each MATLAB run", variable=self.fields["scope"], value="run").pack(anchor="w")
        ttk.Radiobutton(when, text="Only at the end of the whole loop (requires the Loop Finished block)",
                        variable=self.fields["scope"], value="loop").pack(anchor="w")
        phone = ttk.LabelFrame(frame, text="Optional phone alerts via ntfy", padding=8)
        phone.pack(fill="x")
        phone.columnconfigure(1, weight=1)
        ttk.Checkbutton(phone, text="Send alerts to my subscribed phone topic", variable=self.fields["phone"]).grid(row=0, column=0, columnspan=3, sticky="w")
        for row, key, label in ((1, "server", "Server"), (2, "topic", "Topic")):
            ttk.Label(phone, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(phone, textvariable=self.fields[key], width=42).grid(row=row, column=1, sticky="ew")
        ttk.Button(phone, text="Generate topic", command=lambda: self.fields["topic"].set("habsim-" + secrets.token_hex(16))).grid(row=2, column=2, padx=(8, 0))
        ttk.Label(phone, text="Subscribe to the same server and topic in the ntfy phone app.\n"
                  "Alerts contain only completion/failure status and elapsed time.\n"
                  "Public topics can be read by anyone who knows the topic.\n"
                  "For a protected topic, set HABSIM_NTFY_TOKEN before starting Rhino/Python.",
                  wraplength=570).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.status = tk.StringVar(self, value=warning or "Use Test notification to check your chosen channels.")
        ttk.Label(frame, textvariable=self.status, wraplength=580).pack(fill="x", pady=12)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self.test_button = ttk.Button(buttons, text="Test notification", command=self._test)
        self.test_button.pack(side="left")
        ttk.Button(buttons, text="Recent alerts", command=self._history).pack(side="left", padx=6)
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Save settings", command=self._save).pack(side="right", padx=6)

    def _values(self):
        return {key: var.get() for key, var in self.fields.items()}

    def _save(self):
        try:
            save_settings(self._values())
        except (OSError, ValueError) as exc:
            messagebox.showerror("Notification settings", str(exc), parent=self)
            return False
        self.status.set("Settings saved. They apply to the next completion event.")
        return True

    def _test(self):
        if not self._save():
            return
        self.test_button.configure(state="disabled")
        self.status.set("Sending test notification…")
        self.pending = notify_completion(scope="test")
        self._poll = self.after(100, self._check_test)

    def _check_test(self):
        self._poll = None
        if not self.pending.done.is_set():
            self._poll = self.after(100, self._check_test)
            return
        result = self.pending.result
        detail = "; ".join("%s: %s" % item for item in result["channels"].items())
        self.status.set(result["status"].capitalize() + (" — " + detail if detail else ". No channels enabled.")
                        + (" Check that the alert appeared." if result["status"] == "submitted" else ""))
        self.test_button.configure(state="normal")

    def _history(self):
        window = tk.Toplevel(self)
        window.title("Recent notification attempts")
        text = tk.Text(window, width=88, height=18, wrap="word", padx=10, pady=10)
        text.pack(fill="both", expand=True)
        try:
            lines = settings_path().with_name("notifications.log").read_text(encoding="utf-8").splitlines()[-20:]
            for line in reversed(lines):
                item = json.loads(line)
                text.insert("end", "%s | %s\n%s\n\n" % (item.get("time", ""), item["status"],
                            "; ".join("%s: %s" % pair for pair in item["channels"].items())))
            if not lines:
                text.insert("end", "No notification attempts yet.")
        except (OSError, ValueError, KeyError, TypeError):
            text.insert("end", "No readable notification history yet.")
        text.configure(state="disabled")

    def destroy(self):
        if self._poll is not None:
            self.after_cancel(self._poll)
            self._poll = None
        super().destroy()


def main():
    root = tk.Tk()
    root.withdraw()
    window = NotificationSettings(root)
    root.wait_window(window)
    root.destroy()


if __name__ == "__main__":
    main()
