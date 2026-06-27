# -*- coding: utf-8 -*-
"""一鍵更新 ①:從 Notion API 抓主表/作者/公告 + 每篇閱讀連結,
   產出 build_site.py 需要的檔案(CSV + article_links.json)。
   token 從 notion_token.txt 讀。需把三個資料庫都分享給整合。"""
import csv, glob, io, json, os, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta

NOTION_VER = '2022-06-28'
TOKEN = (os.environ.get('NOTION_TOKEN') or io.open('notion_token.txt', encoding='utf-8').read()).strip()
MAIN_ID = '176a7213548080cda25dd9e1edd5b7a4'      # 主表(從匯出檔名得知)
TZ = timezone(timedelta(hours=8))                  # 台北時間,對齊 Notion 顯示

def api(method, url, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    last = None
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header('Authorization', 'Bearer ' + TOKEN)
            req.add_header('Notion-Version', NOTION_VER)
            req.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(3); continue
            print('HTTP', e.code, e.read().decode('utf-8')[:300]); raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e; time.sleep(3 * (attempt + 1)); continue
    raise last or RuntimeError('retry exhausted')

def query_all(db_id):
    out, cur = [], None
    while True:
        b = {'page_size': 100}
        if cur: b['start_cursor'] = cur
        res = api('POST', 'https://api.notion.com/v1/databases/%s/query' % db_id, b)
        out += res['results']
        if not res.get('has_more'): break
        cur = res['next_cursor']
    return out

# ---- 屬性讀取 ----
def p(pg, name): return pg['properties'].get(name)
def p_title(pr): return ''.join(x['plain_text'] for x in pr['title']).strip() if pr and pr.get('type') == 'title' else ''
def p_rich(pr):  return ''.join(x['plain_text'] for x in pr['rich_text']) if pr and pr.get('type') == 'rich_text' else ''
def p_multi(pr): return ', '.join(o['name'] for o in pr['multi_select']) if pr and pr.get('type') == 'multi_select' else ''
def p_relation(pr): return [r['id'] for r in pr['relation']] if pr and pr.get('type') == 'relation' else []
def p_checkbox(pr): return bool(pr['checkbox']) if pr and pr.get('type') == 'checkbox' else False
def p_select(pr):
    if not pr: return ''
    t = pr.get('type')
    if t == 'select' and pr['select']: return pr['select']['name']
    if t == 'status' and pr['status']: return pr['status']['name']
    if t == 'multi_select': return ', '.join(o['name'] for o in pr['multi_select'])
    return ''
def p_url(pr):
    if not pr: return ''
    t = pr.get('type')
    if t == 'url' and pr['url']: return pr['url'].strip()
    if t == 'rich_text': return p_rich(pr).strip()
    return ''
def p_date_start(pr):
    return pr['date']['start'] if pr and pr.get('type') == 'date' and pr['date'] else ''
def is_red(pg):
    """頁面圖示為紅色 = 標記(文章:原文已刪;作者:已刪帳號)。"""
    ic = pg.get('icon')
    return bool(ic and ic.get('type') == 'icon' and (ic.get('icon') or {}).get('color') == 'red')

def read_no(pg):
    pr = p(pg, 'No'); t = pr['type'] if pr else ''
    if t == 'number' and pr['number'] is not None:
        v = pr['number']; return str(int(v)) if float(v).is_integer() else str(v)
    if t == 'unique_id': return str(pr['unique_id'].get('number', ''))
    if t in ('title', 'rich_text'): return ''.join(x['plain_text'] for x in pr[t]).strip()
    return ''

def fmt_dt(iso):
    """ISO → '2026年6月24日 上午12:06'(對齊 Notion / parse_dt)。"""
    if not iso: return ''
    dt = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(TZ)
    ap = '上午' if dt.hour < 12 else '下午'
    h = dt.hour % 12 or 12
    return '%d年%d月%d日 %s%d:%02d' % (dt.year, dt.month, dt.day, ap, h, dt.minute)

def fmt_date(iso):
    if not iso: return ''
    d = datetime.fromisoformat(iso[:10])
    return '%d年%d月%d日' % (d.year, d.month, d.day)

def atomic_write_csv(path, header, rows):
    tmp = path + '.tmp'
    with io.open(tmp, 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(header)
        for r in rows: w.writerow(r)
    os.replace(tmp, path)

# ---- 找三個資料庫 ----
print('搜尋資料庫…')
dbs = api('POST', 'https://api.notion.com/v1/search',
          {'filter': {'property': 'object', 'value': 'database'}, 'page_size': 50})['results']
def find_db(pred):
    for db in dbs:
        if pred(db.get('properties', {})): return db['id']
    return None
authors_db = find_db(lambda pr: '作者名稱' in pr)
announce_db = find_db(lambda pr: '內容' in pr and '日期' in pr and '置頂' in pr)
if not any(db['id'].replace('-', '') == MAIN_ID for db in dbs):
    raise SystemExit('找不到主表(整合沒讀到 %s)。請確認 Notion 整合已連到主資料庫。' % MAIN_ID)
if not authors_db:
    raise SystemExit('找不到「作者/譯者資料庫」。請到該資料庫 ••• → 連結 → 加入同一個整合,再重跑。')

# ---- 作者庫:id→名字、平台連結 ----
print('抓作者庫…')
PLAT = [('AF', '作者平台(AF)'), ('AO3', '作者平台(AO3)'), ('LFT', '作者平台(LFT)'),
        ('LFT2', '作者平台(LFT2)'), ('PT', '作者平台(PT)'), ('WB', '作者平台(WB)'),
        ('X', '作者平台(X)'), ('其他', '作者平台(其他)')]
id2name, author_rows = {}, []
for pg in query_all(authors_db):
    name = p_title(p(pg, '作者名稱'))
    if not name: continue
    id2name[pg['id'].replace('-', '')] = name
    author_rows.append([name] + [p_url(p(pg, col)) for _, col in PLAT] + ['Y' if is_red(pg) else ''])
author_header = ['作者名稱'] + [col for _, col in PLAT] + ['紅標']
os.makedirs('_authors', exist_ok=True)
for old in glob.glob('_authors/*_all.csv'): os.remove(old)
atomic_write_csv('_authors/authors_all.csv', author_header, author_rows)
print('  作者:', len(author_rows), '位')

# ---- 主表 ----
print('抓主表…')
def author_cell(ids):
    parts = []
    for aid in ids:
        nm = id2name.get(aid.replace('-', ''))
        if nm: parts.append('%s (https://www.notion.so/%s)' % (nm, aid.replace('-', '')))
    return ', '.join(parts)

# 各分面欄(直接填在 Notion 分面欄的值,新文用這些;與「文章標籤」合併)
FACET_COLS = ['CP配對', '情感梗', '背景設定', '類型世界觀', '題材梗', '分級', '形式/性質',
              '命定站賀文合集', '계간윶녕 : 𝐋𝐎𝐕𝐄 𝐆𝐀𝐌𝐄', '1st鳳梨汁推薦']
MAIN_HEADER = ['文章名稱', 'No', '上次編輯時間', '人設(安、員)', '作者/譯者資料庫',
               '建立時間', '文章標籤', '文章狀態', '文章篇幅', '文章類型', '結局'] + FACET_COLS + ['紅標']
main_rows = []
pages = query_all(MAIN_ID)
for pg in pages:
    main_rows.append([
        p_title(p(pg, '文章名稱')),
        read_no(pg),
        fmt_dt(pg.get('last_edited_time', '')),
        p_rich(p(pg, '人設(安、員)')),
        author_cell(p_relation(p(pg, '作者/譯者資料庫'))),
        fmt_dt(pg.get('created_time', '')),
        p_multi(p(pg, '文章標籤')),
        p_select(p(pg, '文章狀態')),
        p_select(p(pg, '文章篇幅')),
        p_select(p(pg, '文章類型')),
        p_select(p(pg, '結局')),
    ] + [p_multi(p(pg, c)) for c in FACET_COLS] + ['Y' if is_red(pg) else ''])
for old in glob.glob('*%s_all.csv' % MAIN_ID): os.remove(old)
atomic_write_csv('Annyeongz_%s_all.csv' % MAIN_ID, MAIN_HEADER, main_rows)
print('  文章:', len(main_rows), '篇')

# ---- 公告(可選) ----
if announce_db:
    print('抓公告…')
    arows = []
    for pg in query_all(announce_db):
        content = p_rich(p(pg, '內容')) or p_title(p(pg, '內容'))
        if not content.strip(): continue
        arows.append([content, fmt_date(p_date_start(p(pg, '日期'))),
                      'Yes' if p_checkbox(p(pg, '置頂')) else 'No'])
    os.makedirs('_announce', exist_ok=True)
    for old in glob.glob('_announce/*_all.csv'): os.remove(old)
    atomic_write_csv('_announce/announce_all.csv', ['內容', '日期', '置頂'], arows)
    print('  公告:', len(arows), '則')
else:
    print('  (找不到公告庫,沿用現有公告檔;要自動更新公告請把公告庫也分享給整合)')

# ---- 每篇閱讀連結(增量:只抓沒抓過的 No)----
def block_links(blk):
    t = blk['type']; bd = blk.get(t, {}); out = []
    if isinstance(bd, dict):
        rts = bd.get('rich_text', [])
        label = ''.join(x.get('plain_text', '') for x in rts).strip()
        for x in rts:
            if x.get('href'): out.append([label or x['href'], x['href']])
        if t in ('bookmark', 'embed', 'link_preview') and bd.get('url'):
            out.append([bd['url'], bd['url']])
    return out

links = {}
if os.path.exists('article_links.json'):
    try: links = json.load(io.open('article_links.json', encoding='utf-8'))
    except Exception: links = {}
new = 0
for pg in pages:
    no = read_no(pg)
    if not no: continue
    title = p_title(p(pg, '文章名稱'))
    if no in links and title in links[no]: continue   # 已抓過,跳過
    ch = api('GET', 'https://api.notion.com/v1/blocks/%s/children?page_size=100' % pg['id'])
    seen, lst = set(), []
    for blk in ch.get('results', []):
        for lab, url in block_links(blk):
            if url not in seen: seen.add(url); lst.append([lab, url])
    links.setdefault(no, {})[title] = lst
    new += 1
    time.sleep(0.34)
io.open('article_links.json', 'w', encoding='utf-8').write(json.dumps(links, ensure_ascii=False))
print('  連結:新增', new, '篇(總', sum(len(v) for v in links.values()), '筆標題)')
print('完成 ✅  接著跑 build_site.py')
