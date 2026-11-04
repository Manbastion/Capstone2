"""Tkinter editor for sequential multi-run variable sets."""
import json
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


class MultiRunGUI(tk.Tk):
    def __init__(self, initial_path, state_path):
        super().__init__()
        self.initial_path = initial_path
        self.state_path = state_path
        with open(initial_path, "r", encoding="utf-8") as stream:
            initial = json.load(stream)
        self.defaults = initial.get("variables", {})
        self.names = list(self.defaults.keys())
        self.iteration_count = tk.IntVar(value=3)
        self.status = tk.StringVar(value="Enter values for each iteration, then click Run.")
        self.entries = []
        self.editable = True
        self.title("Grasshopper–MATLAB Multi-run")
        self.geometry("1050x680")
        self.minsize(760, 480)
        self._build()
        self._rebuild_table()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(500, self._poll_state)

    def _build(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        ttk.Label(root, text="Multi-run simulation", font=("Segoe UI", 15, "bold")).grid(
            row=0, column=0, sticky="w")
        ttk.Label(root, text=("Variable names are taken from the connected Grasshopper Names input. "
                              "Edit the values for each run below."), wraplength=950).grid(
            row=1, column=0, sticky="w", pady=(5, 12))

        controls = ttk.Frame(root)
        controls.grid(row=2, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=1)
        controls.rowconfigure(1, weight=1)
        top = ttk.Frame(controls)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(top, text="Number of iterations:").pack(side="left")
        spin = ttk.Spinbox(top, from_=1, to=500, width=7, textvariable=self.iteration_count,
                           command=self._rebuild_table)
        spin.pack(side="left", padx=(8, 12))
        spin.bind("<Return>", lambda _event: self._rebuild_table())
        spin.bind("<FocusOut>", lambda _event: self._rebuild_table())
        ttk.Button(top, text="Import JSON…", command=self._import_json).pack(side="left")
        ttk.Button(top, text="Export JSON…", command=self._export_json).pack(side="left", padx=6)

        table_frame = ttk.Frame(controls)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(table_frame, highlightthickness=0)
        self.vbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.canvas.xview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")

        bottom = ttk.Frame(root)
        bottom.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ttk.Label(bottom, textvariable=self.status, wraplength=760).pack(side="left", fill="x", expand=True)
        self.run_button = ttk.Button(bottom, text="Run iterations", command=self._run)
        self.run_button.pack(side="right")

    def _current_rows(self):
        rows = []
        for column in self.entries:
            row = {}
            for name, entry in zip(self.names, column):
                row[name] = self._parse_value(entry.get())
            rows.append(row)
        return rows

    @staticmethod
    def _parse_value(raw):
        text = raw.strip()
        if not text:
            return ""
        try:
            return json.loads(text)
        except (ValueError, TypeError):
            return raw

    @staticmethod
    def _display_value(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def _rebuild_table(self, values=None):
        if not self.editable:
            return
        if values is None:
            try:
                count = max(1, min(500, int(self.iteration_count.get())))
            except (ValueError, tk.TclError):
                count = 1
            previous = self._current_rows() if self.entries else []
            values = []
            for i in range(count):
                if i < len(previous):
                    values.append(previous[i])
                elif previous:
                    values.append(dict(previous[-1]))
                else:
                    values.append(dict(self.defaults))
        for child in self.inner.winfo_children():
            child.destroy()
        self.entries = []
        ttk.Label(self.inner, text="Variable", font=("Segoe UI", 9, "bold")).grid(
            row=0, column=0, sticky="w", padx=6, pady=5)
        for i in range(len(values)):
            ttk.Label(self.inner, text="Iteration %d" % (i + 1),
                      font=("Segoe UI", 9, "bold")).grid(
                row=0, column=i + 1, sticky="w", padx=6, pady=5)
        for r, name in enumerate(self.names, 1):
            ttk.Label(self.inner, text=name).grid(row=r, column=0, sticky="w", padx=6, pady=3)
        for i, row in enumerate(values):
            column = []
            for r, name in enumerate(self.names, 1):
                entry = ttk.Entry(self.inner, width=22)
                entry.insert(0, self._display_value(row.get(name, self.defaults.get(name, ""))))
                entry.grid(row=r, column=i + 1, sticky="ew", padx=5, pady=3)
                column.append(entry)
            self.entries.append(column)
        self.iteration_count.set(len(values))

    def _import_json(self):
        path = filedialog.askopenfilename(title="Import iteration values",
                                          filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            rows = data.get("iterations") if isinstance(data, dict) else data
            if not isinstance(rows, list) or not rows or not all(isinstance(x, dict) for x in rows):
                raise ValueError("Expected a JSON object with an 'iterations' list of variable/value objects.")
            for row in rows:
                missing = [name for name in self.names if name not in row]
                extra = [name for name in row if name not in self.names]
                if missing or extra:
                    raise ValueError("Each iteration must contain exactly these variables: %s" %
                                     ", ".join(self.names))
            self._rebuild_table(rows)
            self.status.set("Imported %d iteration(s) from %s." % (len(rows), os.path.basename(path)))
        except Exception as error:
            messagebox.showerror("Import failed", str(error), parent=self)

    def _export_json(self):
        path = filedialog.asksaveasfilename(title="Export iteration values", defaultextension=".json",
                                            filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            data = {"variables": self.names, "iterations": self._current_rows()}
            with open(path, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            self.status.set("Exported iteration values to %s." % path)
        except Exception as error:
            messagebox.showerror("Export failed", str(error), parent=self)

    def _run(self):
        try:
            rows = self._current_rows()
            if not rows:
                raise ValueError("Add at least one iteration.")
            for i, row in enumerate(rows):
                if set(row) != set(self.names):
                    raise ValueError("Iteration %d is missing one or more variables." % (i + 1))
            state = {"status": "queued", "phase": "queued", "index": 0,
                     "iterations": rows, "iteration_done": False,
                     "pulse_off_done": False, "started": __import__("time").time()}
            temp = self.state_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as stream:
                json.dump(state, stream, indent=2, ensure_ascii=False, allow_nan=False)
            os.replace(temp, self.state_path)
            self.editable = False
            self.run_button.configure(state="disabled")
            self.status.set("Queued %d iteration(s). Grasshopper will start automatically." % len(rows))
            self.after(150, self.destroy)
        except Exception as error:
            messagebox.showerror("Cannot start", str(error), parent=self)

    def _poll_state(self):
        state = None
        try:
            with open(self.state_path, "r", encoding="utf-8") as stream:
                state = json.load(stream)
        except (OSError, ValueError):
            pass
        if state:
            status = state.get("status")
            index = int(state.get("index", 0))
            total = len(state.get("iterations", []))
            if status == "running":
                self.status.set("Running iteration %d of %d…" % (index + 1, total))
            elif status == "complete":
                self.status.set("Complete: %d iteration(s) finished successfully." % total)
            elif status in ("error", "cancelled"):
                self.status.set(state.get("error") or "Run %s." % status)
        self.after(700, self._poll_state)

    def _close(self):
        self.destroy()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("Usage: multirun_gui.py INITIAL_JSON STATE_JSON")
    MultiRunGUI(sys.argv[1], sys.argv[2]).mainloop()
