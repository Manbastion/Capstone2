import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from config import ConfigEditor
from history import HistoryWindow, record_transfer
from variable_transfer_v2 import read_variables, transfer_data

MODES = ["All Variables", "Include Variables", "Exclude Variables"]
BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Grasshopper–HabSim Variable Transfer")
        self.minsize(820, 560)
        self.geometry("980x650")

        self.source = tk.StringVar()
        self.destination = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.status = tk.StringVar(value="Ready")

        # Saved configuration for the next transfer.
        self.config_selected = []
        self.config_mappings = {}
        self.config_signature = None

        self._ui()
        self._mode()

    def _ui(self):
        main = ttk.Frame(self, padding=14)
        main.grid(sticky="nsew")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(4, weight=1)

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

        ttk.Button(
            tools,
            text="Configure Transfer",
            command=self._config,
        ).pack(side="left")

        ttk.Button(
            tools,
            text="Reload Source",
            command=self._load,
        ).pack(side="left", padx=6)

        ttk.Label(
            tools,
            text="Fuzzy matching is reviewed in the configuration window.",
        ).pack(side="right")

        self.var_frame = ttk.LabelFrame(
            main,
            text="Source Variables",
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

        self.list = tk.Listbox(
            self.var_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
        )
        self.list.grid(row=0, column=0, sticky="nsew")

        bar = ttk.Frame(self.var_frame)
        bar.grid(row=1, column=0, sticky="w", pady=(6, 0))

        ttk.Button(bar, text="Select All", command=self._all).pack(
            side="left"
        )
        ttk.Button(
            bar,
            text="Clear",
            command=lambda: self.list.selection_clear(0, tk.END),
        ).pack(side="left", padx=5)
        ttk.Button(bar, text="Refresh", command=self._load).pack(
            side="left"
        )

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

    def _choose(self, title):
        return filedialog.askopenfilename(
            title=title,
            filetypes=[
                ("Supported", "*.py *.m *.txt *.csv"),
                ("All files", "*.*"),
            ],
        )

    def _browse_source(self):
        path = self._choose("Choose source file")

        if path:
            self.source.set(path)
            self._reset_configuration()
            self._load()

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

            # Open the large configuration menu as soon as both files exist.
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
        self.list.delete(0, tk.END)

        data = self._variables()

        for name in data:
            self.list.insert(tk.END, name)

        self._all()

        if data:
            self.status.set(
                f"Loaded {len(data)} source variable(s)."
            )
        else:
            self.status.set("Choose a valid source file.")

    def _all(self):
        if self.list.size():
            self.list.selection_set(0, tk.END)

    def _selected(self):
        return [
            self.list.get(index)
            for index in self.list.curselection()
        ]

    def _mode(self):
        if self.mode.get() == "All Variables":
            self.var_frame.grid_remove()
        else:
            self.var_frame.grid()
            self._load()

        self._reset_configuration()

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

        ConfigEditor(
            self,
            source,
            destination,
            self._save_config,
        )

    def _save_config(self, selected, mappings):
        self.config_selected = list(selected)
        self.config_mappings = dict(mappings)
        self.config_signature = self._current_signature()

        self.status.set(
            f"Configuration saved: {len(selected)} variable(s) selected, "
            f"{len(mappings)} link(s)."
        )

        return True

    def _history(self):
        HistoryWindow(self, self._after_revert)

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

        signature = self._current_signature()

        # If no configuration exists for these exact files/mode, open it.
        if self.config_signature != signature:
            self._config()
            return

        if not self.config_selected:
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
