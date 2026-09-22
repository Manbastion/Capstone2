# Grasshopper–HabSim Variable Transfer Prototype

## Run

```bash
python main.py
```

No third-party Python packages are required.

## New fuzzy matching workflow

1. Choose a source file.
2. Choose a destination file.
3. The **Transfer Configuration** window opens.
4. The program suggests destination variables using fuzzy name similarity.
5. Review the suggested matches.
6. Tick/untick variables to choose what is transferred.
7. Use **Manual Linking** when names are different.
8. Save the configuration.
9. Press **Transfer** and confirm the final operation.
10. The transfer is recorded in History.

### Example

The test files contain:

```text
source:      battery
destination: battry
```

The fuzzy matcher should suggest:

```text
battery -> battry
```

The user must confirm the fuzzy mapping before it is saved.

## Fuzzy matching

The matcher uses Python's standard-library `difflib.SequenceMatcher`, combined with token similarity.

No external fuzzy-matching package is required.

Similarity bands:

- 90%+: Very high
- 80–89.9%: High
- 65–79.9%: Medium
- 50–64.9%: Low
- below 50%: Very low

The application never silently changes a variable name. Fuzzy matches are shown in the configuration window and require confirmation before being used.

## Important limitation

The current parser intentionally supports simple scalar numeric assignments:

```matlab
battery = 95;
```

It does not yet parse the full hierarchical MATLAB structures and `.mat` output schema of HabSim. That should be implemented as a separate structured HabSim adapter once the exact production I/O specification is finalised.

## History

History stores:

- source/destination files
- selected variables
- source → destination mappings
- before/after destination values
- transfer time
- whether a transfer was reverted

Reverting now changes the **destination only**, which is safer for a source/destination transfer workflow.
