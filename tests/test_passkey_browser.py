"""Real Chromium WebAuthn with a virtual authenticator, isolated application database."""
import json
import os
import sqlite3
import threading
import time
import pytest
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server
from app import create_app

@pytest.fixture
def web(tmp_path):
    app=create_app(tmp_path/'passkeys',test_password='passkey-test-password')
    server=make_server('127.0.0.1',0,app,threaded=True);origin=f'http://localhost:{server.server_port}';app.config['PUBLIC_ORIGIN']=origin
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=os.environ.get('HANJUL_TEST_CHROME','/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),headless=True)
        context=browser.new_context(viewport={'width':390,'height':844},locale='ko-KR',timezone_id='Asia/Seoul')
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        cdp=context.new_cdp_session(page);cdp.send('WebAuthn.enable')
        cdp.send('WebAuthn.addVirtualAuthenticator',{'options':{'protocol':'ctap2','transport':'internal','hasResidentKey':True,'hasUserVerification':True,'isUserVerified':True,'automaticPresenceSimulation':True}})
        page.goto(origin);page.locator('#password').fill('passkey-test-password');page.locator('#login-form button[type=submit]').click();expect(page.locator('#app')).to_be_visible()
        yield app,page,context,origin,tmp_path
        assert not errors,errors
        browser.close()
    server.shutdown();thread.join()

def stale(app):
    with sqlite3.connect(app.config['DB_PATH']) as db:db.execute('UPDATE sessions SET reauth_at=0')

def register(page):
    page.locator('#menu-toggle').click();page.locator('#settings-open').click();page.locator('#passkey-name').fill('갤럭시용 패스키 검증');expect(page.locator('#passkey-register')).to_be_enabled();page.locator('#passkey-register').click();expect(page.locator('#settings-status')).to_contain_text('패스키가 등록되었습니다.')

def test_registration_reauth_login_password_fallback_and_revoke(web):
    app,page,ctx,origin,tmp=web
    cookie=next(c for c in ctx.cookies() if c['name']=='memo_session');assert 29*86400<cookie['expires']-time.time()<=30*86400
    page.locator('#mobile-new').click();page.locator('#rich-body').fill('패스키로 다시 찾는 내 메모');expect(page.locator('#save-status')).to_have_text('저장됨');page.locator('#back').click()
    register(page)
    stale(app);page.locator('#token-name').fill('재인증 검증');page.locator('#token-form button').click();expect(page.locator('#reauth-dialog')).to_be_visible();page.locator('#reauth-passkey').click();expect(page.locator('#token-result')).to_contain_text('memo_');expect(page.locator('#reauth-dialog')).not_to_be_visible()
    page.locator('#logout').click();expect(page.locator('#login-view')).to_be_visible();page.locator('#passkey-login').click();expect(page.locator('#app')).to_be_visible();expect(page.locator('.note-row')).to_contain_text('패스키로 다시 찾는 내 메모')
    page.locator('#menu-toggle').click();page.locator('#settings-open').click();stale(app);page.locator('#export-download').click();expect(page.locator('#reauth-dialog')).to_be_visible()
    page.locator('#reauth-password').fill('wrong');page.locator('#reauth-form button').click();expect(page.locator('#reauth-error')).to_contain_text('비밀번호를 확인')
    page.locator('#reauth-password').fill('passkey-test-password')
    with page.expect_download() as download:page.locator('#reauth-form button').click()
    download.value.save_as(tmp/'notes.zip');assert (tmp/'notes.zip').stat().st_size>0
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.locator('#passkey-register').scroll_into_view_if_needed()
    page.screenshot(path='docs/passkey-settings.png',full_page=True)
    other=app.test_client();assert other.post('/api/login',json={'password':'passkey-test-password'}).status_code==200
    page.locator('#revoke-other-sessions').click();expect(page.locator('#settings-status')).to_contain_text('다른 브라우저의 로그인을 해제');assert other.get('/api/notes').status_code==401
    page.once('dialog',lambda d:d.accept());page.locator('#passkey-list button').click();expect(page.locator('#login-view')).to_be_visible()
    # Password remains a usable recovery method after revoking the current passkey.
    page.locator('#password').fill('passkey-test-password');page.locator('#login-form button[type=submit]').click();expect(page.locator('#app')).to_be_visible();expect(page.locator('.note-row')).to_have_count(1)

def test_tampered_signature_replay_and_cancel_leave_action_undone(web):
    app,page,ctx,origin,tmp=web;register(page)
    captured=[]
    page.on('request',lambda r:captured.append(r.post_data_json) if r.url.endswith('/passkeys/reauth/verify') else None)
    stale(app);page.locator('#token-name').fill('취소 검증');page.locator('#token-form button').click();expect(page.locator('#reauth-dialog')).to_be_visible();page.locator('#reauth-cancel').click();expect(page.locator('#token-list .token-row')).to_have_count(0)
    def tamper(route):
        d=route.request.post_data_json;sig=d['response']['response']['signature'];d['response']['response']['signature']='AAAA'+sig[4:];route.continue_(post_data=json.dumps(d))
    page.route('**/api/passkeys/reauth/verify',tamper);page.locator('#token-form button').click();page.locator('#reauth-passkey').click();expect(page.locator('#reauth-error')).to_contain_text('검증하지 못했습니다.');expect(page.locator('#token-list .token-row')).to_have_count(0)
    page.unroute('**/api/passkeys/reauth/verify',tamper);page.locator('#reauth-passkey').click();expect(page.locator('#token-result')).to_contain_text('memo_')
    replay=page.evaluate("""async data=>{const {csrf}=await(await fetch('/api/session')).json();return (await fetch('/api/passkeys/reauth/verify',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf,'X-Passkey-Request':'1'},body:JSON.stringify(data)})).status;}""",captured[-1]);assert replay==409
