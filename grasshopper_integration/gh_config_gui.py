"""gh_config_gui.py - opens Transfer Configuration window and
saves the result to a JSON file that the Grasshopper Transfer block reads.

Usage (the GUI block runs this for you):
    python gh_config_gui.py <gh_variables.json> <matlab_file.m> <config_out.json>
"""
import json
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from config import ConfigEditor            # noqa: E402  (existing GUI)
from variable_transfer_v2 import read_variables  # noqa: E402


def main():
    vars_json, matlab_file, config_out = sys.argv[1:4]

    with open(vars_json, encoding="utf-8") as f:
        source_variables = json.load(f)               # {name: value-string}
    destination_variables = read_variables(matlab_file)

    # Re-open with the previously saved choices, if any.
    saved_selected, saved_mappings = None, None
    if os.path.isfile(config_out):
        with open(config_out, encoding="utf-8") as f:
            old = json.load(f)
        saved_selected = old.get("selected")
        saved_mappings = old.get("mappings")

    root = tk.Tk()
    root.withdraw()

    def on_save(selected, mappings, source_changes):
        with open(config_out, "w", encoding="utf-8") as f:
            json.dump({"selected": selected,
                       "mappings": mappings,
                       "source_changes": source_changes}, f, indent=2)
        return True

    editor = ConfigEditor(root, source_variables, destination_variables, on_save,
                          saved_selected=saved_selected,
                          saved_mappings=saved_mappings)
    editor.protocol("WM_DELETE_WINDOW", editor.destroy)
    root.wait_window(editor)
    root.destroy()


if __name__ == "__main__":
    main()
