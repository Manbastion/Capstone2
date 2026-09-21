"""Separate variable configuration editor.

The Config page lets the user:
- view source variables and values
- double-click a variable name to rename it
- double-click a value to edit it
- save those edits directly back to the source file
"""

import tkinter as tk
from tkinter import messagebox, ttk

from variable_transfer_v2 import (
    is_valid_numeric_value,
    is_valid_variable_name,
)


class ConfigEditor(tk.Toplevel):
    def __init__(self, parent, variables, on_save):
        super().__init__(parent)

        self.title("Variable Configuration")
        self.minsize(580, 430)
        self.transient(parent)

        self.on_save = on_save

        self.active_editor = None
        self.active_item = None
        self.active_column = None

        # Remember each row's ORIGINAL variable name.
        # This lets the backend know which source line to rename.
        self.original_names = {}

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        ttk.Label(
            self,
            text=(
                "Double-click a variable name or value to edit it. "
                "Press Save to write the changes back to the source file."
            ),
            wraplength=540,
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
            columns=("variable", "value"),
            show="headings",
            selectmode="browse",
        )

        self.tree.heading("variable", text="Variable")
        self.tree.heading("value", text="Value")
        self.tree.column("variable", width=300, anchor="w")
        self.tree.column("value", width=190, anchor="w")
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scrollbar.set)

        for name, value in variables.items():
            item = self.tree.insert(
                "",
                "end",
                values=(name, value),
            )
            self.original_names[item] = name

        self.tree.bind("<Double-1>", self._start_edit)

        button_row = ttk.Frame(self)
        button_row.grid(
            row=2,
            column=0,
            sticky="e",
            padx=14,
            pady=(8, 14),
        )

        ttk.Button(
            button_row,
            text="Cancel",
            command=self.destroy,
        ).grid(row=0, column=0, padx=(0, 8))

        ttk.Button(
            button_row,
            text="Save",
            command=self._save,
        ).grid(row=0, column=1)

        self.grab_set()
        self.focus_set()

    def _start_edit(self, event):
        """Place a temporary text box over a double-clicked table cell."""
        region = self.tree.identify("region", event.x, event.y)

        if region != "cell":
            return

        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item or column not in ("#1", "#2"):
            return

        self._commit_active_edit()

        bbox = self.tree.bbox(item, column)

        if not bbox:
            return

        x, y, width, height = bbox
        values = self.tree.item(item, "values")
        column_index = 0 if column == "#1" else 1
        current_value = values[column_index]

        editor = ttk.Entry(self.tree)
        editor.insert(0, current_value)
        editor.select_range(0, tk.END)
        editor.place(
            x=x,
            y=y,
            width=width,
            height=height,
        )
        editor.focus_set()

        self.active_editor = editor
        self.active_item = item
        self.active_column = column

        editor.bind(
            "<Return>",
            lambda _event: self._commit_active_edit(),
        )
        editor.bind(
            "<FocusOut>",
            lambda _event: self._commit_active_edit(),
        )
        editor.bind(
            "<Escape>",
            lambda _event: self._cancel_active_edit(),
        )

    def _commit_active_edit(self):
        if self.active_editor is None:
            return

        new_text = self.active_editor.get().strip()

        values = list(
            self.tree.item(
                self.active_item,
                "values",
            )
        )

        column_index = (
            0
            if self.active_column == "#1"
            else 1
        )

        values[column_index] = new_text

        self.tree.item(
            self.active_item,
            values=values,
        )

        self.active_editor.destroy()
        self.active_editor = None
        self.active_item = None
        self.active_column = None

    def _cancel_active_edit(self):
        if self.active_editor is not None:
            self.active_editor.destroy()

        self.active_editor = None
        self.active_item = None
        self.active_column = None

    def _save(self):
        """Validate edits and send them to gui.py to save."""
        self._commit_active_edit()

        edited_variables = {}
        source_changes = {}

        for item in self.tree.get_children():
            name, value = [
                str(v).strip()
                for v in self.tree.item(
                    item,
                    "values",
                )
            ]

            original_name = self.original_names[item]

            if not name:
                messagebox.showerror(
                    "Invalid variable",
                    "Variable names cannot be blank.",
                    parent=self,
                )
                return

            if not is_valid_variable_name(name):
                messagebox.showerror(
                    "Invalid variable",
                    f"{name!r} is not a valid simple variable name.",
                    parent=self,
                )
                return

            if name in edited_variables:
                messagebox.showerror(
                    "Duplicate variable",
                    f"The variable name {name!r} appears more than once.",
                    parent=self,
                )
                return

            if not is_valid_numeric_value(value):
                messagebox.showerror(
                    "Invalid value",
                    f"{value!r} is not a supported numeric value for {name}.",
                    parent=self,
                )
                return

            edited_variables[name] = value

            source_changes[original_name] = {
                "name": name,
                "value": value,
            }

        save_succeeded = self.on_save(
            edited_variables,
            source_changes,
        )

        if save_succeeded is False:
            return

        self.destroy()
