"""Headless entry points and module dependency direction."""
import subprocess
import sys
import unittest


class IndependentEntryTests(unittest.TestCase):
    def test_library_cli_help(self):
        completed = subprocess.run([sys.executable, "-m", "library_converter", "--help"], capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))

    def test_theme_cli_help(self):
        completed = subprocess.run([sys.executable, "-m", "theme_converter", "--help"], capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))

    def test_tools_import_without_qt_or_each_other(self):
        code = '''
import builtins, sys
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(("PySide6", "qfluentwidgets", "frontend_gui")):
        raise ImportError("GUI dependency reached from headless tool: " + name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import library_converter.desktop
assert "theme_converter.service" not in sys.modules
import theme_converter.service
'''
        completed = subprocess.run([sys.executable, "-c", code], capture_output=True)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", errors="replace"))
