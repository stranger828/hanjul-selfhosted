from playwright.sync_api import expect
from test_browser import browser_env
from test_rich_formatting import select_text


def paste(page, text='', html=''):
    page.locator('#rich-body').evaluate('''(el,data)=>{el.focus();const clipboard=new DataTransfer();clipboard.setData('text/plain',data.text);clipboard.setData('text/html',data.html);el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}));}''', {'text':text,'html':html})


def test_excel_table_paste_preserves_cells_and_sanitizes(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    paste(page, '할 일\t상태\n문서 작성\t검토중', '''<html><head><style>td {font-weight:bold}</style></head><body><!--StartFragment--><table onclick="alert(1)"><tr><td colspan="2" style="font-weight:700">일정</td></tr><tr><td><b>문서 작성</b><img src="https://example.test/private.png" onerror="window.injected=true"><script>window.injected=true</script></td><td>검토중<br>오늘</td></tr></table><!--EndFragment--></body></html>''')
    expect(page.locator('#rich-body table')).to_have_count(1)
    expect(page.locator('#rich-body td')).to_have_count(3)
    expect(page.locator('#rich-body td').first).to_have_attribute('colspan','2')
    expect(page.locator('#rich-body td').nth(1)).to_have_text('문서 작성')
    expect(page.locator('#rich-body img,#rich-body script')).to_have_count(0)
    assert not page.evaluate('Boolean(window.injected)')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    saved=page.locator('#body').input_value()
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#rich-body td').first).to_have_attribute('colspan','2')
    assert page.evaluate('memoEditor.read()')==saved
    page.locator('#preview-toggle').click();expect(page.locator('#preview td')).to_have_count(3)


def test_tsv_quotes_and_paste_into_existing_cells(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    paste(page, '제품\t설명\r\n가\t"첫 줄\n둘째 줄"\r\n나\t"탭\t포함"\r\n')
    cells=page.locator('#rich-body td');expect(cells).to_have_count(6)
    assert cells.nth(3).inner_text()=='첫 줄\n둘째 줄'
    assert cells.nth(5).inner_text()=='탭\t포함'
    cells.nth(3).click();paste(page,'새 값\t추가 열\n다음 행\t끝')
    expect(page.locator('#rich-body table')).to_have_count(1)
    expect(cells).to_have_count(9)
    expect(cells.nth(4)).to_have_text('새 값');expect(cells.nth(5)).to_have_text('추가 열')
    expect(cells.nth(7)).to_have_text('다음 행');expect(cells.nth(8)).to_have_text('끝')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click();expect(cells).to_have_count(9)


def test_clickable_checklist_enter_exit_and_roundtrip(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('[data-insert=check]').click()
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(1)
    page.keyboard.insert_text('첫 번째 할 일');page.keyboard.press('Enter');page.keyboard.insert_text('두 번째 할 일')
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(2)
    page.locator('#rich-body input[type=checkbox]').first.check()
    assert '- [x] 첫 번째 할 일' in page.locator('#body').input_value()
    select_text(page,'두 번째 할 일');page.keyboard.press('ArrowRight');page.keyboard.press('Enter');page.keyboard.press('Enter');page.keyboard.insert_text('일반 문장')
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(2)
    assert '- [ ] 일반 문장' not in page.locator('#body').input_value()
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    saved=page.locator('#body').input_value()
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#rich-body input[type=checkbox]').first).to_be_checked()
    assert page.evaluate('memoEditor.read()')==saved
    assert '[x]' not in page.locator('#rich-body').inner_text()
    page.locator('#preview-toggle').click();expect(page.locator('#preview input[type=checkbox]').first).to_be_checked()
    page.locator('#preview input[type=checkbox]').first.uncheck();page.locator('#preview-toggle').click()
    expect(page.locator('#rich-body input[type=checkbox]').first).not_to_be_checked()


def test_existing_checklists_and_font_shortcuts(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('- [ ] 이전 할 일\n- [x] 끝난 일')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(2)
    expect(page.locator('#rich-body input[type=checkbox]').last).to_be_checked()
    select_text(page,'이전 할 일');page.keyboard.press('Meta+Equal')
    expect(page.locator('#rich-body font[size="4"]')).to_have_text('이전 할 일')
    page.keyboard.press('Meta+Shift+Equal');expect(page.locator('#rich-body font[size="5"]')).to_have_text('이전 할 일')
    page.keyboard.press('Meta+Minus');expect(page.locator('#rich-body font[size="4"]')).to_have_text('이전 할 일')
    page.keyboard.press('Control+Minus');expect(page.locator('#rich-body font[size="3"]')).to_have_text('이전 할 일')
    expect(page.locator('#font-size option:checked')).to_have_text('17px')
    assert page.locator('#font-size').bounding_box()['width']<=75
    select_text(page,'이전 할 일');page.keyboard.press('ArrowLeft');page.keyboard.press('Backspace')
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(1)
    expect(page.locator('#rich-body')).to_contain_text('이전 할 일')


def test_font_shortcuts_for_new_text_and_whole_checklist(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.locator('#rich-body').press('Meta+Equal');page.keyboard.press('Meta+Equal');page.keyboard.insert_text('새로 쓰는 큰 글자')
    expect(page.locator('#rich-body font[size="5"]')).to_have_text('새로 쓰는 큰 글자')
    page.locator('[data-insert=check]').click()
    page.locator('#rich-body').press('ControlOrMeta+a');page.locator('#format-bold').click()
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.locator('#preview-toggle').click();page.locator('#preview-toggle').click()
    expect(page.locator('#rich-body input[type=checkbox]')).to_have_count(1)
    expect(page.locator('#rich-body strong')).to_contain_text('새로 쓰는 큰 글자')


def test_checkboxes_inside_table_cells(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#insert-table').click();page.locator('#table-grid [data-row="3"][data-col="3"]').click()
    cell=page.locator('#rich-body td').first;cell.click();page.locator('[data-insert=check]').click();page.keyboard.insert_text('셀 안의 할 일')
    expect(cell.locator('input[type=checkbox]')).to_have_count(1)
    cell.locator('input[type=checkbox]').check()
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click()
    expect(cell.locator('input[type=checkbox]')).to_be_checked()
    assert '[x]' not in cell.inner_text()
    page.locator('#preview-toggle').click();page.locator('#preview td input[type=checkbox]').uncheck();page.locator('#preview-toggle').click()
    expect(cell.locator('input[type=checkbox]')).not_to_be_checked()
    expect(cell).to_contain_text('셀 안의 할 일')
