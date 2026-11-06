# -*- coding: utf-8 -*-
"""notion_writeback.py 的 rich_text 純函式:❌ 是連結後一段獨立的純文字、已標判定與復活三種位置都認、--normalize-x 統一舊格式、
   --audit-x 列異常、PATCH 格式、曾用名合併。不碰網路。樣本在 tests/fixtures/notion_rich_text.json(四個模組共用)。"""
import io, json, os
import pytest
import notion_writeback as W

URL = 'https://www.postype.com/@b/post/1'
FIX = os.path.join(os.path.dirname(__file__), '..', 'fixtures', 'notion_rich_text.json')
def link(text='Postype-原文', url=URL):
    return {'type': 'text', 'text': {'content': text, 'link': {'url': url}}, 'plain_text': text, 'href': url,
            'annotations': {'bold': False, 'italic': False, 'strikethrough': False, 'underline': False, 'code': False, 'color': 'default'}}
def plain(text):
    return W._plain_seg(text)
def texts(rts):
    return [W._seg_text(s) for s in rts]
def pairs(rts):
    """rich_text → fixture 的 [文字, 網址 | None] 形狀。"""
    return [[W._seg_text(s), W._href(s) or None] for s in rts]
def from_pairs(ps):
    return [link(t, u) if u else plain(t) for t, u in ps]
def cases():
    return json.load(io.open(FIX, encoding='utf-8'))['cases']

def test_find_link_index_uses_hint_then_scans():
    rts = [plain('原文:'), link()]
    assert W.find_link_index(rts, URL, 1) == 1
    assert W.find_link_index(rts, URL, 0) == 1
    assert W.find_link_index(rts, 'https://other', 1) == -1

def test_mark_dead_inserts_plain_x_after_link():
    """寫入 ❌ 是連結段之後一段獨立的純文字(不帶連結、連結文字原樣):[LFT](url)❌,與站長手標慣例一致。"""
    new, changed = W.mark_dead([plain('原文:'), link('LFT')], 1)
    assert changed and pairs(new) == [['原文:', None], ['LFT', URL], ['❌', None]]
    assert W._href(new[2]) == '' and new[2]['type'] == 'text' and new[2]['text']['link'] is None
    assert W.mark_dead(new, 1) == (new, False)
    new, changed = W.mark_dead([link('LFT ')], 0)       # 連結文字不動(連尾端空白也不碰)
    assert changed and pairs(new) == [['LFT ', URL], ['❌', None]]
    # 後面接著別的純文字:❌ 插在中間,原本的段照舊
    new, changed = W.mark_dead([link('LFT'), plain(' / 備註')], 0)
    assert changed and pairs(new) == [['LFT', URL], ['❌', None], [' / 備註', None]]
    # 同一段裡有別條連結:只改這一條
    other = link('PT', 'https://www.postype.com/@c/post/9')
    new, changed = W.mark_dead([other, plain(' / '), link('LFT')], 2)
    assert changed and texts(new) == ['PT', ' / ', 'LFT', '❌']

