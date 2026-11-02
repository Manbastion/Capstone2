"""Portable integration tests; mock MATLAB and notification delivery, not file IO."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from grasshopper_components import matlab_runner as runner
import habsim_client as client
import habsim_runtime as runtime
from habsim_prototype import load_prototype

REPO = Path(__file__).resolve().parents[1]


class WorkspaceRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="HabSim user's model ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.exe = self.root / "matlab.exe"
        self.exe.touch()
        self.script = self.root / "model.m"
        self.script.write_text("s = struct('values', [1,2]);", encoding="utf-8")

    def run_fake(self, payload, marker=True, code=0):
        def launch(command, **kwargs):
            folder = Path(kwargs["cwd"])
            request = json.loads((folder / "request.json").read_text())
            (folder / "results.json").write_text(payload, encoding="utf-8")
            if marker:
                (folder / "completed.txt").write_text(request["job_id"])
            process = Mock(returncode=code)
            process.poll.return_value = code
            return process
        with patch.object(runner.subprocess, "Popen", side_effect=launch) as popen:
            job = runner.start_job(self.exe, self.script, [], self.root,
                                   notify=False, export_mode="workspace")
            job["worker"].join(5)
            self.assertFalse(job["worker"].is_alive())
        return job, runner.job_status(job), popen.call_args

    def test_nested_workspace_and_fresh_export_without_numeric_csv(self):
        content = {"s": {"values": [[1, 2], [3, 4]], "label": "test", "valid": True}}
        before = self.script.read_bytes()
        job, status, call = self.run_fake(json.dumps(content))
        self.assertEqual(status["state"], "Succeeded", status)
        self.assertEqual(json.loads(Path(status["results_file"]).read_text()), content)
        self.assertEqual(status["csv_file"], "")
        self.assertFalse((job["directory"] / "results.csv").exists())
        self.assertEqual(self.script.read_bytes(), before)
        wrapper = (job["directory"] / "capstone_job_entry.m").read_text()
        self.assertIn("names = evalin('base', 'who');", wrapper)
        self.assertNotIn("isnumeric(value)", wrapper)
        self.assertIn("user''''s", wrapper)
        self.assertIn("env", call.kwargs)

    def test_workspace_failure_never_exposes_an_old_result(self):
        first, status, _ = self.run_fake('{"x": 5}')
        self.assertEqual(status["state"], "Succeeded")
        second, status, _ = self.run_fake('{"x": 9}', marker=False)
        self.assertNotEqual(first["directory"], second["directory"])
        self.assertEqual(status["state"], "Failed")
        self.assertEqual(status["results_file"], "")

    def test_invalid_workspace_exports_fail(self):
        for payload in ('[]', '{"x":NaN}', '{"x":1,"x":2}', 'not json'):
            with self.subTest(payload=payload):
                _, status, _ = self.run_fake(payload)
                self.assertEqual(status["state"], "Failed")
                self.assertEqual(status["results_file"], "")


class ClientPreferencesTests(unittest.TestCase):
    def test_preferences_persist_outside_the_program_folder(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                "HABSIM_NOTIFICATION_SETTINGS": str(Path(temp) / "settings.json")}):
            values = {"matlab": "chosen program", "script": "chosen script", "output": "chosen folder", "minutes": "30"}
            client.save_client_settings(values)
            self.assertEqual(client.load_client_settings(), values)
            self.assertEqual(client.client_settings_path().parent, Path(temp))
            client.client_settings_path().write_text('{"matlab": false}')
            with self.assertRaises(ValueError):
                client.load_client_settings()

    def test_external_tools_do_not_inherit_rhino_python_environment(self):
        with patch.dict(os.environ, {"PYTHONHOME": "rhino", "PYTHONPATH": "rhino",
                                     "HABSIM_NOTIFICATION_SETTINGS": "keep-this"}):
            env = runtime.external_environment()
            self.assertNotIn("PYTHONHOME", env)
            self.assertNotIn("PYTHONPATH", env)
            self.assertEqual(env["HABSIM_NOTIFICATION_SETTINGS"], "keep-this")
            self.assertEqual(os.environ["PYTHONHOME"], "rhino")

    def test_frozen_external_tools_restore_original_library_path(self):
        with patch.object(sys, "frozen", True, create=True), patch.dict(os.environ, {
                "LD_LIBRARY_PATH": "/bundle", "LD_LIBRARY_PATH_ORIG": "/system"}):
            self.assertEqual(runtime.external_environment()["LD_LIBRARY_PATH"], "/system")

    def test_windows_matlab_discovery_without_path(self):
        with tempfile.TemporaryDirectory() as temp:
            expected = Path(temp) / "MATLAB/R2026b/bin/matlab.exe"
            expected.parent.mkdir(parents=True)
            expected.touch()
            with patch.object(sys, "platform", "win32"), patch.object(shutil, "which", return_value=None), patch.dict(os.environ, {
                    "ProgramFiles": temp, "ProgramW6432": temp}):
                self.assertEqual(runtime.find_matlab(), str(expected))

    @unittest.skipUnless(os.name == "nt", "The .bat launcher needs Windows CMD and a desktop.")
    def test_windows_source_launcher_opens_the_gui_with_no_alerts(self):
        with tempfile.TemporaryDirectory(prefix="HabSim startup ") as temp:
            report = Path(temp) / "gui check.json"
            env = dict(os.environ, HABSIM_NOTIFICATION_SETTINGS=str(Path(temp) / "settings.json"))
            result = subprocess.run(["cmd.exe", "/d", "/c", str(REPO / "Launch_HabSim.bat"),
                                     "--self-test", str(report)], cwd=REPO, env=env,
                                    capture_output=True, text=True, timeout=45)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(report.read_text())
            self.assertEqual(data["status"], "passed")
            self.assertFalse(data["notifications_sent"])


class PrototypeCompatibilityTests(unittest.TestCase):
    def test_imports_from_renamed_download_with_spaces_do_not_use_legacy_modules(self):
        with tempfile.TemporaryDirectory(prefix="client download ") as temp:
            root = Path(temp)
            folder = root / "prototype4 - (current version)"
            folder.mkdir()
            for path in (REPO / folder.name).glob("*.py"):
                shutil.copy2(path, folder / path.name)
            shutil.copy2(REPO / "habsim_prototype.py", root)
            code = """import sys, types
