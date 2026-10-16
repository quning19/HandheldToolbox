"""Parser semantics; small XML fixtures test grammar, not fabricated ROM data."""
from pathlib import Path
import tempfile
import unittest
from theme_converter.parser import ThemeParser
from retrolibx.errors import ValidationError


class GenericParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("capabilities.xml", '<themeCapabilities><themeName>Independent</themeName><colorScheme name="dark"/><colorScheme name="light"/></themeCapabilities>')

    def write(self, relative, content="asset"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def analyze(self, xml):
        self.write("theme.xml", xml)
        return ThemeParser(self.root).analyze("gba", "GBA hack", "GBA & Hack")

    def test_nested_variables_and_repeated_platform_tokens(self):
        self.write("art/gba/gba-clear.webp")
        result = self.analyze('<theme><variables><folder>./art/${system.theme}</folder><art>${folder}/${system.theme}-clear.webp</art></variables><view name="system"><image name="background"><path>${art}</path></image></view></theme>')
        self.assertEqual(list(result.resources), ["art/GBA hack/GBA hack-clear.webp"])
        self.assertEqual(result.errors, [])

    def test_color_branches_do_not_leak_into_each_other(self):
        for branch in ("dark", "light"):
            self.write(f"{branch}/gba.webp")
        xml = '<theme><colorScheme name="dark"><variables><art>./dark/${system.theme}.webp</art></variables></colorScheme><colorScheme name="light"><variables><art>./light/${system.theme}.webp</art></variables></colorScheme><view name="system"><image name="art"><path>${art}</path></image></view></theme>'
        result = self.analyze(xml)
        self.assertEqual(set(result.resources), {"dark/GBA hack.webp", "light/GBA hack.webp"})
        for resource in result.resources.values():
            self.assertEqual(resource.branch["colorScheme"], [resource.destination.parts[0]])

    def test_includes_are_relative_to_declaring_xml(self):
        self.write("inc/more.xml", '<theme><view name="system"><image name="art"><path>../art/${system.theme}.png</path></image></view></theme>')
        self.write("art/gba.png")
        result = self.analyze('<theme><include>./inc/more.xml</include></theme>')
        self.assertIn("art/GBA hack.png", result.resources)
        self.assertEqual(result.errors, [])

    def test_specific_art_takes_priority_and_is_not_rebadged(self):
        self.write("art/gba.png")
        self.write("art/GBA hack.png")
        result = self.analyze('<theme><view name="system"><image name="art"><path>./art/${system.theme}.png</path></image></view></theme>')
        self.assertEqual(result.resources, {})
        self.assertTrue(any(edge["type"] == "existing" for edge in result.edges))

    def test_metadata_xml_escapes_name_and_preserves_other_fields(self):
        self.write("metadata/gba.xml", '<theme><variables><systemName>GBA</systemName><manufacturer>Nintendo</manufacturer></variables></theme>')
        result = self.analyze('<theme><include>./metadata/${system.theme}.xml</include></theme>')
        xml = result.documents["metadata/GBA hack.xml"]
        self.assertIn("GBA &amp; Hack", xml)
        self.assertIn("Nintendo", xml)

    def test_shared_overlay_and_fonts_are_not_platform_art(self):
        self.write("overlay/gba.png")
        result = self.analyze('<theme><view name="system"><image name="background-overlay"><path>./overlay/${system.theme}.png</path></image></view></theme>')
        self.assertEqual(next(iter(result.resources.values())).role, "copy")

    def test_missing_explicit_include_and_unknown_resource_are_errors(self):
        result = self.analyze('<theme><include>./missing.xml</include><view name="system"><image name="art"><path>${undefined}</path></image></view></theme>')
        self.assertGreaterEqual(len(result.errors), 2)

    def test_include_cycle_and_traversal_are_rejected(self):
        self.write("loop.xml", '<theme><include>./theme.xml</include></theme>')
        for xml in ('<theme><include>./loop.xml</include></theme>', '<theme><include>../outside.xml</include></theme>'):
            with self.subTest(xml=xml), self.assertRaises(ValidationError):
                self.analyze(xml)

    def test_static_video_is_copied_without_transcoding(self):
        self.write("video/gba.mp4", "video-bytes")
        result = self.analyze('<theme><view name="system"><video name="system-video"><path>./video/${system.theme}.mp4</path></video></view></theme>')
        resource = result.resources["video/GBA hack.mp4"]
        self.assertEqual(resource.source.read_text(), "video-bytes")
        self.assertEqual(result.errors, [])
