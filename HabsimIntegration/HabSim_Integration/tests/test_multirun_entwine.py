import os
import tempfile
import unittest

import multirun
from multirun_entwine import entwine_iteration_overrides


class Path(object):
    def __init__(self, *indices):
        self.Indices = indices


class Tree(object):
    def __init__(self, paths, branches):
        self.Paths = [Path(*p) for p in paths]
        self.Branches = branches


def plain_pairs(names, values):
    names = [str(n).strip() for n in names]
    values = list(values)
    if len(names) == 1 and len(values) != 1 and not any(isinstance(v, (list, tuple)) for v in values):
        values = [values]
    if len(names) != len(values):
        raise ValueError("name/value count mismatch: %d != %d" % (len(names), len(values)))
    return dict(zip(names, values)), []


class EntwineIterationTests(unittest.TestCase):
    def test_one_scalar_per_name_across_three_entwine_inputs(self):
        names = Tree([(0, 0), (1, 0), (2, 0)],
                     [["a", "b"], ["a", "b"], ["a", "b"]])
        values = Tree([(0, 0), (1, 0), (2, 0)],
                      [[1, 2], [3, 4], [5, 6]])
        result = entwine_iteration_overrides(names, values, {"a": 0, "b": 0}, plain_pairs)
        self.assertEqual(result, [{"a": 1, "b": 2}, {"a": 3, "b": 4}, {"a": 5, "b": 6}])

    def test_one_branch_per_variable_supports_vectors(self):
        names = Tree([(0, 0), (1, 0)], [["position"], ["position"]])
        values = Tree([(0, 0, 0), (1, 0, 0)], [[1, 2, 3], [4, 5, 6]])
        result = entwine_iteration_overrides(names, values, {"position": None}, plain_pairs)
        self.assertEqual(result, [{"position": [1, 2, 3]}, {"position": [4, 5, 6]}])

    def test_mismatched_iteration_inputs_fail_clearly(self):
        names = Tree([(0, 0), (1, 0)], [["a"], ["a"]])
        values = Tree([(0, 0)], [[1]])
        with self.assertRaisesRegex(ValueError, "missing iteration input"):
            entwine_iteration_overrides(names, values, {"a": 0}, plain_pairs)

    def test_missing_entwine_input_index_is_not_silently_reindexed(self):
        names = Tree([(0, 0), (2, 0)], [["a"], ["a"]])
        values = Tree([(0, 0), (2, 0)], [[1], [2]])
        with self.assertRaisesRegex(ValueError, "consecutive"):
            entwine_iteration_overrides(names, values, {"a": 0}, plain_pairs)

    def test_unknown_variable_is_rejected(self):
        names = Tree([(0, 0)], [["not_in_baseline"]])
        values = Tree([(0, 0)], [[1]])
        with self.assertRaisesRegex(ValueError, "not present in the baseline"):
            entwine_iteration_overrides(names, values, {"a": 0}, plain_pairs)

    def test_three_iteration_state_machine_advances_to_completion(self):
        fd, state_path = tempfile.mkstemp(prefix="habsim_multirun_test_", suffix=".json")
        os.close(fd)
        try:
            state = {
                "status": "running",
                "index": 0,
                "iterations": [{"a": 1}, {"a": 2}, {"a": 3}],
                "iteration_done": False,
                "pulse_off_done": False,
                "stop_requested": False,
                "phase": "waiting"
            }
            multirun.save_state(state, state_path)
            self.assertTrue(multirun.finish_iteration(0, state_path))
            after_first = multirun.load_state(state_path)
            self.assertEqual(after_first["index"], 1)
            self.assertEqual(after_first["phase"], "pulse_on")
            self.assertFalse(after_first["iteration_done"])

            self.assertTrue(multirun.finish_iteration(0, state_path))
            after_second = multirun.load_state(state_path)
            self.assertEqual(after_second["index"], 2)
            self.assertEqual(after_second["phase"], "pulse_on")

            self.assertTrue(multirun.finish_iteration(0, state_path))
            final = multirun.load_state(state_path)
            self.assertEqual(final["status"], "complete")
            self.assertEqual(final["index"], 2)
        finally:
            try:
                os.remove(state_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
