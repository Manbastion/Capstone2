"""Notification transports are mocked except the explicitly local HTTPS test.

No real OS alerts, external ntfy requests, or phone messages are emitted.
"""
import base64
import contextlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock, patch
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import habsim_notifications as alerts


class NotificationFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings_file = self.root / "settings.json"
        env = patch.dict(os.environ, {"HABSIM_NOTIFICATION_SETTINGS": str(self.settings_file), "HABSIM_NTFY_TOKEN": ""})
        env.start()
        self.addCleanup(env.stop)

    def settings(self, **changes):
        return {**alerts.DEFAULTS, **changes}

    def response(self, body=None, status=200):
        response = Mock(status=status)
        response.read.return_value = json.dumps(body or {"id": "receipt123", "event": "message", "topic": "test"}).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response


class SettingsAndDeliveryTests(NotificationFixture):
    def test_atomic_settings_round_trip_never_saves_token(self):
        values = self.settings(phone=True, topic="test", scope="loop")
        alerts.save_settings({**values, "token": "not-for-disk"})
        self.assertEqual(alerts.load_settings(), values)
        self.assertNotIn("not-for-disk", self.settings_file.read_text())
        self.assertEqual(list(self.root.glob('.notification-*')), [])

    def test_validate_phone_address_and_topic(self):
        for server in ("http://ntfy.sh", "https://user:password@ntfy.sh", "https://ntfy.sh/topic", "https://ntfy.sh?token=x", "https://ntfy.sh:bad"):
            with self.subTest(server=server), self.assertRaises(ValueError):
                alerts.validate_settings(self.settings(phone=True, topic="test", server=server))
        for topic in ("", "two topics", "test\nAuthorization: bad", "x"*65):
            with self.subTest(topic=topic), self.assertRaises(ValueError):
                alerts.validate_settings(self.settings(phone=True, topic=topic))
        self.assertEqual(alerts.validate_settings(self.settings(phone=True, topic="test", server="https://ntfy.example:8443/"))["server"], "https://ntfy.example:8443")

    def test_settings_failure_is_visible_without_attempting_delivery(self):
        self.settings_file.write_text('{broken')
        with patch.object(alerts, "_desktop") as desktop, patch.object(alerts, "_phone") as phone:
            receipt = alerts.notify_completion()
        self.assertEqual(receipt.result["status"], "delivery issue")
        self.assertIn("valid JSON", receipt.result["channels"]["settings"])
        desktop.assert_not_called()
        phone.assert_not_called()

    def test_filters_never_send_and_explain_why(self):
        with patch.object(alerts, "_desktop") as desktop, patch.object(alerts, "_phone") as phone:
            for config, outcome in ((self.settings(enabled=False), True), (self.settings(scope="loop"), True),
                                    (self.settings(failures=False), False), (self.settings(desktop=False), True)):
                result = alerts.notify_completion(success=outcome, settings=config).result
                self.assertEqual(result["status"], "disabled")
                self.assertTrue(result["reason"])
            desktop.assert_not_called()
            phone.assert_not_called()

    def test_channel_test_is_independent_and_honours_opt_in(self):
        with patch.object(alerts, "_desktop") as desktop, patch.object(alerts, "_phone") as phone:
            receipt = alerts.notify_completion(scope="test", settings=self.settings(), only_channel="phone")
            self.assertEqual(receipt.result["status"], "disabled")
            receipt = alerts.notify_completion(scope="test", settings=self.settings(phone=True, topic="test"), only_channel="desktop")
            self.assertEqual(receipt.wait(2)["status"], "submitted")
            desktop.assert_called_once()
            phone.assert_not_called()

    def test_delivery_does_not_wait_for_popup_and_phone_runs_in_parallel(self):
        entered, release, phone_called = threading.Event(), threading.Event(), threading.Event()
        def slow_desktop(*args):
            entered.set()
            release.wait(2)
        with patch.object(alerts, "_desktop", side_effect=slow_desktop), patch.object(alerts, "_phone", side_effect=lambda *args: phone_called.set()):
            receipt = alerts.notify_completion(settings=self.settings(phone=True, topic="test"))
            try:
                self.assertTrue(entered.wait(1))
                self.assertTrue(phone_called.wait(1))
                self.assertFalse(receipt.done.is_set())
                self.assertTrue(receipt.queued)
            finally:
                release.set()
                self.assertEqual(receipt.wait(2)["status"], "submitted")

    def test_partial_failure_is_recorded_without_private_exception_text(self):
        with patch.object(alerts, "_desktop", side_effect=OSError("private model path")), patch.object(alerts, "_phone", return_value={"message_id": "receipt123", "attempts": 1}):
            result = alerts.notify_completion(settings=self.settings(phone=True, topic="test")).wait(2)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["channels"]["phone"], "submitted")
        log = self.settings_file.with_name("notifications.log").read_text()
        self.assertNotIn("private model path", log)
        self.assertNotIn('"topic"', log)
        self.assertEqual(result["details"]["phone"]["message_id"], "receipt123")

    def test_notification_content_and_invalid_duration(self):
        title, body = alerts.notification_text(True, "run", 3661, 3)
        self.assertIn("complete", title)
        self.assertIn("1h 1m 1s", body)
        self.assertIn("3 result variable(s) exported", body)
        self.assertIn("needs attention", alerts.notification_text(False, "loop", 1)[0])
        for value in (float("nan"), -1, "private text"):
            with self.assertRaises(ValueError):
                alerts.notification_text(True, "run", value)
        with self.assertRaises(ValueError):
            alerts.notification_text(True, "run", 1, -1)

    def test_mac_text_is_passed_as_data(self):
        title = '"; do shell script "unexpected"'
        with patch.object(alerts.sys, "platform", "darwin"), patch.object(alerts.subprocess, "run") as run:
            alerts._desktop(title, "body", False)
        argv = run.call_args.args[0]
        self.assertNotIn(title, argv[2])
        self.assertEqual(argv[-3:], [title, "body", "no"])
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_windows_popup_is_quoted_and_bounded(self):
        title = "'; $(unexpected); Unicode ✓"
        with patch.object(alerts.sys, "platform", "win32"), patch.object(alerts.subprocess, "run") as run:
            alerts._desktop(title, "body", True)
        argv = run.call_args.args[0]
        script = base64.b64decode(argv[-1]).decode("utf-16-le")
        self.assertNotIn(title, script)
        self.assertIn("15, $p[0]", script)
        self.assertNotIn("ExecutionPolicy", " ".join(argv))
        self.assertEqual(run.call_args.kwargs["timeout"], 25)

    def test_diagnostics_and_disabled_cli_never_send(self):
        alerts.save_settings(self.settings(enabled=False))
        with patch.object(alerts, "_desktop") as desktop, patch.object(alerts, "_phone") as phone, contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(alerts.main(["--check"]), 0)
            self.assertEqual(alerts.main(["--test"]), 2)
        self.assertNotIn("Authorization", output.getvalue())
        desktop.assert_not_called()
        phone.assert_not_called()

    def test_gate_ignores_saved_true_then_fires_once_per_run(self):
        state = {}
        self.assertIsNone(alerts.completion_transition(state, True))
        alerts.completion_transition(state, False)
        self.assertEqual(alerts.completion_transition(state, True), "success")
        for _ in range(3):
            self.assertIsNone(alerts.completion_transition(state, True))
        alerts.completion_transition(state, False)
        self.assertEqual(alerts.completion_transition(state, True, True), "failure")


