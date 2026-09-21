import json, os, uuid, tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox
from variable_transfer_v2 import read_variables, set_variable_values

FILE = Path(__file__).with_name("history.json")
LIMIT = 500

def load_history():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []

def save_history(records):
    temp = FILE.with_suffix(".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(records[:LIMIT], f, indent=2)
    os.replace(temp, FILE)

def record_transfer(source_file, destination_file, mode, selected_variables, transferred_variables, changes):
    r = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_file": os.path.abspath(source_file),
        "destination_file": os.path.abspath(destination_file),
        "source_name": os.path.basename(source_file),
        "destination_name": os.path.basename(destination_file),
        "mode": mode,
        "selected_variables": list(selected_variables or []),
        "transferred_variables": list(transferred_variables or []),
        "changes": dict(changes or {}),
        "reverted_at": None,
    }
    records = load_history()
    records.insert(0, r)
    save_history(records)
    return r

def delete_history_record(rid):
    save_history([r for r in load_history() if r.get("id") != rid])

def conflicts(record):
    out = []
    paths = (record["source_file"], record["destination_file"])
    if not all(os.path.isfile(p) for p in paths):
        return ["One or both files no longer exist."]
    current = [read_variables(p) for p in paths]
    for name, values in record.get("changes", {}).items():
        for label, data in zip(("source", "destination"), current):
            if data.get(name) != str(values["after"]):
                out.append(f"{name}: {label} is {data.get(name)!r}, expected {values['after']!r}")
    return out

def revert_transfer(rid):
    records = load_history()
    r = next((x for x in records if x.get("id") == rid), None)
    if not r: raise ValueError("History record not found.")
    if r.get("reverted_at"): raise ValueError("This transfer was already reverted.")
    if not r.get("changes"): raise ValueError("Nothing changed in this transfer.")

    before = {k: v["before"] for k, v in r["changes"].items()}
    after = {k: v["after"] for k, v in r["changes"].items()}
    src, dst = r["source_file"], r["destination_file"]
    if not os.path.isfile(src) or not os.path.isfile(dst):
        raise FileNotFoundError("Source or destination file no longer exists.")

    set_variable_values(src, before, True)
    try:
        set_variable_values(dst, before, True)
    except Exception:
        set_variable_values(src, after, True)
        raise

    r["reverted_at"] = datetime.now().isoformat(timespec="seconds")
    save_history(records)
    return r

class Details(tk.Toplevel):
    def __init__(self, parent, record):
        super().__init__(parent)
        self.title("Transfer Details"); self.minsize(580, 400)
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        text = (
            f"Source: {record['source_file']}\nDestination: {record['destination_file']}\n"
            f"Mode: {record['mode']}\nTime: {record['timestamp']}"
        )
        ttk.Label(self, text=text, justify="left", wraplength=540).grid(
            row=0, column=0, sticky="ew", padx=12, pady=12
        )
        tree = ttk.Treeview(self, columns=("name","before","after"), show="headings")
        for c, t in (("name","Variable"),("before","Before"),("after","After")):
            tree.heading(c, text=t)
        tree.grid(row=1, column=0, sticky="nsew", padx=12)
        for name, v in record.get("changes", {}).items():
            tree.insert("", "end", values=(name, v["before"], v["after"]))
        ttk.Button(self, text="Close", command=self.destroy).grid(
            row=2, column=0, sticky="e", padx=12, pady=12
        )

class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, on_revert=None):
        super().__init__(parent)
        self.title("Transfer History"); self.minsize(860, 480)
        self.on_revert, self.map = on_revert, {}
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self, columns=("time","source","dest","mode","changed","status"),
            show="headings", selectmode="browse"
        )
        for c, t in (
            ("time","Time"),("source","Source"),("dest","Destination"),
            ("mode","Mode"),("changed","Changed"),("status","Status")
        ):
            self.tree.heading(c, text=t)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12,6))
        self.tree.bind("<Double-1>", lambda _: self.view())

        row = ttk.Frame(self); row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0,12))
        for text, cmd in (
            ("View Details", self.view), ("Revert Variables", self.revert),
            ("Delete Record", self.delete), ("Refresh", self.refresh)
        ):
            ttk.Button(row, text=text, command=cmd).pack(side="left", padx=(0,6))
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")
        self.refresh()

    def selected(self):
        s = self.tree.selection()
        return self.map.get(s[0]) if s else None

    def refresh(self):
        for x in self.tree.get_children(): self.tree.delete(x)
        self.map.clear()
        for r in load_history():
            item = self.tree.insert("", "end", values=(
                r["timestamp"].replace("T"," "), r["source_name"], r["destination_name"],
                r["mode"], len(r.get("changes",{})),
                "Reverted" if r.get("reverted_at") else "Active"
            ))
            self.map[item] = r

    def view(self):
        r = self.selected()
        if r: Details(self, r)
        else: messagebox.showinfo("History", "Select a transfer first.", parent=self)

    def revert(self):
        r = self.selected()
        if not r:
            messagebox.showinfo("History", "Select a transfer first.", parent=self); return
        if r.get("reverted_at"):
            messagebox.showinfo("History", "This transfer was already reverted.", parent=self); return

        warning = conflicts(r)
        msg = "Restore the recorded BEFORE values in both files?"
        if warning:
            msg += "\n\nCurrent files differ from this history record:\n" + "\n".join(warning[:6])
        if not messagebox.askyesno("Revert transfer", msg, parent=self): return

        try: revert_transfer(r["id"])
        except (OSError, ValueError, UnicodeError) as e:
            messagebox.showerror("Revert failed", str(e), parent=self); return

        self.refresh()
        if self.on_revert: self.on_revert()
        messagebox.showinfo("Revert complete", "Previous values restored.", parent=self)

    def delete(self):
        r = self.selected()
        if not r: return
        if messagebox.askyesno("Delete record", "Delete this history record?", parent=self):
            delete_history_record(r["id"]); self.refresh()