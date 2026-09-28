import re
from difflib import SequenceMatcher

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
ASSIGN = re.compile(
    rf"^(\s*)([A-Za-z_]\w*)(\s*=\s*)({NUM})(\s*;?)(\s*(?:[%#].*)?)$"
)


def valid_name(value):
    return bool(re.fullmatch(r"[A-Za-z_]\w*", str(value).strip()))


def valid_value(value):
    return bool(re.fullmatch(NUM, str(value).strip()))


is_valid_variable_name = valid_name
is_valid_numeric_value = valid_value


def _split(line):
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def read_variables(path):
    """Read simple scalar numeric assignments from .py/.m/.txt-style files."""
    variables = {}
    with open(path, encoding="utf-8") as file:
        for line in file:
            text = _split(line)[0]
            match = ASSIGN.match(text)
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

    with open(path, encoding="utf-8") as file:
        lines = file.readlines()

    found = set()
    output = []

    for line in lines:
        text, newline = _split(line)
        match = ASSIGN.match(text)

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


# ---------------- fuzzy matching ----------------

def _name_parts(name):
    """Turn names such as batteryVoltage, battery_voltage and Battry into comparable text."""
    value = str(name).strip()
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return [part.lower() for part in value.split() if part]


def _normalised_name(name):
    return "".join(_name_parts(name))


def _token_similarity(source, destination):
    a = set(_name_parts(source))
    b = set(_name_parts(destination))

    if not a or not b:
        return 0.0

    return len(a & b) / len(a | b)


def name_similarity(source, destination):
    """
    Return a 0..1 fuzzy similarity score.

    Combines:
      - normalised edit similarity
      - token similarity
      - exact normalised-name match
    """
    source = str(source)
    destination = str(destination)

    normal_a = _normalised_name(source)
    normal_b = _normalised_name(destination)

    if not normal_a or not normal_b:
        return 0.0

    if normal_a == normal_b:
        return 1.0

    sequence_score = SequenceMatcher(None, normal_a, normal_b).ratio()
    token_score = _token_similarity(source, destination)

    return round(0.75 * sequence_score + 0.25 * token_score, 4)


def fuzzy_matches(source_names, destination_names, minimum_score=0.45):
    """Return every useful source -> destination candidate, highest first."""
    matches = []

    for source in source_names:
        candidates = []

        for destination in destination_names:
            score = name_similarity(source, destination)

            if score >= minimum_score:
                candidates.append(
                    {
                        "source": source,
                        "destination": destination,
                        "score": score,
                    }
                )

        candidates.sort(key=lambda item: (-item["score"], item["destination"]))
        matches.extend(candidates)

    return sorted(
        matches,
        key=lambda item: (-item["score"], item["source"], item["destination"]),
    )


def best_fuzzy_match(source, destination_names, used_destinations=None):
    """Return the strongest unused destination match for one source variable."""
    used = set(used_destinations or [])

    candidates = [
        (destination, name_similarity(source, destination))
        for destination in destination_names
        if destination not in used
    ]

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[1], item[0]))
    destination, score = candidates[0]

    return {
        "source": source,
        "destination": destination,
        "score": round(score, 4),
    }


def similarity_label(score):
    if score >= 0.90:
        return "Very high"
    if score >= 0.80:
        return "High"
    if score >= 0.65:
        return "Medium"
    if score >= 0.50:
        return "Low"
    return "Very low"


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

    with open(output_file, encoding="utf-8") as file:
        lines = file.readlines()

    found = set()
    transferred = []
    changes = {}
    output = []

    for line in lines:
        text, newline = _split(line)
        match = ASSIGN.match(text)

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
        with open(output_file, "w", encoding="utf-8", newline="") as file:
            file.writelines(output)

    return {
        "transferred": transferred,
        "changes": changes,
        "missing_in_destination": missing,
        "mappings": mapping,
    }
