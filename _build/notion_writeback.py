# -*- coding: utf-8 -*-
"""巡檢 ②:把 check_links.py 的結果寫回 Notion(資料的唯一源頭;網站下次 sync 自然更新)。
   預設 dry-run 只印將變更的清單,加 --go 才真的寫(與 notion_fill.py 的習慣一致)。只用標準庫。

   死連結:更新該作品頁面內文裡那個連結 block 的 rich_text,在連結段**之後插入一段獨立的純文字「❌」**(不帶連結、連結文字維持原樣:
           [LFT](url)❌,與站長手標的慣例一致;2026-11-06 以前本腳本先是插在連結前面、後來改寫進連結文字結尾「LFT❌」,都是舊格式);
           復活就移除 ❌:連結後緊鄰的純文字 ❌,也相容兩種舊格式(連結文字內的、連結前緊鄰純文字段結尾的)都拿掉。
           「已標」的判定(is_marked)三種位置都算。build_site.py / check_links.py 看的是 fetch_data.block_links 給的標籤
           (整個 block 的文字),三種位置的 ❌ 都在裡面,所以既有的 dead 判定不用改。
   --normalize-x:一次性整理,掃 article_links.json __blocks__ 記錄的所有連結 block,把所有舊格式(連結前的純文字 ❌、連結文字內的 ❌)
           統一成「連結後緊鄰一個純文字 ❌」,連結文字還原成不含 ❌、一條連結只留一個 ❌;印出改了幾筆;預設 dry-run、--go 才寫。
           bookmark / embed 的 caption 統一成結尾一段「❌」、只留一個。
   --audit-x:只讀不寫,列出 ❌ 的異常:同一連結超過一個 ❌、❌ 在連結文字內、連結文字只剩 ❌(audit_marks / audit_caption),
           給站長在 --normalize-x 之前 / 之後核對用。
           block 位置**只用** article_links.json 的 __blocks__(fetch_data.py 記錄),而且 block 的父頁面、網址都要對得上;
           對不上就跳過、附到 Issue 內文「需人工確認」段,絕不拿網址去別的頁面搜尋後亂寫(article_links.json 曾經把別篇的連結留在錯的 No 底下)。
   作者改名:作者庫該頁「作者名稱」title 改成新名字;「曾用名」multi_select(不存在就用 database update API 建立)
           加入舊名字(不刪、不重複;Notion 選項名不能有半形逗號 → 換成全形)。只處理 check_links 列在 renames 的
           (作者庫平台網址核對過的),rename_candidates 不動。寫之前再讀一次作者頁,title 跟報告的舊名不同就跳過。
           寫回前再過一道保險(screen_renames,與 check_links.rename_hold_reason 同一套):新舊名只差簡繁(stmap 折算後相同)、
           新名字含標題片段(上- / 下- / 番外 / 第N章…)、或同一位作者報告裡有兩個以上不同新名字 → 不寫,附到 Issue「需人工確認」。
   用法:python notion_writeback.py [--go] [--report check_report.json] [--no 1352] [--limit N]
         python notion_writeback.py --normalize-x [--go] [--no 276,1352](不讀報告;只掃 __blocks__)
         python notion_writeback.py --audit-x [--no 276,1352](只讀不寫;列出 ❌ 異常)
         token 來源同 fetch_data.py(NOTION_TOKEN → notion_token.txt → 交給代理)。"""
import argparse, copy, io, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as FD
import check_links as CL

DEAD_MARK = '❌'
API = 'https://api.notion.com/v1/'
ALIAS_PROP = '曾用名'
TEXT_TYPES = ('paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item', 'numbered_list_item',
              'quote', 'callout', 'toggle', 'to_do')
CAPTION_TYPES = ('bookmark', 'embed')

# ---------- rich_text 純函式(pytest 測這些) ----------

def _plain_seg(text):
    return {'type': 'text', 'text': {'content': text, 'link': None}, 'plain_text': text, 'href': None,
            'annotations': {'bold': False, 'italic': False, 'strikethrough': False, 'underline': False,
                            'code': False, 'color': 'default'}}

def _seg_text(seg):
    if seg.get('type') == 'text':
        return (seg.get('text') or {}).get('content', '')
    return seg.get('plain_text', '')

def _set_seg_text(seg, s):
    if seg.get('type') == 'text':
        seg.setdefault('text', {})['content'] = s
    seg['plain_text'] = s