def test_is_marked_accepts_three_positions():
    """判斷「已標」時三種位置都算:連結後緊鄰純文字開頭(現行)、連結文字本身(舊)、緊鄰前一段結尾(更舊)。"""
    assert W.is_marked([link(), plain('❌')], 0) and W.is_marked([link(), plain(' ❌ 備註')], 0)       # 站長手標 / 現行寫法
    assert W.is_marked([link('LFT❌')], 0) and W.is_marked([link('❌LFT')], 0) and W.is_marked([link('LFT ❌')], 0)   # 舊:在連結文字內
    assert W.is_marked([plain('❌'), link()], 1) and W.is_marked([plain('原文 ❌ '), link()], 1)     # 更舊:寫在前面
    assert not W.is_marked([link()], 0) and not W.is_marked([plain('原文:'), link(), plain(' / ')], 1)
    # [A](a)❌[B](b):中間那個是 A 的;B 要隔著別的字(「 / ❌」)或 A 不是連結,❌ 才算 B 前面的舊格式
    ab = [link('A', 'https://a'), plain('❌'), link('B', 'https://b')]
    assert W.is_marked(ab, 0) and not W.is_marked(ab, 2)
    assert W.is_marked([link('A', 'https://a'), plain(' / ❌'), link('B', 'https://b')], 2)
    assert W.is_marked([plain('A'), plain('❌'), link('B', 'https://b')], 2)
    # 鄰段中間的 ❌ 不算(那是別條連結的):「PT❌ / LFT」的 LFT 沒標;「PT / ❌LFT」的 LFT 有標、PT 沒標
    pt = link('PT', 'https://www.postype.com/@c/post/9')
    assert not W.is_marked([pt, plain('❌ / '), link()], 2) and W.is_marked([pt, plain('❌ / '), link()], 0)
    assert W.is_marked([pt, plain(' / ❌'), link()], 2) and not W.is_marked([pt, plain(' / ❌'), link()], 0)
    for rts, idx in (([link('LFT❌')], 0), ([plain('❌'), link()], 1), ([link(), plain('❌')], 0)):
        assert W.mark_dead(rts, idx) == (rts, False)                      # 已標(不分位置)就不再加

def test_unmark_dead_clears_both_positions_and_inside():
    """移除 ❌(復活):連結後緊鄰的純文字 ❌(現行),也相容舊格式(連結文字內、連結前)都拿掉。"""
    new, ch = W.unmark_dead([link(), plain('❌')], 0)                     # 現行:後一段(mark_dead 寫的 / 站長手標)
    assert ch and texts(new) == ['Postype-原文']
    new, ch = W.unmark_dead([link('LFT'), plain('❌ / 備註')], 0)        # 後一段沒清空就留著
    assert ch and texts(new) == ['LFT', ' / 備註']
    new, ch = W.unmark_dead([link('LFT❌')], 0)                           # 舊:連結文字內
    assert ch and texts(new) == ['LFT'] and W._href(new[0]) == URL
    new, ch = W.unmark_dead([link('❌ LFT')], 0)                          # 邊上連帶的空白也拿掉
    assert ch and texts(new) == ['LFT']
    new, ch = W.unmark_dead([plain('❌'), link()], 1)                     # 更舊:前一段
    assert ch and texts(new) == ['Postype-原文']
    new, ch = W.unmark_dead([plain('原文 ❌ '), link('❌PT❌')], 1)        # 三處一起清;鄰段沒清空就留著
    assert ch and texts(new) == ['原文  ', 'PT']
    new, ch = W.unmark_dead([plain('❌'), link('LFT❌'), plain('❌')], 1)
    assert ch and texts(new) == ['LFT']
    new, ch = W.unmark_dead([plain('原文:'), link(), plain('❌ 備註')], 1)
    assert ch and texts(new) == ['原文:', 'Postype-原文', ' 備註']
    assert W.unmark_dead([link()], 0) == ([link()], False)
    # 連結文字只有 ❌ → 清空後用網址當文字(Notion 不收空的連結段)
    new, ch = W.unmark_dead([link('❌')], 0, URL)
    assert ch and texts(new) == [URL] and W._href(new[0]) == URL

def test_unmark_does_not_touch_other_links():
    other = link('LFT❌', 'https://x.lofter.com/post/1')
    new, ch = W.unmark_dead([other, link(), plain('❌')], 1)
    assert ch and texts(new) == ['LFT❌', 'Postype-原文']
    # 鄰段中間的 ❌ 屬於別條連結,不動:「PT❌ / LFT❌」只復活 LFT
    new, ch = W.unmark_dead([link('PT', 'https://p'), plain('❌ / '), link('LFT❌')], 2)
    assert ch and texts(new) == ['PT', '❌ / ', 'LFT']
    # [A](a)❌[B](b):復活 B 不會把 A 的 ❌ 拿掉;復活 A 才會
    ab = [link('A', 'https://a'), plain('❌'), link('B', 'https://b')]
    assert W.unmark_dead(ab, 2) == (ab, False)
    assert texts(W.unmark_dead(ab, 0)[0]) == ['A', 'B']

