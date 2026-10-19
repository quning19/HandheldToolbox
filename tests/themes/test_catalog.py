"""Official catalogue lifecycle with isolated files and mocked network/Git."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from frontend_common.files import write_json
from retrolibx.errors import ValidationError
from theme_converter.catalog import (
    MARKER, check_updates, download_themes, git, git_progress, managed_themes,
    read_catalog, refresh_catalog, remote_head, remove_local, stage_repository,
)
from theme_converter.parser import PARSER_VERSION, POLICY_VERSION
from theme_converter.service import local_themes
from theme_converter.state import source_index


OLD, NEW = "a" * 40, "b" * 40
URL = "https://example.org/demo-es-de.git"
IDENTITY = "official-demo-es-de"


def make_theme(path, name):
    path.mkdir(parents=True)
    (path / "capabilities.xml").write_text(
        "<themeCapabilities><themeName>" + name + "</themeName></themeCapabilities>", encoding="utf-8")
    (path / "theme.xml").write_text("<theme/>", encoding="utf-8")
    return path


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.catalog = self.root / "themes/catalog"
        self.entry = {"name": "Demo", "reponame": "demo-es-de", "url": URL, "author": "Author",
                      "screenshots": [{"image": "screenshots/demo/01.jpg", "caption": "System view"}]}
        self.save_catalog()

    def save_catalog(self, **extra):
        write_json(self.catalog / "themes.json", {"themes": [self.entry], **extra})

    def installed(self):
        original = make_theme(self.root / "themes/original" / IDENTITY, "Demo")
        write_json(original / MARKER, {"repository": URL, "revision": OLD})
        output = make_theme(self.root / "themes/exported/Demo_天马G", "Demo_天马G")
        write_json(self.root / "config/theme-results.json", {IDENTITY: {
            "directory": output.name, "complete": True, "parser": PARSER_VERSION,
            "policy": POLICY_VERSION, "dependencies": [], "source_index": source_index(original),
            "output_index": source_index(output),
        }})
        return original, output

    def test_android_additions_and_duplicate_entries_are_merged(self):
        android = {"name": "Modern", "reponame": "modern-es-de", "url": URL}
        self.save_catalog(themesAndroid=[self.entry, android])
        infos = managed_themes(self.root, [])
        self.assertEqual([info.name for info in infos], ["Demo", "Modern"])
        self.assertEqual(infos[0].screenshots[0][0], self.catalog / "screenshots/demo/01.jpg")
        self.assertFalse(infos[0].original)

    def test_conflicting_repositories_are_rejected(self):
        self.save_catalog(themesAndroid=[dict(self.entry, url="https://example.org/other.git")])
        with self.assertRaises(ValidationError):
            read_catalog(self.catalog)

    def test_preview_cannot_escape_catalogue(self):
        self.entry["screenshots"] = [{"image": "../private.png"}]
        self.save_catalog()
        with self.assertRaises(ValidationError):
            read_catalog(self.catalog)

    def test_remote_must_be_https_without_credentials(self):
        for url in ("file:///tmp/repository", "https://user:secret@example.org/repository", "ext::command"):
            self.entry["url"] = url
            self.save_catalog()
            with self.assertRaises(ValidationError):
                read_catalog(self.catalog)

    def test_update_check_does_not_expire_valid_conversion(self):
        original, _output = self.installed()
        before = source_index(original)
        with patch("theme_converter.catalog.remote_head", return_value=("main", NEW)):
            check_updates(self.root, [], [], lambda: False, lambda *_: None)
        info = managed_themes(self.root, [])[0]
        self.assertTrue(info.update_available)
        self.assertTrue(info.converted)
        self.assertEqual(source_index(original), before)

    def test_failed_check_does_not_claim_latest_or_stop_other_themes(self):
        self.installed()
        with patch("theme_converter.catalog.remote_head", side_effect=ValidationError("offline")):
            message = check_updates(self.root, [], [], lambda: False, lambda *_: None)
        info = managed_themes(self.root, [])[0]
        self.assertIsNone(info.update_available)
        self.assertIn("offline", info.update_error)
        self.assertIn("失败", message)
        self.assertTrue(info.converted)

    def test_successful_update_preserves_old_original_and_expires_output(self):
        original, output = self.installed()
        staged = make_theme(self.root / "temp/staged", "Demo")
        (staged / "theme.xml").write_text("<theme><changed/></theme>", encoding="utf-8")
        with patch("theme_converter.catalog.stage_repository", return_value=(staged, NEW, OLD)):
            download_themes(self.root, [], [IDENTITY], lambda: False, lambda *_: None)
        info = managed_themes(self.root, [])[0]
        self.assertTrue(info.stale)
        self.assertFalse(info.converted)
        self.assertFalse(info.update_available)
        self.assertTrue(output.is_dir())
        self.assertIn("changed", (original / "theme.xml").read_text())
        self.assertEqual(len(list((self.root / "backups/themes").glob("*/" + IDENTITY))), 1)

    def test_failed_download_keeps_original_and_conversion(self):
        original, _output = self.installed()
        before = source_index(original)
        with patch("theme_converter.catalog.stage_repository", side_effect=ValidationError("offline")):
            with self.assertRaises(ValidationError):
                download_themes(self.root, [], [IDENTITY], lambda: False, lambda *_: None)
        self.assertEqual(source_index(original), before)
        self.assertTrue(managed_themes(self.root, [])[0].converted)

    def test_no_change_does_not_replace_original_or_expire_conversion(self):
        original, _output = self.installed()
        before = source_index(original)
        with patch("theme_converter.catalog.stage_repository", return_value=(original, OLD, OLD)):
            download_themes(self.root, [], [IDENTITY], lambda: False, lambda *_: None)
        self.assertEqual(source_index(original), before)
        self.assertTrue(managed_themes(self.root, [])[0].converted)
        self.assertFalse((self.root / "backups/themes").exists())

    def test_delete_original_retains_manageable_old_output(self):
        original, output = self.installed()
        remove_local(self.root, [], [IDENTITY], "delete-original")
        info = managed_themes(self.root, [])[0]
        self.assertFalse(original.exists())
        self.assertFalse(info.original)
        self.assertTrue(info.stale)
        self.assertEqual(info.output, output)
        remove_local(self.root, [], [IDENTITY], "delete-output")
        self.assertFalse(output.exists())

    def test_old_import_is_not_matched_to_official_by_name(self):
        make_theme(self.root / "themes/original/local-demo", "Demo")
        infos = managed_themes(self.root, [])
        self.assertEqual(len(infos), 2)
        imported = next(info for info in infos if info.id == "local-demo")
        self.assertEqual(imported.repository, "")

    def test_delisted_download_is_retained(self):
        self.installed()
        write_json(self.catalog / "themes.json", {"themes": []})
        info = managed_themes(self.root, [])[0]
        self.assertTrue(info.deprecated)
        self.assertEqual(info.repository, URL)
        self.assertTrue(info.converted)

    def test_failed_catalogue_refresh_keeps_cache(self):
        before = (self.catalog / "themes.json").read_bytes()
        with patch("theme_converter.catalog.stage_repository", side_effect=ValidationError("offline")):
            with self.assertRaises(ValidationError):
                refresh_catalog(self.root, lambda: False, lambda *_: None)
        self.assertEqual((self.catalog / "themes.json").read_bytes(), before)

    def test_catalogue_forwards_live_transfer_progress(self):
        def stage(*_args, progress, **_kwargs):
            progress("接收数据: 35%, 4.2 MiB | 1.0 MiB/s", 35)
            return self.catalog, OLD, OLD
        events = []
        with patch("theme_converter.catalog.stage_repository", side_effect=stage):
            refresh_catalog(self.root, lambda: False, lambda *event: events.append(event))
        self.assertIn(("官方主题目录 · 接收数据: 35%, 4.2 MiB | 1.0 MiB/s", 35, True), events)
        self.assertEqual(events[0][1], -1)

    def test_batch_download_reports_each_theme_and_stage(self):
        second = dict(self.entry, name="Second", reponame="second-es-de")
        write_json(self.catalog / "themes.json", {"themes": [self.entry, second]})
        def stage(_workspace, _source, url, _cancelled, *, progress, **_kwargs):
            progress("接收数据: 50%, 2 MiB", 50)
            index = len(list((self.root / "temp").glob("stage-*"))) if (self.root / "temp").exists() else 0
            return make_theme(self.root / "temp" / f"stage-{index}", "Demo"), NEW, ""
        events = []
        with patch("theme_converter.catalog.stage_repository", side_effect=stage):
            download_themes(self.root, [], [IDENTITY, "official-second-es-de"], lambda: False,
                            lambda *event: events.append(event))
        for index, name in ((1, "Demo"), (2, "Second")):
            self.assertIn((f"[{index}/2] {name} · 接收数据: 50%, 2 MiB", 50, True), events)
            self.assertIn((f"[{index}/2] {name} · 下载／更新完成", 100, True), events)

    def test_remote_default_branch_and_revision_are_parsed(self):
        with patch("theme_converter.catalog.git", side_effect=["ref: refs/heads/main\tHEAD\n" + NEW + "\tHEAD", ""]):
            self.assertEqual(remote_head(URL, lambda: False), ("main", NEW))

    def test_modified_repository_is_rejected_before_staging_or_fetch(self):
        original, _output = self.installed()
        (original / ".git").mkdir()
        with patch("theme_converter.catalog.git", side_effect=[str(original), URL, " M theme.xml"]), \
                patch("theme_converter.catalog.remote_head") as network:
            with self.assertRaisesRegex(ValidationError, "本地修改"):
                stage_repository(self.root, original, URL, lambda: False, expected_revision=OLD)
            network.assert_not_called()

    def test_diverged_staged_repository_never_replaces_original(self):
        original, _output = self.installed()
        (original / ".git").mkdir()
        def git_call(args, **_kwargs):
            if args[0] == "rev-parse":
                return str(original) if args[1] == "--show-toplevel" else (OLD if args[1] == "HEAD" else NEW)
            if args[0] == "remote":
                return URL
            if args[0] == "merge-base":
                raise ValidationError("diverged")
            return ""
        with patch("theme_converter.catalog.git", side_effect=git_call), \
                patch("theme_converter.catalog.remote_head", return_value=("main", NEW)):
            with self.assertRaisesRegex(ValidationError, "分叉"):
                stage_repository(self.root, original, URL, lambda: False, expected_revision=OLD)
        self.assertTrue(local_themes(self.root, [])[0].converted)


class GitProgressTests(unittest.TestCase):
    """Local child processes only: exercise Windows pipes without network/Git."""

    def spawn_script(self, script):
        original = subprocess.Popen
        def launch(_args, **kwargs):
            if _args[0] != "git":
                return original(_args, **kwargs)
            self.process = original([sys.executable, "-u", "-c", script], **kwargs)
            return self.process
        return patch("theme_converter.catalog.subprocess.Popen", side_effect=launch)

    def test_carriage_return_progress_arrives_before_child_finishes(self):
        script = ("import sys,time; "
                  "sys.stderr.write('Receiving objects: 25% (1/4), 2.00 MiB | 1.00 MiB/s\\r'); "
                  "sys.stderr.flush(); time.sleep(1); "
                  "sys.stderr.write('Resolving deltas: 100% (4/4), done.\\r'); sys.stderr.flush()")
        events = []
        def progress(text, percent):
            events.append((text, percent, self.process.poll()))
        with self.spawn_script(script):
            output = git(["clone", "--progress"], progress=progress)
        transfer = next(event for event in events if event[1] == 25)
        self.assertIsNone(transfer[2], "必须在进程结束之前收到实时进度")
        self.assertIn("2.00 MiB | 1.00 MiB/s", transfer[0])
        self.assertTrue(any("整理数据" in text and percent == 100 for text, percent, _ in events))
        self.assertIn("Receiving objects", output)

    def test_silent_connection_reports_unknown_progress_and_elapsed_wait(self):
        events = []
        with self.spawn_script("import time; time.sleep(1.3)"):
            git(["clone"], progress=lambda *event: events.append(event))
        self.assertTrue(all(percent == -1 for _text, percent in events))
        self.assertTrue(any("等待响应" in text for text, _percent in events))

    def test_live_error_keeps_git_diagnostic(self):
        with self.spawn_script("import sys; sys.stderr.write('fatal: offline\\n'); sys.exit(2)"):
            with self.assertRaisesRegex(ValidationError, "fatal: offline"):
                git(["fetch"], progress=lambda *_: None)

    def test_live_cancellation_terminates_only_launched_child(self):
        from frontend_common.jobs import Cancelled
        cancel = False
        def progress(_text, percent):
            nonlocal cancel
            cancel = percent == 25
        with self.spawn_script("import sys,time; sys.stderr.write('Receiving objects: 25%\\r'); "
                               "sys.stderr.flush(); time.sleep(10)"), \
                patch("theme_converter.catalog.subprocess.run", return_value=subprocess.CompletedProcess(["taskkill"], 1)):
            with self.assertRaises(Cancelled):
                git(["clone"], cancelled=lambda: cancel, progress=progress)
        self.assertIsNotNone(self.process.poll())

    def test_stage_without_percent_remains_indeterminate(self):
        self.assertEqual(git_progress("remote: Enumerating objects: 42, done."), ("服务器整理文件: 42, done.", -1))
