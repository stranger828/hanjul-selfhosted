"""Photo summaries and direct resize gestures, using isolated test data."""
import io
import uuid
from playwright.sync_api import expect
from test_api import env, make, PNG
from test_browser import browser_env
from test_note_improvements import paste_image


def test_photo_summary_uses_owned_inline_image_and_clean_text(env):
    app,c,h,tmp=env
    note=make(c,h,body='사진 설명 검색문장')
    uploaded=c.post('/api/notes/'+note['id']+'/attachments',data={'version':1,'file':(io.BytesIO(PNG),'image.png')},headers=h).json
    image_url='/api/attachments/'+uploaded['attachments'][0]['id']
    markdown=f'![image.png]({image_url} "width=30%")'
    c.patch('/api/notes/'+note['id'],json={'version':2,'body':markdown+'\n사진 설명 검색문장'},headers=h)
    row=c.get('/api/notes?q=검색문장').json['items'][0]
    assert row['thumbnail_url']==image_url
    assert row['display_title']=='사진 설명 검색문장' and row['snippet']=='사진 설명 검색문장'
    assert 'body' not in row and 'attachments' not in row
    assert c.get('/api/notes/'+note['id']).json['body']==markdown+'\n사진 설명 검색문장'
    c.patch('/api/notes/'+note['id'],json={'version':3,'body':markdown},headers=h)
    row=c.get('/api/notes').json['items'][0]
    assert row['display_title']=='사진 메모' and row['snippet']=='' and row['thumbnail_url']==image_url
    other=make(c,h,body=markdown+'\n![외부](https://example.test/image.png)')
    rows={n['id']:n for n in c.get('/api/notes').json['items']}
    assert rows[other['id']]['thumbnail_url'] is None
    assert '/api/' not in rows[other['id']]['snippet'] and 'https://' not in rows[other['id']]['snippet']
    c.patch('/api/notes/'+note['id'],json={'version':4,'body':'사진을 지운 본문'},headers=h)
    rows={n['id']:n for n in c.get('/api/notes').json['items']}
    assert rows[note['id']]['thumbnail_url'] is None
    assert app.test_client().get(image_url).status_code==401


def test_photo_thumbnail_mobile_and_selection(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();paste_image(page)
    expect(page.locator('#rich-body img')).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#back').click()
    thumbnail=page.locator('.note-thumbnail');expect(thumbnail).to_be_visible()
    assert thumbnail.evaluate('img=>img.complete&&img.naturalWidth===1000')
    expect(page.locator('.note-row-title')).to_have_text('사진 메모')
    assert '/api/attachments/' not in page.locator('.note-row').inner_text()
    page.set_viewport_size({'width':390,'height':844});page.reload();expect(thumbnail).to_be_visible()
    page.locator('#select-notes').click();thumbnail.click();expect(page.locator('#selection-count')).to_have_text('1개 선택')
    expect(page.locator('#editor-view')).to_be_hidden();page.locator('#cancel-selection').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='verification/photo-list-mobile.png',full_page=True)
    thumbnail.click();expect(page.locator('#rich-body img')).to_be_visible()


def test_all_four_resize_corners_save_proportion_and_cancel(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();paste_image(page)
    img=page.locator('#rich-body img');expect(img).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    img.click();expect(page.locator('.image-resize-handle')).to_have_count(4)
    expect(page.locator('#image-dialog')).to_be_hidden()
    page.get_by_role('button',name='크기 입력',exact=True).click();page.locator('#image-width').fill('40');page.locator('#image-apply').click()
    expect(page.locator('#save-status')).to_have_text('저장됨')
    for corner,sx,sy in [('nw',-1,-1),('ne',1,-1),('sw',-1,1),('se',1,1)]:
        handle=page.locator('.image-resize-handle.'+corner);handle.scroll_into_view_if_needed()
        before=img.bounding_box();box=handle.bounding_box();x=box['x']+12;y=box['y']+12
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+sx*55,y+sy*33,steps=6);page.mouse.up()
        expect(page.locator('#save-status')).to_have_text('저장됨')
        after=img.bounding_box()
        assert after['width']>before['width']+40,corner
        assert abs(after['width']/after['height']-1000/600)<.02
        assert after['width']<=page.locator('#rich-body').bounding_box()['width']+1
    saved=page.locator('#body').input_value()
    assert '크기 입력' not in saved and '모서리' not in saved
    # During a drag there is no Markdown mutation or partial save. Escape cancels it.
    before=img.bounding_box();handle=page.locator('.image-resize-handle.se');box=handle.bounding_box()
    page.mouse.move(box['x']+12,box['y']+12);page.mouse.down();page.mouse.move(box['x']-70,box['y']-40,steps=5)
    page.wait_for_timeout(750);expect(page.locator('#body')).to_have_value(saved)
    page.keyboard.press('Escape');page.mouse.up();expect(page.locator('.image-resize-handle')).to_have_count(0)
    assert abs(img.bounding_box()['width']-before['width'])<1
    page.reload();page.locator('.note-row').click();expect(page.locator('#body')).to_have_value(saved)
    img.click();page.screenshot(path='verification/photo-corner-resize.png',full_page=True)
    # Keyboard sizing and the same handles on a phone-width screen.
    page.set_viewport_size({'width':390,'height':844});img.click()
    page.locator('.image-resize-handle.se').press('Home');expect(page.locator('#save-status')).to_have_text('저장됨')
    assert 'width=20%' in page.locator('#body').input_value()
    page.locator('.image-resize-handle.se').press('End');expect(page.locator('#save-status')).to_have_text('저장됨')
    assert 'width=100%' in page.locator('#body').input_value()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.locator('#preview-toggle').click();expect(page.locator('#preview img')).to_be_visible()
    assert page.locator('#preview .image-resize-handle').count()==0


def test_resize_second_photo_preserves_first_and_reports_remote_conflict(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();paste_image(page)
    expect(page.locator('#rich-body img')).to_have_count(1);expect(page.locator('#save-status')).to_have_text('저장됨')
    paste_image(page);expect(page.locator('#rich-body img')).to_have_count(2);expect(page.locator('#save-status')).to_have_text('저장됨')
    original=page.locator('#body').input_value();first_line=next(line for line in original.splitlines() if line.startswith('!['))
    page.locator('#rich-body img').nth(1).click()
    expect(page.locator('.inline-image').first.locator('.image-resize-handle')).to_have_count(0)
    handle=page.locator('.image-resize-handle.se');handle.scroll_into_view_if_needed();box=handle.bounding_box()
    page.mouse.move(box['x']+12,box['y']+12);page.mouse.down();page.mouse.move(box['x']-70,box['y']-40,steps=5)
    page.evaluate("""async()=>{await api('/notes/'+S.note.id,{method:'PATCH',body:{version:S.note.version,title:'다른 기기의 수정'}});await refreshOpenNote();}""")
    expect(page.locator('#note-title')).to_have_value('')
    expect(page.locator('.image-resize-handle')).to_have_count(4)
    page.mouse.up();expect(page.locator('#conflict')).to_be_visible()
    lines=[line for line in page.locator('#body').input_value().splitlines() if line.startswith('![')]
    assert lines[0]==first_line and 'width=' not in lines[0] and 'width=' in lines[1]
    expect(page.locator('#server-content')).to_contain_text('다른 기기의 수정')
