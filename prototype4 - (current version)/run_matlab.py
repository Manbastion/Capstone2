import os
import sys

# ---------------------------- CHANGE THESE ----------------------------------
CAPSTONE_FOLDER = r"U:\Capstone\grasshopper_integration\grasshopper_integration"           # folder that contains run_matlab_import_python_v2.py
MATLAB_FILE = r"U:\Capstone\grasshopper_integration\grasshopper_integration\matlab_test.m"      # the SAME .m file that the Grasshopper blocks use
SAVE_TYPE = "json"                                    # "json", "csv" or "txt"
# -----------------------------------------------------------------------------

sys.path.insert(0, CAPSTONE_FOLDER)
from Capstone2.prototype4.run_matlab_import_python_v2 import full_run  # noqa: E402

# full_run uses plain file names, so work from the .m file's own folder.
# This also makes the output files land next to the .m file.
os.chdir(os.path.dirname(os.path.abspath(MATLAB_FILE)))
full_run(os.path.basename(MATLAB_FILE), SAVE_TYPE)
print("Done. Output written next to:", MATLAB_FILE)
input("Press ENTER to close program.")