class PhoneTransportTests(NotificationFixture):
    def test_real_request_shape_and_receipt_validation(self):
        opener = Mock()
        opener.open.return_value = self.response()
        with patch.object(alerts.request, "build_opener", return_value=opener), patch.dict(os.environ, {"HABSIM_NTFY_TOKEN": "private-token"}):
            receipt = alerts._phone("title", "message", self.settings(phone=True, topic="test"))
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, "https://ntfy.sh/")
        self.assertEqual(req.get_header("Authorization"), "Bearer private-token")
        self.assertEqual(json.loads(req.data)["topic"], "test")
        self.assertEqual(receipt, {"attempts": 1, "message_id": "receipt123"})

    def test_success_http_with_wrong_body_is_not_reported_as_delivery(self):
        for body in ({"id": "id", "event": "message", "topic": "wrong"}, {"error": "private response"}):
            opener = Mock()
            opener.open.return_value = self.response(body)
            with patch.object(alerts.request, "build_opener", return_value=opener), self.assertRaises(alerts.NotificationError):
                alerts._phone("title", "body", self.settings(phone=True, topic="test"))

    def test_auth_rejection_not_retried_and_message_is_safe(self):
        opener = Mock()
        opener.open.side_effect = error.HTTPError("private URL", 403, "private body", {}, None)
        with patch.object(alerts.request, "build_opener", return_value=opener):
            with self.assertRaises(error.HTTPError) as caught:
                alerts._phone("title", "body", self.settings(phone=True, topic="test"))
        self.assertEqual(opener.open.call_count, 1)
        self.assertIn("permissions", alerts._error_message(caught.exception))
        self.assertNotIn("private", alerts._error_message(caught.exception))

    def test_transient_rejection_retries_with_bounded_delay(self):
        opener = Mock()
        opener.open.side_effect = [error.HTTPError("", 429, "", {"Retry-After": "1"}, None), self.response()]
        with patch.object(alerts.request, "build_opener", return_value=opener), patch.object(alerts.time, "sleep") as sleep:
            result = alerts._phone("title", "body", self.settings(phone=True, topic="test"))
        self.assertEqual(result["attempts"], 2)
        sleep.assert_called_once_with(1.0)

    def test_long_retry_after_and_connection_loss_not_retried(self):
        for exc in (error.HTTPError("", 429, "", {"Retry-After": "60"}, None), error.URLError("ambiguous acceptance")):
            opener = Mock()
            opener.open.side_effect = exc
            with patch.object(alerts.request, "build_opener", return_value=opener), self.assertRaises(type(exc)):
                alerts._phone("title", "body", self.settings(phone=True, topic="test"))
            self.assertEqual(opener.open.call_count, 1)

    def test_retry_exhaustion_is_bounded(self):
        opener = Mock()
        opener.open.side_effect = error.HTTPError("", 503, "", {}, None)
        with patch.object(alerts.request, "build_opener", return_value=opener), patch.object(alerts.time, "sleep") as sleep:
            with self.assertRaises(error.HTTPError):
                alerts._phone("title", "body", self.settings(phone=True, topic="test"))
        self.assertEqual(opener.open.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_redirects_are_refused(self):
        self.assertIsNone(alerts._NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.example"))

    @unittest.skipUnless(shutil.which("openssl"), "Local TLS fixture generation needs openssl")
    def test_local_https_publish_with_real_http_stack(self):
        # Test-only local CA; production verification is neither disabled nor changed.
        key, cert = self.root / "key.pem", self.root / "cert.pem"
        subprocess.run([shutil.which("openssl"), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost"], check=True, capture_output=True)
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))), self.headers.get("Authorization")))
                body = json.dumps({"id": "localReceipt", "event": "message", "topic": "test"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            trusted = ssl.create_default_context(cafile=str(cert))
            opener = request.build_opener(alerts._NoRedirect(), request.HTTPSHandler(context=trusted), request.ProxyHandler({}))
            config = self.settings(desktop=False, phone=True, topic="test", server="https://localhost:%s" % server.server_port)
            with patch.object(alerts.request, "build_opener", return_value=opener), patch.dict(os.environ, {"HABSIM_NTFY_TOKEN": "local-test-token"}):
                result = alerts.notify_completion(settings=config, scope="test").wait(5)
            self.assertEqual(result["status"], "submitted", result)
            self.assertEqual(received[0][0], "/")
            self.assertEqual(received[0][1]["topic"], "test")
            self.assertEqual(received[0][2], "Bearer local-test-token")
            self.assertEqual(result["details"]["phone"]["message_id"], "localReceipt")
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
