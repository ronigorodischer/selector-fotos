"""Integration test using ONLY a generated, disposable text file."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.deps'))


class SystemTrashTest(unittest.TestCase):
    def test_generated_file_uses_system_trash(self):
        from send2trash import send2trash
        with tempfile.TemporaryDirectory(prefix='selector-test-',dir=ROOT/'data') as folder:
            target=Path(folder)/'selector-disposable-test.txt'
            target.write_text('Archivo generado exclusivamente para probar la papelera.',encoding='utf-8')
            self.assertTrue(target.resolve().is_relative_to((ROOT/'data').resolve()))
            send2trash(str(target))
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
