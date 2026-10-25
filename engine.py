"""Local photo analysis. All generated files live in the workspace data directory."""
from __future__ import annotations
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE / '.deps'))
os.environ.setdefault('OPENCV_LOG_LEVEL', 'ERROR')
import cv2
import numpy as np
from PIL import Image, ImageOps
import exifread
from editing import validate as validate_adjustments, rotate_crop, LutStore

cv2.setNumThreads(1)
VERSION = 'halloween-1.0'
EXTENSIONS = {'.jpg', '.jpeg', '.arw', '.png', '.tif', '.tiff'}
MODEL = BASE / 'models' / 'face_detection_yunet_2026may.onnx'


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def fingerprint(path):
    st = Path(path).stat()
    return {'size': st.st_size, 'mtime_ns': st.st_mtime_ns}


def sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def metadata(path):
    with open(path, 'rb') as stream:
        tags = exifread.process_file(stream, details=False, strict=False)
    def tag(*names):
        return next((str(tags[n]) for n in names if n in tags), '')
    captured = tag('EXIF DateTimeOriginal', 'Image DateTime')
    try:
        stamp = datetime.strptime(captured, '%Y:%m:%d %H:%M:%S').timestamp()
    except ValueError:
        stamp = Path(path).stat().st_mtime
    return {'captured': captured, 'timestamp': stamp, 'camera': tag('Image Model'),
            'make': tag('Image Make'), 'iso': tag('EXIF ISOSpeedRatings'),
            'shutter': tag('EXIF ExposureTime'), 'aperture': tag('EXIF FNumber'),
            'orientation': tag('Image Orientation')}


def read_image(path):
    path = Path(path)
    if path.suffix.lower() == '.arw':
        import rawpy
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(use_camera_wb=True, no_auto_bright=True, output_bps=8)
        return Image.fromarray(rgb), 'RAW revelado localmente'
    with Image.open(path) as source:
        im = ImageOps.exif_transpose(source).convert('RGB')
    return im, 'JPG original' if path.suffix.lower() in {'.jpg', '.jpeg'} else 'Imagen original'


def focus_measure(rgb):
    if rgb.size == 0 or min(rgb.shape[:2]) < 16:
        return None
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if max(gray.shape) > 512:
        gray = cv2.resize(gray, None, fx=512/max(gray.shape), fy=512/max(gray.shape), interpolation=cv2.INTER_AREA)
    gray = cv2.GaussianBlur(gray, (3, 3), 0.6)
    lap = float(cv2.Laplacian(gray, cv2.CV_32F).var())
    sobel = float(np.mean(cv2.Sobel(gray, cv2.CV_32F, 1, 0)**2 + cv2.Sobel(gray, cv2.CV_32F, 0, 1)**2))
    return math.log1p(lap) * 0.65 + math.log1p(sobel) * 0.35


def visual_feature(rgb):
    small = cv2.resize(rgb, (96, 96), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    dct = cv2.dct(cv2.resize(gray, (32, 32)).astype(np.float32))[:8, :8].flatten()
    bits = dct > np.median(dct[1:])
    bits[0] = False
    phash = sum(int(bit) << i for i, bit in enumerate(bits))
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 8], [0, 180, 0, 256]).flatten()
    hist /= max(float(np.linalg.norm(hist)), 1e-6)
    return {'phash': f'{phash:016x}', 'gray': base64.b64encode(gray.tobytes()).decode(), 'hist': hist.tolist()}


def similarity(a, b):
    if abs(math.log(a['width']/a['height']) - math.log(b['width']/b['height'])) > 0.25:
        return 64, 0.0, 0.0
    hamming = (int(a['feature']['phash'], 16) ^ int(b['feature']['phash'], 16)).bit_count()
    x = np.frombuffer(base64.b64decode(a['feature']['gray']), dtype=np.uint8).reshape(96, 96).astype(np.float32)
    y = np.frombuffer(base64.b64decode(b['feature']['gray']), dtype=np.uint8).reshape(96, 96).astype(np.float32)
    # Mean local SSIM; tolerant of small exposure changes, never an identity test.
    mx = cv2.GaussianBlur(x, (11, 11), 1.5)
    my = cv2.GaussianBlur(y, (11, 11), 1.5)
    vx = np.maximum(0, cv2.GaussianBlur(x*x, (11, 11), 1.5) - mx*mx)
    vy = np.maximum(0, cv2.GaussianBlur(y*y, (11, 11), 1.5) - my*my)
    cov = cv2.GaussianBlur(x*y, (11, 11), 1.5) - mx*my
    ssim = float(np.mean(((2*mx*my+6.5025)*(2*cov+58.5225))/((mx*mx+my*my+6.5025)*(vx+vy+58.5225))))
    color = float(np.dot(a['feature']['hist'], b['feature']['hist']))
    return hamming, ssim, color


