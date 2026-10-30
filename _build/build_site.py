# -*- coding: utf-8 -*-
"""一鍵更新 ②:把 fetch_data.py 產出的 CSV / article_links.json 套上 facets_def 分面定義,
   輸出 data.js 與 index.html(樣板注入資料與簡繁對照表),並把 src/、styles/ 一起複製到輸出資料夾。
   只用標準庫。所有步驟都是函式,pytest 可以用 fixture 資料夾直接呼叫 build_data() / write_site()。"""
import csv, glob, io, json, os, re, shutil
from collections import Counter, OrderedDict
from datetime import datetime, timezone, timedelta
import facets_def as F

PLACEHOLDER_URL = "https://pebble-honeycrisp-a9a.notion.site/176a7213548080cda25dd9e1edd5b7a4"

DEAD_MARK = '❌'   # Notion 閱讀連結名稱裡的 ❌ = 該連結已失效
INTERNAL_PREFIX = 'annyeongz:'   # 站內互連(前傳/續寫):連到站內另一篇,不算有效或失效連結

# 作者庫欄位 → 前端顯示的平台名
PLATCOL = OrderedDict([('AF', '作者平台(AF)'), ('AO3', '作者平台(AO3)'), ('Lofter', '作者平台(LFT)'),
                       ('Lofter2', '作者平台(LFT2)'), ('Postype', '作者平台(PT)'), ('微博', '作者平台(WB)'),
                       ('X', '作者平台(X)'), ('其他', '作者平台(其他)')])
SINGLE = [('文章類型', 'TYPE'), ('文章篇幅', 'LENGTH'), ('結局', 'END'), ('文章狀態', 'STATUS')]

# ---------- 純函式(pytest 直接測這些) ----------

def split_links(links):
    """[[名稱, 網址], ...] → 名稱含 ❌ 的改成 [名稱(去掉❌), 網址, 1];有效的維持兩格(資料檔不變大)。"""
    out = []
    for l in links or []:
        lab, url = l[0], l[1]
        if DEAD_MARK in lab:
            out.append([lab.replace(DEAD_MARK, '').strip() or url, url, 1])
        else:
            out.append([lab, url])
    return out

def is_internal(link):
    return link[1].startswith(INTERNAL_PREFIX)

def is_dead(manual_dead, links):
    """原文已刪判定:Notion 紅標(頁面圖示紅色),或站外連結中已失效(❌)的超過一半。站內互連不計。"""
    ext = [l for l in links if not is_internal(l)]
    n_dead = sum(1 for l in ext if len(l) > 2)
    return bool(manual_dead) or n_dead * 2 > len(ext)

def dead_conflict(manual_dead, links):
    """紅標 = Y 但還有沒標 ❌ 的站外連結 → 待人工確認。"""
    ext = [l for l in links if not is_internal(l)]
    return bool(manual_dead) and any(len(l) < 3 for l in ext)

