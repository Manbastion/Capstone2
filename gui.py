import csv
import os
import tkinter as tk
from tkinter import *
from tkinter import ttk

root = Tk()
root.title("Variable Transfer")

modes = ["All Variables", "Exclude Variables", "Include Variables"]

mainframe = ttk.Frame(root, padding=(3, 3, 12, 12))
mainframe.grid(column=0, row=0, sticky=(N, W, E, S))

# Input File
input_file = StringVar()
input_file_entry = ttk.Entry(mainframe, width=7, textvariable=input_file)
input_file_entry.grid(column=2, row=1, sticky=(W, E))

# Output File
output_file = StringVar()
output_file_entry = ttk.Entry(mainframe, width=7, textvariable=output_file)
output_file_entry.grid(column=2, row=2, sticky=(W, E))

# Dropdown for Modes
selected_mode = StringVar()
mode_dropdown = ttk.Combobox(mainframe, textvariable=selected_mode, values=modes, state="readonly")
mode_dropdown.grid(column=2, row=3, sticky=(W, E))
mode_dropdown.current(0)  # Sets default to "All Variables"

# Status
status = StringVar()
ttk.Label(mainframe, textvariable=status).grid(column=3, row=2, sticky=(W, E))

# Labels
ttk.Label(mainframe, text="Input file: ").grid(column=1, row=1, sticky=W)
ttk.Label(mainframe, text="Output file: ").grid(column=1, row=2, sticky=E)
ttk.Label(mainframe, text="Mode: ").grid(column=1, row=3, sticky=W)
ttk.Label(mainframe, text="Status:").grid(column=1, row=4, sticky=W)

# -----------------------------------------------------------------
# Variable selection (dropdown-style menubutton, same look/row as
# the Mode combobox, plus a separate Check All / Uncheck All button)
# -----------------------------------------------------------------

SAMPLE_VARIABLES = ["Var1", "Var2", "Var3", "Var4", "Var5"]

variable_states = {}  # name -> BooleanVar

variables_label = ttk.Label(mainframe, text="Variables: ")

variables_menubutton = ttk.Menubutton(mainframe, text="Select Variables", direction="below")
variables_menu = Menu(variables_menubutton, tearoff=0)
variables_menubutton["menu"] = variables_menu

check_all_var = BooleanVar(value=True)
check_all_button = ttk.Checkbutton(
    mainframe,
    text="Check/Uncheck All",
    variable=check_all_var,
)


def get_variable_names():
    """Try to read column headers from the input CSV file.
    Falls back to a sample list if the file doesn't exist or can't be parsed."""
    path = input_file.get().strip()
    if path and os.path.isfile(path):
        try:
            with open(path, newline="") as f:
                reader = csv.reader(f)
                header = next(reader)
                if header:
                    return [h.strip() for h in header]
        except Exception:
            pass
    return SAMPLE_VARIABLES


def update_menubutton_text():
    total = len(variable_states)
    checked = sum(v.get() for v in variable_states.values())
    if total == 0:
        variables_menubutton.configure(text="Select Variables")
    else:
        variables_menubutton.configure(text=f"Variables ({checked}/{total} selected)")


def on_variable_toggle():
    # Called whenever an individual checkbutton in the menu changes,
    # keeps the "Check/Uncheck All" box in sync (checked only if all are checked)
    all_checked = all(v.get() for v in variable_states.values()) if variable_states else False
    check_all_var.set(all_checked)
    update_menubutton_text()


def populate_menu():
    variables_menu.delete(0, "end")
    variable_states.clear()

    names = get_variable_names()
    for name in names:
        var = BooleanVar(value=True)  # default: checked
        variable_states[name] = var
        variables_menu.add_checkbutton(
            label=name,
            variable=var,
            onvalue=True,
            offvalue=False,
            command=on_variable_toggle,
        )

    check_all_var.set(True)
    update_menubutton_text()


def toggle_check_all():
    new_state = check_all_var.get()
    for var in variable_states.values():
        var.set(new_state)
    update_menubutton_text()


check_all_button.configure(command=toggle_check_all)


def get_selected_variables():
    """Returns the list of currently checked variable names."""
    return [name for name, var in variable_states.items() if var.get()]


def on_mode_change(event=None):
    mode = selected_mode.get()
    if mode in ("Include Variables", "Exclude Variables"):
        populate_menu()
        variables_label.grid(column=1, row=5, sticky=W)
        variables_menubutton.grid(column=2, row=5, sticky=(W, E))
        check_all_button.grid(column=3, row=5, sticky=W)
    else:
        variables_label.grid_remove()
        variables_menubutton.grid_remove()
        check_all_button.grid_remove()


mode_dropdown.bind("<<ComboboxSelected>>", on_mode_change)


# Refresh the variable list if the input file changes while
# Include/Exclude is already selected
def on_input_file_change(*args):
    if selected_mode.get() in ("Include Variables", "Exclude Variables"):
        populate_menu()


input_file.trace_add("write", on_input_file_change)

# -----------------------------------------------------------------
# Layout adjustments
# -----------------------------------------------------------------
root.columnconfigure(0, weight=10)
root.rowconfigure(0, weight=4)
mainframe.columnconfigure(2, weight=10)

for child in mainframe.winfo_children():
    child.grid_configure(padx=5, pady=5)

root.mainloop()