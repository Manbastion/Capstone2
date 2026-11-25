import tkinter as tk
from tkinter import ttk, messagebox

from variable_transfer_v2 import valid_name, valid_value
from fuzzy_algorithm import best_fuzzy_match, name_similarity, similarity_label

ALL = "All Variables"
INCLUDE = "Include Variables"
EXCLUDE = "Exclude Variables"

COLUMNS = (
    "transfer", "source", "source_value", "destination",
    "destination_value", "score", "confidence",
)
HEADINGS = {
    "transfer": "Include",
    "source": "Source Variable",
    "source_value": "Source Value",
    "destination": "Destination Variable",
    "destination_value": "Destination Value",
    "score": "Similarity",
    "confidence": "Confidence",
}
WIDTHS = {
    "transfer": 70, "source": 190, "source_value": 180,
    "destination": 210, "destination_value": 180,
    "score": 90, "confidence": 110,
}

HINTS = {
    ALL: (
        "Every variable is transferred. Double-click Source Variable or Source Value "
        "to edit it. Double-click Destination Variable to choose a different link."
    ),
    INCLUDE: (
        "Only ticked variables are transferred. Double-click the checkbox to tick or "
        "untick a variable, Source Variable / Source Value to edit it, and Destination "
        "Variable to choose a different link."
    ),
    EXCLUDE: (
        "Ticked variables are NOT transferred; every other variable is. Double-click "
        "the checkbox to exclude or include a variable, Source Variable / Source Value "
        "to edit it, and Destination Variable to choose a different link."
    ),
}


