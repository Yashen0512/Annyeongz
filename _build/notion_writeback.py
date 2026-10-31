# -*- coding: utf-8 -*-
"""巡檢 ②:把 check_links.py 的結果寫回 Notion(資料的唯一源頭;網站下次 sync 自然更新)。
   預設 dry-run 只印將變更的清單,加 --go 才真的寫(與 notion_fill.py 的習慣一致)。只用標準庫。

   死連結:更新該作品頁面內文裡那個連結 block 的 rich_text,在連結文字**前**插入一段「❌」純文字;
           復活就移除 ❌(連結段落本身、以及緊鄰前後純文字段裡的 ❌ 都清掉,相容站長以前手動加在後面的寫法)。
           這樣 build_site.py 既有的 dead 判定(❌ 過半)自動接手,不用改判定邏輯。
           block 位置**只用** article_links.json 的 __blocks__(fetch_data.py 記錄),而且 block 的父頁面、網址都要對得上;
           對不上就跳過、附到 Issue 內文「需人工確認」段,絕不拿網址去別的頁面搜尋後亂寫(article_links.json 曾經把別篇的連結留在錯的 No 底下)。
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
