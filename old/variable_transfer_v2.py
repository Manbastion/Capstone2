import ast
import json
import re

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
NAME = re.compile(r"[A-Za-z_]\w*")
ASSIGN_HEAD = re.compile(r"^(\s*)([A-Za-z_]\w*)(\s*=\s*)(.*)$")


def valid_name(value):
    return bool(NAME.fullmatch(str(value).strip()))


def _format_atom(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    raise ValueError(f"Unsupported array element: {value!r}")


def _format_sequence(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("Expected a list or tuple.")

    if value and all(isinstance(item, (list, tuple)) for item in value):
        widths = {len(item) for item in value}
        if len(widths) != 1:
            raise ValueError("Nested arrays must have equal row lengths.")
        rows = [", ".join(_format_atom(item) for item in row) for row in value]
        return "[" + "; ".join(rows) + "]"

    return "[" + ", ".join(_format_atom(item) for item in value) + "]"


def _balanced_brackets(value):
    pairs = {"]": "[", ")": "(", "}": "{"}
    stack = []
    quote = None
    escaped = False

    for char in value:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in "'\"":
            quote = char
        elif char in "[({":
            stack.append(char)
        elif char in "]) }".replace(" ", ""):
            if not stack or stack.pop() != pairs[char]:
                return False

    return not stack and quote is None


def _split_top_level_commas(value):
    parts = []
    start = 0
    depth = 0
    quote = None
    escaped = False

    for index, char in enumerate(value):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in "'\"":
            quote = char
        elif char in "[({":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(value[start:index].strip())
            start = index + 1

    if parts:
        parts.append(value[start:].strip())
    return parts


def _valid_array_item(value):
    value = value.strip()
    if not value:
        return False
    if re.fullmatch(NUM, value):
        return True
    if valid_name(value):
        return True
    if value[0:1] in ("'", '"') and value[-1:] == value[0:1]:
        try:
            return isinstance(ast.literal_eval(value), str)
        except (ValueError, SyntaxError):
            return False
    return False


def normalise_value(value):
    """
    Convert a supported value to text suitable for the bridge/MATLAB file.

    Supported values:
      - scalar numbers: 12, -3.5, 1e-4
      - quoted strings: "lunar base", 'ready'
      - arrays/lists: [1, 2], ["x", "y"]
      - simple comma-separated Grasshopper values: 1, 2 -> [1, 2]

    Existing MATLAB bracket expressions such as [0:5:100] are retained.
    """
    if isinstance(value, (list, tuple)):
        return _format_sequence(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)

    text = str(value).strip()
    if not text or "\n" in text or "\r" in text:
        raise ValueError(f"Unsupported value: {value!r}")

    if re.fullmatch(NUM, text):
        return text

    if text[0:1] in ("'", '"') and text[-1:] == text[0:1]:
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            # MATLAB strings may use quoting rules that Python cannot parse.
            if _balanced_brackets(text):
                return text
            raise ValueError(f"Invalid string value: {value!r}")
        if isinstance(parsed, str):
            return text

    if text.startswith(("[", "(")) and text.endswith(("]", ")")):
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple)):
                return _format_sequence(parsed)
        except (ValueError, SyntaxError):
            pass

        # Keep valid MATLAB array expressions such as [1 2] or [0:5:100].
        if text.startswith("[") and text.endswith("]") and _balanced_brackets(text):
            return text

    parts = _split_top_level_commas(text)
    if len(parts) >= 2 and all(_valid_array_item(part) for part in parts):
        # Grasshopper often exposes list-like data as "x, y". MATLAB expects
        # an array expression, so normalise it to "[x, y]".
        return "[" + ", ".join(parts) + "]"

    if text.lower() in {"true", "false"}:
        return text.lower()
    if text in {"NaN", "Inf", "-Inf"}:
        return text

    # Plain Grasshopper text such as ready or lunar base is treated as a
    # string and written with quotes so MATLAB receives a string literal.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_ .-]*", text):
        return json.dumps(text)

    raise ValueError(
        "Unsupported value. Use a number, quoted string, or array/list. "
        "Examples: 12.5, \"ready\", [1, 2], or 1, 2."
    )


