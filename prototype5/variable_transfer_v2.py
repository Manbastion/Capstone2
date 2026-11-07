import codecs
import csv
import io
import json
import os
import re

from matlab_literals import (
    NAME, NUM, normalize, parse as parse_literal, quote, restyle, scan_statements,
    token_kind, unquote,
)

# ---------------------------------------------------------------------------
# .py / .m / .txt files are read with matlab_literals (scalars, strings, true/
# false, NaN/Inf, vectors/matrices/cell arrays of ANY length, also over several
# lines). .json files keep the original numeric-only line patterns. .csv files
# have their own reader/writer (see "CSV helpers" below): values are handled
# internally as the same literal text as everywhere else ( 5  'text'  [1 2 3] ),
# and only converted to plain cell text when they are written into the file.
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


def valid_expression(value):
    """True for a non-empty single MATLAB/Python assignment expression.

    Expressions are allowed only in text-based source/destination files. They are
    deliberately not treated as literals, and JSON/CSV remain literal-only.

    The scanner has already separated comments and the terminating semicolon, so
    this rejects line breaks and empty values but otherwise preserves MATLAB
    formulas such as ``25 + Variable_b`` or ``zeros(3)``.
    """
    text = str(value).strip()
    return bool(text) and "\n" not in text and "\r" not in text


def valid_assignment_value(value, path=None):
    """Can ``value`` be used on the right-hand side for this file type?"""
    if valid_value(value):
        return True
    return bool(path is not None and _is_text_file(path) and valid_expression(value))


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
# A CSV file has a HEADER ROW and can be laid out in one of two ways (found
# automatically, see _csv_layout):
#
#   "rows"     one variable per row:      name,value[,extra columns]
#                                         v0,12
#                                         a,2
#   "columns"  names in the header row,   IL,impactStart,coordinates
#              values in the row below:   2,438,[0.54 -0.54]
#
# Values are read as the same literal text the rest of the program uses
# (5, 'text', true, [1 2 3]) and written back as plain cell text (5, text, true,
# [1 2 3]). Every other cell, extra column and line is left exactly as it was.
# The file's encoding (UTF-8, UTF-8 with BOM, or Windows-1252), line endings and
# a missing final newline are kept too.

# First-cell header words that say "this file lists one variable per row".
_NAME_HEADERS = {
    "name", "names", "variable", "variables", "var", "vars", "parameter",
    "parameters", "param", "params", "key", "keys", "setting", "settings",
    "field", "property", "item", "label", "id",
}


def _load_csv(path):
    """Read a .csv file -> (rows, meta). meta remembers how to write it back."""
    with open(path, "rb") as file:
        raw = file.read()
    bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text, encoding = raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        try:
            text, encoding = raw.decode("cp1252"), "cp1252"
        except UnicodeDecodeError:
            text, encoding = raw.decode("latin-1"), "latin-1"
    meta = {
        "encoding": encoding,
        "bom": bom,
        "eol": "\r\n" if "\r\n" in text else "\n",
        "trailing": text.endswith(("\n", "\r")) or not text,
    }
    return list(csv.reader(io.StringIO(text, newline=""))), meta


def _save_csv(path, rows, meta):
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator=meta["eol"]).writerows(rows)
    text = buffer.getvalue()
    if not meta["trailing"] and text.endswith(meta["eol"]):
        text = text[:-len(meta["eol"])]
    try:
        data = text.encode(meta["encoding"])
    except UnicodeEncodeError as error:
        raise ValueError(
            f"{os.path.basename(path)} is saved as {meta['encoding']} and can't hold "
            f"the character {error.object[error.start]!r}. Re-save the file as "
            f"UTF-8 (Excel: Save As > CSV UTF-8) and try again."
        )
    if meta["bom"]:
        data = codecs.BOM_UTF8 + data
    temp = path + ".tmp"
    with open(temp, "wb") as file:
        file.write(data)
    try:
        os.replace(temp, path)
    except PermissionError:
        os.remove(temp)
        raise PermissionError(
            f"Can't write {os.path.basename(path)}: it is open in another program "
            f"(Excel?). Close it and try again."
        )


def _csv_ok(value):
    """True if this literal fits in one CSV cell: a single value or a numeric vector."""
    lit = parse_literal(str(value))
    if lit is None:
        return False
    if not lit.bracket:
        return True
    return lit.bracket == "[" and all(
        token_kind(token) != "string" for row in lit.rows for token in row
    )


def _csv_to_literal(text):
    """Cell text -> literal text: 12 -> 12, [1 2 3] -> [1 2 3], m/s -> 'm/s', empty -> ''."""
    cell = str(text).strip()
    if not cell:
        return "''"
    lit = parse_literal(cell)
    if lit is not None and _csv_ok(cell) and not (not lit.bracket and lit.kind == "string"):
        return cell
    return quote(cell)


def _literal_to_csv(value):
    """Literal text -> cell text: 'm/s' -> m/s, everything else as it is."""
    lit = parse_literal(str(value))
    if lit is not None and not lit.bracket and lit.kind == "string":
        return unquote(lit.rows[0][0])
    return str(value).strip()


def _csv_layout(rows):
    """'rows' (name,value per row) or 'columns' (names in the header row)."""
    if len(rows) < 2 or not rows[0]:
        return "rows"
    header = [cell.strip() for cell in rows[0]]
    if header[0].lower() in _NAME_HEADERS:
        return "rows"
    names = [cell for cell in header if cell]
    if not names or not all(valid_name(cell) for cell in names):
        return "rows"
    # Names across the top. If the first cells of the data rows are names too,
    # it is a list of variables with an unusual header; otherwise (numbers,
    # blanks) it is a header row with values underneath.
    first_cells = [row[0].strip() for row in rows[1:] if row]
    if first_cells and all(valid_name(cell) for cell in first_cells):
        return "rows"
    return "columns"


