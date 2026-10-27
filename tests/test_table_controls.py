import re
from playwright.sync_api import expect
from test_browser import browser_env
from test_editor_clipboard import paste
from test_rich_formatting import select_text


def select_table(page):
    table=page.locator("#rich-body table").first
    rect=table.bounding_box()
    page.mouse.move(rect["x"]+1,rect["y"]+rect["height"]*0.3,steps=3)
    expect(table).to_have_css("cursor","default")
    page.mouse.click(rect["x"]+1,rect["y"]+rect["height"]*0.3)
    expect(page.locator("#table-selection-box")).to_be_visible()
    expect(page.locator("#table-selection-box button:visible")).to_have_count(8)
    expect(page.locator("#table-tools")).to_have_count(0)


def drag_cells(page, first, last):
    a=first.bounding_box();b=last.bounding_box()
    page.mouse.move(a["x"]+a["width"]/2,a["y"]+a["height"]/2)
    page.mouse.down()
    page.mouse.move(b["x"]+b["width"]/2+8,b["y"]+b["height"]/2,steps=6)
    page.mouse.up()
    assert page.evaluate("getSelection().toString()") == ""


def insert_grid(page, rows=2, cols=3):
    page.locator('#insert-table').click()
    page.locator(f'#table-grid [data-row="{rows}"][data-col="{cols}"]').click()