def test_normalize_marks_unifies_all_old_formats():
    """--normalize-x:連結前的純文字 ❌、連結文字內的 ❌ 都統一成「連結後一個純文字 ❌」,連結文字還原、一條連結只留一個。"""
    new, n = W.normalize_marks([plain('原文:'), plain('❌'), link('LFT')])   # 最早的 writeback 寫法
    assert n == 1 and pairs(new) == [['原文:', None], ['LFT', URL], ['❌', None]]
    new, n = W.normalize_marks([link('LFT❌')])                                # 2026-11-06 的寫法
    assert n == 1 and pairs(new) == [['LFT', URL], ['❌', None]]
    new, n = W.normalize_marks([link('❌LFT')])
    assert n == 1 and pairs(new) == [['LFT', URL], ['❌', None]]
    new, n = W.normalize_marks([plain('原文 ❌'), link('❌ LFT')])
    assert n == 1 and pairs(new) == [['原文 ', None], ['LFT', URL], ['❌', None]]
    # 後面已經有 → 只拿掉其他位置的,不重複加;多個只留一個
    new, n = W.normalize_marks([plain('❌'), link('LFT❌'), plain('❌')])
    assert n == 1 and pairs(new) == [['LFT', URL], ['❌', None]]
    new, n = W.normalize_marks([link('LFT'), plain('❌❌ 備註')])
    assert n == 1 and pairs(new) == [['LFT', URL], ['❌ 備註', None]]
    new, n = W.normalize_marks([link('LFT'), plain(' ❌ ❌')])
    assert n == 1 and pairs(new) == [['LFT', URL], [' ❌ ', None]]
    # 已經是現行格式、或沒標的 → 不動、不算
    for rts in ([link('LFT'), plain('❌')], [link('LFT'), plain(' ❌ 備註')], [plain('原文:'), link('LFT')], [link('LFT'), plain(' / ❌備註')]):
        assert W.normalize_marks(rts) == (rts, 0)
    # 同一段多條連結、各自處理;「PT❌ / LFT」中間那個 ❌ 是 PT 的(現行格式),LFT 不動
    pt = 'https://www.postype.com/@c/post/9'
    new, n = W.normalize_marks([plain('❌'), link('PT', pt), plain(' / '), plain('❌'), link('LFT')])
    assert n == 2 and pairs(new) == [['PT', pt], ['❌', None], [' / ', None], ['LFT', URL], ['❌', None]]
    assert W.normalize_marks([link('PT', pt), plain('❌ / '), link('LFT')])[1] == 0
    new, n = W.normalize_marks([link('PT❌', pt), plain(' / '), link('LFT❌')])
    assert n == 2 and pairs(new) == [['PT', pt], ['❌', None], [' / ', None], ['LFT', URL], ['❌', None]]
    # [A](a)❌[B](b):中間那個 ❌ 是 A 的(現行格式)、B 沒標 → 不動;隔著「 / 」的才是 B 的舊格式 → 搬到 B 後面
    ab = [link('A', 'https://a'), plain('❌'), link('B', 'https://b')]
    assert W.normalize_marks(ab) == (ab, 0)
    new, n = W.normalize_marks([link('A', 'https://a'), plain(' / ❌'), link('B', 'https://b')])
    assert n == 1 and pairs(new) == [['A', 'https://a'], [' / ', None], ['B', 'https://b'], ['❌', None]]
    new, n = W.normalize_marks([link('A❌', 'https://a'), plain('❌'), link('B', 'https://b')])     # A 兩個 → 一個;B 照舊沒標
    assert n == 1 and pairs(new) == [['A', 'https://a'], ['❌', None], ['B', 'https://b']]
    # 連結文字只有 ❌ → 用網址當文字
    new, n = W.normalize_marks([link('❌')])
    assert n == 1 and pairs(new) == [[URL, URL], ['❌', None]]
    # page mention(站內互連)的文字是 Notion 算的,不動
    m = {'type': 'mention', 'mention': {'type': 'page', 'page': {'id': 'p'}}, 'plain_text': '前傳', 'href': 'https://notion.so/p', 'annotations': {}}
    assert W.normalize_marks([plain('❌'), m]) == ([plain('❌'), m], 0)
    # 不改原本的 rich_text
    src = [plain('❌'), link('LFT❌')]
    W.normalize_marks(src)
    assert texts(src) == ['❌', 'LFT❌']

