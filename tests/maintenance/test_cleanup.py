from pathlib import Path
import tempfile
import unittest
from frontend_common.cleanup import preview_cleanup, clean_workspace
from frontend_common.jobs import new_job
from frontend_common.locking import workspace_lock


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_unknown_temp_and_protected_data_are_retained(self):
        for relative in ("temp/real-rom/keep.gba", "themes/original/A/keep.png", "config/platforms.json", "logs/desktop.log"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"keep")
        items, retained = preview_cleanup(self.root)
        self.assertEqual(items, [])
        self.assertTrue(retained)

    def test_only_marked_staging_is_cleaned(self):
        job = new_job(self.root, "theme-convert")
        (job / "image.png").write_bytes(b"staging")
        items, _ = preview_cleanup(self.root)
        self.assertEqual(len(items), 1)
        clean_workspace(self.root, items)
        self.assertFalse(job.exists())

    def test_changed_preview_is_rejected_before_deletion(self):
        job = new_job(self.root, "theme-import")
        file = job / "image.png"
        file.write_bytes(b"old")
        items, _ = preview_cleanup(self.root)
        file.write_bytes(b"new content")
        with self.assertRaises(ValueError):
            clean_workspace(self.root, items)
        self.assertTrue(file.is_file())

    def test_library_snapshots_and_plans_are_recovery_batches(self):
        for kind in ("scan", "convert"):
            new_job(self.root, kind)
        items, _ = preview_cleanup(self.root)
        self.assertEqual({item.category for item in items}, {"backups"})
        self.assertEqual(sum(item.latest for item in items), 1)

    def test_busy_workspace_blocks_cleanup(self):
        with workspace_lock(self.root):
            with self.assertRaises(ValueError):
                clean_workspace(self.root, [])
