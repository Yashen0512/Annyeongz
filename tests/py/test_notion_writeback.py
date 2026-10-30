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
