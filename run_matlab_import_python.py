import os
import subprocess

from variable_transfer_v2 import transfer_data

custom_block = r"""save vars.mat;
save("vars.txt", "-ascii");
vars = load("vars.mat");
varNames = fieldnames(vars);
fid = fopen("matlab_output_variables.txt", "w");
for i = 1:numel(varNames)
    name = varNames{i};
    fprintf(fid, "%s = %s\n", name, mat2str(vars.(name)));
end
fclose(fid);"""

custom_lines = custom_block.splitlines()

input_file = "python_variables.py"
output_file = "matlab_variables.m"
matlab_script = "matlab_variables"

original_size = os.path.getsize(output_file)

transfer_data(input_file,output_file,"everything")
with open(output_file, "r") as file:
    original_file = file.read()
with open(output_file, "a") as file:
    file.write("\n" + "\n".join(custom_lines) + "\n")

try :
    subprocess.run(["matlab", "-batch", matlab_script], check = True)
finally:
    with open(output_file, "w") as f:
        f.write(original_file)

try:
    os.remove("vars.mat")
    print("File deleted successfully.")
except FileNotFoundError:
    print("The file does not exist.")

try:
    os.remove("vars.txt")
    print("File deleted successfully.")
except FileNotFoundError:
    print("The file does not exist.")