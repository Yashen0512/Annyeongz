# -*- coding: utf-8 -*-
"""隱形版權水印 ③:canary(金絲雀)。
   從主表挑幾篇「編號 + 篇名」的對應關係,用一把只有站長知道的祕密(HMAC-SHA256)算出一組 hash,
   建置時埋進 data.json 的 `_canary` 陣列;哪幾篇、祕密是什麼只記在本機 `_build/canary.json`(git 忽略)。
   之後拿別站的資料來 `check`:他們的資料裡若有同一組 hash(整包搬走 data.json),或用我們的祕密對他們的
   編號 + 篇名重算也對得上(搬走了編輯關係),就是證據。沒有祕密的人看不出哪幾篇是 canary,也偽造不了。
   只用標準庫;所有判斷都是純函式,CLI 在 main()。

   用法(在 _build/ 執行):
     python canary.py init                 產生祕密 → canary.json(已存在就不動)
     python canary.py show [--data 路徑]    列出目前會埋的幾篇與 hash(預設讀 ../data.json,並更新 canary.json 的 items)
     python canary.py check <別站檔案>      比對別站的 data.json / 任何 JSON / 純文字
   建置:build_site.py 讀到祕密(環境變數 CANARY_SECRET 或本機 canary.json)才會埋 `_canary`,沒有就略過。"""
import hashlib, hmac, io, json, os, re, secrets, sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
FILE_NAME = 'canary.json'
ENV = 'CANARY_SECRET'
K = 5              # 埋幾篇
HASH_LEN = 24      # hex 字元數(96 bit,夠辨識又不佔 data.json)

# ---------- 純函式 ----------

