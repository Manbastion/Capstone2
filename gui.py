import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from variable_transfer_v2 import transfer_data

VARIABLE_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=")
MODES = ["All Variables", "Include Variables", "Exclude Variables"]

MODE_TO_BACKEND = {
    "All Variables": "everything",
    "Include Variables": "include",
    "Exclude Variables": "exclude",
}


class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Grasshopper–HabSim Variable Transfer")
        self.minsize(720, 430)

        self.source_file = tk.StringVar()
        self.destination_file = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.status = tk.StringVar(value="Ready")

        self._build_ui()
        self._update_variable_controls()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        main = ttk.Frame(self, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(4, weight=1)

        # Source file
        ttk.Label(main, text="Source file:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(main, textvariable=self.source_file).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(main, text="Browse…", command=self._browse_source).grid(row=0, column=2, padx=(8, 0), pady=6)

        # Destination file
        ttk.Label(main, text="Destination file:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(main, textvariable=self.destination_file).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(main, text="Browse…", command=self._browse_destination).grid(row=1, column=2, padx=(8, 0), pady=6)

        # Mode
        ttk.Label(main, text="Mode:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        mode_box = ttk.Combobox(main, textvariable=self.mode, values=MODES, state="readonly")
        mode_box.grid(row=2, column=1, sticky="ew", pady=6)
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._update_variable_controls())

        # Variable selection area (only shown for Include/Exclude)
        self.variable_frame = ttk.LabelFrame(main, text="Variables", padding=10)
        self.variable_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(12, 8))
        self.variable_frame.columnconfigure(0, weight=1)
        self.variable_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(self.variable_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.variable_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            height=10,
        )
        self.variable_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.variable_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.variable_listbox.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self.variable_frame)
        button_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(button_row, text="Select All", command=self._select_all).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(button_row, text="Clear Selection", command=self._clear_selection).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(button_row, text="Refresh", command=self._load_variables).grid(row=0, column=2)

        # Transfer button: now connected to the backend.
        action_row = ttk.Frame(main)
        action_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)
        self.transfer_button = ttk.Button(
            action_row,
            text="Transfer",
            command=self._run_transfer,
        )
        self.transfer_button.grid(row=0, column=0, sticky="e")

        # Status bar
        ttk.Separator(main).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 6))
        ttk.Label(main, text="Status:").grid(row=7, column=0, sticky="w")
        ttk.Label(main, textvariable=self.status).grid(row=7, column=1, columnspan=2, sticky="w")

    def _browse_source(self):
        path = filedialog.askopenfilename(
            title="Choose source file",
            filetypes=[
                ("Supported files", "*.py *.m *.txt *.csv"),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.source_file.set(path)
            self.status.set(f"Source selected: {os.path.basename(path)}")
            self._load_variables()

    def _browse_destination(self):
        path = filedialog.askopenfilename(
            title="Choose destination file",
            filetypes=[
                ("Supported files", "*.py *.m *.txt *.csv"),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.destination_file.set(path)
            self.status.set(f"Destination selected: {os.path.basename(path)}")

    def _load_variables(self):
        """Read variable names from the selected source file for the GUI list."""
        self.variable_listbox.delete(0, tk.END)
        path = self.source_file.get().strip()

        if not path:
            self.status.set("Choose a source file to load variables.")
            return

        if not os.path.isfile(path):
            self.status.set("Source file could not be found.")
            return

        variables = []
        try:
            with open(path, "r", encoding="utf-8") as file:
                for line in file:
                    match = VARIABLE_PATTERN.match(line)
                    if match:
                        name = match.group(1)
                        if name not in variables:
                            variables.append(name)
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("File error", str(exc))
            self.status.set("Could not read source file.")
            return

        for variable in variables:
            self.variable_listbox.insert(tk.END, variable)

        if variables:
            self._select_all()
            self.status.set(f"Loaded {len(variables)} variable(s).")
        else:
            self.status.set("No simple variable assignments were found.")

    def _select_all(self):
        if self.variable_listbox.size():
            self.variable_listbox.selection_set(0, tk.END)

    def _clear_selection(self):
        self.variable_listbox.selection_clear(0, tk.END)

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

    def _run_transfer(self):
        """Validate GUI choices, then call transfer_data() from the backend."""
        source = self.source_file.get().strip()
        destination = self.destination_file.get().strip()

        if not source or not os.path.isfile(source):
            messagebox.showerror("Source file", "Please choose a valid source file.")
            self.status.set("Transfer failed: invalid source file.")
            return

        if not destination or not os.path.isfile(destination):
            messagebox.showerror("Destination file", "Please choose a valid destination file.")
            self.status.set("Transfer failed: invalid destination file.")
            return

        # Prevent accidentally selecting the exact same file for both sides.
        if os.path.abspath(source) == os.path.abspath(destination):
            messagebox.showerror("File selection", "Source and destination must be different files.")
            self.status.set("Transfer failed: source and destination are the same file.")
            return

        gui_mode = self.mode.get()
        backend_mode = MODE_TO_BACKEND[gui_mode]
        selected_variables = self.get_selected_variables()

        if backend_mode in ("include", "exclude") and not selected_variables:
            messagebox.showwarning(
                "No variables selected",
                "Please select at least one variable for Include/Exclude mode.",
            )
            self.status.set("Transfer cancelled: no variables selected.")
            return

        try:
            result = transfer_data(
                source,
                destination,
                mode=backend_mode,
                selected_variables=selected_variables,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            messagebox.showerror("Transfer error", str(exc))
            self.status.set("Transfer failed.")
            return

        transferred = result["transferred"]
        missing = result["missing_in_destination"]

        if transferred:
            self.status.set(f"Transfer complete: {len(transferred)} variable(s) updated.")

            message = (
                f"Transfer complete.\n\n"
                f"Updated {len(transferred)} variable(s):\n"
                + ", ".join(transferred)
            )

            if missing:
                message += (
                    "\n\nNot found in destination:\n"
                    + ", ".join(missing)
                )

            messagebox.showinfo("Transfer complete", message)
        else:
            self.status.set("Transfer finished, but no matching destination variables were updated.")
            messagebox.showwarning(
                "No variables updated",
                "The transfer ran, but no selected source variables matched assignments in the destination file.",
            )


if __name__ == "__main__":
    app = VariableTransferGUI()
    app.mainloop()
