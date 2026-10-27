'use strict';
// The saved body remains Markdown, with a small, explicitly allowed HTML subset.
// Never pass note contents to innerHTML: unknown tags stay visible as plain text.
const memoFontSizes=[12,14,17,20,24,32,40];
function inline(text){
 const fragment=document.createDocumentFragment(),stack=[fragment];
 const tokens=/<\/?(?:strong|s|table|tbody|tr|td|th)>|<(?:td|th)(?: rowspan="[1-9]\d{0,2}")?(?: colspan="[1-9]\d?")?>|<table(?: data-width="(?:[2-9]\d|100)")?(?: data-height="[1-9]\d{1,4}")?>|<span data-size="(?:12|14|17|20|24|32|40)">|<\/span>|<br>/g;
 let pos=0,match;
 const append=value=>{if(value)stack.at(-1).append(mediaInline(value));};
 while((match=tokens.exec(text))){
  append(text.slice(pos,match.index));const token=match[0];
  if(token.startsWith('</')){
   const tag=token.slice(2,-1);
   if(stack.length>1&&stack.at(-1).dataset.memoTag===tag)stack.pop();else append(token);
  }else{
   const tag=token.match(/^<(\w+)/)[1];
   const parent=stack.at(-1).dataset?.memoTag;
   const valid=tag==='table'?!stack.some(node=>node.dataset?.memoTag==='table'):
    tag==='tbody'?parent==='table':tag==='tr'?['table','tbody'].includes(parent):
    ['td','th'].includes(tag)?parent==='tr':!['table','tbody','tr'].includes(parent);
   if(!valid){append(token);pos=tokens.lastIndex;continue;}
   const node=document.createElement(tag==='span'?'font':tag);
   if(tag==='span')node.setAttribute('size',memoFontSizes.indexOf(Number(token.match(/"(\d+)"/)[1]))+1);
   if(['td','th'].includes(tag))for(const attr of ['rowspan','colspan']){const value=token.match(new RegExp(attr+'="(\\d+)"'));if(value)node.setAttribute(attr,value[1]);}
   if(tag==='table'){for(const [attr,unit] of [['width','%'],['height','px']]){const value=token.match(new RegExp('data-'+attr+'="(\\d+)"'));if(value){node.dataset[attr]=value[1];node.style[attr]=value[1]+unit;}}}
   node.dataset.memoTag=tag;stack.at(-1).append(node);if(tag!=='br')stack.push(node);
  }
  pos=tokens.lastIndex;
 }
 append(text.slice(pos));
 for(const cell of fragment.querySelectorAll('td,th')){
  const contents=memoRead(cell).replace(/^<t[dh][^>]*>/,'').replace(/<\/t[dh]>$/,'');
  if(/(?:^|<br>)\s*[-*] \[[ xX]\] /.test(contents))cell.replaceChildren(...contents.split('<br>').map(memoLine));
 }
 return fragment;
}
function memoRead(node){
 if(node.nodeType===3)return node.nodeValue;
 if(node.nodeType!==1&&node.nodeType!==11)return '';
 if(node.dataset?.markdown!==undefined)return node.dataset.markdown;
 if(node.nodeName==='BR')return '\n';
 const children=[...node.childNodes];
 if(children.length===1&&children[0].nodeName==='BR'&&!['TD','TH'].includes(node.nodeName))return '';
 const block=child=>child.nodeType===1&&['DIV','P','LI','TABLE'].includes(child.tagName);
 let text=children.map((child,i)=>(i&&(block(child)||block(children[i-1]))?'\n':'')+memoRead(child)).join('');
 const tag=node.nodeName;
 if(['TABLE','TBODY','TR','TD','TH'].includes(tag)){
  if(['TD','TH'].includes(tag))text=text.replace(/\n/g,'<br>');
  const dimensions=tag==='TABLE'?['width','height'].map(attr=>node.dataset[attr]?` data-${attr}="${node.dataset[attr]}"`:'').join(''):'';
  const spans=['TD','TH'].includes(tag)?['rowspan','colspan'].map(attr=>Number(node.getAttribute(attr))>1?` ${attr}="${Number(node.getAttribute(attr))}"`:'').join(''):'';
  return `<${tag.toLowerCase()}${dimensions}${spans}>${text}</${tag.toLowerCase()}>`;
 }
 if(!text)return '';
 const wrap=(open,close)=>{text=open+text.replace(/\n/g,'<br>')+close;};
 if(['B','STRONG'].includes(tag)||Number(node.style?.fontWeight)>=600||node.style?.fontWeight==='bold')wrap('<strong>','</strong>');
 if(['S','STRIKE','DEL'].includes(tag)||node.style?.textDecorationLine.includes('line-through'))wrap('<s>','</s>');
 const size=tag==='FONT'?memoFontSizes[Number(node.getAttribute('size'))-1]:parseInt(node.style?.fontSize,10);
 if(memoFontSizes.includes(size))wrap(`<span data-size="${size}">`,'</span>');
 return text;
}
function memoCheckRow(text='',checked=false){
 const row=document.createElement('div');row.className='check-row';
 const marker=document.createElement('span');marker.className='check-marker';marker.contentEditable='false';marker.dataset.markdown=checked?'- [x] ':'- [ ] ';
 const input=document.createElement('input');input.type='checkbox';input.setAttribute('aria-label','할 일 완료');input.checked=checked;if(checked)input.setAttribute('checked','');marker.append(input);
 const content=document.createElement('span');content.className='check-text';content.append(inline(text));if(!content.childNodes.length)content.append(document.createElement('br'));
 row.append(marker,content);return row;
}
function memoLine(line){
 const check=line.match(/^\s*[-*] \[([ xX])\] ?(.*)$/);
 if(check)return memoCheckRow(check[2],check[1]!==' ');
 const row=document.createElement('div');row.append(inline(line));if(!row.childNodes.length)row.append(document.createElement('br'));return row;
}

