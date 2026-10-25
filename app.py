"""Small offline pilot: Python + existing browser, no cloud or npm runtime."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
import io
import json
import mimetypes
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import webbrowser
import zipfile

from engine import BASE, Project, dumps, fingerprint, sha256
from PIL import Image
from editing import Renderer, validate as validate_adjustments

DEFAULT_SOURCE = Path(r'C:\Users\ronig\OneDrive\Escritorio\halloween')
SETTINGS = BASE/'data'/'settings.json'


class Application:
    def __init__(self, source, data_root=None, trash_enabled=True):
        self.project = Project(source, data_root)
        self.data_root = data_root
        self.token = secrets.token_hex(32)
        self.trash_enabled = trash_enabled
        self.manifests = {}
        self.guard = threading.RLock()
        self.renderer=Renderer(self.project)
        self.export_job={'running':False}
        self.export_cancel=threading.Event()
        self.exports={}

    def start_export(self,ids,max_edge=0,quality=95):
        if self.export_job['running']:raise ValueError('Ya hay una exportación en curso.')
        if not isinstance(ids,list) or not ids or len(ids)>10000 or not all(isinstance(s,str) for s in ids):
            raise ValueError('Selecciona entre una y diez mil tomas para exportar.')
        if type(max_edge) is not int or not (max_edge==0 or 320<=max_edge<=12000):raise ValueError('Resolución de salida inválida.')
        if type(quality) is not int or not 80<=quality<=100:raise ValueError('La calidad debe estar entre 80 y 100.')
        project=self.project;renderer=self.renderer
        known={s['id']:s for s in project.rows()};ids=list(dict.fromkeys(ids))
        if not set(ids)<=set(known):raise ValueError('La selección contiene tomas no disponibles.')
        shots=[known[sid] for sid in ids]
        if any(not s['analysis'] for s in shots):raise ValueError('Analiza las fotos antes de exportarlas.')
        nonce=secrets.token_hex(16);folder=project.folder/'exports'/nonce;folder.mkdir(parents=True)
        self.export_cancel.clear()
        job={'id':nonce,'project_id':project.id,'running':True,'done':0,'total':len(shots),'files':0,'errors':[],'cancelled':False}
        self.export_job=job
        def run():
            records=[];written=[];started=time.perf_counter()
            try:
                for shot in shots:
                    if self.export_cancel.is_set():job['cancelled']=True;break
                    try:
                        asset=shot['assets'][0];source=project.source(asset)
                        if sha256(source)!=shot['analysis']['hashes'][asset['path']]:raise ValueError('El original cambió desde su análisis.')
                        payload=renderer.jpeg(shot,max_edge=max_edge,quality=quality)
                        project.source(asset)
                        name=f'{Path(shot["name"]).stem}-editada-{shot["id"][:8]}.jpg'
                        with (folder/name).open('xb') as stream:stream.write(payload)
                        written.append(name);job['files']+=1
                        records.append({'id':shot['id'],'source':asset['path'],'output':name,'rotation':shot['rotation'],
                                        'adjustments':shot['adjustments'],'state':shot['state'],'stars':shot['stars']})
                    except Exception as exc:job['errors'].append({'file':shot['name'],'error':str(exc)})
                    job['done']+=1
                manifest={'project':project.root.name,'color_space':'sRGB','quality':quality,'max_edge':max_edge,
                          'cancelled':job['cancelled'],'errors':job['errors'],'photos':records}
                (folder/'ajustes.json').write_text(dumps(manifest),encoding='utf-8')
                archive=folder/'seleccion-editada.zip'
                with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_STORED) as bundle:
                    for name in written+['ajustes.json']:bundle.write(folder/name,arcname=name)
                self.exports[nonce]=archive
                job.update(ready=True,seconds=round(time.perf_counter()-started,2))
            except Exception as exc:job.update(error=str(exc),ready=False)
            finally:
                job['running']=False
                (folder/'resultado.json').write_text(dumps(job),encoding='utf-8')
        threading.Thread(target=run,daemon=True,name='photo-export').start()
        return dict(job)

    def start_analysis(self):
        if self.project.job['running']: raise ValueError('Ya se está analizando.')
        project=self.project
        project.job['running']=True
        def run():
            try: project.analyze()
            except Exception as exc:
                project.job.update(running=False,stage='Error')
                project.job['errors'].append({'error':str(exc)})
        threading.Thread(target=run,daemon=True,name='photo-analysis').start()

    def prepare_trash(self):
        if self.export_job['running']:raise ValueError('Espera a que termine la exportación antes de preparar la papelera.')
        if self.project.job['running']: raise ValueError('Espera a que termine el análisis.')
        items=[]
        for shot in self.project.rows():
            if shot['state']!='reject': continue
            if not shot['analysis']: raise ValueError('Analiza las fotos rechazadas antes de enviarlas a la papelera.')
            for asset in shot['assets']:
                self.project.source(asset)
                items.append({'shot_id':shot['id'],'revision':shot['revision'],**asset,
                              'sha256':shot['analysis']['hashes'][asset['path']]})
        nonce=secrets.token_hex(24)
        self.manifests={k:v for k,v in self.manifests.items() if time.time()-v['created']<600}
        result={'id':nonce,'created':time.time(),'items':items,'shots':len({x['shot_id'] for x in items}),
                'files':len(items),'bytes':sum(x['size'] for x in items),'root':str(self.project.root),
                'project_id':self.project.id}
        self.manifests[nonce]=result
        return result

    def commit_trash(self, nonce, confirmed, trash_func=None):
        if self.export_job['running']:raise ValueError('Espera a que termine la exportación.')
        if not self.trash_enabled: raise ValueError('La papelera está desactivada en este modo de prueba.')
        manifest=self.manifests.pop(nonce,None)
        if confirmed is not True or not manifest or time.time()-manifest['created']>600:
            raise ValueError('La confirmación expiró o no es válida. Revisa el lote de nuevo.')
        project=self.project
        if manifest['project_id']!=project.id: raise ValueError('El proyecto cambió; prepara un lote nuevo.')
        if project.job['running']: raise ValueError('Hay un análisis en curso.')
        if trash_func is None:
            from send2trash import send2trash
            trash_func=send2trash
        results=[]
        with project.lock:
            current={s['id']:s for s in project.rows()}
            # Validate the ENTIRE batch before touching its first file.
            for item in manifest['items']:
                shot=current.get(item['shot_id'])
                if not shot or shot['state']!='reject' or shot['revision']!=item['revision']:
                    raise ValueError('Las decisiones cambiaron. Revisa el lote de nuevo.')
                project.source(item)
                if sha256(item['path'])!=item['sha256']:
                    raise ValueError('Un original cambió; operación cancelada.')
            for item in manifest['items']:
                with project.connect() as con:
                    con.execute('INSERT INTO trash_log VALUES(?,?,?,?,?,?)',
                                (nonce,item['shot_id'],item['path'],'started','',time.time()))
                try:
                    project.source(item)
                    trash_func(item['path'])
                    status,error='moved',''
                except Exception as exc:
                    status,error='failed',str(exc)
                with project.connect() as con:
                    con.execute('UPDATE trash_log SET status=?,error=? WHERE operation=? AND path=?',
                                (status,error,nonce,item['path']))
                results.append({'path':item['path'],'status':status,'error':error})
                if status=='failed': break
            for sid in {r['shot_id'] for r in manifest['items']}:
                shot=current[sid]
                expected={a['path'] for a in shot['assets']}
                moved={r['path'] for r in results if r['status']=='moved'}
                if expected<=moved:
                    with project.connect() as con:
                        con.execute('UPDATE shots SET trashed=1,revision=revision+1 WHERE id=?',(sid,))
            with project.connect() as con:
                con.execute('DELETE FROM history')
        return {'results':results,'moved':sum(r['status']=='moved' for r in results),
                'failed':sum(r['status']=='failed' for r in results),
                'not_attempted':len(manifest['items'])-len(results)}


def handler_for(application):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if args and str(args[1] if len(args)>1 else '').startswith('5'):
                print('HTTP error',args,flush=True)

        def respond(self, payload, status=200, content_type='application/json; charset=utf-8', filename=None):
            if not isinstance(payload,bytes): payload=dumps(payload).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('X-Application','SelectorLocal')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
            self.end_headers()
            try: self.wfile.write(payload)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass

        def authorized(self, require_token=True):
            expected=f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host')!=expected:
                self.respond({'error':'Host no permitido.'},403);return False
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{expected}':
                self.respond({'error':'Origen no permitido.'},403);return False
            if require_token:
                params=parse_qs(urlparse(self.path).query)
                token=self.headers.get('X-Session-Token') or params.get('token',[''])[0]
                if not secrets.compare_digest(token,application.token):
                    self.respond({'error':'Sesión no autorizada.'},403);return False
            return True

        def do_GET(self):
            parsed=urlparse(self.path);path=parsed.path
            protected=path.startswith('/api/') or path.startswith('/media/')
            if not self.authorized(protected): return
            try:
                if path=='/':
                    payload=(BASE/'web'/'index.html').read_text('utf-8').replace('__TOKEN__',application.token)
                    return self.respond(payload.encode(),content_type='text/html; charset=utf-8')
                if path in {'/app.js','/editor.js','/style.css'}:
                    return self.respond((BASE/'web'/path[1:]).read_bytes(),content_type='text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
                if path=='/favicon.ico': return self.respond(b'',204,'image/x-icon')
                project=application.project
                if path=='/api/state':
                    data=project.public();data.update(luts=application.renderer.luts.listing(),export_job=dict(application.export_job))
                    return self.respond(data)
                if path.startswith('/api/render/file/'):
                    key=path.rsplit('/',1)[-1];archive=application.exports.get(key)
                    if not archive or not archive.exists():raise ValueError('La exportación todavía no está disponible.')
                    return self.send_file(archive,'application/zip','seleccion-editada.zip')
                if path=='/api/export':
                    data=project.public();fmt=parse_qs(parsed.query).get('format',['json'])[0]
                    records=[{'name':s['name'],'state':s['state'],'stars':s['stars'],'rotation':s['rotation'],'adjustments':s['adjustments'],
                              'group':s['group_id'],'files':[a['path'] for a in s['assets']]} for s in data['shots']]
                    if fmt=='csv':
                        stream=io.StringIO(newline='');writer=csv.writer(stream)
                        writer.writerow(['nombre','estado','estrellas','rotacion','grupo','archivos','ajustes_json'])
                        for record in records:
                            # Prevent spreadsheet formula injection in filenames and paths.
                            vals=[record[k] for k in ('name','state','stars','rotation','group')]+[' | '.join(record['files']),dumps(record['adjustments'])]
                            writer.writerow(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in vals])
                        return self.respond(stream.getvalue().encode('utf-8-sig'),content_type='text/csv; charset=utf-8',filename='seleccion.csv')
                    return self.respond(dumps({'project':data['name'],'source':data['root'],'shots':records}).encode(),filename='seleccion.json')
                if path.startswith('/media/'):
                    parts=path.split('/')
                    if len(parts)!=4: raise ValueError('Vista inválida.')
                    sid,variant=parts[2:];shot=project.shot(sid)
                    if not shot or not shot['analysis']: raise ValueError('Vista no disponible aún.')
                    params=parse_qs(parsed.query);rotation=int(params.get('rotation',['0'])[0])
                    if rotation not in {0,90,180,270}: raise ValueError('Rotación inválida.')
                    if variant=='edit-base' or variant.startswith('edited-'):
                        if variant=='edit-base':
                            raw=params.get('draft',['{}'])[0]
                            if len(raw)>4096:raise ValueError('Ajustes demasiado grandes.')
                            settings=validate_adjustments(json.loads(raw));settings['crop']=None
                            payload=application.renderer.jpeg(shot,max_edge=1400,settings=settings,rotation=rotation,preview=True)
                        else:
                            sizes={'edited-thumb':360,'edited-preview':1600,'edited-original':0}
                            if variant not in sizes:raise ValueError('Vista de edición inválida.')
                            payload=application.renderer.jpeg(shot,max_edge=sizes[variant],preview=variant!='edited-original')
                        return self.respond(payload,content_type='image/jpeg')
                    if variant.startswith('face-'):
                        index=int(variant[5:]);faces=shot['analysis']['faces']
                        if not 0<=index<len(faces): raise ValueError('Rostro inválido.')
                        with Image.open(project.folder/'cache'/f'{sid}_preview.jpg') as im:
                            box=faces[index]['box'];w,h=im.size
                            pad=.06
                            im=im.crop((max(0,int((box[0]-pad)*w)),max(0,int((box[1]-pad)*h)),min(w,int((box[2]+pad)*w)),min(h,int((box[3]+pad)*h))))
                            im.thumbnail((360,360));buf=io.BytesIO();im.save(buf,format='JPEG',quality=90)
                        return self.respond(buf.getvalue(),content_type='image/jpeg')
                    if variant=='original':
                        asset=shot['assets'][0];source=project.source(asset)
                        if source.suffix.lower() in {'.jpg','.jpeg','.png'}:
                            if not rotation:
                                return self.respond(source.read_bytes(),content_type=mimetypes.guess_type(source.name)[0] or 'image/jpeg')
                            from engine import read_image
                            im,_=read_image(source)
                        else:
                            from engine import read_image
                            im,_=read_image(source)
                    elif variant in {'thumb','preview'}:
                        cached=project.folder/'cache'/f'{sid}_{variant}.jpg'
                        if not rotation: return self.respond(cached.read_bytes(),content_type='image/jpeg')
                        im=Image.open(cached)
                    else: raise ValueError('Vista inválida.')
                    with im:
                        view=im.rotate(-rotation,expand=True);buf=io.BytesIO();view.save(buf,format='JPEG',quality=93)
                    return self.respond(buf.getvalue(),content_type='image/jpeg')
                self.respond({'error':'No encontrado.'},404)
            except (ValueError,FileNotFoundError,KeyError) as exc:
                self.respond({'error':str(exc)},400)
            except Exception as exc:
                self.respond({'error':str(exc)},500)

        def do_POST(self):
            if not self.authorized(): return
            try:
                if self.headers.get('Content-Type','').split(';')[0]!='application/json': raise ValueError('Se requiere JSON.')
                length=int(self.headers.get('Content-Length','0'))
                limit=16*1024*1024 if urlparse(self.path).path=='/api/luts/import' else 256_000
                if not 0<length<=limit: raise ValueError('Petición demasiado grande o vacía.')
                payload=json.loads(self.rfile.read(length))
                if not isinstance(payload,dict): raise ValueError('Petición inválida.')
                path=urlparse(self.path).path;project=application.project
                with application.guard:
                    if path=='/api/edit':
                        if 'revision' in payload:
                            existing=project.shot(payload['id'])
                            if not existing or type(payload['revision']) is not int or payload['revision']!=existing['revision']:
                                raise ValueError('La foto cambió desde que abriste el editor. Cancela y vuelve a abrirlo para cargar los ajustes actuales.')
                        project.edit(payload['id'],payload['changes'])
                    elif path=='/api/undo': project.undo()
                    elif path=='/api/group': project.manual_group(payload['ids'],payload.get('split',False))
                    elif path=='/api/face': project.set_face(payload['id'],payload['index'])
                    elif path=='/api/luts/import':return self.respond(application.renderer.luts.import_cube(payload['name'],payload['text'],payload.get('srgb')))
                    elif path=='/api/color/batch':project.batch_color(payload['ids'],payload.get('lut'),payload.get('intensity',1))
                    elif path=='/api/render/start':return self.respond(application.start_export(payload['ids'],payload.get('max_edge',0),payload.get('quality',95)))
                    elif path=='/api/render/cancel':application.export_cancel.set()
                    elif path=='/api/regroup':
                        if project.job['running']: raise ValueError('Espera a que termine el análisis.')
                        project.regroup(payload.get('sensitivity','normal'))
                    elif path=='/api/analyze': application.start_analysis()
                    elif path=='/api/pause': project.cancel.set()
                    elif path=='/api/open':
                        if application.export_job['running']:raise ValueError('Espera o cancela la exportación antes de cambiar de proyecto.')
                        if project.job['running']: raise ValueError('Pausa el análisis antes de cambiar de proyecto.')
                        application.project=Project(payload['path'],application.data_root)
                        application.renderer=Renderer(application.project)
                        SETTINGS.parent.mkdir(exist_ok=True)
                        SETTINGS.write_text(dumps({'source':str(application.project.root)}),encoding='utf-8')
                    elif path=='/api/trash/prepare': return self.respond(application.prepare_trash())
                    elif path=='/api/trash/commit': return self.respond(application.commit_trash(payload['id'],payload.get('confirmed')))
                    elif path=='/api/shutdown':
                        if application.export_job['running']:raise ValueError('Espera a que termine la exportación o cancélala antes de cerrar.')
                        project.cancel.set()
                        self.respond({'ok':True})
                        threading.Thread(target=self.server.shutdown,daemon=True).start();return
                    else: return self.respond({'error':'No encontrado.'},404)
                return self.respond({'ok':True})
            except (ValueError,KeyError,TypeError,FileNotFoundError) as exc:
                self.respond({'error':str(exc)},400)
            except Exception as exc:
                self.respond({'error':str(exc)},500)

        def send_file(self,path,content_type,filename):
            # Stream large ZIP files; never read an entire session's export into RAM.
            with path.open('rb') as stream:
                self.send_response(200)
                self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(path.stat().st_size))
                self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Cross-Origin-Resource-Policy','same-origin')
                self.end_headers()
                try:
                    for block in iter(lambda:stream.read(1024*1024),b''):self.wfile.write(block)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
    return Handler


def main():
    parser=argparse.ArgumentParser(description='Selector local de fotografías')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--analyze',action='store_true',help='Analizar toda la sesión sin abrir servidor')
    parser.add_argument('--audit',action='store_true',help='Comprobar hashes de originales')
    parser.add_argument('--open',action='store_true',help='Abrir la interfaz en el navegador')
    parser.add_argument('--no-trash',action='store_true')
    args=parser.parse_args()
    source=args.source
    if not source and SETTINGS.exists(): source=Path(json.loads(SETTINGS.read_text('utf-8'))['source'])
    source=source or (DEFAULT_SOURCE if DEFAULT_SOURCE.exists() else Path.home()/'Pictures')
    if args.analyze or args.audit:
        project=Project(source)
        if args.analyze:
            def progress():
                while not stop.wait(5): print(dumps(project.job),flush=True)
            stop=threading.Event();threading.Thread(target=progress,daemon=True).start()
            try: print(dumps(project.analyze()),flush=True)
            finally: stop.set()
            SETTINGS.parent.mkdir(exist_ok=True)
            SETTINGS.write_text(dumps({'source':str(source.resolve())}),encoding='utf-8')
        if args.audit: print(dumps(project.audit()),flush=True)
        return
    application=Application(source,trash_enabled=not args.no_trash)
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),handler_for(application))
    except OSError:
        # Reopening the launcher must not start a second writer for the same port.
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/',timeout=2) as response:
                if response.headers.get('X-Application')!='SelectorLocal': raise RuntimeError('Puerto ocupado por otra aplicación.')
            if args.open: webbrowser.open(f'http://127.0.0.1:{args.port}/')
            return
        except Exception: raise RuntimeError('El puerto está ocupado; utiliza --port con otro número.')
    print(f'Selector local: http://127.0.0.1:{args.port}/',flush=True)
    if args.open: webbrowser.open(f'http://127.0.0.1:{args.port}/')
    try: server.serve_forever()
    except KeyboardInterrupt: application.project.cancel.set()
    finally: server.server_close()


if __name__=='__main__':
    main()
