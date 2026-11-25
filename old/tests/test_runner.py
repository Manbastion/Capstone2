"""Process tests use a fake executable; they do NOT validate MATLAB execution."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, REPO / "grasshopper_components" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner, bridge = load("matlab_runner"), load("bridge")

FAKE = '''#!/usr/bin/env python3
import json, sys, time
from pathlib import Path
request = json.loads(Path("request.json").read_text())
mode = Path(request["script_file"]).read_text().strip()
Path("received_args.json").write_text(json.dumps(sys.argv[1:]))
print("Fake process; no MATLAB was executed", flush=True)
if mode == "fail":
    print("Deliberate failure", flush=True)
    sys.exit(7)
if mode == "slow":
    time.sleep(30)
if mode == "no_marker":
    sys.exit(0)
values = {"t": [0, 5, 10, 15, 20], "s": [0, 85, 220, 405, 640], "a": 2}
data = {n: values.get(n, 1) for n in request["output_names"]}
if mode == "matrix":
    data[request["output_names"][0]] = [[1, 2], [3, 4]]
Path("results.json").write_text(json.dumps(data))
Path("completed.txt").write_text(request["job_id"])
'''


@unittest.skipIf(os.name == "nt", "Fake executable is a POSIX script; run real Windows smoke test separately.")
class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="capstone test ' ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / "fake matlab"
        self.exe.write_text(FAKE)
        self.exe.chmod(0o700)
        self.script = self.root / "simulation.m"
        self.script.write_text("success")

    def start(self, mode="success", timeout=10):
        self.script.write_text(mode)
        job = runner.start_job(self.exe, self.script, ["t", "s", "a"], self.root, timeout, notify=False)
        self.addCleanup(lambda: (runner.cancel_job(job), job["worker"].join(timeout=5)))
        return job

    def finished(self, job):
        job["worker"].join(timeout=5)
        self.assertFalse(job["worker"].is_alive())
        return runner.job_status(job)

    def test_success_and_json_csv_round_trip(self):
        job = self.start()
        status = self.finished(job)
        self.assertEqual(status["state"], "Succeeded", status)
        self.assertEqual(bridge.read_result(REPO, status["results_file"], "s")[1], [0, 85, 220, 405, 640])
        self.assertEqual(bridge.read_result(REPO, status["csv_file"], "s")[1], [0, 85, 220, 405, 640])
        self.assertEqual(bridge.read_result(REPO, status["csv_file"], "a")[1], [2])
        self.assertEqual(self.script.read_text(), "success")
        args = json.loads((job["directory"] / "received_args.json").read_text())
        self.assertEqual(args[:3], ["-sd", str(self.root.resolve()), "-batch"])
        self.assertIn("''", args[-1])  # Apostrophes in paths are escaped for MATLAB.

    def test_failure_propagates_exit_code_and_log(self):
        status = self.finished(self.start("fail"))
        self.assertEqual(status["state"], "Failed")
        self.assertEqual(status["return_code"], 7)
        self.assertEqual(status["results_file"], "")
        self.assertIn("Deliberate failure", Path(status["log_file"]).read_text())

    def test_zero_exit_without_export_is_not_success(self):
        status = self.finished(self.start("no_marker"))
        self.assertEqual(status["state"], "Failed")
        self.assertIn("completion marker", status["message"])

    def test_old_results_not_reused_after_failed_run(self):
        first = self.start()
        first_status = self.finished(first)
        second = self.start("fail")
        second_status = self.finished(second)
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertTrue(Path(first_status["results_file"]).exists())
        self.assertEqual(second_status["results_file"], "")

    def test_matrices_rejected(self):
        status = self.finished(self.start("matrix"))
        self.assertEqual(status["state"], "Failed")
        self.assertEqual(status["csv_file"], "")

    def test_timeout_stops_process(self):
        job = self.start("slow", timeout=.2)
        self.assertEqual(self.finished(job)["state"], "Timed out")
        self.assertIsNotNone(job["process"].poll())

    def test_cancel_stops_process(self):
        job = self.start("slow")
        runner.cancel_job(job)
        self.assertEqual(self.finished(job)["state"], "Cancelled")
        self.assertIsNotNone(job["process"].poll())

    def test_invalid_names_and_p_file_rejected_before_launch(self):
        with self.assertRaises(ValueError):
            runner.start_job(self.exe, self.script, ["x);system('oops')"], self.root, notify=False)
        self.script.with_suffix(".p").write_text("placeholder")
        with self.assertRaises(ValueError):
            runner.start_job(self.exe, self.script, ["x"], self.root, notify=False)
        self.assertEqual(list(self.root.glob("capstone_run_*")), [])

    def test_source_change_invalidates_signature(self):
        job = self.start()
        self.finished(job)
        self.script.write_text("changed")
        self.assertNotEqual(job["signature"], runner.request_signature(
            self.exe, self.script, ["t", "s", "a"], self.root, 10))


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_input_csv_transfer_uses_existing_backend(self):
        source, destination = self.root / "input.csv", self.root / "demo.m"
        source.write_text("name,value\nv0,12\na,2\n")
        destination.write_text("v0 = 0;\na = 1;\nv = v0 + a*t;\n")
        bridge.transfer(REPO, source, destination, ["v0", "a"], ["v0", "a"], apply=True)
        self.assertIn("v0 = 12;", destination.read_text())
        self.assertIn("v = v0 + a*t;", destination.read_text())

    def test_result_csv_internal_blanks_rejected(self):
        path = self.root / "results.csv"
        path.write_text("t,s\n0,1\n1,\n2,3\n")
        with self.assertRaises(ValueError):
            bridge.read_result(REPO, path, "s")

    def test_ambiguous_input_csv_rejected_without_write(self):
        path, dest = self.root / "bad.csv", self.root / "demo.m"
        path.write_text("v0,a\n12,2\n")
        dest.write_text("v0 = 0;\n")
        with self.assertRaises(ValueError):
            bridge.transfer(REPO, path, dest, ["v0"], ["v0"], apply=True)
        self.assertEqual(dest.read_text(), "v0 = 0;\n")


if __name__ == "__main__":
    unittest.main()