def event_key(tag):
    """合集活動排序:華語圈(依日期)→ LOVE GAME(依季節)→ 鳳梨汁(HE→BE、金銀銅)。新活動自動歸位。"""
    if '鳳梨' in tag:
        he = 0 if 'HE' in tag else 1
        medal = next((i for i, k in enumerate(['金', '銀', '銅']) if k + '賞' in tag), 9)
        return (2, he, medal, tag)
    if 'LOVE GAME' in tag or '계간' in tag:
        smap = {'Spring': 0, 'Summer': 1, 'Authum': 2, 'Autumn': 2, 'Fall': 2, 'Winter': 3}
        season = next((v for k, v in smap.items() if k in tag), 9)
        ym = re.search(r'(\d{4})', tag)
        return (1, int(ym.group(1)) if ym else 0, season, tag)
    y, mo, d, hw = 9999, 99, 99, 0
    mb4 = re.match(r'(\d{4})831901', tag)     # 2025831901 = 4位數年+雙生日 8/31·9/1
    mb = re.match(r'(\d{2})831901', tag)      # 23831901 = 2位數年+雙生日(舊格式)
    m4 = re.match(r'(\d{4})生日賀文', tag)
    m8 = re.match(r'(\d{4})(\d{2})(\d{2})', tag)
    m6 = re.match(r'(\d{2})(\d{2})(\d{2})', tag)
    if mb4:
        y, mo, d, hw = int(mb4.group(1)), 8, 31, 1
    elif mb:
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
    """Notion 中文日期『2025年6月3日 下午10:26』→ (顯示字串, 可排序整數 YYYYMMDDHHMM)。"""
    m = re.search(r'(\d+)年(\d+)月(\d+)日(?:\s*(上午|下午))?\s*(\d+):(\d+)', s or '')
    if not m:
        return ('', 0)
    y, mo, d, ap, h, mi = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5)), int(m.group(6))
    y, mo, d = int(y), int(mo), int(d)
    if ap == '下午' and h < 12: h += 12
    if ap == '上午' and h == 12: h = 0
    key = ((((y * 100 + mo) * 100 + d) * 100 + h) * 100 + mi)
    return ('%d/%d/%d' % (y, mo, d), key)

_NID = re.compile(r'([0-9a-f]{32})')

def author_parts(s):
    """作者欄是 Notion 關聯,匯出成『名字 (https://www.notion.so/<頁面ID>), 名字 (網址)』。
    用『網址邊界』拆,而非逗號 —— 否則名字本身含逗號(如 ㅍ.,ㅍ)會被拆錯。
    回傳 [(名字, 頁面ID)],頁面ID 是 32 碼十六進位;沒有網址(如 LOVE GAME 只有名字)→ 退回逗號拆、ID 為空字串。"""
    s = s or ''
    parts = []
    for nm, url in re.findall(r'(.*?)\((https?://[^)]*)\)\s*,?\s*', s):
        nm = nm.strip().strip(',').strip()
        if not nm:
            continue
        m = _NID.search(url.replace('-', '').lower())
        parts.append((nm, m.group(1) if m else ''))
    if not parts:
        parts = [(p.strip(), '') for p in s.split(',') if p.strip()]
    return parts

def author_names(s):
    """只要名字(相容舊用法)。"""
    return [nm for nm, _ in author_parts(s)]

def split_author_translator(parts, is_translation):
    """譯文且有兩人以上:第一人是作者、其餘是譯者;否則全部是作者。回傳 (作者names, 作者ids, 譯者names, 譯者ids)。"""
    if is_translation and len(parts) >= 2:
        au, tr = parts[:1], parts[1:]
    else:
        au, tr = parts, []
    return ([n for n, _ in au], [i for _, i in au], [n for n, _ in tr], [i for _, i in tr])

def nokey(a):
    v = a['no']
    return (0, int(v)) if v.isdigit() else (1, 0)

def fmt_updated(ek_max):
    """YYYYMMDDHHMM → '2026/10/29 11:54 PM'(12 時制)。0 → ''。"""
    if not ek_max:
        return ''
    _s = str(ek_max)
    _h = int(_s[8:10]); _ap = 'AM' if _h < 12 else 'PM'; _h12 = _h % 12 or 12
    return '%d/%02d/%02d %d:%s %s' % (int(_s[0:4]), int(_s[4:6]), int(_s[6:8]), _h12, _s[10:12], _ap)

def fmt_synced(now):
    """本次建置時間(台北);若落在生日時段(08:31 / 21:01)後 8 分鐘內,貼齊顯示成該生日時間
    (排程班次 → 乾淨的彩蛋);否則(手動 .bat)顯示實際建置時間。"""
    _sync_dt = now
    for _bh, _bm in ((8, 31), (21, 1)):
        _tgt = now.replace(hour=_bh, minute=_bm, second=0, microsecond=0)
        if 0 <= (now - _tgt).total_seconds() <= 8 * 60:
            _sync_dt = _tgt
            break
    _sh = _sync_dt.hour; _sap = 'AM' if _sh < 12 else 'PM'; _sh12 = _sh % 12 or 12
    return '%d/%02d/%02d %d:%02d %s' % (_sync_dt.year, _sync_dt.month, _sync_dt.day, _sh12, _sync_dt.minute, _sap)

