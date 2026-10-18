"""Boundary checks: async MATLAB export validation -> one notification."""
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import habsim_notifications as alerts
import test_runner

ROOT = Path(__file__).resolve().parents[1]
runner = test_runner.runner


@unittest.skipIf(os.name == "nt", "Process fixture is POSIX; Windows transport commands are tested separately.")
class RunnerNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = self.root / "simulation.m"
        self.script.write_text("success")
        self.exe = self.root / "fake-matlab"
        self.exe.write_text(test_runner.FAKE)
        self.exe.chmod(0o700)
        quiet = patch.dict(os.environ, {"HABSIM_NOTIFICATION_SETTINGS": str(self.root / 'settings.json')})
        quiet.start()
        self.addCleanup(quiet.stop)
        alerts.save_settings({"enabled": False})

    def start(self, mode="success", timeout=10):
        self.script.write_text(mode)
        job = runner.start_job(self.exe, self.script, ["t", "s", "a"], self.root, timeout)
        self.addCleanup(lambda: (runner.cancel_job(job), job["worker"].join(timeout=5)))
        return job

    def finish(self, job):
        job["worker"].join(timeout=5)
        self.assertFalse(job["worker"].is_alive())
        return runner.job_status(job)

    def test_success_notifies_after_validated_export_without_polling(self):
        def check(**kwargs):
            self.assertTrue(any(self.root.glob('capstone_run_*/results.csv')))
            self.assertTrue(kwargs["success"])
            self.assertEqual(kwargs["variable_count"], 3)
            return alerts.Delivery()
        with patch.object(runner, "notify_completion", side_effect=check) as notify:
            job = self.start()
            # No job_status/Check call until the monitor has already completed.
            job["worker"].join(timeout=5)
            notify.assert_called_once()
            self.assertEqual(runner.job_status(job)["state"], "Succeeded")
            for _ in range(3):
                runner.job_status(job)
            runner._finish(job, "Succeeded", "duplicate finish")
            notify.assert_called_once()

    def test_fail_timeout_and_invalid_export_emit_only_failure(self):
        for mode, expected, timeout in (("fail", "Failed", 10), ("slow", "Timed out", .2),
                                        ("no_marker", "Failed", 10), ("matrix", "Failed", 10)):
            with self.subTest(mode=mode), patch.object(runner, "notify_completion", return_value=alerts.Delivery()) as notify:
                job = self.start(mode, timeout)
                status = self.finish(job)
                self.assertEqual(status["state"], expected)
                self.assertEqual(status["results_file"], "")
                notify.assert_called_once()
                self.assertFalse(notify.call_args.kwargs["success"])

    def test_cancel_does_not_raise_failure_notification(self):
        with patch.object(runner, "notify_completion") as notify:
            job = self.start("slow")
            runner.cancel_job(job)
            self.assertEqual(self.finish(job)["state"], "Cancelled")
        notify.assert_not_called()

    def test_delivery_exception_cannot_change_successful_run(self):
        with patch.object(runner, "notify_completion", side_effect=RuntimeError("notifier failure")):
            status = self.finish(self.start())
        self.assertEqual(status["state"], "Succeeded")
        self.assertTrue(Path(status["results_file"]).exists())

    def test_loop_scope_suppresses_individual_matlab_alert(self):
        alerts.save_settings({"scope": "loop"})
        with patch.object(alerts, "_desktop") as desktop, patch.object(alerts, "_phone") as phone:
            job = self.start()
            self.finish(job)
        self.assertEqual(job["notification"].result["status"], "disabled")
        desktop.assert_not_called()
        phone.assert_not_called()

    def test_launch_failure_notifies_once_and_preserves_exception(self):
        with patch.object(runner, "notify_completion") as notify:
            with self.assertRaises(ValueError):
                runner.start_job(self.root / 'missing', self.script, ["s"], self.root)
        notify.assert_called_once()
        self.assertFalse(notify.call_args.kwargs["success"])


class LoopComponentTests(unittest.TestCase):
    def test_loop_component_ignores_initial_true_and_latches_recomputes(self):
        sc = ModuleType('scriptcontext')
        sc.sticky = {}
        kernel = ModuleType('Grasshopper.Kernel')
        kernel.GH_RuntimeMessageLevel = SimpleNamespace(Warning='Warning')
        messages = []
        env = {"Repo": str(ROOT), "Done": True, "Failed": False, "Enabled": True,
               "ghenv": SimpleNamespace(Component=SimpleNamespace(InstanceGuid='loop-test',
                    AddRuntimeMessage=lambda *args: messages.append(args)))}
        receipt = alerts.Delivery()
        receipt.queued = True
        receipt.result = {"status": "submitted", "channels": {"desktop": "submitted"}}
        script = compile((ROOT / '04_notify_loop_finished.py').read_text(), 'loop-component', 'exec')
        with patch.dict(sys.modules, {"scriptcontext": sc, "Grasshopper.Kernel": kernel}), patch.object(alerts, 'notify_completion', return_value=receipt) as notify:
            exec(script, env)
            notify.assert_not_called()
            env['Done'] = False
            exec(script, env)
            env['Done'] = True
            exec(script, env)
            self.assertTrue(env['Triggered'])
            for _ in range(3):
                exec(script, env)
                self.assertFalse(env['Triggered'])
            notify.assert_called_once()
            env['Done'], env['Failed'] = False, False
            exec(script, env)
            env['Failed'] = True
            exec(script, env)
            self.assertEqual(notify.call_count, 2)
            self.assertFalse(notify.call_args.kwargs['success'])
            self.assertEqual(notify.call_args.kwargs['scope'], 'loop')
        self.assertEqual(messages, [])


if __name__ == '__main__':
    unittest.main()
