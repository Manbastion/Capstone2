"""Small standalone HabSim launcher; also the Windows executable entry point.

Runs an already prepared MATLAB script. It does not perform Grasshopper input
transfer or drive an outer Grasshopper loop. No pip packages at runtime.
"""
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from grasshopper_components import matlab_runner
from habsim_notifications import load_settings, settings_path
from habsim_runtime import external_environment, find_matlab, prepare_frozen_process
from notification_settings import NotificationSettings

RESOURCE_DIR = Path(__file__).resolve().parent


def client_settings_path():
    return settings_path().with_name("client_settings.json")


def load_client_settings():
    defaults = {"matlab": find_matlab(), "script": "",
                "output": str(settings_path().parent / "runs"), "minutes": "1440"}
    path = client_settings_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Saved launcher settings must be an object.")
        for key in defaults:
            if key in data:
                if not isinstance(data[key], str):
                    raise ValueError("Saved launcher settings contain an invalid value.")
                defaults[key] = data[key]
    return defaults


def save_client_settings(values):
    path = client_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".client-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(values, stream, indent=2)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def open_local(path):
    path = Path(path)
    if not path.exists():
        raise ValueError("This file or folder does not exist yet: " + str(path))
    if sys.platform == "win32":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                         env=external_environment())


class Client(ttk.Frame):
    def __init__(self, root):
        super().__init__(root, padding=20)
        self.root, self.job, self.closing, self.after_id = root, None, False, None
        self.settings_window = None
        root.title("HabSim — Run and notify")
        root.minsize(760, 570)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.pack(fill="both", expand=True)
        self.columnconfigure(1, weight=1)
        warning = ""
        try:
            values = load_client_settings()
        except (OSError, ValueError):
            values = {"matlab": find_matlab(), "script": "",
                      "output": str(settings_path().parent / "runs"), "minutes": "1440"}
            warning = "Saved launcher settings could not be read. Choose your files again."
        self.fields = {key: tk.StringVar(root, value=value) for key, value in values.items()}
        self.controls = []
        ttk.Label(self, text="Run MATLAB. Get an alert when it finishes.",
                  font=("TkDefaultFont", 15, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(self, text="Use the .m script prepared by your project team. Your choices are remembered.",
                  wraplength=690).grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 16))
        self.path_row(2, "MATLAB script", "script", self.choose_script)
        self.path_row(3, "Results folder", "output", self.choose_output)
        self.path_row(4, "MATLAB program", "matlab", self.choose_matlab)
        ttk.Label(self, text="Time limit (minutes)").grid(row=5, column=0, sticky="w", pady=8)
        limit = ttk.Entry(self, textvariable=self.fields["minutes"], width=10)
        limit.grid(row=5, column=1, sticky="w")
        self.controls.append(limit)
        ttk.Label(self, text="Default: 24 hours. Cancel stops only the MATLAB process started here.",
                  wraplength=680).grid(row=6, column=0, columnspan=3, sticky="w")
        buttons = ttk.Frame(self)
        buttons.grid(row=7, column=0, columnspan=3, sticky="ew", pady=18)
        self.run_button = ttk.Button(buttons, text="Run MATLAB", command=self.run)
        self.run_button.pack(side="left", padx=(0, 8))
        self.controls.append(self.run_button)
        self.cancel_button = ttk.Button(buttons, text="Cancel run", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Notification settings / Test", command=self.notifications).pack(side="left")
        demo = ttk.Button(buttons, text="Use demo", command=self.demo)
        demo.pack(side="right")
        self.controls.append(demo)
        self.status = tk.StringVar(root, value=warning or "Ready. Test your notifications, then choose a script and click Run MATLAB.")
        ttk.Label(self, textvariable=self.status, wraplength=690, justify="left").grid(
            row=8, column=0, columnspan=3, sticky="ew", pady=6)
        self.progress = ttk.Progressbar(self, mode="indeterminate")
        self.progress.grid(row=9, column=0, columnspan=3, sticky="ew", pady=8)
        self.alert_status = tk.StringVar(root, value="Notifications: no run yet.")
        ttk.Label(self, textvariable=self.alert_status, wraplength=690).grid(
            row=10, column=0, columnspan=3, sticky="ew", pady=4)
        links = ttk.Frame(self)
        links.grid(row=11, column=0, columnspan=3, sticky="w", pady=12)
        self.results_button = ttk.Button(links, text="Open results", command=self.open_results, state="disabled")
        self.results_button.pack(side="left", padx=(0, 8))
        self.log_button = ttk.Button(links, text="Open run log", command=self.open_log, state="disabled")
        self.log_button.pack(side="left", padx=(0, 8))
        ttk.Button(links, text="Open help", command=self.show_help).pack(side="left")
        ttk.Label(self, text="This app runs the selected script and exports its workspace as JSON.\n"
                  "Use your team's prepared Grasshopper file for variable transfer and geometry updates.",
                  wraplength=690).grid(row=12, column=0, columnspan=3, sticky="w", pady=8)

    def path_row(self, row, label, key, command):
        ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=8)
        entry = ttk.Entry(self, textvariable=self.fields[key])
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 8))
        button = ttk.Button(self, text="Browse…", command=command)
        button.grid(row=row, column=2)
        self.controls.extend((entry, button))

    def choose_script(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose the prepared MATLAB script",
                                          filetypes=[("MATLAB script", "*.m")])
        if path:
            self.fields["script"].set(path)

    def choose_output(self):
        path = filedialog.askdirectory(parent=self.root, title="Choose the results folder")
        if path:
            self.fields["output"].set(path)

    def choose_matlab(self):
        path = filedialog.askopenfilename(parent=self.root, title="Choose MATLAB's bin/matlab.exe (bin/matlab on Mac)")
        if path:
            self.fields["matlab"].set(path)

    def notifications(self):
        if self.settings_window is None or not self.settings_window.winfo_exists():
            self.settings_window = NotificationSettings(self.root)
        self.settings_window.lift()

    def demo(self):
        # A working copy keeps bundled resources and the real model untouched.
        folder = settings_path().parent / "demo"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / "workflow_demo.m"
        shutil.copy2(RESOURCE_DIR / "examples/notification_demo/workflow_demo.m", destination)
        self.fields["script"].set(str(destination))
        self.status.set("Demo selected. Click Run MATLAB. The unmodified demo's final_displacement should be 50.")

    def busy(self):
        if self.job is None:
            return False
        receipt = self.job.get("notification")
        return self.job["worker"].is_alive() or (receipt is not None and not receipt.done.is_set())

    def run(self):
        if self.busy():
            return
        # A rejected new request must not leave the previous run's result button active.
        self.job = None
        self.results_button.configure(state="disabled")
        self.log_button.configure(state="disabled")
        self.alert_status.set("Notifications: no run started.")
        try:
            preferences = load_settings()
            if preferences["enabled"] and preferences["scope"] == "loop":
                self.notifications()
                raise ValueError("Choose 'After each MATLAB run' and save settings. This standalone app does not drive a Grasshopper loop.")
            values = {key: var.get().strip() for key, var in self.fields.items()}
            timeout = float(values["minutes"]) * 60
            output = Path(values["output"]).expanduser()
            if not values["output"] or not output.is_absolute():
                raise ValueError("Choose a full path for the results folder.")
            output.mkdir(parents=True, exist_ok=True)
            # Save before launch so a settings error cannot leave an untracked process.
            save_client_settings(values)
            self.job = matlab_runner.start_job(values["matlab"], values["script"], [], output,
                                               timeout, export_mode="workspace")
        except (OSError, ValueError) as error:
            logging.exception("Cannot start MATLAB")
            self.status.set("Not started: " + str(error))
            messagebox.showerror("MATLAB did not start", str(error), parent=self.root)
            return
        for control in self.controls:
            control.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.log_button.configure(state="normal")
        self.results_button.configure(state="disabled")
        self.progress.start(12)
        self.poll()

    def poll(self):
        self.after_id = None
        state = matlab_runner.job_status(self.job)
        running = state["state"] == "Running"
        text = "Running MATLAB ({:.0f} seconds)…".format(state["elapsed_seconds"]) if running else state["state"] + ": " + state["message"]
        if state["state"] in ("Failed", "Timed out"):
            text += " Click Open run log for the MATLAB error."
        self.status.set(text)
        receipt = self.job.get("notification")
        if receipt is not None:
            result = receipt.result
            detail = "; ".join("{}: {}".format(k, v) for k, v in result.get("channels", {}).items())
            self.alert_status.set("Notifications: " + result["status"] + (" — " + detail if detail else " — " + result.get("reason", "")))
        else:
            self.alert_status.set("Notifications: waiting for completion." if running else "Notifications: not requested.")
        if self.busy():
            if not running:
                self.cancel_button.configure(state="disabled")
            self.after_id = self.after(200, self.poll)
            return
        self.progress.stop()
        self.cancel_button.configure(state="disabled")
        for control in self.controls:
            control.configure(state="normal")
        if state["state"] == "Succeeded":
            self.results_button.configure(state="normal")
        if self.closing:
            if self.settings_window is not None and self.settings_window.winfo_exists():
                pending = self.settings_window.pending
                if pending is not None and not pending.done.is_set():
                    self.after_id = self.after(200, self.poll)
                    return
            self.root.destroy()

    def cancel(self):
        if self.job is not None:
            matlab_runner.cancel_job(self.job)
            self.status.set("Stopping this MATLAB run…")
            self.cancel_button.configure(state="disabled")

    def open_results(self):
        open_local(self.job["directory"])

    def open_log(self):
        self.show_text("MATLAB run log", self.job["directory"] / "matlab.log")

    def show_help(self):
        self.show_text("HabSim help", RESOURCE_DIR / "CLIENT_START_HERE.md")

    def show_text(self, title, path):
        # No dependency on Windows file associations for .md / .log files.
        with Path(path).open("rb") as stream:
            stream.seek(0, 2)
            truncated = stream.tell() > 256 * 1024
            stream.seek(max(0, stream.tell() - 256 * 1024))
            content = stream.read().decode("utf-8", errors="replace")
        window = tk.Toplevel(self.root)
        window.title(title)
        window.geometry("800x560")
        ttk.Label(window, text=str(path), wraplength=760, padding=10).pack(fill="x")
        text = tk.Text(window, wrap="word", padx=12, pady=12)
        scroll = ttk.Scrollbar(window, command=text.yview)
        scroll.pack(side="right", fill="y")
        text.configure(yscrollcommand=scroll.set)
        text.pack(fill="both", expand=True)
        text.insert("end", ("Showing the last 256 KiB.\n\n" if truncated else "") + content)
        text.configure(state="disabled")

    def close(self):
        if self.busy():
            if messagebox.askyesno("Run in progress", "Stop this run and close? If MATLAB has finished, pending notifications will complete first.", parent=self.root):
                self.closing = True
                self.cancel()
            return
        if self.settings_window is not None and self.settings_window.winfo_exists():
            receipt = self.settings_window.pending
            if receipt is not None and not receipt.done.is_set():
                messagebox.showinfo("Notification test", "Wait for the notification test to finish before closing.", parent=self.root)
                return
        self.root.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", action="store_true", help="Open notification settings only")
    parser.add_argument("--self-test", metavar="REPORT", help="Check bundled GUI/resources; sends no alerts and runs no MATLAB")
    args = parser.parse_args(argv)
    root = None
    try:
        log_path = settings_path().with_name("client_startup.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(level=logging.INFO, handlers=[RotatingFileHandler(
            log_path, maxBytes=256 * 1024, backupCount=1, encoding="utf-8")])
        root = tk.Tk()
        prepare_frozen_process()

        def callback_error(kind, error, traceback):
            logging.error("Window action failed", exc_info=(kind, error, traceback))
            messagebox.showerror("HabSim", "{}\n\nDetails: {}".format(error, log_path), parent=root)
        root.report_callback_exception = callback_error
        if args.self_test:
            root.withdraw()
            Client(root)
            settings = NotificationSettings(root)
            settings.withdraw()
            root.update_idletasks()
            assert (RESOURCE_DIR / "examples/notification_demo/workflow_demo.m").is_file()
            assert (RESOURCE_DIR / "CLIENT_START_HERE.md").is_file()
            Path(args.self_test).write_text(json.dumps({"status": "passed", "gui": True,
                "frozen": bool(getattr(sys, "frozen", False)), "python": sys.version,
                "matlab_executed": False, "notifications_sent": False}, indent=2), encoding="utf-8")
            settings.destroy()
            root.destroy()
            return 0
        if args.settings:
            root.withdraw()
            window = NotificationSettings(root)
            root.wait_window(window)
            root.destroy()
        else:
            Client(root)
            root.mainloop()
        return 0
    except Exception as error:
        logging.exception("HabSim startup failed")
        message = "HabSim could not start.\n{}\n\nSee ~/CapstoneGH/client_startup.log (or the configured settings folder).".format(error)
        if args.self_test:
            Path(args.self_test).write_text(json.dumps({"status": "failed", "error": str(error)}), encoding="utf-8")
        if sys.platform == "win32" and not args.self_test:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "HabSim startup problem", 0x10)
        elif sys.stderr is not None:
            print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