def _csv_cells(rows):
    """Every variable in the file: [{'name', 'name_pos', 'value_pos'}] (row, column)."""
    cells, seen = [], set()
    if _csv_layout(rows) == "columns":
        for column, cell in enumerate(rows[0]):
            name = cell.strip()
            if valid_name(name) and name not in seen:
                seen.add(name)
                cells.append({"name": name, "name_pos": (0, column),
                              "value_pos": (1, column)})
        return cells

    for index, row in enumerate(rows):
        if len(row) < 2:
            continue
        name, value = row[0].strip(), row[1].strip()
        if not valid_name(name) or not value or name in seen:
            continue
        if index == 0 and not _numeric_only(value):
            continue                     # the header row, e.g.  name,value
        seen.add(name)
        cells.append({"name": name, "name_pos": (index, 0), "value_pos": (index, 1)})
    return cells


def _csv_value(rows, position):
    row, column = position
    text = rows[row][column] if row < len(rows) and column < len(rows[row]) else ""
    return _csv_to_literal(text)


def _csv_set(rows, position, text):
    row, column = position
    rows[row] = list(rows[row]) + [""] * (column + 1 - len(rows[row]))
    rows[row][column] = text


def _read_variables_csv(path):
    rows, _ = _load_csv(path)
    return {cell["name"]: _csv_value(rows, cell["value_pos"]) for cell in _csv_cells(rows)}


def _write_changes_csv(path, changes, strict):
    rows, meta = _load_csv(path)
    cells = {cell["name"]: cell for cell in _csv_cells(rows)}

    found = set()
    for old, (new, value) in changes.items():
        cell = cells.get(old)
        if cell is None:
            continue
        _csv_set(rows, cell["value_pos"], _literal_to_csv(value))
        _csv_set(rows, cell["name_pos"], new)
        found.add(old)

    missing = sorted(set(changes) - found)
    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    _save_csv(path, rows, meta)
    return {"updated": sorted(found), "missing": missing}


def _transfer_write_csv(output_file, mapping, reverse, source, apply):
    rows, meta = _load_csv(output_file)
    cells = _csv_cells(rows)
    found = {cell["name"] for cell in cells}

    transferred = []
    changes = {}
    dirty = False

    for cell in cells:
        destination_name = cell["name"]
        source_name = reverse.get(destination_name)
        if source_name is None:
            continue

        old_value = _csv_value(rows, cell["value_pos"])
        new_value = restyle(source[source_name], old_value)
        transferred.append({"source": source_name, "destination": destination_name})

        if old_value != new_value:
            _csv_set(rows, cell["value_pos"], _literal_to_csv(new_value))
            dirty = True
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

    if apply and dirty:
        _save_csv(output_file, rows, meta)

    return transferred, changes, missing


def _read_lines(path):
    with open(path, encoding="utf-8", newline="") as file:
        return file.read().splitlines(keepends=True)


def read_variables(path):
    """Read ``name = value`` assignments from .py/.m/.txt, .json or .csv files.

    Text-based files include both plain values and formulas. For example,
    ``Variable_a = 25 + Variable_b`` is returned as
    ``{"Variable_a": "25 + Variable_b"}`` so it appears in Config and can be
    replaced by a transferred value.

    JSON and CSV retain their existing literal-only behaviour.
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


def _check(name, value, path=None, allow_expression=False):
    if not valid_name(name):
        raise ValueError(f"Invalid variable name: {name!r}")

    accepted = (
        valid_assignment_value(value, path)
        if allow_expression
        else valid_value(value)
    )

    if not accepted:
        extra = " or a MATLAB expression" if allow_expression and path and _is_text_file(path) else ""
        raise ValueError(
            f"Invalid value for {name}: {value!r} (use a number, 'text', "
            f"[1 2 3], [1 2;3 4], {{'a','b'}}, true/false, NaN or Inf{extra})"
        )

    if path is not None and valid_value(value):
        _check_fits(name, value, path)
    elif path is not None and not _is_text_file(path):
        _check_fits(name, value, path)


def _check_fits(name, value, path):
    """Can this value be written into this kind of file?"""
    where = os.path.basename(str(path))
    if is_csv_file(path):
        if not _csv_ok(value):
            raise ValueError(
                f"{name} = {value} can't be written into {where}: a CSV cell holds "
                f"one number, true/false, plain text or a numeric vector like [1 2 3]."
            )
    elif is_json_file(path) and not _numeric_only(value):
        raise ValueError(
            f"{name} = {value} can't be written into {where}: "
            f"only plain numbers and numeric vectors fit in .json files."
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


def _write_changes(path, changes, strict=True, allow_expressions=False):
    for old, (new, value) in changes.items():
        _check(old, value, path, allow_expression=allow_expressions)
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


def set_variable_values(path, values, strict=False, allow_expressions=False):
    return _write_changes(
        path,
        {key: (key, str(value).strip()) for key, value in values.items()},
        strict,
        allow_expressions=allow_expressions,
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
    combination. A .json destination takes plain numbers/vectors only; a .csv
    destination takes numbers, true/false, plain text and numeric vectors (see
    "CSV helpers" for the two supported layouts).
    """
    source = dict(source_variables or read_variables(input_file))

    if not source:
        raise ValueError("No supported variables found in source file.")

    for name, value in source.items():
        _check(
            name,
            value,
            input_file,
            allow_expression=_is_text_file(input_file),
        )

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

    # Only the values that will really be written have to fit the file type.
    for source_name in reverse.values():
        _check_fits(source_name, source[source_name], output_file)

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