class ConfigPanel(ttk.Frame):
    """The transfer table: source variables, their values and their destination links.

    It sits in the middle of the main window. What the checkbox column means
    depends on the mode:

      All Variables      no checkbox column; every variable is transferred
      Include Variables  ticked = transferred
      Exclude Variables  ticked = left out, everything else is transferred

    Names, values and links can be edited in every mode. Nothing is saved until
    the owner calls collect() and stores the result.
    """

    def __init__(self, parent, mode=ALL):
        super().__init__(parent)
        self.mode = mode
        self.source_variables = {}
        self.destination_variables = {}
        self.rows = {}
        self.editor = None
        self.edit_cell = None
        self.last_unlinked = 0          # rows that will be transferred but have no link
        self._display = list(COLUMNS)
        self.status = tk.StringVar(value="")

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build()
        self.set_mode(mode)

    # ------------------------------------------------------------------ layout
    def _build(self):
        self.hint = ttk.Label(self, justify="left", wraplength=900)
        self.hint.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.bind("<Configure>", lambda e: self.hint.configure(wraplength=max(300, e.width - 20)))

        self.toolbar = ttk.Frame(self)
        self.toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self.btn_auto = ttk.Button(self.toolbar, text="Auto Match", command=self._auto_match)
        self.btn_accept = ttk.Button(self.toolbar, text="Accept High-Confidence", command=self._accept_high)
        self.btn_clear = ttk.Button(self.toolbar, text="Clear Links", command=self._clear_links)
        self.btn_all = ttk.Button(self.toolbar, text="Select All", command=self._select_all)
        self.btn_none = ttk.Button(self.toolbar, text="Select None", command=self._select_none)

        frame = ttk.Frame(self)
        frame.grid(row=2, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(frame, columns=COLUMNS, show="headings", selectmode="browse")
        for column in COLUMNS:
            self.tree.heading(column, text=HEADINGS[column])
            self.tree.column(column, width=WIDTHS[column], anchor="w")
        self.tree.tag_configure("off", foreground="#8a8a8a")   # rows that won't be transferred

        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.tree.xview)
        hscroll.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.tree.bind("<Double-1>", self._double_click)

        ttk.Label(self, textvariable=self.status).grid(row=3, column=0, sticky="w", pady=(6, 0))

    def _layout_toolbar(self):
        for button in (self.btn_auto, self.btn_accept, self.btn_clear, self.btn_all, self.btn_none):
            button.pack_forget()
        self.btn_auto.pack(side="left")
        if self.mode == INCLUDE:
            self.btn_accept.pack(side="left", padx=6)
        self.btn_clear.pack(side="left", padx=(0 if self.mode == INCLUDE else 6, 0))
        if self.mode != ALL:
            self.btn_all.pack(side="left", padx=(20, 6))
            self.btn_none.pack(side="left")

    # -------------------------------------------------------------------- mode
    def set_mode(self, mode):
        """Switch between All / Include / Exclude. Names, values and links are kept."""
        changed = mode != getattr(self, "_shown_mode", None)
        self.mode = mode
        self._shown_mode = mode

        self._display = [c for c in COLUMNS if c != "transfer" or mode != ALL]
        self.tree.configure(displaycolumns=self._display)
        self.tree.heading("transfer", text="Exclude" if mode == EXCLUDE else "Include")
        self.btn_all.configure(text="Exclude All" if mode == EXCLUDE else "Select All")
        self.btn_none.configure(text="Exclude None" if mode == EXCLUDE else "Select None")
        self.hint.configure(text=HINTS.get(mode, HINTS[ALL]))
        self._layout_toolbar()

        if changed:                      # include: all ticked; exclude: none ticked
            for row in self.rows.values():
                row["selected"] = mode != EXCLUDE
        self._refresh_rows()

    def _will_transfer(self, row):
        if self.mode == INCLUDE:
            return row["selected"]
        if self.mode == EXCLUDE:
            return not row["selected"]
        return True

    # -------------------------------------------------------------------- data
    def load(self, source_variables, destination_variables, saved_selected=None, saved_mappings=None):
        """(Re)build the table from the two variable lists, with a saved choice if there is one."""
        self._cancel_edit()
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        self.source_variables = dict(source_variables)
        self.destination_variables = dict(destination_variables)
        saved = None if saved_selected is None else set(saved_selected)

        for source_name, source_value in self.source_variables.items():
            item = self.tree.insert("", "end")
            if self.mode == ALL:
                selected = True
            elif saved is None:
                selected = self.mode != EXCLUDE
            else:
                selected = source_name in saved
            self.rows[item] = {
                "original_source": source_name,
                "source": source_name,
                "source_value": source_value,
                "selected": selected,
                "destination": None,
                "score": 0.0,
            }

        if saved_mappings:
            self._restore_saved(dict(saved_mappings))
        else:
            self._auto_match()

    def _restore_saved(self, mappings):
        linked = 0
        used = set()
        for row in self.rows.values():
            destination = mappings.get(row["source"])
            if destination in self.destination_variables:
                row["destination"] = destination
                row["score"] = name_similarity(row["source"], destination)
                used.add(destination)
                linked += 1
            else:
                row["destination"] = None
                row["score"] = 0.0

        # Rows with no saved link (left out of the transfer) still get an exact
        # same-name link, so ticking them later doesn't mean linking them by hand.
        for row in self.rows.values():
            name = row["source"]
            if not row["destination"] and name in self.destination_variables and name not in used:
                row["destination"] = name
                row["score"] = 1.0
                used.add(name)

        self._refresh_rows()
        self.status.set(f"Loaded last saved configuration ({linked} link(s)).")

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
            self.tree.item(
                item,
                values=(
                    "☑" if row["selected"] else "☐",
                    row["source"],
                    row["source_value"],
                    destination or "—",
                    self.destination_variables.get(destination, "—") if destination else "—",
                    f"{score * 100:.1f}%" if destination else "—",
                    similarity_label(score) if destination else "Not linked",
                ),
                tags=() if self._will_transfer(row) else ("off",),
            )

    # ----------------------------------------------------------------- editing
    def _column_name(self, event):
        """Name of the column under the mouse (the checkbox column may be hidden)."""
        try:
            index = int(self.tree.identify_column(event.x).lstrip("#")) - 1
        except ValueError:
            return None
        return self._display[index] if 0 <= index < len(self._display) else None

    def _double_click(self, event):
        item = self.tree.identify_row(event.y)
        column = self._column_name(event)
        if not item or not column:
            return

        if column == "transfer":
            self.rows[item]["selected"] = not self.rows[item]["selected"]
            self._refresh_rows()
        elif column in ("source", "source_value"):
            self._start_edit(item, column)
        elif column == "destination":
            self._choose_destination(item)

    def _start_edit(self, item, column):
        self._commit_edit()
        box = self.tree.bbox(item, column)
        if not box:
            return
        row = self.rows[item]
        value = row["source"] if column == "source" else row["source_value"]
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
        top = self.winfo_toplevel()

        if column == "source":
            if not valid_name(value):
                messagebox.showerror("Invalid variable", f"Invalid variable name: {value!r}", parent=top)
                self._cancel_edit()
                return
            other_names = {r["source"] for key, r in self.rows.items() if key != item}
            if value in other_names:
                messagebox.showerror("Duplicate variable", f"{value!r} already exists.", parent=top)
                self._cancel_edit()
                return
            row["source"] = value
            row["destination"] = None
            row["score"] = 0.0
        else:
            if not valid_value(value):
                messagebox.showerror(
                    "Invalid value",
                    f"Use a MATLAB literal or formula/expression: {value!r}",
                    parent=top,
                )
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
        top = self.winfo_toplevel()
        window = tk.Toplevel(top)
        window.title(f"Link {row['source']}")
        window.minsize(500, 500)
        window.transient(top)
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

    # -------------------------------------------------------------------- save
    def collect(self):
        """Check the table. Returns (selected, mappings, source_changes), or None.

        selected   All: every variable.  Include: the ticked ones.
                   Exclude: the ticked ones (the variables that are left out).
        mappings   {source: destination} for every variable that will be transferred
        None       something needs fixing (a message has been shown)
        """
        self._commit_edit()
        top = self.winfo_toplevel()
        selected, mappings, source_changes = [], {}, {}
        unlinked = 0

        for row in self.rows.values():
            source = row["source"]
            if self.mode == ALL or row["selected"]:
                selected.append(source)

            if self._will_transfer(row):
                if row["destination"]:
                    mappings[source] = row["destination"]
                elif self.mode == INCLUDE:
                    messagebox.showwarning(
                        "Unlinked variable",
                        f"{source!r} is ticked but has no destination link.",
                        parent=top,
                    )
                    return None
                else:
                    unlinked += 1

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
                parent=top,
            )
            return None
        if not mappings:
            messagebox.showwarning(
                "No variables",
                "Tick at least one variable to transfer." if self.mode == INCLUDE
                else "Nothing would be transferred. Link at least one variable.",
                parent=top,
            )
            return None

        fuzzy = [
            (row["source"], row["destination"], row["score"])
            for row in self.rows.values()
            if self._will_transfer(row) and row["destination"] and row["score"] < 1.0
        ]
        if fuzzy:
            lines = [f"• {a} → {b} ({score * 100:.1f}%)" for a, b, score in fuzzy[:12]]
            if len(fuzzy) > 12:
                lines.append(f"… and {len(fuzzy) - 12} more.")
            if not messagebox.askyesno(
                "Confirm fuzzy matches",
                "These links are based on name similarity:\n\n" + "\n".join(lines) + "\n\nKeep these links?",
                parent=top,
            ):
                return None

        self.last_unlinked = unlinked
        return selected, mappings, source_changes


class ConfigEditor(tk.Toplevel):
    """The same table in its own pop-up window (OK / Cancel). The main window no
    longer uses it, but it is kept for anything that still opens it."""

    def __init__(self, parent, source_variables, destination_variables, on_save,
                 saved_selected=None, saved_mappings=None, mode=INCLUDE):
        super().__init__(parent)
        self.title("Transfer Configuration")
        self.minsize(1050, 650)
        self.geometry("1150x720")
        self.transient(parent)
        self.grab_set()

        self.on_save = on_save
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.panel = ConfigPanel(self, mode)
        self.panel.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.panel.load(source_variables, destination_variables, saved_selected, saved_mappings)

        bottom = ttk.Frame(self, padding=(12, 0, 12, 12))
        bottom.grid(row=1, column=0, sticky="ew")
        ttk.Button(bottom, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(bottom, text="OK", command=self._save).pack(side="right", padx=6)
        ttk.Label(bottom, text="OK saves the configuration and closes this window.").pack(
            side="right", padx=(0, 12))

    def _save(self):
        result = self.panel.collect()
        if result is None:
            return
        if self.on_save(*result) is not False:
            self.destroy()