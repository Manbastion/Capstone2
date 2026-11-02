from pathlib import Path
import sys

# Grasshopper updates these three lines. Empty defaults show a useful error.
CAPSTONE_FOLDER = r""
MATLAB_FILE = r""
SAVE_TYPE = "json"


def main():
    folder = Path(CAPSTONE_FOLDER).expanduser().resolve() if CAPSTONE_FOLDER else Path(__file__).resolve().parent
    if not (folder / "habsim_prototype.py").is_file():
        folder = folder.parent
    sys.path.insert(0, str(folder))
    from habsim_prototype import load_prototype
    runner = load_prototype("run_matlab_import_python_v2", folder)
    if not MATLAB_FILE:
        raise ValueError("Choose a MATLAB file in the RUN MATLAB block, or use Launch_HabSim.bat.")
    runner.full_run(MATLAB_FILE, SAVE_TYPE)
    try:
        input("Press ENTER to close program.")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
