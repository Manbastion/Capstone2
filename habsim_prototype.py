"""Load Prototype 4 without requiring the checkout to be named Capstone2.

Keep its backend in a separate package: the legacy root has modules with the
same names and must not accidentally satisfy Prototype 4 imports in Rhino.
"""
import importlib
from pathlib import Path
import sys
import types


def load_prototype(module=None, repo=None):
    root = Path(repo).expanduser().resolve() if repo else Path(__file__).resolve().parent
    folder = root / "prototype4 - (current version)"
    if (root / "gh_bridge.py").is_file():
        folder, root = root, root.parent
    if not (folder / "gh_bridge.py").is_file():
        raise ValueError("Choose the extracted Capstone2 folder containing 'prototype4 - (current version)'.")
    name = "habsim_prototype4"
    previous = sys.modules.get(name)
    if previous is not None and list(previous.__path__) != [str(folder)]:
        raise ValueError("Another Prototype 4 folder is already loaded. Restart Rhino before changing Repo.")
    if previous is None:
        package = types.ModuleType(name)
        package.__path__ = [str(folder)]
        package.__package__ = name
        sys.modules[name] = package
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return importlib.import_module(name + "." + module) if module else sys.modules[name]
