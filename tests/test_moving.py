import json
from pathlib import Path
import tempfile
import unittest
import sys
import threading
import urllib.request
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import Application, handler_for, ThreadingHTTPServer
from engine import Project, dumps, fingerprint, sha256
import moving


class MoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'data')
        self.base=Path(self.tmp.name);self.source=self.base/'photos';self.source.mkdir()
        for name in ['a.jpg','b.jpg']:
            Image.new('RGB',(40,60),'red').save(self.source/name)
        self.app=Application(self.source,self.base/'store');self.app.project.scan()
        for shot in self.app.project.rows():
            analysis={'hashes':{a['path']:sha256(a['path']) for a in shot['assets']}}
            with self.app.project.connect() as con:
                con.execute('UPDATE shots SET analysis=? WHERE id=?',(dumps(analysis),shot['id']))
            self.app.project.edit(shot['id'],{'state':'keep','stars':4,'rotation':90})

    def tearDown(self):self.tmp.cleanup()

    def test_move_preserves_identity_decisions_and_rescan(self):
        before=self.app.project.rows();batch=moving.prepare(self.app)
        result=moving.commit(self.app,batch['id'],True)
        self.assertEqual((2,0),(result['moved'],result['failed']))
        self.app.project.scan()
        after=self.app.project.rows()
        self.assertEqual([s['id'] for s in before],[s['id'] for s in after])
        for shot in after:
            self.assertEqual(('keep',4,90),(shot['state'],shot['stars'],shot['rotation']))
            for a in shot['assets']:
                self.assertEqual(self.source/'Seleccionadas',Path(a['path']).parent)
                self.assertEqual(shot['analysis']['hashes'][a['path']],sha256(self.app.project.source(a)))
        again=moving.prepare(self.app)
        self.assertEqual((0,2),(again['files'],again['skipped']))

    def test_changed_decision_and_file_abort_entire_batch(self):
        batch=moving.prepare(self.app)
        self.app.project.edit(batch['items'][-1]['shot_id'],{'state':'pending'})
        with self.assertRaises(ValueError):moving.commit(self.app,batch['id'],True)
        self.assertFalse((self.source/'Seleccionadas').exists())
        self.app.project.edit(batch['items'][-1]['shot_id'],{'state':'keep'})
        batch=moving.prepare(self.app)
        Path(batch['items'][-1]['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):moving.commit(self.app,batch['id'],True)
        self.assertTrue((self.source/'a.jpg').exists())

    def test_collision_before_and_after_prepare_never_overwrites(self):
        batch=moving.prepare(self.app);target=Path(batch['items'][0]['destination'])
        target.parent.mkdir();target.write_bytes(b'existing')
        with self.assertRaises(ValueError):moving.commit(self.app,batch['id'],True)
        with self.assertRaises(ValueError):moving.prepare(self.app)
        self.assertEqual(b'existing',target.read_bytes())
        self.assertTrue(Path(batch['items'][0]['path']).exists())

    def test_linked_raw_moves_with_jpeg_and_failure_keeps_catalog_usable(self):
        shot=self.app.project.rows()[0];raw=self.source/'a.ARW';raw.write_bytes(b'raw fixture')
        assets=shot['assets']+[{'path':str(raw),'name':raw.name,'extension':'.arw',**fingerprint(raw)}]
        analysis=shot['analysis'];analysis['hashes'][str(raw)]=sha256(raw)
        with self.app.project.connect() as con:
            con.execute('UPDATE shots SET assets=?,analysis=? WHERE id=?',(dumps(assets),dumps(analysis),shot['id']))
        batch=moving.prepare(self.app);calls=[]
        def fail_second(source,target):
            calls.append(str(source))
            if len(calls)==2:raise OSError('Archivo bloqueado')
            moving.move_exclusive(source,target)
        result=moving.commit(self.app,batch['id'],True,fail_second)
        self.assertEqual((1,1),(result['moved'],result['failed']))
        for current in self.app.project.rows():
            for a in current['assets']:self.assertTrue(self.app.project.source(a).exists())
        retry=moving.prepare(self.app);result=moving.commit(self.app,retry['id'],True)
        self.assertEqual(2,result['moved'])
        self.assertTrue((self.source/'Seleccionadas'/'a.ARW').exists())

    def test_reopen_recovers_interrupted_catalog_update(self):
        batch=moving.prepare(self.app);item=batch['items'][0]
        target=Path(item['destination']);target.parent.mkdir()
        with self.app.project.connect() as con:
            con.execute('INSERT INTO move_log VALUES(?,?,?,?,?,?,?)',('interrupted',item['shot_id'],item['path'],str(target),'started','',0))
        moving.move_exclusive(item['path'],target)
        reopened=Project(self.source,self.base/'store')
        self.assertEqual(str(target),reopened.shot(item['shot_id'])['assets'][0]['path'])
        reopened.scan();self.assertEqual(2,len(reopened.rows()))

    def test_same_names_in_subfolders_keep_relative_paths(self):
        sub=self.source/'nested';sub.mkdir();Image.new('RGB',(40,60),'blue').save(sub/'a.jpg')
        self.app.project.scan()
        shot=next(s for s in self.app.project.rows() if s['assets'][0]['path']==str(sub/'a.jpg'))
        with self.app.project.connect() as con:
            con.execute('UPDATE shots SET state=?,analysis=? WHERE id=?',('keep',dumps({'hashes':{str(sub/'a.jpg'):sha256(sub/'a.jpg')}}),shot['id']))
        batch=moving.prepare(self.app);result=moving.commit(self.app,batch['id'],True)
        self.assertEqual(3,result['moved'])
        self.assertTrue((self.source/'Seleccionadas'/'nested'/'a.jpg').exists())

    def test_http_prepare_commit_and_catalog_response(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(self.app))
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def post(path,body):
            request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/{path}',
                data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-Session-Token':self.app.token})
            with urllib.request.urlopen(request,timeout=10) as response:return json.load(response)
        try:
            batch=post('move/prepare',{})
            self.assertEqual(2,batch['files'])
            self.assertEqual(2,post('move/commit',{'id':batch['id'],'confirmed':True})['moved'])
            self.assertEqual(2,post('move/prepare',{})['skipped'])
            for s in self.app.project.rows():self.assertTrue(self.app.project.source(s['assets'][0]).exists())
        finally:server.shutdown();server.server_close();worker.join(timeout=3)


if __name__=='__main__':unittest.main()
