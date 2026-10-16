import json
import pathlib
import sys
import unittest
import xml.etree.ElementTree as ET


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/themes"))

from common import batch as load_batch, platform_registry
from package import theme_name  # noqa: E402
from build import badge_params_for, find_directory_source  # noqa: E402
from validate import validate  # noqa: E402


def load_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class ThemeBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.project = load_json("tools/themes/config/project.json")
        cls.alekfull_nx = load_json("tools/themes/config/themes/alekfull-nx.json")
        cls.aura = load_json("tools/themes/config/themes/aura.json")
        cls.canvas = load_json("tools/themes/config/themes/canvas.json")
        cls.elementerial = load_json("tools/themes/config/themes/elementerial.json")
        cls.iconic = load_json("tools/themes/config/themes/iconic.json")
        cls.iisu = load_json("tools/themes/config/themes/iisu.json")
        cls.playstation_x = load_json("tools/themes/config/themes/playstation-x.json")
        cls.canvas_batch = load_batch("batch1")
        cls.alekfull_nx_batch = load_batch("alekfull-nx-batch1")
        cls.aura_batch = load_batch("aura-batch1")
        cls.elementerial_batch = load_batch("elementerial-batch1")
        cls.iconic_batch = load_batch("iconic-batch1")
        cls.iisu_batch = load_batch("iisu-batch1")
        cls.playstation_x_batch = load_batch("playstation-x-batch1")
        cls.systems = ET.parse(ROOT / cls.project["paths"]["system_config"]).getroot()

    def test_shared_platform_rules_preserve_tested_names(self):
        registry = platform_registry()
        self.assertEqual(len(registry.records), 76)
        for name in self.project["theme_profiles"]:
            filename = "batch1" if name == "canvas" else name + "-batch1"
            raw = load_json("tools/themes/config/batches/" + filename + ".json")
            for item in raw["platforms"]:
                for key in ("theme", "source", "badge_text", "system_name"):
                    self.assertNotIn(key, item)
        self.assertTrue(registry.is_hack("GBA hack"))
        self.assertEqual(registry.resolve("GBA hack")["name"], "GBA HACK")
        self.assertEqual(registry.resolve("GBA vib")["rom_directory"], "GBA vib")

    def test_canvas_platform_set(self):
        names = [item["name"] for item in self.canvas_batch["platforms"]]
        self.assertEqual(
            names,
            ["FC-HD", "SFC hack", "SFC-MSU1", "PS1 hack", "PS2 hack",
             "nesh", "GBA HACK", "GBA vib", "WII Ware"],
        )
        self.assertNotIn("WII", names)

    def test_iconic_platform_set_keeps_existing_nesh_untouched(self):
        names = [item["name"] for item in self.iconic_batch["platforms"]]
        self.assertEqual(
            names,
            ["FC-HD", "SFC hack", "SFC-MSU1", "PS1 hack", "PS2 hack",
             "GBA HACK", "GBA vib", "WII Ware"],
        )
        self.assertNotIn("nesh", names)

    def test_alias_platforms_use_all_slots(self):
        for batch in (self.alekfull_nx_batch, self.aura_batch, self.canvas_batch,
                      self.elementerial_batch, self.iconic_batch, self.iisu_batch,
                      self.playstation_x_batch):
            for item in batch["platforms"]:
                if item["action"] == "alias":
                    self.assertEqual(item["slots"], "all")

    def test_required_source_files_exist_with_exact_names(self):
        for profile, batch in ((self.canvas, self.canvas_batch), (self.iconic, self.iconic_batch)):
            source = ROOT / profile["source_theme"]
            for item in batch["platforms"]:
                wanted = batch["slots_all"] if item["slots"] == "all" else item["slots"]
                for slot in wanted:
                    if slot not in profile["required_slots"]:
                        continue
                    folder = source / profile["slots"][slot]
                    filename = item["source"] + profile.get("slot_ext", {}).get(slot, ".webp")
                    self.assertIn(filename, {p.name for p in folder.iterdir()},
                                  (profile["id"], item["name"], slot))
                self.assertTrue(
                    (source / profile["metadata_dir"] / (item["source"] + ".xml")).is_file(),
                    (profile["id"], item["name"]),
                )

    def test_iconic_carousel_and_overlays_are_copy_only(self):
        copy_only = {"carousel", "default-overlay", "classic-overlay", "modern-overlay"}
        self.assertEqual(set(self.iconic["badge_slots"]), set(self.iconic["slots"]) - copy_only)

    def test_wii_system_identifiers_are_lowercase(self):
        wii = next(system for system in self.systems.findall("system")
                   if system.findtext("fullname") == "Nintendo Wii")
        self.assertEqual(wii.findtext("name"), "wii")
        self.assertEqual(wii.findtext("platform"), "wii")
        self.assertEqual(wii.findtext("theme"), "wii")
        self.assertEqual(wii.findtext("path"), "%ROMPATH%/WII")

    def test_export_names_are_derived_from_source_themes(self):
        for profile, expected in (
            (self.alekfull_nx, "Alekfull NX (Revisited)_天马G"),
            (self.aura, "Aura_天马G"),
            (self.canvas, "Canvas_天马G"),
            (self.elementerial, "Elementerial_天马G"),
            (self.iconic, "Iconic_天马G"),
            (self.iisu, "iiSU Interpreted_天马G"),
            (self.playstation_x, "PlayStation-X_天马G"),
        ):
            base, output = theme_name(self.project, str(ROOT / profile["source_theme"]))
            self.assertEqual(output, expected)
            self.assertEqual(output, base + "_天马G")
        self.assertNotIn("suffix", self.project["theme_naming"])

    def test_configuration_preflight_passes(self):
        for name in ("alekfull-nx-batch1", "aura-batch1", "batch1",
                     "elementerial-batch1", "iconic-batch1", "iisu-batch1",
                     "playstation-x-batch1"):
            with self.subTest(batch=name):
                self.assertEqual(validate(name), [])

    def test_active_badge_is_the_capped_pill(self):
        cfg = load_json("tools/themes/config/badge_params.json")
        self.assertEqual(cfg["active_candidate"], "P_pill_top_right")
        params = badge_params_for(cfg, "artwork", "HACK")
        self.assertEqual(params["style"], "pill")
        self.assertEqual(params["opacity"], 170)
        self.assertEqual((params["scale_h"], params["size_add_px"], params["max_height_px"]),
                         (0.065, 15, 140))

    def test_aura_directory_slot_prefers_target_and_renames_fallback(self):
        source = str(ROOT / self.aura["source_theme"])
        nesh = next(item for item in self.aura_batch["platforms"] if item["name"] == "nesh")
        gba = next(item for item in self.aura_batch["platforms"] if item["name"] == "GBA HACK")
        self.assertEqual(find_directory_source(self.aura, source, nesh,
                                               "default-art", "")[1], "nesh")
        self.assertEqual(find_directory_source(self.aura, source, gba,
                                               "default-art", "-clear-full-w-char")[1], "gba")

    def test_new_profiles_have_expected_copy_only_slots(self):
        self.assertEqual(self.iisu["badge_slots"], ["artwork", "controllers"])
        self.assertEqual(self.playstation_x["slot_ext"], {"logos": ".svg", "videos": ".mp4"})
        self.assertNotIn("videos", self.playstation_x["badge_slots"])
        self.assertNotIn("logos", self.playstation_x["badge_slots"])
        self.assertNotIn("overlays", self.playstation_x["badge_slots"])

    def test_new_profiles_are_registered(self):
        self.assertEqual(self.project["theme_profiles"]["alekfull-nx"], "tools/themes/config/themes/alekfull-nx.json")
        self.assertEqual(self.project["theme_profiles"]["aura"], "tools/themes/config/themes/aura.json")
        self.assertEqual(self.project["theme_profiles"]["elementerial"], "tools/themes/config/themes/elementerial.json")
        self.assertEqual(self.project["theme_profiles"]["iisu"], "tools/themes/config/themes/iisu.json")
        self.assertEqual(self.project["theme_profiles"]["playstation-x"], "tools/themes/config/themes/playstation-x.json")


if __name__ == "__main__":
    unittest.main()
