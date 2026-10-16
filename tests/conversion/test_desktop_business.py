"""Focused desktop business cases. Local temporary inputs and mocked ADB only."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import io
import json
import tarfile
import tempfile
import unittest

from library_converter.desktop import (
    convert_library, discover_device, local_target, scan_library,
)
from frontend_devices.adb import capture_device
from library_converter.handheld import HandheldConfig, build_handheld
from frontend_platforms.catalog import materialize_catalog
from library_converter.publication import load_publication
from library_converter.selection import detect_metadata_encoding, select_entries
from theme_converter.service import ThemeInfo, adapt_theme, local_themes
from retrolibx.core.android import render_android_script
from retrolibx.core.models import Game, Library, Rom, System
from retrolibx.core.operations import ConversionPlan, TransferFile, WriteText
from retrolibx.errors import ValidationError
from frontend_common.state import PlatformDefinition, default_definitions
from retrolibx.registry import SystemRegistry
from retrolibx.adapters.esde.merge import parse_xml

NO_CANCEL = lambda: False
NO_PROGRESS = lambda *_args: None


class DesktopBusinessTests(unittest.TestCase):
    def setUp(self):
        root = (Path(__file__).resolve().parents[2] / "test_data/desktop-business-unit").resolve()
        root.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="case-", dir=root)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.workspace = self.base / "workspace"
        self.source = self.base / "Roms"
        self.definitions = default_definitions()
        self.target = local_target(self.workspace, self.source)

    def source_fixture(self):
        folder = self.source / "GBA"
        cover = folder / "media/Test/boxfront.png"
        cover.parent.mkdir(parents=True)
        cover.write_bytes(b"original-cover")
        for name in ("a.gba", "b.gba", "orphan.gba"):
            (folder / name).write_bytes(name.encode())
        metadata = folder / "metadata.pegasus.txt"
        metadata.write_text(
            "collection: GBA\nshortname: gba\n\ngame: Test\nfiles:\n"
            "  a.gba\n  b.gba\n  missing.gba\nassets.box_front: media/Test/boxfront.png\n",
            encoding="utf-8",
        )
        return metadata, cover

    def old_list(self):
        path = self.target / "gamelists/gba/gamelist.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "<gameList><game><path>./a.gba</path><name>User title</name><favorite>true</favorite></game>"
            "<game><path>./old-extra.gba</path><name>Keep extra</name></game></gameList>",
            encoding="utf-8",
        )
        return path

    def scan(self):
        return scan_library(self.workspace, self.definitions, str(self.source), None,
                            NO_CANCEL, NO_PROGRESS, lambda _info: None)

    def test_scan_counts_real_versions_missing_references_and_unlinked_roms(self):
        self.source_fixture()
        self.old_list()
        events = []
        session = scan_library(self.workspace, self.definitions, str(self.source), None,
                               NO_CANCEL, NO_PROGRESS, events.append)
        info = session.platforms["GBA"]
        self.assertEqual((info.roms, info.covers, info.existing, info.missing_references, info.unlinked), (2, 2, 1, 1, 1))
        self.assertEqual(events, [info])
        self.assertEqual(info.error, "")

    def test_increment_copies_only_new_variant_and_preserves_existing_user_fields(self):
        metadata, _cover = self.source_fixture()
        original = metadata.read_bytes()
        path = self.old_list()
        old_cover = self.target / "downloaded_media/gba/covers/a.png"
        old_cover.parent.mkdir(parents=True)
        old_cover.write_bytes(b"keep-old-cover")
        result = convert_library(self.scan(), ["GBA"], False, False, self.workspace, NO_CANCEL, NO_PROGRESS)
        self.assertEqual(result["roms"], 1)
        root = parse_xml(path.read_bytes(), "gameList")
        self.assertEqual(len(root.findall("game")), 3)
        self.assertEqual(root.findtext("game[path='./a.gba']/name"), "User title")
        self.assertEqual(root.findtext("game[path='./a.gba']/favorite"), "true")
        self.assertEqual(old_cover.read_bytes(), b"keep-old-cover")
        self.assertEqual(old_cover.with_name("b.png").read_bytes(), b"original-cover")
        self.assertEqual(metadata.read_bytes(), original)
        for name in ("es_systems.xml", "es_find_rules.xml", "es_import_rules.xml", "es_systems_sorting.xml"):
            self.assertTrue((self.target / "custom_systems" / name).is_file())

    def test_full_replace_updates_media_and_retains_extra_games(self):
        self.source_fixture()
        path = self.old_list()
        cover = self.target / "downloaded_media/gba/covers/a.png"
        cover.parent.mkdir(parents=True)
        cover.write_bytes(b"old")
        result = convert_library(self.scan(), ["GBA"], False, True, self.workspace, NO_CANCEL, NO_PROGRESS)
        self.assertEqual(result["roms"], 2)
        self.assertEqual(cover.read_bytes(), b"original-cover")
        self.assertIsNotNone(parse_xml(path.read_bytes(), "gameList").find("game[path='./old-extra.gba']"))

    def test_shared_mode_can_add_variant_after_source_media_was_migrated(self):
        metadata, cover = self.source_fixture()
        convert_library(self.scan(), ["GBA"], True, False, self.workspace, NO_CANCEL, NO_PROGRESS)
        self.assertFalse(cover.exists())
        (self.source / "GBA/c.gba").write_bytes(b"third-rom")
        content = metadata.read_text(encoding="utf-8").replace("  missing.gba", "  c.gba\n  missing.gba")
        metadata.write_text(content, encoding="utf-8")
        session = self.scan()
        self.assertEqual((session.platforms["GBA"].roms, session.platforms["GBA"].existing), (3, 2))
        result = convert_library(session, ["GBA"], True, False, self.workspace, NO_CANCEL, NO_PROGRESS)
        self.assertEqual(result["roms"], 1)
        for name in ("a.png", "b.png", "c.png"):
            self.assertEqual((self.target / "downloaded_media/gba/covers" / name).read_bytes(), b"original-cover")

    def test_multitrack_disc_keeps_descriptor_and_counts_separate_versions(self):
        self.source.mkdir()
        cue = self.source / "disc.cue"
        cue.write_text('FILE "track 01.bin" BINARY\n TRACK 01 MODE1/2352\n', encoding="utf-8")
        track = self.source / "track 01.bin"
        track.write_bytes(b"track")
        alternate = self.source / "version2.chd"
        alternate.write_bytes(b"version")
        library = Library(format="pegasus", systems=[System(id="psx", name="PS1", games=[
            Game(name="Disc", roms=[Rom(path=path) for path in (cue, track, alternate)])
        ])])
        counts = select_entries(library, self.base / "snapshot", {"psx": str(self.source)}, existing_only=True)
        self.assertEqual(counts["selected"], 2)
        self.assertEqual([rom.path for rom in library.systems[0].games[0].roms], [cue, alternate])

    def test_encoding_is_automatic_for_utf8_bom_utf16_and_chinese_legacy(self):
        text = "collection: GBA\ngame: 中文\n"
        for encoding in ("utf-8-sig", "utf-16", "gb18030"):
            data = text.encode(encoding)
            self.assertEqual(data.decode(detect_metadata_encoding(data)), text)

    def test_mixed_platform_encodings_convert_without_a_manual_encoding_setting(self):
        self.source_fixture()
        folder = self.source / "GB"
        folder.mkdir()
        (folder / "one.gb").write_bytes(b"rom")
        original = "collection: GB\ngame: 中文\nfile: one.gb\n".encode("gb18030")
        (folder / "metadata.pegasus.txt").write_bytes(original)
        result = convert_library(self.scan(), ["GBA", "GB"], False, False,
                                 self.workspace, NO_CANCEL, NO_PROGRESS)
        self.assertEqual(result["roms"], 3)
        self.assertEqual((folder / "metadata.pegasus.txt").read_bytes(), original)
        self.assertTrue((self.target / "gamelists/gb/gamelist.xml").is_file())

    def test_inherited_theme_does_not_make_parent_system_ambiguous(self):
        directory = self.base / "catalog"
        materialize_catalog(self.definitions, directory)
        registry = SystemRegistry.load(platform_config_dir=directory)
        self.assertEqual(registry.resolve("psp").id, "psp")
        self.assertEqual(registry.resolve("PSP Minis").id, "pspminis")
        self.assertEqual(registry.records["pspminis"].theme, registry.records["psp"].theme)

    def test_custom_platform_inherits_complete_launch_template(self):
        custom = PlatformDefinition("gba-custom", "GBA Custom", "GBA Custom", "gba", "separate", "CUSTOM")
        directory = self.base / "catalog"
        materialize_catalog([*self.definitions, custom], directory)
        root = parse_xml((directory / "es_systems.xml").read_bytes(), "systemList")
        parent = root.find("system[name='gba']")
        child = root.find("system[name='gba-custom']")
        self.assertGreaterEqual(len(root.findall("system")), 78)
        self.assertEqual(child.findtext("path"), "%ROMPATH%/GBA Custom")
        self.assertEqual([(n.attrib, n.text) for n in child.findall("command")],
                         [(n.attrib, n.text) for n in parent.findall("command")])
        self.assertEqual(SystemRegistry.load(platform_config_dir=directory).resolve("GBA Custom").id, "gba-custom")

    def android_plan(self, policy="skip"):
        source, target = self.base / "source", self.base / "snapshot"
        media = source / "GBA/.frontendtrans-index/cover.png"
        media.parent.mkdir(parents=True)
        media.write_bytes(b"")
        operation = TransferFile(source=media, destination=target / "downloaded_media/gba/covers/new.png",
                                 category="media", mode="copy")
        return ConversionPlan(source_root=source, target_root=target, source_format="pegasus",
                              target_format="es-de", conflict_policy=policy, operations=[operation])

    def test_android_full_replace_overwrites_even_when_snapshot_has_no_media_files(self):
        plan = self.android_plan("overwrite")
        script, _payload = render_android_script(plan, "/storage/card/Roms", "/storage/emulated/0/ES-DE", [])
        self.assertIn("cp -f --", script)

    def test_android_normal_copy_retains_skip_policy(self):
        plan = self.android_plan()
        script, _payload = render_android_script(plan, "/storage/card/Roms", "/storage/emulated/0/ES-DE", [])
        self.assertIn("cp -n --", script)

    def test_android_rejects_shared_media_override_outside_media_directory(self):
        plan = self.android_plan()
        with self.assertRaises(ValidationError):
            render_android_script(plan, "/storage/card/Roms", "/storage/emulated/0/ES-DE", [],
                                  media_source_overrides={"GBA/.frontendtrans-index/cover.png": "/storage/private/file.png"})

    def test_android_versioned_backups_do_not_reuse_an_old_baseline_filename(self):
        plan = self.android_plan()
        plan.operations = [WriteText(destination=plan.target_root / "gamelists/gba/gamelist.xml",
                                     content="<gameList/>", expected_sha256="a" * 64, backup=True)]
        _script, payload = render_android_script(plan, "/storage/card/Roms", "/storage/emulated/0/ES-DE", [],
                                                 versioned_backups=True)
        publication = json.loads(payload["publication.json"])
        self.assertTrue(publication["writes"][0]["backup"].endswith(".frontendtrans." + "a" * 64 + ".bak"))

    def test_indexed_shared_media_is_copied_from_esde_and_never_scheduled_for_cleanup(self):
        folder = self.base / "Roms/GBA"
        alias = folder / ".frontendtrans-index/cover.png"
        alias.parent.mkdir(parents=True)
        alias.write_bytes(b"")
        (folder / "new.gba").write_bytes(b"")
        remote = "/storage/emulated/0/ES-DE/downloaded_media/gba/covers/old.png"
        metadata = folder / "metadata.pegasus.txt"
        metadata.write_text(f"collection: GBA\ngame: New\nfile: new.gba\nassets.box_front: {remote}\n", encoding="utf-8")
        config_dir = self.base / "catalog"
        materialize_catalog(self.definitions, config_dir)
        index = self.base / "device-index.json"
        index.write_text(json.dumps({"sizes": {"GBA/new.gba": 100, "GBA/.frontendtrans-index/cover.png": 20}}), encoding="utf-8")
        config = HandheldConfig(source_root=folder.parent, device_rom_root="/storage/card/Roms",
                                esde_root="/storage/emulated/0/ES-DE", target_empty=True,
                                platform_config_dir=config_dir, device_index=index, shared_pegasus=True,
                                media_path_aliases={"GBA": {remote: alias}},
                                device_media_sources={"GBA/.frontendtrans-index/cover.png": remote})
        task = self.base / "task"
        summary = build_handheld(config, ["GBA"], task)
        self.assertTrue(summary["executable"])
        data, _payloads = load_publication(task)
        self.assertEqual(data["cleanup"], [])
        self.assertEqual(data["media"][0]["source"], remote)
        self.assertIn(remote, (task / "apply.sh").read_text(encoding="utf-8"))

    def tiny_theme(self):
        from PIL import Image
        source = self.workspace / "themes/original/canvas"
        source.mkdir(parents=True)
        (source / "capabilities.xml").write_text("<themeCapabilities><themeName>Canvas</themeName></themeCapabilities>", encoding="utf-8")
        (source / "theme.xml").write_text('''<theme>
<include>./_inc/systems/metadata-global/${system.theme}.xml</include>
<view name="system">
  <image name="capsule-art"><path>./_inc/carousel-icons-capsule/${system.theme}.webp</path></image>
  <image name="background-art"><path>./_inc/carousel-icons-art/dark/${system.theme}.webp</path></image>
</view></theme>''', encoding="utf-8")
        for directory in ("_inc/carousel-icons-capsule", "_inc/carousel-icons-art/dark"):
            path = source / directory / "gba.webp"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (80, 60), "navy").save(path)
        metadata = source / "_inc/systems/metadata-global/gba.xml"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("<theme><variables><systemName>GBA</systemName></variables></theme>", encoding="utf-8")
        definitions = [
            PlatformDefinition("gba", "GBA", "GBA"),
            PlatformDefinition("gba-test", "Test & More", "GBA Test", "gba", "separate", "HACK"),
        ]
        return source, definitions, ThemeInfo("canvas", "Canvas", original=True, source=source)

    def test_theme_build_generates_complete_output_and_escapes_platform_labels(self):
        source, definitions, info = self.tiny_theme()
        adapt_theme(self.workspace, definitions, info, NO_CANCEL, NO_PROGRESS)
        output = self.workspace / "themes/exported/Canvas_天马G"
        self.assertEqual((source / "theme.xml").read_text(), (output / "theme.xml").read_text())
        self.assertTrue((output / "_inc/carousel-icons-capsule/GBA Test.webp").is_file())
        xml = parse_xml((output / "_inc/systems/metadata-global/GBA Test.xml").read_bytes(), "theme")
        self.assertEqual(xml.findtext("variables/systemName"), "Test & More")
        self.assertTrue(local_themes(self.workspace, definitions)[0].converted)
        self.assertFalse((output / ".retrolibx").exists())

    def test_platform_changes_invalidate_uploadable_theme_state(self):
        _source, definitions, info = self.tiny_theme()
        adapt_theme(self.workspace, definitions, info, NO_CANCEL, NO_PROGRESS)
        definitions[-1] = replace(definitions[-1], badge="NEW")
        self.assertFalse(local_themes(self.workspace, definitions)[0].converted)

    def test_failed_theme_build_keeps_previous_complete_output(self):
        source, definitions, info = self.tiny_theme()
        adapt_theme(self.workspace, definitions, info, NO_CANCEL, NO_PROGRESS)
        output = self.workspace / "themes/exported/Canvas_天马G/capabilities.xml"
        before = output.read_bytes()
        (source / "_inc/carousel-icons-art/dark/gba.webp").unlink()
        with self.assertRaises(ValidationError):
            adapt_theme(self.workspace, definitions, info, NO_CANCEL, NO_PROGRESS)
        self.assertEqual(output.read_bytes(), before)

    def test_device_discovery_uses_authorized_serial_and_shallow_root_counts(self):
        result = SimpleNamespace(stdout=b"List of devices attached\nemulator-5554 device model:Test_Model\n")
        with patch("frontend_devices.discovery.find_adb", return_value=Path("adb.exe")), \
             patch("frontend_devices.discovery.subprocess.run", return_value=result) as run, \
             patch("frontend_devices.discovery.AdbReader") as reader:
            reader.return_value.read.side_effect = [
                b"/storage/emulated/0/Roms\0" + b"4\0/storage/ABCD/roms\0" + b"15\0",
                b"/storage/emulated/0/ES-DE\0",
            ]
            device = discover_device()
        self.assertEqual(device.serial, "emulator-5554")
        self.assertEqual([root[1:] for root in device.roots], [(4, "内置存储"), (15, "SD 卡")])
        self.assertEqual(run.call_args.args[0][1:], ["devices", "-l"])

    def test_capture_keeps_external_media_virtual_and_downloads_no_images(self):
        remote = "/storage/emulated/0/ES-DE/downloaded_media/gba/covers/a.png"
        metadata = f"collection: GBA\ngame: A\nfile: a.gba\nassets.box_front: {remote}\n".encode()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as tar:
            item = tarfile.TarInfo("GBA/metadata.pegasus.txt")
            item.size = len(metadata)
            tar.addfile(item, io.BytesIO(metadata))
        commands = []

        def read(command):
            commands.append(command)
            if command.startswith("find "):
                return b"4|/storage/card/Roms/GBA/a.gba\n" + str(len(metadata)).encode() + b"|/storage/card/Roms/GBA/metadata.pegasus.txt\n"
            if command.startswith("tar "):
                return archive.getvalue()
            if command.startswith("if [ -d "):
                return b""
            if command.startswith("for file "):
                return ("99|" + remote + "\n").encode()
            raise AssertionError(command)

        reader = SimpleNamespace(serial="mock", read=read, temporary_root=self.base)
        destination = self.base / "capture"
        result = capture_device(reader, "/storage/card/Roms", ["GBA"], "/storage/emulated/0/ES-DE",
                                destination, include_shared_media=True)
        config = HandheldConfig.load(destination / "config.json")
        alias = config.media_path_aliases["GBA"][remote]
        self.assertEqual(alias.read_bytes(), b"")
        self.assertEqual(result["media_downloaded"], 0)
        self.assertFalse(any("sha256sum" in command for command in commands))
        self.assertEqual(len(config.device_media_sources), 1)


if __name__ == "__main__":
    unittest.main()

