"""Transfer-history storage and History GUI.

History is deliberately lightweight:
- only variables that actually changed are stored
- whole source/destination files are NOT copied
- only the most recent 500 transfer records are kept

A small history.json file is created automatically beside this module.
"""

import json
import os
import uuid
import tkinter as tk

from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from variable_transfer_v2 import (
    read_variables,
    set_variable_values,
)


HISTORY_FILE = Path(__file__).resolve().with_name("history.json")
MAX_HISTORY_RECORDS = 500


def load_history():
    """Return history records, newest first."""
    if not HISTORY_FILE.exists():
        return []

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, list):
            return []

        return data

    except (OSError, json.JSONDecodeError):
        return []


def save_history(records):
    """Save history atomically and keep only the newest records."""
    records = list(records)[:MAX_HISTORY_RECORDS]

    temporary_file = HISTORY_FILE.with_suffix(".json.tmp")

    with open(
        temporary_file,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            records,
            file,
            indent=2,
        )

    os.replace(
        temporary_file,
        HISTORY_FILE,
    )


def record_transfer(
    source_file,
    destination_file,
    mode,
    selected_variables,
    transferred_variables,
    changes,
):
    """Add one successful transfer to history."""
    record = {
        "id": uuid.uuid4().hex,
        "timestamp": datetime.now().isoformat(
            timespec="seconds"
        ),
        "source_file": os.path.abspath(source_file),
        "destination_file": os.path.abspath(destination_file),
        "source_name": os.path.basename(source_file),
        "destination_name": os.path.basename(destination_file),
        "mode": mode,
        "selected_variables": list(
            selected_variables or []
        ),
        "transferred_variables": list(
            transferred_variables or []
        ),
        # Only before/after values for variables that really changed.
        "changes": dict(changes or {}),
        "reverted_at": None,
    }

    records = load_history()
    records.insert(0, record)
    save_history(records)

    return record


def delete_history_record(record_id):
    records = load_history()
    records = [
        record
        for record in records
        if record.get("id") != record_id
    ]
    save_history(records)


def get_history_record(record_id):
    for record in load_history():
        if record.get("id") == record_id:
            return record

    return None


def get_revert_conflicts(record):
    """Check whether files have changed since this transfer.

    Revert restores BOTH the source and destination to the recorded
    'before' values for variables that changed. This keeps them consistent.
    """
    conflicts = []

    source_file = record["source_file"]
    destination_file = record["destination_file"]
    changes = record.get("changes", {})

    if not os.path.isfile(source_file):
        conflicts.append(
            f"Source file no longer exists: {source_file}"
        )

    if not os.path.isfile(destination_file):
        conflicts.append(
            f"Destination file no longer exists: {destination_file}"
        )

    if conflicts:
        return conflicts

    source_values = read_variables(source_file)
    destination_values = read_variables(
        destination_file
    )

    for name, values in changes.items():
        expected_after = str(values["after"])

        source_current = source_values.get(name)
        destination_current = destination_values.get(name)

        if source_current != expected_after:
            conflicts.append(
                f"{name}: source is currently "
                f"{source_current!r}, expected {expected_after!r}"
            )

        if destination_current != expected_after:
            conflicts.append(
                f"{name}: destination is currently "
                f"{destination_current!r}, expected {expected_after!r}"
            )

    return conflicts


def revert_transfer(record_id):
    """Restore changed variables to their recorded 'before' values.

    Both source and destination are updated so the two files remain
    consistent after the revert.
    """
    records = load_history()
    target = None

    for record in records:
        if record.get("id") == record_id:
            target = record
            break

    if target is None:
        raise ValueError(
            "The selected history record no longer exists."
        )

    if target.get("reverted_at"):
        raise ValueError(
            "This transfer has already been reverted."
        )

    changes = target.get("changes", {})

    if not changes:
        raise ValueError(
            "This transfer did not change any variable values, "
            "so there is nothing to revert."
        )

    source_file = target["source_file"]
    destination_file = target["destination_file"]

    if not os.path.isfile(source_file):
        raise FileNotFoundError(
            f"Source file no longer exists:\n{source_file}"
        )

    if not os.path.isfile(destination_file):
        raise FileNotFoundError(
            f"Destination file no longer exists:\n{destination_file}"
        )

    before_values = {
        name: values["before"]
        for name, values in changes.items()
    }

    # strict=True prevents a partial rollback if a variable disappeared.
    set_variable_values(
        source_file,
        before_values,
        strict=True,
    )

    try:
        set_variable_values(
            destination_file,
            before_values,
            strict=True,
        )
    except Exception:
        # If destination rollback fails, restore source to the post-transfer
        # values so the two files do not silently end in different states.
        after_values = {
            name: values["after"]
            for name, values in changes.items()
        }
        set_variable_values(
            source_file,
            after_values,
            strict=True,
        )
        raise

    target["reverted_at"] = datetime.now().isoformat(
        timespec="seconds"
    )

    save_history(records)

    return target


