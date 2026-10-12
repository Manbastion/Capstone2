# Grasshopper ↔ MATLAB Variable Transfer: Setup Guide

> **Notification update:** keep the integration in its checked-in folder and use
> the Capstone2 project root as `Repo`. The updated block scripts find the nested
> modules automatically; the older “all in the same folder” instruction below is
> no longer needed. Re-paste the current block source into existing definitions.
> See the repository-root `NOTIFICATIONS.md` for desktop/phone alerts and the
> optional final-loop block. The GUI now includes **Notifications…**.

This tool moves variables from Grasshopper into a MATLAB script, runs the script, and brings the results back into Grasshopper. It is made of three Grasshopper blocks:

| Block | What it does |
|---|---|
| **1. GUI** (optional) | Opens the full *Variable Transfer* window, the same one as the standalone app, but using the Grasshopper variables as the source and the connected `.m` file as the destination. Your choices are saved and used by Block 2. |
| **2. Transfer Variables** | Writes the Grasshopper values into your MATLAB `.m` file. |
| **3. Run MATLAB** | Runs the `.m` file (using `run_matlab_gh.py`) and outputs the resulting variables to Grasshopper. |

---

## Part 1: What you need installed

| Software | Version | Why |
|---|---|---|
| Windows | 10 or 11 | The blocks launch programs using Windows paths. |
| **Rhino 8** (includes Grasshopper) | 8 or newer | Needed for the **Python 3 Script** component. Rhino 7 will not work. |
| **MATLAB** | R2019a or newer | Must support the `matlab -batch` command. |
| **Python 3** (from python.org) | 3.9 or newer | Used only to open the GUI window (Block 1). |

### 1.1 Install Python (with tkinter)

The GUI window is built with **tkinter**, which is included in the standard Python installer for Windows. It is usually not included in other Python distributions, such as the Microsoft Store version.

1. Go to <https://www.python.org/downloads/windows/> and download the latest **Windows installer (64-bit)**.
2. Run the installer. On the first screen:
   - ✅ Tick **"Add python.exe to PATH"**.
   - Choose **Customize installation**.
3. On *Optional Features*, make sure **"tcl/tk and IDLE"** is ticked. This is tkinter. Click **Next**.
4. Finish the installation.

### 1.2 Check that Python and tkinter work

Open **Command Prompt** (press the Windows key, type `cmd`, press Enter) and run:

```
python --version
```

It should print a version such as `Python 3.12.x`. Then run:

```
python -m tkinter
```

A small window titled **"tk"** should appear. Close it. If you get `No module named 'tkinter'`, tkinter is missing. Re-run the Python installer, choose **Modify**, and tick **tcl/tk and IDLE**.

> **Note:** If `python --version` opens the Microsoft Store or says Python is not found, the PATH option was not ticked, or the Store shortcut is intercepting the command. Re-run the installer and tick **Add python.exe to PATH**. You can also skip PATH and use the full path in Block 1 (see Part 3).

### 1.3 Find your Python path (you may need it later)

In Command Prompt, run:

```
where python
```

Copy the first path that does **not** contain `WindowsApps`, for example:

```
C:\Users\YourName\AppData\Local\Programs\Python\Python312\python.exe
```

### 1.4 Check that MATLAB can run from the command line

In Command Prompt, run:

```
matlab -batch "disp('hello')"
```

MATLAB should start, print `hello`, and exit.

If you get *"'matlab' is not recognized"*, MATLAB is not on your PATH. That is fine. Find `matlab.exe`, usually at:

```
C:\Program Files\MATLAB\R2024b\bin\matlab.exe
```

(the version folder will match your install). You will paste this path into Block 3 (see Part 3).

---

## Part 2: Prepare the project folder

1. Put the project folder somewhere simple, for example `C:\Capstone2`. Avoid very long paths and OneDrive-synced folders.
2. Confirm these files are **all in the same folder**:

   - `variable_transfer_v2.py`
   - `config.py`
   - `fuzzy_algorithm.py`
   - `gui.py`
   - `history.py`
   - `gh_bridge.py`
   - `gh_gui.py`
   - `run_matlab_gh.py`

   If you downloaded the project as a ZIP, the files may be inside a folder within a folder (for example `Capstone2-main\Capstone2-main`). Use the inner folder that actually contains these files.

3. Note the full path to this folder. You will call it the **Repo path** below.
4. Prepare your **MATLAB `.m` file**:
   - Variables that Grasshopper should overwrite must be simple numeric assignments on their own line, for example:
     ```matlab
     battery = 95;
     altitude = 100;   % comments after the value are fine
     ```
   - Variables that do not already exist in the `.m` file are **not** added. Only existing ones are overwritten.
   - The script must run on its own, without needing input from the user.
5. ⚠️ **Make a backup copy of your `.m` file.** Block 2 permanently overwrites the values in this file.

---

## Part 3: Build the blocks in Grasshopper