def test_grid_picker_mouse_keyboard_and_mobile(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('그리드 표')
    page.locator('#insert-table').click()
    expect(page.locator('#table-picker')).to_be_visible()
    expect(page.locator('dialog[open]')).to_have_count(0)
    page.locator('#table-grid [data-row="2"][data-col="3"]').hover()
    expect(page.locator('#table-grid-size')).to_have_text('3열 × 2행')
    expect(page.locator('#table-grid .chosen')).to_have_count(6)
    page.screenshot(path='verification/table-picker-desktop.png',full_page=True)
    page.locator('#table-grid [data-row="2"][data-col="3"]').click()
    expect(page.locator('#rich-body td')).to_have_count(6)
    expect(page.locator('#table-picker')).to_be_hidden()
    page.locator('#insert-table').click();page.keyboard.press('Escape')
    expect(page.locator('#rich-body table')).to_have_count(1)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#insert-table').click();page.keyboard.press('ArrowRight');page.keyboard.press('ArrowDown')
    expect(page.locator('#table-grid-size')).to_have_text('2열 × 2행')
    page.screenshot(path='verification/table-picker-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.keyboard.press('Enter');expect(page.locator('#rich-body table')).to_have_count(2)
    expect(page.locator('#rich-body table').last.locator('td')).to_have_count(4)


def test_whole_table_delete_and_undo(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#rich-body').fill('표 앞 문장은 유지')
    insert_grid(page)
    page.locator('#rich-body td').first.click();page.keyboard.insert_text('표 안의 글자')
    select_table(page)
    assert 'table-selected' in page.locator('#rich-body table').get_attribute('class')
    page.keyboard.press('Backspace');expect(page.locator('#rich-body table')).to_have_count(0)
    expect(page.locator('#rich-body')).to_contain_text('표 앞 문장은 유지')
    page.keyboard.press('ControlOrMeta+z');expect(page.locator('#rich-body table')).to_have_count(1)
    expect(page.locator('#rich-body td').first).to_have_text('표 안의 글자')
    page.locator('#rich-body td').first.click();select_table(page);page.keyboard.press('Delete')
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click();expect(page.locator('#rich-body table')).to_have_count(0)
    expect(page.locator('#rich-body')).to_contain_text('표 앞 문장은 유지')


def test_resize_persists_and_escape_cancels(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('크기 조절')
    insert_grid(page)
    table=page.locator('#rich-body table');select_table(page)
    before=table.bounding_box();grip=page.locator('#table-resize').bounding_box()
    page.mouse.move(grip['x']+12,grip['y']+12);page.mouse.down();page.mouse.move(grip['x']-170,grip['y']+95,steps=8);page.mouse.up()
    page.screenshot(path='verification/table-selected-desktop.png',full_page=True)
    after=table.bounding_box();assert after['width']<before['width']-100 and after['height']>before['height']+40
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    saved=page.locator('#body').input_value();assert 'data-width=' in saved and 'data-height=' in saved
    page.reload();page.locator('.note-row').click()
    assert abs(table.bounding_box()['width']-after['width'])<3
    assert abs(table.bounding_box()['height']-after['height'])<3
    assert page.evaluate('memoEditor.read()')==saved
    page.locator('#preview-toggle').click();expect(page.locator('#preview table')).to_have_attribute('data-width',table.get_attribute('data-width'))
    page.locator('#preview-toggle').click();page.locator('#rich-body td').first.click();select_table(page)
    grip=page.locator('#table-resize').bounding_box();page.mouse.move(grip['x']+12,grip['y']+12);page.mouse.down();page.mouse.move(grip['x']-80,grip['y']+90,steps=5);page.keyboard.press('Escape');page.mouse.up()
    expect(page.locator('#body')).to_have_value(saved)
    assert abs(table.bounding_box()['width']-after['width'])<3
    select_table(page);page.locator('#table-resize').focus();page.keyboard.press('ArrowLeft')
    assert int(table.get_attribute('data-width')) < int(re.search(r'data-width="(\d+)"',saved)[1])
    page.keyboard.press('ControlOrMeta+z');expect(page.locator('#body')).to_have_value(saved)


def test_cell_selection_is_distinct_from_text_editing(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();paste(page,'A\tB\tC\nD\tE\tF')
    cells=page.locator('#rich-body td');drag_cells(page,cells.first,cells.nth(4))
    expect(page.locator('#rich-body .cell-selected')).to_have_count(4)
    page.keyboard.press('Delete');expect(cells).to_have_count(6)
    for i in [0,1,3,4]:assert cells.nth(i).inner_text().strip()==''
    expect(cells.nth(2)).to_have_text('C');expect(cells.nth(5)).to_have_text('F')
    cells.nth(2).click();select_text(page,'C');page.keyboard.press('Backspace')
    expect(cells).to_have_count(6);expect(cells.nth(5)).to_have_text('F')
    expect(page.locator('#rich-body .cell-selected')).to_have_count(0)


def test_cell_selection_with_merged_cells_and_outside_keys(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('남길 제목')
    paste(page,html='<table><tr><td colspan="2">병합</td><td>오른쪽</td></tr><tr><td>왼쪽</td><td>가운데</td><td>끝</td></tr></table>')
    cells=page.locator('#rich-body td');drag_cells(page,cells.first,cells.first)
    cells.nth(3).click(modifiers=['Shift']);expect(page.locator('.cell-selected')).to_have_count(3)
    page.keyboard.press('Delete');expect(cells).to_have_count(5);expect(cells.first).to_have_attribute('colspan','2')
    expect(cells.nth(1)).to_have_text('오른쪽');expect(cells.nth(4)).to_have_text('끝')
    select_table(page);page.locator('#note-title').click();page.keyboard.press('End');page.keyboard.press('Backspace')
    expect(page.locator('#rich-body table')).to_have_count(1)


def test_table_controls_mobile_and_keyboard(browser_env):
    page,ctx,url,tmp=browser_env
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#mobile-new').click();page.locator('#note-title').fill('모바일 표')
    insert_grid(page,2,2)
    table=page.locator('#rich-body table');select_table(page)
    page.locator('#table-resize').focus();page.keyboard.press('ArrowLeft');page.keyboard.press('ArrowLeft')
    expect(table).to_have_attribute('data-width','90')
    page.screenshot(path='verification/table-selected-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    drag_cells(page,table.locator('td').first,table.locator('td').first);page.keyboard.press('Shift+ArrowRight');page.keyboard.press('Shift+ArrowDown')
    expect(page.locator('#rich-body .cell-selected')).to_have_count(4)
    page.keyboard.press('Enter');expect(page.locator('#rich-body .cell-selected')).to_have_count(0)
    page.keyboard.insert_text('셀 입력');expect(table).to_contain_text('셀 입력')


def test_command_drag_selects_text_and_plain_drag_selects_cells(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();paste(page,'드래그할 텍스트\t옆 셀\n아래 셀\t마지막')
    cell=page.locator('#rich-body td').first
    def drag_text(command):
        coords=cell.evaluate("""el=>{const node=el.firstChild,r=document.createRange();r.setStart(node,0);r.setEnd(node,node.length);const b=r.getBoundingClientRect();return {x:b.x,y:b.y+b.height/2,end:b.right};}""")
        if command:page.keyboard.down('Meta')
        page.mouse.move(coords['x']+1,coords['y']);page.mouse.down();page.mouse.move(coords['end']-1,coords['y'],steps=12);page.mouse.up()
        if command:page.keyboard.up('Meta')
    drag_text(False)
    expect(page.locator('.cell-selected')).to_have_count(1)
    assert page.evaluate('getSelection().toString()')==''
    drag_text(True)
    assert page.evaluate('getSelection().toString()')=='드래그할 텍스트'
    expect(page.locator('.cell-selected')).to_have_count(0)
    expect(page.locator('#table-selection-box')).to_be_hidden()
    page.locator('#format-bold').click();expect(cell.locator('b,strong')).to_have_text('드래그할 텍스트');assert '<strong>드래그할 텍스트</strong>' in page.locator('#body').input_value()
    drag_cells(page,cell,page.locator('#rich-body td').last)
    expect(page.locator('.cell-selected')).to_have_count(4)


def test_all_four_resize_corners(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('모서리 조절')
    insert_grid(page);select_table(page)
    table=page.locator('#rich-body table')
    for corner in ['nw','ne','sw','se']:
        before=table.bounding_box();grip=page.locator(f'.table-resize.{corner}').bounding_box()
        x=grip['x']+12;y=grip['y']+12
        page.mouse.move(x,y);page.mouse.down()
        page.mouse.move(x+(30 if corner.endswith('w') else -30),y+(-20 if corner.startswith('n') else 20),steps=5);page.mouse.up()
        after=table.bounding_box()
        assert after['width']<before['width']-20
        assert after['height']>=before['height']+19
        expect(page.locator('#table-selection-box')).to_be_visible()


def test_border_can_be_selected_from_just_outside_editor(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();insert_grid(page)
    table=page.locator('#rich-body table');rect=table.bounding_box()
    page.mouse.move(rect['x']-3,rect['y']+rect['height']/2,steps=3)
    expect(table).to_have_css('cursor','default')
    page.mouse.click(rect['x']-3,rect['y']+rect['height']/2)
    expect(page.locator('#table-selection-box')).to_be_visible()
    page.keyboard.press('Escape');expect(page.locator('#table-selection-box')).to_be_hidden()


def test_vertical_handles_shrink_default_table_and_persist(browser_env):
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('표 높이')
    insert_grid(page,3,3);page.keyboard.insert_text('내용 유지')
    select_table(page);table=page.locator('#rich-body table');before=table.bounding_box()
    def resize_vertical(side,dy):
        grip=page.locator(f'.table-resize.{side}').bounding_box()
        x=grip['x']+12;y=grip['y']+12
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x,y+dy,steps=8);page.mouse.up()
    resize_vertical('s',-45)
    smaller=table.bounding_box()
    assert smaller['height']<before['height']-30
    assert abs(smaller['width']-before['width'])<2
    expect(table).to_contain_text('내용 유지')
    resize_vertical('n',-80)
    taller=table.bounding_box();assert taller['height']>smaller['height']+70
    assert abs(taller['width']-before['width'])<2
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click()
    assert abs(table.bounding_box()['height']-taller['height'])<2
    page.locator('#preview-toggle').click()
    assert abs(page.locator('#preview table').bounding_box()['height']-taller['height'])<2


def test_native_cell_copy_paste_right_and_selected_destination(browser_env):
    page,ctx,url,tmp=browser_env
    ctx.grant_permissions(['clipboard-read','clipboard-write'])
    page.locator('#new-note').click();paste(page,'A\tB\tC\nD\tE\tF')
    cells=page.locator('#rich-body td')
    page.evaluate("navigator.clipboard.writeText('이전 클립보드')")
    drag_cells(page,cells.first,cells.nth(3));page.keyboard.press('ControlOrMeta+c')
    assert page.evaluate('navigator.clipboard.readText()')=='A\nD'
    # A selected target cell must become the paste origin, not a stale caret.
    drag_cells(page,cells.nth(2),cells.nth(2));page.keyboard.press('ControlOrMeta+v')
    expect(cells.nth(2)).to_have_text('A');expect(cells.nth(5)).to_have_text('D')
    expect(cells.first).to_have_text('A');expect(cells.nth(3)).to_have_text('D')
    drag_cells(page,cells.nth(1),cells.nth(2));page.keyboard.press('ControlOrMeta+c')
    cells.nth(5).click();page.keyboard.press('ControlOrMeta+v')
    expect(cells).to_have_count(8)
    expect(cells.nth(6)).to_have_text('B');expect(cells.nth(7)).to_have_text('A')
    page.keyboard.press('ControlOrMeta+z');expect(cells).to_have_count(6)


def test_selected_image_delete_inside_cell_and_undo(browser_env):
    from test_note_improvements import paste_image
    page,ctx,url,tmp=browser_env
    page.locator('#new-note').click();page.locator('#note-title').fill('셀 안 이미지 삭제')
    insert_grid(page,2,2);cell=page.locator('#rich-body td').first
    page.keyboard.insert_text('남길 내용');paste_image(page)
    expect(cell.locator('img')).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    cell.locator('img').click();page.keyboard.press('Delete')
    expect(cell.locator('img')).to_have_count(0);expect(cell).to_contain_text('남길 내용')
    expect(page.locator('#rich-body td')).to_have_count(4)
    page.keyboard.press('ControlOrMeta+z');expect(cell.locator('img')).to_be_visible()
    cell.locator('img').click();page.locator('.image-resize-handle.se').focus();page.keyboard.press('Backspace');expect(cell.locator('img')).to_have_count(0)
    page.locator('#save-note').click();expect(page.locator('#save-status')).to_have_text('저장됨')
    page.reload();page.locator('.note-row').click()
    expect(page.locator('#rich-body img')).to_have_count(0);expect(cell).to_contain_text('남길 내용')


def test_cell_copy_preserves_format_and_image(browser_env):
    from test_note_improvements import paste_image
    page,ctx,url,tmp=browser_env
    ctx.grant_permissions(['clipboard-read','clipboard-write'])
    page.locator('#new-note').click();insert_grid(page,1,2)
    cells=page.locator('#rich-body td')
    page.locator('#format-bold').click();page.keyboard.insert_text('서식 복사');page.locator('#format-bold').click()
    paste_image(page);expect(cells.first.locator('img')).to_be_visible();expect(page.locator('#save-status')).to_have_text('저장됨')
    # Start in the cell padding so this gesture selects the cell, not its image.
    rect=cells.first.bounding_box()
    page.mouse.move(rect['x']+12,rect['y']+10);page.mouse.down();page.mouse.move(rect['x']+30,rect['y']+10,steps=4);page.mouse.up()
    expect(page.locator('.cell-selected')).to_have_count(1)
    page.keyboard.press('ControlOrMeta+c');cells.last.click();page.keyboard.press('ControlOrMeta+v')
    expect(cells.last.locator('img')).to_be_visible()
    expect(cells.last.locator('b,strong')).to_contain_text('서식 복사')
    cells.last.locator('img').click();page.keyboard.press('Delete')
    expect(cells.last.locator('img')).to_have_count(0);expect(cells.first.locator('img')).to_be_visible()