class HistoryDetailsWindow(tk.Toplevel):
    """Displays before/after values for one history record."""

    def __init__(self, parent, record):
        super().__init__(parent)

        self.title("Transfer Details")
        self.minsize(620, 430)
        self.transient(parent)

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        details = (
            f"Source: {record.get('source_file', '')}\n"
            f"Destination: {record.get('destination_file', '')}\n"
            f"Mode: {record.get('mode', '')}\n"
            f"Time: {record.get('timestamp', '')}"
        )

        if record.get("reverted_at"):
            details += (
                f"\nReverted: {record['reverted_at']}"
            )

        ttk.Label(
            self,
            text=details,
            justify="left",
            wraplength=580,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 8),
        )

        ttk.Label(
            self,
            text="Variables changed:",
        ).grid(
            row=1,
            column=0,
            sticky="w",
            padx=14,
            pady=(4, 4),
        )

        table_frame = ttk.Frame(self)
        table_frame.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=14,
            pady=6,
        )
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            table_frame,
            columns=("variable", "before", "after"),
            show="headings",
        )

        tree.heading("variable", text="Variable")
        tree.heading("before", text="Before")
        tree.heading("after", text="After")

        tree.column("variable", width=220, anchor="w")
        tree.column("before", width=150, anchor="w")
        tree.column("after", width=150, anchor="w")

        tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=tree.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        tree.configure(
            yscrollcommand=scrollbar.set
        )

        changes = record.get("changes", {})

        if changes:
            for name, values in changes.items():
                tree.insert(
                    "",
                    "end",
                    values=(
                        name,
                        values.get("before", ""),
                        values.get("after", ""),
                    ),
                )
        else:
            tree.insert(
                "",
                "end",
                values=(
                    "(No value changes)",
                    "",
                    "",
                ),
            )

        ttk.Button(
            self,
            text="Close",
            command=self.destroy,
        ).grid(
            row=3,
            column=0,
            sticky="e",
            padx=14,
            pady=(8, 14),
        )