Do this once. Save the Grasshopper file afterwards.

### 3.1 How to add a Python block

1. Double-click an empty area of the canvas, type `Python 3`, and press Enter. Choose **Python 3 Script**.
2. **Rename inputs and outputs.** Zoom in on the component until small **+** and **−** icons appear on its left and right edges. Click **+** to add an input or output. Click the name to rename it. Names must match **exactly**, including capital letters.
3. **Set access and type for each input.** Right-click the input's name and set:
   - **Item Access** or **List Access**, as shown in the tables below.
   - **Type hint**, as shown in the tables below.
4. **Paste the code.** Double-click the component to open the script editor. Delete any existing code, paste the full contents of the matching file from the `grasshopper_blocks` folder (the first line `#! python 3` should stay), and close the editor.

> ⚠️ **Most common mistake:** `Names` and `Values` must be set to **List Access**. If they are on Item Access, the block runs once per item and reports *"Names and Values must be the same length"*.

### 3.2 Block 1: GUI (optional)

Paste in: `grasshopper_blocks/block1_gui_config.py`

| Input | Access | Type hint | What to connect |
|---|---|---|---|
| `Repo` | Item | str | Panel containing the Repo path |
| `Names` | **List** | str | Panel with one variable name per line |
| `Values` | **List** | float | Number sliders or a panel of numbers (same count and order as `Names`) |
| `MatlabFile` | Item | str | Panel with the full path to your `.m` file |
| `PythonExe` | Item | str | Panel with the Python path from step 1.3 (needed if `python` is not on PATH) |
| `Open` | Item | bool | A **Button** |

| Output | Use |
|---|---|
| `Config` | Wire to Block 2's `Config` input |
| `Status` | Connect to a Panel to read messages |

### 3.3 Block 2: Transfer Variables

Paste in: `grasshopper_blocks/block2_transfer_variables.py`

| Input | Access | Type hint | What to connect |
|---|---|---|---|
| `Repo` | Item | str | Same Repo panel |
| `Names` | **List** | str | Same names as Block 1 |
| `Values` | **List** | float | Same values as Block 1 |
| `MatlabFile` | Item | str | Same `.m` file path panel |
| `Config` | Item | str | Block 1's `Config` output (optional) |
| `Run` | Item | bool | A **Button** |

| Output | Use |
|---|---|
| `MatlabFile_Out` | Wire to Block 3's `MatlabFile` input |
| `Report` | Panel showing which values changed |
| `Status` | Panel showing messages |

If `Config` is not connected (or no configuration has been saved yet), the block overwrites variables that have the **same name** in the `.m` file and ignores the rest. If the saved configuration was made for a different `.m` file, it is ignored and the block says so in `Report`.

### 3.4 Block 3: Run MATLAB

Paste in: `grasshopper_blocks/block3_run_matlab.py`

| Input | Access | Type hint | What to connect |
|---|---|---|---|
| `Repo` | Item | str | Same Repo panel |
| `MatlabFile` | Item | str | **Block 2's `MatlabFile_Out`** |
| `MatlabExe` | Item | str | Panel with the full `matlab.exe` path (only needed if the test in step 1.4 failed) |
| `PythonExe` | Item | str | Optional. If set, MATLAB is run by `run_matlab_gh.py` in its own Python process. If empty, it runs inside Grasshopper. |
| `Run` | Item | bool | A **Button** |

| Output | Use |
|---|---|
| `Names` | Names of the variables MATLAB produced |
| `Values` | Their values |
| `Status` | Panel showing messages |

### 3.5 Wiring summary

```
[Repo panel] ─────────────► Repo (all three blocks)
[Names panel] ────────────► Names (Blocks 1 and 2)
[Values / sliders] ───────► Values (Blocks 1 and 2)
[.m file panel] ──────────► MatlabFile (Blocks 1 and 2)

Block 1 (Config) ─────────► Block 2 (Config)
Block 2 (MatlabFile_Out) ─► Block 3 (MatlabFile)
```

Connect a **Panel** to every `Status` output so you can read messages.

---

## Part 4: Using it

1. **(Optional) Configure the transfer.**
   Press the **Open** button on Block 1. The *Variable Transfer* window opens with the **Source file** (your Grasshopper variables) and **Destination file** (your `.m` file) already filled in and locked. The *Transfer Configuration* screen opens automatically the first time.
   - It suggests matches between your Grasshopper variable names and the MATLAB variable names.
   - Double-click the **Transfer** column to tick or untick a variable. Double-click **Destination Variable** to pick a different MATLAB variable, or double-click **Source Variable** to rename one.
   - Choose the **Mode** (*All*, *Include* or *Exclude Variables*) in the main window.
   - Click **Save Configuration**. Block 2 uses these settings every time it runs, until you save a new configuration.
   - The window's own **Transfer** and **History** buttons also work, as in the standalone app. Block 2 records its transfers in the same History.
   - The window shows a snapshot of the Grasshopper values from the moment you pressed **Open**. Press **Open** again after changing values if you want to see them updated.
