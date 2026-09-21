import tkinter as tk
from tkinter import ttk, messagebox
from variable_transfer_v2 import valid_name, valid_value

class ConfigEditor(tk.Toplevel):
    def __init__(self, parent, variables, on_save):
        super().__init__(parent)
        self.title("Variable Configuration")
        self.minsize(560, 420)
        self.transient(parent)
        self.on_save, self.editor, self.cell = on_save, None, None
        self.original = {}
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(self, text="Double-click a name or value to edit.").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 6)
        )

        frame = ttk.Frame(self)
        frame.grid(row=1, column=0, sticky="nsew", padx=12)
        frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame, columns=("name", "value"), show="headings")
        for c, t, w in (("name", "Variable", 300), ("value", "Value", 180)):
            self.tree.heading(c, text=t); self.tree.column(c, width=w, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        for name, value in variables.items():
            item = self.tree.insert("", "end", values=(name, value))
            self.original[item] = name

        self.tree.bind("<Double-1>", self._edit)

        buttons = ttk.Frame(self)
        buttons.grid(row=2, column=0, sticky="e", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(buttons, text="Save", command=self._save).pack(side="left")
        self.grab_set()

    def _edit(self, e):
        self._commit()
        item, col = self.tree.identify_row(e.y), self.tree.identify_column(e.x)
        if not item or col not in ("#1", "#2"): return
        box = self.tree.bbox(item, col)
        if not box: return
        values = self.tree.item(item, "values")
        i = 0 if col == "#1" else 1
        self.cell = (item, i)
        self.editor = ttk.Entry(self.tree)
        self.editor.insert(0, values[i])
        self.editor.select_range(0, tk.END)
        self.editor.place(x=box[0], y=box[1], width=box[2], height=box[3])
        self.editor.focus()
        self.editor.bind("<Return>", lambda _: self._commit())
        self.editor.bind("<FocusOut>", lambda _: self._commit())
        self.editor.bind("<Escape>", lambda _: self._cancel())

    def _commit(self):
        if not self.editor: return
        item, i = self.cell
        values = list(self.tree.item(item, "values"))
        values[i] = self.editor.get().strip()
        self.tree.item(item, values=values)
        self._cancel()

    def _cancel(self):
        if self.editor: self.editor.destroy()
        self.editor = self.cell = None

    def _save(self):
        self._commit()
        edited, changes = {}, {}
        for item in self.tree.get_children():
            name, value = map(str.strip, self.tree.item(item, "values"))
            if not valid_name(name):
                messagebox.showerror("Invalid variable", f"Invalid name: {name!r}", parent=self); return
            if name in edited:
                messagebox.showerror("Duplicate", f"{name!r} appears more than once.", parent=self); return
            if not valid_value(value):
                messagebox.showerror("Invalid value", f"Invalid value for {name}: {value!r}", parent=self); return
            edited[name] = value
            changes[self.original[item]] = {"name": name, "value": value}

        if self.on_save(edited, changes) is not False:
            self.destroy()
