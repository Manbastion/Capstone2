import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bridge", REPO / "grasshopper_components/bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "inputs.txt"
        self.dest = self.folder / "parameters.m"
        self.original = b"% Keep comments\nbattry = 0; % battery\nwallThickness = .01;\nuntouched = 42;\n"
        self.dest.write_bytes(self.original)
        bridge.export_inputs(["battery", "wall_thickness"], [95, .08], self.source, apply=True)

    def test_end_to_end_with_repository_backend(self):
        api = bridge.backend(REPO)
        self.assertEqual(api.read_variables(self.source), {"battery": "95", "wall_thickness": "0.08"})
        preview, backup, report = bridge.transfer(REPO, self.source, self.dest,
            ["battery", "wall_thickness"], ["battry", "wallThickness"], apply=True)
        self.assertEqual(Path(backup).read_bytes(), self.original)
        self.assertEqual(api.read_variables(self.dest)["battry"], "95")
        self.assertEqual(api.read_variables(self.dest)["untouched"], "42")
        self.assertIn("% battery", self.dest.read_text())
        self.assertEqual(len(report["changes"]), 2)
        self.assertEqual(bridge.read_result(REPO, self.dest, "wallThickness")[1], [.08])

    def test_current_text_and_json_string_array_inputs_are_preserved(self):
        api = bridge.backend(REPO)
        for suffix, content in ((".py", 'temperature = "ready"\nsolar_power = [1, 1, 2, 3]\n'),
                                (".json", '{"temperature": "ready", "solar_power": [1, 1, 2, 3]}')):
            with self.subTest(suffix=suffix):
                source = self.folder / ("current_inputs" + suffix)
                source.write_text(content)
                self.dest.write_text('temperature = "old";\nsolarPwr = [0, 0];\ncalculated = sum(solarPwr);\n')
                bridge.transfer(REPO, source, self.dest, ["temperature", "solar_power"],
                                ["temperature", "solarPwr"], apply=True)
                values = api.read_variables(self.dest)
                self.assertEqual(values["temperature"], '"ready"')
                self.assertEqual(values["solarPwr"], '[1, 1, 2, 3]')
                self.assertIn('calculated = sum(solarPwr);', self.dest.read_text())

    def test_dry_runs_do_not_write(self):
        target = self.folder / "new.txt"
        bridge.export_inputs(["x"], [1], target)
        self.assertFalse(target.exists())
        bridge.transfer(REPO, self.source, self.dest, ["battery"], ["battry"])
        self.assertEqual(self.dest.read_bytes(), self.original)
        self.assertEqual(list(self.folder.glob("*.bak")), [])

    def test_export_validation_preserves_existing_file(self):
        for names, values in [(["x", "x"], [1, 2]), (["x"], [1, 2]),
                              (["x.y"], [1]), (["for"], [1]), (["x"], [float("nan")]),
                              (["x"], [True]), (["x"], ["1; danger()"]), (["x"], [[1, 2]])]:
            with self.subTest(names=names, values=values):
                before = self.source.read_bytes()
                with self.assertRaises(ValueError):
                    bridge.export_inputs(names, values, self.source, apply=True, overwrite=True)
                self.assertEqual(self.source.read_bytes(), before)

    def test_export_requires_explicit_overwrite(self):
        with self.assertRaises(FileExistsError):
            bridge.export_inputs(["battery"], [1], self.source, apply=True)
        bridge.export_inputs(["battery"], [1], self.source, apply=True, overwrite=True)
        self.assertEqual(self.source.read_text(), "battery = 1\n")

    def test_mapping_failures_leave_destination_unchanged(self):
        for sources, destinations in [(["missing"], ["battry"]), (["battery"], ["missing"]),
            (["battery", "wall_thickness"], ["battry", "battry"]),
            (["battery", "battery"], ["battry", "wallThickness"]), ([], [])]:
            with self.subTest(sources=sources, destinations=destinations):
                with self.assertRaises(ValueError):
                    bridge.transfer(REPO, self.source, self.dest, sources, destinations, apply=True)
                self.assertEqual(self.dest.read_bytes(), self.original)

    def test_repeated_assignments_rejected(self):
        self.dest.write_text("battry = 1;\nbattry = 2;\n")
        with self.assertRaises(ValueError):
            bridge.transfer(REPO, self.source, self.dest, ["battery"], ["battry"], apply=True)
        self.assertEqual(self.dest.read_text(), "battry = 1;\nbattry = 2;\n")

    def test_same_file_rejected(self):
        with self.assertRaises(ValueError):
            bridge.transfer(REPO, self.source, self.source, ["battery"], ["battery"], apply=True)

    def test_actual_repository_json_arrays(self):
        path = REPO / "matlab_output_variables.json"
        data = json.loads(path.read_text())
        names, values = bridge.read_result(REPO, path, "s")
        self.assertIn("t", names)
        self.assertEqual(values, data["s"])
        self.assertEqual(len(values), 21)
        self.assertEqual(bridge.read_result(REPO, path, "a")[1], [2.0])

    def test_bad_json_values_rejected(self):
        path = self.folder / "results.json"
        for value in [[[1, 2]], {"nested": 1}, True, None, "12", float("inf")]:
            with self.subTest(value=value):
                path.write_text(json.dumps({"x": value}))
                with self.assertRaises(ValueError):
                    bridge.read_result(REPO, path, "x")
        path.write_text('{"x": 1, "x": 2}')
        with self.assertRaises(ValueError):
            bridge.read_result(REPO, path, "x")

    def test_button_only_writes_on_armed_rising_edge(self):
        state = {}
        presses = [True, True, False, True, True, False, True]
        self.assertEqual([bridge.button_edge(state, "A", p) for p in presses],
                         [False, False, False, True, False, False, True])
        self.assertFalse(bridge.button_edge(state, "B", True))


if __name__ == "__main__":
    unittest.main()