sys.modules['variable_transfer_v2'] = types.ModuleType('legacy_decoy')
from habsim_prototype import load_prototype
bridge = load_prototype('gh_bridge')
assert bridge.variable_transfer_v2.__name__ == 'habsim_prototype4.variable_transfer_v2'
assert load_prototype('gui').VariableTransferGUI
assert load_prototype('gh_gui').GrasshopperTransferGUI
assert load_prototype('main').main
"""
            result = subprocess.run([sys.executable, "-E", "-c", code], cwd=root,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_old_output_modified_just_before_launch_is_not_ready(self):
        bridge = load_prototype("gh_bridge")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "matlab_output_variables.json"
            path.write_text('{"old":1}')
            run = bridge.ScriptRun.__new__(bridge.ScriptRun)
            run.output_file = str(path)
            run.started = path.stat().st_mtime
            run.previous_output = run._output_stamp()
            self.assertFalse(run.output_ready)
            path.write_text('{"new": 1234567}')
            self.assertTrue(run.output_ready)

    def test_prototype_fresh_export_is_published_and_notified_once(self):
        module = load_prototype("run_matlab_import_python_v2")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            script = root / "model.m"
            script.write_bytes(b"x = 12;\r\n")
            exe = root / "matlab.exe"
            exe.touch()
            destination = root / "matlab_output_variables.json"
            destination.write_text('{"old":1}')
            receipt = Mock(result={"status": "submitted"})

            def finish(command, **kwargs):
                folder = next(root.glob("habsim_run_*"))
                (folder / destination.name).write_text('{"x":12}')

            with patch.object(module.subprocess, "run", side_effect=finish), patch.object(module, "notify_completion", return_value=receipt) as notify:
                self.assertEqual(module.full_run(script, "json", exe), str(destination))
                self.assertEqual(json.loads(destination.read_text()), {"x": 12})
                self.assertEqual(script.read_bytes(), b"x = 12;\r\n")
                notify.assert_called_once()
                self.assertTrue(notify.call_args.kwargs["success"])
                receipt.wait.assert_called_once_with(45)

    def test_prototype_failed_process_preserves_old_export_without_success_alert(self):
        module = load_prototype("run_matlab_import_python_v2")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script, exe = root / "model.m", root / "matlab.exe"
            script.write_text("error('test')")
            exe.touch()
            destination = root / "matlab_output_variables.json"
            destination.write_text('{"old":1}')
            receipt = Mock(result={"status": "submitted"})
            with patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(7, "fake")), patch.object(module, "notify_completion", return_value=receipt) as notify:
                with self.assertRaises(subprocess.CalledProcessError):
                    module.full_run(script, "json", exe)
                self.assertEqual(json.loads(destination.read_text()), {"old": 1})
                notify.assert_called_once()
                self.assertFalse(notify.call_args.kwargs["success"])


if __name__ == "__main__":
    unittest.main()