# ---------- 讀檔 ----------

def read_csv(path):
    return list(csv.reader(io.open(path, encoding='utf-8-sig')))

def load_people(src_dir):
    """作者/譯者資料庫 → people {頁面ID: {name, urls:{平台:網址}, aliases:[], dead}}、name2id {名字: 頁面ID}。
    舊版 CSV 沒有「頁面ID」欄時,ID 由 build_data() 用主表作者欄裡的網址回填(以名字對應)。"""
    people, name2id = OrderedDict(), {}
    afs = glob.glob(os.path.join(src_dir, '_authors', '*_all.csv'))
    if not afs:
        return people, name2id
    arows = read_csv(afs[0])
    ah = {n: i for i, n in enumerate(arows[0])}
    ncol = ah.get('作者名稱', 0)
    rcol = ah.get('紅標', -1)
    icol = ah.get('頁面ID', -1)
    for ar in arows[1:]:
        name = (ar[ncol] or '').strip() if ncol < len(ar) else ''
        if not name:
            continue
        pid = ar[icol].strip().replace('-', '').lower() if 0 <= icol < len(ar) else ''
        if not pid:
            pid = '__name__:' + name   # 暫用鍵,build_data() 會用主表的網址換成真 ID
        urls = {}
        for lab, col in PLATCOL.items():
            ci = ah.get(col, -1)
            if 0 <= ci < len(ar) and ar[ci].strip().startswith('http'):
                urls[lab] = ar[ci].strip()
        people[pid] = {'name': name, 'urls': urls, 'aliases': [],
                       'dead': 0 <= rcol < len(ar) and ar[rcol].strip() == 'Y'}
        name2id.setdefault(name, pid)
    return people, name2id

def load_links_map(src_dir):
    """每篇閱讀連結(由 fetch_data.py 產生):No -> {標題: [[label, url], ...]}"""
    try:
        return json.load(io.open(os.path.join(src_dir, 'article_links.json'), encoding='utf-8'))
    except Exception:
        print('(尚無 article_links.json,連結先留空)')
        return {}

def load_announcements(src_dir):
    anns = []
    anfs = glob.glob(os.path.join(src_dir, '_announce', '*_all.csv')) or glob.glob(os.path.join(src_dir, '_announce', '*.csv'))
    if anfs:
        for ar in read_csv(anfs[0])[1:]:
            content = (ar[0] or '').strip()
            if not content:
                continue
            disp, key = parse_date_only(ar[1] if len(ar) > 1 else '')
            pin = len(ar) > 2 and ar[2].strip().lower() in ('yes', 'true', '是', '✓')
            anns.append({'content': content, 'date': disp, 'dk': key, 'pin': pin})
        anns.sort(key=lambda a: (0 if a['pin'] else 1, -a['dk']))
    return anns

def load_stats(src_dir):
    try:
        return json.load(io.open(os.path.join(src_dir, 'stats.json'), encoding='utf-8'))
    except Exception:
        return None

def load_stmap(src_dir):
    """簡繁對照表 stmap.txt:兩行 = 繁字串 / 簡字串(逐字對應)。"""
    try:
        _st = io.open(os.path.join(src_dir, 'stmap.txt'), encoding='utf-8').read().splitlines()
        return tuple((_st + ['', ''])[:2])
    except Exception:
        return ('', '')

# ---------- 組資料 ----------

def merge_facet_cols(b, r, H):
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