class HashTree:
    def __init__(self):
        self.root = None

    def add(self, value, sid):
        node = self.root
        if node is None:
            self.root = [value, [sid], {}]
            return
        while True:
            distance = (node[0] ^ value).bit_count()
            if distance == 0:
                node[1].append(sid)
                return
            if distance not in node[2]:
                node[2][distance] = [value, [sid], {}]
                return
            node = node[2][distance]

    def search(self, value, radius):
        found, todo = [], [self.root] if self.root else []
        while todo:
            v, ids, children = todo.pop()
            d = (v ^ value).bit_count()
            if d <= radius:
                found.extend((d, sid) for sid in ids)
            todo.extend(child for edge, child in children.items() if d-radius <= edge <= d+radius)
        return sorted(found)[:30]


class Project:
    def __init__(self, root, data_root=None):
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ValueError('Selecciona una carpeta de fotografías.')
        self.id = hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        self.folder = Path(data_root or BASE / 'data') / self.id
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / 'cache').mkdir(exist_ok=True)
        self.db = self.folder / 'project.sqlite'
        self.lock = threading.RLock()
        self.run_lock = threading.Lock()
        self.cancel = threading.Event()
        self.job = {'running': False, 'stage': 'Listo', 'done': 0, 'total': 0, 'errors': []}
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS shots (
                    id TEXT PRIMARY KEY, name TEXT, assets TEXT, meta TEXT, analysis TEXT,
                    state TEXT NOT NULL DEFAULT 'pending', stars INTEGER NOT NULL DEFAULT 0,
                    rotation INTEGER NOT NULL DEFAULT 0, group_id TEXT, group_locked INTEGER DEFAULT 0,
                    trashed INTEGER DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0,
                    adjustments TEXT NOT NULL DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS history (seq INTEGER PRIMARY KEY, shot_id TEXT, previous TEXT);
                CREATE TABLE IF NOT EXISTS trash_log (operation TEXT, shot_id TEXT, path TEXT,
                    status TEXT, error TEXT, created REAL, PRIMARY KEY(operation,path));
            ''')
            if 'adjustments' not in {r['name'] for r in con.execute('PRAGMA table_info(shots)')}:
                backup=self.folder/'project.before-editing.sqlite'
                if not backup.exists():
                    destination=sqlite3.connect(backup)
                    try:con.backup(destination)
                    finally:destination.close()
                con.execute("ALTER TABLE shots ADD COLUMN adjustments TEXT NOT NULL DEFAULT '{}'")
        self.report = json.loads((self.folder/'report.json').read_text('utf-8')) if (self.folder/'report.json').exists() else None

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=20)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def rows(self):
        with self.lock, self.connect() as con:
            result = []
            for row in con.execute('SELECT * FROM shots WHERE trashed=0'):
                item = dict(row)
                for key in ('assets', 'meta', 'analysis', 'adjustments'):
                    item[key] = json.loads(item[key]) if item[key] else None
                item['adjustments']=validate_adjustments(item['adjustments'] or {})
                result.append(item)
        return sorted(result, key=lambda x: (x['meta']['timestamp'], x['name']))

    def shot(self, sid):
        return next((s for s in self.rows() if s['id'] == sid), None)

    def source(self, asset):
        path = Path(asset['path'])
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root) or path.is_symlink():
            raise ValueError('Archivo fuera de las carpetas autorizadas.')
        # Reject symlinked parent directories as well.
        if any(parent.is_symlink() for parent in path.parents if parent != self.root and parent.is_relative_to(self.root)):
            raise ValueError('No se admiten enlaces simbólicos.')
        if fingerprint(resolved) != {k: asset[k] for k in ('size', 'mtime_ns')}:
            raise ValueError('El archivo cambió desde el análisis; vuelve a analizarlo.')
        return resolved

    def scan(self):
        candidates, issues = {}, []
        for parent, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in sorted(dirs) if not (Path(parent)/d).is_symlink()]
            for name in sorted(files):
                path = Path(parent)/name
                if path.suffix.lower() not in EXTENSIONS or path.is_symlink():
                    continue
                st = path.stat()
                if getattr(st, 'st_file_attributes', 0) & (0x1000 | 0x400000):
                    issues.append({'file': str(path), 'error': 'Solo en la nube: omitida para evitar descargas.'})
                    continue
                try:
                    meta = metadata(path)
                    asset = {'path': str(path), 'name': name, 'extension': path.suffix.lower(), **fingerprint(path)}
                    key = (str(path.parent), path.stem.casefold())
                    candidates.setdefault(key, []).append((asset, meta))
                except Exception as exc:
                    issues.append({'file': str(path), 'error': str(exc)})
        count = 0
        with self.lock, self.connect() as con:
            for key, entries in candidates.items():
                jpeg = [e for e in entries if e[0]['extension'] in {'.jpg', '.jpeg'}]
                raw = [e for e in entries if e[0]['extension'] == '.arw']
                paired = len(entries) == 2 and len(jpeg) == 1 and len(raw) == 1
                paired = paired and bool(jpeg[0][1]['captured']) and jpeg[0][1]['captured'] == raw[0][1]['captured'] and jpeg[0][1]['camera'] == raw[0][1]['camera']
                sets = [entries] if paired else [[entry] for entry in entries]
                for group in sets:
                    assets = sorted([e[0] for e in group], key=lambda a: a['extension'] == '.arw')
                    meta = next(e[1] for e in group if e[0] == assets[0])
                    sid = hashlib.sha256('|'.join(a['path'] for a in assets).encode()).hexdigest()[:20]
                    old = con.execute('SELECT assets FROM shots WHERE id=?', (sid,)).fetchone()
                    encoded = dumps(assets)
                    con.execute('INSERT OR IGNORE INTO shots(id,name,assets,meta,group_id) VALUES(?,?,?,?,?)', (sid, assets[0]['name'], encoded, dumps(meta), sid))
                    if old and old['assets'] != encoded:
                        con.execute('UPDATE shots SET assets=?,meta=?,analysis=NULL,revision=revision+1 WHERE id=?', (encoded, dumps(meta), sid))
                    count += 1
        self.job.update(total=count, errors=issues)
        return count

    def analyze_one(self, shot):
        started = time.perf_counter()
        cached = shot['analysis']
        if cached and cached.get('version') == VERSION and all((self.folder/'cache'/f'{shot["id"]}_{v}.jpg').exists() for v in ('thumb', 'preview')):
            for asset in shot['assets']:
                self.source(asset)
            return cached
        hashes = {a['path']: sha256(self.source(a)) for a in shot['assets']}
        im, representation = read_image(shot['assets'][0]['path'])
        w, h = im.size
        rgb = np.asarray(im)
        small = cv2.resize(rgb, (round(w*min(1,960/max(w,h))), round(h*min(1,960/max(w,h)))), interpolation=cv2.INTER_AREA)
        faces = []
        if MODEL.exists():
            detector = cv2.FaceDetectorYN.create(str(MODEL), '', (small.shape[1], small.shape[0]), 0.8, 0.3, 500)
            _, detected = detector.detect(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
            if detected is not None:
                for face in detected:
                    x,y,fw,fh = [float(v) for v in face[:4]]
                    box = [max(0,x/small.shape[1]), max(0,y/small.shape[0]), min(1,(x+fw)/small.shape[1]), min(1,(y+fh)/small.shape[0])]
                    x1,y1,x2,y2 = int(box[0]*w),int(box[1]*h),int(box[2]*w),int(box[3]*h)
                    faces.append({'box': box, 'confidence': round(float(face[-1]),3), 'focus': focus_measure(rgb[y1:y2,x1:x2]), 'limited': min(x2-x1,y2-y1)<100})
        faces.sort(key=lambda f: (f['box'][2]-f['box'][0])*(f['box'][3]-f['box'][1]), reverse=True)
        # Central subject proxy when faces are covered; explicitly not confirmed subject focus.
        cx1,cy1,cx2,cy2 = int(w*.2),int(h*.2),int(w*.8),int(h*.8)
        general = focus_measure(rgb[cy1:cy2,cx1:cx2])
        primary = faces[0]['focus'] if faces and faces[0]['focus'] is not None else general
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        result = {'version':VERSION, 'width':w, 'height':h, 'representation':representation,
                  'hashes':hashes, 'focus':primary, 'general_focus':general, 'faces':faces,
                  'focus_basis':'rostro principal' if faces else 'zona central; sujeto sin confirmar',
                  'eyes':'not_evaluated', 'highlights':round(float(np.mean(gray >= 250))*100,1),
                  'shadows':round(float(np.mean(gray <= 5))*100,1), 'feature':visual_feature(small)}
        for variant, size, quality in [('thumb',360,80),('preview',1600,88)]:
            view=im.copy(); view.thumbnail((size,size),Image.Resampling.LANCZOS)
            target=self.folder/'cache'/f'{shot["id"]}_{variant}.jpg'
            temp=target.with_suffix('.tmp')
            view.save(temp,format='JPEG',quality=quality)
            temp.replace(target)
        for asset in shot['assets']:
            self.source(asset)
        result['seconds'] = round(time.perf_counter()-started,3)
        return result

    def analyze(self):
        if not self.run_lock.acquire(blocking=False):
            raise ValueError('Ya hay un análisis en curso.')
        start = time.perf_counter()
        self.cancel.clear()
        self.job = {'running':True,'stage':'Leyendo archivos','done':0,'total':0,'errors':[]}
        try:
            self.scan()
            shots = self.rows()
            self.job['stage'] = 'Analizando fotografías'
            with ThreadPoolExecutor(max_workers=2) as pool:
                pending = {}
                iterator = iter(shots)
                for _ in range(2):
                    shot = next(iterator, None)
                    if shot: pending[pool.submit(self.analyze_one, shot)] = shot
                while pending:
                    future = next(as_completed(pending))
                    shot = pending.pop(future)
                    try:
                        result = future.result()
                        with self.lock, self.connect() as con:
                            con.execute('UPDATE shots SET analysis=? WHERE id=?', (dumps(result),shot['id']))
                    except Exception as exc:
                        self.job['errors'].append({'file':shot['name'],'error':str(exc)})
                    self.job['done'] += 1
                    nxt = None if self.cancel.is_set() else next(iterator,None)
                    if nxt: pending[pool.submit(self.analyze_one,nxt)] = nxt
            if not self.cancel.is_set():
                self.job['stage'] = 'Agrupando tomas'
                self.regroup()
            rows=self.rows(); good=[s for s in rows if s['analysis']]
            groups={s['group_id'] for s in rows}
            self.report={'project':self.root.name,'source':str(self.root),'version':VERSION,
                         'created':datetime.now().isoformat(timespec='seconds'),'shots':len(rows),
                         'files':sum(len(s['assets']) for s in rows),'analyzed':len(good),
                         'groups':len(groups),'with_faces':sum(bool(s['analysis']['faces']) for s in good),
                         'seconds':round(time.perf_counter()-start,2),'cancelled':self.cancel.is_set(),
                         'errors':self.job['errors'],'originals_modified':False,
                         'note':'Agrupación y puntuación experimentales; precisión pendiente de revisión humana.'}
            (self.folder/'report.json').write_text(dumps(self.report),encoding='utf-8')
            manifest=[{'path':a['path'],'size':a['size'],'mtime_ns':a['mtime_ns'],'sha256':s['analysis']['hashes'][a['path']]} for s in good for a in s['assets']]
            (self.folder/'source_manifest.json').write_text(dumps(manifest),encoding='utf-8')
            return self.report
        finally:
            self.job.update(running=False, stage='Pausado' if self.cancel.is_set() else 'Listo')
            self.run_lock.release()

    def regroup(self, sensitivity='normal'):
        thresholds={'strict':(18,.40,.80),'normal':(26,.24,.65),'broad':(30,.16,.55)}
        if sensitivity not in thresholds: raise ValueError('Sensibilidad inválida.')
        maxhash,minssim,mincolor=thresholds[sensitivity]
        rows=[s for s in self.rows() if s['analysis']]
        byid={s['id']:s for s in rows}; assignments={}; reps={}; tree=HashTree(); exact={}; previous=None
        with self.lock, self.connect() as con:
            for shot in rows:
                sid=shot['id']; a=shot['analysis']; group=sid
                if shot['group_locked']:
                    group=shot['group_id']
                else:
                    digest=next(iter(a['hashes'].values()))
                    if digest in exact and not reps[assignments[exact[digest]]]['group_locked']:
                        group=assignments[exact[digest]]
                    elif previous and shot['meta']['camera']==previous['meta']['camera'] and 0 <= shot['meta']['timestamp']-previous['meta']['timestamp']<=45:
                        pg=assignments[previous['id']]
                        rep=reps[pg]
                        if not rep['group_locked']:
                            hd,ss,col=similarity(a,rep['analysis'])
                            hp,sp,cp=similarity(a,previous['analysis'])
                            if hd<=maxhash and ss>=minssim and col>=mincolor and hp<=maxhash and sp>=minssim and cp>=mincolor:
                                group=pg
                    if group==sid:
                        for _,other in tree.search(int(a['feature']['phash'],16),10):
                            candidate=reps[assignments[other]]
                            if candidate['group_locked']: continue
                            _,ss,col=similarity(a,candidate['analysis'])
                            if ss>=.82 and col>=.90:
                                group=assignments[other]; break
                    con.execute('UPDATE shots SET group_id=? WHERE id=?',(group,sid))
                assignments[sid]=group
                reps.setdefault(group,shot)
                exact.setdefault(next(iter(a['hashes'].values())),sid)
                tree.add(int(a['feature']['phash'],16),sid)
                previous=shot
        if self.report:
            self.report.update(groups=len(set(assignments.values())), grouping_sensitivity=sensitivity)
            (self.folder/'report.json').write_text(dumps(self.report),encoding='utf-8')

    def public(self):
        shots=self.rows(); grouped={}; counts={'pending':0,'keep':0,'reject':0}
        for shot in shots:
            counts[shot['state']]+=1
            a=shot['analysis']
            if a:
                shot['analysis']={k:v for k,v in a.items() if k not in {'feature','hashes'}}
            grouped.setdefault(shot['group_id'],[]).append(shot)
        groups=[]
        for gid,members in grouped.items():
            eligible=[s for s in members if s['analysis'] and s['analysis']['focus'] is not None]
            ranked=sorted(eligible,key=lambda s:s['analysis']['focus'],reverse=True)
            low=min((s['analysis']['focus'] for s in ranked),default=0)
            high=max((s['analysis']['focus'] for s in ranked),default=0)
            for shot in members:
                f=shot['analysis']['focus'] if shot['analysis'] else None
                shot['focus_score']=None if f is None else (50 if high-low<.15 else round((f-low)/(high-low)*100))
                shot['recommended']=bool(len(ranked)>1 and ranked[0]['id']==shot['id'] and high-low>=.15)
            groups.append({'id':gid,'count':len(members),'cover':members[0]['id'],
                           'best':ranked[0]['id'] if ranked else members[0]['id'],
                           'pending':sum(s['state']=='pending' for s in members)})
        return {'id':self.id,'name':self.root.name,'root':str(self.root),'shots':shots,'groups':groups,
                'counts':counts,'job':dict(self.job),'report':self.report}

    def edit(self, sid, changes):
        allowed={'state','stars','rotation','adjustments'}
        changes=dict(changes)
        if not changes or set(changes)-allowed: raise ValueError('Cambio no permitido.')
        if 'state' in changes and changes['state'] not in {'pending','keep','reject'}: raise ValueError('Estado inválido.')
        if 'stars' in changes and (type(changes['stars']) is not int or not 0<=changes['stars']<=5): raise ValueError('Estrellas inválidas.')
        if 'rotation' in changes and changes['rotation'] not in {0,90,180,270}: raise ValueError('Rotación inválida.')
        if 'adjustments' in changes:
            changes['adjustments']=validate_adjustments(changes['adjustments'])
            LutStore(self.folder/'luts').check(changes['adjustments']['lut'])
        with self.lock, self.connect() as con:
            row=con.execute('SELECT * FROM shots WHERE id=? AND trashed=0',(sid,)).fetchone()
            if not row: raise ValueError('Toma no encontrada.')
            if 'rotation' in changes and 'adjustments' not in changes and changes['rotation']!=row['rotation']:
                adjustments=validate_adjustments(json.loads(row['adjustments']))
                if adjustments['crop']:
                    adjustments['crop']=rotate_crop(adjustments['crop'],changes['rotation']-row['rotation'])
                    changes['adjustments']=adjustments
            previous={key:row[key] for key in changes}
            con.execute('INSERT INTO history(shot_id,previous) VALUES(?,?)',(sid,dumps(previous)))
            for key,value in changes.items():
                if key=='adjustments':value=dumps(value)
                con.execute(f'UPDATE shots SET {key}=?,revision=revision+1 WHERE id=?',(value,sid))

    def undo(self):
        with self.lock,self.connect() as con:
            row=con.execute('SELECT * FROM history ORDER BY seq DESC LIMIT 1').fetchone()
            if row:
                entries=json.loads(row['previous']) if row['shot_id']=='__batch__' else [{'id':row['shot_id'],'values':json.loads(row['previous'])}]
                for entry in entries:
                    for key,value in entry['values'].items():
                        if key not in {'state','stars','rotation','adjustments'}:raise ValueError('Historial de cambios inválido.')
                        con.execute(f'UPDATE shots SET {key}=?,revision=revision+1 WHERE id=? AND trashed=0',(value,entry['id']))
                con.execute('DELETE FROM history WHERE seq=?',(row['seq'],))

    def batch_color(self,ids,lut,intensity):
        settings=validate_adjustments({'lut':lut,'intensity':intensity})
        LutStore(self.folder/'luts').check(lut)
        if not isinstance(ids,list) or not ids or len(ids)>10000 or not all(isinstance(sid,str) for sid in ids):
            raise ValueError('Selecciona entre una y diez mil tomas.')
        ids=list(dict.fromkeys(ids))
        with self.lock,self.connect() as con:
            rows={row['id']:row for row in con.execute('SELECT id,adjustments FROM shots WHERE trashed=0')}
            if not set(ids)<=set(rows):raise ValueError('La selección contiene tomas no disponibles.')
            previous=[{'id':sid,'values':{'adjustments':rows[sid]['adjustments']}} for sid in ids]
            con.execute('INSERT INTO history(shot_id,previous) VALUES(?,?)',('__batch__',dumps(previous)))
            for sid in ids:
                adjusted=validate_adjustments(json.loads(rows[sid]['adjustments']))
                adjusted.update(lut=lut,intensity=settings['intensity'])
                con.execute('UPDATE shots SET adjustments=?,revision=revision+1 WHERE id=?',(dumps(adjusted),sid))

    def manual_group(self, ids, split=False):
        if self.job['running']: raise ValueError('Espera a que termine el análisis para cambiar grupos.')
        known={s['id'] for s in self.rows()}
        if not ids or not set(ids)<=known: raise ValueError('Selecciona tomas válidas.')
        gid=ids[0]
        with self.lock,self.connect() as con:
            for sid in ids:
                con.execute('UPDATE shots SET group_id=?,group_locked=1 WHERE id=?',(sid if split else gid,sid))

    def set_face(self, sid, index):
        if self.job['running']: raise ValueError('Espera a que termine el análisis.')
        shot=self.shot(sid)
        if not shot or not shot['analysis']: raise ValueError('Toma sin analizar.')
        a=shot['analysis']
        if type(index) is not int or not 0<=index<len(a['faces']): raise ValueError('Rostro inválido.')
        a['focus']=a['faces'][index]['focus'];a['focus_basis']=f'rostro elegido {index+1}';a['primary_face']=index
        with self.lock,self.connect() as con:
            con.execute('UPDATE shots SET analysis=? WHERE id=?',(dumps(a),sid))

    def audit(self):
        manifest=json.loads((self.folder/'source_manifest.json').read_text('utf-8'))
        changed=[]
        for entry in manifest:
            try:
                if fingerprint(entry['path'])!={k:entry[k] for k in ('size','mtime_ns')} or sha256(entry['path'])!=entry['sha256']:
                    changed.append(entry['path'])
            except OSError:
                changed.append(entry['path'])
        result={'checked':len(manifest),'unchanged':len(manifest)-len(changed),'changed':changed,'checked_at':datetime.now().isoformat(timespec='seconds')}
        (self.folder/'integrity.json').write_text(dumps(result),encoding='utf-8')
        return result
