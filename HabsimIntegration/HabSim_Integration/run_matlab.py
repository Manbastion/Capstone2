"""Launch the MATLAB script supplied by the Grasshopper definition."""

import os
import sys

SCRIPT_FOLDER = os.path.dirname(os.path.abspath(__file__))
MATLAB_FILE = 'C:\\Users\\tarus\\Desktop\\ICT Capstone\\GH-HABSIM-Prototype7-Multirun-Regression-Fix\\GH_HABSIM_Prototype7_Notifications_Fixed\\GH_HabSim_Fixed\\examples\\matlab_test_original.m'
MATLAB_ROOT = 'C:\\Program Files\\MATLAB\\R2024a'
HEADLESS = True

if not MATLAB_FILE:
    raise ValueError("MATLAB_FILE has not been configured by the Grasshopper component.")
if not MATLAB_ROOT:
    raise ValueError("MATLAB_ROOT has not been configured by the Grasshopper component.")

sys.path.insert(0, SCRIPT_FOLDER)
from Capstone2.old.HabSim_Integration_Multirun_History_AutoDetect.HabSim_Integration.run_matlab_import_python_v2 import full_run

matlab_executable = os.path.join(MATLAB_ROOT, "bin", "matlab.exe")
if os.name != "nt":
    matlab_executable = os.path.join(MATLAB_ROOT, "bin", "matlab")

if not os.path.isfile(matlab_executable):
    raise FileNotFoundError(
        "MATLAB executable was not found at: %s. Check the MATLAB Root input."
        % matlab_executable
    )

status = full_run(MATLAB_FILE, matlab_executable, headless=HEADLESS)

if status == 0:
    print("MATLAB run completed.")
else:
    print("MATLAB run failed with status %s." % status)

sys.exit(status)