def test_audit_marks_reports_three_kinds():
    """--audit-x:同一連結超過一個 ❌ / ❌ 在連結文字內 / 連結文字只剩 ❌;正常與沒標的不報。"""
    kinds = lambda rts: [x['kind'] for x in W.audit_marks(rts)]
    assert kinds([link('LFT'), plain('❌')]) == [] and kinds([plain('原文:'), link('LFT')]) == [] and kinds([plain('❌'), link('LFT')]) == []
    assert kinds([link('LFT❌')]) == ['inside'] and kinds([link('❌ LFT')]) == ['inside']
    assert kinds([link('LFT❌'), plain('❌')]) == ['multi', 'inside']
    assert kinds([link('LFT'), plain('❌❌')]) == ['multi'] and kinds([plain('❌'), link('LFT'), plain('❌')]) == ['multi']
    assert kinds([link('❌')]) == ['inside', 'only_x'] and kinds([link(' ❌ ')]) == ['inside', 'only_x']
    assert kinds([link('❌❌')]) == ['multi', 'inside', 'only_x']
    x = W.audit_marks([plain('前'), link('LFT❌'), plain('❌')])[0]
    assert x == {'kind': 'multi', 'url': URL, 'text': 'LFT❌', 'count': 2}
    # 同一段多條連結各自報;鄰段中間的 ❌ 不算到別條頭上
    pt = 'https://www.postype.com/@c/post/9'
    assert [(x['kind'], x['url']) for x in W.audit_marks([link('PT', pt), plain('❌ / '), link('LFT❌')])] == [('inside', URL)]
    assert W.audit_marks([]) == [] and W.audit_marks(None) == []
    assert [k for k, _ in W.AUDIT_KINDS] == ['multi', 'inside', 'only_x']

def test_fixture_cases_round_trip():
    """tests/fixtures/notion_rich_text.json 的每個樣本:is_marked、normalize_marks、audit_marks 都對得上;
    統一後的結果再跑一次 normalize / audit 是乾淨的(冪等),復活(unmark_dead)能把三種格式都清掉。"""
    for c in cases():
        rts = from_pairs(c['rich_text'])
        idxs = [i for i, s in enumerate(rts) if W._href(s)]
        assert [W.is_marked(rts, i) for i in idxs] == c['marked'], c['name']
        new, n = W.normalize_marks(rts)
        assert (pairs(new), n) == (c['normalized'], c['changed']), c['name']
        assert [x['kind'] for x in W.audit_marks(rts)] == c['audit'], c['name']
        assert W.normalize_marks(new) == (new, 0) and W.audit_marks(new) == [], c['name']
        assert [W.is_marked(new, i) for i, s in enumerate(new) if W._href(s)] == c['marked'], c['name']   # 統一後已標 / 沒標不變
        for i in idxs:
            if W.is_marked(rts, i):
                cleared, ch = W.unmark_dead(rts, i, W._href(rts[i]))
                assert ch, c['name']
                j = [k for k, s in enumerate(cleared) if W._href(s) == W._href(rts[i])][0]
                assert not W.is_marked(cleared, j) and '❌' not in W._seg_text(cleared[j]), c['name']

