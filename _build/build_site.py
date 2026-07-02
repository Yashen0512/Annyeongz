# -*- coding: utf-8 -*-
import csv, glob, io, json, os, re
from collections import Counter, OrderedDict
import facets_def as F

PLACEHOLDER_URL = "https://pebble-honeycrisp-a9a.notion.site/176a7213548080cda25dd9e1edd5b7a4"

def event_key(tag):
    """合集活動排序:華語圈(依日期)→ LOVE GAME(依季節)→ 鳳梨汁(HE→BE、金銀銅)。新活動自動歸位。"""
    if '鳳梨' in tag:
        he = 0 if 'HE' in tag else 1
        medal = next((i for i, k in enumerate(['金', '銀', '銅']) if k + '賞' in tag), 9)
        return (2, he, medal, tag)
    if 'LOVE GAME' in tag or '계간' in tag:
        smap = {'Summer': 0, 'Authum': 1, 'Autumn': 1, 'Winter': 2}
        season = next((v for k, v in smap.items() if k in tag), 9)
        ym = re.search(r'(\d{4})', tag)
        return (1, int(ym.group(1)) if ym else 0, season, tag)
    y, mo, d, hw = 9999, 99, 99, 0
    mb = re.match(r'(\d{2})831901', tag)      # 23831901 = 雙生日 8/31·9/1
    m4 = re.match(r'(\d{4})生日賀文', tag)
    m8 = re.match(r'(\d{4})(\d{2})(\d{2})', tag)
    m6 = re.match(r'(\d{2})(\d{2})(\d{2})', tag)
    if mb:
        y, mo, d = 2000 + int(mb.group(1)), 8, 31
    elif m4:
        y, mo, d, hw = int(m4.group(1)), 8, 31, 1
    elif m8 and 2000 <= int(m8.group(1)) <= 2099:
        y, mo, d = int(m8.group(1)), int(m8.group(2)), int(m8.group(3))
    elif m6:
        y, mo, d = 2000 + int(m6.group(1)), int(m6.group(2)), int(m6.group(3))
    return (0, y, mo, d, hw, tag)

def parse_date_only(s):
    m = re.search(r'(\d+)年(\d+)月(\d+)日', s or '')
    if not m:
        return ('', 0)
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return ('%d/%d/%d' % (y, mo, d), (y * 100 + mo) * 100 + d)

def parse_dt(s):
    """Notion 中文日期『2025年6月3日 下午10:26』→ (顯示字串, 可排序整數)。"""
    m = re.search(r'(\d+)年(\d+)月(\d+)日(?:\s*(上午|下午))?\s*(\d+):(\d+)', s or '')
    if not m:
        return ('', 0)
    y, mo, d, ap, h, mi = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5)), int(m.group(6))
    y, mo, d = int(y), int(mo), int(d)
    if ap == '下午' and h < 12: h += 12
    if ap == '上午' and h == 12: h = 0
    key = ((((y * 100 + mo) * 100 + d) * 100 + h) * 100 + mi)
    return ('%d/%d/%d' % (y, mo, d), key)

def author_names(s):
    """作者欄是 Notion 關聯,匯出成『名字 (網址), 名字 (網址)』。
    用『網址邊界』拆,而非逗號 —— 否則名字本身含逗號(如 ㅍ.,ㅍ)會被拆錯。"""
    s = s or ''
    parts = [p.strip().strip(',').strip() for p in re.findall(r'(.*?)\(https?://[^)]*\)\s*,?\s*', s)]
    parts = [p for p in parts if p]
    if not parts:  # 沒有網址(如 LOVE GAME 只有名字)→ 退回逗號拆
        parts = [p.strip() for p in s.split(',') if p.strip()]
    return parts

f = glob.glob('*176a7213548080cda25dd9e1edd5b7a4_all.csv')[0]
allrows = list(csv.reader(io.open(f, encoding='utf-8-sig')))
C = F.cols(allrows[0])
H = {n: i for i, n in enumerate(allrows[0])}   # 表頭名稱 → 欄位索引(用來讀各分面欄)
rows = allrows[1:]

