"""Uses an isolated temporary DB and an isolated Chrome profile. No personal data."""
import base64
import os
import json
import threading
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from app import create_app

@pytest.fixture
def browser_env(tmp_path):
    app=create_app(tmp_path/'browser-db',test_password='browser-test-password')
    server=make_server('127.0.0.1',0,app,threaded=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('HANJUL_TEST_CHROME','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless=True)
        ctx=browser.new_context(viewport={'width':1440,'height':1050},timezone_id='Asia/Seoul',locale='ko-KR')
        page=ctx.new_page();url=f'http://127.0.0.1:{server.server_port}'
        page.goto(url);page.locator('#password').fill('browser-test-password');page.locator('#login-form button[type=submit]').click();expect(page.locator('#app')).to_be_visible()
        yield page,ctx,url,tmp_path
        browser.close()
    server.shutdown();thread.join()

def test_browser_notes_and_failure_recovery(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('제목 없이 기록\n프로젝트 회의 자료 Python\n- [ ] 확인할 일')
    expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();expect(page.locator('.note-row')).to_have_count(1)
    expect(page.locator('.note-row')).to_contain_text('제목 없이 기록')
    page.locator('#search').fill('젝트 PYTHON');expect(page.locator('.note-row')).to_have_count(1)
    expect(page.locator('.snippet mark').first).to_have_text('젝트')
    page.locator('.note-row').click();page.locator('#preview-toggle').click();page.locator('#preview input[type=checkbox]').check()
    expect(page.locator('#save-status')).to_have_text('저장됨');page.locator('#preview-toggle').click();expect(page.locator('#body')).to_contain_text('')
    assert '- [x] 확인할 일' in page.locator('#body').input_value()
    page.screenshot(path='docs/editor.png',full_page=True)
    def fail(route):
        if route.request.method=='PATCH':route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':'테스트 저장 실패'}))
        else:route.continue_()
    page.route('**/api/notes/*',fail);page.locator('#rich-body').fill('저장되지 않은 복구 초안\n프로젝트 Python')
    expect(page.locator('#save-status')).to_contain_text('저장 실패')
    assert page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('hanjul:draft:'))")
    page.once('dialog',lambda d:d.accept());page.reload();page.unroute('**/api/notes/*',fail)
    expect(page.locator('#draft-banner')).to_be_visible();page.locator('#draft-banner button').first.click()
    expect(page.locator('#body')).to_have_value('저장되지 않은 복구 초안\n프로젝트 Python')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    assert not page.evaluate("Object.keys(localStorage).some(k=>k.startsWith('hanjul:draft:'))")
    page.locator('#back').click();expect(page.locator('#search')).to_have_value('젝트 PYTHON')
    expect(page.locator('.note-row')).to_contain_text('저장되지 않은 복구 초안')
    page.locator('.note-row').click()
    expect(page.locator('#editor-view')).to_be_visible()
    page.locator('#file').set_input_files({'name':'테스트.png','mimeType':'image/png','buffer':base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jD1sAAAAASUVORK5CYII=')})
    expect(page.locator('#rich-body img')).to_be_visible();expect(page.locator('#attachment-list')).to_be_hidden()
    page.locator('#preview-toggle').click();expect(page.locator('#preview img')).to_be_visible()
    assert page.locator('#preview img').evaluate('(img)=>img.complete && img.naturalWidth===1')
    page.locator('#trash').click();expect(page.locator('.note-row')).to_have_count(0)
    page.locator('[data-state=trash]').click();expect(page.locator('.note-row')).to_have_count(1)
    page.locator('.note-row').click();page.locator('#trash').click();expect(page.locator('.note-row')).to_have_count(0)

def test_browser_conflict_and_mobile(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('함께 열어둔 메모');expect(page.locator('#save-status')).to_have_text('저장됨')
    second=ctx.new_page();second.goto(url);second.locator('.note-row').click()
    page.locator('#rich-body').fill('첫 탭에서 바뀐 내용');expect(page.locator('#save-status')).to_have_text('저장됨')
    second.locator('#rich-body').fill('다른 탭의 소중한 초안');expect(second.locator('#conflict')).to_be_visible()
    expect(second.locator('#server-content')).to_contain_text('첫 탭에서 바뀐 내용')
    second.locator('#conflict-copy').click();expect(second.locator('#save-status')).to_have_text('새 메모로 저장됨')
    second.locator('#back').click();expect(second.locator('.note-row')).to_have_count(2)
    second.set_viewport_size({'width':390,'height':844});second.screenshot(path='docs/mobile.png',full_page=True)
    assert second.evaluate('document.documentElement.scrollWidth <= innerWidth')
    second.locator('#mobile-new').click();second.locator('#rich-body').fill('휴대폰에서도 편안하게\n짧은 생각 기록');expect(second.locator('#save-status')).to_have_text('저장됨')
    assert second.evaluate('document.documentElement.scrollWidth <= innerWidth')
    second.locator('#back').click();second.set_viewport_size({'width':1440,'height':1050});second.screenshot(path='docs/desktop.png',full_page=True)

def test_typing_during_slow_save(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('처음 내용');expect(page.locator('#save-status')).to_have_text('저장됨')
    # Commit server write, then type and change importance before its response arrives.
    delayed=[False]
    def delay_response(route):
        if route.request.method=='PATCH' and not delayed[0]:
            delayed[0]=True
            response=route.fetch()
            page.evaluate("""() => { const a=document.querySelector('#rich-body'); a.textContent='저장 도중 추가한 내용'; a.dispatchEvent(new Event('input',{bubbles:true})); document.querySelector('#star').click(); }""")
            time.sleep(.2)
            route.fulfill(response=response)
        else:route.continue_()
    page.route('**/api/notes/*',delay_response)
    page.locator('#rich-body').fill('두 번째 내용')
    # Stop the debounce so only the explicit save button can start this request.
    page.evaluate('clearTimeout(S.timer)')
    page.locator('#save-note').click()
    expect(page.locator('#body')).to_have_value('저장 도중 추가한 내용')
    expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click();expect(page.locator('#star')).to_have_attribute('aria-pressed','true');expect(page.locator('#body')).to_have_value('저장 도중 추가한 내용')

def test_search_list_scroll_restored(browser_env):
    page,ctx,url,tmp=browser_env
    # Seed through authenticated API into this test's temporary database only.
    page.evaluate("""async () => { const {csrf}=await (await fetch('/api/session')).json();for(let i=0;i<85;i++){await fetch('/api/notes',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({body:'검색 보존 메모 '+i+'\\n스크롤 위치 확인'})});}}""")
    page.reload();expect(page.locator('.note-row')).to_have_count(40)
    page.locator('#load-more').click();expect(page.locator('.note-row')).to_have_count(80)
    page.locator('.note-row').nth(65).scroll_into_view_if_needed();before=page.evaluate('scrollY')
    page.locator('.note-row').nth(65).click();expect(page.locator('#editor-view')).to_be_visible()
    page.locator('#back').click();expect(page.locator('.note-row')).to_have_count(80)
    page.wait_for_function('(expected) => Math.abs(scrollY-expected)<50',arg=before)
    page.reload();expect(page.locator('.note-row')).to_have_count(80)
    page.wait_for_function('(expected) => Math.abs(scrollY-expected)<50',arg=before)

def test_settings_export_import_and_token(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('데이터 이동 확인\n링크 https://example.org');page.locator('#tags').fill('개인, 자료')
    expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#settings-open').click();expect(page.locator('#settings')).to_be_visible()
    with page.expect_download() as download:
        page.locator('a[href="/api/export"]').click()
    zip_path=tmp/'ui-export.zip';download.value.save_as(zip_path)
    assert zip_path.stat().st_size>0
    page.locator('#import-file').set_input_files(zip_path)
    expect(page.locator('#import-preview')).to_contain_text('기존 ID 1개 건너뛰기')
    page.locator('#import-confirm').click();expect(page.locator('#import-preview')).to_have_text('가져오기 완료: 0개 추가, 1개 건너뜀')
    page.locator('#token-name').fill('테스트 읽기 토큰');page.locator('#token-form button').click()
    expect(page.locator('#token-result')).to_contain_text('memo_')
    token=page.locator('#token-result').inner_text()
    assert ctx.request.get(url+'/api/notes',headers={'Authorization':'Bearer '+token}).status==200
    page.locator('#token-list button').click();expect(page.locator('.token-row')).to_have_count(0)
    assert ctx.request.get(url+'/api/notes',headers={'Authorization':'Bearer '+token}).status==401
    page.locator('#settings-close').click();expect(page.locator('#token-result')).to_have_text('')


def test_inline_images_links_and_markdown_preservation(browser_env):
    import struct
    import zlib
    page,ctx,url,tmp=browser_env
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#mobile-new').click()
    editor=page.locator('#rich-body')
    editor.fill('본문 첫 줄\n\n사진과 링크 확인')
    # Insert a labeled URL through the in-page dialog; no native prompt support required.
    page.locator('#insert-link').click()
    expect(page.locator('#link-dialog')).to_be_visible()
    page.locator('#link-url').fill('https://example.test/watch?v=123&mode=full')
    page.locator('#link-label').fill('영상 열기')
    page.locator('#link-form button[type=submit]').click()
    link=editor.locator('a',has_text='영상 열기')
    expect(link).to_have_attribute('href','https://example.test/watch?v=123&mode=full')
    ctx.route('https://example.test/**',lambda route:route.fulfill(content_type='text/html; charset=utf-8',body='<title>열림 확인</title>'))
    with page.expect_popup() as popup:link.click()
    popup.value.wait_for_load_state();assert popup.value.title()=='열림 확인';popup.value.close()
    # Real wide PNG: ensure the thumbnail stays inside the mobile note width.
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1600,900,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x8c\xb5\xa1'*1600)*900))+chunk(b'IEND',b'')
    page.locator('#file').set_input_files({'name':'가로로 긴 이미지.png','mimeType':'image/png','buffer':png})
    img=editor.locator('img');expect(img).to_be_visible()
    assert img.evaluate('(i)=>i.complete&&i.naturalWidth===1600')
    assert img.bounding_box()['width']<=editor.bounding_box()['width']
    assert img.bounding_box()['height']<=280
    assert '/api/attachments/' not in editor.inner_text()
    before=page.locator('#body').input_value()
    assert '![가로로 긴 이미지.png](/api/attachments/' in before
    assert before.startswith('본문 첫 줄\n\n사진과 링크 확인')
    # Edit after the image; roundtrip retains exact Markdown and empty lines.
    editor.evaluate("el=>{el.focus();const r=document.createRange();r.selectNodeContents(el);r.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(r);}");editor.press('Enter');editor.press('a');editor.press('b')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    written=page.locator('#body').input_value();assert before.rstrip() in written;assert written.endswith('\nab')
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#body')).to_have_value(written)
    expect(editor.locator('img')).to_be_visible()
    expect(editor.locator('a',has_text='영상 열기')).to_have_count(1)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='docs/inline-media-mobile.png',full_page=True)
    # Plain URL pasted with rich HTML is rendered as a link; arbitrary HTML is ignored.
    editor.evaluate("el=>{el.focus();const r=document.createRange();r.selectNodeContents(el);r.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(r);}")
    editor.evaluate(r"""el=>{const data=new DataTransfer();data.setData('text/plain','\nhttps://example.test/pasted');data.setData('text/html','<img src=x onerror=alert(1)>');el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));}""")
    expect(editor.locator('a[href="https://example.test/pasted"]')).to_have_count(1)
    assert editor.locator('img').count()==1
