"""Backend functions for the Grasshopper–HabSim variable bridge.

This module contains file-reading and variable-transfer logic only.
It does not create any GUI windows.

Current prototype supports simple scalar numeric assignments such as:
    variable_a = 10
    repair_rate = -0.25
    scale = 1.2e-3
"""

import re


NUMERIC_VALUE_PATTERN = re.compile(
    r"^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$"
)

ASSIGNMENT_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?P<before_eq>\s*=\s*)"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?P<semicolon>\s*;?)"
    r"(?P<comment>\s*(?:[%#].*)?)$"
)


def is_valid_variable_name(name):
    """Return True if name is a simple Python/MATLAB-style identifier."""
    return bool(re.fullmatch(r"[A-Za-z_]\w*", str(name).strip()))


def is_valid_numeric_value(value):
    """Return True if value is a scalar number supported by this prototype."""
    return bool(NUMERIC_VALUE_PATTERN.fullmatch(str(value).strip()))


def read_variables(file_path):
    """Read supported variable assignments from a file.

    Returns a dict in file order, for example:
        {
            "variable_a": "10.0",
            "variable_b": "2.5"
        }
    """
    variables = {}

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            match = ASSIGNMENT_PATTERN.match(line.rstrip("\r\n"))
            if match:
                variables[match.group("name")] = match.group("value")

    return variables


def _rewrite_values(file_path, replacements, strict=False):
    """Internal helper that replaces existing variable values.

    Parameters
    ----------
    replacements : dict
        {"variable_name": "new_value"}
    strict : bool
        If True, raise an error if any requested variable is missing.

    Returns
    -------
    dict
        {"updated": [...], "missing": [...]}
    """
    clean_replacements = {}

    for name, value in replacements.items():
        name = str(name).strip()
        value = str(value).strip()

        if not is_valid_variable_name(name):
            raise ValueError(f"Invalid variable name: {name!r}")

        if not is_valid_numeric_value(value):
            raise ValueError(f"Invalid numeric value for {name}: {value!r}")

        clean_replacements[name] = value

    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    updated = []
    found = set()
    new_lines = []

    for line in lines:
        if line.endswith("\r\n"):
            newline = "\r\n"
            text = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            text = line[:-1]
        else:
            newline = ""
            text = line

        match = ASSIGNMENT_PATTERN.match(text)

        if not match:
            new_lines.append(line)
            continue

        name = match.group("name")

        if name not in clean_replacements:
            new_lines.append(line)
            continue

        new_value = clean_replacements[name]

        replacement = (
            f'{match.group("indent")}'
            f'{name}'
            f'{match.group("before_eq")}'
            f'{new_value}'
            f'{match.group("semicolon")}'
            f'{match.group("comment")}'
        )

        new_lines.append(replacement + newline)
        found.add(name)
        updated.append(name)

    missing = sorted(set(clean_replacements) - found)

    if strict and missing:
        raise ValueError(
            "Could not find these variables in the file: "
            + ", ".join(missing)
        )

    with open(file_path, "w", encoding="utf-8", newline="") as file:
        file.writelines(new_lines)

    return {
        "updated": sorted(set(updated)),
        "missing": missing,
    }


def set_variable_values(file_path, values, strict=False):
    """Set values of existing variables in a file.

    This is used by the History feature when reverting old transfers.
    """
    return _rewrite_values(file_path, values, strict=strict)


