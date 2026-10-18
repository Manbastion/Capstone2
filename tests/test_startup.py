"""Startup guards can be checked without creating a Tk window."""
import contextlib
import io
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import Mock, patch

import main


class StartupTests(unittest.TestCase):
    def test_xcode_python_gets_actionable_advice_without_opening_tk(self):
        factory = Mock(side_effect=AssertionError('Tk must not be started'))
        with patch.object(sys, 'platform', 'darwin'), patch.object(sys, 'executable', '/Applications/Xcode.app/Contents/Developer/usr/bin/python3'), patch.dict(sys.modules, {'gui': SimpleNamespace(VariableTransferGUI=factory)}), contextlib.redirect_stderr(io.StringIO()) as output:
            self.assertEqual(main.main(), 2)
        factory.assert_not_called()
        self.assertIn('python.org', output.getvalue())

    def test_supported_interpreter_starts_the_existing_gui(self):
        app = Mock()
        with patch.object(sys, 'platform', 'linux'), patch.dict(sys.modules, {'gui': SimpleNamespace(VariableTransferGUI=lambda: app)}):
            self.assertEqual(main.main(), 0)
        app.mainloop.assert_called_once()
