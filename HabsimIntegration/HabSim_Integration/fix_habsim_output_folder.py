"""Safely fix the known undefined Output_Folder error in HabSim plotting scripts.

Usage:
    python fix_habsim_output_folder.py "C:\\path\\MCVT_v6_3_Plot_Data_Monika.m"

No changes are made if a default guard is already present. Creates one backup
beside the script before the first change. Does NOT change any Grasshopper wires.
"""
import re
import shutil
import sys
from pathlib import Path

GUARD = ("if ~exist('Output_Folder', 'var') || isempty(Output_Folder)\n"
         "    Output_Folder = fullfile(pwd, 'HabSim_Output');\n"
         "end\n"
         "if ~exist(Output_Folder, 'dir')\n"
         "    mkdir(Output_Folder);\n"
         "end\n")


def fix(path):
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != '.m':
        raise ValueError('Provide the existing MATLAB .m plotting script.')
    raw = path.read_bytes()
    encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        raise ValueError('Please convert the MATLAB script to UTF-8 first.')
    if re.search(r"(?:exist\s*\(\s*'Output_Folder'\s*,\s*'var'|Output_Folder\s*=\s*fullfile\s*\(\s*pwd)", text):
        print('Output_Folder guard or definition already found; review it manually.')
        return False
    # This is the exact statement evidenced by the user's MATLAB error.
    target = re.search(r"^\s*movefile\s*\(\s*['\"]Sys02_out\.mat['\"]\s*,\s*Output_Folder\s*,", text, re.M)
    if not target:
        raise ValueError('Could not find the known movefile(\'Sys02_out.mat\',Output_Folder,...) line. No changes made.')
    line_start = text.rfind('\n', 0, target.start()) + 1
    eol = '\r\n' if '\r\n' in text else '\n'
    if 'Output_Folder' in text[:line_start] and re.search(r'\bOutput_Folder\s*=', text[:line_start]):
        print('Output_Folder appears assigned earlier; not modifying.')
        return False
    backup = path.with_suffix('.m.before_output_folder_fix.bak')
    if not backup.exists():
        shutil.copy2(path, backup)
    updated = text[:line_start] + GUARD.replace('\n', eol) + text[line_start:]
    path.write_bytes(updated.encode(encoding))
    print('Patched:', path)
    print('Original backup:', backup)
    return True


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python fix_habsim_output_folder.py "C:\\path\\MCVT_v6_3_Plot_Data_Monika.m"')
    fix(sys.argv[1])
