from Capstone2.old.oldFiles.variable_transfer_v2 import transfer_data
from Capstone2.old.oldFiles.run_matlab_import_python_v2 import full_run

input_file = "python_variables.py"
output_file = "matlab_variables.m"

full_run(input_file, output_file, "txt")