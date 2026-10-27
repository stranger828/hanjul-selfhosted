"""Regression coverage using isolated databases and browser profiles."""
import io
import json
import sqlite3
import uuid
import base64
import struct
import zlib
from playwright.sync_api import expect
from test_api import env, make, PNG
from test_browser import browser_env


def test_empty_notes_and_atomic_first_attachment(env):
    app,c,h,tmp=env
    for body in ['', ' \n\t', '\u200b\ufeff\u00a0', '- ', '- [ ] ', '* [x]\n- ']:
        assert c.post('/api/notes',json={'title':' ', 'body':body,'tags':['태그'],'starred':True},headers=h).status_code==400
    assert c.get('/api/notes').json['total']==0
    note=make(c,h)
    assert c.patch('/api/notes/'+note['id'],json={'version':1,'title':'','body':' '},headers=h).status_code==400
    assert c.get('/api/notes/'+note['id']).json['body']==note['body']
    assert c.post('/api/notes/'+note['id']+'/copy',json={'body':''},headers=h).status_code==400
    assert c.post('/api/notes',json={'title':'제목만'},headers=h).status_code==201
    nid=str(uuid.uuid4());url='/api/notes/'+nid+'/attachments'
    bad=c.post(url,data={'version':'0','note':'{}','offset':'1','file':(io.BytesIO(PNG),'screenshot.png')},headers=h)
    assert bad.status_code==400 and c.get('/api/notes/'+nid).status_code==404
    # Both note and attachment roll back if storing the attachment fails.
    with sqlite3.connect(app.config['DB_PATH']) as db:
        db.execute("CREATE TRIGGER fail_attachment BEFORE INSERT ON attachments BEGIN SELECT RAISE(ABORT,'test failure'); END")
    assert c.post(url,data={'version':'0','note':'{}','file':(io.BytesIO(PNG),'screenshot.png')},headers=h).status_code==503
    assert c.get('/api/notes/'+nid).status_code==404
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('DROP TRIGGER fail_attachment')
    r=c.post(url,data={'version':'0','note':'{}','file':(io.BytesIO(PNG),'screenshot.png')},headers=h)
    assert r.status_code==201 and r.json['version']==1 and len(r.json['attachments'])==1
    # Retrying a lost response cannot create another empty note or attachment.
    assert c.post(url,data={'version':'0','note':'{}','file':(io.BytesIO(PNG),'screenshot.png')},headers=h).status_code==409
    assert len(c.get('/api/notes/'+nid).json['attachments'])==1


def test_batch_trash_atomic_conflict_and_permissions(env):
    app,c,h,tmp=env
    a,b=make(c,h,body='첫 메모'),make(c,h,body='둘째 메모')
    items=[{'id':n['id'],'version':n['version']} for n in [a,b]]
    assert c.post('/api/notes/trash',json={'items':items}).status_code==403
    token=c.post('/api/tokens',json={'name':'읽기','scope':'read'},headers=h).json['token']
    assert c.post('/api/notes/trash',json={'items':items},headers={'Authorization':'Bearer '+token}).status_code==403
    assert c.post('/api/notes/trash',json={'items':[items[0],items[0]]},headers=h).status_code==400
    c.patch('/api/notes/'+b['id'],json={'body':'다른 기기에서 수정','version':1},headers=h)
    assert c.post('/api/notes/trash',json={'items':items},headers=h).status_code==409
    assert c.get('/api/notes').json['total']==2
    items[1]['version']=2
    assert c.post('/api/notes/trash',json={'items':items},headers=h).json=={'deleted':2}
    assert c.get('/api/notes').json['total']==0
    assert c.get('/api/notes?state=trash').json['total']==2
    assert c.patch('/api/notes/'+a['id'],json={'version':2,'deleted':False},headers=h).status_code==200


