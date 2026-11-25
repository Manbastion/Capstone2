import csv
import json
import os
import re

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"

ASSIGN = re.compile(
    rf"^(\s*)([A-Za-z_]\w*)(\s*=\s*)({NUM})(\s*;?)(\s*(?:[%#].*)?)$"
)

# Same 6-group layout as ASSIGN so the rebuild code can be shared for
# "name": value style JSON lines.
#   1: indent + opening quote      2: key name
#   3: closing quote + colon       4: number
#   5: optional trailing comma     6: trailing whitespace
ASSIGN_JSON = re.compile(
    rf'^(\s*")([A-Za-z_]\w*)("\s*:\s*)({NUM})(\s*,?)(\s*)$'
)


def valid_name(value):
    return bool(re.fullmatch(r"[A-Za-z_]\w*", str(value).strip()))


def valid_value(value):
    return bool(re.fullmatch(NUM, str(value).strip()))


is_valid_variable_name = valid_name
is_valid_numeric_value = valid_value


def is_json_file(path):
    return os.path.splitext(str(path))[1].lower() == ".json"


def is_csv_file(path):
    return os.path.splitext(str(path))[1].lower() == ".csv"


def _pattern(path):
    """Line regex for non-CSV formats (CSV is handled separately, row-based)."""
    return ASSIGN_JSON if is_json_file(path) else ASSIGN


def _check_json_output(path, lines):
    """Refuse to write a .json file that would no longer parse."""
    if not is_json_file(path):
        return
    try:
        json.loads("".join(lines))
    except json.JSONDecodeError as error:
        raise ValueError(f"Edit would produce invalid JSON: {error}") from error


def _split(line):
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


# ---------------- CSV helpers ----------------
# A CSV "variable" is any row shaped like: name,value[,...extra columns].
# Extra columns are preserved untouched. A header row (e.g. "name,value")
# is skipped automatically because its value cell isn't numeric.

def _read_variables_csv(path):
    variables = {}
    with open(path, encoding="utf-8", newline="") as file:
        for row in csv.reader(file):
            if len(row) < 2:
                continue
            name, value = row[0].strip(), row[1].strip()
            if valid_name(name) and valid_value(value):
                variables[name] = value
    return variables


def _write_changes_csv(path, changes, strict):
    with open(path, encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))

    found = set()
    output_rows = []

    for row in rows:
        if len(row) < 2:
            output_rows.append(row)
            continue

        name, value = row[0].strip(), row[1].strip()
        if not (valid_name(name) and valid_value(value) and name in changes):
            output_rows.append(row)
            continue

        new, new_value = changes[name]
        new_row = list(row)
        new_row[0] = new
        new_row[1] = new_value
        output_rows.append(new_row)
        found.add(name)

    missing = sorted(set(changes) - found)
    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    with open(path, "w", encoding="utf-8", newline="") as file:
        csv.writer(file).writerows(output_rows)

    return {"updated": sorted(found), "missing": missing}


def _transfer_write_csv(output_file, mapping, reverse, source, apply):
    with open(output_file, encoding="utf-8", newline="") as file:
        rows = list(csv.reader(file))

    found = set()
    transferred = []
    changes = {}
    output_rows = []

    for row in rows:
        if len(row) < 2:
            output_rows.append(row)
            continue

        destination_name = row[0].strip()
        old_value = row[1].strip()

        if not (valid_name(destination_name) and valid_value(old_value)):
            output_rows.append(row)
            continue

        found.add(destination_name)
        source_name = reverse.get(destination_name)

        if source_name is None:
            output_rows.append(row)
            continue

        new_value = source[source_name]
        new_row = list(row)
        new_row[1] = new_value
        output_rows.append(new_row)

        transferred.append({"source": source_name, "destination": destination_name})

        if old_value != new_value:
            changes[destination_name] = {
                "before": old_value,
                "after": new_value,
                "source": source_name,
            }

    missing = sorted(
        destination_name
        for source_name, destination_name in mapping.items()
        if destination_name not in found
    )

    if apply:
        with open(output_file, "w", encoding="utf-8", newline="") as file:
            csv.writer(file).writerows(output_rows)

    return transferred, changes, missing


def read_variables(path):
    """Read simple scalar numeric assignments from .py/.m/.txt, .json or .csv files."""
    if is_csv_file(path):
        return _read_variables_csv(path)

    variables = {}
    pattern = _pattern(path)
    with open(path, encoding="utf-8") as file:
        for line in file:
            text = _split(line)[0]
            match = pattern.match(text)
            if match:
                variables[match.group(2)] = match.group(4)
    return variables


def _check(name, value):
    if not valid_name(name):
        raise ValueError(f"Invalid variable name: {name!r}")
    if not valid_value(value):
        raise ValueError(
            f"Invalid numeric value for {name}: {value!r}"
        )