def _href(seg):
    if seg.get('type') == 'text':
        lk = (seg.get('text') or {}).get('link')
        if lk and lk.get('url'):
            return lk['url']
    return seg.get('href') or ''

def find_link_index(rts, url, hint=None):
    """rich_text 裡 href == url 的段落位置;hint 對就用 hint,否則全掃;找不到回 -1。"""
    if hint is not None and 0 <= hint < len(rts) and _href(rts[hint]) == url:
        return hint
    for i, seg in enumerate(rts):
        if _href(seg) == url:
            return i
    return -1

_LEAD = re.compile(r'^[\s❌]+')     # 文字開頭的「❌ / 空白」連續段
_TRAIL = re.compile(r'[\s❌]+$')    # 文字結尾的「❌ / 空白」連續段

def _has_lead(s):
    """開頭(只隔空白)就是 ❌。"""
    m = _LEAD.match(s or '')
    return bool(m and DEAD_MARK in m.group(0))

def _has_trail(s):
    """結尾(只隔空白)就是 ❌。"""
    m = _TRAIL.search(s or '')
    return bool(m and DEAD_MARK in m.group(0))

def _strip_lead(s):
    """拿掉開頭連續段裡的 ❌(空白照舊)。"""
    return _LEAD.sub(lambda m: m.group(0).replace(DEAD_MARK, ''), s or '', count=1)

def _strip_trail(s):
    return _TRAIL.sub(lambda m: m.group(0).replace(DEAD_MARK, ''), s or '', count=1)

def _count_lead(s):
    """開頭連續段(只隔空白)裡有幾個 ❌。"""
    m = _LEAD.match(s or '')
    return m.group(0).count(DEAD_MARK) if m else 0

def _count_trail(s):
    m = _TRAIL.search(s or '')
    return m.group(0).count(DEAD_MARK) if m else 0

def _strip_all(s):
    """拿掉文字裡所有 ❌;開頭 / 結尾那段連帶的空白也去掉(「❌ LFT」→「LFT」),中間的空白照舊。"""
    s = s or ''
    if _has_lead(s):
        s = _strip_lead(s).lstrip()
    if _has_trail(s):
        s = _strip_trail(s).rstrip()
    return s.replace(DEAD_MARK, '')

def _dedupe_lead(s):
    """開頭連續段裡只留第一個 ❌(空白照舊、其餘的 ❌ 拿掉)。"""
    m = _LEAD.match(s or '')
    if not m:
        return s
    keep, seen = [], False
    for ch in m.group(0):
        if ch == DEAD_MARK:
            if seen:
                continue
            seen = True
        keep.append(ch)
    return ''.join(keep) + s[m.end():]

def _plain_at(rts, j):
    """rts[j] 存在且是純文字段(沒有連結)才回傳它,否則 None。"""
    return rts[j] if 0 <= j < len(rts) and not _href(rts[j]) else None

def _editable(seg):
    """這段的文字可以改寫回去:一般文字、或 to_api_rich_text 會退化成文字的 link_mention / link_preview;
    page / database / user / date 的 mention 文字是 Notion 自己算的,寫回也不會留。"""
    if seg.get('type') != 'mention':
        return True
    return (seg.get('mention') or {}).get('type') not in ('page', 'database', 'user', 'date')

def _prev_owned_by_link(rts, idx):
    """緊鄰前一段純文字整段只有 ❌ / 空白、而它前面又是另一條連結([A](a)❌[B](b) 的 B):那個 ❌ 是 A 後面的(現行格式),不算 B 的。"""
    prev = _plain_at(rts, idx - 1)
    if prev is None or idx - 2 < 0 or not _href(rts[idx - 2]):
        return False
    s = _seg_text(prev)
    m = _LEAD.match(s)
    return bool(m and m.end() == len(s) and DEAD_MARK in s)

def _mark_counts(rts, idx):
    """這條連結三種位置各有幾個 ❌:(緊鄰前一段純文字結尾, 連結文字內, 緊鄰後一段純文字開頭);
    前一段的 ❌ 若屬於再前一條連結(_prev_owned_by_link)就不算。"""
    prev, nxt = _plain_at(rts, idx - 1), _plain_at(rts, idx + 1)
    return (_count_trail(_seg_text(prev)) if prev and not _prev_owned_by_link(rts, idx) else 0,
            _seg_text(rts[idx]).count(DEAD_MARK),
            _count_lead(_seg_text(nxt)) if nxt else 0)

