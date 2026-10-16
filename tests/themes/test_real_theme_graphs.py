"""Seven migrated originals are local read-only parser acceptance fixtures."""
from pathlib import Path
import unittest
from frontend_platforms.user_catalog import default_definitions
from theme_converter.parser import ThemeParser
from theme_converter.state import bindings

ROOT = Path(__file__).resolve().parents[2] / "test_data/themes/original"


class RealThemeGraphTests(unittest.TestCase):
    def check_theme(self, directory):
        source = ROOT / directory
        if not source.is_dir():
            self.skipTest("真实主题未导入：" + str(source))
        parser = ThemeParser(source)
        for binding in bindings(default_definitions()):
            with self.subTest(platform=binding.id):
                result = parser.analyze(binding.mother, binding.target, binding.name, binding.source_name, binding.id, binding.source_fullname)
                self.assertEqual(result.errors, [])
                self.assertTrue(result.resources or result.edges, "必须有已存在资源或继承引用")

    def test_canvas(self):
        self.check_theme("canvas-es-de")

    def test_aura(self):
        self.check_theme("aura-es-de")

    def test_alekfull_nx(self):
        self.check_theme("alekfull-nx-es-de")

    def test_elementerial(self):
        self.check_theme("elementerial-es-de")

    def test_iconic(self):
        self.check_theme("iconic-es-de")

    def test_iisu(self):
        self.check_theme("iisu-interpreted-es-de")

    def test_playstation_x(self):
        self.check_theme("playstation-x-es-de")