def test_blank_editor_never_creates_note(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.locator('#rich-body').fill(' \n\t\u200b')
    page.locator('#tags').fill('빈 메모의 태그')
    page.locator('#star').click()
    page.locator('#save-note').click()
    expect(page.locator('#save-status')).to_contain_text('빈 메모는 저장하지 않습니다')
    page.locator('#back').click();expect(page.locator('.note-row')).to_have_count(0)
    assert ctx.request.get(url+'/api/notes').json()['total']==0
    assert not page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('hanjul:draft:'))")
    page.locator('#new-note').click();page.locator('#note-title').fill('제목만 있는 메모')
    expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#note-title').fill('');expect(page.locator('#save-status')).to_contain_text('기존 내용 유지')
    page.locator('#back').click();expect(page.locator('.note-row')).to_contain_text('제목만 있는 메모')
    page.locator('.note-row').click();page.locator('#note-title').fill('');page.locator('#trash').click()
    expect(page.locator('.note-row')).to_have_count(0)
    assert ctx.request.get(url+'/api/notes?state=trash').json()['items'][0]['title']=='제목만 있는 메모'


def test_mobile_drawer_and_bulk_long_press(browser_env):
    page,ctx,url,tmp=browser_env
    page.evaluate("""async()=>{for(let i=0;i<3;i++)await api('/notes',{method:'POST',body:{body:'선택할 메모 '+i}});await loadList();}""")
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#sidebar')).to_be_hidden()
    page.locator('#menu-toggle').click();expect(page.locator('#sidebar')).to_be_visible()
    expect(page.locator('#menu-toggle')).to_have_attribute('aria-expanded','true')
    page.locator('#folder-add').click();page.locator('#folder-name').fill('모바일 폴더');page.locator('#folder-submit').click()
    expect(page.locator('#list-title')).to_have_text('모바일 폴더');expect(page.locator('#sidebar')).to_be_hidden()
    page.locator('#menu-toggle').click();page.locator('[data-state=active]').click()
    expect(page.locator('#sidebar')).to_be_hidden();expect(page.locator('.note-row')).to_have_count(3)
    page.locator('#menu-toggle').click();page.keyboard.press('Escape')
    expect(page.locator('#menu-toggle')).to_be_focused()
    # A cancelled touch gesture must never enter selection mode or open a note.
    first=page.locator('.note-row').first;expect(first).to_be_visible();box=first.bounding_box()
    first.dispatch_event('pointerdown',{'button':0,'pointerType':'touch','clientX':box['x']+40,'clientY':box['y']+25})
    first.dispatch_event('pointermove',{'pointerType':'touch','clientX':box['x']+40,'clientY':box['y']+65})
    first.dispatch_event('pointercancel',{'pointerType':'touch'});page.wait_for_timeout(550)
    expect(page.locator('#selection-bar')).to_be_hidden()
    # Native Chromium touch injection also checks suppression of the release click.
    touch=ctx.new_cdp_session(page);box=first.bounding_box()
    touch.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':box['x']+40,'y':box['y']+25}]})
    page.wait_for_timeout(1600)
    touch.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    expect(page.locator('#selection-count')).to_have_text('1개 선택');expect(page.locator('#editor-view')).to_be_hidden()
    page.locator('.note-select').nth(1).check();expect(page.locator('#selection-count')).to_have_text('2개 선택')
    page.screenshot(path='verification/improvements-mobile-selection.png',full_page=True)
    page.once('dialog',lambda dialog:dialog.dismiss());page.locator('#delete-selected').click()
    expect(page.locator('.note-row')).to_have_count(3)
    page.once('dialog',lambda dialog:dialog.accept());page.locator('#delete-selected').click()
    expect(page.locator('.note-row')).to_have_count(1);expect(page.locator('#selection-bar')).to_be_hidden()
    page.locator('#menu-toggle').click();page.screenshot(path='verification/improvements-mobile-drawer.png',full_page=True,animations='disabled')
    page.locator('[data-state=trash]').click();expect(page.locator('.note-row')).to_have_count(2)
    page.locator('.note-row').first.click();page.locator('#trash').click();expect(page.locator('.note-row')).to_have_count(1)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def wide_png():
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1000,600,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x8c\xb5\xa1'*1000)*600))+chunk(b'IEND',b'')


def paste_image(page):
    page.locator('#rich-body').evaluate("""(el,data)=>{const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));const clipboard=new DataTransfer();clipboard.items.add(new File([bytes],'스크린샷.png',{type:'image/png'}));clipboard.setData('text/html','<img src="file:///private/screenshot.png">');el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}));}""",base64.b64encode(wide_png()).decode())


