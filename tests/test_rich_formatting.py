"""Formatting survives editing, save/reload and safe preview rendering."""
from playwright.sync_api import expect
from test_browser import browser_env


def select_text(page, text):
    page.locator('#rich-body').evaluate('''(el,text)=>{
      el.focus();const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);
      while(walker.nextNode()){const node=walker.currentNode,i=node.data.indexOf(text);if(i<0)continue;
       const r=document.createRange();r.setStart(node,i);r.setEnd(node,i+text.length);
       getSelection().removeAllRanges();getSelection().addRange(r);return;}
      throw Error('Text not found: '+text);
    }''', text)


def test_formatting_roundtrip_and_toggle(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.locator('#rich-body').fill('첫 글자와 강조할 내용 그리고 마지막')
    expect(page.locator('#font-size')).to_have_value('3')
    select_text(page,'강조할 내용')
    page.locator('#format-bold').click()
    page.locator('#format-strike').click()
    page.locator('#font-size').select_option('5')
    expect(page.locator('#rich-body')).to_contain_text('첫 글자와 강조할 내용 그리고 마지막')
    assert '<strong>' in page.locator('#body').input_value()
    assert '<s>' in page.locator('#body').input_value()
    assert 'data-size="24"' in page.locator('#body').input_value()
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    saved=page.locator('#body').input_value()
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#body')).to_have_value(saved)
    expect(page.locator('#rich-body font[size="5"]')).to_have_css('font-size','24px')
    page.locator('#preview-toggle').click()
    expect(page.locator('#preview strong')).to_have_text('강조할 내용')
    expect(page.locator('#preview s')).to_have_text('강조할 내용')
    page.locator('#preview-toggle').click()
    select_text(page,'강조할 내용');page.locator('#format-bold').click()
    assert '<strong>' not in page.locator('#body').input_value()
    page.locator('#format-strike').click()
    assert '<s>' not in page.locator('#body').input_value()


def test_edit_table_save_and_mobile(browser_env):
    page,ctx,url,tmp=browser_env
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#mobile-new').click();page.locator('#rich-body').fill('표 위의 메모')
    page.locator('#insert-table').click()
    page.locator('#table-grid [data-row="2"][data-col="3"]').click()
    cells=page.locator('#rich-body td');expect(cells).to_have_count(6)
    cells.nth(0).click();page.keyboard.insert_text('첫 셀')
    page.keyboard.press('Tab');page.keyboard.insert_text('둘째 셀')
    select_text(page,'첫 셀');page.locator('#format-bold').click()
    cells.last.click();page.keyboard.press('Tab');page.keyboard.insert_text('표 아래의 메모')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    saved=page.locator('#body').input_value()
    page.reload();page.locator('.note-row').click()
    expect(cells).to_have_count(6);expect(cells.nth(0).locator('strong')).to_have_text('첫 셀')
    expect(cells.nth(1)).to_have_text('둘째 셀')
    expect(page.locator('#rich-body')).to_contain_text('표 아래의 메모')
    assert '표 아래의 메모' not in page.locator('#rich-body table').inner_text()
    expect(page.locator('#body')).to_have_value(saved)
    page.locator('#preview-toggle').click();expect(page.locator('#preview td')).to_have_count(6)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path='verification/rich-formatting-mobile.png',full_page=True)


def test_typing_styles_undo_and_multiline(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click()
    page.locator('#format-bold').click();page.keyboard.insert_text('새 글자')
    assert '<strong>새 글자</strong>' in page.locator('#body').input_value()
    page.locator('#format-bold').click();page.keyboard.insert_text(' 보통')
    select_text(page,'보통');page.locator('#format-strike').click()
    page.locator('#rich-body').press('ControlOrMeta+z')
    assert '<s>' not in page.locator('#body').input_value()
    page.locator('#rich-body').fill('첫째 줄\n둘째 줄')
    page.locator('#rich-body').press('ControlOrMeta+a');page.locator('#font-size').select_option('6')
    page.locator('#format-bold').click()
    saved=page.locator('#body').input_value()
    page.locator('#preview-toggle').click();page.locator('#preview-toggle').click()
    assert page.evaluate('memoEditor.read()')==saved
    expect(page.locator('#rich-body')).to_contain_text('둘째 줄')
    assert page.locator('#rich-body').inner_text().count('strong')==0


def test_safe_markup_and_table_image_position(browser_env):
    from test_note_improvements import paste_image
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('앞 문장')
    page.locator('#insert-table').click();page.locator('#table-grid [data-row="3"][data-col="3"]').click()
    cell=page.locator('#rich-body td').first
    cell.click();page.keyboard.insert_text('사진 앞뒤')
    select_text(page,'사진 앞뒤');page.locator('#format-bold').click()
    select_text(page,'앞뒤');page.keyboard.press('ArrowLeft')
    paste_image(page)
    expect(cell.locator('img')).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    assert page.evaluate('S.note.attachments[0].name')=='스크린샷.png'
    assert cell.inner_text().replace('\n','')=='사진 앞뒤'
    assert page.evaluate('memoEditor.read()')==page.locator('#body').input_value()
    expect(page.locator('#rich-body td')).to_have_count(9)
    page.locator('#preview-toggle').click();expect(page.locator('#preview td').first.locator('img')).to_be_visible()
    page.locator('#preview-toggle').click()
    page.locator('#rich-body td').last.click();page.keyboard.press('Tab');page.keyboard.insert_text('표 밖')
    assert '표 밖' not in page.locator('#rich-body table').inner_text()
    page.evaluate('''()=>{document.querySelector('#body').value='<strong>안전한 서식</strong><script>window.executed=true</script><img src=x onerror="window.executed=true"><span data-size="999">제한 밖</span>';memoEditor.load();}''')
    expect(page.locator('#rich-body strong')).to_have_text('안전한 서식')
    expect(page.locator('#rich-body script,#rich-body img')).to_have_count(0)
    assert not page.evaluate('Boolean(window.executed)')


def test_list_hides_format_tags(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('제목과 발췌에 서식 코드가 보이지 않아요')
    select_text(page,'제목과 발췌');page.locator('#format-bold').click();page.locator('#font-size').select_option('5')
    page.locator('#back').click()
    expect(page.locator('.note-row-title')).to_have_text('제목과 발췌에 서식 코드가 보이지 않아요')
    expect(page.locator('.snippet')).to_have_text('제목과 발췌에 서식 코드가 보이지 않아요')
