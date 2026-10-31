# -*- coding: utf-8 -*-
"""notion_writeback.py 的 rich_text 純函式:❌ 加在連結前、復活時前後都清、PATCH 格式、曾用名合併。不碰網路。"""
import notion_writeback as W

URL = 'https://www.postype.com/@b/post/1'
def link(text='Postype-原文', url=URL):
    return {'type': 'text', 'text': {'content': text, 'link': {'url': url}}, 'plain_text': text, 'href': url,
            'annotations': {'bold': False, 'italic': False, 'strikethrough': False, 'underline': False, 'code': False, 'color': 'default'}}
def plain(text):
    return W._plain_seg(text)
def texts(rts):
    return [W._seg_text(s) for s in rts]

def test_find_link_index_uses_hint_then_scans():
    rts = [plain('原文:'), link()]
    assert W.find_link_index(rts, URL, 1) == 1
    assert W.find_link_index(rts, URL, 0) == 1
    assert W.find_link_index(rts, 'https://other', 1) == -1

def test_mark_dead_inserts_before_link():
    new, changed = W.mark_dead([link()], 0)
    assert changed and texts(new) == ['❌', 'Postype-原文'] and W._href(new[1]) == URL
    new2, changed2 = W.mark_dead(new, 1)
    assert not changed2 and new2 == new

def test_mark_dead_respects_owner_style_after_link():
    rts = [link(), plain('❌')]           # 站長以前手動加在後面
    assert W.mark_dead(rts, 0) == (rts, False)
    assert W.mark_dead([link('PT ❌')], 0) == ([link('PT ❌')], False)

def test_unmark_dead_clears_before_after_and_inside():
    new, ch = W.unmark_dead([link(), plain('❌')], 0)
    assert ch and texts(new) == ['Postype-原文']
    new, ch = W.unmark_dead([plain('❌'), link()], 1)
    assert ch and texts(new) == ['Postype-原文']
    new, ch = W.unmark_dead([plain('原文 ❌ '), link('PT❌')], 1)
    assert ch and texts(new) == ['原文  ', 'PT']
    assert W.unmark_dead([link()], 0) == ([link()], False)

def test_unmark_does_not_touch_other_links():
    other = link('LFT ❌', 'https://x.lofter.com/post/1')
    new, ch = W.unmark_dead([other, link(), plain('❌')], 1)
    assert ch and texts(new) == ['LFT ❌', 'Postype-原文']

def test_to_api_rich_text_strips_readonly_and_keeps_link():
    out = W.to_api_rich_text([plain('❌'), link()])
    assert out[0] == {'type': 'text', 'annotations': out[0]['annotations'], 'text': {'content': '❌', 'link': None}}
    assert out[1]['text'] == {'content': 'Postype-原文', 'link': {'url': URL}} and 'plain_text' not in out[1] and 'href' not in out[1]
    m = {'type': 'mention', 'mention': {'type': 'page', 'page': {'id': 'p'}}, 'plain_text': 'T', 'href': 'https://notion.so/p', 'annotations': {}}
    assert W.to_api_rich_text([m])[0] == {'type': 'mention', 'annotations': {}, 'mention': {'page': {'id': 'p'}}}
    lm = {'type': 'mention', 'mention': {'type': 'link_mention', 'link_mention': {}}, 'plain_text': 'x', 'href': 'https://x', 'annotations': {}}
    assert W.to_api_rich_text([lm])[0]['text'] == {'content': 'x', 'link': {'url': 'https://x'}}

def test_merged_aliases():
    assert W.merged_aliases([], '舊名') == ['舊名']
    assert W.merged_aliases(['舊名'], '舊名') == ['舊名']
    assert W.merged_aliases(['甲'], 'ㅍ.,ㅍ') == ['甲', 'ㅍ.，ㅍ']   # 半形逗號不能當選項名
    assert W.merged_aliases(['甲'], '  ') == ['甲']

# ---- locate / apply_link:只信 __blocks__ 記錄的 block,對不上就跳過並列入「需人工確認」 ----
def _blk(bid, page, rts, typ='paragraph'):
    return {'id': bid, 'type': typ, 'parent': {'type': 'page_id', 'page_id': page}, typ: {'rich_text': rts}}

def test_locate_trusts_only_recorded_block(monkeypatch):
    blocks = {'B1': _blk('B1', 'PA', [plain('原文:'), link()])}
    monkeypatch.setattr(W, 'get_block', lambda bid: blocks[bid])
    item = {'url': URL, 'no': '1', 'title': 'T', 'label': 'Postype-原文', 'block': ['B1', 1], 'page': 'PA'}
    found, why = W.locate(item)
    assert found[0] is blocks['B1'] and found[1] == 'rich_text' and found[3] == 1 and why == ''
    assert W.locate(dict(item, block=['B1', 0]))[0] is not None            # hint 不對就在同一個 block 裡掃
    assert W.locate({'url': URL, 'no': '1', 'page': 'PA'})[0] is None        # 沒有 block 位置 → 不去頁面找
    assert W.locate(dict(item, page='PB'))[0] is None                        # block 在別的頁面底下
    assert W.locate(dict(item, url='https://other'))[0] is None              # block 裡沒有這個網址
    blocks['B1']['archived'] = True
    assert W.locate(item)[0] is None
    assert not hasattr(W, 'page_children') and not hasattr(W, 'find_page_by_no')   # 整頁重掃 / 用 No 查主表的退路已移除

def test_apply_link_skips_and_collects_manual_when_block_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(W, 'get_block', lambda bid: (_ for _ in ()).throw(RuntimeError('404')))
    patched = []
    monkeypatch.setattr(W, 'api', lambda *a, **k: patched.append(a))
    item = {'url': URL, 'no': '786', 'title': 'Passionate A&W', 'label': 'Postype-番外1-原文', 'block': ['B9', 1], 'page': 'PA'}
    manual = []
    assert W.apply_link(item, 'mark', True, manual) == 'fail'
    assert patched == [] and len(manual) == 1 and manual[0]['action'] == 'mark' and 'B9' in manual[0]['why']
    md = tmp_path / 'check_report.md'
    md.write_text('## 已刪\n- x\n', encoding='utf-8')
    W.append_manual_section(str(md), manual)
    text = md.read_text(encoding='utf-8')
    assert text.startswith('## 已刪\n- x\n\n### 需人工確認') and 'No.786《Passionate A&W》Postype-番外1-原文 — ' + URL in text
    W.append_manual_section(str(md), [])                                     # 沒有東西就不動
    assert md.read_text(encoding='utf-8') == text