def test_paste_image_into_empty_note_resize_and_roundtrip(browser_env):
    page,ctx,url,tmp=browser_env
    page.set_viewport_size({'width':390,'height':844});page.locator('#mobile-new').click()
    paste_image(page)
    img=page.locator('#rich-body img');expect(img).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    assert ctx.request.get(url+'/api/notes').json()['total']==1
    img.click();expect(page.locator('.image-resize-handle')).to_have_count(4);page.get_by_role('button',name='크기 입력',exact=True).click();expect(page.locator('#image-dialog')).to_be_visible()
    page.locator('#image-width').fill('50');page.locator('#image-apply').click()
    expect(page.locator('#save-status')).to_have_text('저장됨')
    assert '"width=50%"' in page.locator('#body').input_value()
    assert abs(img.bounding_box()['width']/page.locator('#rich-body').bounding_box()['width']-.5)<.02
    page.reload();page.locator('.note-row').click();expect(img).to_be_visible()
    assert abs(img.bounding_box()['width']/page.locator('#rich-body').bounding_box()['width']-.5)<.02
    expect(page.locator('#attachment-list')).to_be_hidden()
    page.locator('#preview-toggle').click();expect(page.locator('#preview img')).to_be_visible()
    page.locator('#preview-toggle').click()
    page.screenshot(path='verification/improvements-mobile-image.png',full_page=True)
    img.click();page.get_by_role('button',name='크기 입력',exact=True).click();page.locator('#image-reset').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    assert 'width=' not in page.locator('#body').input_value()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')


def test_paste_at_caret_and_upload_failure(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.route('**/api/notes/*/attachments',lambda r:r.fulfill(status=503,json={'error':'테스트 첨부 실패'}))
    paste_image(page);expect(page.locator('#save-status')).to_contain_text('첨부 저장 실패')
    assert ctx.request.get(url+'/api/notes').json()['total']==0
    expect(page.locator('#rich-body')).to_have_attribute('contenteditable','true')
    page.unroute('**/api/notes/*/attachments')
    page.locator('#rich-body').fill('앞😀뒤');expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#rich-body').evaluate("""el=>{const text=el.firstChild.nodeType===3?el.firstChild:el.firstChild.firstChild;const r=document.createRange();r.setStart(text,3);r.collapse(true);const s=getSelection();s.removeAllRanges();s.addRange(r);}""")
    paste_image(page);expect(page.locator('#rich-body img')).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    body=page.locator('#body').input_value()
    assert body.startswith('앞😀\n![') and body.endswith('\n뒤')
    assert ctx.request.get(url+'/api/notes').json()['total']==1


def test_selection_pagination_filter_and_conflict(browser_env):
    page,ctx,url,tmp=browser_env
    page.evaluate("""async()=>{for(let i=0;i<42;i++)await api('/notes',{method:'POST',body:{body:'페이지 메모 '+i}});await loadList();}""")
    page.locator('#select-notes').click();page.locator('.note-select').first.check()
    page.locator('#load-more').click();expect(page.locator('.note-row')).to_have_count(42)
    expect(page.locator('#selection-count')).to_have_text('1개 선택')
    page.locator('.note-select').last.check();expect(page.locator('#selection-count')).to_have_text('2개 선택')
    page.locator('#select-all').click();expect(page.locator('#selection-count')).to_have_text('42개 선택')
    page.locator('#search').fill('페이지 메모 41');expect(page.locator('.note-row')).to_have_count(1)
    expect(page.locator('#selection-bar')).to_be_hidden()
    page.locator('#select-notes').click();page.locator('.note-select').check()
    page.evaluate("""async()=>{const [id,version]=[...S.selected][0];await api('/notes/'+id,{method:'PATCH',body:{version,body:'다른 기기에서 변경한 내용'}});}""")
    page.once('dialog',lambda d:d.accept());page.locator('#delete-selected').click()
    expect(page.locator('#toast')).to_contain_text('다른 곳에서 변경')
    assert ctx.request.get(url+'/api/notes?state=trash').json()['total']==0
    page.locator('#search').fill('');expect(page.locator('.note-row')).to_have_count(40)
