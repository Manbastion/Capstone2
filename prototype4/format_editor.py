import tkinter as tk
from tkinter import ttk, messagebox

import Capstone2.prototype4.value_formats as vf

HINT = {"foreground": "#666666"}


def _label_for(rule):
    mark = "[x]" if rule["enabled"] else "[ ]"
    return "%s  %s" % (mark, rule["name"] or "(no name)")


def _show(value, limit=46):
    text = repr(value) if isinstance(value, str) else str(value)
    return text if len(text) <= limit else text[:limit - 3] + "..."


class FormatEditor(tk.Toplevel):
    def __init__(self, parent, rules_path, raw_values, on_saved=None):
        super().__init__(parent)
        self.title("Value Formats")
        self.minsize(980, 720)
        self.geometry("1120x780")
        self.rules_path = rules_path
        self.raw = raw_values or {}
        self.on_saved = on_saved
        self.index = None
        self._loading = False

        try:
            self.rules = vf.load_rules(rules_path)
        except ValueError as error:
            messagebox.showerror("Value Formats", str(error), parent=parent)
            self.rules = []

        self._build()
        self._refill_list()
        if self.rules:
            self._select(0)
        else:
            self._enable_form(False)
        self._refresh_preview()
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ------------------------------------------------------------- layout
    def _build(self):
        main = ttk.Frame(self, padding=12)
        main.grid(sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(1, weight=1)
        main.rowconfigure(2, weight=1)

        intro = ttk.Label(
            main, wraplength=1040, justify="left",
            text=("A format tells the program how a value typed in Grasshopper should "
                  "look in MATLAB, for example  1 | 2 | 3  becomes  [1 2 3].  Formats that name "
                  "specific variables are tried first, then general ones, each from top to "
                  "bottom; the first one that fits is used. "
                  "Anything no format covers still works: numbers, text, lists like "
                  "1,2,3 or -1,0, true/false, points and tables are converted automatically."))
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        # ---- left: list of formats
        left = ttk.LabelFrame(main, text="Your formats", padding=8)
        left.grid(row=1, column=0, sticky="ns", padx=(0, 10))
        left.rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(left, width=36, height=12, exportselection=False,
                                  activestyle="none")
        self.listbox.grid(row=0, column=0, columnspan=3, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_pick())
        bar = ttk.Frame(left)
        bar.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for text, cmd in (("Add", self._add), ("Duplicate", self._duplicate),
                          ("Remove", self._remove)):
            ttk.Button(bar, text=text, command=cmd, width=10).pack(side="left", padx=(0, 4))
        bar2 = ttk.Frame(left)
        bar2.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(4, 0))
        ttk.Button(bar2, text="Move up", command=lambda: self._move(-1),
                   width=10).pack(side="left", padx=(0, 4))
        ttk.Button(bar2, text="Move down", command=lambda: self._move(1),
                   width=10).pack(side="left")

        # ---- right: edit form
        self.form = ttk.LabelFrame(main, text="Edit the selected format", padding=10)
        self.form.grid(row=1, column=1, sticky="nsew")
        self.form.columnconfigure(1, weight=1)

        self.v_name = tk.StringVar()
        self.v_enabled = tk.BooleanVar(value=True)
        self.v_vars = tk.StringVar()
        self.v_sep = tk.StringVar()
        self.v_rowsep = tk.StringVar()
        self.v_strip = tk.StringVar()
        self.v_items = tk.StringVar()
        self.v_output = tk.StringVar()
        self.v_example = tk.StringVar()

        self._widgets = []
        row = 0

        def field(label, widget, hint=None):
            nonlocal row
            ttk.Label(self.form, text=label).grid(row=row, column=0, sticky="w",
                                                  pady=(4, 0), padx=(0, 10))
            widget.grid(row=row, column=1, sticky="ew", pady=(4, 0))
            self._widgets.append(widget)
            row += 1
            if hint:
                ttk.Label(self.form, text=hint, wraplength=470, justify="left", **HINT).grid(
                    row=row, column=1, sticky="w")
                row += 1

        field("Name", ttk.Entry(self.form, textvariable=self.v_name))
        chk = ttk.Checkbutton(self.form, text="This format is switched on",
                              variable=self.v_enabled)
        chk.grid(row=row, column=1, sticky="w", pady=(4, 0))
        self._widgets.append(chk)
        row += 1
        field("Applies to variables named", ttk.Entry(self.form, textvariable=self.v_vars),
              "Empty = any variable whose text contains the separator. "
              "Or names:  coords, pos*, meteorite.*")
        field("Items are separated by", ttk.Entry(self.form, textvariable=self.v_sep, width=12),
              "e.g.   |    ,    ;    -    (empty = spaces,  \\t = tab)")
        field("Rows are separated by (optional)",
              ttk.Entry(self.form, textvariable=self.v_rowsep, width=12),
              "Tables only, e.g.  ;   so  1,2 ; 3,4  becomes [1 2;3 4]")
        field("Ignore these characters around it",
              ttk.Entry(self.form, textvariable=self.v_strip, width=12),
              "e.g.  ()[]<>   so that  (1 | 2 | 3)  works too")
        self.c_items = ttk.Combobox(self.form, textvariable=self.v_items, state="readonly",
                                    values=[label for _k, label in vf.ITEM_MODES])
        field("Each item is", self.c_items)
        self.c_output = ttk.Combobox(self.form, textvariable=self.v_output, state="readonly",
                                     values=[label for _k, label in vf.OUTPUTS])
        field("In MATLAB it becomes", self.c_output)
        ttk.Separator(self.form).grid(row=row, column=0, columnspan=2, sticky="ew", pady=8)
        row += 1
        ttk.Label(self.form, text="Example").grid(row=row, column=0, sticky="w")
        ttk.Label(self.form, textvariable=self.v_example,
                  font=("TkFixedFont", 11, "bold")).grid(row=row, column=1, sticky="w")

        for var in (self.v_name, self.v_enabled, self.v_vars, self.v_sep, self.v_rowsep,
                    self.v_strip, self.v_items, self.v_output):
            var.trace_add("write", lambda *_a: self._on_edit())

        # ---- middle: current Grasshopper values
        check = ttk.LabelFrame(main, text="Your current Grasshopper values, as MATLAB will get them",
                               padding=8)
        check.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        check.columnconfigure(0, weight=1)
        check.rowconfigure(0, weight=1)
        cols = ("name", "gh", "matlab", "format")
        self.tree = ttk.Treeview(check, columns=cols, show="headings", height=5)
        for col, text, width in (("name", "Variable", 200), ("gh", "From Grasshopper", 250),
                                 ("matlab", "Written to MATLAB as", 320),
                                 ("format", "Format used", 230)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="w")
        self.tree.tag_configure("bad", foreground="#b00020")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(check, orient="vertical", command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=sb.set)

        # ---- try it
        tryit = ttk.LabelFrame(main, text="Try it", padding=8)
        tryit.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        tryit.columnconfigure(3, weight=1)
        self.t_name = tk.StringVar(value="x")
        self.t_value = tk.StringVar(value="1 | 2 | 3")
        self.t_result = tk.StringVar()
        ttk.Label(tryit, text="Variable").grid(row=0, column=0, padx=(0, 4))
        ttk.Entry(tryit, textvariable=self.t_name, width=14).grid(row=0, column=1, padx=(0, 12))
        ttk.Label(tryit, text="Value in Grasshopper").grid(row=0, column=2, padx=(0, 4))
        ttk.Entry(tryit, textvariable=self.t_value).grid(row=0, column=3, sticky="ew")
        ttk.Label(tryit, text="MATLAB gets").grid(row=0, column=4, padx=(12, 4))
        ttk.Entry(tryit, textvariable=self.t_result, state="readonly", width=34).grid(
            row=0, column=5)
        self.t_name.trace_add("write", lambda *_a: self._refresh_try())
        self.t_value.trace_add("write", lambda *_a: self._refresh_try())

        # ---- buttons
        buttons = ttk.Frame(main)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        ttk.Label(buttons, text="Saved in: %s" % self.rules_path, **HINT).pack(side="left")
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=6)

    # ------------------------------------------------------------ helpers
    def _enable_form(self, on):
        for widget in self._widgets:
            try:
                widget.configure(state="normal" if on else "disabled")
            except tk.TclError:
                pass
        if on:
            self.c_items.configure(state="readonly")
            self.c_output.configure(state="readonly")

    def _refill_list(self, keep=None):
        self.listbox.delete(0, tk.END)
        for rule in self.rules:
            self.listbox.insert(tk.END, _label_for(rule))
        if keep is not None and self.rules:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(keep)
            self.listbox.see(keep)

    @staticmethod
    def _key(options, label, default):
        for key, text in options:
            if text == label:
                return key
        return default

    @staticmethod
    def _label(options, key):
        for k, text in options:
            if k == key:
                return text
        return options[0][1]

    def _current(self):
        return self.rules[self.index] if self.index is not None else None

    # ---------------------------------------------------------- selection
    def _on_pick(self):
        picked = self.listbox.curselection()
        if picked:
            self._select(picked[0])

    def _select(self, index):
        self.index = index
        rule = self.rules[index]
        self._loading = True
        try:
            self.v_name.set(rule["name"])
            self.v_enabled.set(rule["enabled"])
            self.v_vars.set(rule["variables"])
            self.v_sep.set(rule["separator"])
            self.v_rowsep.set(rule["row_separator"])
            self.v_strip.set(rule["strip"])
            self.v_items.set(self._label(vf.ITEM_MODES, rule["items"]))
            self.v_output.set(self._label(vf.OUTPUTS, rule["output"]))
        finally:
            self._loading = False
        self._enable_form(True)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(index)
        self._refresh_example()

    def _on_edit(self):
        rule = self._current()
        if self._loading or rule is None:
            return
        rule["name"] = self.v_name.get()
        rule["enabled"] = bool(self.v_enabled.get())
        rule["variables"] = self.v_vars.get()
        rule["separator"] = self.v_sep.get()
        rule["row_separator"] = self.v_rowsep.get()
        rule["strip"] = self.v_strip.get()
        rule["items"] = self._key(vf.ITEM_MODES, self.v_items.get(), "auto")
        rule["output"] = self._key(vf.OUTPUTS, self.v_output.get(), "row")
        self.listbox.delete(self.index)
        self.listbox.insert(self.index, _label_for(rule))
        self.listbox.selection_set(self.index)
        self._refresh_example()
        self._refresh_preview()

    # -------------------------------------------------------------- buttons
    def _add(self):
        names = {r["name"] for r in self.rules}
        n = 1
        while "New format %d" % n in names:
            n += 1
        rule = vf.normalize_rule({"name": "New format %d" % n, "separator": "|"})
        self.rules.append(rule)
        self._refill_list(len(self.rules) - 1)
        self._select(len(self.rules) - 1)
        self._refresh_preview()

    def _duplicate(self):
        rule = self._current()
        if rule is None:
            return
        copy = dict(rule, name=rule["name"] + " (copy)")
        self.rules.insert(self.index + 1, copy)
        self._refill_list(self.index + 1)
        self._select(self.index + 1)
        self._refresh_preview()

    def _remove(self):
        rule = self._current()
        if rule is None:
            return
        if not messagebox.askyesno("Remove format", "Remove '%s'?" % rule["name"], parent=self):
            return
        del self.rules[self.index]
        self.index = None
        self._refill_list()
        if self.rules:
            self._select(min(self.listbox.size() - 1, 0))
        else:
            self._enable_form(False)
            for var in (self.v_name, self.v_vars, self.v_sep, self.v_rowsep, self.v_strip,
                        self.v_example):
                var.set("")
        self._refresh_preview()

    def _move(self, step):
        i, j = self.index, (self.index or 0) + step
        if i is None or not 0 <= j < len(self.rules):
            return
        self.rules[i], self.rules[j] = self.rules[j], self.rules[i]
        self.index = j
        self._refill_list(j)
        self._refresh_preview()

    # --------------------------------------------------------------- views
    def _active(self):
        return [r for r in self.rules if r["enabled"]]

    def _refresh_example(self):
        rule = self._current()
        if rule is None:
            self.v_example.set("")
            return
        problems = vf.rule_problems(rule)
        if problems:
            self.v_example.set("(not complete: %s)" % problems[0])
        else:
            sample, result = vf.example_for(rule)
            self.v_example.set("%s     →     %s" % (sample, result))
        self._refresh_try()

    def _refresh_try(self):
        name = self.t_name.get().strip() or "x"
        try:
            text, used = vf.convert(name, self.t_value.get(), self._active())
            result = text + ("" if used is None else "    (format: %s)" % used)
        except ValueError as error:
            result = "error: %s" % error
        self.t_result.set(result)

    def _refresh_preview(self):
        self.tree.delete(*self.tree.get_children())
        rules = self._active()
        if not self.raw:
            self.tree.insert("", tk.END, values=(
                "(nothing yet)", "Press Open on the Grasshopper block with values "
                "connected to see them here", "", ""))
        for name, value in self.raw.items():
            try:
                text, used = vf.convert(name, value, rules)
                self.tree.insert("", tk.END, values=(name, _show(value), text, used or "built-in"))
            except ValueError as error:
                self.tree.insert("", tk.END, tags=("bad",),
                                 values=(name, _show(value), "ERROR: %s" % error, ""))
        self._refresh_try()

    # ----------------------------------------------------------------- save
    def _save(self):
        for rule in self.rules:
            if not rule["enabled"]:
                continue
            problems = vf.rule_problems(rule)
            if problems:
                messagebox.showerror(
                    "Value Formats",
                    "The format '%s' can't be saved: %s.\n\nFix it, or switch it off."
                    % (rule["name"], problems[0]), parent=self)
                return
        try:
            vf.save_rules(self.rules_path, self.rules)
        except OSError as error:
            messagebox.showerror("Value Formats", "Could not save:\n%s" % error, parent=self)
            return
        if self.on_saved:
            self.on_saved()
        self.destroy()
