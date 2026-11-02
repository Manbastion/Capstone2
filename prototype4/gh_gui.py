import json
import os
import sys
from pathlib import Path
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import Capstone2.prototype4.gui as gui  # noqa: E402  (the existing window)
from Capstone2.prototype4.variable_transfer_v2 import read_variables  # noqa: E402
import Capstone2.prototype4.gh_bridge as gh_bridge  # noqa: E402
from Capstone2.prototype4.gh_bridge import compose_renames  # noqa: E402
from Capstone2.prototype4.format_editor import FormatEditor  # noqa: E402


class GrasshopperTransferGUI(gui.VariableTransferGUI):
    gh_source = ""
    gh_destination = ""

    # ---- start-up: fixed files, restore saved choices -----------------------
    def __init__(self):
        self.renames = {}
        super().__init__()
        self.title("Grasshopper–HabSim Variable Transfer (live Grasshopper variables)")
        self._lock_file_pickers(self)

    # ---- extra button: the client's own value formats ------------------------
    def _ui(self):
        super()._ui()
        bar = self._find_toolbar(self)
        if bar is not None:
            ttk.Button(bar, text="Value Formats…", command=self._open_formats).pack(
                side="left", padx=(0, 6))

    def _find_toolbar(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Button) and str(child.cget("text")) == "Configure Transfer":
                return child.master
            found = self._find_toolbar(child)
            if found is not None:
                return found
        return None

    def _open_formats(self):
        FormatEditor(self, gh_bridge.FORMATS_FILE, gh_bridge.load_raw(),
                     self._formats_saved)

    def _formats_saved(self):
        """Formats changed: convert the Grasshopper values again and refresh the list."""
        if not gh_bridge.load_raw():
            self.status.set("Formats saved. They will be used on the next transfer.")
            return
        try:
            final, skipped = gh_bridge.render_source(self.renames, self.gh_source)
        except ValueError as error:
            messagebox.showerror("Value Formats", str(error), parent=self)
            return
        self._load()
        self.status.set("Formats saved: %d variable(s) converted again." % len(final))
        if skipped:
            messagebox.showwarning(
                "Value Formats",
                "These variables can't be sent with the current formats:\n\n"
                + "\n".join(skipped), parent=self)

    def _lock_file_pickers(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Entry):
                child.configure(state="readonly")
            self._lock_file_pickers(child)

    def _browse_source(self):
        messagebox.showinfo(
            "Source",
            "The source is the variables wired into the Grasshopper block.",
            parent=self)

    def _browse_destination(self):
        messagebox.showinfo(
            "Destination",
            "The destination is the MATLAB file wired into the Grasshopper block.",
            parent=self)

    def _config(self):
        """Same as the standalone window, but say exactly why a file is rejected."""
        path = self.destination.get().strip()
        problem = None
        if not os.path.isfile(path):
            problem = "The MATLAB file was not found:\n%s" % path
        else:
            try:
                found = read_variables(path)
            except UnicodeError:
                found = None
                problem = ("The MATLAB file can't be read as UTF-8 text:\n%s\n\n"
                           "Re-save it as UTF-8 (in MATLAB or Notepad: Save As > "
                           "Encoding: UTF-8)." % path)
            except OSError as error:
                found = None
                problem = "The MATLAB file can't be opened:\n%s\n\n%s" % (path, error)
            if found == {}:
                problem = (
                    "No variables found in the MATLAB file:\n%s\n\n"
                    "Only plain value lines are read, e.g.\n"
                    "    battery = 95;\n    pos = [1 2 3];\n    name = 'rover';\n"
                    "    ok = true;   %% comment\n"
                    "Lines like  x = a + b  or  z = zeros(3)  are calculations and "
                    "are ignored. Add at least one plain line like the examples, or "
                    "check that the MatlabFile input points at the right file." % path)
        if problem:
            messagebox.showerror("Configuration", problem, parent=self)
            self.status.set("Destination problem - see message.")
            return
        super()._config()

    def _read_state(self):
        try:
            data = json.loads(Path(gui.STATE_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _restore_state(self):
        self.source.set(self.gh_source)
        self.destination.set(self.gh_destination)
        state = self._read_state()

        mode = state.get("mode")
        self.mode.set(mode if mode in gui.MODES else gui.MODES[0])
        self.renames = dict(state.get("renames") or {})

        # A saved configuration only applies to the same .m file.
        same_dest = (
            not state.get("destination")
            or os.path.normcase(os.path.abspath(state["destination"]))
            == os.path.normcase(os.path.abspath(self.gh_destination)))

        source = self._variables()
        destination = self._destination_variables()
        selected, mappings = [], {}
        if same_dest:
            selected = [n for n in state.get("selected", []) if n in source]
            mappings = {s: d for s, d in state.get("mappings", {}).items()
                        if s in source and d in destination}
        self.config_selected = selected
        self.config_mappings = mappings
        self.config_signature = (
            self._current_signature() if selected and mappings else None)

        self._mode(reset=False)
        self._load()

        if self.config_signature:
            self.status.set(
                "Last saved state restored: %d variable(s), %d link(s)."
                % (len(selected), len(mappings)))
        else:
            self.status.set("Click 'Configure Transfer' to review the matches.")
        # Open the configuration window straight away, like the standalone
        # GUI does once both files are chosen.
        if not self.config_signature:
            self.after(200, self._config)
        return True

    # ---- saving: also remember renames + that a config was saved -----------
    def _save_state(self):
        state = {
            "source": self.source.get().strip(),
            "destination": self.destination.get().strip(),
            "mode": self.mode.get(),
            "selected": self.config_selected,
            "mappings": self.config_mappings,
            "renames": self.renames,
            "configured": bool(
                self.config_signature
                and self.config_signature == self._current_signature()),
        }
        try:
            Path(gui.STATE_FILE).write_text(json.dumps(state, indent=2),
                                            encoding="utf-8")
        except OSError:
            pass

    def _save_config(self, selected, mappings, source_changes):
        old = dict(self.renames)
        self.renames = compose_renames(old, source_changes)
        ok = super()._save_config(selected, mappings, source_changes)
        if ok is False:
            self.renames = old
            return False
        self._save_state()
        return ok


def main():
    source, destination, config = (os.path.abspath(p) for p in sys.argv[1:4])
    gui.STATE_FILE = Path(config)
    GrasshopperTransferGUI.gh_source = source
    GrasshopperTransferGUI.gh_destination = destination
    GrasshopperTransferGUI().mainloop()


if __name__ == "__main__":
    main()