def valid_value(value):
    try:
        normalise_value(value)
        return True
    except (TypeError, ValueError):
        return False


is_valid_variable_name = valid_name
is_valid_numeric_value = lambda value: bool(re.fullmatch(NUM, str(value).strip()))


def _split(line):
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _split_comment(text):
    quote = None
    escaped = False

    for index, char in enumerate(text):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in "'\"":
            quote = char
        elif char in "#%":
            return text[:index], text[index:]

    return text, ""


def _parse_assignment(text):
    match = ASSIGN_HEAD.match(text)
    if not match:
        return None

    code, comment = _split_comment(match.group(4))
    code_without_trailing = code.rstrip()
    trailing = code[len(code_without_trailing):]
    terminator = ""

    if code_without_trailing.endswith(";"):
        terminator = ";"
        code_without_trailing = code_without_trailing[:-1].rstrip()

    raw_value = code_without_trailing.strip()
    if not raw_value:
        return None

    try:
        value = normalise_value(raw_value)
    except ValueError:
        return None

    return {
        "indent": match.group(1),
        "name": match.group(2),
        "separator": match.group(3),
        "value": value,
        "terminator": terminator,
        "trailing": trailing,
        "comment": comment,
    }



def _json_native_value(value):
    """Convert bridge-normalised text back to a JSON-compatible Python value."""
    normalised = normalise_value(value)

    if normalised == "true":
        return True
    if normalised == "false":
        return False
    if normalised == "NaN":
        return "NaN"
    if normalised == "Inf":
        return "Inf"
    if normalised == "-Inf":
        return "-Inf"

    if re.fullmatch(NUM, normalised):
        try:
            return int(normalised)
        except ValueError:
            return float(normalised)

    if normalised.startswith('"') and normalised.endswith('"'):
        try:
            return json.loads(normalised)
        except json.JSONDecodeError:
            return normalised

    if normalised.startswith("[") and normalised.endswith("]"):
        try:
            parsed = ast.literal_eval(normalised)
            if isinstance(parsed, (list, tuple)):
                return list(parsed)
        except (ValueError, SyntaxError):
            # MATLAB-only array expressions are kept as text if they cannot
            # be represented directly in JSON.
            return normalised

    return normalised


def _read_json_variables(path):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    variables = {}

    # History-export JSON:
    # {"format": ..., "values": [{"source": "x", "value": 1}, ...]}
    if isinstance(data, dict) and isinstance(data.get("values"), list):
        for row in data["values"]:
            if not isinstance(row, dict):
                continue
            name = str(row.get("source") or row.get("destination") or "").strip()
            value = row.get("value", row.get("after"))
            if valid_name(name) and value is not None:
                variables[name] = normalise_value(value)
        return variables

    # Simple JSON source:
    # {"temperature": 295, "status": "ready", "point": [1, 2]}
    if isinstance(data, dict):
        for name, value in data.items():
            if name in {"format", "version", "transfer"}:
                continue
            if valid_name(name):
                variables[name] = normalise_value(value)
        return variables

    raise ValueError(
        "JSON source must be an object of variable/value pairs or a "
        "Grasshopper-HabSim exported history JSON file."
    )


def _update_json_variables(path, changes, strict=True):
    with open(path, encoding="utf-8") as file:
        data = json.load(file)

    cleaned = {}
    for old, (new, value) in changes.items():
        old = str(old).strip()
        new = str(new).strip()
        if not valid_name(old):
            raise ValueError(f"Invalid variable name: {old!r}")
        if not valid_name(new):
            raise ValueError(f"Invalid variable name: {new!r}")
        cleaned[old] = (new, _json_native_value(value))

    found = set()

    if isinstance(data, dict) and isinstance(data.get("values"), list):
        for row in data["values"]:
            if not isinstance(row, dict):
                continue
            old = str(row.get("source") or "").strip()
            if old not in cleaned:
                continue

            new, value = cleaned[old]
            row["source"] = new
            row["value"] = value
            row["after"] = value
            found.add(old)

    elif isinstance(data, dict):
        rebuilt = {}
        for key, value in data.items():
            if key in cleaned:
                new, new_value = cleaned[key]
                rebuilt[new] = new_value
                found.add(key)
            else:
                rebuilt[key] = value
        data = rebuilt

    else:
        raise ValueError(
            "JSON source must be an object of variable/value pairs or a "
            "Grasshopper-HabSim exported history JSON file."
        )

    missing = sorted(set(cleaned) - found)
    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")

    return {"updated": sorted(found), "missing": missing}