2. **Transfer the variables.**
   Press the **Run** button on Block 2. `Status` should say *"Transfer complete."* and `Report` lists what changed.
3. **Run MATLAB.**
   Press the **Run** button on Block 3. **Grasshopper will appear frozen while MATLAB runs. This is normal.** When MATLAB finishes, `Status` says how many variables were read, and `Names` / `Values` hold the results.
4. **Repeat.** Change your Grasshopper values and press the buttons again, in order: Block 2, then Block 3.

### Running MATLAB without Grasshopper (for debugging)

`run_matlab_gh.py` also works on its own. In Command Prompt:

```
python run_matlab_gh.py "C:\path\to\matlab_variables.m"
```

It runs the script and writes `matlab_output_variables.txt` next to it. If this works but Block 3 doesn't, the problem is in the Grasshopper wiring, not MATLAB.

### Where things are saved

| Item | Location |
|---|---|
| MATLAB output (text) | `matlab_output_variables.txt`, in the same folder as your `.m` file |
| Saved GUI configuration | `C:\Users\<you>\CapstoneGH\transfer_config.json` |
| Grasshopper variables as a file (the GUI's "source file") | `C:\Users\<you>\CapstoneGH\grasshopper_variables.txt` |
| Transfer history | `history.json`, in the project folder |

### What happens to your `.m` file

- **Block 2** permanently overwrites the matching variable values in the `.m` file.
- **Block 3** adds a temporary export section to the file, runs it, and then restores the file to exactly what it was before. This also happens if MATLAB fails.

---

## Part 5: Troubleshooting

| Message or problem | Cause and fix |
|---|---|
| `Names and Values must be the same length (got 2 names, 1 values)` | `Names` or `Values` is on Item Access (right-click the input → **List Access**), or the two lists have different lengths. |
| `Status` shows two entries instead of one | Same cause: an input is on Item Access instead of List Access. |
| `[WinError 2] The system cannot find the file specified` in Block 1 | Python was not found. Put the full Python path from step 1.3 into `PythonExe`. |
| `[WinError 2] ...` in Block 3 | MATLAB was not found. Put the full `matlab.exe` path from step 1.4 into `MatlabExe`. |
| `No module named 'gh_bridge'` | The `Repo` path is wrong, or `gh_bridge.py` is not in that folder. Check Part 2. |
| Pressing **Open** shows no error but no window appears | The GUI crashed in the background, usually because tkinter is missing. In Command Prompt, run `python -m tkinter` to test it (step 1.2). To see the actual error, run (all on one line, with your own paths): `python "C:\path\to\Capstone2\gh_gui.py" "%USERPROFILE%\CapstoneGH\grasshopper_variables.txt" "C:\path\to\matlab_variables.m" "%USERPROFILE%\CapstoneGH\transfer_config.json"` |
| The window opens but the file boxes can't be changed | By design. The source is the Grasshopper variables and the destination is the `.m` file wired into Block 1. To use a different `.m` file, change the Panel wired to `MatlabFile` and press **Open** again. |
| Block 2 says `no saved GUI config - used same-name matching` | No configuration has been saved yet, or `Config` isn't wired from Block 1. Press **Open** on Block 1 and click **Save Configuration**. |
| Block 2 says `history not recorded` | Harmless. The transfer still happened. It means Grasshopper's Python has no tkinter, which the History log needs. |
| `MATLAB file not found` | Check the `.m` file path for typos. Do not include quotation marks in the Panel. |
| `MATLAB failed: ...` | Open the `.m` file in MATLAB and run it manually to check for errors. It must run without user input. |
| `MATLAB finished but wrote no output file` | The script may have stopped early or called `exit` or `quit`. Remove those lines. |
| A variable was not transferred | It must already exist in the `.m` file as a simple line like `name = 5;`. Check `Report` for warnings. |
| Block shows red with an error balloon | Hover over the balloon, or read the `Status` panel. |
| Changes to the script code are not taking effect | Press **F5** to recompute, or click the block and change any input. |

---

## Part 6: Current limitations

- Edits to a **Source Value** inside the window apply to that window's own *Transfer* button only. Block 2 always uses the live Grasshopper values, so change values in Grasshopper. Renames and links are kept.
- Only **simple numeric scalar** variables can be sent to MATLAB (for example `battery = 95;`). Matrices, strings and structs are not supported as inputs.
- Matrix results from MATLAB come back as **text** (for example `[1 2;3 4]`). Scalars come back as numbers.
- Grasshopper is unresponsive while MATLAB is running.
- Grasshopper does not allow wires to loop back on themselves, so automatic repeating requires an extra component such as **Timer** or the **Anemone** plugin.
- The buttons are separate Grasshopper **Button** components wired to each block, not buttons drawn on the block itself.