def digest(secret, no, name):
    """一組「編號 + 篇名」的 canary hash:HMAC-SHA256(祕密, 'no\\tname') 取前 HASH_LEN 個 hex 字元。"""
    msg = ('%s\t%s' % (no, name)).encode('utf-8')
    return hmac.new(secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()[:HASH_LEN]

def _rank(secret, no):
    return hmac.new(secret.encode('utf-8'), ('pick\t%s' % no).encode('utf-8'), hashlib.sha256).hexdigest()

def pick(articles, secret, k=K):
    """挑 k 篇:只看有編號、有篇名、原文沒刪的,依 HMAC(祕密, 編號) 排序取前 k 篇。
    同一把祕密、同一批文章 → 永遠挑同一組(本機與 Actions 建置結果一致);外人看不出挑選規則。"""
    cands = [a for a in articles if a.get('no') and a.get('name') and not a.get('dead')]
    cands.sort(key=lambda a: (_rank(secret, a['no']), a['no']))
    return cands[:k]

def items(DATA, secret, k=K):
    """會埋進 data.json 的幾篇:[{no, name, hash}](記在本機 canary.json 用)。"""
    return [{'no': a['no'], 'name': a['name'], 'hash': digest(secret, a['no'], a['name'])}
            for a in pick(DATA.get('articles') or [], secret, k)]

def canary_list(DATA, secret, k=K):
    """data.json 的 `_canary` 值:hash 陣列,排序過(順序不洩漏挑選順位)。"""
    return sorted(x['hash'] for x in items(DATA, secret, k))

def new_secret():
    return secrets.token_hex(24)

def pairs_of(obj):
    """從任何 JSON 物件裡盡量撈出 (編號, 篇名) 對:接受完整形狀(no / name)、精簡形狀(n / m)、
    任意巢狀的 list / dict。回傳去重後的 list。"""
    out, seen = [], set()
    def walk(x):
        if isinstance(x, dict):
            no = x.get('no', x.get('n')); name = x.get('name', x.get('m'))
            if no is not None and isinstance(name, str) and name and isinstance(no, (str, int)):
                key = (str(no), name)
                if key not in seen:
                    seen.add(key); out.append(key)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return out

def compare(canary, foreign_obj=None, foreign_text=''):
    """比對別站資料。canary = 本機 canary.json 的內容({secret, items});
    foreign_obj = 對方的 JSON(可為 None),foreign_text = 對方檔案原文(純文字比對 hash / _origin 標記)。
    回傳 {'hashes': 對方內容裡出現的我方 hash 清單, 'pairs': 對方資料裡與我方 canary 相同的 (no, name),
          'recomputed': 對方資料的所有 (no, name) 以我方祕密重算後、剛好出現在對方自己內容裡的 hash 數(= 對方的 _canary 是用我們的祕密算的),
          'origin': 對方內容裡的 _origin 標記(沒有就 None), 'verdict': 'copied' | 'pairs' | 'clean'}。"""
    secret = canary['secret']
    mine = {x['hash']: (x['no'], x['name']) for x in canary.get('items', [])}
    text = foreign_text or ''
    hashes = sorted(h for h in mine if h in text)
    fpairs = pairs_of(foreign_obj) if foreign_obj is not None else []
    pairs = sorted(p for p in fpairs if digest(secret, p[0], p[1]) in mine)
    recomputed = sum(1 for p in fpairs if digest(secret, p[0], p[1]) in text)
    m = re.search(r'annyeongz-平行宇宙-原創編輯-[0-9A-Za-z-]+', text)
    origin = m.group(0) if m else None
    verdict = 'copied' if (hashes or recomputed or origin) else ('pairs' if pairs else 'clean')
    return {'hashes': hashes, 'pairs': pairs, 'recomputed': recomputed, 'origin': origin, 'verdict': verdict}

# ---------- 本機檔案 ----------

def _path(path=None):
    return path or os.path.join(HERE, FILE_NAME)

def load_secret(src_dir=None):
    """祕密的來源:環境變數 CANARY_SECRET(Actions 的 secret)→ <src_dir>/canary.json 的 secret → None(不埋)。src_dir 預設 _build/。"""
    src_dir = src_dir or HERE
    s = (os.environ.get(ENV) or '').strip()
    if s:
        return s
    p = os.path.join(src_dir, FILE_NAME)
    if os.path.isfile(p):
        try:
            s = (json.load(io.open(p, encoding='utf-8')).get('secret') or '').strip()
        except (ValueError, AttributeError):
            s = ''
        return s or None
    return None

def load_file(path=None):
    return json.load(io.open(_path(path), encoding='utf-8'))

def record(DATA, secret, path=None, k=K):
    """把目前埋的幾篇寫進本機 canary.json({secret, k, items, updated});已有的 history 保留並追加舊 items
    (篇名改了或挑選換人時,舊 hash 仍可比對)。回傳寫入的 dict。"""
    path = _path(path)
    old = {}
    if os.path.isfile(path):
        try:
            old = load_file(path)
        except ValueError:
            old = {}
    cur = items(DATA, secret, k)
    history = [x for x in old.get('history', []) if x not in cur]
    for x in old.get('items', []):
        if x not in cur and x not in history:
            history.append(x)
    doc = {'secret': secret, 'k': k, 'items': cur, 'history': history,
           'updated': datetime.now(timezone(timedelta(hours=8))).strftime('%Y/%m/%d %H:%M')}
    io.open(path, 'w', encoding='utf-8').write(json.dumps(doc, ensure_ascii=False, indent=1))
    return doc

def load_foreign(path):
    """讀別站檔案:JSON 解析得了就回 (obj, 原文),解析不了就 (None, 原文)。"""
    text = io.open(path, encoding='utf-8', errors='replace').read()
    try:
        obj = json.loads(text)
    except ValueError:
        obj = None
    if isinstance(obj, dict) and obj.get('v') == 2:
        try:
            sys.path.insert(0, HERE)
            import build_site
            obj = build_site.expand_data(obj)
        except Exception:
            pass
    return obj, text

def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    cmd = argv[0] if argv else ''
    path = _path()
    if cmd == 'init':
        if os.path.isfile(path) and '--force' not in argv:
            print('已有 %s,不動(要重做請加 --force;換祕密後舊 hash 就比不出來了)' % path); return 0
        io.open(path, 'w', encoding='utf-8').write(json.dumps({'secret': new_secret(), 'k': K, 'items': [], 'history': []}, ensure_ascii=False, indent=1))
        print('已建立 %s(git 忽略;請自行備份這把祕密)。下一步:python canary.py show,或直接建置。' % path); return 0
    if cmd == 'show':
        secret = load_secret(HERE)
        if not secret:
            print('沒有祕密:先 python canary.py init,或設環境變數 %s' % ENV); return 1
        data_path = argv[argv.index('--data') + 1] if '--data' in argv else os.path.join(HERE, '..', 'data.json')
        DATA, _ = load_foreign(data_path)
        doc = record(DATA, secret, path) if os.path.isfile(path) else {'items': items(DATA, secret)}
        for x in doc['items']:
            print('  #%s  %s  %s' % (x['no'], x['hash'], x['name']))
        print('共 %d 篇;data.json 的 _canary 會是這些 hash 排序後的陣列。' % len(doc['items'])); return 0
    if cmd == 'check' and len(argv) >= 2:
        canary = load_file(path)
        canary['items'] = canary.get('items', []) + canary.get('history', [])
        obj, text = load_foreign(argv[1])
        r = compare(canary, obj, text)
        print('_origin 標記:', r['origin'] or '無')
        print('出現我方 canary hash:%d 個 %s' % (len(r['hashes']), r['hashes']))
        print('對方 (編號, 篇名) 以我方祕密重算後出現在對方內容裡:%d 筆' % r['recomputed'])
        print('對方資料與我方 canary 相同的 (編號, 篇名):%d 筆 %s' % (len(r['pairs']), r['pairs']))
        print({'copied': '判定:整包搬走了 data.json(或帶走了標記)', 'pairs': '判定:編號 + 篇名的對應關係與本站相同(可能搬走了編輯內容)',
               'clean': '判定:沒有比對到'}[r['verdict']]); return 0
    print(__doc__); return 1

if __name__ == '__main__':
    sys.exit(main())
