'use strict';
const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const S={csrf:'',instance:'',state:'active',folderId:null,folders:[],note:null,dirty:false,saving:null,timer:null,conflict:false,offset:0,next:null,querySeq:0,tab:crypto.randomUUID(),scroll:0,loaded:40,localError:false,preview:false,selecting:false,selected:new Map()};
const dateFmt=new Intl.DateTimeFormat(undefined,{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const date=s=>dateFmt.format(new Date(s));
const escapeHTML=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(s){$('#toast').textContent=s;$('#toast').hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').hidden=true,5000);}
async function api(path,options={}){
 const originalOptions=options;
 const headers={...options.headers};if(S.csrf)headers['X-CSRF-Token']=S.csrf;
 if(options.body && !(options.body instanceof FormData)){headers['Content-Type']='application/json';options={...options,body:JSON.stringify(options.body)};}
 const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),path.startsWith('/import')?120000:15000);let res;try{res=await fetch('/api'+path,{...options,headers,signal:controller.signal});}finally{clearTimeout(timer);}let data;try{data=await res.json();}catch{data={error:'서버 응답을 확인할 수 없습니다.'};}
 if(res.status===428&&data.code==='REAUTH_REQUIRED'&&!options.reauthenticated){await window.confirmIdentity();return api(path,{...originalOptions,reauthenticated:true});}
 if(!res.ok){const e=new Error(data.error||'요청에 실패했습니다.');e.status=res.status;e.data=data;throw e;}return data;
}
function status(text,failed=false){$('#save-status').textContent=text;$('#save-status').classList.toggle('failed',failed);$('#retry').hidden=!failed||S.conflict;}
function fields(){return {id:S.note.id,folder_id:$('#note-folder').value||null,title:$('#note-title').value,body:$('#body').value,tags:$('#tags').value.split(',').map(s=>s.trim()).filter(Boolean),starred:S.note.starred,archived:S.note.archived,deleted:S.note.deleted,version:S.note.version};}
function draftKey(){return `hanjul:draft:${S.instance}:${S.note.id}:${S.tab}`;}
function isEmptyNote(n=fields()){return !((n.title+n.body.replace(/^\s*[-*](?:\s+\[[ xX]\])?\s*$/gm,'')).replace(/[\s\u200b\ufeff]/g,''))&&!(S.note.attachments||[]).length;}
function stash(){if(!S.note)return;if(isEmptyNote()){removeDraft();return;}try{localStorage.setItem(draftKey(),JSON.stringify({note:fields(),savedAt:new Date().toISOString()}));S.localError=false;}catch{S.localError=true;status('로컬 초안 보관 실패 · 저장 공간을 확인하세요',true);}}
function removeDraft(){try{localStorage.removeItem(draftKey());}catch{/* server saved; local cleanup can be retried */}}
function dirty(){if(!S.note)return;if(isEmptyNote()&&!S.saving){S.dirty=false;clearTimeout(S.timer);removeDraft();status(S.note.version?'빈 메모는 저장하지 않습니다 · 기존 내용 유지':'빈 메모는 저장하지 않습니다');return;}S.dirty=true;stash();if(!S.conflict&&!S.localError)status('저장 대기…');clearTimeout(S.timer);S.timer=setTimeout(()=>save(),650);}
function noteEquivalent(a,b){return (a.folder_id??null)===(b.folder_id??null)&&['title','body','starred','archived','deleted'].every(k=>a[k]===b[k])&&JSON.stringify(a.tags)===JSON.stringify(b.tags);}
// Only the open note is checked; unchanged versions never download the body.
function remoteStatus(text=''){const el=$('#remote-status');el.textContent=text;el.hidden=!text;}
function showConflict(server){
 clearTimeout(S.timer);S.conflict=true;S.server=server;stash();$('#conflict').hidden=false;
 $('#server-content').textContent=(server.title?server.title+'\n\n':'')+server.body;
 status(S.localError?'수정 충돌 · 로컬 보관 실패':'수정 충돌 · 로컬 초안 보관됨',true);
}
async function refreshOpenNote(){
 if(document.hidden||$('#app').hidden||!S.note?.version||S.saving||S.remoteChecking||S.attachmentBusy||S.imageResizing||S.tableInteracting||S.composing||document.querySelector('dialog[open]'))return;
 const id=S.note.id,generation=S.editorGeneration;S.remoteChecking=true;
 try{
  const server=await api('/notes/'+id+'?known_version='+S.note.version);
  if(S.note?.id!==id||S.editorGeneration!==generation||S.saving||S.attachmentBusy||S.imageResizing||S.tableInteracting)return;
  if(server.unchanged||server.version<=S.note.version){if(!S.conflict)remoteStatus();return;}
  if(S.composing)return; // Korean IME text has not yet reached the Markdown source.
  if(S.dirty||S.conflict){showConflict(server);remoteStatus();return;}
  const selection=getSelection();if(selection&&!selection.isCollapsed&&$('#editor-view').contains(selection.anchorNode))return;
  const x=scrollX,y=scrollY,editorScroll=$('#rich-body').scrollTop;
  S.note=server;$('#note-title').value=server.title;$('#body').value=server.body;$('#tags').value=server.tags.join(', ');
  window.memoEditor?.load();if(S.preview)renderPreview();renderMeta();$('#rich-body').scrollTop=editorScroll;window.scrollTo(x,y);
  status('저장됨');remoteStatus('다른 기기에서 저장한 최신 내용으로 갱신했습니다.'+(server.deleted?' 이 메모는 휴지통에 있습니다.':''));
 }catch(e){if(S.note?.id===id&&S.editorGeneration===generation)remoteStatus(e.status===401?'최신 내용 확인 중단 · 다시 로그인해 주세요.':'최신 내용을 확인하지 못했습니다. 연결되면 다시 확인합니다.');}
 finally{S.remoteChecking=false;}
}
setInterval(refreshOpenNote,5000);
window.addEventListener('focus',refreshOpenNote);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshOpenNote();});
window.addEventListener('online',refreshOpenNote);
async function save(){
 clearTimeout(S.timer);if(S.saving)return S.saving;if(!S.note||!S.dirty||S.conflict)return !S.conflict;
 S.saving=(async()=>{while(S.dirty&&!S.conflict){const snapshot=fields();if(isEmptyNote(snapshot)){S.dirty=false;removeDraft();status(S.note.version?'빈 메모는 저장하지 않습니다 · 기존 내용 유지':'빈 메모는 저장하지 않습니다');return true;}stash();status('저장 중…');
 try{const saved=await api(S.note.version?'/notes/'+S.note.id:'/notes',{method:S.note.version?'PATCH':'POST',body:snapshot});
 const live=fields();const changed=!noteEquivalent(live,snapshot);S.note={...saved,folder_id:live.folder_id,starred:live.starred,archived:live.archived,deleted:live.deleted};S.dirty=changed;if(changed){stash();continue;}removeDraft();status('저장됨');renderMeta();loadFolders();return true;
 }catch(e){stash();if(e.status===409){showConflict(e.data.current);}else status(S.localError?'저장 실패 · 로컬 보관도 실패':`저장 실패 · 로컬 초안 보관됨${e.status===401?' · 다시 로그인 필요':''}`,true);return false;}
 }return !S.conflict;})();try{return await S.saving;}finally{S.saving=null;}
}
function highlight(text){const terms=$('#search').value.trim().split(/\s+/).filter(Boolean).sort((a,b)=>b.length-a.length);if(!terms.length)return escapeHTML(text);const rx=new RegExp('('+terms.map(s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','ig');return String(text).split(rx).map((s,i)=>i%2?'<mark>'+escapeHTML(s)+'</mark>':escapeHTML(s)).join('');}
function params(offset=0){const p=new URLSearchParams({q:$('#search').value,state:S.state,sort:$('#sort').value,limit:'40',offset:String(offset)});if(S.folderId)p.set('folder_id',S.folderId);const start=$('#date-from').value,end=$('#date-to').value;if(start)p.set('from',new Date(start+'T00:00:00').toISOString());if(end){const d=new Date(end+'T00:00:00');d.setDate(d.getDate()+1);p.set('to',d.toISOString());}if($('#tag-filter').value.trim())p.set('tag',$('#tag-filter').value.trim());return p;}
function rememberList(){try{sessionStorage.setItem('hanjul:list',JSON.stringify({state:S.state,folderId:S.folderId,q:$('#search').value,sort:$('#sort').value,from:$('#date-from').value,to:$('#date-to').value,tag:$('#tag-filter').value,scroll:S.scroll,loaded:S.loaded}));}catch{}}
async function loadList(append=false){
 const seq=++S.querySeq;if(!append)exitSelection();$('#select-notes').hidden=S.state==='trash';loadFolders();$('#list-error').textContent='';$('#reset-search').hidden=!($('#search').value||$('#date-from').value||$('#date-to').value||$('#tag-filter').value);rememberList();
 try{const data=await api('/notes?'+params(append?S.next:0));if(seq!==S.querySeq)return;S.next=data.next_offset;$('#count').textContent=data.total.toLocaleString()+'개의 메모';if(!append)$('#notes-list').replaceChildren();
 for(const n of data.items){const b=document.createElement('button');b.className='note-row';b.innerHTML=`<div class="note-row-copy"><div class="note-row-title"><span>${highlight(n.display_title)}</span>${n.starred?'<span class="row-star" aria-label="중요">☆</span>':''}</div><p class="snippet">${highlight(n.snippet)}</p><div class="row-meta"><time>${escapeHTML(date(n.updated_at))}</time>${n.tags.map(t=>`<span class="row-tag">#${escapeHTML(t)}</span>`).join('')}${n.archived?'<span>보관됨</span>':''}</div></div>`;if(n.thumbnail_url&&/^\/api\/attachments\/[0-9a-f-]{36}$/.test(n.thumbnail_url)){const thumb=document.createElement('img');thumb.className='note-thumbnail';thumb.src=n.thumbnail_url;thumb.alt='첨부 사진';thumb.loading='lazy';thumb.decoding='async';thumb.draggable=false;thumb.addEventListener('error',()=>thumb.remove(),{once:true});b.append(thumb);}const item=document.createElement('div');item.className='note-item';item.dataset.id=n.id;item.dataset.version=n.version;const check=document.createElement('input');check.type='checkbox';check.className='note-select';check.setAttribute('aria-label',n.display_title+' 선택');check.hidden=!S.selecting;check.checked=S.selected.has(n.id);check.onchange=()=>toggleSelected(n,check.checked);item.append(check,b);bindNoteRow(b,n);$('#notes-list').append(item);}
 if(!data.total){const search=!!($('#search').value||$('#date-from').value||$('#date-to').value||$('#tag-filter').value);$('#notes-list').innerHTML=`<div class="empty"><div class="empty-symbol" aria-hidden="true">≡</div><h2>${search?'찾는 메모가 없어요':S.state==='trash'?'휴지통이 비어 있어요':S.state==='archive'?'보관한 메모가 없어요':S.state==='starred'?'중요 표시한 메모가 없어요':S.folderId?'이 폴더에 메모가 없어요':'첫 생각을 남겨보세요'}</h2><p>${search?'검색 단어를 줄이거나 날짜·태그 필터를 바꿔보세요.':'짧은 한 줄, 링크 하나도 좋아요.<br>제목과 태그는 나중에 정해도 됩니다.'}</p></div>`;}
 S.loaded=$$('.note-row').length;renderSelection();rememberList();$('#load-more').hidden=S.next===null;
 }catch(e){if(seq===S.querySeq)$('#list-error').textContent=e.message;}renderDrafts();
}
function renderDrafts(){const box=$('#draft-banner');box.replaceChildren();let entries=[];try{entries=Object.keys(localStorage).filter(k=>k.startsWith(`hanjul:draft:${S.instance}:`)).map(key=>({key,...JSON.parse(localStorage.getItem(key))}));}catch{toast('로컬 초안 목록을 읽지 못했습니다.');}box.hidden=!entries.length;if(!entries.length)return;const text=document.createElement('strong');text.textContent=`저장되지 않은 로컬 초안 ${entries.length}개`;box.append(text);for(const entry of entries){const row=document.createElement('div'),b=document.createElement('button'),del=document.createElement('button');b.textContent=(entry.note.title||entry.note.body.split('\n').find(s=>s.trim())||'빈 초안').slice(0,48)+' · 복구';b.onclick=()=>recover(entry);del.textContent='삭제';del.onclick=()=>{if(confirm('이 기기의 로컬 초안을 삭제할까요?')){localStorage.removeItem(entry.key);renderDrafts();}};row.append(b,del);box.append(row);}}
function showEditor(n){setSidebar(false);exitSelection();S.editorGeneration=(S.editorGeneration||0)+1;remoteStatus();S.note=n;S.dirty=false;S.conflict=false;S.preview=false;$('#conflict').hidden=true;$('#list-view').hidden=true;$('#editor-view').hidden=false;document.body.classList.add('editing');$('#note-title').value=n.title;$('#body').value=n.body;$('#tags').value=n.tags.join(', ');$('#preview').hidden=true;$('#body').hidden=false;$('#preview-toggle').textContent='읽기';$('#preview-toggle').setAttribute('aria-pressed','false');status(n.version?'저장됨':'입력하면 자동 저장');renderMeta();window.scrollTo(0,0);window.memoEditor?.load();window.memoEditor?.focus();}
async function openNote(id){if(S.attachmentBusy||S.deleting)return;try{S.scroll=window.scrollY;rememberList();const n=await api('/notes/'+id);showEditor(n);}catch(e){toast(e.message);}}
async function newNote(){if(S.navigating||S.attachmentBusy||S.deleting)return;setSidebar(false);S.navigating=true;try{if(S.note){const ok=await save();if(!ok){toast('기존 내용은 로컬 초안에 보관했습니다.');}}if(!S.note)S.scroll=window.scrollY;showEditor({id:crypto.randomUUID(),title:'',body:'',tags:[],folder_id:S.folderId&&S.folderId!=='none'?S.folderId:null,starred:false,archived:false,deleted:false,version:0,attachments:[]});}finally{S.navigating=false;}}
async function recover(entry){if(S.note)await save();showEditor({...entry.note,attachments:[]});S.dirty=true;stash();if(!S.localError)localStorage.removeItem(entry.key);status('로컬 초안 복구됨 · 저장하려면 다시 저장',true);if(S.note.version){try{const server=await api('/notes/'+S.note.id);S.note.attachments=server.attachments;renderMeta();if(server.version!==S.note.version){S.server=server;S.conflict=true;$('#conflict').hidden=false;$('#server-content').textContent=server.body;status('수정 충돌 · 복구 초안 보관됨',true);}}catch(e){toast(e.message);}}}
function renderMeta(){const n=S.note;renderFolderOptions(n.folder_id||'');$('#star').textContent=n.starred?'★':'☆';$('#star').setAttribute('aria-pressed',String(n.starred));$('#archive').textContent=n.archived?'보관 해제':'보관';$('#trash').textContent=n.deleted?'휴지통에서 복구':'휴지통으로';$('#editor-dates').textContent=n.created_at?`작성 ${date(n.created_at)} · 수정 ${date(n.updated_at)} · 버전 ${n.version}`:'';$('#attachment-list').replaceChildren();const inlineImages=new Set([...$('#body').value.matchAll(/!\[[^\]]*\]\(\/api\/attachments\/([0-9a-f-]{36})(?: "width=\d{1,3}%")?\)/g)].map(m=>m[1]));for(const a of n.attachments||[]){if(inlineImages.has(a.id)&&['image/png','image/jpeg','image/gif','image/webp'].includes(a.mime))continue;const link=document.createElement('a');link.href='/api/attachments/'+a.id;link.target='_blank';link.rel='noopener';link.textContent=`↳ ${a.name} · ${Math.ceil(a.size/1024)}KB`;$('#attachment-list').append(link);}$('#attachment-list').hidden=!$('#attachment-list').children.length;}
async function restoreList(){const count=S.loaded,scroll=S.scroll;S.restoring=true;try{await loadList();while(S.next!==null&&S.loaded<count){const before=S.loaded;await loadList(true);if(S.loaded===before)break;}S.scroll=scroll;window.scrollTo(0,scroll);}finally{S.restoring=false;}}
async function back(){if(S.navigating||S.attachmentBusy||S.deleting)return;S.navigating=true;try{await save();window.memoTables?.clear();S.note=null;S.dirty=false;S.conflict=false;$('#editor-view').hidden=true;$('#list-view').hidden=false;document.body.classList.remove('editing');await restoreList();}finally{S.navigating=false;}}
function insert(value){if(window.memoEditor)return window.memoEditor.insert(value);const area=$('#body');if(S.preview)togglePreview();const start=area.selectionStart;area.setRangeText(value,start,area.selectionEnd,'end');area.focus();dirty();}
function mediaInline(text){const frag=document.createDocumentFragment();const rx=/(!?)\[([^\]]*)\]\(([^\s)]+)(?: "width=(\d{1,3})%")?\)|(https?:\/\/[^\s<>]+)/g;let pos=0,m;while((m=rx.exec(text))){frag.append(document.createTextNode(text.slice(pos,m.index)));const url=m[3]||m[5],label=m[2]||m[5],safe=/^https?:\/\//i.test(url)||/^\/api\/attachments\/[0-9a-f-]{36}$/.test(url);if(m[1]&&/^\/api\/attachments\/[0-9a-f-]{36}$/.test(url)){const img=document.createElement('img');img.src=url;img.alt=label;img.loading='lazy';const frame=document.createElement('span');frame.dataset.markdown=m[0];frame.contentEditable='false';frame.className='inline-image';const a=document.createElement('a');a.href=url;a.target='_blank';a.rel='noopener noreferrer';a.draggable=img.draggable=false;const width=Number(m[4]);if(width>=20&&width<=100){frame.dataset.width=width;frame.style.width=width+'%';img.style.width='100%';img.style.maxHeight='none';}a.title=S.preview?'이미지 원본 보기':'사진 선택 · 모서리를 드래그해 크기 조절';if(!S.preview)a.setAttribute('role','button');a.append(img);frame.append(a);frag.append(frame);}else if(safe){const a=document.createElement('a');a.href=url;a.textContent=label;a.target='_blank';a.rel='noopener noreferrer';a.dataset.markdown=m[0];a.contentEditable='false';frag.append(a);}else frag.append(document.createTextNode(m[0]));pos=rx.lastIndex;}frag.append(document.createTextNode(text.slice(pos)));return frag;}
function renderPreview(){const box=$('#preview');box.replaceChildren();$('#body').value.split('\n').forEach((line,index)=>{const check=line.match(/^\s*[-*] \[([ xX])\] (.*)$/);if(check){const label=document.createElement('label');label.className='check-line';const input=document.createElement('input');input.type='checkbox';input.checked=check[1]!==' ';const span=document.createElement('span');span.className=input.checked?'done':'';span.append(inline(check[2]));input.onchange=()=>{const lines=$('#body').value.split('\n');lines[index]=lines[index].replace(/\[([ xX])\]/,input.checked?'[x]':'[ ]');$('#body').value=lines.join('\n');dirty();renderPreview();};label.append(input,span);box.append(label);}else{const p=document.createElement('p');p.append(inline(line.replace(/^[-*] /,'• ')));if(!line)p.append(document.createElement('br'));p.addEventListener('change',e=>{const marker=e.target.closest('.check-marker');if(!marker)return;marker.dataset.markdown=e.target.checked?'- [x] ':'- [ ] ';const lines=$('#body').value.split('\n');lines[index]=memoRead(p);$('#body').value=lines.join('\n');dirty();renderPreview();});box.append(p);}});}
function togglePreview(){window.memoTables?.clear();S.preview=!S.preview;$('#body').hidden=true;$('#rich-body').hidden=S.preview;$('#preview').hidden=!S.preview;$('#preview-toggle').textContent=S.preview?'편집':'읽기';$('#preview-toggle').setAttribute('aria-pressed',String(S.preview));if(S.preview)renderPreview();else {window.memoEditor.load();window.memoEditor.focus();}}
async function settings(){if(S.attachmentBusy)return;setSidebar(false);if(S.note)await save();$('#settings').showModal();$('#settings-status').textContent='';try{await loadTokens();await window.loadSecurity();}catch(e){$('#settings-status').textContent=e.message;}}
async function loadTokens(){const d=await api('/tokens');$('#token-list').replaceChildren();for(const t of d.items){const row=document.createElement('div');row.className='token-row';const label=document.createElement('span');label.textContent=`${t.name} · ${t.scope==='read'?'읽기 전용':'읽기 + 쓰기'}`;const b=document.createElement('button');b.textContent='폐기';b.onclick=async()=>{try{await api('/tokens/'+t.id,{method:'DELETE'});await loadTokens();}catch(e){$('#settings-status').textContent=e.message;}};row.append(label,b);$('#token-list').append(row);}}
function renderFolderOptions(value=$('#note-folder').value){
 const select=$('#note-folder');select.replaceChildren(new Option('폴더 없음',''));
 for(const f of S.folders)select.add(new Option(f.name,f.id));
 if(value&&!S.folders.some(f=>f.id===value))select.add(new Option('폴더 불러오는 중…',value));
 select.value=value;
}
function renderFolderNav(){
 const list=$('#folder-list');list.replaceChildren();
 const entries=[{id:'none',name:'폴더 없음',count:S.unfiled||0},...S.folders];
 for(const f of entries){
  const row=document.createElement('div');row.className='folder-row';
  const button=document.createElement('button');button.className='nav folder-nav';button.dataset.folder=f.id;
  button.classList.toggle('active',S.folderId===f.id);button.setAttribute('aria-pressed',String(S.folderId===f.id));
  const name=document.createElement('span');name.className='folder-name';name.textContent=f.name;
  const count=document.createElement('span');count.className='folder-count';count.textContent=f.count.toLocaleString();count.setAttribute('aria-label',f.count+'개의 메모');
  button.append(name,count);button.onclick=()=>selectFolder(f.id);row.append(button);
  if(f.id!=='none'){const edit=document.createElement('button');edit.className='folder-rename quiet';edit.textContent='✎';edit.setAttribute('aria-label',f.name+' 폴더 이름 변경');edit.onclick=()=>folderDialog(f);row.append(edit);}
  list.append(row);
 }
 $$('[data-state]').forEach(b=>b.classList.toggle('active',!S.folderId&&b.dataset.state===S.state));
 if(S.folderId)$('#list-title').textContent=entries.find(f=>f.id===S.folderId)?.name||'폴더';
}
async function loadFolders(){
 const seq=S.folderSeq=(S.folderSeq||0)+1;
 try{const data=await api('/folders');if(seq!==S.folderSeq)return;S.folders=data.items;S.unfiled=data.unfiled;renderFolderNav();renderFolderOptions();$('#folder-error').hidden=true;}
 catch(e){if(seq===S.folderSeq){$('#folder-error').textContent='폴더를 불러오지 못했습니다. '+e.message;$('#folder-error').hidden=false;}}
}
async function selectFolder(id){
 setSidebar(false);if(S.note)await back();S.folderId=id;S.state='active';S.scroll=0;S.loaded=40;renderFolderNav();await loadList();
}
function folderDialog(folder=null,assign=false){
 S.editingFolder=folder;S.assignNewFolder=assign;$('#folder-dialog-title').textContent=folder?'폴더 이름 변경':'새 폴더';$('#folder-submit').textContent=folder?'저장':'만들기';$('#folder-name').value=folder?.name||'';$('#folder-form-error').textContent='';$('#folder-dialog').showModal();$('#folder-name').focus();
}
$('#folder-add').onclick=()=>folderDialog();$('#editor-folder-add').onclick=()=>folderDialog(null,true);
$('#folder-cancel').onclick=()=>$('#folder-dialog').close();
$('#note-folder').onchange=dirty;
$('#folder-form').onsubmit=async e=>{
 e.preventDefault();const name=$('#folder-name').value.trim();if(!name){$('#folder-form-error').textContent='폴더 이름을 입력해 주세요.';return;}
 const button=$('#folder-submit');button.disabled=true;
 try{const f=S.editingFolder;const saved=await api(f?'/folders/'+f.id:'/folders',{method:f?'PATCH':'POST',body:f?{name,version:f.version}:{name}});
 await loadFolders();$('#folder-dialog').close();
 if(!f&&S.assignNewFolder&&S.note){renderFolderOptions(saved.id);dirty();}else if(!f&&!S.note)await selectFolder(saved.id);
 toast(f?'폴더 이름을 변경했습니다.':'폴더를 만들었습니다.');
 }catch(e){$('#folder-form-error').textContent=e.message;if(e.status===409&&e.data.current){S.editingFolder=e.data.current;await loadFolders();}}
 finally{button.disabled=false;}
};
window.addEventListener('focus',()=>{if(!$('#app').hidden)loadFolders();});
const mobileMenu=matchMedia('(max-width:600px)');
function setSidebar(open){
 open=!!open&&mobileMenu.matches;
 const wasOpen=document.body.classList.contains('menu-open');
 document.body.classList.toggle('menu-open',open);$('#menu-toggle').setAttribute('aria-expanded',String(open));
 $('#sidebar-backdrop').hidden=!open;$('#sidebar').inert=mobileMenu.matches&&!open;$('.workspace').inert=open;
 if(open)$('#sidebar-close').focus();else if(wasOpen)$('#menu-toggle').focus();
}
$('#menu-toggle').onclick=()=>setSidebar(true);
$('#sidebar-close').onclick=$('#sidebar-backdrop').onclick=()=>setSidebar(false);
mobileMenu.addEventListener('change',()=>setSidebar(false));setSidebar(false);
document.addEventListener('keydown',e=>{
 if(document.querySelector('dialog[open]'))return;
 if(document.body.classList.contains('menu-open')){
  if(e.key==='Escape'){e.preventDefault();setSidebar(false);}
  if(e.key==='Tab'){const els=[...$('#sidebar').querySelectorAll('a,button')].filter(el=>!el.disabled&&el.getClientRects().length);const first=els[0],last=els.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}
 }else if(e.key==='Escape'&&S.selecting)exitSelection();
});
function renderSelection(){
 $('#selection-bar').hidden=!S.selecting;$('#select-notes').hidden=S.selecting||S.state==='trash';$('#selection-count').textContent=S.selected.size+'개 선택';$('#delete-selected').disabled=!S.selected.size||S.deleting;
 for(const item of $$('.note-item')){const checked=S.selected.has(item.dataset.id),check=item.querySelector('.note-select');check.hidden=!S.selecting;check.checked=checked;item.classList.toggle('selected',checked);}
 const all=$$('.note-item').length>0&&$$('.note-item').every(item=>S.selected.has(item.dataset.id));$('#select-all').textContent=all?'전체 선택 해제':'현재 목록 전체 선택';
}
function exitSelection(){S.pressCancel?.();S.selecting=false;S.selected.clear();renderSelection();}
function toggleSelected(n,checked=!S.selected.has(n.id)){if(S.deleting)return;S.selecting=true;if(checked)S.selected.set(n.id,n.version);else S.selected.delete(n.id);renderSelection();}
function bindNoteRow(button,n){
 let timer=null,start=null,suppressClick=false;
 const cancel=()=>{clearTimeout(timer);timer=null;start=null;};
 button.onpointerdown=e=>{if(e.button!==0||S.state==='trash'||S.deleting)return;S.pressCancel?.();S.pressCancel=cancel;suppressClick=false;start={x:e.clientX,y:e.clientY};timer=setTimeout(()=>{suppressClick=true;toggleSelected(n,true);timer=null;},500);};
 button.onpointermove=e=>{if(start&&Math.hypot(e.clientX-start.x,e.clientY-start.y)>10)cancel();};
 button.onpointerup=button.onpointercancel=button.onpointerleave=cancel;
 button.oncontextmenu=e=>{if(S.state!=='trash')e.preventDefault();};
 button.onclick=e=>{cancel();if(S.deleting||e.detail&&suppressClick){suppressClick=false;e.preventDefault();return;}if(S.selecting)toggleSelected(n);else openNote(n.id);};
}
window.addEventListener('scroll',()=>S.pressCancel?.(),true);
$('#select-notes').onclick=()=>{S.selecting=true;renderSelection();};
$('#cancel-selection').onclick=exitSelection;
$('#select-all').onclick=()=>{const items=$$('.note-item'),all=items.every(item=>S.selected.has(item.dataset.id));for(const item of items){if(all)S.selected.delete(item.dataset.id);else S.selected.set(item.dataset.id,Number(item.dataset.version));}renderSelection();};
$('#delete-selected').onclick=async()=>{
 if(S.deleting||!S.selected.size)return;
 const items=[...S.selected].map(([id,version])=>({id,version}));
 if(!confirm(`선택한 메모 ${items.length}개를 휴지통으로 이동할까요?`))return;
 S.deleting=true;const locks=$$('#app button,#app input,#app select').map(el=>[el,el.disabled]);locks.forEach(([el])=>el.disabled=true);
 try{const result=await api('/notes/trash',{method:'POST',body:{items}});toast(`${result.deleted}개의 메모를 휴지통으로 이동했습니다.`);await loadList();}
 catch(e){toast(e.message);if(e.status===409)await loadList();}
 finally{S.deleting=false;locks.forEach(([el,disabled])=>el.disabled=disabled);renderSelection();}
};
async function boot(){try{const info=await api('/session');S.csrf=info.csrf;S.instance=info.instance;$('#app').hidden=false;$('#login-view').hidden=true;await restoreList();}catch{$('#login-view').hidden=false;$('#app').hidden=true;}}
$('#login-form').onsubmit=async e=>{e.preventDefault();try{const info=await api('/login',{method:'POST',body:{password:$('#password').value,remember:$('#remember-login').checked}});S.csrf=info.csrf;$('#password').value='';await boot();}catch(e){$('#login-error').textContent=e.message;}};
$('#new-note').onclick=newNote;$('#mobile-new').onclick=newNote;$('#back').onclick=back;$('#retry').onclick=save;$('#save-note').onclick=save;
for(const el of [$('#note-title'),$('#body'),$('#tags')])el.addEventListener('input',dirty);
$('#search').oninput=()=>{clearTimeout(S.searchTimer);S.searchTimer=setTimeout(async()=>{if(S.note)await back();await loadList();},250);};
$('#sort').onchange=()=>loadList();$('#filter-toggle').onclick=()=>$('#filter-panel').hidden=!$('#filter-panel').hidden;$('#apply-filter').onclick=()=>loadList();$('#load-more').onclick=()=>loadList(true);
$('#reset-search').onclick=()=>{for(const id of ['search','date-from','date-to','tag-filter'])$('#'+id).value='';loadList();};
$$('[data-state]').forEach(b=>b.onclick=async()=>{setSidebar(false);if(S.note)await back();S.state=b.dataset.state;S.folderId=null;renderFolderNav();$$('[data-state]').forEach(x=>x.classList.toggle('active',x===b));$('#list-title').textContent=b.textContent.replace('☆ ','');await loadList();});
async function changeNoteState(key,returnToList=false){
 if(S.attachmentBusy||!S.note)return;
 if(S.note.version&&isEmptyNote()){
  const id=S.note.id,generation=S.editorGeneration;
  // A cleared editor keeps its last saved text, but state actions still work.
  if(!await save()||S.note?.id!==id)return;
  try{const saved=await api('/notes/'+id,{method:'PATCH',body:{version:S.note.version,[key]:!S.note[key]}});if(S.note?.id!==id||S.editorGeneration!==generation)return;showEditor(saved);if(returnToList)await back();}
  catch(e){if(S.note?.id!==id||S.editorGeneration!==generation)return;if(e.status===409)showConflict(e.data.current);else toast(e.message);}
  return;
 }
 S.note[key]=!S.note[key];renderMeta();dirty();if(returnToList&&await save())await back();
}
$('#star').onclick=()=>changeNoteState('starred');
$('#archive').onclick=()=>changeNoteState('archived',true);
$('#trash').onclick=()=>changeNoteState('deleted',true);
$$('[data-insert]').forEach(b=>b.onclick=()=>b.dataset.insert==='check'?window.memoEditor.checklist():window.memoEditor.insertLine('- '));
$('#preview-toggle').onclick=togglePreview;$('#attach-button').onclick=()=>$('#file').click();
async function uploadAttachments(files,{atCaret=false}={}){
 if(!S.note||S.attachmentBusy)return;
 if(files.some(file=>file.size>20*1024*1024))return toast('파일은 20MB까지 첨부할 수 있습니다.');
 const noteId=S.note.id,locks=$$('#app input,#app textarea,#app select,#app button').map(el=>[el,el.disabled]);
 let offset=atCaret?window.memoEditor.offset():null;
 S.attachmentBusy=true;$('#rich-body').contentEditable='false';locks.forEach(([el])=>el.disabled=true);
 try{
  if(S.note.version||!isEmptyNote()){if(!await save()){toast('메모 저장 문제를 먼저 해결해 주세요.');return;}}
  for(const file of files){
   const form=new FormData();form.set('file',file);form.set('version',S.note.version);
   if(!S.note.version)form.set('note',JSON.stringify(fields()));
   if(offset!==null)form.set('offset',offset);
   const oldLength=[...$('#body').value].length;status('첨부 저장 중…');
   const saved=await api('/notes/'+noteId+'/attachments',{method:'POST',body:form});
   if(offset!==null)offset += [...saved.body].length-oldLength;
   showEditor(saved);removeDraft();status('저장됨');
  }
  if(offset!==null)window.memoEditor.load([...$('#body').value].slice(0,offset).join('').length);
  await loadFolders();
 }catch(e){if(e.status===409&&e.data.current)showConflict(e.data.current);else {status('첨부 저장 실패 · 다시 붙여넣거나 첨부해 주세요',true);$('#retry').hidden=true;}toast(e.message);}
 finally{S.attachmentBusy=false;locks.forEach(([el,disabled])=>el.disabled=disabled);$('#rich-body').contentEditable='true';window.memoEditor.focus();}
}
$('#file').onchange=()=>{const files=[...$('#file').files];$('#file').value='';if(files.length)uploadAttachments(files);};
$('#conflict-copy').onclick=async()=>{const oldKey=draftKey(),local=fields();try{const saved=await api('/notes/'+S.note.id+'/copy',{method:'POST',body:local});showEditor(saved);localStorage.removeItem(oldKey);status('새 메모로 저장됨');}catch(e){toast(e.message);}};
$('#conflict-server').onclick=()=>{if(confirm('내 로컬 초안을 삭제하고 서버 내용을 열까요?')){removeDraft();showEditor(S.server);}};
$('#settings-open').onclick=settings;$('#settings-close').onclick=()=>{$('#settings').close();$('#token-result').textContent='';};
$('#settings').addEventListener('close',()=>{$('#token-result').textContent='';});
$('#import-file').onchange=async()=>{const file=$('#import-file').files[0];if(!file)return;$('#import-file').value='';$('#import-confirm').hidden=true;$('#import-preview').textContent='파일을 검사하고 있습니다…';try{const f=new FormData();f.set('file',file);const d=await api('/import/preview',{method:'POST',body:f});S.importId=d.preview_id;$('#import-preview').textContent=`총 ${d.total}개 · 새 메모 ${d.create}개 · 기존 ID ${d.skip}개 건너뛰기 · 첨부 ${d.attachments}개. ${d.policy}`;$('#import-confirm').hidden=false;}catch(e){$('#import-preview').textContent=e.message;}};
$('#import-confirm').onclick=async()=>{const b=$('#import-confirm');b.disabled=true;try{const d=await api('/import/commit',{method:'POST',body:{preview_id:S.importId}});$('#import-preview').textContent=`가져오기 완료: ${d.created}개 추가, ${d.skipped}개 건너뜀`;b.hidden=true;await loadList();}catch(e){$('#import-preview').textContent=e.message;}finally{b.disabled=false;}};
$('#token-form').onsubmit=async e=>{e.preventDefault();try{const d=await api('/tokens',{method:'POST',body:{name:$('#token-name').value,scope:$('#token-scope').value}});$('#token-result').textContent=d.token;$('#token-name').value='';await loadTokens();}catch(e){$('#settings-status').textContent=e.message;}};
$('#password-form').onsubmit=async e=>{e.preventDefault();try{await api('/password',{method:'POST',body:{password:$('#new-password').value}});location.reload();}catch(e){$('#settings-status').textContent=e.message;}};
$('#logout').onclick=async()=>{if(S.note)await save();try{await api('/logout',{method:'POST'});location.reload();}catch(e){$('#settings-status').textContent=e.message;}};
window.addEventListener('beforeunload',e=>{if(S.dirty){stash();e.preventDefault();e.returnValue='';}});document.addEventListener('visibilitychange',()=>{if(document.hidden&&S.dirty){stash();save();}});window.addEventListener('online',()=>{if(S.dirty&&!S.conflict)save();});window.addEventListener('storage',renderDrafts);window.addEventListener('scroll',()=>{if(!S.note&&!S.navigating&&!S.restoring){S.scroll=window.scrollY;clearTimeout(S.scrollTimer);S.scrollTimer=setTimeout(rememberList,150);}});
document.addEventListener('keydown',e=>{if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!$('#settings').open){if(S.note)back().then(()=>$('#search').focus());else $('#search').focus();}}if((e.metaKey||e.ctrlKey)&&e.key==='Enter'&&!$('#app').hidden&&!document.querySelector('dialog[open]')){e.preventDefault();newNote();}if((e.metaKey||e.ctrlKey)&&e.key==='s'&&S.note){e.preventDefault();save();}});
try{const p=JSON.parse(sessionStorage.getItem('hanjul:list'));if(p){S.state=p.state||'active';S.folderId=p.folderId||null;for(const [id,key] of [['search','q'],['sort','sort'],['date-from','from'],['date-to','to'],['tag-filter','tag']])$('#'+id).value=p[key]||'';S.scroll=p.scroll||0;S.loaded=p.loaded||40;$$('[data-state]').forEach(b=>{b.classList.toggle('active',b.dataset.state===S.state);if(b.dataset.state===S.state)$('#list-title').textContent=b.textContent.replace('☆ ','');});}}catch{}
if(document.modelContext?.registerTool){try{document.modelContext.registerTool({name:'search_notes',title:'메모 검색',description:'입력한 단어를 모두 포함하는 메모를 검색하고 목록을 표시합니다.',inputSchema:{type:'object',properties:{query:{type:'string',maxLength:300}},required:['query'],additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:true},execute:async input=>{if(!input||typeof input.query!=='string'||input.query.length>300)throw new Error('검색어 형식이 올바르지 않습니다.');if(S.note)await back();$('#search').value=input.query;await loadList();return api('/notes?'+params());}});}catch{}}
boot();
