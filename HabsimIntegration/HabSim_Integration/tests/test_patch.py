"""Regression tests for the equation and repeatable revert additions."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matlab_literals as ml
import variable_transfer_v2 as vt
import value_formats as vf
import history


class EquationTransferTests(unittest.TestCase):
    def test_read_expressions_and_initial_assignment_only(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'simulation.m'
            path.write_text('''a = 25 + b;\nb = sin(t);\nz = [1 2];\nfor t = 1:10\n    a = a + 2;\nend\n''')
            variables = vt.read_variables(path)
            self.assertEqual(variables['a'], '25 + b')
            self.assertEqual(variables['b'], 'sin(t)')
            self.assertEqual(variables['z'], '[1 2]')
            self.assertNotIn('t', variables)

    def test_transfer_and_revert_equation(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'simulation.m'
            src = Path(folder) / 'source.m'
            dest.write_text('''a = 25 + b; % initial\nb = sin(t);\nfor t = 1:10\n    a = a + 2;\nend\n''')
            src.write_text('''a = 100 + b;\nb = 5;\n''')
            result = vt.transfer_data(src, dest)
            updated = dest.read_text()
            self.assertIn('a = 100 + b; % initial', updated)
            self.assertIn('b = 5;', updated)
            self.assertIn('    a = a + 2;', updated)
            self.assertEqual(result['changes']['a']['before'], '25 + b')
            vt.set_variable_values(dest, {k: x['before'] for k,x in result['changes'].items()}, strict=True)
            self.assertIn('a = 25 + b;', dest.read_text())
            self.assertIn('b = sin(t);', dest.read_text())

    def test_grasshopper_equation_opt_in(self):
        self.assertEqual(vf.convert('a', '=25 + b')[0], '25 + b')
        self.assertEqual(vf.convert('a', '=linspace(0,1,10)')[0], 'linspace(0,1,10)')
        self.assertEqual(vf.convert('a', 'hello + world')[0], "'hello + world'")
        self.assertFalse(ml.is_value('25; delete(\'file\')'))
        self.assertFalse(ml.is_value('5\nquit'))
        self.assertFalse(ml.is_value('other = 5'))

    def test_revert_unlimited(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / 'simulation.m'
            dest.write_text('a = 100;\n')
            old_file = history.FILE
            try:
                history.FILE = Path(folder) / 'history.json'
                record = history.record_transfer('source.m', dest, 'All Variables', ['a'],
                    [{'source':'a','destination':'a'}],
                    {'a': {'source':'a', 'before':'25 + b', 'after':'100'}}, {'a':'a'})
                # Legacy record has reverted_at set, but should remain repeatable.
                records = history.load_history()
                records[0]['reverted_at'] = '2026-11-15T14:15:50'
                history.FILE.write_text(json.dumps(records))
                for _ in range(3):
                    dest.write_text('a = 100;\n')
                    history.revert_transfer(record['id'])
                    self.assertEqual(vt.read_variables(dest)['a'], '25 + b')
                self.assertNotIn('reverted_at', history.load_history()[0])
                self.assertFalse(history.conflicts(history.load_history()[0]))
            finally:
                history.FILE = old_file

if __name__ == '__main__':
    unittest.main()
