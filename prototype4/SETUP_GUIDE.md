# Grasshopper ↔ MATLAB Variable Transfer: Setup Guide

This tool moves variables from Grasshopper into a MATLAB script, lets you run that script, and gives you the results as a file you can read back into Grasshopper.

| Step | Where | What it does |
|---|---|---|
| **1. GUI block** (optional) | Grasshopper | Opens the *Variable Transfer* window: choose which variables to send and how they map to MATLAB names. Settings are saved. |
| **2. Transfer Variables block** | Grasshopper | Writes the Grasshopper values into your MATLAB `.m` file, using the saved GUI settings. |
| **3. Run MATLAB block** | Grasshopper | Opens your `run_matlab.py` (with the settings from the block's inputs). It runs the `.m` file and writes the resulting variables to a `.json` (or `.csv` / `.txt`) file. |
| **4. Read the results** | Grasshopper | Read that output file back into Grasshopper (see Part 5). |

Typical loop: change Grasshopper values → press **Run** on the Transfer block → press **Run** on the Run MATLAB block → read the output file.

---

## Part 1: What you need installed

| Software | Version | Why |
|---|---|---|
| Windows | 10 or 11 | The blocks use Windows paths. |
| **Rhino 8** (includes Grasshopper) | 8 or newer | Needed for the **Python 3 Script** component. Rhino 7 will not work. |
| **MATLAB** | R2021a or newer | Needs the `matlab -batch` command. The JSON output uses an option added in R2021a. |
| **Python 3** (python.org) | **3.10 or newer** | Opens the GUI window (needs tkinter) and runs `run_matlab.py` (uses `match`, which needs 3.10+). |

### 1.1 Install Python (with tkinter)

tkinter draws the GUI window. It is included in the standard installer from python.org, but is often **missing** from Python copies bundled inside other software (for example Maptek Vulcan) and from the Microsoft Store version.

1. Download the **Windows installer (64-bit)** from <https://www.python.org/downloads/windows/>.
2. Run it. On the first screen tick **"Add python.exe to PATH"**, then choose **Customize installation**.
3. On *Optional Features*, make sure **"tcl/tk and IDLE"** is ticked.
4. Finish the installation.

If you can't install software, you can use an existing Python as long as it is 3.10+ and passes the tkinter test below. Test the one you plan to use (for example the interpreter VS Code uses).

### 1.2 Check Python and tkinter

Open **Command Prompt** and run:

```
python --version
python -m tkinter
```

The first should print `Python 3.10` or higher. The second should open a small window titled **"tk"**; close it. If you get `No module named 'tkinter'`, re-run the Python installer, choose **Modify**, and tick **tcl/tk and IDLE**.

To find the full path of the Python you are using, run `where python`, or in VS Code run:

```python
import sys
print(sys.executable)
```

Keep that path (for example `C:\Users\you\AppData\Local\Programs\Python\Python312\python.exe`). Ignore any path containing `WindowsApps` (the Microsoft Store shortcut).

### 1.3 Check that MATLAB runs from the command line

```
matlab -batch "disp('hello')"
```

MATLAB should start, print `hello`, and exit. If you get *"'matlab' is not recognized"*, add the folder containing `matlab.exe` (for example `C:\Program Files\MATLAB\R2024b\bin`) to your Windows PATH, then open a new Command Prompt and test again.

---

## Part 2: Prepare the project folder

1. Put the project folder somewhere simple, for example `C:\Capstone2`. Avoid OneDrive-synced folders.
2. Confirm these files are **all in the same folder**:

   - `variable_transfer_v2.py`
   - `config.py`
   - `fuzzy_algorithm.py`
   - `gui.py`
   - `history.py`
   - `gh_bridge.py`
   - `gh_gui.py`
   - `matlab_literals.py`, `value_formats.py`, `format_editor.py`  (converts values to MATLAB and holds the Value Formats window)
   - `run_matlab_import_python_v2.py`  (runs MATLAB; used by `run_matlab.py`)
   - `run_matlab.py`  (your script; the Run MATLAB block opens it, see Part 5)

   The three scripts in `grasshopper_blocks` (`block1_gui_config.py`, `block2_transfer_variables.py`, `block3_run_matlab.py`) are pasted into Grasshopper in Part 3 and can live anywhere.

   If you downloaded the project as a ZIP, the files may be inside a folder within a folder (for example `Capstone2-main\Capstone2-main`). Use the inner folder that actually contains these files.

3. Note the full path of this folder. This is the **Repo path** used below.
4. Prepare your **MATLAB `.m` file**. The tool finds variables written as `name = value`, and replaces the value:
   ```matlab
   battery = 95;                  % a number (the ; and a comment are fine)
   meteorite.IL = 1               % a struct field: dotted names work
   coords = [0 0];               % a coordinate / vector of any length
   t = [0:5:100];                 % a range (replaced by real data from Grasshopper)
   M = [1 2; 3 4];                % a matrix, also fine over several lines
   name = 'rocket';               % text ("rocket" in double quotes works too)
   flag = false;                  % true / false
   labels = {'a','b','c'};        % a cell array
   ```
   - Only variables that **already exist** in the `.m` file are overwritten. New ones are not added.
   - Lines that are calculations, such as `v = v0 + a*t;` or `zeros(3)`, are ignored.
   - Whole structs can't be sent, but struct *fields* like `meteorite.IL` can.
   - The script must run on its own, without asking for input.
5. ⚠️ **Make a backup copy of your `.m` file.** The Transfer block permanently overwrites the values in it.

---

## Part 3: Build the blocks in Grasshopper

Do this once, then save the Grasshopper file.

### 3.1 How to add a Python block

1. Double-click an empty area of the canvas, type `Python 3`, and press Enter. Choose **Python 3 Script**.
2. **Rename inputs and outputs.** Zoom in on the component until small **+** and **−** icons appear on its left and right edges. Click **+** to add one. Click a name to rename it. Names must match **exactly**, including capital letters.
3. **Set access and type for each input.** Right-click the input's name and set **Item**, **List** or **Tree** access and the **type hint**, as shown in the tables below.
4. **Paste the code.** Double-click the component to open the script editor, delete any existing code, and paste in the full contents of the matching script from the `grasshopper_blocks` folder (keep the first line `#! python 3`). **Press the ▶ (Run/Save) button in the editor, then close it.** Edits don't always apply until you do.

> ⚠️ **Most common mistake:** `Names` must be **List Access** and `Values` must be **Tree Access**. On Item Access the block runs once per item and reports *"Names and Values must match"*.

### 3.2 Block 1: GUI (optional)

Paste in: `grasshopper_blocks/block1_gui_config.py`

| Input | Access | Type hint | What to connect |
|---|---|---|---|
| `Repo` | Item | str | Panel containing the Repo path |
| `Names` | **List** | str | Panel with one variable name per line |
| `Values` | **Tree** | **none** | One branch per variable, same order as `Names` (see 3.5) |
| `MatlabFile` | Item | str | Panel with the full path to your `.m` file (no quotation marks) |
| `PythonExe` | Item | str | Panel with the full path to a Python that has tkinter (step 1.2). Needed if `python` isn't on your PATH. |
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
| `Values` | **Tree** | **none** | Same values as Block 1 |
| `MatlabFile` | Item | str | Same `.m` file path panel |
| `Config` | Item | str | Block 1's `Config` output (optional) |
| `Run` | Item | bool | A **Button** |

| Output | Use |
|---|---|
| `MatlabFile_Out` | The `.m` file path, but only after a successful transfer |
| `Report` | Panel showing which values changed |
| `Status` | Panel showing messages |

If `Config` is not connected, or no configuration has been saved yet, the block overwrites variables that have the **same name** in the `.m` file and ignores the rest. If the saved configuration was made for a different `.m` file, it is ignored and `Report` says so.

> **Check the `Values` type hint on BOTH Block 1 and Block 2.** Each block has its own. It must be **No type hint** with **Tree Access**. A hint such as `float` makes Grasshopper convert values *before* the script sees them. For example, the text `-0.54,-0.54` silently becomes the single number `0.7637` (its distance from the origin). Block 2's `Report` ends with a "received from Grasshopper" list showing the type and value of each variable, so you can spot this.

### 3.4 Block 3: Run MATLAB

Paste in: `grasshopper_blocks/block3_run_matlab.py`

This block **opens your own `run_matlab.py`**. It doesn't contain a copy of it. Before opening it, the block rewrites the three settings lines at the top of that file (`CAPSTONE_FOLDER`, `MATLAB_FILE` and `SAVE_TYPE`) from its inputs. Nothing else in the file is changed, so keep those three lines in their current form (`CAPSTONE_FOLDER = r"..."`, `MATLAB_FILE = r"..."`, `SAVE_TYPE = "..."`).

| Input | Access | Type hint | What to connect |
|---|---|---|---|
| `Repo` | Item | str | Same Repo panel |
| `RunScript` | Item | str | Panel with the full path to your `run_matlab.py` |
| `CapstoneFolder` | Item | str | Optional. The folder that contains `run_matlab_import_python_v2.py`. Empty = the Repo folder. |
| `MatlabFile` | Item | str | **Block 2's `MatlabFile_Out`** (or the same `.m` file panel) |
| `SaveType` | Item | str | Panel with `json`, `csv` or `txt`. Empty = `json`. |
| `PythonExe` | Item | str | Optional. Full path to a **Python 3.10+** `python.exe`. Empty = `python`. |
| `Run` | Item | bool | A **Button** |

| Output | Use |
|---|---|
| `OutputFile` | Path of the results file (`matlab_output_variables.json`, `.csv` or `.txt`, next to your `.m` file). Empty until MATLAB has written it. |
| `Ready` | `True` once MATLAB has written the output file during this run |
| `Status` | Panel showing messages |

### 3.5 Arranging `Values` and how they reach MATLAB

Give each variable its own **branch** in `Values`, in the same order as `Names`. The tool converts each value into the right MATLAB form **automatically**:

| In Grasshopper | In the `.m` file |
|---|---|
| `5`, `5.0`, `"5"` | `5` |
| `-1,0` or `(-1, 0)` or `<-1, 0>` (text) | `[-1 0]` |
| a branch with several numbers, or text `1 2 3` / `1,2,3` | `[1 2 3]` (any length) |
| a Grasshopper **Point** or **Vector** | `[x y z]` |
| text `1,2;3,4`, or branches `{2;0}`, `{2;1}` ... (rows of a matrix) | `[1 2;3 4]` |
| `True` / `"true"` | `true` |
| `hello`, `it's` | `'hello'`, `'it''s'` |
| a list of text items | `{'a','b'}` |
| `nan`, `inf`, `-inf` | `NaN`, `Inf`, `-Inf` |
| empty text / empty list | `''` / `[]` |

- Text that is not a number or list of numbers is sent as text. A list that mixes numbers and text becomes a cell array `{1,'x'}`.
- If the old value in the `.m` file used commas (`[1, 2, 3]`), or was a column (`[1;2;3]`), or used double quotes, the new value keeps that style.
- Text that *looks* like numbers (such as `007`) is sent as the number `7`. Use a **Value Format** (3.7) with *One piece of text* if you need it kept as text.
- Build the tree with **Merge** or **Entwine**, and check it with a **Param Viewer**. The number of branches must equal the number of names.

### 3.7 Value Formats: your own conversions

If your values look different from the table above, add a **Value Format**. Example: Grasshopper has `a = 1 | 2 | 3` and MATLAB should have `a = [1 2 3]`.

1. Press **Open** on Block 1 (Part 4.1), then click **Value Formats…** in the window.
2. The list on the left shows your formats. Use **Add**, **Duplicate**, **Remove**, **Move up** and **Move down**.
3. Select a format and fill in the form on the right:
   - **Name**: anything you like.
   - **Applies to variables**: a comma list such as `a, coords*` (`*` means "anything"). Leave empty to apply to every text value containing the separator.
   - **Item separator**: the character between items, e.g. `|`. Empty means spaces. **Row separator** (optional) starts a new matrix row.
   - **Strip characters**: brackets to remove first, e.g. `()`.
   - **Items are** (numbers, text, or either) and **Output as** (vector, column, cell array, string array, or one piece of text).
4. The line under the form shows an example, and the table at the bottom shows how **your current Grasshopper values** will be converted. The **Try it** box lets you type any value.
5. Click **Save**. The formats are stored in one file, `variable_formats.json`, and used by every transfer, so nothing in the code changes however many you add.

Rules that name their variables are checked first, then general ones, top to bottom. The first that fits wins; if none fits, the automatic conversion is used. A format with a problem can't be saved until you fix it or untick it.

### 3.6 Wiring summary

```
[Repo panel] ─────────────► Repo (all three blocks)
[Names panel] ────────────► Names (both blocks)
[Values tree] ────────────► Values (both blocks)
[.m file panel] ──────────► MatlabFile (Blocks 1 and 2)
[Python path panel] ──────► PythonExe (Blocks 1 and 3)
[run_matlab.py path] ─────► RunScript (Block 3)
[json / csv / txt panel] ─► SaveType (Block 3)

Block 1 (Config) ─────────► Block 2 (Config)
Block 2 (MatlabFile_Out) ─► Block 3 (MatlabFile)
```

Connect a **Panel** to every `Status` output so you can read messages.

---

## Part 4: Using the GUI and Transfer blocks

### 4.1 (Optional) Configure the transfer

Press the **Open** button on Block 1. The *Variable Transfer* window opens, the same window as the standalone app, with the **Source file** (your Grasshopper variables) and **Destination file** (your `.m` file) already filled in and locked. The *Transfer Configuration* screen opens automatically the first time.

- It suggests matches between your Grasshopper names and the MATLAB names.
- Double-click the **Transfer** column to tick or untick a variable. Double-click **Destination Variable** to pick a different MATLAB variable, or **Source Variable** to rename one.
- Choose the **Mode** (*All*, *Include* or *Exclude Variables*) in the main window.
- Click **Save Configuration**. Block 2 uses these settings every time it runs, until you save a new configuration.
- The window's own **Transfer** and **History** buttons also work, as in the standalone app. Block 2's transfers are recorded in the same History.
- The window shows a snapshot of the Grasshopper values from the moment you pressed **Open**. Press **Open** again after changing values to refresh it.

> A **Button** makes Grasshopper run the block twice (once pressed, once released), so `Status` shows a launch result only briefly. Block 1 therefore keeps it and shows it after the main message as `Last Open: ...`.

### 4.2 Transfer the variables

Press the **Run** button on Block 2. `Status` should say *"Transfer complete."* and `Report` lists what changed. Wait for this before running MATLAB.

---

## Part 5: Running MATLAB and reading the results

### 5.1 Run MATLAB from Grasshopper (Block 3)

1. Make sure Block 2 says *"Transfer complete."*.
2. Press **Run** on Block 3. It writes your three settings into `run_matlab.py`, then **opens a window** that runs your script. Grasshopper stays usable.
3. MATLAB starts without a window and runs the `.m` file. This can take from a few seconds to a minute or more, depending on your script. The block's `Status` says *"Running..."*.
4. When MATLAB has written the output file, `Status` says *"MATLAB finished - output is ready"*, `Ready` turns **True**, and `OutputFile` shows the file's path. This happens **before** you close the window.
5. The script's window then shows *"Done"* and waits. **Press ENTER in it to close it** (your script ends with `input(...)`).

Things to know:
- If the script **crashes** (for example a wrong folder or a missing file), its window stays open and shows the error, so you can read it. Press ENTER to close it.
- A **Toggle** left on runs the script once, when it turns on. Turn it off and on again to run again.
- Pressing **Run** while the previous window is still open does nothing. Close the window (ENTER) first.
- The block updates itself when the output appears. If it doesn't, press **F5**.

What the script does to your `.m` file: it adds a temporary export section at the end, runs it, then **restores the file exactly as it was**, even if MATLAB fails. It also deletes the temporary `vars.mat` and `vars.txt`.

### 5.2 Running the script by hand (alternative)

You can also run `run_matlab.py` yourself, in VS Code (**Run Python File**) or Command Prompt:

```
python "C:\Users\you\Capstone2\run_matlab.py"
```

In that case you set the three settings at the top of the file yourself:

```python
CAPSTONE_FOLDER = r"C:\Users\you\Capstone2"           # folder that contains run_matlab_import_python_v2.py
MATLAB_FILE = r"C:\Users\you\Downloads\ghtest.m"      # the SAME .m file the Grasshopper blocks use
SAVE_TYPE = "json"                                      # "json", "csv" or "txt"
```

`MATLAB_FILE` must be the same file as the `MatlabFile` panel in Grasshopper. Keep the `r` before the quotation marks and don't add a trailing backslash. If Block 3 is wired up, it overwrites these three lines every time it runs.

### 5.3 The output file

The results are written **next to your `.m` file**, and overwritten on every run:

| `SAVE_TYPE` | File | Best for |
|---|---|---|
| `"json"` (recommended) | `matlab_output_variables.json` | Everything: numbers, vectors, matrices and **structs** (`meteorite.IL` appears as nested `{"meteorite": {"IL": 1}}`). Needs MATLAB R2021a+. |
| `"txt"` | `matlab_output_variables.txt` | Simple variables only: lines like `name = value`. ⚠️ MATLAB stops with an error if the workspace contains a struct, so don't use it with names like `meteorite.IL`. |
| `"csv"` | `matlab_output_variables.csv` | Simple scalar variables only (one table row). Not suited to vectors of different lengths or structs. |

The export contains **every variable in the MATLAB workspace** when the script finishes, not just the ones you sent.

### 5.4 Read the results into Grasshopper

Use Block 3's `Ready` and `OutputFile` outputs to know when the file is there. Read the output file with whatever you normally use to bring files into Grasshopper. If you'd like to reuse the project's own reader, `gh_bridge.py` includes `read_results`, which understands the `json` and `txt` formats. It returns the names, with struct fields as dotted names like `meteorite.IL`, and the values as numbers or lists of numbers. In a **Python 3 Script** component with inputs `Repo` (str) and `File` (str, wire Block 3's `OutputFile` here) and outputs `Names` and `Values`:

