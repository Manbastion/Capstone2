# Grasshopper–HabSim Variable Transfer Prototype

## Run

```bash
python main.py
```

The core transfer, GUI, history, fuzzy matching, JSON and TXT value files use the Python standard library.


```bash
```

## Transfer workflow

1. Choose a source file.
2. Choose a destination file.
3. The **Transfer Configuration** window opens.
4. The program suggests destination variables using fuzzy name similarity.
5. Review the suggested matches.
6. Tick/untick variables to choose what is transferred.
7. Double-click source names/values to edit them when required.
8. Save the configuration.
9. Press **Transfer** and confirm the final operation.
10. The transfer is recorded in History.

## Supported values

The text-file bridge supports scalar numbers, strings and one-dimensional/simple matrix arrays.

Examples:

```text
speed = 12.5
status = "ready"    # quoted strings are supported
state = ready       # plain Grasshopper text is quoted automatically
point = [1, 2]
labels = ["x", "y"]
```

A simple comma-separated Grasshopper value is automatically converted to MATLAB array notation:

```text
Grasshopper/source: point = 1, 2
MATLAB destination: point = [1, 2];
```

Existing MATLAB bracket expressions such as `[0:5:100]` are retained. Complex MATLAB expressions such as `v0 + a*t` are intentionally not treated as transferable input values.

## Saved values and History

Every new history record stores the source/destination names and the before/after value for every transferred variable, including values that did not change.

In **History**, select a transfer and choose **Export Values…**. The transfer can be saved as:

- JSON (`.json`)
- text (`.txt`)
- CSV (`.csv`)


History reverting still changes the recorded destination values back to their pre-transfer state.

## Fuzzy matching

The matcher uses Python's standard-library `difflib.SequenceMatcher`, combined with token similarity.

Similarity bands:

- 90%+: Very high
- 80–89.9%: High
- 65–79.9%: Medium
- 50–64.9%: Low
- below 50%: Very low

The application never silently changes a variable mapping. Fuzzy matches are shown in the configuration window and require confirmation before they are saved.

## Current scope limitation

The bridge supports simple assignment-style files. It does not yet parse the full hierarchical MATLAB structures and `.mat` schema used by production HabSim. That should remain a separate HabSim adapter once the final production I/O structure is confirmed.


## JSON source files

The normal **Source file** picker also accepts `.json` files.

Supported JSON source forms include a simple variable object:

```json
{
  "temperature": 295.15,
  "status": "ready",
  "point": [1, 2]
}
```

and JSON files exported from the Transfer History window. JSON strings and arrays are
normalised for transfer to MATLAB, so `"ready"` remains a string and `[1, 2]` is written
as a MATLAB array.

