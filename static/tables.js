'use strict';
(() => {
 const root=$('#rich-body'),editor=window.memoEditor,picker=$('#table-picker'),trigger=$('#insert-table'),grid=$('#table-grid'),box=$('#table-selection-box'),handles=[...document.querySelectorAll('#table-selection-box .table-resize')];
 let active=null,mode='text',anchor=null,endpoint=null,selected=[],cellDrag=null,resize=null,frame=null,hoverTable=null;
 const clamp=(n,min,max)=>Math.max(min,Math.min(max,Math.round(n)));
 const element=node=>node?.nodeType===1?node:node?.parentElement;
 const available=()=>S.note&&!S.preview&&!S.attachmentBusy&&!root.hidden&&!$('#editor-view').hidden;
 const interact=()=>{S.tableInteracting=!picker.hidden||!!resize||!!active&&mode!=='text';};
 function cleanTable(table){return inline(memoRead(table)).querySelector('table');}
 function pointIn(cell){const r=document.createRange();r.selectNodeContents(cell);r.collapse(true);root.focus({preventScroll:true});getSelection().removeAllRanges();getSelection().addRange(r);editor.remember();}
 function coordinates(table){
  const map=[],cells=[];
  [...table.rows].forEach((row,r)=>{map[r]??=[];let c=0;for(const cell of row.cells){while(map[r][c])c++;const rs=cell.rowSpan||table.rows.length-r,cs=cell.colSpan;const entry={cell,r,c,rs,cs};cells.push(entry);for(let y=r;y<r+rs;y++){map[y]??=[];for(let x=c;x<c+cs;x++)map[y][x]=entry;}c+=cs;}});
  return {map,cells};
 }
 function paintSelection(){
  if(!active)return;
  active.classList.toggle('table-selected',mode==='table');active.classList.toggle('cell-selection-mode',mode==='cells');
  for(const cell of active.querySelectorAll('td,th')){const chosen=mode==='cells'&&selected.includes(cell);cell.classList.toggle('cell-selected',chosen);if(chosen)cell.setAttribute('aria-selected','true');else cell.removeAttribute('aria-selected');}
  interact();position();
 }
 function selectCells(first,last=first){
  if(!active||!first||!last)return;const all=coordinates(active).cells,a=all.find(e=>e.cell===first),b=all.find(e=>e.cell===last);if(!a||!b)return;
  const top=Math.min(a.r,b.r),left=Math.min(a.c,b.c),bottom=Math.max(a.r+a.rs,b.r+b.rs),right=Math.max(a.c+a.cs,b.c+b.cs);
  selected=all.filter(e=>e.r<bottom&&e.r+e.rs>top&&e.c<right&&e.c+e.cs>left).map(e=>e.cell);anchor=first;endpoint=last;paintSelection();
 }
 function setActive(table,nextMode='text',cell=null){
  if(!available()||!table||!root.contains(table))return;
  if(active!==table){clear(false);active=table;}
  mode=nextMode;
  if(mode==='cells')selectCells(cell||active.querySelector('td,th'));
  else{selected=[];anchor=endpoint=null;paintSelection();}
  if(mode!=='text'){root.focus({preventScroll:true});getSelection().removeAllRanges();}
 }
 function clear(close=true){
  cancelResize();hoverBorder(null);if(active){active.classList.remove('table-selected','cell-selection-mode');for(const cell of active.querySelectorAll('.cell-selected')){cell.classList.remove('cell-selected');cell.removeAttribute('aria-selected');}}
  active=null;mode='text';anchor=endpoint=null;selected=[];cellDrag=null;box.hidden=true;if(close)closePicker(false);interact();
 }
 function position(){
  if(!active)return;if(!available()||!root.contains(active)){clear();return;}
  const rect=active.getBoundingClientRect();box.hidden=mode!=='table'||rect.bottom<0||rect.top>innerHeight;
  box.style.left=(rect.left-2)+'px';box.style.top=(rect.top-2)+'px';box.style.width=(rect.width+4)+'px';box.style.height=(rect.height+4)+'px';
 }
 function schedulePosition(){if(frame)return;frame=requestAnimationFrame(()=>{frame=null;position();});}
 function replaceTable(copy,nextMode=mode){
  if(!active||!available()||!root.contains(active))return;
  const old=active,id=crypto.randomUUID();copy.dataset.tableEdit=id;
  const r=document.createRange();r.selectNode(old);root.focus({preventScroll:true});getSelection().removeAllRanges();getSelection().addRange(r);
  document.execCommand('insertHTML',false,copy.outerHTML);
  const inserted=root.querySelector(`[data-table-edit="${id}"]`);if(inserted){delete inserted.dataset.tableEdit;restoreDimensions();setActive(inserted,nextMode);}
  editor.remember();editor.sync();
 }
 function removeTable(){
  if(!active||!available())return;
  const table=active;clear();const r=document.createRange();r.selectNode(table);root.focus({preventScroll:true});getSelection().removeAllRanges();getSelection().addRange(r);document.execCommand('delete');editor.remember();editor.sync();
 }
 function clearCells(){
  if(!selected.length)return;const indices=coordinates(active).cells.filter(e=>selected.includes(e.cell)).map(e=>({r:e.r,c:e.c})),copy=cleanTable(active),layout=coordinates(copy);
  for(const point of indices)layout.map[point.r][point.c].cell.replaceChildren(document.createElement('br'));
  replaceTable(copy,'cells');const updated=coordinates(active).map;selectCells(updated[indices[0].r][indices[0].c].cell,updated[indices.at(-1).r][indices.at(-1).c].cell);
 }
 function copySelection(e){
  if(!active||mode==='text'||!available()||!root.contains(e.target)||!e.clipboardData)return;
  const source=cleanTable(active),layout=coordinates(source),original=coordinates(active);
  const chosen=mode==='table'?original.cells:original.cells.filter(entry=>selected.includes(entry.cell));
  if(!chosen.length)return;
  const top=Math.min(...chosen.map(p=>p.r)),left=Math.min(...chosen.map(p=>p.c)),bottom=Math.max(...chosen.map(p=>p.r+p.rs)),right=Math.max(...chosen.map(p=>p.c+p.cs));
  const table=document.createElement('table'),lines=[];
  for(let r=top;r<bottom;r++){
   const row=table.insertRow(),values=[];
   for(let c=left;c<right;c++){
    const entry=layout.map[r]?.[c];
    if(entry&&entry.r===r&&entry.c===c){
     const cell=entry.cell.cloneNode(true);row.append(cell);
     const plain=cell.cloneNode(true);plain.querySelectorAll('br').forEach(br=>br.replaceWith('\n'));
     values.push(plain.textContent);
    }else values.push('');
   }
   lines.push(values.map(value=>/[\t\n\r"]/.test(value)?'"'+value.replaceAll('"','""')+'"':value).join('\t'));
  }
  e.preventDefault();e.clipboardData.setData('application/x-hanjul-table',memoRead(table));
  for(const font of table.querySelectorAll('font[size]')){const span=document.createElement('span');span.style.fontSize=memoFontSizes[Number(font.getAttribute('size'))-1]+'px';span.append(...font.childNodes);font.replaceWith(span);}
  e.clipboardData.setData('text/html',table.outerHTML);e.clipboardData.setData('text/plain',lines.join('\n'));
 }
 root.addEventListener('copy',copySelection);
 function preparePaste(){
  if(!active||mode!=='cells'||!selected.length)return;
  const cell=coordinates(active).cells.find(entry=>selected.includes(entry.cell)).cell;
  setActive(active,'text');pointIn(cell);
 }
 function borderTable(e){
  if(!root.contains(e.target)&&e.target!==root.parentElement)return null;
  const direct=e.target.closest?.('table'),tables=direct?[direct]:[...root.querySelectorAll('table')];
  return tables.find(table=>{const r=table.getBoundingClientRect();return e.clientX>=r.left-5&&e.clientX<=r.right+5&&e.clientY>=r.top-5&&e.clientY<=r.bottom+5&&Math.min(Math.abs(e.clientX-r.left),Math.abs(e.clientX-r.right),Math.abs(e.clientY-r.top),Math.abs(e.clientY-r.bottom))<=5;});
 }
 function hoverBorder(table){
  if(hoverTable===table)return;hoverTable?.classList.remove('table-border-hover');hoverTable=table||null;hoverTable?.classList.add('table-border-hover');root.style.cursor=table?'default':'';
 }
 function caretAt(e,cell){
  let range;
  if(document.caretPositionFromPoint){const point=document.caretPositionFromPoint(e.clientX,e.clientY);if(point){range=document.createRange();range.setStart(point.offsetNode,point.offset);range.collapse(true);}}
  else range=document.caretRangeFromPoint(e.clientX,e.clientY);
  if(!range||!cell.contains(range.startContainer)){pointIn(cell);return;}
  root.focus({preventScroll:true});getSelection().removeAllRanges();getSelection().addRange(range);editor.remember();
 }
 document.addEventListener('pointermove',e=>{if(!resize&&!cellDrag&&available())hoverBorder(box.contains(e.target)?null:borderTable(e));});
 document.addEventListener('pointerleave',()=>hoverBorder(null));
 document.addEventListener('pointerdown',e=>{
  if(e.button!==0||!available()||box.contains(e.target))return;
  const border=borderTable(e);if(border){e.preventDefault();setActive(border,'table');}
 },true);
 root.addEventListener('pointerdown',e=>{
  if(e.defaultPrevented||e.button!==0||!available())return;
  const cell=e.target.closest('td,th'),table=cell?.closest('table');if(!table)return;
  if(e.target.closest('input,button,a,.inline-image')){setActive(table,'text');return;}
  // A click still places the caret. Only an unmodified drag becomes a cell range.
  if(e.metaKey||e.ctrlKey){setActive(table,'text');cellDrag=null;return;}
  const first=e.shiftKey&&active===table&&mode==='cells'&&anchor?anchor:cell;
  e.preventDefault();setActive(table,'text');caretAt(e,cell);
  cellDrag={pointerId:e.pointerId,first,x:e.clientX,y:e.clientY,moved:false};
  if(e.shiftKey){mode='cells';selectCells(first,cell);cellDrag.moved=true;getSelection().removeAllRanges();}
 });
 document.addEventListener('pointermove',e=>{
  if(!cellDrag||e.pointerId!==cellDrag.pointerId)return;
  if(!cellDrag.moved&&Math.hypot(e.clientX-cellDrag.x,e.clientY-cellDrag.y)<4)return;
  const cell=document.elementFromPoint(e.clientX,e.clientY)?.closest('td,th');if(!cell||cell.closest('table')!==active)return;
  e.preventDefault();cellDrag.moved=true;mode='cells';selectCells(cellDrag.first,cell);getSelection().removeAllRanges();hoverBorder(null);
 });
 document.addEventListener('pointerup',()=>cellDrag=null);document.addEventListener('pointercancel',()=>cellDrag=null);
 root.addEventListener('dragstart',e=>{if(cellDrag){e.preventDefault();}});
 document.addEventListener('selectionchange',()=>{if(mode!=='text'||resize)return;const table=element(getSelection().anchorNode)?.closest('table');if(table&&root.contains(table))setActive(table,'text');});
 document.addEventListener('pointerdown',e=>{
  if(!picker.hidden&&!picker.contains(e.target)&&!trigger.contains(e.target))closePicker(false);
  if(active&&!active.contains(e.target)&&!box.contains(e.target)&&borderTable(e)!==active)clear(false);
 });
 document.addEventListener('keydown',e=>{
  if(!picker.hidden&&e.key==='Escape'){e.preventDefault();closePicker();return;}
  if(!active||!available()||e.isComposing||S.composing)return;
  const fromEditor=root.contains(e.target)||box.contains(e.target);
  if(!fromEditor||e.target.matches('input,textarea,select'))return;
  if(e.key==='Escape'){e.preventDefault();const table=active;clear();pointIn(table.querySelector('td,th'));return;}
  if(mode==='text')return;
  if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();e.stopImmediatePropagation();if(mode==='table')removeTable();else clearCells();return;}
  if(e.key==='Enter'&&!box.contains(e.target)){e.preventDefault();const cell=endpoint||active.querySelector('td,th');setActive(active,'text');pointIn(cell);return;}
  if(mode==='cells'&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){
   e.preventDefault();e.stopImmediatePropagation();const layout=coordinates(active),current=layout.cells.find(p=>p.cell===endpoint);if(!current)return;
   const r=current.r+(e.key==='ArrowDown'?current.rs:e.key==='ArrowUp'?-1:0),c=current.c+(e.key==='ArrowRight'?current.cs:e.key==='ArrowLeft'?-1:0),next=layout.map[r]?.[c]?.cell;
   if(next)selectCells(e.shiftKey?anchor:next,next);return;
  }
  if(e.key.length===1&&!e.metaKey&&!e.ctrlKey&&!box.contains(e.target)){e.preventDefault();e.stopImmediatePropagation();}
 },true);
 function paintSize(table,width,height){
  if(width===null){delete table.dataset.width;table.style.width='';}else{table.dataset.width=width;table.style.width=width+'%';}
  if(height===null){delete table.dataset.height;table.style.height='';}else{table.dataset.height=height;table.style.height=height+'px';}
 }
 function beginResize(kind){
  if(!active||!available())return null;
  if(!resize)resize={kind,table:active,noteId:S.note.id,width:active.dataset.width?Number(active.dataset.width):null,height:active.dataset.height?Number(active.dataset.height):null};interact();return resize;
 }
 function cancelResize(){if(!resize)return;const old=resize;resize=null;paintSize(old.table,old.width,old.height);document.body.classList.remove('resizing-table');if(old.pointerId!==undefined&&old.handle.hasPointerCapture(old.pointerId))old.handle.releasePointerCapture(old.pointerId);interact();}
 function finishResize(){
  if(!resize)return;const old=resize,width=old.table.dataset.width?Number(old.table.dataset.width):null,height=old.table.dataset.height?Number(old.table.dataset.height):null;cancelResize();
  if(root.contains(old.table)&&S.note?.id===old.noteId&&(width!==old.width||height!==old.height)){const copy=cleanTable(old.table);paintSize(copy,width,height);replaceTable(copy,'table');}else paintSelection();
 }
 for(const handle of handles){
 handle.addEventListener('pointerdown',e=>{
  if(e.button!==0)return;e.preventDefault();const state=beginResize('pointer');if(!state)return;
  const rect=active.getBoundingClientRect();Object.assign(state,{handle,corner:handle.dataset.corner,pointerId:e.pointerId,x:e.clientX,y:e.clientY,startWidth:rect.width,startHeight:rect.height,parentWidth:active.parentElement.getBoundingClientRect().width});handle.setPointerCapture(e.pointerId);handle.focus({preventScroll:true});document.body.classList.add('resizing-table');
 });
 handle.addEventListener('pointermove',e=>{
  if(resize?.kind!=='pointer'||e.pointerId!==resize.pointerId)return;e.preventDefault();
  const width=clamp((resize.startWidth+(e.clientX-resize.x)*(resize.corner.includes('w')?-1:resize.corner.includes('e')?1:0))/resize.parentWidth*100,20,100),height=clamp(resize.startHeight+(e.clientY-resize.y)*(resize.corner.includes('n')?-1:resize.corner.includes('s')?1:0),active.rows.length*32+1,20000);
  paintSize(active,width,height);position();
 });
 handle.addEventListener('pointerup',finishResize);handle.addEventListener('pointercancel',()=>{cancelResize();paintSelection();});handle.addEventListener('lostpointercapture',()=>{if(resize?.kind==='pointer'){cancelResize();paintSelection();}});
 handle.addEventListener('keydown',e=>{
  if(!active||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();e.stopPropagation();
  const copy=cleanTable(active),width=Number(active.dataset.width)||100,height=Number(active.dataset.height)||Math.round(active.getBoundingClientRect().height);
  paintSize(copy,clamp(width+(e.key==='ArrowRight'?5:e.key==='ArrowLeft'?-5:0),20,100),clamp(height+(e.key==='ArrowDown'?20:e.key==='ArrowUp'?-20:0),active.rows.length*32+1,20000));replaceTable(copy,'table');handle.focus({preventScroll:true});
 });
 }
 document.addEventListener('keydown',e=>root.classList.toggle('table-text-modifier',e.metaKey||e.ctrlKey));
 document.addEventListener('keyup',e=>root.classList.toggle('table-text-modifier',e.metaKey||e.ctrlKey));
 window.addEventListener('blur',()=>{cancelResize();cellDrag=null;hoverBorder(null);root.classList.remove('table-text-modifier');position();});window.addEventListener('resize',()=>{cancelResize();position();if(!picker.hidden)positionPicker();});window.addEventListener('scroll',schedulePosition,true);
 new ResizeObserver(schedulePosition).observe(root);
 new MutationObserver(()=>{if(active&&!root.contains(active))clear(false);else schedulePosition();}).observe(root,{childList:true,subtree:true});
 new MutationObserver(()=>{if(!available())clear();}).observe($('#editor-view'),{attributes:true,attributeFilter:['hidden']});
 function restoreDimensions(){for(const table of root.querySelectorAll('table')){table.style.width=table.dataset.width?table.dataset.width+'%':'';table.style.height=table.dataset.height?table.dataset.height+'px':'';}}
 root.addEventListener('input',()=>{restoreDimensions();schedulePosition();});
 // Grid picker: the hovered or focused square is the bottom-right of the new table.
 const columns=10,rows=8;let chosenRow=1,chosenCol=1;
 function highlight(r,c){chosenRow=r;chosenCol=c;$('#table-grid-size').textContent=`${c}열 × ${r}행`;for(const button of grid.querySelectorAll('button')){button.classList.toggle('chosen',Number(button.dataset.row)<=r&&Number(button.dataset.col)<=c);button.tabIndex=Number(button.dataset.row)===r&&Number(button.dataset.col)===c?0:-1;}}
 for(let r=1;r<=rows;r++){
  const row=document.createElement('div');row.setAttribute('role','row');
  for(let c=1;c<=columns;c++){
   const button=document.createElement('button');button.type='button';button.dataset.row=r;button.dataset.col=c;button.setAttribute('role','gridcell');button.setAttribute('aria-label',`${c}열 × ${r}행 표 삽입`);
   button.addEventListener('pointerenter',()=>highlight(r,c));button.addEventListener('focus',()=>highlight(r,c));button.onclick=()=>insertTable(r,c);row.append(button);
  }grid.append(row);
 }
 function positionPicker(){const rect=trigger.getBoundingClientRect();picker.style.left=clamp(rect.left,8,innerWidth-picker.offsetWidth-8)+'px';picker.style.top=clamp(rect.bottom+6,8,innerHeight-picker.offsetHeight-8)+'px';}
 function closePicker(focus=true){if(picker.hidden)return;picker.hidden=true;trigger.setAttribute('aria-expanded','false');interact();if(focus){editor.restoreSelection();}}
 function insertTable(r,c){
  if(!available())return;closePicker(false);clear(false);editor.restoreSelection();
  const range=editor.range(),inTable=element(range.startContainer)?.closest('table');if(inTable){range.setStartAfter(inTable);range.collapse(true);}
  const table=document.createElement('table');for(let y=0;y<r;y++){const row=table.insertRow();for(let x=0;x<c;x++)row.insertCell().append(document.createElement('br'));}
  const id=crypto.randomUUID();table.dataset.tableEdit=id;document.execCommand('insertHTML',false,'<div><br></div>'+table.outerHTML+'<div><br></div>');
  const inserted=root.querySelector(`[data-table-edit="${id}"]`);if(inserted){delete inserted.dataset.tableEdit;pointIn(inserted.querySelector('td'));setActive(inserted,'text');}editor.remember();editor.sync();
 }
 trigger.onclick=()=>{if(!picker.hidden){closePicker();return;}if(S.preview)togglePreview();editor.remember();clear(false);picker.hidden=false;trigger.setAttribute('aria-expanded','true');highlight(1,1);positionPicker();interact();grid.querySelector('button').focus({preventScroll:true});};
 $('#table-picker-close').onclick=()=>closePicker();
 grid.addEventListener('keydown',e=>{let r=chosenRow,c=chosenCol;if(e.key==='ArrowRight')c++;else if(e.key==='ArrowLeft')c--;else if(e.key==='ArrowDown')r++;else if(e.key==='ArrowUp')r--;else return;e.preventDefault();r=clamp(r,1,rows);c=clamp(c,1,columns);grid.querySelector(`[data-row="${r}"][data-col="${c}"]`).focus();});
 $('#table-form').onsubmit=e=>{e.preventDefault();const r=Number($('#table-rows').value),c=Number($('#table-cols').value);if(Number.isInteger(r)&&r>=1&&r<=20&&Number.isInteger(c)&&c>=1&&c<=10)insertTable(r,c);};
 picker.querySelector('details').addEventListener('toggle',positionPicker);
 window.memoTables={clear,preparePaste};
})();