def test_caption_helpers():
    """bookmark / embed 的 caption:❌ 放結尾、移除時全清、normalize 統一成結尾一段、只留一個;audit 只報超過一個。"""
    new, ch = W.mark_caption([plain('LFT')])
    assert ch and texts(new) == ['LFT', '❌']
    assert W.mark_caption([]) [0] and texts(W.mark_caption([])[0]) == ['❌']
    assert W.mark_caption([plain('❌'), plain('LFT')]) == ([plain('❌'), plain('LFT')], False)
    assert W.unmark_caption([plain('❌'), plain('LFT ❌')]) == ([plain('LFT ')], True)
    assert W.unmark_caption([plain('LFT')]) == ([plain('LFT')], False)
    new, n = W.normalize_caption([plain('❌'), plain('LFT')])
    assert n == 1 and texts(new) == ['LFT', '❌']
    new, n = W.normalize_caption([plain('❌LFT')])
    assert n == 1 and texts(new) == ['LFT', '❌']
    new, n = W.normalize_caption([plain('❌'), plain('LFT ❌')])          # 兩個 → 一個
    assert n == 1 and texts(new) == ['LFT ', '❌']
    assert W.normalize_caption([plain('LFT'), plain('❌')]) == ([plain('LFT'), plain('❌')], 0)
    assert W.normalize_caption([plain('❌')]) == ([plain('❌')], 0)          # 沒有 caption 時 mark_caption 就是這樣寫的
    assert W.normalize_caption([]) == ([], 0) and W.normalize_caption([plain('LFT')]) == ([plain('LFT')], 0)
    assert W.audit_caption([plain('❌'), plain('LFT ❌')]) == [{'kind': 'multi', 'url': '', 'text': '❌LFT ❌', 'count': 2}]
    assert W.audit_caption([plain('LFT'), plain('❌')]) == [] and W.audit_caption([]) == []

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

# ---- 改名寫回前的保險(2026-11-05) ----
def test_screen_renames():
    rn = lambda pid, old, new: {'pid': pid, 'old': old, 'new': new, 'platform': 'lofter', 'nos': ['1', '2']}
    ok, held = W.screen_renames([rn('a', '咸魚', '咸鱼'), rn('b', '百憂解', '百忧解'), rn('c', '一只大鹅', '上-一只大鹅'),
                                 rn('d', '舊', '新筆名'), rn('e', 'X', 'Y1'), rn('e', 'X', 'Y2')])
    assert [r['pid'] for r in ok] == ['d']
    assert sorted(r['pid'] for r in held) == ['a', 'b', 'c', 'e', 'e']
    assert all(r['why'] for r in held)
    assert '標題片段' in next(r for r in held if r['pid'] == 'c')['why']

def test_append_rename_manual(tmp_path):
    md = tmp_path / 'check_report.md'
    md.write_text('## 改名\n', encoding='utf-8')
    W.append_rename_manual(str(md), [{'pid': 'c', 'old': '一只大鹅', 'new': '上-一只大鹅', 'platform': 'lofter', 'nos': ['1', '2'], 'why': 'w'}])
    t = md.read_text(encoding='utf-8')
    assert t.startswith('## 改名\n') and '需人工確認' in t and '「上-一只大鹅」(No.1、2)' in t