def is_marked(rts, idx):
    """這條連結已標 ❌,三種位置都算:緊鄰後一段純文字的**開頭**是 ❌(站長手標慣例 [LFT](url)❌、本腳本現在的寫法)、
    連結文字本身含 ❌(舊格式「LFT❌」「❌LFT」)、緊鄰前一段純文字的**結尾**是 ❌(更舊的寫法「❌」+ 連結)。
    鄰段中間的 ❌(例如屬於另一條連結的)不算;[A](a)❌[B](b) 中間那個是 A 的、B 沒標。"""
    return any(_mark_counts(rts, idx))

def mark_dead(rts, idx):
    """在連結段之後插入一段獨立的純文字「❌」(不帶連結;連結文字維持原樣:[LFT](url)❌);已標過(不分位置)就原樣回傳。
    回傳 (新 rich_text, 是否有改)。"""
    if is_marked(rts, idx):
        return rts, False
    out = copy.deepcopy(rts)
    out.insert(idx + 1, _plain_seg(DEAD_MARK))
    return out, True

def unmark_dead(rts, idx, url=''):
    """移除這條連結的 ❌:連結後緊鄰純文字開頭的(現行格式),也相容舊格式:連結文字裡的全部、緊鄰前一段結尾的
    (鄰段被清空就整段拿掉;前一段的 ❌ 屬於再前一條連結的不動)。連結文字被清空時改用網址當文字(Notion 不收空的連結段)。
    回傳 (新 rich_text, 是否有改)。"""
    out, changed, drop = copy.deepcopy(rts), False, set()
    s = _seg_text(out[idx])
    if DEAD_MARK in s:
        s2 = _strip_all(s)
        _set_seg_text(out[idx], s2 if s2.strip() else (url or _href(out[idx]) or s2))
        changed = True
    for j, strip, has in ((idx - 1, _strip_trail, _has_trail), (idx + 1, _strip_lead, _has_lead)):
        seg = _plain_at(out, j)
        if j < idx and _prev_owned_by_link(out, idx):
            continue
        if seg is not None and has(_seg_text(seg)):
            s2 = strip(_seg_text(seg))
            _set_seg_text(seg, s2)
            changed = True
            if s2.strip() == '':
                drop.add(j)
    return [seg for j, seg in enumerate(out) if j not in drop], changed

def normalize_marks(rts):
    """--normalize-x 用:把每條連結的 ❌ 統一成「連結後緊鄰一個純文字 ❌」:連結前(緊鄰前一段結尾)的、連結文字內的(任何位置)都拿掉,
    連結文字還原成不含 ❌(只剩 ❌ 的用網址當文字),連結後已有的只留一個、沒有就插入一段「❌」。
    已經是「後面剛好一個、其他位置沒有」的不動。有沒有標以**原本**的 rich_text 為準([A](a)❌[B](b) 中間那個是 A 的、B 不算,
    所以統一後的結果再跑一次是 0 筆);從後往前處理,插入 / 清空的段用物件身分追蹤。
    回傳 (新 rich_text, 改了幾條連結)。純函式。"""
    out, moved, drop = copy.deepcopy(rts), 0, set()
    orig = {id(seg): _mark_counts(out, i) for i, seg in enumerate(out) if _href(seg)}
    for i in range(len(out) - 1, -1, -1):
        seg = out[i]
        if not _href(seg) or not _editable(seg):
            continue
        n_prev, n_in, _ = orig[id(seg)]
        if not any(orig[id(seg)]):
            continue
        changed = False
        prev = _plain_at(out, i - 1)
        if n_prev and prev is not None and _has_trail(_seg_text(prev)):
            p2 = _strip_trail(_seg_text(prev))
            _set_seg_text(prev, p2)
            if p2.strip() == '':
                drop.add(id(prev))
            changed = True
        if n_in:
            s2 = _strip_all(_seg_text(seg))
            _set_seg_text(seg, s2 if s2.strip() else _href(seg))
            changed = True
        nxt = _plain_at(out, i + 1)
        live_next = _count_lead(_seg_text(nxt)) if nxt is not None else 0
        if live_next > 1:
            _set_seg_text(nxt, _dedupe_lead(_seg_text(nxt)))
            changed = True
        elif live_next == 0:
            out.insert(i + 1, _plain_seg(DEAD_MARK))
            changed = True
        if changed:
            moved += 1
    return [seg for seg in out if id(seg) not in drop], moved

