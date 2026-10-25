"""Render a whole session in an isolated project copy, preserving user decisions."""
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import time
import zipfile
from PIL import Image
from app import Application
from engine import Project,BASE,dumps
from editing import DEFAULT


def main():
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(json.loads((BASE/'data/settings.json').read_text('utf-8'))['source'])
    original=Project(root)
    parent=BASE/'data'/('validacion-edicion-'+secrets.token_hex(4))
    folder=parent/original.id;folder.mkdir(parents=True)
    destination=sqlite3.connect(folder/'project.sqlite')
    try:
        with original.connect() as connection:connection.backup(destination)
    finally:destination.close()
    app=Application(root,parent,trash_enabled=False)
    # Only the isolated project copy receives these test adjustments.
    settings={**DEFAULT,'crop':[.1,.1,.8,.8],'straighten':1.5,'lut':'warm','intensity':.65}
    with app.project.connect() as con:
        con.execute('UPDATE shots SET adjustments=? WHERE trashed=0',(dumps(settings),))
    job=app.start_export([s['id'] for s in app.project.rows()],max_edge=1600,quality=95)
    while app.export_job['running']:
        time.sleep(5)
        print(dumps({'done':app.export_job['done'],'total':app.export_job['total'],'errors':len(app.export_job['errors'])}),flush=True)
    result=dict(app.export_job);checked=0;dimensions=set()
    archive=app.exports.get(job['id'])
    if archive:
        with zipfile.ZipFile(archive) as bundle:
            if bundle.testzip() is not None:raise RuntimeError('ZIP corrupto')
            for path in archive.parent.glob('*.jpg'):
                with Image.open(path) as im:
                    im.load()
                    if max(im.size)>1600 or not im.info.get('icc_profile'):raise RuntimeError('Salida sin perfil sRGB o fuera de resolución')
                    checked+=1;dimensions.add(im.size)
    result.update(validated_jpgs=checked,dimensions=sorted(dimensions),archive=str(archive),
                  integrity=original.audit(),test_settings=settings,source_project_modified=False)
    (parent/'validacion.json').write_text(dumps(result),encoding='utf-8')
    print(dumps(result),flush=True)
    if checked!=result['total'] or result['errors'] or result['integrity']['changed']:raise SystemExit(1)


if __name__=='__main__':main()
