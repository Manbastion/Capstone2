import tkinter as tk
from tkinter import ttk, messagebox

from variable_transfer_v2 import (
    valid_name,
    valid_value,
    fuzzy_matches,
    best_fuzzy_match,
    similarity_label,
)


class ConfigEditor(tk.Toplevel):
    """
    Main transfer configuration window.

    The user can:
      - choose which source variables are transferred
      - see fuzzy suggestions for destination variables
      - accept/reject suggestions
      - manually link any source variable to any destination variable
    """

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
        self.selected_source = None
        self.selected_destination = None

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
            header,
            text="Transfer Configuration",
            font=("TkDefaultFont", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            header,
            text=(
                "Choose the variables to transfer and confirm how source "
                "variables map to destination variables. Suggested matches "
                "are based on fuzzy name similarity."
            ),
            wraplength=950,
            justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(5, 0))

        toolbar = ttk.Frame(self, padding=(12, 0, 12, 8))
        toolbar.grid(row=1, column=0, sticky="ew")

        ttk.Button(
            toolbar, text="Auto Match", command=self._auto_match
        ).pack(side="left")

        ttk.Button(
            toolbar, text="Accept High-Confidence", command=self._accept_high
        ).pack(side="left", padx=6)

        ttk.Button(
            toolbar, text="Clear Links", command=self._clear_links
        ).pack(side="left")

        ttk.Button(
            toolbar, text="Select All", command=self._select_all
        ).pack(side="left", padx=(20, 6))

        ttk.Button(
            toolbar, text="Select None", command=self._select_none
        ).pack(side="left")

        ttk.Label(
            toolbar,
            text="Tip: select one source and one destination, then click Link.",
        ).pack(side="right")

        frame = ttk.Frame(self, padding=(12, 0, 12, 12))
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = (
            "transfer",
            "source",
            "source_value",
            "destination",
            "destination_value",
            "score",
            "confidence",
        )

        self.tree = ttk.Treeview(
            frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

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
            "transfer": 70,
            "source": 190,
            "source_value": 120,
            "destination": 210,
            "destination_value": 120,
            "score": 90,
            "confidence": 110,
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor="w")

        self.tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(
            frame, orient="vertical", command=self.tree.yview
        )
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)

        self.tree.bind("<<TreeviewSelect>>", self._row_selected)
        self.tree.bind("<Double-1>", self._double_click)

        manual = ttk.LabelFrame(
            self,
            text="Manual Linking",
            padding=10,
        )
        manual.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        manual.columnconfigure(1, weight=1)
        manual.columnconfigure(3, weight=1)

        ttk.Label(manual, text="Selected source:").grid(
            row=0, column=0, sticky="w"
        )
        self.source_label = ttk.Label(manual, text="None")
        self.source_label.grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(manual, text="Selected destination:").grid(
            row=0, column=2, sticky="w", padx=(20, 0)
        )
        self.destination_label = ttk.Label(manual, text="None")
        self.destination_label.grid(row=0, column=3, sticky="w", padx=6)

        ttk.Button(
            manual,
            text="Link Selected",
            command=self._link_selected,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        ttk.Button(
            manual,
            text="Unlink Selected Row",
            command=self._unlink_selected,
        ).grid(row=1, column=2, columnspan=2, sticky="w", pady=(8, 0))

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.grid(row=4, column=0, sticky="ew")

        self.status = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.status).pack(side="left")

        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(
            side="right"
        )
        ttk.Button(bottom, text="Save Configuration", command=self._save).pack(
            side="right", padx=6
        )

    def _populate(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        self.rows.clear()

        for source_name, source_value in self.source_variables.items():
            item = self.tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    source_name,
                    source_value,
                    "—",
                    "—",
                    "—",
                    "Not linked",
                ),
            )
            self.rows[item] = {
                "source": source_name,
                "selected": True,
                "destination": None,
                "score": 0.0,
            }

    def _auto_match(self):
        used = set()

        # Exact names always win.
        for item, row in self.rows.items():
            source = row["source"]
            if source in self.destination_variables:
                row["destination"] = source
                row["score"] = 1.0
                used.add(source)

        # Then fuzzy match the remaining variables.
        for item, row in self.rows.items():
            if row["destination"]:
                continue

            result = best_fuzzy_match(
                row["source"],
                self.destination_variables.keys(),
                used,
            )

            if result and result["score"] >= 0.45:
                row["destination"] = result["destination"]
                row["score"] = result["score"]
                used.add(result["destination"])

        self._refresh_rows()

        linked = sum(1 for row in self.rows.values() if row["destination"])
        self.status.set(
            f"Suggested {linked} link(s). Review every fuzzy match before saving."
        )

    def _accept_high(self):
        count = 0

        for row in self.rows.values():
            if row["destination"] and row["score"] >= 0.80:
                row["selected"] = True
                count += 1

        self._refresh_rows()
        self.status.set(
            f"Accepted {count} high-confidence match(es)."
        )

    def _clear_links(self):
        for row in self.rows.values():
            row["destination"] = None
            row["score"] = 0.0

        self._refresh_rows()
        self.status.set("All links cleared.")

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
            source = row["source"]
            destination = row["destination"]

            if destination:
                destination_value = self.destination_variables.get(
                    destination, "?"
                )
                score = row["score"]
                score_text = f"{score * 100:.1f}%"
                confidence = similarity_label(score)
            else:
                destination_value = "—"
                score_text = "—"
                confidence = "Not linked"

            transfer_text = "☑" if row["selected"] else "☐"

            self.tree.item(
                item,
                values=(
                    transfer_text,
                    source,
                    self.source_variables[source],
                    destination or "—",
                    destination_value,
                    score_text,
                    confidence,
                ),
            )

    def _row_selected(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return

        item = selection[0]
        row = self.rows[item]

        self.selected_source = row["source"]
        self.selected_destination = row["destination"]

        self.source_label.config(text=self.selected_source)

        if row["destination"]:
            self.destination_label.config(text=row["destination"])
        else:
            self.destination_label.config(text="None")

    def _double_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)

        if not item:
            return

        # Clicking the transfer column toggles whether this source is included.
        if column == "#1":
            self.rows[item]["selected"] = not self.rows[item]["selected"]
            self._refresh_rows()
            return

        # Double-click destination column opens a manual destination chooser.
        if column == "#4":
            self._choose_destination(item)

    def _choose_destination(self, item):
        row = self.rows[item]

        window = tk.Toplevel(self)
        window.title(f"Link {row['source']}")
        window.minsize(500, 500)
        window.transient(self)
        window.grab_set()

        ttk.Label(
            window,
            text=f"Choose destination for: {row['source']}",
            font=("TkDefaultFont", 11, "bold"),
        ).pack(anchor="w", padx=12, pady=12)

        search = tk.StringVar()
        ttk.Entry(window, textvariable=search).pack(
            fill="x", padx=12, pady=(0, 8)
        )

        listing = tk.Listbox(window, exportselection=False)
        listing.pack(fill="both", expand=True, padx=12)

        def refresh(*_):
            listing.delete(0, tk.END)
            query = search.get().lower().strip()

            candidates = sorted(
                self.destination_variables,
                key=lambda name: (
                    0 if query and query in name.lower() else 1,
                    -name_similarity_safe(row["source"], name),
                    name.lower(),
                ),
            )

            for name in candidates:
                score = name_similarity_safe(row["source"], name)
                listing.insert(
                    tk.END,
                    f"{name}    ({score * 100:.1f}%)"
                )

        def choose():
            selection = listing.curselection()
            if not selection:
                messagebox.showwarning(
                    "Link variable",
                    "Select a destination variable.",
                    parent=window,
                )
                return

            text = listing.get(selection[0])
            destination = text.rsplit("    (", 1)[0]

            row["destination"] = destination
            row["score"] = name_similarity_safe(
                row["source"], destination
            )

            self._refresh_rows()
            window.destroy()

        search.trace_add("write", refresh)
        refresh()

        buttons = ttk.Frame(window)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Cancel", command=window.destroy).pack(
            side="right"
        )
        ttk.Button(buttons, text="Link", command=choose).pack(
            side="right", padx=6
        )

    def _link_selected(self):
        if not self.selected_source:
            messagebox.showwarning(
                "Link variable",
                "Select a source row first.",
                parent=self,
            )
            return

        # A row is selected, so use its existing destination if it has one.
        item = self.tree.selection()[0]
        self._choose_destination(item)

    def _unlink_selected(self):
        selection = self.tree.selection()

        if not selection:
            return

        row = self.rows[selection[0]]
        row["destination"] = None
        row["score"] = 0.0
        self._refresh_rows()

    def _save(self):
        mappings = {}
        selected = []

        for row in self.rows.values():
            if row["selected"]:
                selected.append(row["source"])

                if not row["destination"]:
                    messagebox.showwarning(
                        "Unlinked variable",
                        f"{row['source']!r} is selected for transfer "
                        "but has no destination link.",
                        parent=self,
                    )
                    return

                mappings[row["source"]] = row["destination"]

        # Destination variables can only receive one source.
        destinations = list(mappings.values())
        duplicates = {
            name for name in destinations if destinations.count(name) > 1
        }

        if duplicates:
            messagebox.showerror(
                "Duplicate destination",
                "More than one source variable is linked to: "
                + ", ".join(sorted(duplicates)),
                parent=self,
            )
            return

        if not selected:
            messagebox.showwarning(
                "No variables",
                "Select at least one variable to transfer.",
                parent=self,
            )
            return

        # Explicitly ask for confirmation when the configuration contains
        # fuzzy rather than exact matches. This prevents an apparently
        # plausible name from being silently linked to the wrong variable.
        fuzzy = [
            (source, destination, self.rows[item]["score"])
            for item, row in self.rows.items()
            for source, destination in [(row["source"], row["destination"])]
            if row["selected"]
            and destination
            and row["score"] < 1.0
        ]

        if fuzzy:
            lines = [
                f"• {source}  →  {destination}  "
                f"({score * 100:.1f}%)"
                for source, destination, score in fuzzy[:12]
            ]

            if len(fuzzy) > 12:
                lines.append(f"… and {len(fuzzy) - 12} more.")

            confirmed = messagebox.askyesno(
                "Confirm fuzzy matches",
                "The following links are based on name similarity, "
                "not exact names:\n\n"
                + "\n".join(lines)
                + "\n\nDo you want to keep these links?",
                parent=self,
            )

            if not confirmed:
                return

        if self.on_save(selected, mappings) is not False:
            self.destroy()


def name_similarity_safe(source, destination):
    from variable_transfer_v2 import name_similarity
    return name_similarity(source, destination)
