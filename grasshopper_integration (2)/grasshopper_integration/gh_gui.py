"""gh_gui.py - your teammate's Variable Transfer window, run from Grasshopper.

It is the SAME window as gui.py (same config editor, fuzzy matching, History and
Transfer button). The only differences:
  * Source file      = the live Grasshopper variables (written by the GUI block)
  * Destination file = the MATLAB .m file wired into the block
  * The two Browse buttons are locked, because both files come from Grasshopper
  * Its saved state goes to the block's config file, not config_state.json,
    and also remembers renames so the Transfer block can re-apply them.

Usage (the GUI block runs this for you):
    python gh_gui.py <source.txt> <destination.m> <config.json>
"""
import json
import os
import sys
from pathlib import Path
from tkinter import ttk, messagebox

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
for parent in Path(HERE).parents:
    if (parent / "gui.py").is_file():
        if str(parent) not in sys.path:
            sys.path.insert(0, str(parent))
        break

import gui  # noqa: E402  (the existing window)
from gh_bridge import compose_renames  # noqa: E402


class GrasshopperTransferGUI(gui.VariableTransferGUI):
    gh_source = ""
    gh_destination = ""

    # ---- start-up: fixed files, restore saved choices -----------------------
    def __init__(self):
        self.renames = {}
        super().__init__()
        self.title("Grasshopper–HabSim Variable Transfer (live Grasshopper variables)")
        self._lock_file_pickers(self)

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