def test_main_exclude_skips_listed_nos(tmp_path, monkeypatch, capsys):
    rep = {'date': '2026-11-06', 'renames': [],
           'new_dead': [{'no': '1347', 'url': 'https://a.lofter.com/post/1', 'name': 'x'}, {'no': '20', 'url': 'https://a.lofter.com/post/2', 'name': 'y'}],
           'revived': [{'no': '30', 'url': 'https://a.lofter.com/post/3', 'name': 'z'}]}
    p = tmp_path / 'check_report.json'
    p.write_text(json.dumps(rep, ensure_ascii=False), encoding='utf-8')
    seen = []
    monkeypatch.setattr(W, 'apply_link', lambda x, mode, go, manual: (seen.append((x['no'], mode, go)), 'done')[1])
    t = W.main(['--report', str(p), '--exclude', '1347, 30', '--go'])
    assert seen == [('20', 'mark', True)] and t == {'done': 1, 'skip': 0, 'fail': 0}
    assert '--exclude 跳過 2 筆:No.1347、30' in capsys.readouterr().out
    # 全部被排除 → 沒有要寫回的變更;--no 與 --exclude 同時給時取交集後再排除
    seen.clear()
    assert W.main(['--report', str(p), '--exclude', '1347,20,30'])['done'] == 0 and seen == []
    assert W.main(['--report', str(p), '--no', '1347,20', '--exclude', '1347']) == {'done': 1, 'skip': 0, 'fail': 0}
    assert seen == [('20', 'mark', False)]

def test_main_holds_bad_renames_without_touching_notion(tmp_path, monkeypatch, capsys):
    rep = {'date': '2026-11-05', 'new_dead': [], 'revived': [],
           'renames': [{'pid': 'c', 'old': '咸魚', 'new': '咸鱼', 'platform': 'lofter', 'nos': ['1', '2']}]}
    p = tmp_path / 'check_report.json'
    p.write_text(__import__('json').dumps(rep, ensure_ascii=False), encoding='utf-8')
    monkeypatch.setattr(W, 'api', lambda *a, **k: (_ for _ in ()).throw(AssertionError('不該打 Notion')))
    t = W.main(['--report', str(p), '--go'])
    assert t == {'done': 0, 'skip': 1, 'fail': 0}
    assert '需人工確認' in (tmp_path / 'check_report.md').read_text(encoding='utf-8')

def test_apply_link_marks_and_unmarks_in_place(monkeypatch):
    """apply_link 走到 PATCH:段落連結之後插一段純文字 ❌;bookmark caption 放結尾;復活時舊寫法(前 / 連結文字內)也清得掉。"""
    blocks = {'B1': _blk('B1', 'PA', [plain('原文:'), link('LFT')]),
              'B2': _blk('B2', 'PA', [plain('❌'), link('LFT')]),
              'B5': _blk('B5', 'PA', [link('LFT❌')]),
              'B3': {'id': 'B3', 'type': 'bookmark', 'parent': {'type': 'page_id', 'page_id': 'PA'}, 'bookmark': {'url': URL, 'caption': [plain('LFT')]}}}
    monkeypatch.setattr(W, 'get_block', lambda bid: blocks[bid])
    patched = []
    monkeypatch.setattr(W, 'api', lambda m, path, body=None: patched.append((m, path, body)))
    base = {'url': URL, 'no': '276', 'title': 'T', 'label': 'LFT', 'page': 'PA'}
    assert W.apply_link(dict(base, block=['B1', 1]), 'mark', True) == 'done'
    rt = patched[-1][2]['paragraph']['rich_text']
    assert [x['text']['content'] for x in rt] == ['原文:', 'LFT', '❌'] and rt[1]['text']['link'] == {'url': URL} and rt[2]['text']['link'] is None
    assert W.apply_link(dict(base, block=['B2', 1]), 'mark', True) == 'skip'          # 舊寫法已標 → 不重複
    assert W.apply_link(dict(base, block=['B5', 0]), 'mark', True) == 'skip'
    assert W.apply_link(dict(base, block=['B5', 0]), 'unmark', True) == 'done'
    assert [x['text']['content'] for x in patched[-1][2]['paragraph']['rich_text']] == ['LFT']
    assert W.apply_link(dict(base, block=['B2', 1]), 'unmark', True) == 'done'
    assert [x['text']['content'] for x in patched[-1][2]['paragraph']['rich_text']] == ['LFT']
    assert W.apply_link(dict(base, block=['B3', -1]), 'mark', True) == 'done'
    assert [x['text']['content'] for x in patched[-1][2]['bookmark']['caption']] == ['LFT', '❌']

