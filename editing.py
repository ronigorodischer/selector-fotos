"""Deterministic non-destructive SDR edits, shared by previews and JPG export."""
from __future__ import annotations
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import re
import threading

from PIL import Image, ImageCms, ImageFilter

DEFAULT = {'crop': None, 'straighten': 0.0, 'lut': None, 'intensity': 1.0}
BUILTINS = [
    {'id':'warm','name':'Cálido suave','builtin':True},
    {'id':'cool','name':'Frío suave','builtin':True},
    {'id':'mono','name':'Blanco y negro','builtin':True},
]
SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB'))
SRGB_BYTES = SRGB.tobytes()


def validate(settings):
    if not isinstance(settings,dict) or set(settings)-set(DEFAULT):
        raise ValueError('Ajustes de imagen inválidos.')
    result={**DEFAULT,**settings}
    for key,minimum,maximum in [('straighten',-15,15),('intensity',0,1)]:
        value=result[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not minimum<=value<=maximum:
            raise ValueError(f'{key}: valor fuera de rango.')
        result[key]=round(float(value),5)
    crop=result['crop']
    if crop is not None:
        if not isinstance(crop,list) or len(crop)!=4 or any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in crop):
            raise ValueError('El recorte requiere [x,y,ancho,alto].')
        x,y,w,h=[float(n) for n in crop]
        if min(x,y)<0 or min(w,h)<.01 or x+w>1.000001 or y+h>1.000001:
            raise ValueError('El recorte debe quedar dentro de la imagen y tener al menos 1 % de ancho y alto.')
        result['crop']=[round(n,7) for n in (x,y,w,h)]
    lut=result['lut']
    if lut is not None and (not isinstance(lut,str) or not (lut in {'warm','cool','mono'} or re.fullmatch(r'[a-f0-9]{24}',lut))):
        raise ValueError('LUT no válido.')
    return result


