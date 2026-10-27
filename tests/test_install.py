import json
import struct
from test_browser import browser_env


def test_browser_accepts_install_manifest_and_icons(browser_env):
    page, context, url, tmp_path = browser_env
    session = context.new_cdp_session(page)
    manifest = session.send('Page.getAppManifest')
    assert manifest['errors'] == []
    data = json.loads(manifest['data'])
    assert data['display'] == 'standalone'
    assert data['start_url'] == '/' and data['scope'] == '/'
    for icon in data['icons']:
        response = context.request.get(url + icon['src'])
        assert response.ok and response.headers['content-type'].startswith('image/png')
        body = response.body()
        assert body.startswith(b'\x89PNG\r\n\x1a\n')
        width, height = struct.unpack('>II', body[16:24])
        assert icon['sizes'] == f'{width}x{height}'
    # Installation must not create a second store of private memo responses.
    assert page.evaluate('caches.keys()') == []
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#menu-toggle').click();page.locator('#settings-open').click()
    assert page.get_by_text('휴대폰 앱으로 사용', exact=True).is_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
