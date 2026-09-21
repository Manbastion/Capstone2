import os, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from config import ConfigEditor
from history import HistoryWindow, record_transfer
from variable_transfer_v2 import read_variables, transfer_data, update_source_variables

MODES = ["All Variables", "Include Variables", "Exclude Variables"]
BACKEND = {"All Variables":"everything", "Include Variables":"include", "Exclude Variables":"exclude"}

class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Grasshopper–HabSim Variable Transfer")
        self.minsize(760, 500)
        self.source, self.destination = tk.StringVar(), tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.status = tk.StringVar(value="Ready")
        self._ui(); self._mode()

    def _ui(self):
        main = ttk.Frame(self, padding=14)
        main.grid(sticky="nsew")
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1); main.rowconfigure(4, weight=1)

        for row, (label, var, cmd) in enumerate((
            ("Source file:", self.source, self._browse_source),
            ("Destination file:", self.destination, self._browse_destination),
        )):
            ttk.Label(main, text=label).grid(row=row, column=0, sticky="w", pady=5)
            ttk.Entry(main, textvariable=var).grid(row=row, column=1, sticky="ew", pady=5)
            ttk.Button(main, text="Browse…", command=cmd).grid(row=row, column=2, padx=(8,0))

        ttk.Label(main, text="Mode:").grid(row=2, column=0, sticky="w", pady=5)
        box = ttk.Combobox(main, textvariable=self.mode, values=MODES, state="readonly")
        box.grid(row=2, column=1, sticky="ew"); box.bind("<<ComboboxSelected>>", lambda _: self._mode())

        tools = ttk.Frame(main); tools.grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Button(tools, text="Open Config", command=self._config).pack(side="left")
        ttk.Button(tools, text="Reload Source", command=self._load).pack(side="left", padx=6)

        self.var_frame = ttk.LabelFrame(main, text="Variables", padding=8)
        self.var_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=6)
        self.var_frame.columnconfigure(0, weight=1); self.var_frame.rowconfigure(0, weight=1)
        self.list = tk.Listbox(self.var_frame, selectmode=tk.EXTENDED, exportselection=False)
        self.list.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Frame(self.var_frame); bar.grid(row=1, column=0, sticky="w", pady=(6,0))
        ttk.Button(bar, text="Select All", command=self._all).pack(side="left")
        ttk.Button(bar, text="Clear", command=lambda: self.list.selection_clear(0, tk.END)).pack(side="left", padx=5)
        ttk.Button(bar, text="Refresh", command=self._load).pack(side="left")

        actions = ttk.Frame(main); actions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Button(actions, text="History", command=self._history).pack(side="left")
        ttk.Button(actions, text="Transfer", command=self._transfer).pack(side="right")

        ttk.Separator(main).grid(row=6, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(main, text="Status:").grid(row=7, column=0, sticky="w")
        ttk.Label(main, textvariable=self.status).grid(row=7, column=1, columnspan=2, sticky="w")

    def _choose(self, title):
        return filedialog.askopenfilename(
            title=title,
            filetypes=[("Supported","*.py *.m *.txt *.csv"),("All files","*.*")]
        )

    def _browse_source(self):
        p = self._choose("Choose source file")
        if p: self.source.set(p); self._load()

    def _browse_destination(self):
        p = self._choose("Choose destination file")
        if p: self.destination.set(p); self.status.set(f"Destination: {os.path.basename(p)}")

    def _variables(self):
        p = self.source.get().strip()
        return read_variables(p) if os.path.isfile(p) else {}

    def _load(self):
        self.list.delete(0, tk.END)
        data = self._variables()
        for name in data: self.list.insert(tk.END, name)
        self._all()
        self.status.set(f"Loaded {len(data)} variable(s)." if data else "Choose a valid source file.")

    def _all(self):
        if self.list.size(): self.list.selection_set(0, tk.END)

    def _selected(self):
        return [self.list.get(i) for i in self.list.curselection()]

    def _mode(self):
        if self.mode.get() == "All Variables": self.var_frame.grid_remove()
        else: self.var_frame.grid(); self._load()

    def _config(self):
        data = self._variables()
        if not data:
            messagebox.showerror("Config", "Choose a valid source file first."); return
        ConfigEditor(self, data, self._save_config)

    def _save_config(self, edited, changes):
        try:
            result = update_source_variables(self.source.get().strip(), changes)
        except (OSError, ValueError, UnicodeError) as e:
            messagebox.showerror("Config error", str(e)); return False
        self._load()
        self.status.set(f"Source saved ({result['count']} variables).")
        return True

    def _history(self):
        HistoryWindow(self, self._after_revert)

    def _after_revert(self):
        self._load()
        self.status.set("History revert complete.")

    def _transfer(self):
        src, dst = self.source.get().strip(), self.destination.get().strip()
        if not os.path.isfile(src) or not os.path.isfile(dst):
            messagebox.showerror("Transfer", "Choose valid source and destination files."); return
        if os.path.abspath(src) == os.path.abspath(dst):
            messagebox.showerror("Transfer", "Source and destination must be different."); return

        mode, selected = BACKEND[self.mode.get()], self._selected()
        if mode != "everything" and not selected:
            messagebox.showwarning("Transfer", "Select at least one variable."); return

        try:
            result = transfer_data(src, dst, mode, selected)
            record_transfer(src, dst, self.mode.get(), selected, result["transferred"], result["changes"])
        except (OSError, ValueError, UnicodeError) as e:
            messagebox.showerror("Transfer error", str(e)); return

        changed, missing = len(result["changes"]), result["missing_in_destination"]
        self.status.set(f"Transfer complete: {changed} value(s) changed.")
        msg = f"Transferred {len(result['transferred'])} variable(s).\nChanged {changed} value(s)."
        if missing: msg += "\n\nNot found in destination:\n" + ", ".join(missing)
        messagebox.showinfo("Transfer complete", msg)