"""Check Python component wiring/state with host stubs, not a live Rhino UI."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
COMPONENTS = REPO


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settings = self.root / "notifications.json"
        settings.write_text('{"enabled": false}')
        quiet = patch.dict(os.environ, {"HABSIM_NOTIFICATION_SETTINGS": str(settings)})
        quiet.start()
        self.addCleanup(quiet.stop)
        self.messages = []
        sc = ModuleType("scriptcontext")
        sc.sticky = {}
        gh, kernel = ModuleType("Grasshopper"), ModuleType("Grasshopper.Kernel")
        kernel.GH_RuntimeMessageLevel = SimpleNamespace(Error="Error", Warning="Warning")
        self.patch = patch.dict(sys.modules, {"scriptcontext": sc, "Grasshopper": gh, "Grasshopper.Kernel": kernel})
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.env = SimpleNamespace(Component=SimpleNamespace(
            InstanceGuid="test-component", AddRuntimeMessage=lambda level, text: self.messages.append(text)))

    def execute(self, filename, inputs):
        scope = {"Repo": str(REPO), "ghenv": self.env}
        scope.update(inputs)
        exec(compile((COMPONENTS / filename).read_text(), filename, "exec"), scope)
        return scope

    def test_transfer_path_persists_then_invalidates(self):
        source, dest = self.root / "input.py", self.root / "dest.m"
        source.write_text("v0 = 12\n")
        dest.write_text("v0 = 0;\n")
        inputs = dict(SourceFile=str(source), DestinationFile=str(dest), SourceNames=["v0"],
                      DestinationNames=["v0"], Apply=False)
        self.assertFalse(self.execute("01_transfer_variables.py", inputs)["Ready"])
        inputs["Apply"] = True
        output = self.execute("01_transfer_variables.py", inputs)
        self.assertTrue(output["Ready"], output["Status"])
        self.assertEqual(output["TransferredFile"], str(dest.resolve()))
        inputs["Apply"] = False
        self.assertTrue(self.execute("01_transfer_variables.py", inputs)["Ready"])
        source.write_text("v0 = 20\n")
        changed = self.execute("01_transfer_variables.py", inputs)
        self.assertFalse(changed["Ready"])
        self.assertEqual(changed["TransferredFile"], "")

    def test_loader_waits_and_clears_previous_values(self):
        results = self.root / "results.json"
        results.write_text(json.dumps({"s": [0, 85, 220]}))
        inputs = dict(FilePath=str(results), Variable="s", Load=True, Refresh=False)
        loaded = self.execute("03_read_results.py", inputs)
        self.assertEqual(loaded["Values"], [0, 85, 220])
        inputs["Load"] = False
        waiting = self.execute("03_read_results.py", inputs)
        self.assertEqual(waiting["Values"], [])
        self.assertEqual(waiting["Names"], [])

    def test_runner_idle_and_failed_launch_have_no_results(self):
        script = self.root / "demo.m"
        script.write_text("s = 1;\n")
        inputs = dict(MatlabExe=str(self.root / "missing_matlab"), ScriptFile=str(script),
                      OutputNames=["s"], OutputFolder=str(self.root), Run=False,
                      Check=False, Cancel=False, TimeoutSeconds=600)
        initial = self.execute("02_run_matlab.py", inputs)
        self.assertFalse(initial["Done"])
        self.assertEqual(initial["ResultsFile"], "")
        inputs["Run"] = True
        failed = self.execute("02_run_matlab.py", inputs)
        self.assertFalse(failed["Done"])
        self.assertEqual(failed["ResultsFile"], "")
        self.assertIn("not found", failed["Status"])


if __name__ == "__main__":
    unittest.main()