class HistoryWindow(tk.Toplevel):
    """Separate window that displays and manages transfer history."""

    def __init__(
        self,
        parent,
        on_revert=None,
    ):
        super().__init__(parent)

        self.title("Transfer History")
        self.minsize(900, 500)
        self.transient(parent)

        self.on_revert = on_revert
        self.records_by_item = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text=(
                "History stores only changed variable values, not full file copies. "
                "Revert restores the selected transfer's previous values in BOTH "
                "the source and destination files."
            ),
            wraplength=850,
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 8),
        )

        table_frame = ttk.Frame(self)
        table_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=14,
            pady=6,
        )
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            table_frame,
            columns=(
                "time",
                "source",
                "destination",
                "mode",
                "changed",
                "status",
            ),
            show="headings",
            selectmode="browse",
        )

        headings = {
            "time": "Time",
            "source": "Source",
            "destination": "Destination",
            "mode": "Mode",
            "changed": "Changed",
            "status": "Status",
        }

        for column, heading in headings.items():
            self.tree.heading(
                column,
                text=heading,
            )

        self.tree.column(
            "time",
            width=150,
            anchor="w",
        )
        self.tree.column(
            "source",
            width=170,
            anchor="w",
        )
        self.tree.column(
            "destination",
            width=170,
            anchor="w",
        )
        self.tree.column(
            "mode",
            width=130,
            anchor="w",
        )
        self.tree.column(
            "changed",
            width=80,
            anchor="center",
        )
        self.tree.column(
            "status",
            width=100,
            anchor="center",
        )

        self.tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        self.tree.configure(
            yscrollcommand=scrollbar.set
        )

        self.tree.bind(
            "<Double-1>",
            lambda _event: self._view_details(),
        )

        button_row = ttk.Frame(self)
        button_row.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=(8, 14),
        )
        button_row.columnconfigure(4, weight=1)

        ttk.Button(
            button_row,
            text="View Details",
            command=self._view_details,
        ).grid(
            row=0,
            column=0,
            padx=(0, 8),
        )

        ttk.Button(
            button_row,
            text="Revert Variables",
            command=self._revert_selected,
        ).grid(
            row=0,
            column=1,
            padx=(0, 8),
        )

        ttk.Button(
            button_row,
            text="Delete Record",
            command=self._delete_selected,
        ).grid(
            row=0,
            column=2,
            padx=(0, 8),
        )

        ttk.Button(
            button_row,
            text="Refresh",
            command=self._refresh,
        ).grid(
            row=0,
            column=3,
        )

        ttk.Button(
            button_row,
            text="Close",
            command=self.destroy,
        ).grid(
            row=0,
            column=5,
        )

        self._refresh()

    def _selected_record(self):
        selected = self.tree.selection()

        if not selected:
            return None

        return self.records_by_item.get(
            selected[0]
        )

    def _refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.records_by_item.clear()

        for record in load_history():
            timestamp = record.get(
                "timestamp",
                "",
            ).replace("T", " ")

            status = (
                "Reverted"
                if record.get("reverted_at")
                else "Active"
            )

            item = self.tree.insert(
                "",
                "end",
                values=(
                    timestamp,
                    record.get("source_name", ""),
                    record.get("destination_name", ""),
                    record.get("mode", ""),
                    len(record.get("changes", {})),
                    status,
                ),
            )

            self.records_by_item[item] = record

    def _view_details(self):
        record = self._selected_record()

        if record is None:
            messagebox.showinfo(
                "History",
                "Select a transfer first.",
                parent=self,
            )
            return

        HistoryDetailsWindow(
            self,
            record,
        )

    def _revert_selected(self):
        record = self._selected_record()

        if record is None:
            messagebox.showinfo(
                "History",
                "Select a transfer first.",
                parent=self,
            )
            return

        if record.get("reverted_at"):
            messagebox.showinfo(
                "History",
                "This transfer has already been reverted.",
                parent=self,
            )
            return

        if not record.get("changes"):
            messagebox.showinfo(
                "History",
                "This transfer did not change any values.",
                parent=self,
            )
            return

        conflicts = get_revert_conflicts(record)

        message = (
            "This will restore the recorded BEFORE values "
            "in both the source and destination files.\n\n"
            f"Variables to revert: {len(record.get('changes', {}))}"
        )

        if conflicts:
            preview = "\n".join(
                f"• {conflict}"
                for conflict in conflicts[:8]
            )

            message += (
                "\n\nWarning: the files have changed since this transfer:\n"
                f"{preview}"
            )

            if len(conflicts) > 8:
                message += (
                    f"\n• ...and {len(conflicts) - 8} more"
                )

            message += (
                "\n\nContinuing will overwrite the current values."
            )

        confirmed = messagebox.askyesno(
            "Revert transfer",
            message,
            parent=self,
        )

        if not confirmed:
            return

        try:
            revert_transfer(
                record["id"]
            )
        except (
            OSError,
            ValueError,
            UnicodeError,
        ) as exc:
            messagebox.showerror(
                "Revert failed",
                str(exc),
                parent=self,
            )
            return

        messagebox.showinfo(
            "Revert complete",
            "The previous variable values were restored in both files.",
            parent=self,
        )

        self._refresh()

        if self.on_revert is not None:
            self.on_revert()

    def _delete_selected(self):
        record = self._selected_record()

        if record is None:
            messagebox.showinfo(
                "History",
                "Select a transfer first.",
                parent=self,
            )
            return

        confirmed = messagebox.askyesno(
            "Delete history record",
            "Delete this history record?\n\n"
            "This does not change either source or destination file.",
            parent=self,
        )

        if not confirmed:
            return

        delete_history_record(
            record["id"]
        )

        self._refresh()
