import json
import os
import uuid
import tkinter as tk
from pathlib import Path
from datetime import datetime
from tkinter import ttk, messagebox

from variable_transfer_v2 import read_variables, set_variable_values

FILE = Path(__file__).with_name("history.json")
LIMIT = 500


def load_history():
    try:
        with open(FILE, encoding="utf-8") as file:
            data = json.load(file)

        return data if isinstance(data, list) else []

    except (OSError, json.JSONDecodeError):
        return []


def save_history(records):
    temp = FILE.with_suffix(".tmp")

    with open(temp, "w", encoding="utf-8") as file:
        json.dump(records[:LIMIT], file, indent=2)

    os.replace(temp, FILE)


def record_transfer(
    source_file,
    destination_file,
    mode,
    selected_variables,
    transferred_variables,
    changes,
    mappings=None,
):
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source_file": os.path.abspath(source_file),
        "destination_file": os.path.abspath(destination_file),
        "source_name": os.path.basename(source_file),
        "destination_name": os.path.basename(destination_file),
        "mode": mode,
        "selected_variables": list(selected_variables or []),
        "transferred_variables": list(transferred_variables or []),
        "mappings": dict(mappings or {}),
        "changes": dict(changes or {}),
        "reverted_at": None,
    }

    records = load_history()
    records.insert(0, record)
    save_history(records)

    return record


def delete_history_record(record_id):
    save_history(
        [
            record
            for record in load_history()
            if record.get("id") != record_id
        ]
    )


def conflicts(record):
    destination = record["destination_file"]

    if not os.path.isfile(destination):
        return ["The destination file no longer exists."]

    current = read_variables(destination)
    warnings = []

    for name, values in record.get("changes", {}).items():
        expected = str(values["after"])

        if current.get(name) != expected:
            warnings.append(
                f"{name}: destination is {current.get(name)!r}, "
                f"expected {expected!r}"
            )

    return warnings


def revert_transfer(record_id):
    records = load_history()
    record = next(
        (item for item in records if item.get("id") == record_id),
        None,
    )

    if not record:
        raise ValueError("History record not found.")

    if record.get("reverted_at"):
        raise ValueError("This transfer was already reverted.")

    if not record.get("changes"):
        raise ValueError("Nothing changed in this transfer.")

    destination = record["destination_file"]

    if not os.path.isfile(destination):
        raise FileNotFoundError(
            "Destination file no longer exists."
        )

    before = {
        name: values["before"]
        for name, values in record["changes"].items()
    }

    after = {
        name: values["after"]
        for name, values in record["changes"].items()
    }

    set_variable_values(destination, before, True)

    record["reverted_at"] = datetime.now().isoformat(
        timespec="seconds"
    )
    save_history(records)

    return record


class Details(tk.Toplevel):
    def __init__(self, parent, record):
        super().__init__(parent)

        self.title("Transfer Details")
        self.minsize(700, 480)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        mappings = record.get("mappings", {})

        text = (
            f"Source: {record['source_file']}\n"
            f"Destination: {record['destination_file']}\n"
            f"Mode: {record['mode']}\n"
            f"Time: {record['timestamp']}"
        )

        ttk.Label(
            self,
            text=text,
            justify="left",
            wraplength=650,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=12,
            pady=12,
        )

        tree = ttk.Treeview(
            self,
            columns=("source", "destination", "before", "after"),
            show="headings",
        )

        for column, title in (
            ("source", "Source"),
            ("destination", "Destination"),
            ("before", "Before"),
            ("after", "After"),
        ):
            tree.heading(column, text=title)

        tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=12,
        )

        for destination, values in record.get("changes", {}).items():
            tree.insert(
                "",
                "end",
                values=(
                    values.get(
                        "source",
                        mappings.get(destination, destination),
                    ),
                    destination,
                    values["before"],
                    values["after"],
                ),
            )

        ttk.Button(
            self,
            text="Close",
            command=self.destroy,
        ).grid(
            row=2,
            column=0,
            sticky="e",
            padx=12,
            pady=12,
        )


class HistoryWindow(tk.Toplevel):
    def __init__(self, parent, on_revert=None):
        super().__init__(parent)

        self.title("Transfer History")
        self.minsize(980, 500)

        self.on_revert = on_revert
        self.map = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self,
            columns=(
                "time",
                "source",
                "dest",
                "mode",
                "mapped",
                "changed",
                "status",
            ),
            show="headings",
            selectmode="browse",
        )

        for column, title in (
            ("time", "Time"),
            ("source", "Source"),
            ("dest", "Destination"),
            ("mode", "Mode"),
            ("mapped", "Mapped"),
            ("changed", "Changed"),
            ("status", "Status"),
        ):
            self.tree.heading(column, text=title)

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=12,
            pady=(12, 6),
        )

        self.tree.bind("<Double-1>", lambda _: self.view())

        buttons = ttk.Frame(self)
        buttons.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=12,
            pady=(0, 12),
        )

        for text, command in (
            ("View Details", self.view),
            ("Revert Variables", self.revert),
            ("Delete Record", self.delete),
            ("Refresh", self.refresh),
        ):
            ttk.Button(
                buttons,
                text=text,
                command=command,
            ).pack(side="left", padx=(0, 6))

        ttk.Button(
            buttons,
            text="Close",
            command=self.destroy,
        ).pack(side="right")

        self.refresh()

    def selected(self):
        selection = self.tree.selection()
        return self.map.get(selection[0]) if selection else None

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.map.clear()

        for record in load_history():
            item = self.tree.insert(
                "",
                "end",
                values=(
                    record["timestamp"].replace("T", " "),
                    record["source_name"],
                    record["destination_name"],
                    record["mode"],
                    len(record.get("mappings", {})),
                    len(record.get("changes", {})),
                    "Reverted"
                    if record.get("reverted_at")
                    else "Active",
                ),
            )

            self.map[item] = record

    def view(self):
        record = self.selected()

        if record:
            Details(self, record)
        else:
            messagebox.showinfo(
                "History",
                "Select a transfer first.",
                parent=self,
            )

    def revert(self):
        record = self.selected()

        if not record:
            messagebox.showinfo(
                "History",
                "Select a transfer first.",
                parent=self,
            )
            return

        if record.get("reverted_at"):
            messagebox.showinfo(
                "History",
                "This transfer was already reverted.",
                parent=self,
            )
            return

        warning = conflicts(record)

        message = (
            "Restore the recorded BEFORE values in the destination file?"
        )

        if warning:
            message += (
                "\n\nCurrent destination differs from the recorded "
                "post-transfer values:\n"
                + "\n".join(warning[:8])
            )

        if not messagebox.askyesno(
            "Revert transfer",
            message,
            parent=self,
        ):
            return

        try:
            revert_transfer(record["id"])

        except (OSError, ValueError, UnicodeError) as error:
            messagebox.showerror(
                "Revert failed",
                str(error),
                parent=self,
            )
            return

        self.refresh()

        if self.on_revert:
            self.on_revert()

        messagebox.showinfo(
            "Revert complete",
            "Previous destination values restored.",
            parent=self,
        )

    def delete(self):
        record = self.selected()

        if not record:
            return

        if messagebox.askyesno(
            "Delete record",
            "Delete this history record?",
            parent=self,
        ):
            delete_history_record(record["id"])
            self.refresh()
