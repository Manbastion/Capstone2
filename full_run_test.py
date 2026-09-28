from variable_transfer_v2 import transfer_data
from run_matlab_import_python_v2 import full_run

input_file = "python_variables.txt"
output_file = "matlab_variables.m"

full_run(input_file, output_file, "json")