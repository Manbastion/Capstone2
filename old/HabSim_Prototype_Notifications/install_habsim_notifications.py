"""Add the per-run HabSim notification hook to a working prototype."""
import ast
import io
import os
from pathlib import Path
import re
import shutil
import tempfile
import tokenize


HERE = Path(__file__).resolve().parent
RUNNER_MODULE = "run_matlab_import_python_v2"
HOOK_MODULE = "habsim_completion"
HOOK = "notify_run"
LOCAL_HOOK = "_habsim_notify_run"


def read_source(data):
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    return data.decode(encoding), encoding


def edited_source(data, filename):
    source, encoding = read_source(data)
    tree = ast.parse(source, filename=filename)
    defs = [node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "full_run"]
    if len(defs) != 1:
        raise ValueError("Expected one top-level full_run() in " + filename + ".")
    runner = defs[0]
    imported = {
        name.asname or name.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.level == 0
        and node.module == HOOK_MODULE and node.lineno < runner.lineno
        for name in node.names if name.name == HOOK
    }
    decorators = {item.id for item in runner.decorator_list if isinstance(item, ast.Name)}
    if imported & decorators:
        return None  # A previous setup, or the GitHub hook, is already active.
    if decorators & {HOOK, LOCAL_HOOK}:
        raise ValueError("full_run() already has a notification decorator without its import. "
                         "Please check the existing notification edit.")

    first_line = min([runner.lineno] + [item.lineno for item in runner.decorator_list])
    newline = re.search(r"\r\n|\n|\r", source)
    eol = newline.group(0) if newline else "\n"
    lines = re.split(r"(?<=\n)|(?<=\r)(?!\n)", source)
    lines.insert(first_line - 1, eol.join((
        "from " + HOOK_MODULE + " import " + HOOK + " as " + LOCAL_HOOK,
        "", "", "@" + LOCAL_HOOK, "",
    )))
    updated = "".join(lines).encode(encoding)
    compile(updated, filename, "exec")
    return updated


def make_backup(target, data):
    index = 0
    while True:
        suffix = ".before_notifications" + ("." + str(index) if index else "")
        backup = target.with_name(target.name + suffix)
        try:
            with backup.open("xb") as stream:
                stream.write(data)
            return backup
        except FileExistsError:
            index += 1


def update_runner(folder):
    launcher = folder / "run_matlab.py"
    target = folder / (RUNNER_MODULE + ".py")
    if not launcher.is_file() or not target.is_file():
        raise ValueError(
            "Copy the contents of this bundle into the grasshopper_integration "
            "folder that already contains run_matlab.py and " + target.name + "."
        )
    for name in ("habsim_completion.py", "habsim_notifications.py"):
        if not (folder / name).is_file():
            raise ValueError("Missing " + name + ". Copy all the files from the bundle.")
    source, _ = read_source(launcher.read_bytes())
    script = ast.parse(source, filename=str(launcher))
    if not any(isinstance(node, ast.ImportFrom) and node.level == 0
               and node.module == RUNNER_MODULE and any(n.name == "full_run" for n in node.names)
               for node in ast.walk(script)):
        raise ValueError(
            launcher.name + " does not import full_run() from " + target.name
            + ". This prototype needs a different notification hook."
        )

    original = target.read_bytes()
    updated = edited_source(original, str(target))
    if updated is None:
        return None
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=folder, prefix=".notify-",
                                         suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(updated)
        shutil.copymode(target, temp)
        if target.read_bytes() != original:
            raise ValueError(target.name + " changed during setup. Close any editor and retry.")
        backup = make_backup(target, original)
        os.replace(temp, target)
        return backup
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def main():
    try:
        backup = update_runner(HERE)
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        print("Could not enable notifications: " + str(error))
        return 1
    if backup is None:
        print("The notification hook is already enabled.")
    else:
        print("Notifications added. Your original runner is backed up as:")
        print(backup.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
