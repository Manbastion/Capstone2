# Grasshopper–MATLAB Integration: Setup Guide

This system transfers Grasshopper values into a MATLAB `.m` file and/or CSV file, launches MATLAB, and can repeat the process for multiple iterations.

## 1. Requirements

- Windows 10/11
- Rhino 8 with Grasshopper and the Python 3 Script component
- MATLAB R2021a or newer
- Python 3.10+ with `tkinter`

Keep all project Python files together in one local folder. Avoid cloud-synchronised folders where possible. Connect this folder to the `Repo` input on each component.

Check MATLAB from Command Prompt:

```bat
matlab -batch "disp('hello')"
```

In MATLAB, run `matlabroot`. Copy the returned installation folder into the `MATLABRoot` input on Run MATLAB.

## 2. Add scripts as Grasshopper components

For each script in `grasshopper_blocks`:

1. Add a **Python 3 Script** component.
2. Add and rename its inputs and outputs to match the tables below.
3. Set each input's access and type hint as specified.
4. Paste the complete matching `.py` script into the component.
5. Connect its `Status` output to a Panel.

For an existing Grasshopper definition, update the component input/output
names and access settings to match the tables below, then replace each
component's script with the corresponding file in `grasshopper_blocks`.
Reconnect the trigger chain using the wiring diagrams.

`Names` must use **List** access. `Values` must use **Tree** access with **no type hint**. Use the same ordering for names and value branches.

## 3. Components

### Multi-run

Script: `grasshopper_blocks/multirun_controller.py`

| Input | Access | Type | Purpose |
|---|---|---|---|
| `Repo` | Item | str | Project folder |
| `Names` | List | str | Baseline variable names |
| `Values` | Tree | none | Baseline values, one branch per variable |
| `Names_1` … `Names_10` | List | str | Optional variable names for iterations 1–10 |
| `Values_1` … `Values_10` | Tree | none | Values paired with the corresponding `Names_N` |
| `EntwinedNames` | Tree | none | Optional Entwine-based iteration names |
| `EntwinedValues` | Tree | none | Optional Entwine-based iteration values |
| `PythonExe` | Item | str | Optional Python executable; empty uses `python` |
| `Open` | Item | bool | Button to open the multi-run editor |
| `Stop` | Item | bool | Button to stop after the current iteration |
| `SavePath` | Item | str | Optional JSON file path for this batch record |

Outputs: `Trigger` (bool), `Iteration` (int), `Status` (str).

The component opens the multi-run editor. Enter iteration values and press **Run iterations**. The `Trigger` output pulses once for each iteration and should connect to Transfer Variables MATLAB's `TriggerIn` input. It does not connect directly to Run MATLAB.

If using `Names_N` and `Values_N`, connect both inputs for each iteration. Each supplied name must exist in the baseline `Names` list. Do not provide the same variable twice for one iteration through both the numbered inputs and Entwine inputs.

At the end of each batch, a JSON record is merged into the existing `history.json`. Connect `SavePath` to optionally save a standalone JSON file at a chosen location. If it is not connected, the integration scans MATLAB's workspace for character-array or string variables that point to existing folders modified during the current run and saves `multirun_history.json` there. If MATLAB does not expose a valid `Output_Folder`, the batch is recorded in the existing history file. `SavePath` takes priority over MATLAB's output folder.

### GUI Config

Script: `grasshopper_blocks/gui_config.py`

| Input | Access | Type | Purpose |
|---|---|---|---|
| `Repo` | Item | str | Project folder |
| `Names` | List | str | Variable names |
| `Values` | Tree | none | Values |
| `MatlabFile` | Item | str | MATLAB `.m` file |
| `PythonExe` | Item | str | Optional Python executable |
| `Open` | Item | bool | Button to open the configuration window |

Outputs: `Config` (str), `Status` (str).

Use the GUI to configure how Grasshopper variables map to MATLAB variables. Connect the `Config` output to Transfer Variables MATLAB's `Config` input.

### Transfer Variables MATLAB

Script: `grasshopper_blocks/transfer_variables_matlab.py`

| Input | Access | Type | Purpose |
|---|---|---|---|
| `Repo` | Item | str | Project folder |
| `Names` | List | str | Variable names |
| `Values` | Tree | none | Values |
| `MatlabFile` | Item | str | MATLAB `.m` file to update |
| `Config` | Item | str | Optional GUI Config output |
| `TriggerIn` | Item | bool | Button for a single run, or Multi-run's `Trigger` |

