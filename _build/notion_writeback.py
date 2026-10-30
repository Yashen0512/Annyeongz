# -*- coding: utf-8 -*-
"""巡檢 ②:把 check_links.py 的結果寫回 Notion(資料的唯一源頭;網站下次 sync 自然更新)。
   預設 dry-run 只印將變更的清單,加 --go 才真的寫(與 notion_fill.py 的習慣一致)。只用標準庫。

   死連結:更新該作品頁面內文裡那個連結 block 的 rich_text,在連結文字**前**插入一段「❌」純文字;
           復活就移除 ❌(連結段落本身、以及緊鄰前後純文字段裡的 ❌ 都清掉,相容站長以前手動加在後面的寫法)。
           這樣 build_site.py 既有的 dead 判定(❌ 過半)自動接手,不用改判定邏輯。
           block 位置優先用 article_links.json 的 __blocks__(fetch_data.py 記錄),對不上就重新抓頁面子 block 找 href,
           連頁面 ID 都沒有時用 No 查主表。
   作者改名:作者庫該頁「作者名稱」title 改成新名字;「曾用名」multi_select(不存在就用 database update API 建立)
           加入舊名字(不刪、不重複;Notion 選項名不能有半形逗號 → 換成全形)。只處理 check_links 列在 renames 的
           (作者庫平台網址核對過的),rename_candidates 不動。寫之前再讀一次作者頁,title 跟報告的舊名不同就跳過。
   用法:python notion_writeback.py [--go] [--report check_report.json] [--no 1352] [--limit N]
         token 來源同 fetch_data.py(NOTION_TOKEN → notion_token.txt → 交給代理)。"""
import argparse, copy, io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_data as FD

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

def is_marked(rts, idx):
    """連結段落本身、或緊鄰前後的純文字段,任一含 ❌ 就算已標。"""
    for j in (idx - 1, idx, idx + 1):
        if 0 <= j < len(rts) and (j == idx or not _href(rts[j])) and DEAD_MARK in _seg_text(rts[j]):
            return True
    return False

def mark_dead(rts, idx):
    """在連結段落前插入一段「❌」;已標過就原樣回傳。回傳 (新 rich_text, 是否有改)。"""
    if is_marked(rts, idx):
        return rts, False
    out = copy.deepcopy(rts)
    out.insert(idx, _plain_seg(DEAD_MARK))
    return out, True

def unmark_dead(rts, idx):
    """移除連結段落與緊鄰前後純文字段裡的 ❌(鄰段被清空就整段拿掉)。回傳 (新 rich_text, 是否有改)。"""
    out, changed, drop = copy.deepcopy(rts), False, set()
    for j in (idx - 1, idx, idx + 1):
        if 0 <= j < len(out) and (j == idx or not _href(out[j])):
            s = _seg_text(out[j])
            if DEAD_MARK in s:
                s2 = s.replace(DEAD_MARK, '')
                _set_seg_text(out[j], s2)
                changed = True
                if j != idx and s2.strip() == '':
                    drop.add(j)
    return [seg for j, seg in enumerate(out) if j not in drop], changed

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

def page_children(page_id):
    out, cur = [], None
    while True:
        res = api('GET', 'blocks/%s/children?page_size=100%s' % (page_id, '&start_cursor=' + cur if cur else ''))
        out += res.get('results', [])
        if not res.get('has_more'):
            return out
        cur = res['next_cursor']

def find_page_by_no(no):
    try:
        n = int(no)
    except ValueError:
        return None
    res = api('POST', 'databases/%s/query' % FD.MAIN_ID, {'filter': {'property': 'No', 'number': {'equals': n}}, 'page_size': 2})
    r = res.get('results', [])
    return r[0]['id'] if len(r) == 1 else None

def rich_text_of(block):
    t = block['type']; bd = block.get(t, {})
    if t in CAPTION_TYPES:
        return 'caption', bd.get('caption', [])
    return 'rich_text', bd.get('rich_text', [])