def build_article(r, H, C, links_map):
    """一列 CSV → 一篇文章 dict(不含作者 ID 回填)。"""
    b = F.bucketize(r[C.TAGS], (r[C.NO] or '').strip())
    b = merge_facet_cols(b, r, H)
    tags = OrderedDict()
    for k, attr in SINGLE:
        v = (r[getattr(C, attr)] or '').strip()
        tags[k] = [v] if v else []
    for fac in list(F.FACETS.keys()) + F.EVENT_FACETS:
        tags[fac] = b[fac]
    parts = author_parts(r[C.AUTHOR])
    au, au_ids, tr, tr_ids = split_author_translator(parts, '譯文' in b['形式/性質'])
    ed_disp, ed_key = parse_dt(r[C.EDIT])
    cr_disp, cr_key = parse_dt(r[C.CREATE])      # 建立時間=實際收錄(新增)時間,供「最新收錄」排序
    no_s = (r[C.NO] or '').strip()
    title_s = (r[C.NAME] or '').strip()
    lm = links_map.get(no_s, {})
    links = lm.get(title_s)
    if links is None and len(lm) == 1:
        links = next(iter(lm.values()))
    links = split_links(links)
    manual_dead = 0 <= H.get('紅標', -1) < len(r) and r[H['紅標']].strip() == 'Y'
    return {
        'no': no_s,
        'name': title_s,
        'persona': (r[C.PERSONA] or '').strip(),
        'author': '、'.join(au),
        'author_ids': au_ids,          # 與 author 以「、」拆開後一一對應的 Notion 作者頁 ID(穩定鍵)
        'translator': '、'.join(tr),
        'translator_ids': tr_ids,
        'edited': ed_disp,
        'ek': ed_key,
        'created': cr_disp,
        'ck': cr_key,
        'tags': tags,
        'links': links,
        'dead': is_dead(manual_dead, links),   # 紅標,或超過一半連結已失效(大篇幅失去連結)
        'alias': (r[H['收錄篇名']].strip() if 0 <= H.get('收錄篇名', -1) < len(r) else ''),
        '_conflict': dead_conflict(manual_dead, links),
    }

def build_facets(articles):
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
    return facet_defs

def resolve_people(articles, people, name2id):
    """用主表作者欄裡的頁面 ID 補齊 people:
    - 作者庫 CSV 沒有「頁面ID」欄(舊版)→ 以名字把暫用鍵換成真 ID
    - 主表關聯到、但作者庫讀不到的作者 → 以名字補一筆(urls 空)
    - 名字沒有 ID(LOVE GAME 只有名字)→ 不能對應,ID 留空字串"""
    for a in articles:
        for names_key, ids_key in (('author', 'author_ids'), ('translator', 'translator_ids')):
            names = a[names_key].split('、') if a[names_key] else []
            for i, (nm, pid) in enumerate(zip(names, a[ids_key])):
                if not pid:
                    continue
                if pid in people:
                    continue
                tmp = name2id.get(nm)
                if tmp and tmp.startswith('__name__:') and tmp in people:
                    people[pid] = people.pop(tmp); name2id[nm] = pid
                elif pid not in people:
                    people[pid] = {'name': nm, 'urls': {}, 'aliases': [], 'dead': False}
                    name2id.setdefault(nm, pid)
    # 還留著暫用鍵的(作者庫有、但沒任何文章關聯到)→ 仍然輸出,鍵維持 __name__:名字
    return people