def _write_changes(path, changes, strict=True):
    for old, (new, value) in changes.items():
        _check(old, value)
        if not valid_name(new):
            raise ValueError(f"Invalid variable name: {new!r}")

    if is_csv_file(path):
        return _write_changes_csv(path, changes, strict)

    with open(path, encoding="utf-8") as file:
        lines = file.readlines()

    pattern = _pattern(path)
    found = set()
    output = []

    for line in lines:
        text, newline = _split(line)
        match = pattern.match(text)

        if not match or match.group(2) not in changes:
            output.append(line)
            continue

        old = match.group(2)
        new, value = changes[old]
        output.append(
            f"{match.group(1)}{new}{match.group(3)}{value}"
            f"{match.group(5)}{match.group(6)}{newline}"
        )
        found.add(old)

    missing = sorted(set(changes) - found)

    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    _check_json_output(path, output)

    with open(path, "w", encoding="utf-8", newline="") as file:
        file.writelines(output)

    return {"updated": sorted(found), "missing": missing}


def set_variable_values(path, values, strict=False):
    return _write_changes(
        path,
        {key: (key, str(value).strip()) for key, value in values.items()},
        strict,
    )


def update_source_variables(path, changes):
    final_names = [str(value["name"]).strip() for value in changes.values()]

    if len(final_names) != len(set(final_names)):
        raise ValueError("Variable names must be unique.")

    data = {
        str(old).strip(): (
            str(value["name"]).strip(),
            str(value["value"]).strip(),
        )
        for old, value in changes.items()
    }

    result = _write_changes(path, data, True)
    return {"updated": result["updated"], "count": len(result["updated"])}


# ---------------- transfer ----------------

def transfer_data(
    input_file,
    output_file,
    mode="everything",
    selected_variables=None,
    source_variables=None,
    mappings=None,
    apply=True,
):
    """
    Transfer source values into destination variables.

    mappings is a dict:
        {source_name: destination_name}

    If mappings is omitted, same-name variables are used.

    input_file / output_file may be .py/.m/.txt, .json or .csv, in any
    combination.
    """
    source = dict(source_variables or read_variables(input_file))

    if not source:
        raise ValueError("No supported variables found in source file.")

    for name, value in source.items():
        _check(name, value)

    selected = set(selected_variables or [])

    if mode == "everything":
        wanted = set(source)
    elif mode == "include":
        wanted = set(source) & selected
    elif mode == "exclude":
        wanted = set(source) - selected
    else:
        raise ValueError(f"Unknown transfer mode: {mode}")

    destination_variables = read_variables(output_file)
    mapping = dict(mappings or {})

    # Default exact-name mapping when the user has not supplied one.
    for source_name in wanted:
        if source_name not in mapping and source_name in destination_variables:
            mapping[source_name] = source_name

    # Only transfer variables that were actually requested.
    mapping = {
        source_name: destination_name
        for source_name, destination_name in mapping.items()
        if source_name in wanted
    }

    reverse = {}
    for source_name, destination_name in mapping.items():
        if source_name not in source:
            raise ValueError(f"Source variable does not exist: {source_name!r}")
        if destination_name not in destination_variables:
            continue
        if destination_name in reverse:
            raise ValueError(
                f"Multiple source variables are linked to destination "
                f"{destination_name!r}."
            )
        reverse[destination_name] = source_name

    if is_csv_file(output_file):
        transferred, changes, missing = _transfer_write_csv(
            output_file, mapping, reverse, source, apply
        )
        return {
            "transferred": transferred,
            "changes": changes,
            "missing_in_destination": missing,
            "mappings": mapping,
        }

    with open(output_file, encoding="utf-8") as file:
        lines = file.readlines()

    pattern = _pattern(output_file)
    found = set()
    transferred = []
    changes = {}
    output = []

    for line in lines:
        text, newline = _split(line)
        match = pattern.match(text)

        if not match:
            output.append(line)
            continue

        destination_name = match.group(2)
        found.add(destination_name)

        source_name = reverse.get(destination_name)

        if source_name is None:
            output.append(line)
            continue

        new_value = source[source_name]
        old_value = match.group(4)

        output.append(
            f"{match.group(1)}{destination_name}{match.group(3)}"
            f"{new_value}{match.group(5)}{match.group(6)}{newline}"
        )

        transferred.append(
            {
                "source": source_name,
                "destination": destination_name,
            }
        )

        if old_value != new_value:
            changes[destination_name] = {
                "before": old_value,
                "after": new_value,
                "source": source_name,
            }

    missing = sorted(
        destination_name
        for source_name, destination_name in mapping.items()
        if destination_name not in found
    )

    if apply:
        _check_json_output(output_file, output)
        with open(output_file, "w", encoding="utf-8", newline="") as file:
            file.writelines(output)

    return {
        "transferred": transferred,
        "changes": changes,
        "missing_in_destination": missing,
        "mappings": mapping,
    }