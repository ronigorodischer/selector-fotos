import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from engine import Project, fingerprint, sha256
from app import Application, handler_for, ThreadingHTTPServer
from PIL import Image, ImageFilter, ImageDraw


class PhotoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'data')
        self.base=Path(self.tmp.name);self.source=self.base/'photos';self.source.mkdir()
        image=Image.new('RGB',(320,240),'#aa9988')
        draw=ImageDraw.Draw(image)
        for i in range(0,300,10):draw.line((i,0,320-i,240),fill='white',width=3)
        exif=Image.Exif();exif[272]='ZV-E10';exif[306]='2026:10:25 09:30:00'
        image.save(self.source/'sharp.jpg',exif=exif)
        shutil.copyfile(self.source/'sharp.jpg',self.source/'copy.jpg')
        image.filter(ImageFilter.GaussianBlur(5)).save(self.source/'blurred.jpg',exif=exif)
        self.project=Project(self.source,self.base/'store');self.project.analyze()

    def tearDown(self):self.tmp.cleanup()

    def application(self):
        return Application(self.source,self.base/'store')

    def test_complete_analysis_hashes_and_focus(self):
        rows=self.project.rows();self.assertEqual(3,len(rows));self.assertEqual([],self.project.report['errors'])
        byname={s['name']:s for s in rows}
        self.assertGreater(byname['sharp.jpg']['analysis']['focus'],byname['blurred.jpg']['analysis']['focus'])
        self.assertEqual(byname['sharp.jpg']['group_id'],byname['copy.jpg']['group_id'])
        self.assertEqual(3,self.project.audit()['unchanged'])
        self.assertEqual({'pending':3,'keep':0,'reject':0},self.project.public()['counts'])

    def test_persistence_rotation_undo_validation(self):
        sid=self.project.rows()[0]['id'];self.project.edit(sid,{'state':'keep','stars':4,'rotation':90})
        restored=Project(self.source,self.base/'store');shot=restored.shot(sid)
        self.assertEqual(('keep',4,90),(shot['state'],shot['stars'],shot['rotation']))
        restored.undo();self.assertEqual('pending',restored.shot(sid)['state'])
        for change in ({'state':'destroy'},{'stars':8},{'rotation':45},{'assets':[]}):
            with self.assertRaises(ValueError):restored.edit(sid,change)

    def test_group_manual_corrections_survive_regroup(self):
        rows=self.project.rows();ids=[r['id'] for r in rows]
        self.project.manual_group(ids,split=True);self.project.regroup('broad')
        self.assertEqual(3,len({r['group_id'] for r in self.project.rows()}))
        self.project.manual_group(ids);self.project.regroup('strict')
        self.assertEqual(1,len({r['group_id'] for r in self.project.rows()}))

    def test_stale_trash_batch_never_calls_delete(self):
        app=self.application();sid=app.project.rows()[0]['id'];app.project.edit(sid,{'state':'reject'})
        batch=app.prepare_trash();app.project.edit(sid,{'state':'keep'});called=[]
        with self.assertRaises(ValueError):app.commit_trash(batch['id'],True,lambda path:called.append(path))
        self.assertFalse(called);self.assertEqual(3,len(list(self.source.glob('*.jpg'))))

    def test_modified_source_aborts_whole_trash_batch(self):
        app=self.application();rows=app.project.rows()
        for row in rows:app.project.edit(row['id'],{'state':'reject'})
        batch=app.prepare_trash();path=Path(batch['items'][-1]['path']);path.write_bytes(path.read_bytes()+b'changed')
        called=[]
        with self.assertRaises(ValueError):app.commit_trash(batch['id'],True,lambda p:called.append(p))
        self.assertEqual([],called)

    def test_partial_pair_failure_is_reported_and_not_marked_trashed(self):
        app=self.application();shot=app.project.rows()[0];second=self.source/'paired.ARW';second.write_bytes(b'test-raw')
        assets=shot['assets']+[{'path':str(second),'name':second.name,'extension':'.arw',**fingerprint(second)}]
        analysis=shot['analysis'];analysis['hashes'][str(second)]=sha256(second)
        with app.project.connect() as con:
            con.execute('UPDATE shots SET assets=?,analysis=? WHERE id=?',(json.dumps(assets),json.dumps(analysis),shot['id']))
        app.project.edit(shot['id'],{'state':'reject'});batch=app.prepare_trash();calls=[]
        def partial(path):
            calls.append(path)
            if len(calls)==2:raise OSError('Simulated locked file')
            Path(path).rename(self.base/'simulated-trash.jpg')
        result=app.commit_trash(batch['id'],True,partial)
        self.assertEqual((1,1),(result['moved'],result['failed']));self.assertIsNotNone(app.project.shot(shot['id']))
        self.assertTrue(second.exists())

    def test_cancel_and_failed_trash_have_no_delete_fallback(self):
        app=self.application();sid=app.project.rows()[0]['id'];app.project.edit(sid,{'state':'reject'})
        batch=app.prepare_trash()
        with self.assertRaises(ValueError):app.commit_trash(batch['id'],False)
        batch=app.prepare_trash()
        def fail(path):raise OSError('Papelera no disponible')
        result=app.commit_trash(batch['id'],True,fail)
        self.assertEqual(1,result['failed']);self.assertTrue(Path(batch['items'][0]['path']).exists())
        with self.assertRaises(ValueError):app.commit_trash(batch['id'],True,fail)

    def test_successful_trash_records_only_moved_shot(self):
        app=self.application();sid=app.project.rows()[0]['id'];app.project.edit(sid,{'state':'reject'});batch=app.prepare_trash()
        def move(path):Path(path).rename(self.base/'simulated-trash.jpg')
        result=app.commit_trash(batch['id'],True,move)
        self.assertEqual(1,result['moved']);self.assertEqual(2,len(app.project.rows()))
        self.assertTrue((self.base/'simulated-trash.jpg').exists())

    def test_api_auth_origin_and_media(self):
        app=self.application();server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(app))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}'
        try:
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(base+'/api/state')
            self.assertEqual(403,e.exception.code)
            headers={'X-Session-Token':app.token}
            with urllib.request.urlopen(urllib.request.Request(base+'/api/state',headers=headers)) as response:data=json.load(response)
            self.assertEqual(3,len(data['shots']))
            sid=data['shots'][0]['id']
            with urllib.request.urlopen(base+f'/media/{sid}/preview?token='+app.token) as response:
                image=Image.open(io.BytesIO(response.read()));self.assertEqual((320,240),image.size)
            headers.update({'Origin':'https://evil.example','Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(base+'/api/edit',data=b'{}',headers=headers))
            self.assertEqual(403,e.exception.code)
            headers.pop('Origin')
            body=json.dumps({'id':sid,'changes':{'state':'keep'}}).encode()
            with urllib.request.urlopen(urllib.request.Request(base+'/api/edit',data=body,headers=headers)) as response:self.assertTrue(json.load(response)['ok'])
            self.assertEqual('keep',app.project.shot(sid)['state'])
            with urllib.request.urlopen(urllib.request.Request(base+'/api/export?format=csv',headers=headers)) as response:self.assertIn('keep',response.read().decode('utf-8-sig'))
        finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