def test_normalize_all_scans_recorded_blocks_once(monkeypatch, capsys):
    """--normalize-x:同一 block 只讀一次、只改有變的、dry-run 不 PATCH、--no 只看那幾篇、讀不到就計失敗。"""
    pt = 'https://www.postype.com/@c/post/9'
    blocks = {'B1': _blk('B1', 'PA', [plain('❌'), link('LFT')]),                    # 舊格式,要改
              'B2': _blk('B2', 'PB', [link('PT', pt), plain(' / '), link('LFT')]),   # 沒標,不動
              'B3': _blk('B3', 'PC', [link('LFT'), plain('❌')]),                    # 已是現行格式
              'B4': {'id': 'B4', 'type': 'bookmark', 'parent': {'type': 'page_id', 'page_id': 'PD'}, 'bookmark': {'url': URL, 'caption': [plain('❌LFT')]}}}
    reads, patched = [], []
    def get_block(bid):
        reads.append(bid)
        if bid not in blocks: raise RuntimeError('404')
        return blocks[bid]
    monkeypatch.setattr(W, 'get_block', get_block)
    monkeypatch.setattr(W, 'api', lambda m, path, body=None: patched.append((m, path, body)))
    rec = {'276': {'page': 'PA', 'links': {URL: ['B1', 1]}},
           '10': {'page': 'PB', 'links': {pt: ['B2', 0], URL: ['B2', 2]}},
           '3': {'page': 'PC', 'links': {URL: ['B3', 0]}},
           '4': {'page': 'PD', 'links': {URL: ['B4', -1]}},
           '5': {'page': 'PE', 'links': {URL: ['B9', 0]}}}
    t = W.normalize_all(rec, False)
    assert reads == ['B3', 'B4', 'B9', 'B2', 'B1'] and patched == []                 # 依編號、B2 只讀一次
    assert t == {'blocks': 4, 'changed': 2, 'links': 2, 'fail': 1}
    out = capsys.readouterr().out
    assert '「❌LFT」→「LFT❌」(block B1)' in out and '「❌LFT」→「LFT❌」(block B4)' in out and '將改 2 個 block' in out and 'B9 讀不到' in out
    reads.clear()
    t = W.normalize_all(rec, True, only={'276', '3'})
    assert reads == ['B3', 'B1'] and t == {'blocks': 2, 'changed': 1, 'links': 1, 'fail': 0}
    assert len(patched) == 1 and patched[0][1] == 'blocks/B1' and [x['text']['content'] for x in patched[0][2]['paragraph']['rich_text']] == ['LFT', '❌']
    assert '已改 1 個 block' in capsys.readouterr().out