AUDIT_KINDS = (('multi', '同一連結超過一個 ❌'), ('inside', '❌ 在連結文字內'), ('only_x', '連結文字只剩 ❌'))

def audit_marks(rts):
    """--audit-x 用:這段 rich_text 裡每條連結的 ❌ 異常 → [{kind, url, text, count}, ...];kind 見 AUDIT_KINDS
    (multi = 三種位置加起來超過一個;inside = 連結文字內有 ❌;only_x = 連結文字去掉 ❌ 與空白後是空的)。純函式、不改資料。"""
    found = []
    for i, seg in enumerate(rts or []):
        if not _href(seg):
            continue
        s = _seg_text(seg)
        n = sum(_mark_counts(rts, i))
        kinds = []
        if n > 1:
            kinds.append('multi')
        if DEAD_MARK in s:
            kinds.append('inside')
            if not s.replace(DEAD_MARK, '').strip():
                kinds.append('only_x')
        found.extend({'kind': k, 'url': _href(seg), 'text': s, 'count': n} for k in kinds)
    return found

# bookmark / embed 沒有 rich_text,❌ 放在 caption(整段文字就是連結名稱)
def caption_marked(rts):
    return any(DEAD_MARK in _seg_text(s) for s in rts or [])

def mark_caption(rts):
    """caption 結尾加一段「❌」;已有就不動。"""
    if caption_marked(rts):
        return rts, False
    return copy.deepcopy(rts or []) + [_plain_seg(DEAD_MARK)], True

def unmark_caption(rts):
    """拿掉 caption 裡所有 ❌(清空的段整段拿掉)。"""
    out, changed = [], False
    for seg in rts or []:
        s = _seg_text(seg)
        if DEAD_MARK in s:
            changed = True
            s = s.replace(DEAD_MARK, '')
            if s.strip() == '':
                continue
            seg = copy.deepcopy(seg); _set_seg_text(seg, s)
        out.append(seg)
    return out, changed

def normalize_caption(rts):
    """caption 裡的 ❌ 統一成結尾一段獨立的「❌」、只留一個(其餘位置的拿掉,清空的段整段拿掉)。回傳 (新 caption, 0 或 1)。"""
    if not caption_marked(rts):
        return rts, 0
    out, _ = unmark_caption(rts)
    out.append(_plain_seg(DEAD_MARK))
    if [_seg_text(x) for x in out] == [_seg_text(x) for x in rts]:
        return rts, 0
    return out, 1

def audit_caption(rts):
    """--audit-x 用:caption 裡超過一個 ❌ → [{kind:'multi', …}];bookmark / embed 沒有連結文字,其他兩種異常不適用。"""
    n = sum(_seg_text(x).count(DEAD_MARK) for x in rts or [])
    return [{'kind': 'multi', 'url': '', 'text': ''.join(_seg_text(x) for x in rts or []), 'count': n}] if n > 1 else []

def to_api_rich_text(rts):
    """GET 回來的 rich_text → 可以 PATCH 回去的格式(拿掉唯讀欄位 plain_text / href)。"""
    out = []
    for seg in rts:
        t = seg.get('type', 'text')
        item = {'type': t, 'annotations': seg.get('annotations') or {}}
        if t == 'text':
            tx = seg.get('text') or {}
            item['text'] = {'content': tx.get('content', ''), 'link': ({'url': tx['link']['url']} if tx.get('link') and tx['link'].get('url') else None)}
        elif t == 'mention':
            m = seg.get('mention') or {}
            mt = m.get('type')
            if mt in ('page', 'database', 'user', 'date'):
                item['mention'] = {mt: m.get(mt)}
            else:   # link_preview / link_mention 等 API 不能回寫的 → 退化成一般連結文字
                item = {'type': 'text', 'annotations': seg.get('annotations') or {},
                        'text': {'content': seg.get('plain_text', ''), 'link': ({'url': seg['href']} if seg.get('href') else None)}}
        elif t == 'equation':
            item['equation'] = seg.get('equation') or {'expression': seg.get('plain_text', '')}
        else:
            item = {'type': 'text', 'annotations': seg.get('annotations') or {},
                    'text': {'content': seg.get('plain_text', ''), 'link': None}}
        out.append(item)
    return out

def alias_option_name(name):
    """multi_select 選項名不能含半形逗號 → 全形;並去頭尾空白、限 100 字。"""
    return (name or '').replace(',', '，').strip()[:100]