// Parse clipboard HTML in an inert template, then copy only safe cell content.
// Excel also supplies TSV; its quoted fields may contain tabs and line breaks.
function memoClipboardTable(html,text){
 const maxRows=200,maxCols=50;
 const tooLarge=()=>{throw Error('표는 한 번에 200행, 50열까지 붙여넣을 수 있습니다.');};
 function safeContent(node){
  if(node.nodeType===3)return document.createTextNode(node.nodeValue);
  const result=document.createDocumentFragment();if(node.nodeType!==1)return result;
  if(['SCRIPT','STYLE','IFRAME','OBJECT','IMG','SVG','LINK','META'].includes(node.tagName))return result;
  if(node.tagName==='BR')return document.createElement('br');
  for(const child of node.childNodes)result.append(safeContent(child));
  let content=result;
  const wrap=tag=>{const element=document.createElement(tag);element.append(content);content=element;return element;};
  if(['B','STRONG','TH'].includes(node.tagName)||Number(node.style.fontWeight)>=600||node.style.fontWeight==='bold')wrap('strong');
  if(['S','STRIKE','DEL'].includes(node.tagName)||node.style.textDecorationLine.includes('line-through'))wrap('s');
  const size=parseFloat(node.style.fontSize)*(node.style.fontSize.endsWith('pt')?4/3:1);
  if(size>0){const closest=memoFontSizes.reduce((a,b)=>Math.abs(b-size)<Math.abs(a-size)?b:a);wrap('font').setAttribute('size',memoFontSizes.indexOf(closest)+1);}
  if(['DIV','P','LI'].includes(node.tagName)&&node.nextSibling)content.append(document.createElement('br'));
  return content;
 }
 if(html){
  if(html.length>4000000)tooLarge();
  const template=document.createElement('template');template.innerHTML=html;
  const original=template.content.querySelector('table');
  if(original){
   const rows=[...original.rows];if(!rows.length)return null;if(rows.length>maxRows)tooLarge();
   const table=document.createElement('table'),occupied=[];
   rows.forEach((row,r)=>{
    const target=table.insertRow();let col=0;
    for(const cell of row.cells){
     while(occupied[r]?.[col])col++;
     const rs=cell.rowSpan===0?rows.length-r:cell.rowSpan,cs=cell.colSpan;
     if(r+rs>maxRows||col+cs>maxCols)tooLarge();
     for(let y=r;y<r+rs;y++){occupied[y]??=[];for(let x=col;x<col+cs;x++)occupied[y][x]=true;}
     const dest=document.createElement(cell.tagName.toLowerCase());dest.append(safeContent(cell));if(!dest.childNodes.length)dest.append(document.createElement('br'));
     if(rs>1)dest.rowSpan=rs;if(cs>1)dest.colSpan=cs;target.append(dest);col+=cs;
    }
   });return table;
  }
 }
 if(!text.includes('\t'))return null;
 const rows=[[]];let cell='',quoted=false;
 for(let i=0;i<text.length;i++){
  const char=text[i];
  if(char==='"'&&(quoted||cell==='')){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}
  else if(!quoted&&(char==='\t'||char==='\n'||char==='\r')){
   rows.at(-1).push(cell);cell='';if(rows.at(-1).length>maxCols)tooLarge();
   if(char!=='\t'){if(char==='\r'&&text[i+1]==='\n')i++;rows.push([]);if(rows.length>maxRows+1)tooLarge();}
  }else cell+=char;
 }
 rows.at(-1).push(cell);if(rows.at(-1).length===1&&cell===''&&/[\r\n]$/.test(text))rows.pop();
 const cols=Math.max(...rows.map(row=>row.length));if(cols<2)return null;if(rows.length>maxRows||cols>maxCols)tooLarge();
 const table=document.createElement('table');
 for(const row of rows){const tr=table.insertRow();for(let col=0;col<cols;col++){const td=tr.insertCell(),value=row[col]||'';value.split(/\r?\n/).forEach((line,i)=>{if(i)td.append(document.createElement('br'));td.append(document.createTextNode(line));});if(!value)td.append(document.createElement('br'));}}
 return table;
}
