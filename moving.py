"""Move kept originals within a project, preserving catalog identities."""
import os
from pathlib import Path
import secrets
import shutil
import time

from engine import dumps, fingerprint, sha256


def safe_destination(project, path):
    path=Path(path)
    if not path.is_relative_to(project.root) or path==project.root:
        raise ValueError('El destino debe estar dentro del proyecto.')
    for part in (path,*path.parents):
        if part==project.root:break
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('El destino no puede contener enlaces o uniones de carpetas.')
    if not path.resolve().is_relative_to(project.root):
        raise ValueError('El destino está fuera del proyecto.')


def move_exclusive(source, destination):
    """Never replace an existing file, including one created after preflight."""
    if os.name=='nt':
        os.rename(source,destination)  # Windows rename fails if the target exists.
        return
    try:
        os.link(source,destination)
    except FileExistsError:raise
    except OSError:
        created=False
        try:
            with open(destination,'xb') as output:
                created=True
                with open(source,'rb') as original:shutil.copyfileobj(original,output)
                output.flush();os.fsync(output.fileno())
            shutil.copystat(source,destination)
            if sha256(source)!=sha256(destination):raise OSError('La copia no coincide con el original.')
        except Exception:
            if created:Path(destination).unlink(missing_ok=True)
            raise
    try:Path(source).unlink()
    except Exception:
        Path(destination).unlink(missing_ok=True)
        raise


def available(app):
    if app.export_job['running'] or app.project.job['running']:
        raise ValueError('Espera a que termine el análisis o la exportación.')


def prepare(app):
    available(app)
    project=app.project;destination=project.root/'Seleccionadas';safe_destination(project,destination)
    items=[];skipped=0;targets=set()
    for shot in project.rows():
        if shot['state']!='keep':continue
        if all(Path(a['path']).is_relative_to(destination) for a in shot['assets']):
            skipped+=1;continue
        if not shot['analysis']:raise ValueError('Analiza las fotos antes de moverlas.')
        for asset in shot['assets']:
            source=project.source(asset)
            if source.is_relative_to(destination):continue
            target=destination/source.relative_to(project.root)
            safe_destination(project,target)
            if target.exists() or str(target).casefold() in targets:
                raise ValueError(f'Ya existe un archivo en el destino: {target}. No se sobrescribirá.')
            targets.add(str(target).casefold())
            items.append({**asset,'shot_id':shot['id'],'revision':shot['revision'],
                          'destination':str(target),'sha256':shot['analysis']['hashes'][asset['path']]})
    nonce=secrets.token_hex(24)
    batch={'id':nonce,'kind':'move','created':time.time(),'project_id':project.id,
           'destination':str(destination),'items':items,'shots':len({i['shot_id'] for i in items}),
           'files':len(items),'bytes':sum(i['size'] for i in items),'skipped':skipped}
    app.manifests={k:v for k,v in app.manifests.items() if time.time()-v['created']<600}
    app.manifests[nonce]=batch
    return batch


def commit(app, nonce, confirmed, mover=move_exclusive):
    available(app)
    batch=app.manifests.pop(nonce,None);project=app.project
    if confirmed is not True or not batch or batch.get('kind')!='move' or time.time()-batch['created']>600:
        raise ValueError('Revisa de nuevo las fotos que se moverán.')
    if batch['project_id']!=project.id:raise ValueError('El proyecto cambió; revisa el lote de nuevo.')
    results=[]
    with project.lock:
        rows={s['id']:s for s in project.rows()}
        for item in batch['items']:
            shot=rows.get(item['shot_id'])
            if not shot or shot['state']!='keep' or shot['revision']!=item['revision']:
                raise ValueError('La selección cambió. Revisa el lote de nuevo.')
            project.source(item);safe_destination(project,item['destination'])
            if Path(item['destination']).exists():raise ValueError('Ya existe un archivo en el destino. No se sobrescribirá.')
            if sha256(item['path'])!=item['sha256']:raise ValueError('Un original cambió; no se movió ningún archivo.')
        for item in batch['items']:
            source=Path(item['path']);target=Path(item['destination'])
            shot=rows[item['shot_id']]
            try:
                target.parent.mkdir(parents=True,exist_ok=True);safe_destination(project,target)
                project.source(item)
                with project.connect() as con:
                    con.execute('INSERT INTO move_log VALUES(?,?,?,?,?,?,?)',
                                (nonce,shot['id'],str(source),str(target),'started','',time.time()))
                mover(source,target)
                assets=[{**a,'path':str(target),**fingerprint(target)} if a['path']==str(source) else a for a in shot['assets']]
                analysis=dict(shot['analysis']);analysis['hashes']=dict(analysis['hashes'])
                analysis['hashes'][str(target)]=analysis['hashes'].pop(str(source))
                with project.connect() as con:
                    con.execute('UPDATE shots SET assets=?,analysis=?,revision=revision+1 WHERE id=?',
                                (dumps(assets),dumps(analysis),shot['id']))
                    con.execute("UPDATE move_log SET status='moved' WHERE operation=? AND source=?",(nonce,str(source)))
                shot['assets']=assets;shot['analysis']=analysis
                results.append({'source':str(source),'destination':str(target),'status':'moved'})
            except Exception as exc:
                with project.connect() as con:
                    con.execute("UPDATE move_log SET status='failed',error=? WHERE operation=? AND source=?",(str(exc),nonce,str(source)))
                results.append({'source':str(source),'destination':str(target),'status':'failed','error':str(exc)})
                project.recover_moves()
                break
    return {'moved':sum(r['status']=='moved' for r in results),'failed':sum(r['status']=='failed' for r in results),
            'not_attempted':len(batch['items'])-len(results),'results':results,'destination':batch['destination']}
