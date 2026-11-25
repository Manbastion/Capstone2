# Grasshopper–MATLAB Integration

This folder contains the Grasshopper–MATLAB integration, including variable transfer, optional CSV updates, multi-run automation and completion notifications.

Read `SETUP_GUIDE.md` for installation, component setup, input/output names, wiring and troubleshooting.

## Main components

| Component script | Purpose |
|---|---|
| `grasshopper_blocks/multirun_controller.py` | Opens the multi-run editor and triggers each iteration |
| `grasshopper_blocks/gui_config.py` | Opens the variable-linking/configuration GUI |
| `grasshopper_blocks/transfer_variables_matlab.py` | Writes Grasshopper values into a MATLAB `.m` file |
| `grasshopper_blocks/transfer_variables_csv.py` | Updates mapped cells in a CSV file |
| `grasshopper_blocks/run_matlab_component.py` | Launches MATLAB and reports completion |

These scripts are pasted into Grasshopper Python 3 Script components. The filenames are descriptive; the scripts are not automatically loaded from the folder.

## Setup checklist

1. Use Rhino 8/Grasshopper, MATLAB R2021a or newer, and Python 3.10+ with `tkinter`.
2. Keep the project Python files together in one local folder.
3. In Grasshopper, connect that folder to each component's `Repo` input.
4. Set `MATLABRoot` on Run MATLAB to the folder returned by MATLAB's `matlabroot` command.
5. Back up the MATLAB `.m` and CSV files before transferring values. Transfers modify those files in place.
6. Set `Names` to List access and `Values` to Tree access with no type hint.
7. Restart Rhino after replacing project Python files.

## Typical wiring

- Single run: Button → Transfer Variables MATLAB `TriggerIn` → Run MATLAB `Trigger`.
- With CSV: Button → Transfer Variables MATLAB `TriggerIn` → Transfer Variables CSV `TriggerIn` → Run MATLAB `Trigger`.
- Multi-run: Multi-run `Trigger` → Transfer Variables MATLAB `TriggerIn`. Continue through the CSV component if used, then connect the final `Trigger` to Run MATLAB.

The MATLAB file path is supplied directly to the transfer component and Run MATLAB. The launcher script is configured automatically from the `RunScript`, `MatlabFile` and `MATLABRoot` inputs; no user-specific paths are stored in the launcher.

See `SETUP_GUIDE.md` for complete input/output definitions and multi-run configuration.
