import os
import subprocess

from variable_transfer_v2 import transfer_data

custom_block_txt = r"""save vars.mat;
save("vars.txt", "-ascii");
vars = load("vars.mat");
varNames = fieldnames(vars);
fid = fopen("matlab_output_variables.txt", "w");
for i = 1:numel(varNames)
    name = varNames{i};
    fprintf(fid, "%s = %s\n", name, mat2str(vars.(name)));
end
fclose(fid);"""

custom_block_csv = r"""save vars.mat;
vars = load("vars.mat")
varNames = fieldnames(vars);
T = struct2table(vars)
writetable(T, "matlab_output_variables.csv")"""

custom_block_json = r"""save vars.mat;
vars = load("vars.mat");
fid = fopen("matlab_output_variables.json", "w");
fprintf(fid, "%s", jsonencode(vars, "PrettyPrint", true));
fclose(fid);"""

def full_run(input_file, output_file, save_type) :

    match (save_type) :
        case "csv" :
            custom_block = custom_block_csv
        case "json" :
            custom_block = custom_block_json
        case _ :
            custom_block = custom_block_txt
    custom_lines = custom_block.splitlines()

    matlab_script = output_file[0:len(output_file)-2]
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
        print("\nFile deleted successfully.")
    except FileNotFoundError:
        print("The file does not exist.")

    try:
        os.remove("vars.txt")
        print("File deleted successfully.")
    except FileNotFoundError:
        print("The file does not exist.")