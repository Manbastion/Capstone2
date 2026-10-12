"""run_matlab_gh.py - runs a MATLAB script and exports its variables.

This is the same flow as your run_matlab_import_python script:
  1. append an export block to the .m file
  2. run it with `matlab -batch`
  3. restore the .m file exactly as it was (even if MATLAB fails)
  4. delete the temporary vars.mat / vars.txt

Differences, because Grasshopper calls it:
  * it takes the .m file path as an argument (nothing is hard-coded)
  * it does NOT call transfer_data - the Transfer block already did that
  * it runs MATLAB from the .m file's own folder
  * the export skips variables mat2str can't print (structs, cells, ...)
    instead of stopping MATLAB with an error
Uses only the standard library, so it works in any Python 3.

From a terminal:
    python run_matlab_gh.py "C:\\path\\to\\matlab_variables.m" [path\\to\\matlab.exe]
Output is written to matlab_output_variables.txt next to the .m file.
"""
import os
import subprocess
import sys

OUTPUT_NAME = "matlab_output_variables.txt"

CUSTOM_BLOCK = r"""save vars.mat;
save("vars.txt", "-ascii");
vars = load("vars.mat");
varNames = fieldnames(vars);
fid = fopen("matlab_output_variables.txt", "w");
for i = 1:numel(varNames)
    name = varNames{i};
    try
        fprintf(fid, "%s = %s\n", name, mat2str(vars.(name)));
    catch
    end
end
fclose(fid);"""


def run(matlab_file, matlab_exe="matlab", timeout=600):
    """Run the .m file and return the path of the exported variables file."""
    matlab_file = os.path.abspath(matlab_file)
    if not os.path.isfile(matlab_file):
        raise FileNotFoundError("MATLAB file not found: %s" % matlab_file)

    if os.path.isfile(matlab_exe):  # a path to matlab.exe: make it absolute
        matlab_exe = os.path.abspath(matlab_exe)

    folder = os.path.dirname(matlab_file)
    script = os.path.splitext(os.path.basename(matlab_file))[0]
    output = os.path.join(folder, OUTPUT_NAME)
    if os.path.exists(output):
        os.remove(output)

    with open(matlab_file, "r", encoding="utf-8", newline="") as f:
        original = f.read()

    try:
        with open(matlab_file, "w", encoding="utf-8", newline="") as f:
            f.write(original + "\n" + CUSTOM_BLOCK + "\n")
        # cd first so the script and its output files are found in its folder
        command = "cd('%s'); %s" % (folder.replace("'", "''"), script)
        proc = subprocess.run([matlab_exe, "-batch", command], cwd=folder,
                              capture_output=True, text=True, timeout=timeout)
    finally:
        with open(matlab_file, "w", encoding="utf-8", newline="") as f:
            f.write(original)  # always restore the user's file
        for name in ("vars.mat", "vars.txt"):
            try:
                os.remove(os.path.join(folder, name))
            except FileNotFoundError:
                pass

    if proc.returncode != 0:
        raise RuntimeError("MATLAB failed:\n" + (proc.stderr or proc.stdout)[-1500:])
    if not os.path.isfile(output):
        raise RuntimeError("MATLAB finished but wrote no %s." % OUTPUT_NAME)
    return output


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        print(run(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "matlab"))
    except Exception as error:
        print(error, file=sys.stderr)
        sys.exit(1)