def merged_aliases(existing, old_name):
    """既有曾用名 + 舊名(不重複、不刪)。"""
    out = [x for x in existing if x]
    cand = alias_option_name(old_name)
    if cand and cand not in out:
        out.append(cand)
    return out

# ---------- Notion 存取 ----------

def api(method, path, body=None):
    return FD.api(method, API + path, body)

def get_block(block_id):
    return api('GET', 'blocks/%s' % block_id)

def rich_text_of(block):
    t = block['type']; bd = block.get(t, {})
    if t in CAPTION_TYPES:
        return 'caption', bd.get('caption', [])
    return 'rich_text', bd.get('rich_text', [])

def locate(item):
    """報告裡的一筆連結 → ((block, field, rich_text, idx), '') ;對不上就回 (None, 原因)。
    **只信 article_links.json 記錄的 block 位置**(fetch_data.py 抓該篇頁面時記下的 __blocks__),而且 block 的父頁面要等於
    記錄的頁面 ID、block 裡要真的有這個網址。不拿網址去整頁重掃、也不用 No 查主表:article_links.json 曾把別篇的連結留在
    錯的 No 底下(2026-10-31 的 No.786 / No.10047),那種情況去別的頁面找只會把 ❌ 寫到不相干的地方。
    對不上就跳過,由 main() 附到 Issue「需人工確認」。"""
    url, pos = item['url'], item.get('block')
    if not pos:
        return None, '沒有 block 位置(article_links.json 的 __blocks__ 沒記到這條連結)'
    try:
        blk = get_block(pos[0])
    except Exception as e:
        return None, 'block %s 讀不到:%s' % (pos[0], e)
    if blk.get('archived') or blk.get('in_trash'):
        return None, 'block %s 已封存' % pos[0]
    parent = ((blk.get('parent') or {}).get('page_id') or '').replace('-', '')
    if item.get('page') and parent and parent != item['page']:
        return None, 'block %s 不在記錄的頁面 %s 底下(在 %s)' % (pos[0], item['page'], parent)
    field, rts = rich_text_of(blk)
    idx = find_link_index(rts, url, pos[1] if len(pos) > 1 else None)
    if idx >= 0 or (blk['type'] in CAPTION_TYPES and blk[blk['type']].get('url') == url):
        return (blk, field, rts, idx), ''
    return None, 'block %s 裡沒有這個網址' % pos[0]

def apply_link(item, action, go, manual=None):
    """action: 'mark' | 'unmark'。回傳 'done' | 'skip' | 'fail'。
    找不到 block 就跳過、附進 manual(main() 寫進 Issue「需人工確認」),絕不改去別的頁面找。"""
    found, why = locate(item)
    tag = 'No.%s《%s》%s' % (item['no'], item['title'], item['label'].replace(DEAD_MARK, '').strip())
    if not found:
        print('   ⚠️ 找不到連結 block,跳過(需人工確認):%s %s — %s' % (tag, item['url'], why))
        if manual is not None:
            manual.append(dict(item, action=action, why=why))
        return 'fail'
    blk, field, rts, idx = found
    if idx < 0:   # bookmark / embed 沒有 rich_text:❌ 放 caption 結尾
        rts = rts or []
        new, changed = mark_caption(rts) if action == 'mark' else unmark_caption(rts)
    else:
        new, changed = mark_dead(rts, idx) if action == 'mark' else unmark_dead(rts, idx, item['url'])
    if not changed:
        print('   = 已是目標狀態,不動:%s' % tag)
        return 'skip'
    before = ''.join(_seg_text(s) for s in rts)
    after = ''.join(_seg_text(s) for s in new)
    print('   %s %s:「%s」→「%s」(block %s)' % ('❌' if action == 'mark' else '♻️', tag, before, after, blk['id'].replace('-', '')))
    if not go:
        return 'done'
    try:
        api('PATCH', 'blocks/%s' % blk['id'], {blk['type']: {field: to_api_rich_text(new)}})
        return 'done'
    except Exception as e:
        print('   ⚠️ 寫入失敗:%s %s' % (tag, e))
        return 'fail'

