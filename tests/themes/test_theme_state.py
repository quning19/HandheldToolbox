from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from theme_converter.state import dependencies, fingerprint
from theme_converter.service import local_themes
from frontend_platforms.user_catalog import default_definitions, PlatformDefinition


class ThemeStateTests(unittest.TestCase):
    def test_empty_workspace_has_no_predefined_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(local_themes(Path(directory), default_definitions()), [])

    def test_inherited_addition_does_not_expire_results(self):
        definitions = default_definitions()
        extra = PlatformDefinition("gba-other", "Other", "Other", "gba", "inherit")
        self.assertEqual(dependencies(definitions), dependencies([*definitions, extra]))

    def test_separate_addition_or_badge_change_expires_results(self):
        definitions = default_definitions()
        extra = PlatformDefinition("gba-other", "Other", "Other", "gba", "separate", "OTHER")
        self.assertNotEqual(dependencies(definitions), dependencies([*definitions, extra]))
        edited = [replace(item, badge="NEW") if item.id == "GBA HACK" else item for item in definitions]
        self.assertNotEqual(dependencies(definitions), dependencies(edited))

    def test_content_fingerprint_covers_more_than_capabilities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            asset = source / "asset.png"
            asset.write_bytes(b"first")
            first, _ = fingerprint(source, root / "cache.json")
            asset.write_bytes(b"changed-content")
            second, _ = fingerprint(source, root / "cache.json")
            self.assertNotEqual(first, second)
