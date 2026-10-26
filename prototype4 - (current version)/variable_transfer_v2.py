import csv
import json
import os
import re

from Capstone2.prototype4.matlab_literals import (
    NAME, NUM, normalize, parse as parse_literal, restyle, scan_statements,
)

# ---------------------------------------------------------------------------
# .py / .m / .txt files are read with matlab_literals (scalars, strings, true/
# false, NaN/Inf, vectors/matrices/cell arrays of ANY length, also over several
# lines). .json and .csv files keep the original numeric-only line patterns.
# ---------------------------------------------------------------------------
_SEP = r"(?:\s*[,;:]\s*|\s+)"
_VEC = rf"\[\s*(?:{NUM}(?:{_SEP}{NUM})*)?\s*[,;]?\s*\](?:'|\.')?"
_NUMERIC_VALUE = rf"(?:{NUM}|{_VEC})"

# 6-group layout, used for '"name": value,' lines in .json files
#   1: indent + opening quote      2: key name
#   3: closing quote + colon       4: number
#   5: optional trailing comma     6: trailing whitespace
ASSIGN_JSON = re.compile(
    rf'^(\s*")({NAME})("\s*:\s*)({_NUMERIC_VALUE})(\s*,?)(\s*)$'
)


def valid_name(value):
    return bool(re.fullmatch(NAME, str(value).strip()))


def valid_value(value):
    """True for any plain MATLAB literal: 5, 'text', [1 2 3], {'a','b'}, true ..."""
    return parse_literal(str(value)) is not None


def _numeric_only(value):
    return bool(re.fullmatch(_NUMERIC_VALUE, str(value).strip()))


def normalise_value(value):
    """A value as clean one-line text, e.g. ' 5 ' -> '5', '[1\n 2]' -> '[1 2]'.

    Kept because value_files.py (History export) imports it.
    """
    return normalize(str(value))


is_valid_variable_name = valid_name
is_valid_numeric_value = valid_value


def is_json_file(path):
    return os.path.splitext(str(path))[1].lower() == ".json"


def is_csv_file(path):
    return os.path.splitext(str(path))[1].lower() == ".csv"


def _is_text_file(path):
    """.m / .py / .txt (anything that is not .json or .csv)."""
    return not (is_json_file(path) or is_csv_file(path))


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
            if valid_name(name) and _numeric_only(value):
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
        if not (valid_name(name) and _numeric_only(value) and name in changes):
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

        if not (valid_name(destination_name) and _numeric_only(old_value)):
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


def _read_lines(path):
    with open(path, encoding="utf-8", newline="") as file:
        return file.read().splitlines(keepends=True)


def read_variables(path):
    """Read 'name = value' assignments from .py/.m/.txt, .json or .csv files.

    Values are returned as text on one line, e.g. '5', "'hello'", '[1 2 3]',
    '[1 2;3 4]', '{'a','b'}'. Calculations (v = v0 + a*t) are not variables.
    """
    if is_csv_file(path):
        return _read_variables_csv(path)

    variables = {}
    if is_json_file(path):
        with open(path, encoding="utf-8") as file:
            for line in file:
                match = ASSIGN_JSON.match(_split(line)[0])
                if match:
                    variables[match.group(2)] = match.group(4)
        return variables

    for statement in scan_statements(_read_lines(path)):
        variables[statement.name] = statement.text
    return variables


def _check(name, value, path=None):
    if not valid_name(name):
        raise ValueError(f"Invalid variable name: {name!r}")
    if not valid_value(value):
        raise ValueError(
            f"Invalid value for {name}: {value!r} (use a number, 'text', "
            f"[1 2 3], [1 2;3 4], {{'a','b'}}, true/false, NaN or Inf)"
        )
    if path is not None and not _is_text_file(path) and not _numeric_only(value):
        raise ValueError(
            f"{name} = {value} can't be written into {os.path.basename(str(path))}: "
            f"only plain numbers and numeric vectors fit in .json/.csv files."
        )