Outputs: `Trigger` (bool), `Report` (list), `Status` (str).

On a successful transfer, `Trigger` becomes true for that solution. Connect it to Run MATLAB's `Trigger`, or to Transfer Variables CSV's `TriggerIn` when CSV updates are also required.

Without a saved GUI configuration, variables are matched by name. With a configuration, the saved mapping is applied. The `.m` file is modified in place. Back it up before use.

### Transfer Variables CSV

Script: `grasshopper_blocks/transfer_variables_csv.py`

| Input | Access | Type | Purpose |
|---|---|---|---|
| `Repo` | Item | str | Project folder |
| `Names` | List | str | Variable names |
| `Values` | Tree | none | Values |
| `CSVFile` | Item | str | CSV file to update |
| `Mapping` | List | str | One mapping rule per item |
| `TriggerIn` | Item | bool | Transfer Variables MATLAB's `Trigger` |

Outputs: `Trigger` (bool), `Report` (list), `Status` (str).

Each mapping line has this format:

```text
variable | identifier column | identifier | column to change
```

Example:

```text
fan_repair_rate | Failure Mode (ID) | 5002001 | Repair Rate
radiator_t2f | Index | 1 | T2F
```

When triggered, the component updates the mapped cells and pulses its `Trigger` output. Connect that output to Run MATLAB's `Trigger`. The CSV is modified in place; back it up before use.

### Run MATLAB

Script: `grasshopper_blocks/run_matlab_component.py`

| Input | Access | Type | Purpose |
|---|---|---|---|
| `Repo` | Item | str | Project folder |
| `RunScript` | Item | str | Full path to `run_matlab.py` |
| `MatlabFile` | Item | str | MATLAB `.m` file to execute |
| `MATLABRoot` | Item | str | MATLAB installation folder returned by `matlabroot` |
| `PythonExe` | Item | str | Optional Python executable; empty uses `python` |
| `Trigger` | Item | bool | Trigger from Transfer Variables MATLAB or Transfer Variables CSV |

Outputs: `Ready` (bool), `Status` (str).

On a rising edge of `Trigger`, the component configures `run_matlab.py` using `MatlabFile` and `MATLABRoot`, then launches it. The MATLAB installation path is an input; it does not need to be edited in the Python file. `Ready` becomes true when MATLAB completes successfully.

The launcher runs headlessly by default. Your MATLAB script is responsible for saving any simulation outputs you need.

## 4. Wiring

**Single MATLAB run**

```text
Button
  ↓
Transfer Variables MATLAB (TriggerIn)
  ↓ Trigger
Run MATLAB (Trigger)
```

**Single run with CSV update**

```text
Button
  ↓
Transfer Variables MATLAB (TriggerIn)
  ↓ Trigger
Transfer Variables CSV (TriggerIn)
  ↓ Trigger
Run MATLAB (Trigger)
```

**Multi-run**

```text
Multi-run (Trigger)
  ↓
Transfer Variables MATLAB (TriggerIn)
  ↓ Trigger
[Transfer Variables CSV (TriggerIn), if required]
  ↓ Trigger
Run MATLAB (Trigger)
```

Connect the same baseline `Names` and `Values` to Multi-run and Transfer Variables MATLAB. If using CSV, also connect them to Transfer Variables CSV.

## 5. Error handling and troubleshooting

- **Missing module:** Check that `Repo` points to the folder containing the project `.py` files and restart Rhino after replacing files.
- **Names and values do not match:** Use List access for `Names`, Tree access with no type hint for `Values`, and provide one value branch per name.
- **MATLAB executable not found:** Check that `MATLABRoot` is the folder returned by MATLAB's `matlabroot`, not the `bin` folder.
- **MATLAB script not found:** Check the `MatlabFile` path and ensure the file exists.
- **RunScript not found:** Connect the full path to the project's `run_matlab.py`.
- **Transfer fails while MATLAB is running:** Wait for MATLAB to finish before updating the same `.m` file.
- **CSV mapping fails:** Check the four fields in each mapping line and verify that the identifier and target column exist.
- **Multi-run stops:** Read the Status output. Invalid iteration inputs, transfer failures and MATLAB errors stop the batch.

Always back up the `.m` and CSV files before the first run. Transfers overwrite values/cells in those files.

## 6. Notifications

Notifications are optional. Use `00_Enable_Notifications.bat` to install/check the notification hook and open settings. Use `Launch_Notifications.bat` to reopen settings later. Notification preferences are stored in the user's `HabSim` settings folder.