def locate(item):
    """報告裡的一筆連結 → (block, field, rich_text, idx);找不到回 None。"""
    url = item['url']
    blk = None
    if item.get('block'):
        try:
            blk = get_block(item['block'][0])
        except Exception as e:
            print('   (block %s 讀不到:%s,改掃頁面)' % (item['block'][0], e))
            blk = None
    if blk and not blk.get('archived'):
        field, rts = rich_text_of(blk)
        idx = find_link_index(rts, url, item['block'][1] if len(item['block']) > 1 else None)
        if idx >= 0 or (blk['type'] in CAPTION_TYPES and blk[blk['type']].get('url') == url):
            return blk, field, rts, idx
    page_id = item.get('page') or find_page_by_no(item['no'])
    if not page_id:
        return None
    for b in page_children(page_id):
        field, rts = rich_text_of(b)
        idx = find_link_index(rts, url)
        if idx >= 0 or (b['type'] in CAPTION_TYPES and b[b['type']].get('url') == url):
            return b, field, rts, idx
    return None

def apply_link(item, action, go):
    """action: 'mark' | 'unmark'。回傳 'done' | 'skip' | 'fail'。"""
    found = locate(item)
    tag = 'No.%s《%s》%s' % (item['no'], item['title'], item['label'].replace(DEAD_MARK, '').strip())
    if not found:
        print('   ⚠️ 找不到連結 block:%s %s' % (tag, item['url']))
        return 'fail'
    blk, field, rts, idx = found
    if idx < 0:   # bookmark / embed 沒有 rich_text:把 ❌ 放進 caption 開頭
        rts = rts or []
        idx = 0
        if action == 'mark':
            new, changed = (rts, False) if any(DEAD_MARK in _seg_text(s) for s in rts) else ([_plain_seg(DEAD_MARK)] + copy.deepcopy(rts), True)
        else:
            new, changed = unmark_dead(rts, 0) if rts else (rts, False)
    else:
        new, changed = mark_dead(rts, idx) if action == 'mark' else unmark_dead(rts, idx)
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

def main(argv=None):
    ap = argparse.ArgumentParser(description='把巡檢結果寫回 Notion(預設 dry-run)')
    ap.add_argument('--go', action='store_true', help='真的寫入 Notion(不加 = 只印清單)')
    ap.add_argument('--report', default='check_report.json')
    ap.add_argument('--no', default='', help='只處理這些編號(逗號分隔;測試用)')
    ap.add_argument('--limit', type=int, default=0, help='死 / 復活各最多處理幾筆(測試用)')
    ap.add_argument('--skip-renames', action='store_true')
    args = ap.parse_args(argv)
    try:
        rep = json.load(io.open(args.report, encoding='utf-8'))
    except Exception as e:
        raise SystemExit('讀不到 %s(先跑 check_links.py):%s' % (args.report, e))
    only = set(x.strip() for x in args.no.split(',') if x.strip())
    pick = lambda lst: [x for x in lst if not only or x['no'] in only][:args.limit or None]
    dead, revived = pick(rep.get('new_dead', [])), pick(rep.get('revived', []))
    renames = [] if args.skip_renames or only else rep.get('renames', [])
    mode = '寫入 Notion(--go)' if args.go else 'dry-run(只印清單;加 --go 才寫)'
    print('notion_writeback %s:%s' % (rep.get('date', ''), mode))
    if not (dead or revived or renames):
        print('沒有要寫回的變更。')
        return {'done': 0, 'skip': 0, 'fail': 0}
    tally = {'done': 0, 'skip': 0, 'fail': 0}
    if dead:
        print('— 標 ❌(新死 %d 筆)' % len(dead))
        for x in dead:
            tally[apply_link(x, 'mark', args.go)] += 1
    if revived:
        print('— 移除 ❌(復活 %d 筆)' % len(revived))
        for x in revived:
            tally[apply_link(x, 'unmark', args.go)] += 1
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
