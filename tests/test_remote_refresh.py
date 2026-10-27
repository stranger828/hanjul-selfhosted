"""Cross-device refresh and races, using isolated temporary notes only."""
import json
from playwright.sync_api import expect
from test_browser import browser_env


def pair(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.locator('#rich-body').fill('공유 메모 원본')
    expect(page.locator('#save-status')).to_have_text('저장됨')
    other_context=ctx.browser.new_context()
    other=other_context.new_page();other.goto(url)
    other.locator('#password').fill('browser-test-password')
    other.locator('#login-form button[type=submit]').click()
    other.locator('.note-row').click()
    return page,other


def test_periodic_refresh_and_focus_keep_read_mode(browser_env):
    page,other=pair(browser_env)
    page.locator('#preview-toggle').click()
    other.locator('#rich-body').fill('휴대폰에서 저장한 최신 내용')
    expect(other.locator('#save-status')).to_have_text('저장됨')
    expect(page.locator('#preview')).to_contain_text('휴대폰에서 저장한 최신 내용',timeout=10000)
    expect(page.locator('#preview')).to_be_visible()
    expect(page.locator('#conflict')).to_be_hidden()
    # Focus restoration checks immediately, independently of the periodic timer.
    other.locator('#rich-body').fill('다시 저장한 내용')
    expect(other.locator('#save-status')).to_have_text('저장됨')
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(page.locator('#preview')).to_contain_text('다시 저장한 내용')


def test_unsaved_draft_is_not_replaced_and_can_be_copied(browser_env):
    page,other=pair(browser_env)
    page.locator('#rich-body').fill('맥에 남겨야 할 초안')
    page.evaluate('clearTimeout(S.timer)')
    other.locator('#rich-body').fill('휴대폰 수정본')
    expect(other.locator('#save-status')).to_have_text('저장됨')
    page.evaluate('refreshOpenNote()')
    expect(page.locator('#conflict')).to_be_visible()
    expect(page.locator('#body')).to_have_value('맥에 남겨야 할 초안')
    expect(page.locator('#server-content')).to_contain_text('휴대폰 수정본')
    assert page.evaluate("Object.values(localStorage).some(v=>v.includes('맥에 남겨야 할 초안'))")
    page.locator('#conflict-copy').click()
    expect(page.locator('#save-status')).to_have_text('새 메모로 저장됨')
    page.locator('#back').click();expect(page.locator('.note-row')).to_have_count(2)


def test_refresh_response_during_korean_composition_preserves_input(browser_env):
    page,other=pair(browser_env)
    other.locator('#rich-body').fill('다른 기기에서 바뀐 본문')
    expect(other.locator('#save-status')).to_have_text('저장됨')
    def delay(route):
        response=route.fetch()
        page.evaluate("""() => {
          const editor=document.querySelector('#rich-body');
          editor.dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true}));
          editor.textContent='조합 중인 한글';
        }""")
        route.fulfill(response=response)
    page.route('**/api/notes/*?known_version=*',delay)
    page.evaluate('refreshOpenNote()')
    expect(page.locator('#rich-body')).to_have_text('조합 중인 한글')
    page.unroute('**/api/notes/*?known_version=*',delay)
    page.evaluate("document.querySelector('#rich-body').dispatchEvent(new CompositionEvent('compositionend',{bubbles:true}));clearTimeout(S.timer)")
    page.evaluate('refreshOpenNote()')
    expect(page.locator('#conflict')).to_be_visible()
    expect(page.locator('#body')).to_have_value('조합 중인 한글')


def test_old_refresh_cannot_replace_another_note_and_failure_recovers(browser_env):
    page,other=pair(browser_env)
    def fail(route):
        route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':'temporary test failure'}))
    page.route('**/api/notes/*?known_version=*',fail)
    page.evaluate('refreshOpenNote()')
    expect(page.locator('#remote-status')).to_contain_text('확인하지 못했습니다')
    expect(page.locator('#body')).to_have_value('공유 메모 원본')
    page.unroute('**/api/notes/*?known_version=*',fail)
    page.evaluate('refreshOpenNote()');expect(page.locator('#remote-status')).to_be_hidden()
    other.locator('#rich-body').fill('이전 메모의 최신 내용')
    expect(other.locator('#save-status')).to_have_text('저장됨')
    def navigate(route):
        response=route.fetch()
        page.evaluate('newNote()')
        route.fulfill(response=response)
    page.route('**/api/notes/*?known_version=*',navigate)
    page.evaluate('refreshOpenNote()')
    expect(page.locator('#body')).to_have_value('')
    expect(page.locator('#conflict')).to_be_hidden()