def merge_facet_cols(b, r):
    """把 Notion 各分面欄直接填的值,合併進 bucketize 結果(新文直接填分面欄時靠這個)。"""
    for fac in list(F.FACETS.keys()) + F.EVENT_FACETS:
        ci = H.get(fac, -1)
        if ci < 0 or ci >= len(r):
            continue
        for raw in F.split_tags(r[ci]):
            tag = F.REMAP.get(raw, raw)
            if tag in F.DROP:
                continue
            if fac in F.FACETS and tag not in F.FACETS[fac]:
                continue   # 不在該分面控制詞彙內,略過
            if tag not in b[fac]:
                b[fac].append(tag)
    # 依分面定義順序重新排好
    for fac, tags in F.FACETS.items():
        order = {t: i for i, t in enumerate(tags)}
        b[fac].sort(key=lambda t: order.get(t, 999))
    return b

# 作者/譯者資料庫 → 名字: {平台: 網址}(依標題名稱定位欄位)
people = {}
dead_authors = []   # 紅標作者(已刪帳號)
afs = glob.glob('_authors/*_all.csv')
if afs:
    arows = list(csv.reader(io.open(afs[0], encoding='utf-8-sig')))
    ah = {n: i for i, n in enumerate(arows[0])}
    PLATCOL = {'AF': '作者平台(AF)', 'AO3': '作者平台(AO3)', 'Lofter': '作者平台(LFT)',
               'Lofter2': '作者平台(LFT2)', 'Postype': '作者平台(PT)', '微博': '作者平台(WB)',
               'X': '作者平台(X)', '其他': '作者平台(其他)'}
    ncol = ah.get('作者名稱', 0)
    rcol = ah.get('紅標', -1)
    for ar in arows[1:]:
        name = (ar[ncol] or '').strip() if ncol < len(ar) else ''
        if not name:
            continue
        if 0 <= rcol < len(ar) and ar[rcol].strip() == 'Y':
            dead_authors.append(name)
        links = {}
        for lab, col in PLATCOL.items():
            ci = ah.get(col, -1)
            if 0 <= ci < len(ar) and ar[ci].strip().startswith('http'):
                links[lab] = ar[ci].strip()
        if links:
            people[name] = links

# 每篇閱讀連結(由 fetch_links.py 產生):No -> {標題: [[label, url], ...]}
links_map = {}
try:
    links_map = json.load(io.open('article_links.json', encoding='utf-8'))
except Exception:
    print('(尚無 article_links.json,連結先留空)')

SINGLE = [('文章類型', C.TYPE), ('文章篇幅', C.LENGTH), ('結局', C.END), ('文章狀態', C.STATUS)]

articles = []
for r in rows:
    b = F.bucketize(r[C.TAGS], (r[C.NO] or '').strip())
    b = merge_facet_cols(b, r)
    tags = OrderedDict()
    for k, idx in SINGLE:
        v = (r[idx] or '').strip()
        tags[k] = [v] if v else []
    for fac in list(F.FACETS.keys()) + F.EVENT_FACETS:
        tags[fac] = b[fac]
    names = author_names(r[C.AUTHOR])
    is_tr = '譯文' in b['形式/性質']
    if is_tr and len(names) >= 2:
        author = names[0]; translator = '、'.join(names[1:])
    else:
        author = '、'.join(names); translator = ''
    ed_disp, ed_key = parse_dt(r[C.EDIT])
    cr_disp, cr_key = parse_dt(r[C.CREATE])      # 建立時間=實際收錄(新增)時間,供「最新收錄」排序
    no_s = (r[C.NO] or '').strip()
    title_s = (r[C.NAME] or '').strip()
    lm = links_map.get(no_s, {})
    links = lm.get(title_s)
    if links is None and len(lm) == 1:
        links = next(iter(lm.values()))
    articles.append({
        'no': no_s,
        'name': title_s,
        'persona': (r[C.PERSONA] or '').strip(),
        'author': author,
        'translator': translator,
        'edited': ed_disp,
        'ek': ed_key,
        'created': cr_disp,
        'ck': cr_key,
        'tags': tags,
        'links': links or [],
        'dead': (0 <= H.get('紅標', -1) < len(r) and r[H['紅標']].strip() == 'Y'),
    })

# sort by No desc (newest first)
def nokey(a):
    v = a['no']
    return (0, int(v)) if v.isdigit() else (1, 0)
articles.sort(key=lambda a: (-(nokey(a)[1]), a['no']))

# facet option lists with counts
facet_defs = []
for k, _ in SINGLE:
    c = Counter()
    for a in articles:
        for v in a['tags'][k]:
            c[v] += 1
    facet_defs.append({'key': k, 'type': 'single', 'options': c.most_common()})
