from dataclasses import replace
import unittest
from frontend_platforms.user_catalog import PlatformDefinition as P, encode_overrides, merge_catalog


class CatalogUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.old = [P("gba", "GBA", "GBA"), P("gb", "GB", "GB")]

    def test_new_defaults_merge_while_user_fields_win(self):
        doc = encode_overrides([replace(self.old[0], name="我的 GBA"), self.old[1]], self.old)
        new = [replace(self.old[0], badge="NEW"), self.old[1], P("gbc", "GBC", "GBC")]
        result, _ = merge_catalog(doc, new)
        self.assertEqual(result[0].name, "我的 GBA")
        self.assertEqual(result[0].badge, "NEW")
        self.assertEqual(result[-1].id, "gbc")

    def test_disabled_default_stays_disabled(self):
        doc = encode_overrides([self.old[0]], self.old)
        rows, _ = merge_catalog(doc, self.old)
        self.assertEqual([row.id for row in rows], ["gba"])

    def test_custom_id_conflict_retains_user_and_reports(self):
        custom = P("future", "My future", "My future")
        doc = encode_overrides([*self.old, custom], self.old)
        rows, notices = merge_catalog(doc, [*self.old, P("future", "Default", "Future")])
        self.assertEqual(next(r.name for r in rows if r.id == "future"), "My future")
        self.assertTrue(notices)

    def test_custom_directory_conflict_retains_user_and_reports(self):
        doc = encode_overrides([*self.old, P("custom", "Custom", "Same")], self.old)
        rows, notices = merge_catalog(doc, [*self.old, P("future", "Default", "Same")])
        self.assertIn("custom", [row.id for row in rows])
        self.assertNotIn("future", [row.id for row in rows])
        self.assertTrue(notices)

    def test_retired_parent_is_retained(self):
        child = P("hack", "Hack", "Hack", "gba", "separate", "HACK")
        doc = encode_overrides([*self.old, child], self.old)
        rows, notices = merge_catalog(doc, [self.old[1]])
        self.assertIn("gba", [row.id for row in rows])
        self.assertTrue(notices)

    def test_invalid_graph_is_not_saved(self):
        with self.assertRaises(ValueError):
            encode_overrides([P("a", "A", "A", "b"), P("b", "B", "B", "a")], [])