def rotate_crop(crop, degrees):
    if crop is None:return None
    x,y,w,h=crop
    for _ in range((degrees%360)//90):x,y,w,h=1-y-h,x,h,w
    return [round(max(0,x),7),round(max(0,y),7),round(w,7),round(h,7)]


def parse_cube(text):
    if not isinstance(text,str) or len(text.encode('utf-8'))>12*1024*1024:
        raise ValueError('El LUT supera el límite de 12 MB.')
    size=None;table=[];title='LUT importado';seen=set()
    for line_number,line in enumerate(text.lstrip('\ufeff').splitlines(),1):
        line=line.split('#',1)[0].strip()
        if not line:continue
        parts=line.split();key=parts[0]
        if key in {'TITLE','LUT_3D_SIZE','DOMAIN_MIN','DOMAIN_MAX','LUT_3D_INPUT_RANGE'}:
            if key in seen:raise ValueError(f'Cabecera repetida: {key}.')
            if table:raise ValueError('Las cabeceras deben preceder a la tabla de color.')
            seen.add(key)
            if key=='TITLE':title=line[5:].strip().strip('"')[:120] or title
            elif key=='LUT_3D_SIZE':
                if len(parts)!=2:raise ValueError('LUT_3D_SIZE inválido.')
                try:size=int(parts[1])
                except ValueError:raise ValueError('El tamaño del LUT debe ser entero.')
                if not 2<=size<=65:raise ValueError('Se admiten LUTs 3D de tamaño 2 a 65.')
            else:
                expected={'DOMAIN_MIN':[0,0,0],'DOMAIN_MAX':[1,1,1],'LUT_3D_INPUT_RANGE':[0,1]}[key]
                try:values=[float(x) for x in parts[1:]]
                except ValueError:raise ValueError('Dominio del LUT inválido.')
                if values!=expected:raise ValueError('Este editor solo admite LUTs SDR con dominio 0–1 y entrada/salida sRGB.')
            continue
        if size is None or len(parts)!=3:raise ValueError(f'Línea {line_number}: se requiere una tabla 3D .cube sin shaper 1D.')
        try:values=[float(v) for v in parts]
        except ValueError:raise ValueError(f'Línea {line_number}: valores no numéricos.')
        if not all(math.isfinite(v) and 0<=v<=1 for v in values):
            raise ValueError('Solo se admiten valores SDR finitos entre 0 y 1.')
        table.extend(values)
        if len(table)>size**3*3:raise ValueError('El LUT contiene más entradas de las declaradas.')
    if size is None or len(table)!=size**3*3:raise ValueError('La cantidad de entradas no coincide con LUT_3D_SIZE³.')
    return {'name':title,'size':size,'table':table}


class LutStore:
    def __init__(self, folder):
        self.folder=Path(folder);self.folder.mkdir(exist_ok=True,parents=True)

    def listing(self):
        imported=[]
        for p in sorted(self.folder.glob('*.json')):
            data=json.loads(p.read_text('utf-8'))
            imported.append({'id':p.stem,'name':data['name'],'builtin':False})
        return BUILTINS+imported

    def import_cube(self,name,text,srgb):
        if srgb is not True:raise ValueError('Confirma que el LUT fue creado para entrada y salida sRGB, no Log ni HLG.')
        if not isinstance(name,str) or not name.lower().endswith('.cube'):raise ValueError('Selecciona un archivo .cube.')
        data=parse_cube(text)
        data['name']=Path(name.replace('\\','/')).stem[:120] or data['name']
        lut_id=hashlib.sha256(text.encode('utf-8')).hexdigest()[:24]
        destination=self.folder/f'{lut_id}.json'
        if not destination.exists():destination.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        return {'id':lut_id,'name':data['name'],'builtin':False}

    def check(self,lut_id):
        if lut_id is not None:self.filter(lut_id)

    @lru_cache(maxsize=8)
    def filter(self,lut_id):
        if lut_id=='warm':
            return ImageFilter.Color3DLUT.generate(17,lambda r,g,b:(min(1,r*1.025+.012),min(1,g*1.005+.004),max(0,b*.965)),target_mode='RGB')
        if lut_id=='cool':
            return ImageFilter.Color3DLUT.generate(17,lambda r,g,b:(r*.975,min(1,g*1.005+.003),min(1,b*1.025+.01)),target_mode='RGB')
        if lut_id=='mono':
            return ImageFilter.Color3DLUT.generate(17,lambda r,g,b:(.2126*r+.7152*g+.0722*b,)*3,target_mode='RGB')
        if not isinstance(lut_id,str) or not re.fullmatch(r'[a-f0-9]{24}',lut_id):raise ValueError('LUT desconocido.')
        path=self.folder/f'{lut_id}.json'
        if not path.exists():raise ValueError('El LUT importado no está disponible en este proyecto.')
        data=json.loads(path.read_text('utf-8'))
        return ImageFilter.Color3DLUT(data['size'],data['table'],channels=3,target_mode='RGB')


def to_srgb(image):
    icc=image.info.get('icc_profile')
    if icc:
        try:
            profile=ImageCms.ImageCmsProfile(io.BytesIO(icc))
            result=ImageCms.profileToProfile(image,profile,SRGB,outputMode='RGB')
        except (ImageCms.PyCMSError,ValueError,OSError) as exc:
            raise ValueError('No se puede convertir el perfil ICC de esta fotografía a sRGB.') from exc
    else:result=image.convert('RGB')
    result.info.clear()
    return result


def geometry(image,rotation,angle):
    if rotation not in {0,90,180,270}:raise ValueError('Giro inválido.')
    result=image.rotate(-rotation,expand=True) if rotation else image.copy()
    if angle:
        width,height=result.size;t=abs(math.radians(angle));c,s=math.cos(t),math.sin(t)
        scale=min(width/(width*c+height*s),height/(width*s+height*c))
        # An inscribed rectangle, with the same aspect ratio, avoids black corners.
        neww=max(1,int(width*scale)-2);newh=max(1,int(height*scale)-2)
        turned=result.rotate(-angle,resample=Image.Resampling.BICUBIC,expand=False)
        left=(width-neww)//2;top=(height-newh)//2
        result=turned.crop((left,top,left+neww,top+newh))
    return result


def transform(image,rotation,settings,luts):
    settings=validate(settings)
    result=geometry(image,rotation,settings['straighten'])
    if settings['crop']:
        x,y,w,h=settings['crop'];width,height=result.size
        box=tuple(int(math.floor(v+.5)) for v in (x*width,y*height,(x+w)*width,(y+h)*height))
        if box[2]<=box[0] or box[3]<=box[1]:raise ValueError('El recorte no contiene píxeles suficientes.')
        result=result.crop(box)
    if settings['lut'] and settings['intensity']:
        graded=result.filter(luts.filter(settings['lut']))
        result=Image.blend(result,graded,settings['intensity'])
    return result


class Renderer:
    def __init__(self,project):
        self.project=project
        self.luts=LutStore(project.folder/'luts')
        self.lock=threading.RLock()

    def base_image(self,shot,max_edge=0):
        from engine import read_image
        source=self.project.source(shot['assets'][0])
        cache=self.project.folder/'cache'/f'{shot["id"]}_srgb_{shot["assets"][0]["mtime_ns"]}.jpg'
        if max_edge and cache.exists():
            with Image.open(cache) as im:return im.convert('RGB')
        im,_=read_image(source);im=to_srgb(im)
        self.project.source(shot['assets'][0])
        if max_edge:
            im.thumbnail((1920,1920),Image.Resampling.LANCZOS)
            im.save(cache,format='JPEG',quality=95,icc_profile=SRGB_BYTES)
        return im

    def image(self,shot,max_edge=0,settings=None,rotation=None,preview=False):
        chosen=validate(shot['adjustments'] if settings is None else settings)
        r=shot['rotation'] if rotation is None else rotation
        self.luts.check(chosen['lut'])
        with self.lock:
            source=self.base_image(shot,1920 if preview else 0)
            result=transform(source,r,chosen,self.luts)
            if max_edge:result.thumbnail((max_edge,max_edge),Image.Resampling.LANCZOS)
        return result

    def jpeg(self,shot,max_edge=0,quality=95,settings=None,rotation=None,preview=False):
        with self.image(shot,max_edge,settings,rotation,preview) as im:
            buffer=io.BytesIO();im.save(buffer,format='JPEG',quality=quality,subsampling=0,icc_profile=SRGB_BYTES)
        return buffer.getvalue()
