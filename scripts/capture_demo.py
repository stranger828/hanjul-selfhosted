"""Render README screenshots using synthetic notes and an isolated temporary DB."""
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import create_app
from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server


def capture():
    with tempfile.TemporaryDirectory(prefix='hanjul-demo-') as temp:
        app = create_app(Path(temp) / 'data', test_password='synthetic-demo-password')
        client = app.test_client()
        csrf = client.post('/api/login', json={'password': 'synthetic-demo-password'}).json['csrf']
        for body, tags in [
            ('자료 조사 체크리스트\n- [ ] 읽은 자료의 링크 남기기\n- [ ] 필요한 화면 캡처하기\n- [x] 기억할 내용을 한 줄로 정리하기', ['자료']),
            ('다음 프로젝트 아이디어\n생각이 떠오르면 먼저 적고, 분류는 나중에 정하기.\n컴퓨터와 휴대폰에서 같은 기록을 이어서 본다.', ['아이디어']),
            ('오늘 남길 한 줄\n기억나는 단어로 다시 찾을 수 있다면, 제목 없이 시작해도 괜찮다.\n이 화면의 메모는 공개 소개용 예시입니다.', ['기록']),
        ]:
            response = client.post('/api/notes', headers={'X-CSRF-Token': csrf}, json={'body': body, 'tags': tags})
            assert response.status_code == 201
        server = make_server('127.0.0.1', 0, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                options = {'headless': True}
                if os.environ.get('HANJUL_TEST_CHROME'):
                    options['executable_path'] = os.environ['HANJUL_TEST_CHROME']
                browser = playwright.chromium.launch(**options)
                try:
                    for name, viewport in [('desktop', {'width': 1440, 'height': 980}), ('mobile', {'width': 390, 'height': 844})]:
                        context = browser.new_context(viewport=viewport, locale='ko-KR', timezone_id='Asia/Seoul')
                        page = context.new_page()
                        page.goto(f'http://localhost:{server.server_port}')
                        page.locator('#password').fill('synthetic-demo-password')
                        page.locator('#login-form button[type=submit]').click()
                        expect(page.locator('#app')).to_be_visible()
                        expect(page.locator('.note-row')).to_have_count(3)
                        page.screenshot(path=str(ROOT / 'docs' / f'demo-{name}.png'), full_page=True, animations='disabled')
                        context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join()


if __name__ == '__main__':
    capture()
