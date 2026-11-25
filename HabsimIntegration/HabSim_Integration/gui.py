import os
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import gh_bridge
from config import ConfigPanel
from history import HistoryWindow, record_transfer
from format_editor import FormatEditor
from variable_transfer_v2 import (
    read_variables,
    transfer_data,
    update_source_variables,
)

MODES = ["All Variables", "Include Variables", "Exclude Variables"]
STATE_FILE = Path(__file__).resolve().with_name("config_state.json")
BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Grasshopper–HabSim Variable Transfer")
        self.minsize(900, 620)
        self.geometry("1180x780")

        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.status = tk.StringVar(value="Ready")

        # Saved configuration for the next transfer.
        self.config_selected = []
        self.config_mappings = {}
        self.config_signature = None

        self._ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if not self._restore_state():
            self._mode(reset=False)
            self._load()

    def _ui(self):
        main = ttk.Frame(self, padding=14)
        main.grid(sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(4, weight=1)      # the transfer table takes the spare space

        for row, (label, variable, command) in enumerate((
            ("Source file:", self.source, self._browse_source),
            ("Destination file:", self.destination, self._browse_destination),
        )):
            ttk.Label(main, text=label).grid(
                row=row, column=0, sticky="w", pady=5
            )
            ttk.Entry(main, textvariable=variable).grid(
                row=row, column=1, sticky="ew", pady=5
            )
            ttk.Button(main, text="Browse…", command=command).grid(
                row=row, column=2, padx=(8, 0)
            )


        ttk.Label(main, text="Mode:").grid(
            row=2, column=0, sticky="w", pady=5
        )

        box = ttk.Combobox(
            main,
            textvariable=self.mode,
            values=MODES,
            state="readonly",
        )
        box.grid(row=2, column=1, sticky="ew")
        box.bind("<<ComboboxSelected>>", lambda _: self._mode())

        tools = ttk.Frame(main)
        tools.grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=6
        )

        self.tools = tools

        ttk.Button(
            tools,
            text="Save Configuration",
            command=self._save_clicked,
        ).pack(side="left")

        ttk.Button(
            tools,
            text="Reload Source",
            command=self._load,
        ).pack(side="left", padx=6)


        ttk.Label(
            tools,
            text="Fuzzy matches are marked in the table below - check them before saving.",
        ).pack(side="right")

        # The transfer table (what used to be a separate pop-up window) lives here.
        self.var_frame = ttk.LabelFrame(
            main,
            text="Transfer Configuration",
            padding=8,
        )
        self.var_frame.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=6,
        )
        self.var_frame.columnconfigure(0, weight=1)
        self.var_frame.rowconfigure(0, weight=1)

        self.panel = ConfigPanel(self.var_frame, self.mode.get())
        self.panel.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(main)
        actions.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=8,
        )

        ttk.Button(
            actions,
            text="History",
            command=self._history,
        ).pack(side="left")

        ttk.Button(
            actions,
            text="Notifications…",
            command=self._notifications,
        ).pack(side="left", padx=6)

        ttk.Button(
            actions,
            text="Transfer",
            command=self._transfer,
        ).pack(side="right")

        ttk.Separator(main).grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=6,
        )

        ttk.Label(main, text="Status:").grid(
            row=7, column=0, sticky="w"
        )
        ttk.Label(
            main,
            textvariable=self.status,
        ).grid(row=7, column=1, columnspan=2, sticky="w")

    def _choose(self, title, include_json=False):
        patterns = "*.py *.m *.txt *.csv"
        if include_json:
            patterns += " *.json"

        filetypes = [("Supported", patterns)]
        if include_json:
            filetypes.append(("JSON file", "*.json"))
        filetypes.append(("All files", "*.*"))

        return filedialog.askopenfilename(
            title=title,
            filetypes=filetypes,
        )

    def _open_formats(self):
            FormatEditor(self, gh_bridge.FORMATS_FILE, gh_bridge.load_raw(),
                         self._formats_saved)

    def _formats_saved(self):
            """Formats changed: convert the Grasshopper values again and refresh the list."""
            if not gh_bridge.load_raw():
                self.status.set("Formats saved. They will be used on the next transfer.")
                return
            try:
                final, skipped = gh_bridge.render_source(self.renames, self.gh_source)
            except ValueError as error:
                messagebox.showerror("Value Formats", str(error), parent=self)
                return
            self._load()
            self.status.set("Formats saved: %d variable(s) converted again." % len(final))
            if skipped:
                messagebox.showwarning(
                    "Value Formats",
                    "These variables can't be sent with the current formats:\n\n"
                    + "\n".join(skipped), parent=self)

    def _browse_source(self):
        path = self._choose("Choose source file", include_json=True)

        if path:
            self.source.set(path)
            self._reset_configuration()
            self._load()
            self._save_state()

            if self.destination.get().strip():
                self._config()

    def _browse_destination(self):
        path = self._choose("Choose destination file")

        if path:
            self.destination.set(path)
            self._reset_configuration()
            self.status.set(
                f"Destination: {os.path.basename(path)}"
            )
            self._save_state()
            self._load()

            # Check both files as soon as both exist.
            if os.path.isfile(self.source.get().strip()):
                self.after(100, self._config)

    def _variables(self):
        path = self.source.get().strip()

        if not os.path.isfile(path):
            return {}

        try:
            return read_variables(path)
        except (OSError, UnicodeError):
            return {}

    def _destination_variables(self):
        path = self.destination.get().strip()

        if not os.path.isfile(path):
            return {}

        try:
            return read_variables(path)
        except (OSError, UnicodeError):
            return {}

    def _load(self):
        """Read both files again and rebuild the transfer table."""
        source = self._variables()
        destination = self._destination_variables()
        saved = self.config_signature == self._current_signature()

        self.panel.load(
            source,
            destination,
            self.config_selected if saved else None,
            self.config_mappings if saved else None,
        )

        if source and destination:
            self.status.set(
                f"Loaded {len(source)} source variable(s) and "
                f"{len(destination)} destination variable(s)."
            )
        elif not source:
            self.status.set("Choose a valid source file.")
        else:
            self.status.set("Choose a valid destination file.")

    def _mode(self, reset=True):
        self.panel.set_mode(self.mode.get())

        if reset:
            self._reset_configuration()
            self._save_state()

    def _save_state(self):
        state = {
            "source": self.source.get().strip(),
            "destination": self.destination.get().strip(),
            "mode": self.mode.get(),
            "selected": self.config_selected,
            "mappings": self.config_mappings,
        }
        try:
            STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _restore_state(self):
        if not STATE_FILE.exists():
            return False

        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False

        self.source.set(state.get("source", ""))
        self.destination.set(state.get("destination", ""))
        self.mode.set(state.get("mode") if state.get("mode") in MODES else MODES[0])

        source = self._variables()
        destination = self._destination_variables()

        selected = [
            name for name in state.get("selected", [])
            if name in source
        ]
        mappings = {
            source_name: destination_name
            for source_name, destination_name in state.get("mappings", {}).items()
            if source_name in source and destination_name in destination
        }

        self.config_selected = selected
        self.config_mappings = mappings
        self.config_signature = (
            self._current_signature()
            if mappings
            else None
        )

        self._mode(reset=False)
        self._load()

        if self.config_signature:
            self.status.set(
                f"Last saved state restored: {len(selected)} variable(s), "
                f"{len(mappings)} link(s)."
            )
        elif self.source.get() or self.destination.get():
            self.status.set("Previous files restored. Configuration needs review.")

        return True

    def _close(self):
        self._save_state()
        self.destroy()

    def _reset_configuration(self):
        self.config_selected = []
        self.config_mappings = {}
        self.config_signature = None

    def _current_signature(self):
        return (
            os.path.abspath(self.source.get().strip())
            if self.source.get().strip()
            else "",
            os.path.abspath(self.destination.get().strip())
            if self.destination.get().strip()
            else "",
            self.mode.get(),
        )

    def _config(self):
        """Check both files and rebuild the transfer table (it used to open a pop-up)."""
        source = self._variables()
        destination = self._destination_variables()

        if not source:
            messagebox.showerror(
                "Configuration",
                "Choose a valid source file first.",
            )
            return

        if not destination:
            messagebox.showerror(
                "Configuration",
                "Choose a valid destination file first.",
            )
            return

        self._load()

    def _apply_config(self):
        """Check the table and save it as the configuration. True if it was saved."""
        result = self.panel.collect()
        if result is None:
            return False
        return self._save_config(*result) is not False

    def _save_clicked(self):
        self._apply_config()

    def _save_config(self, selected, mappings, source_changes):
        try:
            update_source_variables(self.source.get().strip(), source_changes)
        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror("Configuration error", str(error), parent=self)
            return False

        self.config_selected = list(selected)
        self.config_mappings = dict(mappings)
        self.config_signature = self._current_signature()
        self._load()
        self._save_state()

        unlinked = getattr(self.panel, "last_unlinked", 0)
        self.status.set(
            f"Configuration saved: {len(mappings)} link(s)"
            + (f", {unlinked} variable(s) not linked" if unlinked else "")
            + ". Source variables updated."
        )
        return True

    def _history(self):
        HistoryWindow(self, self._after_revert)

    def _notifications(self):
        from notification_settings import NotificationSettings
        NotificationSettings(self)

    def _after_revert(self):
        self._load()
        self.status.set("History revert complete.")

    def _transfer(self):
        source_path = self.source.get().strip()
        destination_path = self.destination.get().strip()

        if (
            not os.path.isfile(source_path)
            or not os.path.isfile(destination_path)
        ):
            messagebox.showerror(
                "Transfer",
                "Choose valid source and destination files.",
            )
            return

        if os.path.abspath(source_path) == os.path.abspath(destination_path):
            messagebox.showerror(
                "Transfer",
                "Source and destination must be different.",
            )
            return

        # Whatever is in the table is saved first.
        if not self._apply_config():
            return

        if BACKEND[self.mode.get()] != "exclude" and not self.config_selected:
            messagebox.showwarning(
                "Transfer",
                "No variables are selected.",
            )
            return

        try:
            result = transfer_data(
                source_path,
                destination_path,
                BACKEND[self.mode.get()],
                self.config_selected,
                mappings=self.config_mappings,
                apply=False,
            )
        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror(
                "Transfer error",
                str(error),
            )
            return

        # Confirm before making changes.
        changed = len(result["changes"])
        transferred = len(result["transferred"])
        missing = result["missing_in_destination"]

        summary = (
            f"Transfer {transferred} variable(s)?\n\n"
            f"Values that will change: {changed}\n"
        )

        if missing:
            summary += (
                "\nThe following destination variables were not found:\n"
                + ", ".join(missing)
                + "\n\nThey will NOT be transferred."
            )

        if not messagebox.askyesno(
            "Confirm Transfer",
            summary,
            parent=self,
        ):
            self.status.set("Transfer cancelled.")
            return

        try:
            # Re-run after confirmation so the file is changed only here.
            result = transfer_data(
                source_path,
                destination_path,
                BACKEND[self.mode.get()],
                self.config_selected,
                mappings=self.config_mappings,
            )

            record_transfer(
                source_path,
                destination_path,
                self.mode.get(),
                self.config_selected,
                result["transferred"],
                result["changes"],
                result["mappings"],
            )
        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror(
                "Transfer error",
                str(error),
            )
            return

        changed = len(result["changes"])
        missing = result["missing_in_destination"]

        self.status.set(
            f"Transfer complete: {changed} value(s) changed."
        )

        message = (
            f"Transferred {len(result['transferred'])} variable(s).\n"
            f"Changed {changed} value(s)."
        )

        if missing:
            message += (
                "\n\nNot found in destination:\n"
                + ", ".join(missing)
            )

        messagebox.showinfo(
            "Transfer complete",
            message,
            parent=self,
        )