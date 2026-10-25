import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageDraw
from editing import DEFAULT,LutStore,Renderer,parse_cube,validate,transform,rotate_crop,SRGB_BYTES
from engine import Project,sha256
from app import Application,handler_for,ThreadingHTTPServer


def cube(swap=False):
    values=[]
    for b in range(2):
        for g in range(2):
            for r in range(2):values.append(f'{b if swap else r} {g} {r if swap else b}')
    return 'TITLE "Test"\nLUT_3D_SIZE 2\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n'+'\n'.join(values)


class EditingTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'data')
        self.base=Path(self.tmp.name);self.source=self.base/'photos';self.source.mkdir()
        im=Image.new('RGB',(400,300),'#dccdbb');draw=ImageDraw.Draw(im)
        draw.rectangle((0,0,199,149),fill='#dd1111');draw.rectangle((200,150,399,299),fill='#1122dd')
        exif=Image.Exif();exif[272]='ZV-E10';exif[306]='2026:10:25 09:30:00'
        im.save(self.source/'first.jpg',exif=exif);im.save(self.source/'second.jpg',exif=exif)
        self.p=Project(self.source,self.base/'store');self.p.analyze()
        self.renderer=Renderer(self.p);self.shot=self.p.rows()[0]

    def tearDown(self):self.tmp.cleanup()

    def test_identity_lut_preserves_rgb(self):
        lut=self.renderer.luts.import_cube('identity.cube',cube(),True)
        rng=np.random.default_rng(20);pixels=rng.integers(0,256,(40,30,3),dtype=np.uint8)
        result=transform(Image.fromarray(pixels),0,{**DEFAULT,'lut':lut['id']},self.renderer.luts)
        self.assertLessEqual(np.abs(np.asarray(result).astype(int)-pixels).max(),1)

    def test_cube_rgb_order_and_intensity(self):
        lut=self.renderer.luts.import_cube('swap.cube',cube(True),True)
        im=Image.new('RGB',(20,10),(255,0,0))
        result=transform(im,0,{**DEFAULT,'lut':lut['id']},self.renderer.luts)
        self.assertEqual((0,0,255),result.getpixel((0,0)))
        zero=transform(im,0,{**DEFAULT,'lut':lut['id'],'intensity':0},self.renderer.luts)
        self.assertEqual((255,0,0),zero.getpixel((0,0)))
        half=transform(im,0,{**DEFAULT,'lut':lut['id'],'intensity':.5},self.renderer.luts)
        self.assertEqual((127,0,127),half.getpixel((0,0)))

    def test_cube_validation_rejects_incomplete_hdr_nonfinite_and_1d(self):
        bad=[cube().rsplit('\n',1)[0],cube()+'\n0 0 0',cube().replace('DOMAIN_MIN 0 0 0','DOMAIN_MIN -1 -1 -1'),
             cube().replace('0 0 0\n1 0 0','nan 0 0\n1 0 0'),cube().replace('LUT_3D_SIZE 2','LUT_1D_SIZE 2'),
             cube().replace('LUT_3D_SIZE 2','LUT_3D_SIZE 66'),cube().replace('1 1 1','2 1 1')]
        for text in bad:
            with self.subTest(text=text[:50]):
                with self.assertRaises(ValueError):parse_cube(text)
        with self.assertRaises(ValueError):self.renderer.luts.import_cube('test.cube',cube(),False)

    def test_settings_validation_bounds_and_no_path_traversal(self):
        invalid=[{'crop':[0,0,1.1,.5]},{'crop':[.9,0,.2,1]},{'crop':[0,0,.001,1]},
                 {'straighten':float('nan')},{'straighten':16},{'intensity':2},{'lut':'../secret'},{'exposure':4}]
        for settings in invalid:
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):validate(settings)

    def test_crop_rotation_keeps_same_region(self):
        with Image.open(self.source/'first.jpg') as image:
            crop=[0,0,.5,.5];first=transform(image,0,{**DEFAULT,'crop':crop},self.renderer.luts)
            second=transform(image,90,{**DEFAULT,'crop':rotate_crop(crop,90)},self.renderer.luts)
        self.assertTrue(np.array_equal(np.asarray(first.rotate(-90,expand=True)),np.asarray(second)))
        self.assertEqual([0,0,.5,.5],rotate_crop(crop,360))

    def test_straightening_has_no_black_corners(self):
        image=Image.new('RGB',(400,600),'white')
        for rotation in (0,90,270):
            for angle in (-15,5,15):
                result=transform(image,rotation,{**DEFAULT,'straighten':angle},self.renderer.luts)
                self.assertGreaterEqual(np.asarray(result).min(),250)
                self.assertLess(result.width*result.height,400*600)

    def test_edits_persist_and_undo_restores_exact_settings(self):
        settings={**DEFAULT,'crop':[.1,.2,.7,.6],'straighten':3,'lut':'warm','intensity':.6}
        sid=self.shot['id'];self.p.edit(sid,{'rotation':90,'adjustments':settings})
        reopened=Project(self.source,self.base/'store');row=reopened.shot(sid)
        self.assertEqual(settings,row['adjustments']);self.assertEqual(90,row['rotation'])
        reopened.undo();row=reopened.shot(sid);self.assertEqual(DEFAULT,row['adjustments']);self.assertEqual(0,row['rotation'])

    def test_rotation_of_saved_crop(self):
        sid=self.shot['id'];crop=[.1,.2,.4,.5]
        self.p.edit(sid,{'adjustments':{**DEFAULT,'crop':crop}});self.p.edit(sid,{'rotation':90})
        self.assertEqual(rotate_crop(crop,90),self.p.shot(sid)['adjustments']['crop'])

    def test_batch_color_preserves_geometry_and_undo_is_one_step(self):
        rows=self.p.rows();self.p.edit(rows[0]['id'],{'rotation':90,'adjustments':{**DEFAULT,'crop':[0,0,.5,.5]}})
        before={s['id']:s for s in self.p.rows()};self.p.batch_color(list(before),'cool',.5)
        for row in self.p.rows():
            self.assertEqual(before[row['id']]['rotation'],row['rotation'])
            self.assertEqual(before[row['id']]['adjustments']['crop'],row['adjustments']['crop'])
            self.assertEqual('cool',row['adjustments']['lut'])
        self.p.undo()
        for row in self.p.rows():self.assertEqual(before[row['id']]['adjustments'],row['adjustments'])

    def test_missing_lut_does_not_change_project(self):
        with self.assertRaises(ValueError):self.p.edit(self.shot['id'],{'adjustments':{'lut':'a'*24}})
        self.assertEqual(DEFAULT,self.p.shot(self.shot['id'])['adjustments'])

    def test_export_uses_full_resolution_after_preview(self):
        image=Image.new('RGB',(4000,3000),'#ccaa99');image.save(self.source/'large.jpg')
        self.p.analyze();shot=next(s for s in self.p.rows() if s['name']=='large.jpg')
        self.p.edit(shot['id'],{'adjustments':{**DEFAULT,'crop':[0,0,.5,.5]}});shot=self.p.shot(shot['id'])
        self.renderer.jpeg(shot,max_edge=1600,preview=True)
        payload=self.renderer.jpeg(shot,max_edge=1600)
        with Image.open(io.BytesIO(payload)) as exported:
            self.assertEqual((1600,1200),exported.size);self.assertTrue(exported.info['icc_profile'])

    def test_old_database_migration_keeps_decisions_and_creates_backup(self):
        sid=self.shot['id'];self.p.edit(sid,{'state':'keep','stars':4})
        with self.p.connect() as con:con.execute('ALTER TABLE shots DROP COLUMN adjustments')
        reopened=Project(self.source,self.base/'store')
        self.assertTrue((reopened.folder/'project.before-editing.sqlite').exists())
        self.assertEqual(('keep',4),(reopened.shot(sid)['state'],reopened.shot(sid)['stars']))
        self.assertEqual(DEFAULT,reopened.shot(sid)['adjustments'])

    def wait_export(self,app):
        deadline=time.monotonic()+15
        while app.export_job['running'] and time.monotonic()<deadline:time.sleep(.02)
        self.assertFalse(app.export_job['running'])

    def test_export_zip_contains_rendered_jpg_and_manifest_preserves_source(self):
        app=Application(self.source,self.base/'store');sid=self.shot['id'];before=sha256(self.source/'first.jpg')
        app.project.edit(sid,{'rotation':90,'adjustments':{**DEFAULT,'crop':[0,0,.5,1],'lut':'mono'}})
        job=app.start_export([sid]);self.wait_export(app)
        self.assertEqual(1,app.export_job['files']);self.assertEqual([],app.export_job['errors'])
        with zipfile.ZipFile(app.exports[job['id']]) as archive:
            names=archive.namelist();jpg=next(n for n in names if n.endswith('.jpg'))
            with Image.open(io.BytesIO(archive.read(jpg))) as im:
                self.assertEqual((150,400),im.size);self.assertTrue(im.info.get('icc_profile'));self.assertNotIn(274,im.getexif())
            manifest=json.loads(archive.read('ajustes.json'));self.assertEqual('mono',manifest['photos'][0]['adjustments']['lut'])
        self.assertEqual(before,sha256(self.source/'first.jpg'))

    def test_export_changed_source_reports_error_without_outputs(self):
        app=Application(self.source,self.base/'store');path=self.source/'first.jpg';path.write_bytes(path.read_bytes()+b'changed')
        app.start_export([self.shot['id']]);self.wait_export(app)
        self.assertEqual(0,app.export_job['files']);self.assertEqual(1,len(app.export_job['errors']))

    def test_http_edit_preview_import_export_and_revision_guard(self):
        app=Application(self.source,self.base/'store');server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(app));worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        base=f'http://127.0.0.1:{server.server_port}';headers={'X-Session-Token':app.token,'Content-Type':'application/json'}
        def request(path,payload=None):
            req=urllib.request.Request(base+path,headers=headers,data=json.dumps(payload).encode() if payload is not None else None)
            return urllib.request.urlopen(req,timeout=15)
        try:
            with request('/api/luts/import',{'name':'identity.cube','text':cube(),'srgb':True}) as response:lut=json.load(response)
            sid=self.shot['id'];revision=app.project.shot(sid)['revision']
            change={'id':sid,'revision':revision,'changes':{'adjustments':{**DEFAULT,'crop':[0,0,.5,1],'lut':lut['id']}}}
            with request('/api/edit',change) as response:self.assertTrue(json.load(response)['ok'])
            with self.assertRaises(urllib.error.HTTPError) as error:request('/api/edit',change)
            self.assertEqual(400,error.exception.code)
            with request(f'/media/{sid}/edited-preview') as response:
                with Image.open(io.BytesIO(response.read())) as image:self.assertEqual((200,300),image.size)
            with request('/api/render/start',{'ids':[sid],'max_edge':1600}) as response:job=json.load(response)
            self.wait_export(app)
            with request('/api/render/file/'+job['id']) as response:self.assertEqual('application/zip',response.headers['Content-Type']);self.assertTrue(zipfile.is_zipfile(io.BytesIO(response.read())))
        finally:server.shutdown();server.server_close();worker.join()


if __name__=='__main__':unittest.main()