def _rebuild(lines, replacements):
    """Copy lines, swapping each {first_line: (last_line, new_text)} span."""
    output = []
    index = 0
    while index < len(lines):
        if index in replacements:
            last, text = replacements[index]
            output.append(text)
            index = last + 1
        else:
            output.append(lines[index])
            index += 1
    return output


def _write_file(path, lines):
    with open(path, "w", encoding="utf-8", newline="") as file:
        file.writelines(lines)


def _write_changes(path, changes, strict=True):
    for old, (new, value) in changes.items():
        _check(old, value, path)
        if not valid_name(new):
            raise ValueError(f"Invalid variable name: {new!r}")

    if is_csv_file(path):
        return _write_changes_csv(path, changes, strict)

    if _is_text_file(path):
        lines = _read_lines(path)
        replacements = {}
        found = set()
        for statement in scan_statements(lines):
            if statement.name not in changes:
                continue
            new, value = changes[statement.name]
            replacements[statement.start] = (
                statement.end,
                f"{statement.indent}{new}{statement.op}{value}"
                f"{statement.tail}{statement.newline}",
            )
            found.add(statement.name)
        output = _rebuild(lines, replacements)
    else:                                              # .json
        with open(path, encoding="utf-8", newline="") as file:
            lines = file.read().splitlines(keepends=True)
        found = set()
        output = []
        for line in lines:
            text, newline = _split(line)
            match = ASSIGN_JSON.match(text)

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
    _write_file(path, output)

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

def _destination_for(source_name, destination_variables, lowered):
    """Same name if it exists, else the one destination that differs only by case."""
    if source_name in destination_variables:
        return source_name
    matches = lowered.get(source_name.lower(), [])
    return matches[0] if len(matches) == 1 else None


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

    If mappings is omitted, same-name variables are used (a name that differs
    only in upper/lower case is matched too, when that is unambiguous; the
    value is always written under the destination's own spelling).

    A value replaces the old one in the destination's own style: a destination
    written [1, 2, 3] receives [4, 5, 6] (not [4 5 6]) and 'a' / "a" quotes are kept.
    Array values of any length are written on one line.

    input_file / output_file may be .py/.m/.txt, .json or .csv, in any
    combination. (.json and .csv destinations take plain numbers/vectors only.)
    """
    source = dict(source_variables or read_variables(input_file))

    if not source:
        raise ValueError("No supported variables found in source file.")

    for name, value in source.items():
        _check(name, value, output_file)

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

    lowered = {}
    for destination_name in destination_variables:
        lowered.setdefault(destination_name.lower(), []).append(destination_name)

    # Default mapping when the user has not supplied one.
    for source_name in sorted(wanted):
        if source_name not in mapping:
            found_name = _destination_for(source_name, destination_variables, lowered)
            if found_name:
                mapping[source_name] = found_name

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

    found = set()
    transferred = []
    changes = {}

    if _is_text_file(output_file):
        lines = _read_lines(output_file)
        replacements = {}

        for statement in scan_statements(lines):
            destination_name = statement.name
            found.add(destination_name)
            source_name = reverse.get(destination_name)

            if source_name is None:
                continue

            old_value = statement.text
            new_value = restyle(source[source_name], old_value)

            transferred.append(
                {"source": source_name, "destination": destination_name}
            )

            if old_value == new_value:
                continue                      # leave the line exactly as it is

            replacements[statement.start] = (
                statement.end,
                f"{statement.indent}{destination_name}{statement.op}"
                f"{new_value}{statement.tail}{statement.newline}",
            )
            changes[destination_name] = {
                "before": old_value,
                "after": new_value,
                "source": source_name,
            }

        output = _rebuild(lines, replacements)

    else:                                      # .json
        with open(output_file, encoding="utf-8", newline="") as file:
            lines = file.read().splitlines(keepends=True)

        output = []

        for line in lines:
            text, newline = _split(line)
            match = ASSIGN_JSON.match(text)

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
        _write_file(output_file, output)

    return {
        "transferred": transferred,
        "changes": changes,
        "missing_in_destination": missing,
        "mappings": mapping,
    }