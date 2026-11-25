"""Exercise existing runners and batch transitions; send no real notifications."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import Capstone2.old.habsim_completion as hook
import Capstone2.old.habsim_notifications as alerts

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = [ROOT / 'prototype4', ROOT / 'prototype5',
           ROOT / 'grasshopper_integration_multirun/grasshopper_integration']


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SimpleNotificationTests(unittest.TestCase):
    def setUp(self):
        self.receipt = Mock()
        self.notify = patch.object(hook, 'notify_completion', return_value=self.receipt).start()
        self.addCleanup(patch.stopall)

    def test_success_preserves_return_and_waits_for_cli_delivery(self):
        wrapped = hook.notify_run(lambda: 0)
        self.assertEqual(wrapped(), 0)
        self.assertTrue(self.notify.call_args.kwargs['success'])
        self.receipt.wait.assert_called_once_with(45)

    def test_return_failure_and_exception_notify_once(self):
        self.assertEqual(hook.notify_run(lambda: 7)(), 7)
        self.assertFalse(self.notify.call_args.kwargs['success'])
        self.notify.reset_mock()
        def fail():
            raise OSError('runner failed')
        with self.assertRaises(OSError):
            hook.notify_run(fail)()
        self.notify.assert_called_once()
        self.assertFalse(self.notify.call_args.kwargs['success'])

    def test_interruption_is_not_a_failure_alert(self):
        def stop():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            hook.notify_run(stop)()
        self.notify.assert_not_called()

    def test_delivery_exception_does_not_change_result(self):
        self.notify.side_effect = RuntimeError('unavailable')
        self.assertEqual(hook.notify_run(lambda: 0)(), 0)

    def test_all_three_actual_runners_report_marker_success(self):
        for index, folder in enumerate(FOLDERS):
            with self.subTest(folder=folder), tempfile.TemporaryDirectory() as temp:
                self.notify.reset_mock()
                module = load(folder / 'run_matlab_import_python_v2.py', 'simple_runner_' + str(index))
                model = Path(temp) / 'model.m'
                model.write_text('x=1;')
                def spawn(*args, **kwargs):
                    (Path(temp) / module.MARKER_NAME).write_text('0')
                    return Mock(returncode=0, poll=Mock(return_value=0), wait=Mock(return_value=0))
                with patch.object(module.subprocess, 'Popen', side_effect=spawn):
                    self.assertEqual(module.full_run(str(model)), 0)
                self.notify.assert_called_once()
                self.assertTrue(self.notify.call_args.kwargs['success'])
                self.assertEqual(model.read_text(), 'x=1;')

    def test_missing_matlab_is_a_failure_alert(self):
        module = load(FOLDERS[1] / 'run_matlab_import_python_v2.py', 'simple_missing')
        with tempfile.TemporaryDirectory() as temp, patch.object(module.subprocess, 'Popen', side_effect=FileNotFoundError()):
            self.assertEqual(module.full_run(str(Path(temp) / 'model.m')), 1)
        self.notify.assert_called_once()
        self.assertFalse(self.notify.call_args.kwargs['success'])

    def test_missing_marker_does_not_send_false_success(self):
        module = load(FOLDERS[1] / 'run_matlab_import_python_v2.py', 'simple_no_marker')
        process = Mock(returncode=0, poll=Mock(return_value=0), wait=Mock(return_value=0))
        with tempfile.TemporaryDirectory() as temp, patch.object(module.subprocess, 'Popen', return_value=process):
            self.assertEqual(module.full_run(str(Path(temp) / 'model.m')), 1)
        self.assertFalse(self.notify.call_args.kwargs['success'])

    def test_nonzero_process_exit_overrules_success_marker(self):
        module = load(FOLDERS[1] / 'run_matlab_import_python_v2.py', 'simple_bad_exit')
        with tempfile.TemporaryDirectory() as temp:
            def spawn(*args, **kwargs):
                (Path(temp) / module.MARKER_NAME).write_text('0')
                return Mock(returncode=8, poll=Mock(return_value=8), wait=Mock(return_value=8))
            with patch.object(module.subprocess, 'Popen', side_effect=spawn):
                self.assertEqual(module.full_run(str(Path(temp) / 'model.m')), 8)
        self.assertFalse(self.notify.call_args.kwargs['success'])

    def test_batch_only_notifies_on_final_completion_once(self):
        module = load(FOLDERS[2] / 'multirun.py', 'simple_batch')
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'batch.json')
            module.save_state({'status':'running','index':0,'iteration_done':False,
                               'iterations':[{'x':1},{'x':2}]}, path)
            module.finish_iteration(0, path)
            self.notify.assert_not_called()
            module.finish_iteration(0, path)
            self.notify.assert_called_once()
            self.assertEqual(self.notify.call_args.kwargs['scope'], 'loop')
            module.finish_iteration(0, path)
            self.notify.assert_called_once()

    def test_batch_failure_transfer_failure_and_stop(self):
        module = load(FOLDERS[2] / 'multirun.py', 'simple_batch_fail')
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / 'batch.json')
            for mode in ('matlab_error', 'transfer_error', 'stop'):
                self.notify.reset_mock()
                module.save_state({'status':'running','index':0,'iteration_done':False,
                                   'iterations':[{'x':1}]}, path)
                if mode == 'transfer_error':
                    module.fail_transfer(ValueError('bad input'), path)
                    module.fail_transfer(ValueError('repeat'), path)
                elif mode == 'stop':
                    module.request_stop(path)
                    module.finish_iteration(0, path)
                else:
                    module.finish_iteration(1, path)
                    module.finish_iteration(1, path)
                if mode == 'stop':
                    self.notify.assert_not_called()
                else:
                    self.notify.assert_called_once()
                    self.assertFalse(self.notify.call_args.kwargs['success'])

    def test_real_scope_filters_prevent_duplicate_run_and_loop_alerts(self):
        # Re-enable the real dispatcher but keep both OS/network transports mocked.
        self.notify.side_effect = alerts.notify_completion
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {
                'HABSIM_NOTIFICATION_SETTINGS':str(Path(temp)/'settings.json')}), patch.object(alerts, '_desktop') as desktop, patch.object(alerts, '_phone') as phone:
            alerts.save_settings({**alerts.DEFAULTS, 'scope':'loop'})
            hook.notify_run(lambda: 0)()
            desktop.assert_not_called()
            receipt = hook.notify_batch({'status':'complete'})
            receipt.wait(5)
            desktop.assert_called_once()
            phone.assert_not_called()


if __name__ == '__main__':
    unittest.main()