def build_data(src_dir='.', now=None):
    """讀 src_dir 裡的 CSV / json → (DATA, report)。report 含 dead_conflicts、重複編號、空號等給 main() 印。"""
    f = glob.glob(os.path.join(src_dir, '*176a7213548080cda25dd9e1edd5b7a4_all.csv'))[0]
    allrows = read_csv(f)
    C = F.cols(allrows[0])
    H = {n: i for i, n in enumerate(allrows[0])}   # 表頭名稱 → 欄位索引(用來讀各分面欄)
    rows = allrows[1:]
    people, name2id = load_people(src_dir)
    links_map = load_links_map(src_dir)

    articles = [build_article(r, H, C, links_map) for r in rows]
    dead_conflicts = [a['no'] for a in articles if a.pop('_conflict')]
    people = resolve_people(articles, people, name2id)
    dead_authors = [p['name'] for p in people.values() if p['dead']]   # 紅標作者(已刪帳號);相容舊前端
    # sort by No desc (newest first)
    articles.sort(key=lambda a: (-(nokey(a)[1]), a['no']))

    _mx = max((a['ek'] for a in articles), default=0)   # 資料庫更新時間 = 所有文章中最新的編輯時間
    now = now or datetime.now(timezone(timedelta(hours=8)))
    DATA = {'total': len(articles), 'facets': build_facets(articles), 'articles': articles,
            'people': people, 'announcements': load_announcements(src_dir),
            'updated': fmt_updated(_mx), 'synced': fmt_synced(now),
            'dead_authors': dead_authors, 'stats': load_stats(src_dir)}
    report = {'dead_conflicts': dead_conflicts, 'H': H}
    return DATA, report

def data_decl(DATA):
    return 'window.DATA = ' + json.dumps(DATA, ensure_ascii=False, sort_keys=True) + ';'

def render_index(tpl, DATA, stmap):
    """樣板 → index.html:注入簡繁對照表與資料(佔位符 __STMAP_T__ / __STMAP_S__ / /*__DATA__*/)。"""
    tpl = tpl.replace('__STMAP_T__', stmap[0]).replace('__STMAP_S__', stmap[1])
    return tpl.replace('/*__DATA__*/', data_decl(DATA))

STATIC_DIRS = ('src', 'styles')   # 前端程式與樣式,源頭在倉庫根目錄,建置時一起複製到輸出資料夾

def copy_static(repo_root, out_dir):
    """把 repo_root/src、repo_root/styles 複製到 out_dir(輸出就是倉庫根目錄時不動)。"""
    copied = []
    for d in STATIC_DIRS:
        s, t = os.path.join(repo_root, d), os.path.join(out_dir, d)
        if not os.path.isdir(s) or os.path.abspath(s) == os.path.abspath(t):
            continue
        if os.path.isdir(t):
            shutil.rmtree(t)
        shutil.copytree(s, t)
        copied.append(d)
    return copied

def write_site(DATA, src_dir, out_dir, repo_root=None):
    """輸出 data.js、index.html,並複製 src/、styles/。回傳 (樣板字串, 複製了哪些資料夾)。"""
    os.makedirs(out_dir, exist_ok=True)
    decl = data_decl(DATA)
    io.open(os.path.join(out_dir, 'data.js'), 'w', encoding='utf-8').write(decl)   # 也單獨輸出 data.js(供分檔部署)
    tpl = io.open(os.path.join(src_dir, 'site_template.html'), encoding='utf-8').read()
    io.open(os.path.join(out_dir, 'index.html'), 'w', encoding='utf-8').write(render_index(tpl, DATA, load_stmap(src_dir)))
    copied = copy_static(repo_root or os.path.join(src_dir, '..'), out_dir)
    return tpl, copied

# ---------- 檢查 ----------

def number_report(articles):
    """編號重複偵測 + 下一個可用號;回傳要印的行。"""
    lines = []
    _byno = OrderedDict()
    for a in articles:
        if a['no']:
            _byno.setdefault(a['no'], []).append(a['name'] or '(無標題)')
    _dups = {no: names for no, names in _byno.items() if len(names) > 1}
    _nums = [int(a['no']) for a in articles if a['no'].isdigit()]
    _reg = [n for n in _nums if n < 10000]     # 一般文(10000+ 是活動系列)
    if _dups:
        lines.append('')
        lines.append('==================== ⚠️  編號重複警告  ⚠️ ====================')
        for no in sorted(_dups, key=lambda x: (len(x), x)):
            lines.append('  No %s 重複 %d 篇:%s' % (no, len(_dups[no]), '、'.join(_dups[no])))
        lines.append('  請到 Notion 修正其中一篇的編號後再更新一次。')
        lines.append('==============================================================')
    else:
        lines.append('編號檢查:無重複 ✅')
    if _reg:
        _gaps = sorted(set(range(min(_reg), max(_reg) + 1)) - set(_reg))
        if _gaps:
            lines.append('可回填空號(%d 個):%s' % (len(_gaps), '、'.join(map(str, _gaps))))
        lines.append('目前最大編號:%d(一般文最大 %d) → 下一篇一般文建議用 #%d(或優先回填空號)'
                     % (max(_nums), max(_reg), max(_reg) + 1))
    return lines

