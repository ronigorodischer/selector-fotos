'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="session-token"]').content;
const ui = { data:null, active:null, group:null, filter:'all', selected:new Set(), view:'single', zoom:false, before:false, manifest:null, shuttingDown:false };
let toastTimer, pollTimer, loading=false, editQueue=Promise.resolve();
const labels = {pending:'Pendiente',keep:'Se queda',reject:'Se va'};
function el(tag, cls, text) { const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n; }
function hasAdjustments(shot){const a=shot?.adjustments;return !!(a&&(a.crop||a.straighten||(a.lut&&a.intensity)));}
function media(shot, variant='thumb',before=false) { if(!variant.startsWith('face-')&&!before&&hasAdjustments(shot))variant='edited-'+variant;return `/media/${shot.id}/${variant}?token=${token}&rotation=${before?0:shot.rotation}&rev=${shot.revision}`; }
function toast(message, error=false) { $('toast').textContent=message;$('toast').classList.toggle('error',error);$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,error?7000:3500); }
async function api(path, body) {
  const res=await fetch(`/api/${path}`,{method:body===undefined?'GET':'POST',headers:{'X-Session-Token':token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await res.json();if(!res.ok)throw Error(data.error||'No se pudo completar la operación.');return data;
}
const current = () => ui.data?.shots.find(s=>s.id===ui.active);
function matches(shot) { const q=$('search').value.trim().toLowerCase();return (ui.filter==='all'||shot.state===ui.filter)&&(!q||shot.name.toLowerCase().includes(q)); }
function visible() { return ui.data?.shots.filter(s=>(!ui.group||s.group_id===ui.group)&&matches(s))||[]; }
function render() {
  if(!ui.data)return;
  const d=ui.data;
  $('project-name').textContent=d.name;$('project-total').textContent=`${d.shots.length} tomas · ${d.shots.reduce((n,s)=>n+s.assets.length,0)} archivos`;
  document.title=`${d.name} · Selector local`;
  for(const f of ['all','pending','keep','reject'])$(`count-${f}`).textContent=f==='all'?d.shots.length:d.counts[f];
  document.querySelectorAll('[data-filter]').forEach(b=>b.classList.toggle('active',b.dataset.filter===ui.filter));
  $('group-count').textContent=d.groups.length;
  if(ui.group&&!d.groups.some(g=>g.id===ui.group))ui.group=null;
  const groupIndex=d.groups.findIndex(g=>g.id===ui.group);
  $('scene-title').textContent=ui.group?`Grupo ${String(groupIndex+1).padStart(2,'0')} · ${d.groups[groupIndex].count} tomas`: 'Toda la sesión';
  const valid=d.shots.filter(matches);
  if(!current()||!matches(current()))ui.active=(visible()[0]||valid[0])?.id||null;
  if(current()&&ui.group&&current().group_id!==ui.group)ui.active=visible()[0]?.id||null;
  const known=new Set(d.shots.map(s=>s.id));ui.selected=new Set([...ui.selected].filter(id=>known.has(id)));
  $('trash-count').textContent=d.counts.reject;$('trash').disabled=d.counts.reject===0||d.job.running;
  $('selection-summary').textContent=`${d.counts.keep} se quedan · ${d.counts.pending} por revisar`;
  $('selected-count').textContent=ui.selected.size;
  $('analyze').disabled=d.job.running;$('sensitivity').disabled=d.job.running;
  $('progress').hidden=!d.job.running;
  $('progress-label').textContent=`${d.job.stage} · ${d.job.done} / ${d.job.total}`;
  $('progress-bar').max=d.job.total||1;$('progress-bar').value=d.job.done;
  renderGroups();renderFilm();renderViewer();renderInspector();
  if(typeof refreshExport==='function')refreshExport();
}
function renderGroups() {
  const fragment=document.createDocumentFragment();
  ui.data.groups.forEach((group,index)=>{
    if(!ui.data.shots.some(s=>s.group_id===group.id&&matches(s)))return;
    const b=el('button',`group-card${ui.group===group.id?' active':''}`);b.dataset.group=group.id;
    const cover=ui.data.shots.find(s=>s.id===group.best)||ui.data.shots.find(s=>s.id===group.cover);
    const img=el('img');if(cover.analysis)img.src=media(cover);img.alt='';img.loading='lazy';
    const text=el('div');text.append(el('strong','',`Grupo ${String(index+1).padStart(2,'0')}`),el('small','',`${group.count} ${group.count===1?'toma':'tomas'} · ${group.pending} pendientes`));
    b.append(img,text);fragment.append(b);
  });$('groups').replaceChildren(fragment);
}
function renderFilm() {
  const before=$('filmstrip').scrollLeft, fragment=document.createDocumentFragment();
  const shots=visible();$('film-label').textContent=`${ui.group?'TOMAS DEL GRUPO':'TODA LA SESIÓN'} · ${shots.length}`;
  shots.forEach(shot=>{
    const n=el('div',`thumb ${shot.state}${shot.id===ui.active?' active':''}${ui.selected.has(shot.id)?' chosen':''}`);n.tabIndex=0;n.role='button';n.dataset.shot=shot.id;n.title=`${shot.name} · ${labels[shot.state]}`;n.setAttribute('aria-label',n.title);
    const image=el('img');if(shot.analysis)image.src=media(shot);image.loading='lazy';image.alt='';
    const select=el('button','choose-thumb',ui.selected.has(shot.id)?'✓':'');select.dataset.choose=shot.id;select.setAttribute('aria-label',`Seleccionar ${shot.name} para comparar`);select.setAttribute('aria-pressed',String(ui.selected.has(shot.id)));
    n.append(image,select,el('span','thumb-name',shot.name));if(shot.recommended)n.append(el('span','thumb-best','✧'));fragment.append(n);
  });$('filmstrip').replaceChildren(fragment);$('filmstrip').scrollLeft=before;
}
function displayShots() {
  if(ui.view==='compare')return [...ui.selected].map(id=>ui.data.shots.find(s=>s.id===id)).filter(Boolean).slice(0,4);
  return current()?[current()]:[];
}
function renderViewer() {
  const shot=current();
  $('photo-name').textContent=shot?`${shot.name} · ${labels[shot.state]}`:'Sin fotografías para este filtro';
  const list=visible(),index=list.findIndex(s=>s.id===ui.active);
  $('photo-counter').textContent=index>=0?`${index+1} / ${list.length}`:'';
  $('representation').textContent=ui.before?'Original sin ajustes':hasAdjustments(shot)?'Vista con ajustes sRGB':shot?.analysis?.representation||'Vista local';
  $('before').setAttribute('aria-pressed',String(ui.before));$('before').textContent=ui.before?'Ver ajustes':'Ver original';
  ['reject','pending','keep'].forEach(state=>$(`mark-${state}`).classList.toggle('is-current',shot?.state===state));
  for(const id of ['mark-reject','mark-pending','mark-keep','rotate-left','rotate-right','zoom','open-editor','before'])$(id).disabled=!shot?.analysis;
  $('view-single').classList.toggle('selected',ui.view==='single');$('view-grid').classList.toggle('selected',ui.view==='grid');
  const stage=$('stage');stage.classList.toggle('grid-view',ui.view==='grid');stage.classList.toggle('zoomed',ui.zoom&&ui.view!=='grid');
  const signature=ui.view+'|'+ui.zoom+'|'+ui.before+'|'+(ui.view==='grid'?list:displayShots()).map(s=>`${s.id}:${s.rotation}:${!!s.analysis}:${s.state}:${s.revision}`).join(',');
  if(stage.dataset.signature===signature)return;
  stage.dataset.signature=signature;stage.replaceChildren();
  if(ui.view==='grid') {
    list.forEach(s=>{const tile=el('button',`grid-tile${s.id===ui.active?' active':''}`);tile.dataset.gridShot=s.id;const img=el('img');if(s.analysis)img.src=media(s,'thumb');img.loading='lazy';img.alt=s.name;tile.append(img,el('span','',`${s.name} · ${labels[s.state]}`));stage.append(tile);});
  } else {
    const shots=displayShots();
    if(!shots.length)stage.append(el('div','empty-stage',ui.data.job.running?'Preparando tus fotografías…':'No hay fotos en esta vista. Cambia el filtro o analiza la sesión.'));
    shots.forEach(s=>{
      const pane=el('div','photo-pane');
      if(s.analysis){const img=el('img');img.alt=s.name;img.addEventListener('load',()=>{if(ui.zoom){img.style.width=`${img.naturalWidth}px`;img.style.height=`${img.naturalHeight}px`;}});img.src=media(s,ui.zoom?'original':'preview',ui.before);
        img.addEventListener('error',()=>{pane.replaceChildren(el('div','empty-stage','No se pudo abrir esta vista. El original puede haber cambiado o estar desconectado.'));});pane.append(img,el('span','pane-label',`${s.name}${s.recommended?' · Candidata por detalle':''}`));
      }else pane.append(el('div','empty-stage','Esta foto aún no se ha analizado.'));
      pane.addEventListener('scroll',()=>{if(!ui.zoom||ui.syncing)return;ui.syncing=true;stage.querySelectorAll('.photo-pane').forEach(other=>{if(other===pane)return;other.scrollLeft=pane.scrollLeft/Math.max(1,pane.scrollWidth-pane.clientWidth)*(other.scrollWidth-other.clientWidth);other.scrollTop=pane.scrollTop/Math.max(1,pane.scrollHeight-pane.clientHeight)*(other.scrollHeight-other.clientHeight);});requestAnimationFrame(()=>ui.syncing=false);});stage.append(pane);
    });
  }
}
function renderInspector() {
  const shot=current(),a=shot?.analysis;
  const inGroup=ui.data.shots.filter(s=>s.group_id===shot?.group_id).length;
  $('focus-score').textContent=a&&inGroup>1?shot.focus_score:'—';$('focus-unit').textContent=inGroup>1?'/ 100':'sin comparación';
  $('focus-verdict').textContent=!a?'Sin evaluar':inGroup===1?'Una sola toma en este grupo':shot.focus_score>=75?'Mayor detalle en este grupo':shot.focus_score<=25?'Menor detalle en este grupo':'Detalle intermedio';
  $('focus-basis').textContent=a?`Medido en ${a.focus_basis}. Índice orientativo, sin calibración artística.`:'El análisis no cambia tus decisiones.';
  $('recommendation').hidden=!shot?.recommended;
  $('faces-count').textContent=a?.faces.length||0;
  const fragment=document.createDocumentFragment();
  (a?.faces||[]).forEach((face,index)=>{
    const b=el('button',`face-item${(a.primary_face||0)===index?' selected':''}`);b.dataset.face=index;b.title='Usar este rostro para comparar el enfoque';const img=el('img');img.src=media(shot,`face-${index}`);img.alt=`Rostro ${index+1}`;b.append(img,el('span','',face.limited?'Detalle limitado':`Rostro ${index+1}`));fragment.append(b);
  });$('faces').replaceChildren(fragment);
  $('face-note').textContent=a?.faces.length?'Pulsa un rostro para priorizar su detalle.':'No hay un rostro fiable detectado. Puede estar cubierto, de perfil o ser demasiado pequeño.';
  const stars=document.createDocumentFragment();for(let i=1;i<=5;i++){const b=el('button',shot?.stars>=i?'filled':'',shot?.stars>=i?'★':'☆');b.dataset.stars=i;b.setAttribute('aria-label',`${i} estrellas`);stars.append(b);}$('stars').replaceChildren(stars);
  const m=shot?.meta;$('camera-info').replaceChildren();
  if(m){$('camera-info').append(el('div','',m.camera||'Cámara sin datos'),el('div','',`${m.shutter?m.shutter+' s · ':''}${m.aperture?'f/'+formatAperture(m.aperture)+' · ':''}${m.iso?'ISO '+m.iso:''}`),el('div','',m.captured||'Fecha EXIF no disponible'));if(a)$('camera-info').append(el('div','',`${a.width} × ${a.height} · ${shot.assets.length>1?'RAW + JPG':shot.assets[0].extension.slice(1).toUpperCase()}`));}
}
function formatAperture(v){const a=v.split('/').map(Number);return Number.isFinite(a[0])?(a.length===2?a[0]/a[1]:a[0]).toFixed(1):v;}
async function load(){if(loading||ui.shuttingDown)return;loading=true;try{const data=await api('state');const changed=ui.data?.id!==data.id;ui.data=data;if(changed){ui.group=data.groups[0]?.id||null;ui.active=data.shots[0]?.id||null;ui.selected.clear();}render();}catch(e){toast(e.message,true);}finally{loading=false;clearTimeout(pollTimer);if(!ui.shuttingDown)pollTimer=setTimeout(load,ui.data?.job.running||ui.data?.export_job?.running?1400:12000);}}
async function action(path,body,message){try{await api(path,body);await load();if(message)toast(message);}catch(e){toast(e.message,true);}}
function changeActive(sid){ui.active=sid;ui.before=false;render();const thumb=$('filmstrip').querySelector(`[data-shot="${sid}"]`);thumb?.scrollIntoView({block:'nearest',inline:'nearest'});}
function navigate(delta){const list=ui.data.shots.filter(matches);if(!list.length)return;const at=list.findIndex(s=>s.id===ui.active),next=list[Math.max(0,Math.min(list.length-1,at+delta))];if(ui.group)ui.group=next.group_id;ui.zoom=false;changeActive(next.id);}
function edit(changes,advance=false){
  const sid=ui.active;if(!sid)return;
  editQueue=editQueue.then(async()=>{const oldList=ui.data.shots.filter(matches),idx=oldList.findIndex(s=>s.id===sid);$('saved-status').textContent='Guardando…';
    try{await api('edit',{id:sid,changes});if(advance&&$('auto-next').checked&&oldList[idx+1]){ui.active=oldList[idx+1].id;if(ui.group)ui.group=oldList[idx+1].group_id;}await load();$('saved-status').textContent='✓ Guardado en este equipo';}catch(e){$('saved-status').textContent='No guardado';toast(e.message,true);}
  });
}
$('filters').addEventListener('click',e=>{const button=e.target.closest('[data-filter]');if(!button)return;ui.filter=button.dataset.filter;ui.group=null;render();});
$('groups').addEventListener('click',e=>{const b=e.target.closest('[data-group]');if(!b)return;ui.group=b.dataset.group;ui.active=visible()[0]?.id||null;ui.zoom=false;render();});
$('all-groups').onclick=()=>{ui.group=null;render();};
$('search').addEventListener('input',()=>{ui.group=null;render();});
$('filmstrip').addEventListener('click',e=>{const choose=e.target.closest('[data-choose]');if(choose){const id=choose.dataset.choose;ui.selected.has(id)?ui.selected.delete(id):ui.selected.add(id);render();return;}const thumb=e.target.closest('[data-shot]');if(thumb){ui.zoom=false;changeActive(thumb.dataset.shot);}});
$('filmstrip').addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){const thumb=e.target.closest('[data-shot]');if(thumb){e.preventDefault();changeActive(thumb.dataset.shot);}}});
$('stage').onclick=e=>{const tile=e.target.closest('[data-grid-shot]');if(tile){ui.view='single';changeActive(tile.dataset.gridShot);}};
$('view-single').onclick=()=>{ui.view='single';ui.zoom=false;render();};$('view-grid').onclick=()=>{ui.view='grid';ui.zoom=false;render();};
$('select-group').onclick=()=>{visible().forEach(s=>ui.selected.add(s.id));render();};
$('compare').onclick=()=>{if(ui.selected.size<2){if(ui.active)ui.selected.add(ui.active);const next=visible().find(s=>!ui.selected.has(s.id));if(next)ui.selected.add(next.id);}if(ui.selected.size<2)return toast('Selecciona al menos dos tomas.');if(ui.selected.size>4)toast('Se comparan las primeras cuatro de la selección.');ui.view=ui.view==='compare'?'single':'compare';ui.zoom=false;render();};
$('merge').onclick=()=>{if(ui.selected.size<2)return toast('Selecciona dos o más tomas con sus casillas.');action('group',{ids:[...ui.selected]},'Grupo unido.');};
$('split').onclick=()=>{const ids=ui.selected.size?[...ui.selected]:(ui.active?[ui.active]:[]);action('group',{ids,split:true},'Tomas separadas y agrupación manual guardada.');};
$('sensitivity').onchange=()=>action('regroup',{sensitivity:$('sensitivity').value},'Agrupación actualizada. Tus decisiones siguen guardadas.');
for(const state of ['keep','reject','pending'])$(`mark-${state}`).onclick=()=>edit({state},true);
$('rotate-right').onclick=()=>edit({rotation:((current()?.rotation||0)+90)%360});$('rotate-left').onclick=()=>edit({rotation:((current()?.rotation||0)+270)%360});
$('zoom').onclick=()=>{ui.zoom=!ui.zoom;render();};$('previous').onclick=()=>navigate(-1);$('next').onclick=()=>navigate(1);
$('stars').onclick=e=>{const b=e.target.closest('[data-stars]');if(b)edit({stars:current()?.stars===Number(b.dataset.stars)?0:Number(b.dataset.stars)});};
$('faces').onclick=e=>{const b=e.target.closest('[data-face]');if(b&&ui.active)action('face',{id:ui.active,index:Number(b.dataset.face)},'Rostro principal actualizado.');};
$('undo').onclick=()=>action('undo',{},'Última decisión deshecha.');
$('analyze').onclick=()=>action('analyze',{},'Análisis local iniciado. Puedes seguir revisando.');$('pause').onclick=()=>action('pause',{},'Terminando las dos imágenes en curso; después se pausará.');
document.addEventListener('keydown',e=>{
  if(e.target.closest('input,select,textarea')||document.querySelector('dialog[open]'))return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$('undo').click();return;}
  if(e.ctrlKey||e.metaKey||e.altKey||e.repeat)return;
  const key=e.key.toLowerCase();
  if(['p','x','u','r','c','arrowleft','arrowright','0','1','2','3','4','5'].includes(key))e.preventDefault();
  if(key==='c')$('open-editor').click();
  if(key==='p')edit({state:'keep'},true);if(key==='x')edit({state:'reject'},true);if(key==='u')edit({state:'pending'},true);
  if(key==='arrowleft')navigate(-1);if(key==='arrowright')navigate(1);if(key==='r')$(e.shiftKey?'rotate-left':'rotate-right').click();
  if(/^[0-5]$/.test(key))edit({stars:Number(key)});
});
$('open-folder').onclick=()=>{$('folder-path').value=ui.data?.root||'';$('folder-dialog').showModal();};
$('confirm-folder').onclick=async()=>{try{await api('open',{path:$('folder-path').value});$('folder-dialog').close();ui.data=null;ui.filter='all';await load();toast('Carpeta abierta. Pulsa Analizar sesión si es un proyecto nuevo.');}catch(e){toast(e.message,true);}};
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
$('trash').onclick=async()=>{try{ui.manifest=await api('trash/prepare',{});const m=ui.manifest;$('trash-summary').textContent=`${m.shots} tomas · ${m.files} archivos · ${(m.bytes/1024/1024).toFixed(1)} MB`;$('trash-files').textContent=m.items.map(i=>i.path).join('\n');$('trash-result').textContent='';$('confirm-trash').disabled=m.files===0;$('confirm-trash').textContent=`Enviar ${m.files} archivos a la papelera`;$('trash-dialog').showModal();}catch(e){toast(e.message,true);}};
$('confirm-trash').onclick=async()=>{if(!ui.manifest)return;$('confirm-trash').disabled=true;try{const result=await api('trash/commit',{id:ui.manifest.id,confirmed:true});$('trash-result').textContent=`${result.moved} enviados · ${result.failed} fallidos · ${result.not_attempted} no intentados.`;if(result.failed)$('trash-result').textContent+=' '+result.results.filter(r=>r.error).map(r=>`${r.path}: ${r.error}`).join(' ');await load();}catch(e){$('trash-result').textContent=e.message;}finally{ui.manifest=null;}};
$('show-report').onclick=()=>{
  const r=ui.data?.report,container=$('report-content');container.replaceChildren();
  if(!r)container.append(el('p','','Todavía no hay un análisis completo. Pulsa Analizar sesión.'));
  else{const grid=el('div','report-stats');[[r.analyzed,'fotos analizadas'],[r.groups,'grupos al analizar'],[`${r.seconds} s`,'duración']].forEach(([v,label])=>{const c=el('div','report-stat');c.append(el('strong','',v),el('span','',label));grid.append(c);});container.append(grid,el('p','',`${r.with_faces} fotografías con rostros detectados. ${r.errors.length} incidencias. ${r.cancelled?'Análisis pausado.':''}`),el('p','muted','Agrupación y enfoque experimentales: requieren revisión visual. El análisis se hace sobre la foto original y no cambia con un recorte o LUT. Ojos abiertos/cerrados: sin evaluar.'));if(r.errors.length)container.append(el('div','report-errors',r.errors.map(x=>`${x.file||''}: ${x.error}`).join('\n')));}
  $('report-dialog').showModal();
};
$('export').onclick=()=>{$('export-csv').href=`/api/export?format=csv&token=${token}`;$('export-json').href=`/api/export?format=json&token=${token}`;if(typeof refreshExport==='function')refreshExport();$('export-dialog').showModal();};
$('shutdown').onclick=async()=>{try{await api('shutdown',{});ui.shuttingDown=true;clearTimeout(pollTimer);toast('Servidor cerrado. Puedes cerrar esta pestaña y abrirlo de nuevo con el acceso de la carpeta.');}catch(e){toast(e.message,true);}};
load();