def update_source_variables(file_path, changes):
    """Update variable names AND values directly in the source file.

    changes format:
        {
            "original_name": {
                "name": "new_name",
                "value": "new_value"
            }
        }

    This is used by config.py.
    """
    final_names = []

    for original_name, change in changes.items():
        original_name = str(original_name).strip()
        new_name = str(change["name"]).strip()
        new_value = str(change["value"]).strip()

        if not is_valid_variable_name(original_name):
            raise ValueError(f"Invalid original variable name: {original_name!r}")

        if not is_valid_variable_name(new_name):
            raise ValueError(f"Invalid new variable name: {new_name!r}")

        if not is_valid_numeric_value(new_value):
            raise ValueError(f"Invalid numeric value for {new_name}: {new_value!r}")

        final_names.append(new_name)

    if len(final_names) != len(set(final_names)):
        raise ValueError("Two variables cannot have the same final variable name.")

    with open(file_path, "r", encoding="utf-8") as file:
        source_lines = file.readlines()

    updated = []
    found = set()
    new_lines = []

    for line in source_lines:
        if line.endswith("\r\n"):
            newline = "\r\n"
            text = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            text = line[:-1]
        else:
            newline = ""
            text = line

        match = ASSIGNMENT_PATTERN.match(text)

        if not match:
            new_lines.append(line)
            continue

        original_name = match.group("name")

        if original_name not in changes:
            new_lines.append(line)
            continue

        new_name = str(changes[original_name]["name"]).strip()
        new_value = str(changes[original_name]["value"]).strip()

        replacement = (
            f'{match.group("indent")}'
            f'{new_name}'
            f'{match.group("before_eq")}'
            f'{new_value}'
            f'{match.group("semicolon")}'
            f'{match.group("comment")}'
        )

        new_lines.append(replacement + newline)
        found.add(original_name)
        updated.append(
            {
                "old_name": original_name,
                "new_name": new_name,
                "value": new_value,
            }
        )

    missing = sorted(set(changes) - found)

    if missing:
        raise ValueError(
            "Could not find these variables in the source file: "
            + ", ".join(missing)
        )

    with open(file_path, "w", encoding="utf-8", newline="") as file:
        file.writelines(new_lines)

    return {
        "updated": updated,
        "count": len(updated),
    }


def transfer_data(
    input_file,
    output_file,
    mode="everything",
    selected_variables=None,
    source_variables=None,
):
    """Transfer matching source values into the destination file.

    Returns a summary including a compact before/after change set.
    The GUI uses that change set to create a History record.
    """
    if source_variables is None:
        source_variables = read_variables(input_file)
    else:
        source_variables = dict(source_variables)

    if not source_variables:
        raise ValueError(
            "No supported variable assignments were found in the source data."
        )

    for name, value in source_variables.items():
        if not is_valid_variable_name(name):
            raise ValueError(f"Invalid variable name: {name!r}")

        if not is_valid_numeric_value(value):
            raise ValueError(f"Invalid numeric value for {name}: {value!r}")

    selected = set(selected_variables or [])

    if mode == "everything":
        variables_to_transfer = set(source_variables)
    elif mode == "include":
        variables_to_transfer = set(source_variables) & selected
    elif mode == "exclude":
        variables_to_transfer = set(source_variables) - selected
    else:
        raise ValueError(f"Unknown transfer mode: {mode}")

    with open(output_file, "r", encoding="utf-8") as file:
        output_lines = file.readlines()

    transferred = []
    destination_variables = set()
    changes = {}
    new_lines = []

    for line in output_lines:
        if line.endswith("\r\n"):
            newline = "\r\n"
            text = line[:-2]
        elif line.endswith("\n"):
            newline = "\n"
            text = line[:-1]
        else:
            newline = ""
            text = line

        match = ASSIGNMENT_PATTERN.match(text)

        if not match:
            new_lines.append(line)
            continue

        name = match.group("name")
        destination_variables.add(name)

        if name not in variables_to_transfer:
            new_lines.append(line)
            continue

        old_value = match.group("value")
        new_value = str(source_variables[name]).strip()

        replacement = (
            f'{match.group("indent")}'
            f'{name}'
            f'{match.group("before_eq")}'
            f'{new_value}'
            f'{match.group("semicolon")}'
            f'{match.group("comment")}'
        )

        new_lines.append(replacement + newline)
        transferred.append(name)

        # Store only real changes. This keeps history very small.
        if old_value != new_value:
            changes[name] = {
                "before": old_value,
                "after": new_value,
            }

    with open(output_file, "w", encoding="utf-8", newline="") as file:
        file.writelines(new_lines)

    missing_in_destination = sorted(
        variables_to_transfer - destination_variables
    )

    return {
        "source_count": len(source_variables),
        "requested_count": len(variables_to_transfer),
        "transferred": sorted(set(transferred)),
        "changes": changes,
        "missing_in_destination": missing_in_destination,
    }