def manual_markdown(items):
    """Issue 內文的「需人工確認」段:寫回時找不到 block 而跳過的連結(給站長手動標 ❌ / 移除 ❌)。"""
    L = ['', '### 需人工確認(找不到連結 block,未寫回 Notion;請手動%s)' % ' / '.join(
        sorted({'標 ❌' if x['action'] == 'mark' else '移除 ❌' for x in items}, reverse=True))]
    for x in items:
        L.append('- %s No.%s《%s》%s — %s;%s' % ('標 ❌' if x['action'] == 'mark' else '移除 ❌', x['no'], x['title'],
                                               x['label'].replace(DEAD_MARK, '').strip(), x['url'], x['why']))
    return '\n'.join(L) + '\n'

def append_manual_section(md_path, items):
    """把跳過的連結附到 check_links.py 產的 Issue 內文(check_report.md)末尾;檔案不存在就建立。"""
    if not items:
        return
    old = io.open(md_path, encoding='utf-8').read() if os.path.exists(md_path) else ''
    io.open(md_path, 'w', encoding='utf-8').write(old.rstrip('\n') + '\n' + manual_markdown(items))

def screen_renames(renames):
    """改名寫回前的保險 → (可以寫的, 擋下的);擋下的元素多一個 why。純函式。"""
    news = {}
    for r in renames:
        news.setdefault(r['pid'], set()).add(CL.norm_name(r['new']))
    ok, held = [], []
    for r in renames:
        why = ('同一位作者有 %d 個不同的新名字,可能抓錯來源' % len(news[r['pid']]) if len(news[r['pid']]) > 1
               else CL.rename_hold_reason(r['old'], r['new']))
        (held if why else ok).append(dict(r, why=why) if why else r)
    return ok, held

def append_rename_manual(md_path, items):
    """把擋下的改名附到 Issue 內文(check_report.md)末尾。"""
    if not items:
        return
    old = io.open(md_path, encoding='utf-8').read() if os.path.exists(md_path) else ''
    io.open(md_path, 'w', encoding='utf-8').write(old.rstrip('\n') + '\n' + '\n'.join(CL.rename_manual_lines(items)) + '\n')

def find_authors_db():
    dbs = api('POST', 'search', {'filter': {'property': 'object', 'value': 'database'}, 'page_size': 50})['results']
    for db in dbs:
        if '作者名稱' in db.get('properties', {}):
            return db
    return None

def ensure_alias_prop(db, go):
    if ALIAS_PROP in db.get('properties', {}):
        if db['properties'][ALIAS_PROP]['type'] != 'multi_select':
            print('   ⚠️ 作者庫的「%s」不是 multi_select,改名不寫曾用名' % ALIAS_PROP)
            return False
        return True
    print('   + 作者庫沒有「%s」欄,%s建立(multi_select)' % (ALIAS_PROP, '將' if not go else ''))
    if go:
        api('PATCH', 'databases/%s' % db['id'], {'properties': {ALIAS_PROP: {'multi_select': {'options': []}}}})
    return True

def apply_rename(r, has_alias_prop, go):
    pg = api('GET', 'pages/%s' % r['pid'])
    cur = FD.p_title(FD.p(pg, '作者名稱'))
    if cur != r['old']:
        print('   = 跳過:作者頁目前名稱「%s」≠ 報告舊名「%s」(已被改過?)' % (cur, r['old']))
        return 'skip'
    if cur == r['new']:
        return 'skip'
    existing = [o['name'] for o in (FD.p(pg, ALIAS_PROP) or {}).get('multi_select', [])] if has_alias_prop else []
    aliases = merged_aliases(existing, r['old'])
    print('   ✏️ %s → %s(%s;No.%s);曾用名:%s' % (r['old'], r['new'], r['platform'], '、'.join(r['nos']), '、'.join(aliases)))
    if not go:
        return 'done'
    props = {'作者名稱': {'title': [{'type': 'text', 'text': {'content': r['new']}}]}}
    if has_alias_prop:
        props[ALIAS_PROP] = {'multi_select': [{'name': a} for a in aliases]}
    try:
        api('PATCH', 'pages/%s' % r['pid'], {'properties': props})
        return 'done'
    except Exception as e:
        print('   ⚠️ 改名寫入失敗:%s' % e)
        return 'fail'

def recorded_blocks(blocks, only=None):
    """article_links.json __blocks__ → [(no, block_id)]:依編號、同一 block 只列一次(--normalize-x / --audit-x 共用)。"""
    order, seen = [], set()
    for no in sorted((n for n in blocks if not n.startswith('__')), key=lambda n: (len(n), n)):
        if only and no not in only:
            continue
        for url, pos in ((blocks.get(no) or {}).get('links') or {}).items():
            if pos and pos[0] not in seen:
                seen.add(pos[0]); order.append((no, pos[0]))
    return order

