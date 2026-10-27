'use strict';
(() => {
 const source=document.querySelector('#body'),root=document.querySelector('#rich-body');
 let bookmark=null,composing=false,pendingFont=null;
 const read=memoRead;
 // :only-child ignores text nodes, so line-break markup cannot determine emptiness.
 function updatePlaceholder(){root.classList.toggle('is-empty',!root.textContent.trim()&&!root.querySelector('img,table,input,hr'));}
 function sync(){updatePlaceholder();source.value=read(root);source.dispatchEvent(new Event('input',{bubbles:true}));}
 function remember(){const s=getSelection();if(s.rangeCount&&root.contains(s.anchorNode)&&root.contains(s.focusNode))bookmark=s.getRangeAt(0).cloneRange();}
 function activeRange(){const s=getSelection();if(s.rangeCount&&root.contains(s.anchorNode)&&root.contains(s.focusNode))return s.getRangeAt(0);if(bookmark&&root.contains(bookmark.startContainer)&&root.contains(bookmark.endContainer))return bookmark;const r=document.createRange();r.selectNodeContents(root);r.collapse(false);return r;}
 function sourceOffset(range){
  // Serialize a marker in a clone so positions include opening formatting/table tags.
  const path=[];let node=range.startContainer;
  while(node!==root){path.unshift([...node.parentNode.childNodes].indexOf(node));node=node.parentNode;}
  const copy=root.cloneNode(true);node=copy;for(const index of path)node=node.childNodes[index];
  const marker='memo-caret-'+crypto.randomUUID(),r=document.createRange();r.setStart(node,range.startOffset);r.collapse(true);r.insertNode(document.createTextNode(marker));
  return read(copy).indexOf(marker);
 }
 function caret(offset){
  const r=document.createRange(),walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT),points=[];
  while(walker.nextNode()){
   const node=walker.currentNode;if(node.parentElement?.closest('[contenteditable="false"]'))continue;
   if(node.nodeType===3)points.push({node,offset:0});
   else if(node.dataset?.markdown!==undefined)points.push({node:node.parentNode,offset:[...node.parentNode.childNodes].indexOf(node)+1});
  }
  let lo=0,hi=points.length-1,best=null;
  while(lo<=hi){
   const mid=(lo+hi)>>1,point=points[mid];r.setStart(point.node,point.offset);r.collapse(true);const start=sourceOffset(r);
   if(start<=offset){best={...point,start};lo=mid+1;}else hi=mid-1;
  }
  if(best)r.setStart(best.node,best.node.nodeType===3?Math.min(best.node.length,offset-best.start):best.offset);
  else{r.selectNodeContents(root);r.collapse(false);}
  r.collapse(true);const selection=getSelection();selection.removeAllRanges();selection.addRange(r);bookmark=r.cloneRange();
 }
 function load(offset){
  clearImageSelection();window.memoTables?.clear();
  const frag=document.createDocumentFragment();for(const line of source.value.split('\n'))frag.append(memoLine(line));
  root.replaceChildren(frag);updatePlaceholder();source.hidden=true;root.hidden=S.preview;bookmark=null;pendingFont=null;
  if(offset!==undefined){root.focus();caret(offset);}
 }
 function restoreSelection(){
  const r=activeRange();root.focus();const selection=getSelection();selection.removeAllRanges();selection.addRange(r);return r;
 }
 function insert(text){
  if(S.preview)togglePreview();restoreSelection();
  const container=document.createElement('div');
  text.split('\n').forEach((line,i)=>{if(i)container.append(document.createElement('br'));container.append(inline(line));});
  document.execCommand('insertHTML',false,container.innerHTML);remember();sync();
 }
 function format(command,value=null){
  if(S.attachmentBusy||composing)return;
  if(S.preview)togglePreview();restoreSelection();
  // Native editing commands preserve selection, typing styles and browser undo.
  document.execCommand('styleWithCSS',false,false);
  document.execCommand(command,false,value);remember();
  if(command==='fontSize'){const r=activeRange();pendingFont=r.collapsed?{value,node:r.startContainer,offset:r.startOffset}:null;}
  sync();updateToolbar();
 }
 function updateToolbar(){
  if(!S.note||S.preview)return;
  const selection=getSelection();if(!root.contains(selection.anchorNode))return;
  document.querySelector('#format-bold').setAttribute('aria-pressed',String(document.queryCommandState('bold')));
  document.querySelector('#format-strike').setAttribute('aria-pressed',String(document.queryCommandState('strikeThrough')));
  const anchor=selection.anchorNode,element=anchor.nodeType===1?anchor:anchor.parentElement;
  const index=memoFontSizes.indexOf(parseFloat(getComputedStyle(element).fontSize));
  if(pendingFont&&(!selection.isCollapsed||selection.anchorNode!==pendingFont.node||selection.anchorOffset!==pendingFont.offset))pendingFont=null;
  document.querySelector('#font-size').value=pendingFont?.value||String(index<0?3:index+1);
 }
 for(const id of ['format-bold','format-strike','insert-table'])document.querySelector('#'+id).addEventListener('mousedown',e=>e.preventDefault());
 document.querySelector('#format-bold').onclick=()=>format('bold');
 document.querySelector('#format-strike').onclick=()=>format('strikeThrough');
 document.querySelector('#font-size').onchange=e=>format('fontSize',e.target.value);
 document.addEventListener('selectionchange',updateToolbar);
 root.addEventListener('keydown',e=>{
  if(composing||e.isComposing)return;
  if((e.metaKey||e.ctrlKey)&&!e.altKey&&['+','=','-','_'].includes(e.key)){
   e.preventDefault();const current=Number(document.querySelector('#font-size').value)||3;format('fontSize',String(Math.max(1,Math.min(7,current+(['+','='].includes(e.key)?1:-1)))));return;
  }
  if(checklistKey(e))return;
  if((e.metaKey||e.ctrlKey)&&!e.altKey&&e.key.toLowerCase()==='b'){e.preventDefault();format('bold');}
  if(e.key==='Tab'){
   const anchor=getSelection().anchorNode,cell=(anchor?.nodeType===1?anchor:anchor?.parentElement)?.closest('td,th');if(!cell||!root.contains(cell))return;
   const table=cell.closest('table'),cells=[...table.querySelectorAll('td,th')],next=cells[cells.indexOf(cell)+(e.shiftKey?-1:1)];
   let outside=table;while(outside.parentNode!==root&&!(e.shiftKey?outside.previousSibling:outside.nextSibling))outside=outside.parentNode;
   const target=next||(e.shiftKey?outside.previousSibling:outside.nextSibling);
   if(target){e.preventDefault();const range=document.createRange();range.selectNodeContents(target);range.collapse(!e.shiftKey);getSelection().removeAllRanges();getSelection().addRange(range);remember();}
  }
 });
 function selectedElement(){const node=activeRange().startContainer;return node.nodeType===1?node:node.parentElement;}
 function putRows(rows,focusIndex=rows.length-1){
  const id=crypto.randomUUID(),target=rows[focusIndex].querySelector('.check-text')||rows[focusIndex];target.dataset.memoFocus=id;
  document.execCommand('insertHTML',false,rows.map(row=>row.outerHTML).join(''));
  const inserted=root.querySelector(`[data-memo-focus="${id}"]`);
  if(inserted){delete inserted.dataset.memoFocus;const r=document.createRange();r.selectNodeContents(inserted);r.collapse(true);getSelection().removeAllRanges();getSelection().addRange(r);}
  remember();sync();
 }
 function checklist(){
  if(S.attachmentBusy||composing)return;if(S.preview)togglePreview();const r=restoreSelection(),element=selectedElement(),existing=element.closest('.check-row');
  if(existing?.querySelector('.check-marker')){removeChecklist(existing);return;}
  const line=element.closest('#rich-body>div,#rich-body>p');
  if(line&&!line.querySelector('table')&&line.contains(r.endContainer)){const text=read(line);r.selectNode(line);putRows([memoCheckRow(text)]);}
  else if(root.childNodes.length===1&&root.firstChild.nodeType===3&&!root.textContent.includes('\n')){const text=read(root);r.selectNodeContents(root);putRows([memoCheckRow(text)]);}
  else putRows([memoCheckRow(read(r.cloneContents()))]);
 }
 function removeChecklist(row){
  const r=activeRange();r.selectNode(row.querySelector('.check-marker'));document.execCommand('delete');
  const content=row.querySelector('.check-text');if(content&&root.contains(content)){r.selectNodeContents(content);r.collapse(true);getSelection().removeAllRanges();getSelection().addRange(r);}
  remember();sync();
 }
 function checklistKey(e){
  if(!['Enter','Backspace'].includes(e.key)||e.shiftKey||e.metaKey||e.ctrlKey||e.altKey)return false;
  const r=activeRange(),content=selectedElement().closest('.check-text'),row=content?.closest('.check-row');
  if(!row?.querySelector('.check-marker')||!content.contains(r.endContainer))return false;
  const before=document.createRange();before.selectNodeContents(content);before.setEnd(r.startContainer,r.startOffset);
  const after=document.createRange();after.selectNodeContents(content);after.setStart(r.endContainer,r.endOffset);
  if(e.key==='Backspace'&&(!r.collapsed||read(before.cloneContents())))return false;
  e.preventDefault();
  const empty=!read(content).trim();
  if(e.key==='Backspace'||empty){removeChecklist(row);return true;}
  const rows=[memoCheckRow(read(before.cloneContents()),row.querySelector('input').checked),memoCheckRow(read(after.cloneContents()))];
  r.selectNode(row);putRows(rows);return true;
 }
 root.addEventListener('change',e=>{
  const marker=e.target.closest('.check-marker');if(!marker)return;
  const input=marker.querySelector('input');marker.dataset.markdown=input.checked?'- [x] ':'- [ ] ';
  input.toggleAttribute('checked',input.checked);sync();
 });
 function pasteTable(table){
  restoreSelection();const cell=selectedElement().closest('td,th'),current=cell?.closest('table');
  if(current){
   if(current.querySelector('[rowspan],[colspan]')||table.querySelector('[rowspan],[colspan]')){toast('병합된 셀이 있는 표는 기존 표 밖에 붙여넣어 주세요.');return;}
   const rowIndex=cell.parentElement.rowIndex,colIndex=cell.cellIndex,copy=current.cloneNode(true);
   const height=Math.max(copy.rows.length,rowIndex+table.rows.length),width=Math.max(...[...copy.rows].map(row=>row.cells.length),colIndex+Math.max(...[...table.rows].map(row=>row.cells.length)));
   if(height>200||width>50){toast('표는 200행, 50열까지 붙여넣을 수 있습니다.');return;}
   while(copy.rows.length<height)copy.insertRow();for(const row of copy.rows)while(row.cells.length<width)row.insertCell().append(document.createElement('br'));
   [...table.rows].forEach((row,r)=>[...row.cells].forEach((source,c)=>copy.rows[rowIndex+r].cells[colIndex+c].replaceChildren(...[...source.childNodes].map(node=>node.cloneNode(true)))));
   const r=activeRange();r.selectNode(current);document.execCommand('insertHTML',false,copy.outerHTML);
  }else document.execCommand('insertHTML',false,'<div><br></div>'+table.outerHTML+'<div><br></div>');
  remember();sync();
 }
 root.addEventListener('input',()=>{if(composing)updatePlaceholder();else sync();});
 root.addEventListener('compositionstart',()=>{composing=true;S.composing=true;});
 root.addEventListener('compositionend',()=>{composing=false;S.composing=false;sync();});
 root.addEventListener('paste',e=>{
  e.preventDefault();if(S.attachmentBusy||!e.clipboardData)return;
  window.memoTables?.preparePaste();remember();
  const internal=e.clipboardData.getData('application/x-hanjul-table');
  if(internal&&internal.length<=4000000){const table=inline(internal).querySelector('table');if(table){pasteTable(table);return;}}
  try{const table=memoClipboardTable(e.clipboardData.getData('text/html'),e.clipboardData.getData('text/plain'));if(table){pasteTable(table);return;}}catch(error){toast(error.message);return;}
  const images=[...e.clipboardData.items].filter(item=>item.kind==='file'&&item.type.startsWith('image/')).map(item=>item.getAsFile()).filter(Boolean);
  if(!images.length)images.push(...[...e.clipboardData.files].filter(file=>file.type.startsWith('image/')));
  if(images.length){uploadAttachments(images,{atCaret:true});return;}
  insert(e.clipboardData.getData('text/plain'));
 });
 root.addEventListener('drop',e=>e.preventDefault());
 document.addEventListener('selectionchange',remember);
 window.memoEditor={load,insert,checklist,sync,remember,range:activeRange,restoreSelection,offset:()=>[...source.value.slice(0,sourceOffset(activeRange()))].length,insertLine:text=>{const r=activeRange(),prefix=document.createRange();prefix.selectNodeContents(root);prefix.setEnd(r.startContainer,r.startOffset);const before=read(prefix.cloneContents());insert((before&&!before.endsWith('\n')?'\n':'')+text);},focus:()=>root.focus(),read:()=>read(root)};
 const imageDialog=document.querySelector('#image-dialog'),width=document.querySelector('#image-width'),widthValue=document.querySelector('#image-width-value');
 let selectedImage=null,imageNoteId=null,drag=null;
 const clampWidth=value=>Math.max(20,Math.min(100,Math.round(value)));
 function imageWidth(frame){return Math.round(frame.querySelector('img').getBoundingClientRect().width/root.getBoundingClientRect().width*100);}
 function paintWidth(frame,value){
  const img=frame.querySelector('img');frame.style.width=value===null?'':value+'%';img.style.width=value===null?'':'100%';img.style.maxHeight=value===null?'':'none';
  const output=frame.querySelector('.image-size-value');if(output)output.textContent=(value??imageWidth(frame))+'%';
 }
 function commitWidth(frame,value){
  paintWidth(frame,value);
  frame.dataset.markdown=frame.dataset.markdown.replace(/(?: "width=\d{1,3}%")?\)$/,value===null?')':` "width=${value}%")`);
  if(value===null)delete frame.dataset.width;else frame.dataset.width=value;
  sync();
 }
 function finishResize(commit){
  if(!drag)return;
  const current=drag;drag=null;S.imageResizing=false;document.body.classList.remove('resizing-image');
  if(current.handle.hasPointerCapture(current.pointerId))current.handle.releasePointerCapture(current.pointerId);
  if(!root.contains(current.frame)||S.note?.id!==current.noteId)return;
  if(commit&&current.moved)commitWidth(current.frame,current.value);
  else paintWidth(current.frame,current.original);
 }
 function clearImageSelection(){
  finishResize(false);
  if(selectedImage){selectedImage.classList.remove('image-selected');selectedImage.querySelector('.image-controls')?.remove();}
  selectedImage=null;imageNoteId=null;
 }
 function openImageDialog(){
  if(!selectedImage)return;
  width.value=selectedImage.dataset.width||clampWidth(imageWidth(selectedImage));widthValue.value=width.value+'%';
  document.querySelector('#image-original').href=selectedImage.querySelector('a').href;
  imageDialog.showModal();width.focus();
 }
 function selectImage(frame){
  if(selectedImage===frame)return;
  clearImageSelection();selectedImage=frame;imageNoteId=S.note.id;frame.classList.add('image-selected');
  const controls=document.createElement('span');controls.className='image-controls';
  for(const [corner,label] of [['nw','왼쪽 위'],['ne','오른쪽 위'],['sw','왼쪽 아래'],['se','오른쪽 아래']]){
   const handle=document.createElement('button');handle.type='button';handle.className='image-resize-handle '+corner;handle.dataset.corner=corner;
   handle.setAttribute('aria-label',label+' 모서리 크기 조절');handle.title='드래그 또는 방향키로 크기 조절';controls.append(handle);
  }
  const tools=document.createElement('span');tools.className='image-tools';
  const output=document.createElement('span');output.className='image-size-value';output.textContent=imageWidth(frame)+'%';
  const size=document.createElement('button');size.type='button';size.textContent='크기 입력';size.onclick=openImageDialog;
  const original=document.createElement('a');original.href=frame.querySelector('a').href;original.target='_blank';original.rel='noopener noreferrer';original.textContent='원본 보기';
  tools.append(output,size,original);controls.append(tools);frame.append(controls);
 }
 root.addEventListener('click',e=>{
  if(e.target.closest('.image-controls'))return;
  const frame=e.target.closest('.inline-image');if(!frame||S.attachmentBusy)return;
  e.preventDefault();remember();selectImage(frame);
 });
 root.addEventListener('dragstart',e=>{if(e.target.closest('.inline-image'))e.preventDefault();});
 root.addEventListener('pointerdown',e=>{
  const handle=e.target.closest('.image-resize-handle');if(!handle||e.button!==0||S.attachmentBusy)return;
  e.preventDefault();const frame=handle.closest('.inline-image'),rect=frame.querySelector('img').getBoundingClientRect();
  drag={handle,frame,noteId:S.note.id,pointerId:e.pointerId,x:e.clientX,y:e.clientY,width:rect.width,ratio:rect.height/rect.width,parentWidth:root.getBoundingClientRect().width,original:frame.dataset.width?Number(frame.dataset.width):null,value:imageWidth(frame),corner:handle.dataset.corner,moved:false};
  S.imageResizing=true;document.body.classList.add('resizing-image');handle.setPointerCapture(e.pointerId);handle.focus({preventScroll:true});
 });
 root.addEventListener('pointermove',e=>{
  if(!drag||drag.pointerId!==e.pointerId)return;
  e.preventDefault();const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
  if(!drag.moved&&Math.hypot(dx,dy)<3)return;
  drag.moved=true;
  const sx=drag.corner.endsWith('w')?-1:1,sy=drag.corner.startsWith('n')?-1:1;
  const delta=(sx*dx+sy*dy*drag.ratio)/(1+drag.ratio*drag.ratio);
  drag.value=clampWidth((drag.width+delta)/drag.parentWidth*100);paintWidth(drag.frame,drag.value);
 });
 root.addEventListener('pointerup',e=>{if(drag?.pointerId===e.pointerId){e.preventDefault();finishResize(true);}});
 root.addEventListener('pointercancel',()=>finishResize(false));
 root.addEventListener('lostpointercapture',()=>finishResize(false));
 root.addEventListener('keydown',e=>{
  if(['Delete','Backspace'].includes(e.key)&&selectedImage&&root.contains(selectedImage)&&imageNoteId===S.note?.id&&!S.attachmentBusy&&!composing&&!e.isComposing&&!e.target.matches('input,textarea,select')){
   e.preventDefault();e.stopImmediatePropagation();const frame=selectedImage;clearImageSelection();
   const range=document.createRange();range.selectNode(frame);root.focus({preventScroll:true});getSelection().removeAllRanges();getSelection().addRange(range);
   document.execCommand('delete');remember();sync();return;
  }
  const handle=e.target.closest('.image-resize-handle');
  if(handle&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Home','End'].includes(e.key)){
   e.preventDefault();const frame=handle.closest('.inline-image'),delta=['ArrowLeft','ArrowDown'].includes(e.key)?-5:5;
   commitWidth(frame,e.key==='Home'?20:e.key==='End'?100:clampWidth(imageWidth(frame)+delta));return;
  }
  if(e.key===' '&&e.target.matches('.inline-image>a')){e.preventDefault();selectImage(e.target.parentElement);}
 },true);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!document.querySelector('dialog[open]')&&selectedImage){e.preventDefault();clearImageSelection();root.focus();}});
 document.addEventListener('pointerdown',e=>{if(selectedImage&&!selectedImage.contains(e.target)&&!imageDialog.contains(e.target))clearImageSelection();});
 window.addEventListener('blur',()=>finishResize(false));
 window.addEventListener('resize',()=>{finishResize(false);if(selectedImage){const output=selectedImage.querySelector('.image-size-value');if(output)output.textContent=imageWidth(selectedImage)+'%';}});
 width.oninput=()=>widthValue.value=width.value+'%';
 document.querySelector('#image-close').onclick=()=>imageDialog.close();
 function resizeImage(value){
  if(selectedImage&&root.contains(selectedImage)&&S.note?.id===imageNoteId)commitWidth(selectedImage,value);
  imageDialog.close();root.focus();
 }
 document.querySelector('#image-apply').onclick=()=>resizeImage(Number(width.value));
 document.querySelector('#image-reset').onclick=()=>resizeImage(null);
 const dialog=document.querySelector('#link-dialog'),url=document.querySelector('#link-url'),label=document.querySelector('#link-label'),error=document.querySelector('#link-error');
 document.querySelector('#insert-link').onclick=()=>{remember();url.value='';label.value='';error.textContent='';dialog.showModal();url.focus();};
 document.querySelector('#link-cancel').onclick=()=>dialog.close();
 document.querySelector('#link-form').onsubmit=e=>{e.preventDefault();let value=url.value.trim();try{const parsed=new URL(value);if(!['http:','https:'].includes(parsed.protocol))throw Error();value=parsed.href;}catch{error.textContent='http 또는 https로 시작하는 주소를 입력해 주세요.';return;}
  const title=label.value.trim().replace(/[\[\]\\\r\n]/g,' ');dialog.close();insert(title?`[${title}](${value.replace(/\(/g,'%28').replace(/\)/g,'%29')})`:value);
 };
})();
