import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app


class PortableTests(unittest.TestCase):
    def test_fresh_install_and_stale_path_start_without_original_machine(self):
        with tempfile.TemporaryDirectory(dir=app.BASE/'data') as temp:
            root=Path(temp);settings=root/'data'/'settings.json'
            with patch.object(app,'BASE',root),patch.object(app,'SETTINGS',settings):
                self.assertEqual(root/'data'/'inicio',app.initial_source())
                self.assertTrue(app.initial_source().is_dir())
                settings.write_text(json.dumps({'source':str(root/'missing')}),encoding='utf-8')
                self.assertEqual(root/'data'/'inicio',app.initial_source())
                settings.write_text('invalid json',encoding='utf-8')
                self.assertEqual(root/'data'/'inicio',app.initial_source())

    def test_saved_and_explicit_folders_take_priority(self):
        with tempfile.TemporaryDirectory(dir=app.BASE/'data') as temp:
            root=Path(temp);saved=root/'photos';saved.mkdir()
            settings=root/'settings.json';settings.write_text(json.dumps({'source':str(saved)}),encoding='utf-8')
            with patch.object(app,'SETTINGS',settings):
                self.assertEqual(saved,app.initial_source())
                self.assertEqual(root/'explicit',app.initial_source(root/'explicit'))


if __name__=='__main__':unittest.main()
