'use strict';
const defaults=()=>({crop:null,straighten:0,lut:null,intensity:1});
let editor=null,previewTimer;
function cropRotated(crop,degrees){if(!crop)return null;let[x,y,w,h]=crop;for(let i=0;i<((degrees%360)+360)%360/90;i++)[x,y,w,h]=[1-y-h,x,h,w];return[Math.max(0,x),Math.max(0,y),w,h];}
function lutOptions(selected=''){$('lut-select').replaceChildren(new Option('Original',''));(ui.data?.luts||[]).forEach(lut=>$('lut-select').add(new Option(lut.name,lut.id)));$('lut-select').value=selected||'';}
function openEditor(){
  const shot=current();if(!shot?.analysis)return;
  const settings=structuredClone(shot.adjustments||defaults());
  editor={id:shot.id,revision:shot.revision,rotation:shot.rotation,settings,crop:settings.crop?.slice()||[0,0,1,1],image:null,aspect:null,sequence:0,drag:null};
  $('editor-title').textContent=shot.name+' · Reencuadre y color';
  $('crop-ratio').value='free';$('straighten').value=settings.straighten;$('straighten-value').textContent=settings.straighten+'°';
  $('lut-intensity').value=Math.round(settings.intensity*100);$('intensity-value').textContent=Math.round(settings.intensity*100)+' %';
  $('editor-before').checked=false;$('lut-srgb').checked=false;$('lut-file').value='';
  $('batch-color').disabled=ui.selected.size<2;$('batch-color').textContent=`Aplicar color a ${ui.selected.size} seleccionadas`;
  lutOptions(settings.lut);$('editor-dialog').showModal();previewEditor();
}
function previewEditor(){
  if(!editor)return;
  clearTimeout(previewTimer);const e=editor,sequence=++e.sequence;
  $('editor-loading').hidden=false;$('editor-loading').textContent='Preparando vista sRGB…';$('editor-save').disabled=true;
  const draft={...e.settings,crop:null};if($('editor-before').checked)draft.intensity=0;
  const image=new Image();image.onload=()=>{if(editor!==e||sequence!==e.sequence)return;e.image=image;
    if(e.aspect){const[bw,bh]=baseOutputSize(),ratio=e.aspect*bh/bw;let[x,y,w,h]=e.crop;const cx=x+w/2,cy=y+h/2;h=w/ratio;if(h>1){h=1;w=ratio;}e.crop=[Math.max(0,Math.min(1-w,cx-w/2)),Math.max(0,Math.min(1-h,cy-h/2)),w,h];}
    $('editor-loading').hidden=true;$('editor-save').disabled=false;drawCrop();};
  image.onerror=()=>{if(editor!==e||sequence!==e.sequence)return;$('editor-loading').textContent='No se pudo cargar la vista. Revisa que el original esté disponible.';};
  image.src=`/media/${e.id}/edit-base?token=${token}&rotation=${e.rotation}&draft=${encodeURIComponent(JSON.stringify(draft))}`;
}
function debouncePreview(){clearTimeout(previewTimer);if(editor)editor.sequence++;$('editor-save').disabled=true;$('editor-loading').hidden=false;$('editor-loading').textContent='Actualizando vista sRGB…';previewTimer=setTimeout(previewEditor,180);}
function baseOutputSize(){
  if(!editor)return[0,0];const shot=ui.data.shots.find(s=>s.id===editor.id);if(!shot)return[0,0];
  let w=shot.analysis.width,h=shot.analysis.height;if(editor.rotation===90||editor.rotation===270)[w,h]=[h,w];
  const angle=Math.abs(editor.settings.straighten)*Math.PI/180;
  if(angle){const c=Math.cos(angle),s=Math.sin(angle),k=Math.min(w/(w*c+h*s),h/(w*s+h*c));w=Math.max(1,Math.floor(w*k)-2);h=Math.max(1,Math.floor(h*k)-2);}
  return[w,h];
}
function outputSize(){
  const[w,h]=baseOutputSize();if(!editor)return[w,h];
  const[x,y,cw,ch]=editor.crop;return[Math.floor((x+cw)*w+.5)-Math.floor(x*w+.5),Math.floor((y+ch)*h+.5)-Math.floor(y*h+.5)];
}
function drawCrop(){
  if(!editor?.image)return;const e=editor,canvas=$('crop-canvas'),ctx=canvas.getContext('2d');
  const box=canvas.getBoundingClientRect(),dpr=Math.min(2,window.devicePixelRatio||1);canvas.width=Math.round(box.width*dpr);canvas.height=Math.round(box.height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle='#0c110e';ctx.fillRect(0,0,box.width,box.height);
  const scale=Math.min((box.width-26)/e.image.naturalWidth,(box.height-26)/e.image.naturalHeight);
  const width=e.image.naturalWidth*scale,height=e.image.naturalHeight*scale,x=(box.width-width)/2,y=(box.height-height)/2;e.layout={x,y,width,height};
  ctx.drawImage(e.image,x,y,width,height);
  const[cx,cy,cw,ch]=e.crop,rx=x+cx*width,ry=y+cy*height,rw=cw*width,rh=ch*height;
  ctx.fillStyle='rgba(0,0,0,.62)';ctx.fillRect(x,y,width,ry-y);ctx.fillRect(x,ry+rh,width,y+height-ry-rh);ctx.fillRect(x,ry,rx-x,rh);ctx.fillRect(rx+rw,ry,x+width-rx-rw,rh);
  ctx.strokeStyle='#d3eedc';ctx.lineWidth=1.5;ctx.strokeRect(rx,ry,rw,rh);ctx.strokeStyle='rgba(230,245,234,.4)';ctx.lineWidth=.7;
  for(let i=1;i<3;i++){ctx.beginPath();ctx.moveTo(rx+rw*i/3,ry);ctx.lineTo(rx+rw*i/3,ry+rh);ctx.moveTo(rx,ry+rh*i/3);ctx.lineTo(rx+rw,ry+rh*i/3);ctx.stroke();}
  ctx.fillStyle='#d3eedc';for(const[xx,yy]of[[rx,ry],[rx+rw,ry],[rx+rw,ry+rh],[rx,ry+rh]])ctx.fillRect(xx-4,yy-4,8,8);
  ['x','y','w','h'].forEach((key,index)=>{const input=$('crop-'+key);if(document.activeElement!==input)input.value=(e.crop[index]*100).toFixed(1);});
  const[w,h]=outputSize();$('crop-dimensions').textContent=`Salida del recorte: ${w} × ${h} px · Arrastra las esquinas o el interior. También puedes usar los campos de porcentaje.`;
}
function fitRatio(ratio){
  if(!editor?.image)return;const e=editor;
  e.aspect=ratio;
  if(ratio){const[bw,bh]=baseOutputSize();const normal=ratio*bh/bw;const w=Math.min(1,normal),h=w/normal;e.crop=[(1-w)/2,(1-h)/2,w,h];}
  drawCrop();
}
function point(event){const rect=$('crop-canvas').getBoundingClientRect(),p=editor.layout;return[(event.clientX-rect.left-p.x)/p.width,(event.clientY-rect.top-p.y)/p.height];}
const canvas=$('crop-canvas');
canvas.addEventListener('pointerdown',event=>{
  if(!editor?.image||!$('editor-loading').hidden)return;
  const e=editor,p=point(event),[x,y,w,h]=e.crop,[px,py]=p,layout=e.layout;
  if(px<0||py<0||px>1||py>1)return;
  let handle=null;const corners=[['nw',x,y],['ne',x+w,y],['se',x+w,y+h],['sw',x,y+h]];
  for(const[name,cx,cy]of corners)if(Math.hypot((px-cx)*layout.width,(py-cy)*layout.height)<18)handle=name;
  let initial=e.crop.slice();
  if(!handle){if(px>=x&&px<=x+w&&py>=y&&py<=y+h)handle='move';else{handle='se';initial=[Math.min(.99,px),Math.min(.99,py),.01,.01];e.crop=initial.slice();}}
  e.drag={handle,point:p,crop:initial};canvas.setPointerCapture(event.pointerId);event.preventDefault();drawCrop();
});
canvas.addEventListener('pointermove',event=>{
  const e=editor;if(!e?.drag)return;const[px,py]=point(event),d=e.drag,[x,y,w,h]=d.crop;
  if(d.handle==='move'){e.crop=[Math.max(0,Math.min(1-w,x+px-d.point[0])),Math.max(0,Math.min(1-h,y+py-d.point[1])),w,h];}
  else{
    const west=d.handle.includes('w'),north=d.handle.includes('n'),ax=west?x+w:x,ay=north?y+h:y;
    const maxw=west?ax:1-ax,maxh=north?ay:1-ay;
    let nw=Math.max(.01,west?ax-px:px-ax),nh=Math.max(.01,north?ay-py:py-ay);
    if(e.aspect){const[bw,bh]=baseOutputSize();const ratio=e.aspect*bh/bw;if(nh*ratio>nw)nw=nh*ratio;nw=Math.min(nw,maxw,maxh*ratio);nh=nw/ratio;if(Math.min(nw,nh)<.01)return;}
    else{nw=Math.min(nw,maxw);nh=Math.min(nh,maxh);}
    e.crop=[west?ax-nw:ax,north?ay-nh:ay,nw,nh];
  }drawCrop();
});
function endDrag(){if(editor)editor.drag=null;}
canvas.addEventListener('pointerup',endDrag);canvas.addEventListener('pointercancel',endDrag);
window.addEventListener('resize',drawCrop);
$('open-editor').onclick=openEditor;
$('editor-dialog').addEventListener('close',()=>{editor=null;clearTimeout(previewTimer);});
$('crop-ratio').onchange=()=>{const parts=$('crop-ratio').value.split(':').map(Number);fitRatio(parts.length===2?parts[0]/parts[1]:null);};
$('crop-flip').onclick=()=>{if(!editor?.image)return;const[bw,bh]=baseOutputSize();const r=editor.aspect||(editor.crop[2]*bw/(editor.crop[3]*bh));fitRatio(1/r);};
for(const key of ['x','y','w','h'])$('crop-'+key).onchange=()=>{
  if(!editor)return;
  const values=['x','y','w','h'].map(k=>Number($('crop-'+k).value)/100);
  if(values.some(v=>!Number.isFinite(v))||values[0]<0||values[1]<0||values[2]<.01||values[3]<.01||values[0]+values[2]>1.00001||values[1]+values[3]>1.00001){toast('El recorte debe quedar dentro de la fotografía.',true);drawCrop();return;}
  editor.crop=values;editor.aspect=null;$('crop-ratio').value='free';drawCrop();
};
function editorRotate(degrees){if(!editor)return;editor.rotation=(editor.rotation+degrees+360)%360;editor.crop=cropRotated(editor.crop,degrees);if(editor.aspect)editor.aspect=1/editor.aspect;previewEditor();}
$('editor-left').onclick=()=>editorRotate(-90);$('editor-right').onclick=()=>editorRotate(90);
$('straighten').oninput=()=>{if(!editor)return;editor.settings.straighten=Number($('straighten').value);$('straighten-value').textContent=editor.settings.straighten+'°';debouncePreview();};
$('lut-select').onchange=()=>{if(!editor)return;editor.settings.lut=$('lut-select').value||null;previewEditor();};
$('lut-intensity').oninput=()=>{if(!editor)return;editor.settings.intensity=Number($('lut-intensity').value)/100;$('intensity-value').textContent=$('lut-intensity').value+' %';debouncePreview();};
$('editor-before').onchange=previewEditor;
$('lut-file').onchange=async()=>{
  const file=$('lut-file').files[0];if(!file||!editor)return;
  if(!$('lut-srgb').checked){toast('Confirma primero que el LUT fue creado para entrada y salida sRGB.',true);$('lut-file').value='';return;}
  if(file.size>12*1024*1024){toast('El LUT supera el límite de 12 MB.',true);return;}
  const e=editor;try{const lut=await api('luts/import',{name:file.name,text:await file.text(),srgb:true});await load();if(editor!==e)return;lutOptions(lut.id);e.settings.lut=lut.id;previewEditor();toast('LUT importado en este proyecto.');}catch(error){toast(error.message,true);}
};
$('editor-reset').onclick=()=>{if(!editor)return;editor.rotation=0;editor.crop=[0,0,1,1];editor.settings=defaults();editor.aspect=null;$('crop-ratio').value='free';$('straighten').value=0;$('straighten-value').textContent='0°';$('lut-select').value='';$('lut-intensity').value=100;$('intensity-value').textContent='100 %';previewEditor();};
$('editor-save').onclick=async()=>{
  if(!editor)return;const e=editor;const full=e.crop.every((v,i)=>Math.abs(v-[0,0,1,1][i])<1e-7);const settings={...e.settings,crop:full?null:e.crop.slice()};
  $('editor-save').disabled=true;
  try{await api('edit',{id:e.id,revision:e.revision,changes:{rotation:e.rotation,adjustments:settings}});$('editor-dialog').close();ui.before=false;await load();toast('Recorte y color guardados. Original conservado.');}
  catch(error){toast(error.message,true);$('editor-save').disabled=false;}
};
$('batch-color').onclick=async()=>{
  if(!editor||ui.selected.size<2)return;const e=editor;
  try{await api('color/batch',{ids:[...ui.selected],lut:e.settings.lut,intensity:e.settings.intensity});await load();e.revision=ui.data.shots.find(s=>s.id===e.id)?.revision??e.revision;toast(`Color aplicado a ${ui.selected.size} tomas. Sus recortes y giros se conservan.`);}catch(error){toast(error.message,true);}
};
$('before').onclick=()=>{ui.before=!ui.before;render();};
function exportIds(){if(!ui.data)return[];const scope=$('render-scope').value;if(scope==='current')return ui.active?[ui.active]:[];if(scope==='selected')return[...ui.selected];return ui.data.shots.filter(s=>scope==='all'||s.state==='keep').map(s=>s.id);}
function refreshExport(){
  const ids=exportIds(),job=ui.data?.export_job||{};const relevant=!job.project_id||job.project_id===ui.data?.id;
  $('render-count').textContent=`Se exportarán ${ids.length} tomas. Se guardarán archivos nuevos dentro de esta aplicación.`;
  $('render-start').disabled=!ids.length||job.running||ui.data?.job.running;
  $('render-progress').hidden=!job.running;$('render-cancel').hidden=!job.running;$('render-progress').max=job.total||1;$('render-progress').value=job.done||0;
  $('render-download').hidden=!job.ready||!relevant;
  if(job.ready&&relevant)$('render-download').href=`/api/render/file/${job.id}?token=${token}`;
  $('render-status').textContent=!relevant?'':job.running?`Creando JPG: ${job.done} / ${job.total}…`:job.error?job.error:job.ready?`${job.cancelled?'Cancelada. ':''}${job.files} JPG creados en ${job.seconds} s. ${job.errors.length} incidencias.${job.errors.length?' '+job.errors.map(e=>e.file+': '+e.error).join(' '):''}`:'';
}
$('render-scope').onchange=refreshExport;
$('render-start').onclick=async()=>{try{await api('render/start',{ids:exportIds(),max_edge:Number($('render-size').value),quality:95});await load();toast('Exportación local iniciada. El ZIP aparecerá aquí al terminar.');}catch(error){toast(error.message,true);}};
$('render-cancel').onclick=()=>action('render/cancel',{},'Se detendrá después de la foto en curso.');
