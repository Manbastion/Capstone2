import os
import sys

# ---------------------------- CHANGE THESE ----------------------------------
CAPSTONE_FOLDER = r"U:\Capstone\grasshopper_integration\grasshopper_integration"           # folder that contains run_matlab_import_python_v2.py
MATLAB_FILE = r"U:\Capstone\grasshopper_integration\grasshopper_integration\matlab_test.m"      # the SAME .m file that the Grasshopper blocks use
HEADLESS = True    # True = matlab -batch (no MATLAB window, output prints here). False = open the MATLAB desktop.
# -----------------------------------------------------------------------------

sys.path.insert(0, CAPSTONE_FOLDER)
from run_matlab_import_python_v2 import full_run  # noqa: E402

status = full_run(MATLAB_FILE, headless=HEADLESS)
if status == 0:
    print("Done.")
else:
    print("The MATLAB run did not finish cleanly (status %s)." % status)
input("Press ENTER to close program.")
sys.exit(status)