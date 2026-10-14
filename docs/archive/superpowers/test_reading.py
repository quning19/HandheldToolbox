import tempfile
import unittest
from pathlib import Path

from frontend_trans_tool.metadata import parse_metadata
from frontend_trans_tool.profile import load_profile
from frontend_trans_tool.storage import LocalStorage, scan


ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'test_data' / 'original_excerpt' / 'Roms'


class ReadingTests(unittest.TestCase):
    def test_real_original_metadata_expands_files(self):
        model = parse_metadata((FIXTURE / 'GBA' / 'metadata.pegasus.txt').read_bytes())
        self.assertEqual(len(model['games']), 5)
        self.assertEqual(sum(len(g['files']) for g in model['games']), 12)
        self.assertEqual(model['games'][1]['files'][3], '口袋妖怪 红宝石 [4]E版官译全汉化+英文名+可联动+可银行.zip')
        self.assertEqual(model['encoding'], 'utf-8')
        self.assertIn('mgba_libretro', model['fields']['launch'])

    def test_bom_gbk_and_multiline_are_lossless(self):
        text = 'collection: 中文\r\n\r\ngame: 名称\nfile: 中文.zip\ndescription: 第一行\n  第二行\n\n  第三行\n'
        for raw, encoding in [(text.encode('utf-8-sig'), None), (text.encode('gbk'), 'gbk')]:
            with self.subTest(encoding=encoding):
                model = parse_metadata(raw, encoding)
                self.assertEqual(model['games'][0]['fields']['description'], '第一行\n第二行\n\n第三行')
                self.assertEqual(model['raw_sha256'], __import__('hashlib').sha256(raw).hexdigest())
        with self.assertRaises(ValueError):
            parse_metadata(text.encode('gbk'))

    def test_malformed_metadata_does_not_fallback_to_filenames(self):
        for text in ['not metadata', 'collection: GBA\ngame: Missing file', 'collection: GBA\nfile: a.zip']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_metadata(text.encode())

    def test_scan_finds_independent_platforms(self):
        rows = scan({'mode': 'local', 'source_root': str(FIXTURE)})
        self.assertEqual([(r['platform'], r['roms']) for r in rows], [('GBA', 12), ('GBA hack', 1), ('GBA vib', 2)])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'Parent' / 'Child').mkdir(parents=True)
            for folder in [root / 'Parent', root / 'Parent' / 'Child']:
                (folder / 'metadata.pegasus.txt').write_text('collection: Same\ngame: a\nfile: a.zip\n')
                (folder / 'a.zip').write_bytes(b'rom')
            store = LocalStorage(str(root))
            self.assertEqual(store.discover(), ['Parent', 'Parent/Child'])
            self.assertNotIn('Child/a.zip', store.index('Parent'))

    def test_profile_rejects_missing_and_unsafe_roots(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'profile.json'
            path.write_text(json.dumps({'source_root': str(FIXTURE), 'target_root': str(FIXTURE / 'media'), 'runtime_rom_root': '/storage/Roms'}))
            with self.assertRaises(ValueError):
                load_profile(path)
            path.write_text('{}')
            with self.assertRaises(ValueError):
                load_profile(path)


if __name__ == '__main__':
    unittest.main()
