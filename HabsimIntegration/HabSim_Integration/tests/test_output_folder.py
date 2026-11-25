import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fix_habsim_output_folder import fix

class OutputFolderTests(unittest.TestCase):
    def test_optional_plot_file_patch_and_idempotence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'MCVT_v6_3_Plot_Data_Monika.m'
            original = "% Plot output\nmovefile('Sys02_out.mat',Output_Folder,'f');\n"
            path.write_text(original)
            self.assertTrue(fix(path))
            text = path.read_text()
            self.assertIn('fullfile(pwd', text)
            self.assertIn('mkdir(Output_Folder)', text)
            self.assertTrue(path.with_suffix('.m.before_output_folder_fix.bak').exists())
            self.assertFalse(fix(path))
            self.assertEqual(path.with_suffix('.m.before_output_folder_fix.bak').read_text(),original)

if __name__ == '__main__':unittest.main()
