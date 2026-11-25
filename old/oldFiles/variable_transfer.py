import re

variable_list = {"variable_a" : None, 
                 "variable_b" : None, 
                 "variable_c" : None, 
                 "variable_d" : None, 
                 "variable_e" : None, 
                 "variable_f" : None}

file_pattern = r"(\w+)\s*=\s*([\d.]+)"

def transfer_data(input_file, output_file):
    with open(input_file,"r") as open_input_file :
        for line in open_input_file :
            string_match = re.search(file_pattern, line)
            if string_match :
                var_name = string_match.group(1)
                var_value = string_match.group(2)

                if var_name in variable_list:
                    variable_list[var_name] = var_value

    with open(output_file, "r") as open_output_file:
        output_file_content = open_output_file.read()

    for var_name, var_value in variable_list.items():
        target_pattern = r"\b" + re.escape(var_name) + r"\s*=\s*.*"
        replacement_text = f"{var_name} = {var_value}"
        output_file_content = re.sub(target_pattern, replacement_text, output_file_content)

    with open(output_file, "w") as open_output_file:
        open_output_file.write(output_file_content)

py_file = "python_variables.py"
matlab_file = "matlab_variables.m"

transfer_data(matlab_file, py_file)