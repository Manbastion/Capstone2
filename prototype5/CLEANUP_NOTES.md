# Prototype 4 cleanup notes

This cleanup is intentionally conservative: live function names, function parameters,
Grasshopper input/output names, and the current GUI/transfer/MATLAB/history workflow
have been kept unchanged.

## Changes made

- Removed Python cache folders and runtime/generated output files from the project copy.
- Removed `find_py.py`, a one-line development helper that is not referenced by Prototype 4.
- Added `.gitignore` so runtime outputs do not keep reappearing in Git.
- Kept the current MATLAB runner files (`run_matlab.py`,
  `run_matlab_import_python_v2.py`, `gh_matlab_run.py`) because Block 3 currently relies on
  that workflow.
- Kept the compatibility MATLAB helpers in `gh_bridge.py`; removing them could break code
  outside the three documented Grasshopper blocks.
- Cleaned the History revert implementation:
  - normal transfers no longer publish a fake revert event;
  - the revert event is published only after a real History revert;
  - removed an unused `after` dictionary in `revert_transfer()`;
  - retained the existing `RevertedValues` Grasshopper output behavior.

## Important generated files

These are created again automatically when needed and are now ignored by Git:

- `history.json`
- `revert_output.json`
- `gui_running.flag`
- `matlab_run_done.txt`
- `vars.mat` / `vars.txt`
- `matlab_output_variables.*`

## Current live flow

1. `grasshopper_blocks/block1_gui_config.py` -> opens the configuration GUI and exposes
   `Config`, `Status`, `RevertedValues`.
2. `grasshopper_blocks/block2_transfer_variables.py` -> calls `gh_bridge.transfer()`.
3. `grasshopper_blocks/block3_run_matlab.py` -> uses `gh_matlab_run.py` to run
   `run_matlab.py` asynchronously.
4. `history.py` -> records transfers, exports history values, restores MATLAB/destination
   values, and publishes real reverted source values to Grasshopper.