for fac in list(F.FACETS.keys()) + F.EVENT_FACETS:
    c = Counter()
    for a in articles:
        for v in a['tags'][fac]:
            c[v] += 1
    # keep defined order for multi facets; events by rule
    if fac in F.FACETS:
        opts = [(t, c.get(t, 0)) for t in F.FACETS[fac] if c.get(t, 0) > 0]
    else:  # 合集活動:規則排序
        opts = sorted(c.items(), key=lambda kv: event_key(kv[0]))
    facet_defs.append({'key': fac, 'type': 'multi', 'options': opts})

# 公告資料庫
anns = []
anfs = glob.glob('_announce/*_all.csv') or glob.glob('_announce/*.csv')
if anfs:
    for ar in list(csv.reader(io.open(anfs[0], encoding='utf-8-sig')))[1:]:
        content = (ar[0] or '').strip()
        if not content:
            continue
        disp, key = parse_date_only(ar[1] if len(ar) > 1 else '')
        pin = len(ar) > 2 and ar[2].strip().lower() in ('yes', 'true', '是', '✓')
        anns.append({'content': content, 'date': disp, 'dk': key, 'pin': pin})
    anns.sort(key=lambda a: (0 if a['pin'] else 1, -a['dk']))

# 資料庫更新時間 = 所有文章中「最新的編輯時間」(只在內容變動時才變,避免每次建置都跳動)
_mx = max((a['ek'] for a in articles), default=0)
if _mx:
    _s = str(_mx)  # YYYYMMDDHHMM
    _h = int(_s[8:10]); _ap = 'AM' if _h < 12 else 'PM'; _h12 = _h % 12 or 12   # 12 時制 AM/PM
    updated = '%d/%d/%d %d:%s %s' % (int(_s[0:4]), int(_s[4:6]), int(_s[6:8]), _h12, _s[10:12], _ap)
else:
    updated = ''

stats = None
try:
    stats = json.load(io.open('stats.json', encoding='utf-8'))
except Exception:
    pass

DATA = {'total': len(articles), 'facets': facet_defs, 'articles': articles,
        'people': people, 'announcements': anns, 'updated': updated,
        'dead_authors': dead_authors, 'stats': stats}

# 輸出資料夾:本機預設 ../site;GitHub Action 設環境變數 SITE_OUT=.. 直接輸出到倉庫根目錄
OUT = os.environ.get('SITE_OUT', '../site')
os.makedirs(OUT, exist_ok=True)
data_decl = 'window.DATA = ' + json.dumps(DATA, ensure_ascii=False, sort_keys=True) + ';'
# also emit data.js (for deploy if ever served as separate files)
io.open(os.path.join(OUT, 'data.js'), 'w', encoding='utf-8').write(data_decl)
# self-contained index.html (works via double-click / preview / file://)
tpl = io.open('site_template.html', encoding='utf-8').read()
# 注入簡繁對照表(搜尋簡繁互通);stmap.txt 兩行=繁字串 / 簡字串
try:
    _st = io.open('stmap.txt', encoding='utf-8').read().splitlines()
    _stT, _stS = (_st + ['', ''])[:2]
except Exception:
    _stT, _stS = '', ''
tpl = tpl.replace('__STMAP_T__', _stT).replace('__STMAP_S__', _stS)
io.open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(tpl.replace('/*__DATA__*/', data_decl))

print('site built:', len(articles), 'articles,', len(facet_defs), 'facets (self-contained index.html)')

# ---- 編號重複偵測 + 下一個可用號 ----
from collections import defaultdict as _dd
_byno = _dd(list)
for a in articles:
    if a['no']:
        _byno[a['no']].append(a['name'] or '(無標題)')
_dups = {no: names for no, names in _byno.items() if len(names) > 1}
_nums = [int(a['no']) for a in articles if a['no'].isdigit()]
_reg = [n for n in _nums if n < 10000]     # 一般文(10000+ 是活動系列)
if _dups:
    print('')
    print('==================== ⚠️  編號重複警告  ⚠️ ====================')
    for no in sorted(_dups, key=lambda x: (len(x), x)):
        print('  No %s 重複 %d 篇:%s' % (no, len(_dups[no]), '、'.join(_dups[no])))
    print('  請到 Notion 修正其中一篇的編號後再更新一次。')
    print('==============================================================')
else:
    print('編號檢查:無重複 ✅')
if _reg:
    print('目前最大編號:%d(一般文最大 %d) → 下一篇一般文建議用 #%d'
          % (max(_nums), max(_reg), max(_reg) + 1))