def normalize_all(blocks, go, only=None, sleep=lambda s: None):
    """--normalize-x:掃 article_links.json __blocks__ 記錄的每個連結 block(同一 block 只讀一次),
    把每條連結的 ❌ 統一成「連結後緊鄰一個純文字 ❌」(normalize_marks / normalize_caption);go=False 只印。
    回傳 {'blocks': 看過的 block 數, 'changed': 改了的 block 數, 'links': 改了的連結數, 'fail': 讀 / 寫失敗數}。"""
    order = recorded_blocks(blocks, only)
    tally = {'blocks': 0, 'changed': 0, 'links': 0, 'fail': 0}
    print('--normalize-x:%s;%d 個 block 要看' % ('寫入 Notion(--go)' if go else 'dry-run(只印;加 --go 才寫)', len(order)))
    for k, (no, bid) in enumerate(order, 1):
        try:
            blk = get_block(bid)
        except Exception as e:
            print('   ⚠️ No.%s block %s 讀不到:%s' % (no, bid, e)); tally['fail'] += 1; continue
        tally['blocks'] += 1
        if blk.get('archived') or blk.get('in_trash'):
            continue
        field, rts = rich_text_of(blk)
        new, n = normalize_caption(rts) if field == 'caption' else normalize_marks(rts)
        if not n:
            if k % 100 == 0:
                print('   … %d / %d' % (k, len(order)))
            continue
        print('   🔁 No.%s:「%s」→「%s」(block %s)' % (no, ''.join(_seg_text(s) for s in rts), ''.join(_seg_text(s) for s in new), bid))
        if go:
            try:
                api('PATCH', 'blocks/%s' % blk['id'], {blk['type']: {field: to_api_rich_text(new)}})
            except Exception as e:
                print('   ⚠️ 寫入失敗:No.%s block %s:%s' % (no, bid, e)); tally['fail'] += 1; continue
        tally['changed'] += 1; tally['links'] += n
        sleep(0.34)
    print('完成:%s %d 個 block(%d 條連結的 ❌ 統一成連結後一個純文字 ❌),看過 %d 個 block,失敗 %d'
          % ('已改' if go else '將改', tally['changed'], tally['links'], tally['blocks'], tally['fail']))
    return tally

def audit_all(blocks, only=None):
    """--audit-x:只讀不寫。掃 __blocks__ 記錄的每個連結 block,列出 ❌ 異常(audit_marks / audit_caption),最後依種類統計。
    回傳 {'blocks': 看過的 block 數, 'issues': 異常筆數, 'fail': 讀失敗數, 'by_kind': {kind: 筆數}}。"""
    order = recorded_blocks(blocks, only)
    labels = dict(AUDIT_KINDS)
    tally = {'blocks': 0, 'issues': 0, 'fail': 0, 'by_kind': {k: 0 for k, _ in AUDIT_KINDS}}
    print('--audit-x:只讀不寫;%d 個 block 要看(%s)' % (len(order), ' / '.join(v for _, v in AUDIT_KINDS)))
    for no, bid in order:
        try:
            blk = get_block(bid)
        except Exception as e:
            print('   ⚠️ No.%s block %s 讀不到:%s' % (no, bid, e)); tally['fail'] += 1; continue
        tally['blocks'] += 1
        if blk.get('archived') or blk.get('in_trash'):
            continue
        field, rts = rich_text_of(blk)
        for x in (audit_caption(rts) if field == 'caption' else audit_marks(rts)):
            tally['issues'] += 1; tally['by_kind'][x['kind']] += 1
            print('   ⚠️ No.%s %s:「%s」%s(❌ ×%d;block %s)' % (
                no, labels[x['kind']], ''.join(_seg_text(s) for s in rts), (' ' + x['url']) if x['url'] else '', x['count'], bid))
    print('完成:看過 %d 個 block,異常 %d 筆(%s),讀不到 %d' % (
        tally['blocks'], tally['issues'], '、'.join('%s %d' % (labels[k], tally['by_kind'][k]) for k, _ in AUDIT_KINDS), tally['fail']))
    return tally