def test_audit_all_reads_only_and_tallies(monkeypatch, capsys):
    """--audit-x:只讀不寫(永遠不 PATCH),列出異常並依種類統計;正常 / 沒標 / 已封存的不報;讀不到計 fail。"""
    pt = 'https://www.postype.com/@c/post/9'
    blocks = {'B1': _blk('B1', 'PA', [link('LFT❌'), plain('❌')]),                   # multi + inside
              'B2': _blk('B2', 'PB', [link('PT', pt), plain(' / '), link('LFT')]),   # 沒標
              'B3': _blk('B3', 'PC', [link('LFT'), plain('❌')]),                    # 現行格式
              'B4': {'id': 'B4', 'type': 'bookmark', 'parent': {'type': 'page_id', 'page_id': 'PD'}, 'bookmark': {'url': URL, 'caption': [plain('❌'), plain('❌')]}},
              'B6': _blk('B6', 'PF', [link('❌')]),                                  # inside + only_x
              'B7': dict(_blk('B7', 'PG', [link('❌')]), archived=True)}
    reads, patched = [], []
    def get_block(bid):
        reads.append(bid)
        if bid not in blocks: raise RuntimeError('404')
        return blocks[bid]
    monkeypatch.setattr(W, 'get_block', get_block)
    monkeypatch.setattr(W, 'api', lambda *a, **k: patched.append(a))
    rec = {'276': {'page': 'PA', 'links': {URL: ['B1', 0]}},
           '10': {'page': 'PB', 'links': {pt: ['B2', 0], URL: ['B2', 2]}},
           '3': {'page': 'PC', 'links': {URL: ['B3', 0]}},
           '4': {'page': 'PD', 'links': {URL: ['B4', -1]}},
           '5': {'page': 'PE', 'links': {URL: ['B9', 0]}},
           '6': {'page': 'PF', 'links': {URL: ['B6', 0]}},
           '7': {'page': 'PG', 'links': {URL: ['B7', 0]}}}
    t = W.audit_all(rec)
    assert patched == [] and reads == ['B3', 'B4', 'B9', 'B6', 'B7', 'B2', 'B1']
    assert t == {'blocks': 6, 'issues': 5, 'fail': 1, 'by_kind': {'multi': 2, 'inside': 2, 'only_x': 1}}
    out = capsys.readouterr().out
    assert '只讀不寫' in out and 'No.276 同一連結超過一個 ❌:「LFT❌❌」 ' + URL + '(❌ ×2;block B1)' in out
    assert 'No.276 ❌ 在連結文字內' in out and 'No.6 連結文字只剩 ❌:「❌」' in out and 'No.4 同一連結超過一個 ❌:「❌❌」(❌ ×2;block B4)' in out
    assert 'No.3' not in out and 'No.10' not in out and 'No.7' not in out and 'B9 讀不到' in out
    assert '異常 5 筆(同一連結超過一個 ❌ 2、❌ 在連結文字內 2、連結文字只剩 ❌ 1),讀不到 1' in out
    reads.clear()
    assert W.audit_all(rec, only={'3', '6'}) == {'blocks': 2, 'issues': 2, 'fail': 0, 'by_kind': {'multi': 0, 'inside': 1, 'only_x': 1}}
    assert reads == ['B3', 'B6'] and patched == []

def test_main_normalize_x_reads_blocks_not_report(tmp_path, monkeypatch):
    lk = tmp_path / 'article_links.json'
    lk.write_text(json.dumps({'276': {'T': [['❌LFT', URL]]}, '__edited__': {}, '__blocks__': {'276': {'page': 'PA', 'links': {URL: ['B1', 1]}}}}, ensure_ascii=False), encoding='utf-8')
    calls = []
    monkeypatch.setattr(W, 'normalize_all', lambda blocks, go, only=None, sleep=None: (calls.append((blocks, go, only)), {'changed': 0})[1])
    assert W.main(['--normalize-x', '--links', str(lk), '--no', '276'])['changed'] == 0            # 不需要 check_report.json
    assert calls == [({'276': {'page': 'PA', 'links': {URL: ['B1', 1]}}}, False, {'276'})]
    W.main(['--normalize-x', '--links', str(lk), '--go'])
    assert calls[-1][1] is True and calls[-1][2] == set()
    with pytest.raises(SystemExit):
        W.main(['--normalize-x', '--links', str(tmp_path / 'nope.json')])
    # --audit-x 走 audit_all(同一份 __blocks__、--no 照用),--go 也不會寫
    audits = []
    monkeypatch.setattr(W, 'audit_all', lambda blocks, only=None: (audits.append((blocks, only)), {'issues': 0})[1])
    assert W.main(['--audit-x', '--links', str(lk), '--no', '276', '--go'])['issues'] == 0
    assert audits == [({'276': {'page': 'PA', 'links': {URL: ['B1', 1]}}}, {'276'})] and len(calls) == 2
    with pytest.raises(SystemExit):
        W.main(['--audit-x', '--links', str(tmp_path / 'nope.json')])
