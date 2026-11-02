'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="session-token"]').content;
const ui = { data:null, active:null, group:null, filter:'all', selected:new Set(), view:'single', layout:'auto', zoom:false, zoomScale:1, before:false, manifest:null, shuttingDown:false };
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
  $('move-keepers').disabled=d.counts.keep===0||d.job.running||d.export_job?.running||!!ui.moving;
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
function displayedSize(shot){
  if(!shot?.analysis)return[1,1];
  let w=shot.analysis.width,h=shot.analysis.height;
  if(ui.before)return[w,h];
  if(shot.rotation===90||shot.rotation===270)[w,h]=[h,w];
  const a=shot.adjustments;
  if(a?.straighten){const t=Math.abs(a.straighten)*Math.PI/180,c=Math.cos(t),s=Math.sin(t),k=Math.min(w/(w*c+h*s),h/(w*s+h*c));w=Math.max(1,Math.floor(w*k)-2);h=Math.max(1,Math.floor(h*k)-2);}
  if(a?.crop){w*=a.crop[2];h*=a.crop[3];}
  return[w,h];
}
function viewerLayout(){
  const shots=displayShots(),[w,h]=displayedSize(current()||shots[0]);
  const app=document.querySelector('.app'),stage=$('stage');
  let chosen=ui.view==='grid'?'landscape':ui.layout==='auto'?(h>w?'portrait':'landscape'):ui.layout;
  stage.classList.toggle('comparison-view',ui.view==='compare'&&shots.length>1);
  if(ui.view==='compare'&&shots.length>1&&ui.layout==='auto'){
    let largest=-1;
    for(const candidate of ['portrait','landscape']){
      app.dataset.layout=candidate;
      const fit=bestComparisonGrid(stage.clientWidth,stage.clientHeight,shots);
      if(fit.area>largest){largest=fit.area;chosen=candidate;}
    }
  }
  app.dataset.layout=chosen;
  $('layout-choice').value=ui.layout;$('layout-choice').disabled=ui.view==='grid';
  arrangeComparison();return chosen;
}
function bestComparisonGrid(width,height,shots){
  const gap=8;
  let best={area:-1,columns:1,rows:shots.length};
  for(let columns=1;columns<=shots.length;columns++){
    const rows=Math.ceil(shots.length/columns),cw=(width-gap*(columns-1))/columns,ch=(height-gap*(rows-1))/rows;
    const area=shots.reduce((sum,shot)=>{const[w,h]=displayedSize(shot),scale=Math.max(0,Math.min(cw/w,ch/h));return sum+w*h*scale*scale;},0);
    if(area>best.area)best={area,columns,rows};
  }
  return best;
}
function arrangeComparison(){
  const stage=$('stage'),shots=displayShots();
  if(ui.view!=='compare'||shots.length<2){stage.style.removeProperty('grid-template-columns');stage.style.removeProperty('grid-template-rows');return;}
  if(!stage.clientWidth||!stage.clientHeight)return;
  const best=bestComparisonGrid(stage.clientWidth,stage.clientHeight,shots);
  const cols=`repeat(${best.columns}, minmax(0, 1fr))`,rows=`repeat(${best.rows}, minmax(0, 1fr))`;
  if(stage.style.gridTemplateColumns!==cols)stage.style.gridTemplateColumns=cols;
  if(stage.style.gridTemplateRows!==rows)stage.style.gridTemplateRows=rows;
}
function zoomAnchor(view,x=view.clientWidth/2,y=view.clientHeight/2){
  const old=view._zoomInfo;
  if(!old)return{x:.5,y:.5,px:x/Math.max(1,view.clientWidth),py:y/Math.max(1,view.clientHeight)};
  return{x:Math.max(0,Math.min(1,(view.scrollLeft+x-(old.surfaceWidth-old.width)/2)/old.width)),
    y:Math.max(0,Math.min(1,(view.scrollTop+y-(old.surfaceHeight-old.height)/2)/old.height)),
    px:x/Math.max(1,view.clientWidth),py:y/Math.max(1,view.clientHeight)};
}
function resizePhoto(view,anchor){
  const img=view.querySelector('img'),surface=view.querySelector('.zoom-surface');
  if(!img||!view._photoSize||!view.clientWidth||!view.clientHeight)return;
  anchor=anchor||zoomAnchor(view);
  const[nw,nh]=view._photoSize,fit=Math.min(1,view.clientWidth/nw,view.clientHeight/nh);
  const scale=ui.zoom?Math.max(fit,Math.min(4,ui.zoomScale)):fit;
  const width=nw*scale,height=nh*scale,surfaceWidth=Math.max(view.clientWidth,width),surfaceHeight=Math.max(view.clientHeight,height);
  img.style.width=width+'px';img.style.height=height+'px';surface.style.width=surfaceWidth+'px';surface.style.height=surfaceHeight+'px';
  view._zoomInfo={width,height,surfaceWidth,surfaceHeight,fit,scale};
  view.classList.toggle('is-magnified',scale>fit*1.001);
  view._ignoreScroll=true;
  view.scrollLeft=anchor.x*width+(surfaceWidth-width)/2-anchor.px*view.clientWidth;
  view.scrollTop=anchor.y*height+(surfaceHeight-height)/2-anchor.py*view.clientHeight;
  if(ui.zoom&&img.dataset.resolution!=='original'){
    img.dataset.resolution='original';img.src=media(view._shot,'original',ui.before);
  }
}
function refreshZoom(anchor){
  $('stage').classList.toggle('zoomed',ui.zoom&&ui.view!=='grid');
  $('stage').querySelectorAll('.photo-viewport').forEach(view=>resizePhoto(view,anchor));
  $('zoom').textContent=ui.zoom?'Ajustar':'100 %';
  $('zoom').setAttribute('aria-pressed',String(ui.zoom));
  $('zoom').title=ui.zoom?'Volver a encajar la foto en el visor':'Ver al 100 % · También puedes usar la ruedita sobre la foto';
  const counter=$('photo-counter');
  counter.textContent=(counter.dataset.baseLabel||'')+(ui.zoom?` · ${Math.round(ui.zoomScale*100)} %`:'');
}
function setupPhotoZoom(view,shot,img){
  view._shot=shot;view._photoSize=displayedSize(shot);view.tabIndex=0;
  view.setAttribute('aria-label',`${shot.name}: ruedita para acercar o alejar; arrastrar para desplazar`);
  img.draggable=false;img.dataset.resolution=ui.zoom?'original':'preview';
  img.addEventListener('load',()=>{
    if(img.dataset.resolution==='original')view._photoSize=[img.naturalWidth,img.naturalHeight];
    resizePhoto(view);
  });
  view.addEventListener('wheel',event=>{
    if(!view._zoomInfo||!event.deltaY)return;
    event.preventDefault();event.stopPropagation();view.focus({preventScroll:true});
    const rect=view.getBoundingClientRect(),anchor=zoomAnchor(view,event.clientX-rect.left,event.clientY-rect.top);
    const delta=event.deltaY*(event.deltaMode===1?16:event.deltaMode===2?view.clientHeight:1);
    const info=view._zoomInfo;
    const next=Math.max(info.fit,Math.min(4,info.scale*Math.exp(-Math.max(-240,Math.min(240,delta))*.002)));
    ui.zoom=next>info.fit*1.001;ui.zoomScale=ui.zoom?next:1;
    refreshZoom(anchor);
  },{passive:false});
  view.addEventListener('pointerdown',event=>{
    if(event.button!==0)return;
    view.focus({preventScroll:true});
    if(!view.classList.contains('is-magnified'))return;
    view._drag={x:event.clientX,y:event.clientY,left:view.scrollLeft,top:view.scrollTop};
    view._ignoreScroll=false;view.classList.add('is-dragging');view.setPointerCapture(event.pointerId);event.preventDefault();
  });
  view.addEventListener('pointermove',event=>{
    if(!view._drag)return;
    view._ignoreScroll=false;view.scrollLeft=view._drag.left-event.clientX+view._drag.x;view.scrollTop=view._drag.top-event.clientY+view._drag.y;
  });
  const endDrag=()=>{view._drag=null;view.classList.remove('is-dragging');};
  view.addEventListener('pointerup',endDrag);view.addEventListener('pointercancel',endDrag);view.addEventListener('lostpointercapture',endDrag);
  view.addEventListener('scroll',()=>{
    if(view._ignoreScroll){view._ignoreScroll=false;return;}
    if(!ui.zoom||ui.syncing)return;
    ui.syncing=true;const anchor=zoomAnchor(view);
    $('stage').querySelectorAll('.photo-viewport').forEach(other=>{if(other!==view)resizePhoto(other,anchor);});
    requestAnimationFrame(()=>ui.syncing=false);
  });
}
function renderViewer() {
  const shot=current();
  const layout=viewerLayout();
  $('photo-name').textContent=shot?`${shot.name} · ${labels[shot.state]}`:'Sin fotografías para este filtro';
  const list=visible(),index=list.findIndex(s=>s.id===ui.active);
  const members=navigationShots();
  const memberIndex=members.findIndex(s=>s.id===ui.active);
  $('previous').disabled=memberIndex<=0;
  $('next').disabled=memberIndex<0||memberIndex===members.length-1;
  const viewLabel=ui.view==='grid'?'Cuadrícula':ui.view==='compare'?'Comparación':layout==='portrait'?'Vista vertical':'Vista horizontal';
  $('photo-counter').textContent=index>=0?`${viewLabel} · ${index+1} / ${list.length}`:'';
  $('photo-counter').dataset.baseLabel=$('photo-counter').textContent;
  $('representation').textContent=ui.before?'Original sin ajustes':hasAdjustments(shot)?'Vista con ajustes sRGB':shot?.analysis?.representation||'Vista local';
  $('before').setAttribute('aria-pressed',String(ui.before));$('before').textContent=ui.before?'Ver ajustes':'Ver original';
  ['reject','pending','keep'].forEach(state=>$(`mark-${state}`).classList.toggle('is-current',shot?.state===state));
  for(const id of ['mark-reject','mark-pending','mark-keep','rotate-left','rotate-right','zoom','open-editor','before'])$(id).disabled=!shot?.analysis;
  $('view-single').classList.toggle('selected',ui.view==='single');$('view-grid').classList.toggle('selected',ui.view==='grid');
  const stage=$('stage');stage.classList.toggle('grid-view',ui.view==='grid');stage.classList.toggle('zoomed',ui.zoom&&ui.view!=='grid');
  const signature=ui.view+'|'+ui.before+'|'+(ui.view==='grid'?list:displayShots()).map(s=>`${s.id}:${s.rotation}:${!!s.analysis}:${s.state}:${s.revision}`).join(',');
  if(stage.dataset.signature===signature){refreshZoom();return;}
  stage.dataset.signature=signature;stage.replaceChildren();
  if(ui.view==='grid') {
    list.forEach(s=>{const tile=el('button',`grid-tile${s.id===ui.active?' active':''}`);tile.dataset.gridShot=s.id;const img=el('img');if(s.analysis)img.src=media(s,'thumb');img.loading='lazy';img.alt=s.name;tile.append(img,el('span','',`${s.name} · ${labels[s.state]}`));stage.append(tile);});
  } else {
    const shots=displayShots();
    if(!shots.length)stage.append(el('div','empty-stage',ui.data.job.running?'Preparando tus fotografías…':'No hay fotos en esta vista. Cambia el filtro o analiza la sesión.'));
    shots.forEach(s=>{
      const pane=el('div','photo-pane');
      if(s.analysis){const img=el('img');img.alt=s.name;const view=el('div','photo-viewport'),surface=el('div','zoom-surface');surface.append(img);view.append(surface);setupPhotoZoom(view,s,img);img.src=media(s,ui.zoom?'original':'preview',ui.before);
        img.addEventListener('error',()=>{pane.replaceChildren(el('div','empty-stage','No se pudo abrir esta vista. El original puede haber cambiado o estar desconectado.'));});pane.append(view,el('span','pane-label',`${s.name}${s.recommended?' · Candidata por detalle':''}`));
      }else pane.append(el('div','empty-stage','Esta foto aún no se ha analizado.'));
      stage.append(pane);
    });
  }
  refreshZoom();
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
async function load(){if(loading||ui.shuttingDown)return;loading=true;try{const data=await api('state');const changed=ui.data?.id!==data.id;ui.data=data;if(changed){ui.group=data.groups[0]?.id||null;ui.active=data.shots[0]?.id||null;ui.zoom=false;ui.zoomScale=1;ui.selected.clear();}render();}catch(e){toast(e.message,true);}finally{loading=false;clearTimeout(pollTimer);if(!ui.shuttingDown)pollTimer=setTimeout(load,ui.data?.job.running||ui.data?.export_job?.running?1400:12000);}}
async function action(path,body,message){try{await api(path,body);await load();if(message)toast(message);}catch(e){toast(e.message,true);}}
function changeActive(sid){if(ui.active!==sid){ui.zoom=false;ui.zoomScale=1;}ui.active=sid;ui.before=false;render();const thumb=$('filmstrip').querySelector(`[data-shot="${sid}"]`);thumb?.scrollIntoView({block:'nearest',inline:'nearest'});}
function scrollActiveGroup(){if(ui.group)$('groups').querySelector(`[data-group="${ui.group}"]`)?.scrollIntoView({block:'nearest',inline:'nearest'});}
function navigationShots(){
  const groups=new Map(ui.data.groups.map(g=>[g.id,[]]));
  ui.data.shots.filter(matches).forEach(s=>groups.get(s.group_id)?.push(s));
  return [...groups.values()].flat();
}
function navigate(delta){
  const shot=current();if(!shot)return;
  const list=navigationShots();
  const at=list.findIndex(s=>s.id===ui.active),next=list[Math.max(0,Math.min(list.length-1,at+delta))];
  if(!next||next.id===ui.active)return;
  ui.group=next.group_id;ui.zoom=false;if(ui.view==='compare')ui.view='single';
  changeActive(next.id);scrollActiveGroup();
}
function navigateGroup(delta){
  if(!ui.data)return;
  const matchingGroups=new Set(ui.data.shots.filter(matches).map(s=>s.group_id));
  const groups=ui.data.groups.filter(g=>matchingGroups.has(g.id));if(!groups.length)return;
  const activeGroup=current()?.group_id||ui.group;
  const at=groups.findIndex(g=>g.id===activeGroup);
  const next=groups[at<0?0:Math.max(0,Math.min(groups.length-1,at+delta))];
  if(next.id===activeGroup)return;
  const first=ui.data.shots.find(s=>s.group_id===next.id&&matches(s));if(!first)return;
  ui.group=next.id;ui.zoom=false;if(ui.view==='compare')ui.view='single';
  changeActive(first.id);scrollActiveGroup();
}
function edit(changes,advance=false){
  const sid=ui.active;if(!sid)return;
  editQueue=editQueue.then(async()=>{const oldList=ui.data.shots.filter(matches),idx=oldList.findIndex(s=>s.id===sid);$('saved-status').textContent='Guardando…';
    try{await api('edit',{id:sid,changes});if(advance&&$('auto-next').checked&&oldList[idx+1]){ui.active=oldList[idx+1].id;ui.zoom=false;ui.zoomScale=1;if(ui.group)ui.group=oldList[idx+1].group_id;}await load();$('saved-status').textContent='✓ Guardado en este equipo';}catch(e){$('saved-status').textContent='No guardado';toast(e.message,true);}
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
$('layout-choice').onchange=()=>{ui.layout=$('layout-choice').value;render();};
new ResizeObserver(()=>{if(ui.data&&ui.layout==='auto'&&ui.view==='compare')viewerLayout();else arrangeComparison();refreshZoom();}).observe($('stage'));
$('select-group').onclick=()=>{visible().forEach(s=>ui.selected.add(s.id));render();};
$('compare').onclick=()=>{if(ui.selected.size<2){if(ui.active)ui.selected.add(ui.active);const next=visible().find(s=>!ui.selected.has(s.id));if(next)ui.selected.add(next.id);}if(ui.selected.size<2)return toast('Selecciona al menos dos tomas.');if(ui.selected.size>4)toast('Se comparan las primeras cuatro de la selección.');ui.view=ui.view==='compare'?'single':'compare';ui.zoom=false;render();};
$('merge').onclick=()=>{if(ui.selected.size<2)return toast('Selecciona dos o más tomas con sus casillas.');action('group',{ids:[...ui.selected]},'Grupo unido.');};
$('split').onclick=()=>{const ids=ui.selected.size?[...ui.selected]:(ui.active?[ui.active]:[]);action('group',{ids,split:true},'Tomas separadas y agrupación manual guardada.');};
$('sensitivity').onchange=()=>action('regroup',{sensitivity:$('sensitivity').value},'Agrupación actualizada. Tus decisiones siguen guardadas.');
for(const state of ['keep','reject','pending'])$(`mark-${state}`).onclick=()=>edit({state},true);
$('rotate-right').onclick=()=>edit({rotation:((current()?.rotation||0)+90)%360});$('rotate-left').onclick=()=>edit({rotation:((current()?.rotation||0)+270)%360});
$('zoom').onclick=()=>{ui.zoom=!ui.zoom;ui.zoomScale=1;refreshZoom();};$('previous').onclick=()=>navigate(-1);$('next').onclick=()=>navigate(1);
$('stars').onclick=e=>{const b=e.target.closest('[data-stars]');if(b)edit({stars:current()?.stars===Number(b.dataset.stars)?0:Number(b.dataset.stars)});};
$('faces').onclick=e=>{const b=e.target.closest('[data-face]');if(b&&ui.active)action('face',{id:ui.active,index:Number(b.dataset.face)},'Rostro principal actualizado.');};
$('undo').onclick=()=>action('undo',{},'Última decisión deshecha.');
$('analyze').onclick=()=>action('analyze',{},'Análisis local iniciado. Puedes seguir revisando.');$('pause').onclick=()=>action('pause',{},'Terminando las dos imágenes en curso; después se pausará.');
document.addEventListener('keydown',e=>{
  if(e.target.closest('input,select,textarea')||document.querySelector('dialog[open]'))return;
  if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();$('undo').click();return;}
  if(e.ctrlKey||e.metaKey||e.altKey)return;
  const key=e.key.toLowerCase();
  if(['p','x','u','r','c','arrowleft','arrowright','arrowup','arrowdown','0','1','2','3','4','5'].includes(key))e.preventDefault();
  if(e.repeat)return;
  if(key==='c')$('open-editor').click();
  if(key==='p')edit({state:'keep'},true);if(key==='x')edit({state:'reject'},true);if(key==='u')edit({state:'pending'},true);
  if(key==='arrowleft')navigate(-1);if(key==='arrowright')navigate(1);if(key==='r')$(e.shiftKey?'rotate-left':'rotate-right').click();
  if(key==='arrowup')navigateGroup(-1);if(key==='arrowdown')navigateGroup(1);
  if(/^[0-5]$/.test(key))edit({stars:Number(key)});
});
$('open-folder').onclick=()=>{$('folder-path').value=ui.data?.root||'';$('folder-dialog').showModal();};
let moveBatch=null;
$('move-keepers').onclick=async()=>{
  try{
    moveBatch=await api('move/prepare',{});
    $('move-summary').textContent=`${moveBatch.shots} tomas · ${moveBatch.files} archivos · ${(moveBatch.bytes/1024/1024).toFixed(1)} MB. ${moveBatch.skipped} tomas ya están en Seleccionadas.`;
    $('move-destination').textContent=moveBatch.destination;
    $('move-files').textContent=moveBatch.items.map(i=>`${i.path} → ${i.destination}`).join('\n');
    $('move-result').textContent=moveBatch.files?'': 'Todas las fotos que se quedan ya están en Seleccionadas.';
    $('confirm-move').disabled=!moveBatch.files;$('confirm-move').textContent=`Mover ${moveBatch.files} originales`;
    $('move-dialog').showModal();
  }catch(e){toast(e.message,true);}
};
$('confirm-move').onclick=async()=>{
  if(!moveBatch||ui.moving)return;
  ui.moving=true;$('confirm-move').disabled=true;$('move-result').textContent='Moviendo originales…';
  try{
    const result=await api('move/commit',{id:moveBatch.id,confirmed:true});
    $('move-result').textContent=`${result.moved} archivos movidos · ${result.failed} fallidos · ${result.not_attempted} sin intentar.`;
    if(result.failed)$('move-result').textContent+=' '+result.results.filter(r=>r.error).map(r=>r.error).join(' ');
    await load();
  }catch(e){$('move-result').textContent=e.message;}
  finally{moveBatch=null;ui.moving=false;render();}
};
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