def main(argv=None):
    ap = argparse.ArgumentParser(description='把巡檢結果寫回 Notion(預設 dry-run)')
    ap.add_argument('--go', action='store_true', help='真的寫入 Notion(不加 = 只印清單)')
    ap.add_argument('--normalize-x', action='store_true', help='一次性整理:掃所有連結 block,把舊格式的 ❌ 統一成連結後一個純文字 ❌(不讀報告)')
    ap.add_argument('--audit-x', action='store_true', help='只讀不寫:列出 ❌ 異常(同一連結超過一個 / 在連結文字內 / 連結文字只剩 ❌)')
    ap.add_argument('--links', default='article_links.json', help='--normalize-x / --audit-x 讀的 article_links.json(用它的 __blocks__)')
    ap.add_argument('--report', default='check_report.json')
    ap.add_argument('--no', default='', help='只處理這些編號(逗號分隔;測試用)')
    ap.add_argument('--exclude', default='', help='跳過這些編號的 ❌ 標記 / 移除(逗號分隔;誤判時用。作者改名是作者層級,不受影響)')
    ap.add_argument('--limit', type=int, default=0, help='死 / 復活各最多處理幾筆(測試用)')
    ap.add_argument('--skip-renames', action='store_true')
    args = ap.parse_args(argv)
    only = set(x.strip() for x in args.no.split(',') if x.strip())
    if args.normalize_x or args.audit_x:
        try:
            blocks = json.load(io.open(args.links, encoding='utf-8')).get('__blocks__') or {}
        except Exception as e:
            raise SystemExit('讀不到 %s(先跑 fetch_data.py):%s' % (args.links, e))
        if args.audit_x:
            return audit_all(blocks, only)
        return normalize_all(blocks, args.go, only, sleep=time.sleep)
    try:
        rep = json.load(io.open(args.report, encoding='utf-8'))
    except Exception as e:
        raise SystemExit('讀不到 %s(先跑 check_links.py):%s' % (args.report, e))
    exclude = set(x.strip() for x in args.exclude.split(',') if x.strip())
    pick = lambda lst: [x for x in lst if (not only or x['no'] in only) and x['no'] not in exclude][:args.limit or None]
    dead, revived = pick(rep.get('new_dead', [])), pick(rep.get('revived', []))
    renames = [] if args.skip_renames or only else rep.get('renames', [])
    mode = '寫入 Notion(--go)' if args.go else 'dry-run(只印清單;加 --go 才寫)'
    print('notion_writeback %s:%s' % (rep.get('date', ''), mode))
    skipped = [x['no'] for lst in (rep.get('new_dead', []), rep.get('revived', [])) for x in lst if x['no'] in exclude]
    if skipped:
        print('— --exclude 跳過 %d 筆:No.%s' % (len(skipped), '、'.join(skipped)))
    if not (dead or revived or renames):
        print('沒有要寫回的變更。')
        return {'done': 0, 'skip': 0, 'fail': 0}
    tally, manual = {'done': 0, 'skip': 0, 'fail': 0}, []
    if dead:
        print('— 標 ❌(新死 %d 筆)' % len(dead))
        for x in dead:
            tally[apply_link(x, 'mark', args.go, manual)] += 1
    if revived:
        print('— 移除 ❌(復活 %d 筆)' % len(revived))
        for x in revived:
            tally[apply_link(x, 'unmark', args.go, manual)] += 1
    if manual and args.go:
        md_path = os.path.join(os.path.dirname(args.report) or '.', 'check_report.md')
        append_manual_section(md_path, manual)
        print('   ↳ %d 筆找不到 block,已附到 %s「需人工確認」' % (len(manual), md_path))
    renames, held = screen_renames(renames)
    for r in held:
        print('   ✋ 不寫回(需人工確認):%s → %s(%s)— %s' % (r['old'], r['new'], r['platform'], r['why']))
        tally['skip'] += 1
    if held and args.go:
        md_path = os.path.join(os.path.dirname(args.report) or '.', 'check_report.md')
        append_rename_manual(md_path, held)
        print('   ↳ %d 筆改名已附到 %s「需人工確認」' % (len(held), md_path))
    if renames:
        print('— 作者改名(%d 位)' % len(renames))
        db = find_authors_db()
        if not db:
            print('   ⚠️ 找不到作者庫,改名全部略過')
            tally['fail'] += len(renames)
        else:
            has_alias = ensure_alias_prop(db, args.go)
            for r in renames:
                tally[apply_rename(r, has_alias, args.go)] += 1
    print('完成:%s %d、略過 %d、失敗 %d' % ('已寫入' if args.go else '將寫入', tally['done'], tally['skip'], tally['fail']))
    return tally

if __name__ == '__main__':
    main()
