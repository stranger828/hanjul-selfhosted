from pathlib import Path
from playwright.sync_api import expect
from test_browser import browser_env


def test_folder_creation_assignment_rename_and_mobile(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('기존의 분류 없는 메모')
    expect(page.locator('#save-status')).to_have_text('저장됨');page.locator('#back').click()
    page.locator('#folder-add').click();page.locator('#folder-name').fill('여행');page.locator('#folder-submit').click()
    expect(page.locator('#list-title')).to_have_text('여행')
    expect(page.locator('.folder-row').filter(has_text='여행').locator('.folder-count')).to_have_text('0')
    page.locator('#new-note').click();expect(page.locator('#note-folder option:checked')).to_have_text('여행')
    page.locator('#rich-body').fill('부산 여행 준비물');expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#back').click();expect(page.locator('.note-row')).to_have_count(1)
    expect(page.locator('.folder-row').filter(has_text='여행').locator('.folder-count')).to_have_text('1')
    page.get_by_role('button',name='여행 폴더 이름 변경').click();page.locator('#folder-name').fill('여행 계획');page.locator('#folder-submit').click()
    expect(page.locator('#list-title')).to_have_text('여행 계획')
    page.reload();expect(page.locator('#list-title')).to_have_text('여행 계획');expect(page.locator('.note-row')).to_have_count(1)
    page.locator('[data-state=active]').click();expect(page.locator('.note-row')).to_have_count(2)
    page.locator('.note-row').filter(has_text='기존의 분류 없는 메모').click()
    page.locator('#note-folder').select_option(label='여행 계획');expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#back').click();expect(page.locator('.folder-row').filter(has_text='여행 계획').locator('.folder-count')).to_have_text('2')
    page.locator('.folder-nav').filter(has_text='여행 계획').click();expect(page.locator('.note-row')).to_have_count(2)
    page.locator('#search').fill('부산');expect(page.locator('.note-row')).to_have_count(1)
    page.locator('#search').fill('');expect(page.locator('.note-row')).to_have_count(2)
    Path('verification').mkdir(exist_ok=True)
    page.screenshot(path='verification/folders-desktop.png',full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('#sidebar')).to_be_hidden()
    page.locator('#menu-toggle').click()
    expect(page.locator('.folder-nav').filter(has_text='여행 계획')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='verification/folders-mobile.png',full_page=True)
    page.locator('#sidebar-close').click()
    page.locator('.note-row').filter(has_text='부산').click();page.locator('#trash').click()
    expect(page.locator('.folder-row').filter(has_text='여행 계획').locator('.folder-count')).to_have_text('1')
