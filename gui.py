import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

VARIABLE_PATTERN = re.compile(r"^\s*([A-Za-z_]\w*)\s*=")
MODES = ["All Variables", "Include Variables", "Exclude Variables"]

# The class represents then entire application window
class VariableTransferGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Grasshopper–HabSim Variable Transfer")
        self.minsize(720, 430) #window size is set to 720x430 pixels

        self.source_file = tk.StringVar()
        self.destination_file = tk.StringVar()
        self.mode = tk.StringVar(value=MODES[0])
        self.status = tk.StringVar(value="Ready")

        self._build_ui()
        self._update_variable_controls()

    # builds the user interface of the application
    def _build_ui(self):
        # Main layout (window resizing)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        # Main frame
        main = ttk.Frame(self, padding=16)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)
        main.rowconfigure(4, weight=1)

        # Source file
        ttk.Label(main, text="Source file:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(main, textvariable=self.source_file).grid(row=0, column=1, sticky="ew", pady=6)
        ttk.Button(main, text="Browse…", command=self._browse_source).grid(row=0, column=2, padx=(8, 0), pady=6)

        # Destination file
        ttk.Label(main, text="Destination file:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=6)
        ttk.Entry(main, textvariable=self.destination_file).grid(row=1, column=1, sticky="ew", pady=6)
        ttk.Button(main, text="Browse…", command=self._browse_destination).grid(row=1, column=2, padx=(8, 0), pady=6)

        # Mode
        ttk.Label(main, text="Mode:").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=6)
        mode_box = ttk.Combobox(main, textvariable=self.mode, values=MODES, state="readonly")
        mode_box.grid(row=2, column=1, sticky="ew", pady=6)
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._update_variable_controls())

        # Variable selection area
        self.variable_frame = ttk.LabelFrame(main, text="Variables", padding=10)
        self.variable_frame.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(12, 8))
        self.variable_frame.columnconfigure(0, weight=1)
        self.variable_frame.rowconfigure(0, weight=1)

        list_frame = ttk.Frame(self.variable_frame)
        list_frame.grid(row=0, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.variable_listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,
            exportselection=False,
            height=10,
        )
        self.variable_listbox.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.variable_listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.variable_listbox.configure(yscrollcommand=scrollbar.set)

        button_row = ttk.Frame(self.variable_frame)
        button_row.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(button_row, text="Select All", command=self._select_all).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(button_row, text="Clear Selection", command=self._clear_selection).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(button_row, text="Refresh", command=self._load_variables).grid(row=0, column=2)

        # Future backend hook
        action_row = ttk.Frame(main)
        action_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        action_row.columnconfigure(0, weight=1)
        self.transfer_button = ttk.Button(
            action_row,
            text="Transfer (backend not connected yet)",
            state="disabled",
        )
        self.transfer_button.grid(row=0, column=0, sticky="e")

        # Status bar
        ttk.Separator(main).grid(row=6, column=0, columnspan=3, sticky="ew", pady=(12, 6)) #seperator line
        ttk.Label(main, text="Status:").grid(row=7, column=0, sticky="w")
        ttk.Label(main, textvariable=self.status).grid(row=7, column=1, columnspan=2, sticky="w") #displays whatever is inside variable box

    # Browse for source file
    def _browse_source(self):
        path = filedialog.askopenfilename(
            title="Choose source file",
            #filter for file types that can be selected
            filetypes=[
                ("Supported files", "*.py *.m *.txt *.csv"),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )
        #if a file was selected, set the source_file variable and update the status
        if path:
            self.source_file.set(path) #saves the selected path
            self.status.set(f"Source selected: {os.path.basename(path)}") #upates the status bar to show the selected file name
            self._load_variables() #automatically loads the variables from the selected source file

    def _browse_destination(self):
        path = filedialog.askopenfilename(
            title="Choose destination file",
            filetypes=[
                ("Supported files", "*.py *.m *.txt *.csv"),
                ("Python files", "*.py"),
                ("MATLAB files", "*.m"),
                ("All files", "*.*"),
            ],
        )
        #if a file was selected, set the destination_file variable and update the status
        if path:
            self.destination_file.set(path)
            self.status.set(f"Destination selected: {os.path.basename(path)}")

    # This functions reads the srource file line by line and extracts the variable names from it. It then populates the listbox with the variable names.
    def _load_variables(self):
        self.variable_listbox.delete(0, tk.END)
        path = self.source_file.get().strip()

        # Check if the source file path is valid
        if not path:
            self.status.set("Choose a source file to load variables.")
            return

        # Check if the source file exists
        if not os.path.isfile(path):
            self.status.set("Source file could not be found.")
            return

        variables = [] #empty list to store the variable names

        #reads the source file and extracts variable names 
        try:
            with open(path, "r", encoding="utf-8") as file: #opens the source file in read mode with utf-8 encoding, "r" means read mode
                #reads the source file line by line
                for line in file:
                    match = VARIABLE_PATTERN.match(line) #checks if the line matches the variable assignment pattern (e.g., variable_name = value)
                    #if a match is found, extract the variable name and add it to the list if it's not already present
                    if match:
                        name = match.group(1)
                        if name not in variables: #checks if the variable name is already in the list to avoid duplicates
                            variables.append(name)
        except (OSError, UnicodeError) as exc:
            messagebox.showerror("File error", str(exc))
            self.status.set("Could not read source file.")
            return

        # Populate the listbox with the extracted variable names
        for variable in variables:
            self.variable_listbox.insert(tk.END, variable)

        #update the status bar to show how many variables were loaded or if none were found
        if variables:
            self._select_all()
            self.status.set(f"Loaded {len(variables)} variable(s).")
        else:
            self.status.set("No simple variable assignments were found.")

    #Select all variables in the listbox
    def _select_all(self):
        if self.variable_listbox.size():
            self.variable_listbox.selection_set(0, tk.END)

    #Clear all selections in the listbox
    def _clear_selection(self):
        self.variable_listbox.selection_clear(0, tk.END)

    #updates the variable selection controls based on the selected mode. If "All Variables" is selected, the variable selection frame is hidden. Otherwise, it is shown and the variables are loaded from the source file.
    def _update_variable_controls(self):
        if self.mode.get() == "All Variables":
            self.variable_frame.grid_remove()
        else:
            self.variable_frame.grid()
            self._load_variables()

    #returns a list of the currently selected variables in the listbox
    def get_selected_variables(self):
        return [self.variable_listbox.get(i) for i in self.variable_listbox.curselection()]


if __name__ == "__main__":
    app = VariableTransferGUI()
    app.mainloop()
