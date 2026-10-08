import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / 'skills/livestream-scene/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('batch', SCRIPTS / 'batch.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class BatchTest(unittest.TestCase):
    def test_only_images_and_matching_text_with_history_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / '项目'
            src = Path(tmp) / 'source.png'
            Image.new('RGB', (90, 160), 'white').save(src)
            first = m.save(root, '本批次测试', 1, 1, src, scenes=12)
            with self.assertRaises(ValueError):
                m.check(root, '本批次测试', scenes=12)
            p = Path(first['image'])
            p.with_suffix('.txt').write_text('完全无人，中文独立文生图描述。', encoding='utf-8')
            before = p.read_bytes()
            with self.assertRaises(FileExistsError):
                m.save(root, '本批次测试', 1, 1, src, scenes=12)
            second = m.save(root, '本批次测试', 1, 2, src, scenes=12)
            Path(second['image']).with_suffix('.txt').write_text('第二版中文场景描述。', encoding='utf-8')
            result = m.check(root, '本批次测试', scenes=12, expected_scenes=1)
            self.assertEqual(result['images'], ['01 (1).png', '01 (2).png'])
            self.assertEqual(p.read_bytes(), before)
            self.assertEqual(list(root.iterdir()), [root / '本批次测试'])
            self.assertEqual(list((root / '本批次测试').iterdir()), [p.parent])
            self.assertEqual(len(list(p.parent.iterdir())), 4)
            with Image.open(p) as image:
                self.assertEqual(image.size, (1080, 1920))

    def test_bad_ratio_skipped_version_and_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / 'square.png'
            Image.new('RGB', (100, 100)).save(src)
            with self.assertRaises(ValueError):
                m.output(tmp, '../outside')
            with self.assertRaises(ValueError):
                m.save(tmp, '批次', 1, 2, src)
            with self.assertRaises(ValueError):
                m.save(tmp, '批次', 1, 1, src)
            self.assertEqual(list((Path(tmp) / '批次/全部场景版本').iterdir()), [])

if __name__ == '__main__':
    unittest.main()