```python
#! python 3
import sys
if Repo not in sys.path:
    sys.path.insert(0, Repo)
import gh_bridge
Names, Values = gh_bridge.read_results(File)
```

If a `matlab_output_variables.json` file exists next to the path you give it, it reads that one, even if you passed the `.txt` path. When you switch `SAVE_TYPE`, delete the old `matlab_output_variables.*` files first, so you don't read stale results. This reader was tested outside Grasshopper only. A vector comes back as a list of numbers, so `Values` is a list in which each item is a number or a list.

---

## Part 6: Where things are saved

| Item | Location |
|---|---|
| MATLAB output (`matlab_output_variables.*`) | Next to your `.m` file |
| Your `run_matlab.py` | Where you keep it. Block 3 rewrites its three settings lines each run. |
| Your Value Formats | `C:\Users\<you>\CapstoneGH\variable_formats.json` (can be copied to another computer) |
| Saved GUI configuration | `C:\Users\<you>\CapstoneGH\transfer_config.json` |
| Grasshopper variables as a file (the GUI's "source file") | `C:\Users\<you>\CapstoneGH\grasshopper_variables.txt` |
| Last GUI launch message and crash log | `C:\Users\<you>\CapstoneGH\last_gui_status.txt` and `gui_error.log` |
| Transfer history | `history.json`, in the project folder |

> **After replacing any `.py` file in the project folder, close and reopen Rhino.** Rhino keeps Python modules in memory until it closes, so an old copy can keep being used.

---

## Part 7: Troubleshooting

### Grasshopper blocks

| Message or problem | Cause and fix |
|---|---|
| `Names and Values must match: N names but M values/branches` | `Names` is on Item Access (set **List**) or `Values` is (set **Tree**), or the counts differ. With vectors, `Values` needs exactly one branch per name. |
| `Status` shows two entries instead of one | Same cause: `Names` or `Values` is on Item Access. |
| `Status` or an output shows `null` | The script code isn't applied or is empty. Open the script editor, check the code is there, press **▶**, and close it. Also check that the output names are exactly `Config` / `Status`, the component is enabled, and **Solution → Enable Solver** isn't showing. |
| `[WinError 2] The system cannot find the file specified` (Block 1) | Python was not found. Put the full Python path from step 1.2 into `PythonExe`. |
| The black command window flashes and the GUI doesn't open | The GUI crashed on start. Read `Status` (it shows `Last Open: ...` with the error) or open `CapstoneGH\gui_error.log`. If a black window still appears, an old `gh_bridge.py` is being used: replace it and restart Rhino. |
| `No module named 'tkinter'` | That Python has no tkinter. Install Python from python.org with **tcl/tk and IDLE** ticked (step 1.1), or point `PythonExe` at one that has it. |
| `SRE module mismatch`, or errors mentioning `.rhinocode\py39-rh8\Lib` | The external Python was loading Rhino's Python library. The current `gh_bridge.py` prevents this. Replace it and restart Rhino. |
| `No module named 'gh_bridge'` | The `Repo` path is wrong, or `gh_bridge.py` isn't in that folder. Check Part 2. |
| `No valid numeric GH variables ... Rejected: name (reason)` | The message lists each rejected variable and why. If a dotted name like `meteorite.IL` is called an *invalid name*, Rhino is using an old `variable_transfer_v2.py`: replace it and **restart Rhino**. |
| The window says *The MATLAB file was not found*, *No variables found*, or *can't be read as UTF-8* | The file wired into `MatlabFile` is missing, has no simple lines like `battery = 95;`, or isn't saved as UTF-8 (re-save it as UTF-8). The message names the file it tried to read. |
| The window's file boxes can't be changed | By design. To use a different `.m` file, change the `MatlabFile` panel and press **Open** again. |
| Block 2 says `no saved GUI config - used same-name matching` | No configuration has been saved, or `Config` isn't wired from Block 1. Press **Open** on Block 1 and click **Save Configuration**. |
| Block 2 says `history not recorded` | Harmless. The transfer still happened. It means Grasshopper's Python has no tkinter, which the History log needs. |
| A variable is missing from the transfer and listed as skipped | Its value couldn't be converted (see the reason in the message), for example matrix rows of different lengths, or a Value Format that expects numbers but got text. |
| A variable was not transferred | It must already exist in the `.m` file as a simple line like `name = 5;`. Check `Report` for warnings. |
| `MATLAB file not found` | Check the `.m` file path for typos. Don't include quotation marks in the Panel. |

### Running MATLAB (Block 3 and `run_matlab.py`)

| Message or problem | Cause and fix |
|---|---|
| Block 3: `MatlabFile is empty - has the Transfer block finished?` | `MatlabFile` is wired from Block 2's `MatlabFile_Out`, which stays empty until a transfer succeeds. Press **Run** on Block 2 first, or wire the `.m` path panel directly. |
| Block 3: `Could not find a line like CAPSTONE_FOLDER = r"..."` | The three settings lines at the top of `run_matlab.py` were changed. Restore them to the form `NAME = r"..."` (and `SAVE_TYPE = "json"`). |
| Block 3: `SaveType must be one of json, csv, txt` | Fix the text in the `SaveType` panel. |
| Block 3: `run_matlab.py not found` | Check the `RunScript` path. Don't include quotation marks. |
| A window opens and shows a Python error, and `Status` says the script stopped | Read the error in the window and see the rows below. The window stays open until you press ENTER. |
| `Status` says *Already running* | The previous script window is still open. Press ENTER in it (or close it) first. |
| `Status` stays at *Running...* and never says output is ready | MATLAB is slow or stuck (`pause`, `input`, a long loop), or it failed before writing the file. Look at the script window. Close it to stop MATLAB. |
| Nothing opens when you press **Run** | The block ran with `Run` already on. Use a Button, or turn the Toggle off and on. If `Status` shows an error, read it. |
| `SyntaxError` pointing at `match` | Your Python is older than 3.10. Use a newer Python (step 1.1). |
| `ModuleNotFoundError: No module named 'run_matlab_import_python_v2'` (or `variable_transfer_v2`) | `CAPSTONE_FOLDER` (Block 3's `CapstoneFolder`, or the Repo folder if that's empty) doesn't contain those files. |
| `FileNotFoundError: [WinError 2]` | `matlab` isn't on your PATH. Add MATLAB's `bin` folder to PATH (step 1.3) and open a new Command Prompt or VS Code. |
| `FileNotFoundError` for the `.m` file | `MATLAB_FILE` doesn't point at an existing file. |
| `CalledProcessError ... returned non-zero exit status` | MATLAB hit an error. Open the `.m` file in MATLAB and run it manually to see the message. It must run without user input. With `SAVE_TYPE = "txt"` this also happens when the workspace contains a struct: use `"json"`. |
| It seems stuck | MATLAB is slow, or the script is waiting (`pause`, `input`, a long loop). Close the window to stop it, and check the script by running it in MATLAB. |
| No output file appears | Look **next to the `.m` file**. If it's missing, the script may have called `exit`, `quit` or `return` early, so remove it. |
| Output file is old | The file is overwritten on every run. Check its modified time to confirm the run finished. |

---

## Part 8: Current limitations

- **The script window needs ENTER.** Your `run_matlab.py` ends with `input(...)`, so its window stays open until you press ENTER. The results are ready before that (`Ready` turns True). Remove that last line from the script if you don't want the pause.
- **Block 3 edits your `run_matlab.py`.** It rewrites the three settings lines every time it runs. Don't put anything you want to keep on those lines other than a trailing comment.
- **Grasshopper can't loop by itself.** Wires can't feed back into themselves, so repeating automatically needs an extra component such as **Timer** or the **Anemone** plugin.
- **Reading the results back into Grasshopper is separate** (Part 5.4). Block 3 gives you the output file's path, but doesn't read it.
- **Variables sent to MATLAB** can be numbers, text, true/false, vectors (any length), matrices, cell arrays of text, and struct fields such as `meteorite.IL`. Whole structs and cell arrays of vectors are not supported.
- **Only literal values in the `.m` file are replaced.** `x = linspace(0,1,10);` is a calculation and is left alone. Change it to `x = [0 1];` if Grasshopper should supply it.
- **Multi-line arrays in the `.m` file** are read and replaced, but the new value is written on one line.
- **Text containing a line break** can't be sent.
- **Vectors are sent as rows** (`[1 2 3]`) unless the old value was a column, or a Value Format says *Column vector*.
- **Edits to a *Source Value* inside the GUI window** apply to that window's own **Transfer** button only. The Transfer block always uses the live Grasshopper values, so change values in Grasshopper. Renames and links are kept.
- **Don't press Transfer while MATLAB is running**, because the script temporarily changes the `.m` file.
- **The buttons are separate Grasshopper Button components** wired to each block, not buttons drawn on the block itself.