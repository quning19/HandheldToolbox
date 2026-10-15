"""Portable GUI configuration checks; no Qt window, backend or ADB access."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from retrolibx.gui.state import PlatformDefinition, UiStore, write_json


class GuiStateTests(unittest.TestCase):
    def setUp(self) -> None:
        root = (Path(__file__).resolve().parents[2] / "test_data/gui-state-unit").resolve()
        root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="case-", dir=root)
        self.base = Path(temporary.name).resolve()
        if not self.base.is_relative_to(root):
            raise RuntimeError("Temporary test directory escaped the workspace")
        self.addCleanup(temporary.cleanup)
        self.application = self.base / "应用 程序"
        self.application.mkdir()
        patcher = patch("retrolibx.gui.state.app_directory", return_value=self.application)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_workspace_and_unicode_definition_survive_reopen(self) -> None:
        store = UiStore()
        workspace = self.base / "中文 工作目录"
        store.change_workspace(workspace)
        custom = PlatformDefinition("gba-test", "GBA 测试", "GBA 测试", "gba", "separate", "测试")
        store.save_definitions([*store.definitions, custom])
        reopened = UiStore()
        self.assertEqual(reopened.workspace, workspace)
        self.assertEqual(reopened.definitions[-1], custom)
        self.assertTrue((self.application / "settings.json").is_file())
        for name in ("config", "themes/original", "themes/exported", "library", "devices", "logs", "temp"):
            self.assertTrue((workspace / name).is_dir(), name)

    def test_switch_workspace_keeps_old_data_and_loads_new_definitions(self) -> None:
        store = UiStore()
        old, new = self.base / "old", self.base / "new"
        store.change_workspace(old)
        store.save_definitions(store.definitions)
        previous = (old / "config/platforms.json").read_bytes()
        write_json(new / "config/platforms.json", {"version": 1, "platforms": []})
        store.change_workspace(new)
        self.assertEqual(store.definitions, [])
        self.assertEqual((old / "config/platforms.json").read_bytes(), previous)
        self.assertEqual(UiStore().workspace, new)

    def test_remove_definition_preserves_rom_media_and_other_definitions(self) -> None:
        store = UiStore()
        store.change_workspace(self.base / "workspace")
        custom = PlatformDefinition("custom", "测试", "测试")
        store.save_definitions([*store.definitions, custom])
        media = store.workspace / "themes/exported/keep.png"
        rom = store.workspace / "library/keep.gba"
        media.write_bytes(b"original-cover")
        rom.write_bytes(b"original-rom")
        expected = [entry for entry in store.definitions if entry.id != "custom"]
        store.save_definitions(expected)
        reopened = UiStore()
        self.assertEqual(reopened.definitions, expected)
        self.assertEqual(media.read_bytes(), b"original-cover")
        self.assertEqual(rom.read_bytes(), b"original-rom")

    def test_bad_platform_references_and_duplicate_directories_are_rejected(self) -> None:
        base = {"id": "one", "name": "One", "directory": "One"}
        bad_lists = [
            [dict(base, parent="missing")],
            [dict(base, parent="two"), {"id": "two", "name": "Two", "directory": "Two", "parent": "one"}],
            [base, {"id": "two", "name": "Two", "directory": "one"}],
            [dict(base, directory="../escape")],
        ]
        workspace = self.base / "invalid"
        for entries in bad_lists:
            with self.subTest(entries=entries):
                write_json(workspace / "config/platforms.json", {"version": 1, "platforms": entries})
                with self.assertRaises(ValueError):
                    UiStore.read_definitions(workspace)

    def test_save_failure_keeps_in_memory_definitions_and_previous_file(self) -> None:
        store = UiStore()
        store.change_workspace(self.base / "workspace")
        store.save_definitions(store.definitions)
        original = list(store.definitions)
        config = store.workspace / "config/platforms.json"
        before = config.read_bytes()
        changed = [replace(entry, name="Changed") if entry.id == "gb" else entry for entry in original]
        with patch("retrolibx.gui.state.write_json", side_effect=PermissionError("read-only")):
            with self.assertRaises(PermissionError):
                store.save_definitions(changed)
        self.assertEqual(store.definitions, original)
        self.assertEqual(config.read_bytes(), before)

    def test_invalid_settings_are_preserved_instead_of_silently_overwritten(self) -> None:
        path = self.application / "settings.json"
        for value in ([], {"version": 1, "workspace": "relative/path"}):
            with self.subTest(value=value):
                path.write_text(json.dumps(value), encoding="utf-8")
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    UiStore()
                self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
