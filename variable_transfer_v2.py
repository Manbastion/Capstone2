import re

NUM = r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?"
ASSIGN = re.compile(
    rf"^(\s*)([A-Za-z_]\w*)(\s*=\s*)({NUM})(\s*;?)(\s*(?:[%#].*)?)$"
)

def valid_name(x):
    return bool(re.fullmatch(r"[A-Za-z_]\w*", str(x).strip()))

def valid_value(x):
    return bool(re.fullmatch(NUM, str(x).strip()))

is_valid_variable_name = valid_name
is_valid_numeric_value = valid_value

def _split(line):
    if line.endswith("\r\n"): return line[:-2], "\r\n"
    if line.endswith("\n"): return line[:-1], "\n"
    return line, ""

def read_variables(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = ASSIGN.match(_split(line)[0])
            if m: out[m.group(2)] = m.group(4)
    return out

def _check(name, value):
    if not valid_name(name): raise ValueError(f"Invalid variable name: {name!r}")
    if not valid_value(value): raise ValueError(f"Invalid numeric value for {name}: {value!r}")

def _write_changes(path, changes, strict=True):
    for old, (new, value) in changes.items():
        _check(old, value)
        if not valid_name(new): raise ValueError(f"Invalid variable name: {new!r}")

    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    found, out = set(), []
    for line in lines:
        text, nl = _split(line)
        m = ASSIGN.match(text)
        if not m or m.group(2) not in changes:
            out.append(line)
            continue

        old = m.group(2)
        new, value = changes[old]
        out.append(f"{m.group(1)}{new}{m.group(3)}{value}{m.group(5)}{m.group(6)}{nl}")
        found.add(old)

    missing = sorted(set(changes) - found)
    if strict and missing:
        raise ValueError("Could not find: " + ", ".join(missing))

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.writelines(out)
    return {"updated": sorted(found), "missing": missing}

def set_variable_values(path, values, strict=False):
    return _write_changes(path, {k: (k, str(v).strip()) for k, v in values.items()}, strict)

def update_source_variables(path, changes):
    final = [str(v["name"]).strip() for v in changes.values()]
    if len(final) != len(set(final)):
        raise ValueError("Variable names must be unique.")
    data = {
        str(old).strip(): (str(v["name"]).strip(), str(v["value"]).strip())
        for old, v in changes.items()
    }
    result = _write_changes(path, data, True)
    return {"updated": result["updated"], "count": len(result["updated"])}

def transfer_data(input_file, output_file, mode="everything", selected_variables=None, source_variables=None):
    source = dict(source_variables or read_variables(input_file))
    if not source: raise ValueError("No supported variables found in source file.")
    for k, v in source.items(): _check(k, v)

    selected = set(selected_variables or [])
    wanted = (
        set(source) if mode == "everything"
        else set(source) & selected if mode == "include"
        else set(source) - selected if mode == "exclude"
        else None
    )
    if wanted is None: raise ValueError(f"Unknown transfer mode: {mode}")

    with open(output_file, encoding="utf-8") as f:
        lines = f.readlines()

    found, transferred, changes, out = set(), [], {}, []
    for line in lines:
        text, nl = _split(line)
        m = ASSIGN.match(text)
        if not m:
            out.append(line)
            continue

        name = m.group(2)
        found.add(name)
        if name not in wanted:
            out.append(line)
            continue

        old, new = m.group(4), source[name]
        out.append(f"{m.group(1)}{name}{m.group(3)}{new}{m.group(5)}{m.group(6)}{nl}")
        transferred.append(name)
        if old != new: changes[name] = {"before": old, "after": new}

    with open(output_file, "w", encoding="utf-8", newline="") as f:
        f.writelines(out)

    return {
        "transferred": sorted(set(transferred)),
        "changes": changes,
        "missing_in_destination": sorted(wanted - found),
    }