def read_variables(path):
    """Read supported variables from text-based files or JSON source files."""
    if str(path).lower().endswith(".json"):
        return _read_json_variables(path)

    variables = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            parsed = _parse_assignment(_split(line)[0])
            if parsed:
                variables[parsed["name"]] = parsed["value"]
    return variables


def _check(name, value):
    if not valid_name(name):
        raise ValueError(f"Invalid variable name: {name!r}")
    return normalise_value(value)


def _write_changes(path, changes, strict=True):
    if str(path).lower().endswith(".json"):
        return _update_json_variables(path, changes, strict)

    cleaned = {}
    for old, (new, value) in changes.items():
        value = _check(old, value)
        if not valid_name(new):
            raise ValueError(f"Invalid variable name: {new!r}")
        cleaned[old] = (new, value)

    with open(path, encoding="utf-8") as file:
        lines = file.readlines()

    found = set()
    output = []

    for line in lines:
        text, newline = _split(line)
        parsed = _parse_assignment(text)

        if not parsed or parsed["name"] not in cleaned:
            output.append(line)
            continue

        old = parsed["name"]
        new, value = cleaned[old]
        suffix = (
            parsed["terminator"]
            + parsed["trailing"]
            + parsed["comment"]
        )
        output.append(
            f"{parsed['indent']}{new}{parsed['separator']}{value}{suffix}{newline}"
        )
        found.add(old)

    missing = sorted(set(cleaned) - found)

    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    with open(path, "w", encoding="utf-8", newline="") as file:
        file.writelines(output)

    return {"updated": sorted(found), "missing": missing}


def set_variable_values(path, values, strict=False):
    return _write_changes(
        path,
        {key: (key, normalise_value(value)) for key, value in values.items()},
        strict,
    )


def update_source_variables(path, changes):
    final_names = [str(value["name"]).strip() for value in changes.values()]

    if len(final_names) != len(set(final_names)):
        raise ValueError("Variable names must be unique.")

    data = {
        str(old).strip(): (
            str(value["name"]).strip(),
            normalise_value(value["value"]),
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
    """
    source = dict(source_variables or read_variables(input_file))

    if not source:
        raise ValueError("No supported variables found in source file.")

    source = {
        name: _check(name, value)
        for name, value in source.items()
    }

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

    for source_name in wanted:
        if source_name not in mapping and source_name in destination_variables:
            mapping[source_name] = source_name

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

    with open(output_file, encoding="utf-8") as file:
        lines = file.readlines()

    found = set()
    transferred = []
    changes = {}
    output = []

    for line in lines:
        text, newline = _split(line)
        parsed = _parse_assignment(text)

        if not parsed:
            output.append(line)
            continue

        destination_name = parsed["name"]
        found.add(destination_name)
        source_name = reverse.get(destination_name)

        if source_name is None:
            output.append(line)
            continue

        new_value = source[source_name]
        old_value = parsed["value"]
        suffix = (
            parsed["terminator"]
            + parsed["trailing"]
            + parsed["comment"]
        )

        output.append(
            f"{parsed['indent']}{destination_name}{parsed['separator']}"
            f"{new_value}{suffix}{newline}"
        )

        transferred.append(
            {
                "source": source_name,
                "destination": destination_name,
                "before": old_value,
                "after": new_value,
                "value": new_value,
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
        with open(output_file, "w", encoding="utf-8", newline="") as file:
            file.writelines(output)

    return {
        "transferred": transferred,
        "changes": changes,
        "missing_in_destination": missing,
        "mappings": mapping,
    }