def self_check(tpl, H, out_dir):
    """架構自檢:把「靜默失敗」變成看得到的警告。回傳警告清單(空 = 通過)。"""
    _warn = []
    # 1) 樣板端點還在不在(val 端點/計數器被改壞會導致統計或回報靜默失效);端點寫在 window.AZ_CONFIG 裡(KEY:"…")
    for _name, _pat in (('即時統計 STATS_API', r'STATS_API[:=]"https://[a-z0-9-]+--[a-z0-9]+\.web\.val\.run"'),
                        ('回報 REPORT_API', r'REPORT_API[:=]"https://[a-z0-9-]+--[a-z0-9]+\.web\.val\.run"'),
                        ('愛心/查看 REACT_API', r'REACT_API[:=]"https://[a-z0-9-]+--[a-z0-9]+\.web\.val\.run"'),
                        ('GoatCounter 追蹤碼', r'gc\.zgo\.at/count\.js')):
        if not re.search(_pat, tpl):
            _warn.append('樣板缺少 %s(統計/回報會靜默失效)' % _name)
    # 2) 主表必要欄位是否齊全(Notion 改欄名會讓對應欄整批消失)
    for _col in ('文章名稱', 'No', '上次編輯時間', '建立時間', '文章狀態', '文章篇幅', '文章類型', '結局', '紅標'):
        if _col not in H:
            _warn.append('主表缺欄位「%s」(Notion 欄名被改?該欄資料會整批消失)' % _col)
    # 3) 分面欄是否齊全
    for _fac in list(F.FACETS.keys()) + F.EVENT_FACETS:
        if _fac not in H:
            _warn.append('主表缺分面欄「%s」' % _fac)
    # 4) 簡繁對照有沒有注入成功
    if '__STMAP_T__' in tpl or '__STMAP_S__' in tpl:
        _warn.append('stmap 佔位符未被取代(簡繁互搜會壞)')
    # 5) 前端模組與樣式有沒有一起到輸出資料夾(index.html 用 <script type="module"> 引用它們)
    for d in STATIC_DIRS:
        if not os.path.isdir(os.path.join(out_dir, d)):
            _warn.append('輸出資料夾缺少 %s/(index.html 會載不到程式/樣式)' % d)
    return _warn

def main():
    # 輸出資料夾:本機預設 ../site;GitHub Action 設環境變數 SITE_OUT=.. 直接輸出到倉庫根目錄
    OUT = os.environ.get('SITE_OUT', '../site')
    DATA, report = build_data('.')
    tpl, copied = write_site(DATA, '.', OUT)
    articles = DATA['articles']
    print('site built:', len(articles), 'articles,', len(DATA['facets']), 'facets →', OUT,
          ('(複製 %s)' % '、'.join(copied)) if copied else '')
    if report['dead_conflicts']:
        print('待確認:紅標但仍有未標 ❌ 的連結 %d 篇(補 ❌ 或取消紅標):No.%s'
              % (len(report['dead_conflicts']), ', '.join(report['dead_conflicts'])))
    for line in number_report(articles):
        print(line)
    _warn = self_check(render_index(tpl, DATA, load_stmap('.')), report['H'], OUT)
    if _warn:
        print('')
        print('==================== ⚠️  架構自檢警告  ⚠️ ====================')
        for _w in _warn:
            print('  ⚠️ ' + _w)
        print('==============================================================')
    else:
        print('架構自檢:通過 ✅(端點/欄位/簡繁注入/模組複製都正常)')


if __name__ == '__main__':
    main()
