import re

ASSIGNMENT_PATTERN = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<name>[A-Za-z_]\w*)"
    r"(?P<before_eq>\s*=\s*)"
    r"(?P<value>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    r"(?P<semicolon>\s*;?)"
    r"(?P<comment>\s*(?:[%#].*)?)$"
)


def read_variables(file_path):
    variables = {}

    with open(file_path, "r", encoding="utf-8") as file:
        for line in file:
            match = ASSIGNMENT_PATTERN.match(line.rstrip("\n"))
            if match:
                variables[match.group("name")] = match.group("value")

    return variables


def transfer_data(input_file, output_file, mode="everything", selected_variables=None):

    source_variables = read_variables(input_file)
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
    new_lines = []

    for line in output_lines:
        original_newline = "\n" if line.endswith("\n") else ""
        text = line.rstrip("\n")
        match = ASSIGNMENT_PATTERN.match(text)

        if not match:
            new_lines.append(line)
            continue

        name = match.group("name")
        destination_variables.add(name)

        if name in variables_to_transfer:
            new_value = source_variables[name]

            # Preserve the destination file's indentation, spacing,
            # semicolon, and trailing comment. Only the value changes.
            replacement = (
                f'{match.group("indent")}'
                f'{name}'
                f'{match.group("before_eq")}'
                f'{new_value}'
                f'{match.group("semicolon")}'
                f'{match.group("comment")}'
            )
            new_lines.append(replacement + original_newline)
            transferred.append(name)
        else:
            new_lines.append(line)

    with open(output_file, "w", encoding="utf-8") as file:
        file.writelines(new_lines)

    missing_in_destination = sorted(variables_to_transfer - destination_variables)

    return {
        "source_count": len(source_variables),
        "requested_count": len(variables_to_transfer),
        "transferred": sorted(set(transferred)),
        "missing_in_destination": missing_in_destination,
    }

if __name__ == "__main__":
    py_file = "python_variables.py"
    matlab_file = "matlab_variables.m"
    result = transfer_data(py_file, matlab_file, "everything")
    print(result)
