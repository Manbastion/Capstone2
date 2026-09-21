"""Main GUI for the Grasshopper–HabSim variable-transfer prototype.

Run the application from main.py, not from this file.
"""

import os
import tkinter as tk

from tkinter import filedialog, messagebox, ttk

from config import ConfigEditor
from history import HistoryWindow, record_transfer
from variable_transfer_v2 import (
    read_variables,
    transfer_data,
    update_source_variables,
)


MODES = [
    "All Variables",
    "Include Variables",
    "Exclude Variables",
]

MODE_TO_BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title(
            "Grasshopper–HabSim Variable Transfer"
        )
        self.minsize(780, 520)

        self.source_file = tk.StringVar()
        self.destination_file = tk.StringVar()
        self.mode = tk.StringVar(
            value=MODES[0]
        )
        self.status = tk.StringVar(
            value="Ready"
        )
        self.config_status = tk.StringVar(
            value="Using values from source file"
        )

        self._build_ui()
        self._update_variable_controls()

    def _build_ui(self):
        self.columnconfigure(
            0,
            weight=1,
        )
        self.rowconfigure(
            0,
            weight=1,
        )

        main = ttk.Frame(
            self,
            padding=16,
        )

        main.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        main.columnconfigure(
            1,
            weight=1,
        )

        main.rowconfigure(
            5,
            weight=1,
        )

        # --------------------------------------------------------
        # Source file
        # --------------------------------------------------------
        ttk.Label(
            main,
            text="Source file:",
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=6,
        )

        ttk.Entry(
            main,
            textvariable=self.source_file,
        ).grid(
            row=0,
            column=1,
            sticky="ew",
            pady=6,
        )

        ttk.Button(
            main,
            text="Browse…",
            command=self._browse_source,
        ).grid(
            row=0,
            column=2,
            padx=(8, 0),
            pady=6,
        )

        # --------------------------------------------------------
        # Destination file
        # --------------------------------------------------------
        ttk.Label(
            main,
            text="Destination file:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=6,
        )

        ttk.Entry(
            main,
            textvariable=self.destination_file,
        ).grid(
            row=1,
            column=1,
            sticky="ew",
            pady=6,
        )

        ttk.Button(
            main,
            text="Browse…",
            command=self._browse_destination,
        ).grid(
            row=1,
            column=2,
            padx=(8, 0),
            pady=6,
        )

        # --------------------------------------------------------
        # Mode
        # --------------------------------------------------------
        ttk.Label(
            main,
            text="Mode:",
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=6,
        )

        mode_box = ttk.Combobox(
            main,
            textvariable=self.mode,
            values=MODES,
            state="readonly",
        )

        mode_box.grid(
            row=2,
            column=1,
            sticky="ew",
            pady=6,
        )

        mode_box.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._update_variable_controls(),
        )

        # --------------------------------------------------------
        # Config controls
        # --------------------------------------------------------
        config_row = ttk.Frame(main)

        config_row.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(6, 2),
        )

        config_row.columnconfigure(
            1,
            weight=1,
        )

        ttk.Button(
            config_row,
            text="Open Config",
            command=self._open_config,
        ).grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 10),
        )

        ttk.Label(
            config_row,
            textvariable=self.config_status,
        ).grid(
            row=0,
            column=1,
            sticky="w",
        )

        ttk.Button(
            config_row,
            text="Reload Source",
            command=self._reload_source,
        ).grid(
            row=0,
            column=2,
            sticky="e",
        )

        # --------------------------------------------------------
        # Variable selector
        # --------------------------------------------------------
        self.variable_frame = ttk.LabelFrame(
            main,
            text="Variables",
            padding=10,
        )

        self.variable_frame.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(12, 8),
        )

        self.variable_frame.columnconfigure(
            0,
            weight=1,
        )
        self.variable_frame.rowconfigure(
            0,
            weight=1,
        )

        list_frame = ttk.Frame(
            self.variable_frame
        )

        list_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        list_frame.columnconfigure(
            0,
            weight=1,
        )
        list_frame.rowconfigure(
            0,
            weight=1,
        )

        self.variable_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            height=10,
        )

        self.variable_listbox.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.variable_listbox.yview,
        )

        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.variable_listbox.configure(
            yscrollcommand=scrollbar.set
        )

        button_row = ttk.Frame(
            self.variable_frame
        )

        button_row.grid(
            row=1,
            column=0,
            sticky="w",
            pady=(8, 0),
        )

        ttk.Button(
            button_row,
            text="Select All",
            command=self._select_all,
        ).grid(
            row=0,
            column=0,
            padx=(0, 6),
        )

        ttk.Button(
            button_row,
            text="Clear Selection",
            command=self._clear_selection,
        ).grid(
            row=0,
            column=1,
            padx=(0, 6),
        )

        ttk.Button(
            button_row,
            text="Refresh",
            command=self._load_variables,
        ).grid(
            row=0,
            column=2,
        )

        # --------------------------------------------------------
        # Main actions: History + Transfer
        # --------------------------------------------------------
        action_row = ttk.Frame(main)

        action_row.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 0),
        )

        action_row.columnconfigure(
            1,
            weight=1,
        )

        ttk.Button(
            action_row,
            text="History",
            command=self._open_history,
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        ttk.Button(
            action_row,
            text="Transfer",
            command=self._run_transfer,
        ).grid(
            row=0,
            column=2,
            sticky="e",
        )

        # --------------------------------------------------------
        # Status bar
        # --------------------------------------------------------
        ttk.Separator(main).grid(
            row=7,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 6),
        )

        ttk.Label(
            main,
            text="Status:",
        ).grid(
            row=8,
            column=0,
            sticky="w",
        )

        ttk.Label(
            main,
            textvariable=self.status,
        ).grid(
            row=8,
            column=1,
            columnspan=2,
            sticky="w",
        )

    def _browse_source(self):
        path = filedialog.askopenfilename(
            title="Choose source file",
            filetypes=[
                (
                    "Supported files",
                    "*.py *.m *.txt *.csv",
                ),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.source_file.set(path)
            self.config_status.set(
                "Using values from source file"
            )
            self.status.set(
                f"Source selected: {os.path.basename(path)}"
            )
            self._load_variables()

    def _browse_destination(self):
        path = filedialog.askopenfilename(
            title="Choose destination file",
            filetypes=[
                (
                    "Supported files",
                    "*.py *.m *.txt *.csv",
                ),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )

        if path:
            self.destination_file.set(path)
            self.status.set(
                f"Destination selected: {os.path.basename(path)}"
            )

    def _current_variables(self):
        source = self.source_file.get().strip()

        if not source or not os.path.isfile(source):
            return {}

        return read_variables(source)

    def _open_config(self):
        source = self.source_file.get().strip()

        if not source or not os.path.isfile(source):
            messagebox.showerror(
                "Source file",
                "Choose a valid source file before opening Config.",
            )
            return

        variables = self._current_variables()

        if not variables:
            messagebox.showerror(
                "No variables",
                "No supported simple numeric variable assignments "
                "were found in the source file.",
            )
            return

        ConfigEditor(
            self,
            variables,
            self._save_config_from_editor,
        )

    def _save_config_from_editor(
        self,
        edited_variables,
        source_changes,
    ):
        source = self.source_file.get().strip()

        if not source or not os.path.isfile(source):
            messagebox.showerror(
                "Source file",
                "The source file is no longer available.",
            )
            return False

        try:
            result = update_source_variables(
                source,
                source_changes,
            )
        except (
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            messagebox.showerror(
                "Config save error",
                str(exc),
            )
            self.status.set(
                "Config save failed."
            )
            return False

        self.config_status.set(
            f"Source saved ({result['count']} variables)"
        )
        self.status.set(
            "Config saved. Source file has been updated."
        )
        self._load_variables()

        return True

    def _reload_source(self):
        self.config_status.set(
            "Using values from source file"
        )
        self.status.set(
            "Source values reloaded."
        )
        self._load_variables()

    def _load_variables(self):
        self.variable_listbox.delete(
            0,
            tk.END,
        )

        variables = self._current_variables()

        for name in variables:
            self.variable_listbox.insert(
                tk.END,
                name,
            )

        if variables:
            self._select_all()
            self.status.set(
                f"Loaded {len(variables)} variable(s)."
            )
        else:
            self.status.set(
                "Choose a source file to load variables."
            )

    def _select_all(self):
        if self.variable_listbox.size():
            self.variable_listbox.selection_set(
                0,
                tk.END,
            )

    def _clear_selection(self):
        self.variable_listbox.selection_clear(
            0,
            tk.END,
        )

    def _update_variable_controls(self):
        if self.mode.get() == "All Variables":
            self.variable_frame.grid_remove()
        else:
            self.variable_frame.grid()
            self._load_variables()

    def get_selected_variables(self):
        return [
            self.variable_listbox.get(i)
            for i in self.variable_listbox.curselection()
        ]

    def _open_history(self):
        HistoryWindow(
            self,
            on_revert=self._after_history_revert,
        )

    def _after_history_revert(self):
        """Refresh the main GUI after History changes the files."""
        self._load_variables()
        self.config_status.set(
            "Source updated by History revert"
        )
        self.status.set(
            "History revert complete. Source and destination were restored."
        )

    def _run_transfer(self):
        source = self.source_file.get().strip()
        destination = self.destination_file.get().strip()

        if not source or not os.path.isfile(source):
            messagebox.showerror(
                "Source file",
                "Please choose a valid source file.",
            )
            self.status.set(
                "Transfer failed: invalid source file."
            )
            return

        if (
            not destination
            or not os.path.isfile(destination)
        ):
            messagebox.showerror(
                "Destination file",
                "Please choose a valid destination file.",
            )
            self.status.set(
                "Transfer failed: invalid destination file."
            )
            return

        if (
            os.path.abspath(source)
            == os.path.abspath(destination)
        ):
            messagebox.showerror(
                "File selection",
                "Source and destination must be different files.",
            )
            self.status.set(
                "Transfer failed: source and destination are the same file."
            )
            return

        backend_mode = MODE_TO_BACKEND[
            self.mode.get()
        ]

        selected_variables = (
            self.get_selected_variables()
        )

        if (
            backend_mode in (
                "include",
                "exclude",
            )
            and not selected_variables
        ):
            messagebox.showwarning(
                "No variables selected",
                "Please select at least one variable "
                "for Include/Exclude mode.",
            )
            self.status.set(
                "Transfer cancelled: no variables selected."
            )
            return

        try:
            result = transfer_data(
                source,
                destination,
                mode=backend_mode,
                selected_variables=selected_variables,
            )

            # Record every successful transfer.
            record_transfer(
                source_file=source,
                destination_file=destination,
                mode=self.mode.get(),
                selected_variables=selected_variables,
                transferred_variables=result["transferred"],
                changes=result["changes"],
            )

        except (
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            messagebox.showerror(
                "Transfer error",
                str(exc),
            )
            self.status.set(
                "Transfer failed."
            )
            return

        transferred = result["transferred"]
        missing = result[
            "missing_in_destination"
        ]
        changed_count = len(
            result["changes"]
        )

        if transferred:
            self.status.set(
                f"Transfer complete: {len(transferred)} transferred, "
                f"{changed_count} value(s) changed."
            )

            message = (
                "Transfer complete.\n\n"
                f"Transferred: {len(transferred)}\n"
                f"Values changed: {changed_count}"
            )

            if missing:
                message += (
                    "\n\nNot found in destination:\n"
                    + ", ".join(missing)
                )

            messagebox.showinfo(
                "Transfer complete",
                message,
            )

        else:
            self.status.set(
                "Transfer finished, but no matching "
                "destination variables were updated."
            )

            message = (
                "No matching destination variables "
                "were updated."
            )

            if missing:
                message += (
                    "\n\nNot found in destination:\n"
                    + ", ".join(missing)
                )

            messagebox.showwarning(
                "Transfer finished",
                message,
            )
