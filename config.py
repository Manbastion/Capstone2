import tkinter as tk
from tkinter import ttk, messagebox

from variable_transfer_v2 import valid_name, valid_value
from fuzzy_algorithm import best_fuzzy_match, name_similarity, similarity_label


class ConfigEditor(tk.Toplevel):
    def __init__(self, parent, source_variables, destination_variables, on_save):
        super().__init__(parent)
        self.title("Transfer Configuration")
        self.minsize(1050, 650)
        self.geometry("1150x720")
        self.transient(parent)
        self.grab_set()

        self.source_variables = dict(source_variables)
        self.destination_variables = dict(destination_variables)
        self.on_save = on_save
        self.rows = {}
        self.editor = None
        self.edit_cell = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()
        self._populate()
        self._auto_match()

    def _build(self):
        header = ttk.Frame(self, padding=12)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        ttk.Label(
            header, text="Transfer Configuration",
            font=("TkDefaultFont", 14, "bold")
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text=(
                "Double-click Source Variable or Source Value to edit it. "
                "Double-click Destination Variable to choose a different link."
            ),
            wraplength=950, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        toolbar = ttk.Frame(self, padding=(12, 0, 12, 8))
        toolbar.grid(row=1, column=0, sticky="ew")
        ttk.Button(toolbar, text="Auto Match", command=self._auto_match).pack(side="left")
        ttk.Button(toolbar, text="Accept High-Confidence", command=self._accept_high).pack(side="left", padx=6)
        ttk.Button(toolbar, text="Clear Links", command=self._clear_links).pack(side="left")
        ttk.Button(toolbar, text="Select All", command=self._select_all).pack(side="left", padx=(20, 6))
        ttk.Button(toolbar, text="Select None", command=self._select_none).pack(side="left")

        frame = ttk.Frame(self, padding=(12, 0, 12, 12))
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = (
            "transfer", "source", "source_value", "destination",
            "destination_value", "score", "confidence",
        )
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")

        headings = {
            "transfer": "Transfer",
            "source": "Source Variable",
            "source_value": "Source Value",
            "destination": "Destination Variable",
            "destination_value": "Destination Value",
            "score": "Similarity",
            "confidence": "Confidence",
        }
        widths = {
            "transfer": 70, "source": 190, "source_value": 120,
            "destination": 210, "destination_value": 120,
            "score": 90, "confidence": 110,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")

        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<Double-1>", self._double_click)

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.grid(row=3, column=0, sticky="ew")
        self.status = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="Save Configuration", command=self._save).pack(side="right", padx=6)

    def _populate(self):
        for source_name, source_value in self.source_variables.items():
            item = self.tree.insert("", "end")
            self.rows[item] = {
                "original_source": source_name,
                "source": source_name,
                "source_value": source_value,
                "selected": True,
                "destination": None,
                "score": 0.0,
            }
        self._refresh_rows()

    def _auto_match(self):
        used = set()
        for row in self.rows.values():
            row["destination"] = None
            row["score"] = 0.0

        for row in self.rows.values():
            source = row["source"]
            if source in self.destination_variables and source not in used:
                row["destination"] = source
                row["score"] = 1.0
                used.add(source)

        for row in self.rows.values():
            if row["destination"]:
                continue
            result = best_fuzzy_match(row["source"], self.destination_variables.keys(), used)
            if result and result["score"] >= 0.45:
                row["destination"] = result["destination"]
                row["score"] = result["score"]
                used.add(result["destination"])

        self._refresh_rows()
        linked = sum(bool(row["destination"]) for row in self.rows.values())
        self.status.set(f"Suggested {linked} link(s).")

    def _accept_high(self):
        count = 0
        for row in self.rows.values():
            if row["destination"] and row["score"] >= 0.80:
                row["selected"] = True
                count += 1
        self._refresh_rows()
        self.status.set(f"Accepted {count} high-confidence match(es).")

    def _clear_links(self):
        for row in self.rows.values():
            row["destination"] = None
            row["score"] = 0.0
        self._refresh_rows()

    def _select_all(self):
        for row in self.rows.values():
            row["selected"] = True
        self._refresh_rows()

    def _select_none(self):
        for row in self.rows.values():
            row["selected"] = False
        self._refresh_rows()

    def _refresh_rows(self):
        for item, row in self.rows.items():
            destination = row["destination"]
            score = row["score"]
            self.tree.item(item, values=(
                "☑" if row["selected"] else "☐",
                row["source"],
                row["source_value"],
                destination or "—",
                self.destination_variables.get(destination, "—") if destination else "—",
                f"{score * 100:.1f}%" if destination else "—",
                similarity_label(score) if destination else "Not linked",
            ))

    def _double_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        if not item:
            return

        if column == "#1":
            self.rows[item]["selected"] = not self.rows[item]["selected"]
            self._refresh_rows()
        elif column in ("#2", "#3"):
            self._start_edit(item, column)
        elif column == "#4":
            self._choose_destination(item)

    def _start_edit(self, item, column):
        self._commit_edit()
        box = self.tree.bbox(item, column)
        if not box:
            return
        row = self.rows[item]
        value = row["source"] if column == "#2" else row["source_value"]
        self.editor = ttk.Entry(self.tree)
        self.editor.insert(0, value)
        self.editor.select_range(0, tk.END)
        self.editor.place(x=box[0], y=box[1], width=box[2], height=box[3])
        self.editor.focus_set()
        self.edit_cell = (item, column)
        self.editor.bind("<Return>", lambda _e: self._commit_edit())
        self.editor.bind("<FocusOut>", lambda _e: self._commit_edit())
        self.editor.bind("<Escape>", lambda _e: self._cancel_edit())

    def _commit_edit(self):
        if not self.editor:
            return
        item, column = self.edit_cell
        value = self.editor.get().strip()
        row = self.rows[item]

        if column == "#2":
            if not valid_name(value):
                messagebox.showerror("Invalid variable", f"Invalid variable name: {value!r}", parent=self)
                self._cancel_edit()
                return
            other_names = {r["source"] for key, r in self.rows.items() if key != item}
            if value in other_names:
                messagebox.showerror("Duplicate variable", f"{value!r} already exists.", parent=self)
                self._cancel_edit()
                return
            row["source"] = value
            row["destination"] = None
            row["score"] = 0.0
        else:
            if not valid_value(value):
                messagebox.showerror("Invalid value", f"Invalid numeric value: {value!r}", parent=self)
                self._cancel_edit()
                return
            row["source_value"] = value

        self._cancel_edit()
        self._refresh_rows()

    def _cancel_edit(self):
        if self.editor:
            self.editor.destroy()
        self.editor = None
        self.edit_cell = None

    def _choose_destination(self, item):
        row = self.rows[item]
        window = tk.Toplevel(self)
        window.title(f"Link {row['source']}")
        window.minsize(500, 500)
        window.transient(self)
        window.grab_set()

        ttk.Label(window, text=f"Choose destination for: {row['source']}", font=("TkDefaultFont", 11, "bold")).pack(anchor="w", padx=12, pady=12)
        search = tk.StringVar()
        ttk.Entry(window, textvariable=search).pack(fill="x", padx=12, pady=(0, 8))
        listing = tk.Listbox(window, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12)

        def refresh(*_):
            listing.delete(0, tk.END)
            query = search.get().lower().strip()
            candidates = sorted(
                self.destination_variables,
                key=lambda name: (
                    0 if query and query in name.lower() else 1,
                    -name_similarity(row["source"], name),
                    name.lower(),
                ),
            )
            for name in candidates:
                listing.insert(tk.END, f"{name}    ({name_similarity(row['source'], name) * 100:.1f}%)")

        def choose():
            selection = listing.curselection()
            if not selection:
                messagebox.showwarning("Link variable", "Select a destination variable.", parent=window)
                return
            destination = listing.get(selection[0]).rsplit("    (", 1)[0]
            row["destination"] = destination
            row["score"] = name_similarity(row["source"], destination)
            self._refresh_rows()
            window.destroy()

        search.trace_add("write", refresh)
        refresh()
        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(side="right")
        ttk.Button(buttons, text="Link", command=choose).pack(side="right", padx=6)

    def _save(self):
        self._commit_edit()
        selected, mappings, source_changes = [], {}, {}

        for row in self.rows.values():
            source = row["source"]
            if row["selected"]:
                if not row["destination"]:
                    messagebox.showwarning(
                        "Unlinked variable",
                        f"{source!r} is selected but has no destination link.",
                        parent=self,
                    )
                    return
                selected.append(source)
                mappings[source] = row["destination"]

            source_changes[row["original_source"]] = {
                "name": source,
                "value": row["source_value"],
            }

        destinations = list(mappings.values())
        duplicates = {name for name in destinations if destinations.count(name) > 1}
        if duplicates:
            messagebox.showerror(
                "Duplicate destination",
                "More than one source variable is linked to: " + ", ".join(sorted(duplicates)),
                parent=self,
            )
            return
        if not selected:
            messagebox.showwarning("No variables", "Select at least one variable to transfer.", parent=self)
            return

        fuzzy = [
            (row["source"], row["destination"], row["score"])
            for row in self.rows.values()
            if row["selected"] and row["destination"] and row["score"] < 1.0
        ]
        if fuzzy:
            lines = [f"• {a} → {b} ({score * 100:.1f}%)" for a, b, score in fuzzy[:12]]
            if len(fuzzy) > 12:
                lines.append(f"… and {len(fuzzy) - 12} more.")
            if not messagebox.askyesno(
                "Confirm fuzzy matches",
                "These links are based on name similarity:\n\n" + "\n".join(lines) + "\n\nKeep these links?",
                parent=self,
            ):
                return

        if self.on_save(selected, mappings, source_changes) is not False:
            self.destroy()
