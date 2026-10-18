"""Rhino-independent adapter for the repository's current transfer backend."""
import importlib.util
import csv
import hashlib
import json
import keyword
import math
import os
from pathlib import Path
import re
import tempfile
import uuid


def backend(repo):
    path = Path(repo).expanduser().resolve() / "variable_transfer_v2.py"
    if not path.is_file():
        raise ValueError("Repo must be the Capstone2 folder containing variable_transfer_v2.py.")
    spec = importlib.util.spec_from_file_location("capstone_transfer_backend", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def absolute_file(value):
    if value is None or not str(value).strip():
        raise ValueError("Supply a full file path.")
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        raise ValueError("Use a full, absolute file path.")
    return path.resolve()


def numeric(value):
    if isinstance(value, bool):
        raise ValueError("Boolean values are not numeric simulation inputs.")
    text = str(value).strip()
    if not re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", text):
        raise ValueError("Expected a scalar number, got {!r}.".format(value))
    if not math.isfinite(float(text)):
        raise ValueError("NaN, infinity and overflowing numbers are not supported.")
    return text


def build_assignments(names, values):
    names, values = list(names), list(values)
    if not names or len(names) != len(values):
        raise ValueError("Names and Values must be non-empty lists of equal length.")
    # Conservative identifier subset valid in both Python and MATLAB.
    matlab_keywords = set("break case catch classdef continue else elseif end for function global if otherwise parfor persistent return spmd switch try while".split())
    used, lines = set(), []
    for name, value in zip(names, values):
        name = str(name).strip()
        if (not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", name)
                or keyword.iskeyword(name) or name in matlab_keywords):
            raise ValueError("Unsupported variable name: {!r}.".format(name))
        if name in used:
            raise ValueError("Duplicate variable name: " + name)
        used.add(name)
        lines.append("{} = {}".format(name, numeric(value)))
    return "\n".join(lines) + "\n"


def export_inputs(names, values, target, apply=False, overwrite=False):
    content = build_assignments(names, values)
    path = absolute_file(target)
    if path.suffix.lower() not in (".txt", ".py", ".m"):
        raise ValueError("Export to .txt, .py or .m; this is assignment text, not JSON/CSV.")
    if not path.parent.is_dir():
        raise ValueError("Create the destination folder first.")
    if apply:
        if path.exists() and not overwrite:
            raise FileExistsError("File exists. Set Overwrite=True to replace this export file.")
        if overwrite:
            _atomic_replace(path, content.encode("utf-8"))
        else:
            with path.open("x", encoding="utf-8", newline="\n") as output:
                output.write(content)
    return content


def _atomic_replace(path, content):
    fd, temporary = tempfile.mkstemp(prefix=".capstone-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def scalar_variables(api, path):
    """Use current assignment grammar, preserving strings/arrays and rejecting duplicates."""
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        parsed = api._parse_assignment(line)
        if parsed:
            name, value = parsed["name"], parsed["value"]
            if name in data:
                raise ValueError("Repeated assignment to {!r}; use a flat parameter file.".format(name))
            data[name] = value
    if not data:
        raise ValueError("No supported input assignments found in " + str(path))
    return data


def transfer(repo, source, destination, source_names, destination_names, apply=False):
    api = backend(repo)
    source, destination = absolute_file(source), absolute_file(destination)
    if source == destination or os.path.samefile(source, destination):
        raise ValueError("Source and destination must be different files.")
    source_data = source_variables(api, source)
    dest_data = scalar_variables(api, destination)
    source_names = [str(n).strip() for n in source_names]
    destination_names = [str(n).strip() for n in destination_names]
    if not source_names or len(source_names) != len(destination_names):
        raise ValueError("Supply equal, non-empty SourceNames and DestinationNames lists.")
    if len(set(source_names)) != len(source_names) or len(set(destination_names)) != len(destination_names):
        raise ValueError("Each source and destination name must appear only once.")
    for name in source_names:
        if name not in source_data:
            raise ValueError("Source variable not found: " + name)
    for name in destination_names:
        if name not in dest_data:
            raise ValueError("Destination variable not found: " + name)
    mapping = dict(zip(source_names, destination_names))
    report = api.transfer_data(str(source), str(destination), mode="include",
                               selected_variables=source_names, source_variables=source_data,
                               mappings=mapping, apply=False)
    preview = ["{} -> {}: {} -> {}".format(s, d, dest_data[d], source_data[s])
               for s, d in mapping.items()]
    backup = ""
    if apply:
        # Run the existing writer against a temporary copy, then replace only
        # after it succeeds. Keep an independent full-file backup for this path.
        original = destination.read_bytes()
        fd, temporary = tempfile.mkstemp(prefix=".capstone-transfer-", dir=str(destination.parent))
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(original)
            api.transfer_data(str(source), temporary, mode="include",
                              selected_variables=source_names, source_variables=source_data,
                              mappings=mapping, apply=True)
            if destination.read_bytes() != original:
                raise RuntimeError("Destination changed during transfer; try again after closing other editors.")
            backup_path = destination.with_name(destination.name + "." + uuid.uuid4().hex[:12] + ".bak")
            with backup_path.open("xb") as output:
                output.write(original)
            backup = str(backup_path)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return preview, backup, report


def source_variables(api, path):
    """Accept current text/JSON inputs or an explicit two-column name,value CSV."""
    if path.suffix.lower() == ".json":
        json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_json_object)
        data = api.read_variables(str(path))
        if not data:
            raise ValueError("JSON source contains no supported variables.")
        return data
    if path.suffix.lower() != ".csv":
        return scalar_variables(api, path)
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != ["name", "value"]:
        raise ValueError("Input CSV must start with the exact header name,value.")
    result = {}
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != 2:
            raise ValueError("Input CSV needs exactly two columns per row.")
        name, value = row[0].strip(), row[1].strip()
        if not api.valid_name(name) or name in result:
            raise ValueError("Invalid or duplicate CSV variable name: " + name)
        result[name] = api.normalise_value(value)
    if not result:
        raise ValueError("Input CSV has no numeric variables.")
    return result


def read_csv_results(path):
    """Numeric columns with headers; shorter columns may have trailing blanks."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or not rows[0]:
        raise ValueError("Results CSV is empty.")
    names = [name.strip() for name in rows[0]]
    if any(not n for n in names) or len(set(names)) != len(names):
        raise ValueError("Results CSV needs unique, non-empty column headers.")
    result = {name: [] for name in names}
    ended = set()
    for row in rows[1:]:
        if not row:
            continue
        if len(row) != len(names):
            raise ValueError("Every results CSV row must match the header width.")
        for name, value in zip(names, row):
            if not value.strip():
                ended.add(name)
            elif name in ended:
                raise ValueError("CSV column {!r} has an internal blank; refusing to shift sample alignment.".format(name))
            else:
                result[name].append(float(numeric(value)))
    return result


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def read_result(repo, path, variable):
    path = absolute_file(path)
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_json_object)
        if not isinstance(data, dict):
            raise ValueError("JSON must contain a top-level object of named variables.")
    elif path.suffix.lower() == ".csv":
        data = read_csv_results(path)
    else:
        data = scalar_variables(backend(repo), path)
    names = list(data)
    if variable is None or not str(variable).strip():
        return names, []
    name = str(variable).strip()
    if name not in data:
        raise ValueError("Variable {!r} not found. Available: {}".format(name, ", ".join(names)))
    value = data[name]
    values = value if isinstance(value, list) else [value]
    if any(isinstance(v, (list, dict)) or v is None for v in values):
        raise ValueError("Only scalars and flat numeric arrays are supported; matrices/structures need an adapter.")
    if path.suffix.lower() == ".json" and any(isinstance(v, (str, bool)) for v in values):
        raise ValueError("JSON results must be numbers, not strings or Booleans.")
    return names, [float(numeric(v)) for v in values]


def button_edge(state, key, pressed):
    """Require an observed False before True; held buttons never repeat writes."""
    current = bool(pressed)
    previous = state.get(key, True)
    state[key] = current
    return current and not previous


def transfer_signature(source, destination, source_names, destination_names):
    """Track whether a successful transfer still represents the current inputs."""
    source, destination = absolute_file(source), absolute_file(destination)
    fields = [str(source), str(destination), list(source_names), list(destination_names),
              hashlib.sha256(source.read_bytes()).hexdigest(),
              hashlib.sha256(destination.read_bytes()).hexdigest()]
    return json.dumps(fields)
