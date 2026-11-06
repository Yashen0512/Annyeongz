# -*- coding: utf-8 -*-
"""巡檢 ①:每天檢查所有原文連結是否還在、順便收集作者目前顯示名,結果記在 link_status.json,
   變更摘要寫到 check_report.json(+ 有變更時的 check_report.md,給 GitHub Issue 用)。
   **不寫 Notion**;寫回由 notion_writeback.py 讀 check_report.json 負責。只用標準庫。

   來源:article_links.json(每篇頁面內文的閱讀連結;保留鍵 __blocks__ 給寫回定位 block)
         + 作者庫 CSV 的各平台網址(fetch_data.py 產出;沒有 CSV 時退回讀 ../data.json,用 build_site.expand_data 還原)
   規則:
   - 依網域分派 checkers/{postype,lofter,ao3,aff}.py;同平台請求間隔 1.5~3 秒隨機,四個平台各一條執行緒交錯
   - 逾時 / 5xx / 429 重試 2 次,仍失敗 = unknown,不算已刪
   - 某平台前 3 筆全是「被擋」(登入牆 / Cloudflare 挑戰頁)→ 該平台本次略過(其餘連結不打,狀態不動)
   - 狀態機(advance):只有「連續兩天都 deleted」才算真的死(dead);unknown 不改變任何計數;
     已死的改為每 30 天複查一次(is_due);複查看到 ok 就復活(dead=False);
     結果帶 skipped(被限速而沒真的查:browser_checker.rate_limited_skip)連 last 都不動,下次仍排在最前面
   - 每次執行的上限(PLAT_MAX_PER_RUN,目前只有 AFF 150 筆):超過就依 link_status.json 的 last 排序、最久沒查(含沒查過)的先,
     剩下的下次再跑(prioritize;2026-11-06 實測 AFF 約 100 筆後被限速)。作者頁與作品頁同一個清單、同一套
   - 報告:新死 = dead 且 Notion 連結名稱還沒有 ❌;復活 = Notion 有 ❌ 但今天看到 ok
     (以「該是什麼狀態」為準,寫回失敗隔天會再列一次,不會漏)
   - 作者改名:同一作者(Notion 作者頁 ID)在同一平台有兩篇以上作品解析到同一個新名字、該名字不是目前名稱 /
     括號內別名 / 曾用名、該名字 / 帳號沒有同時出現在別的作者名下(合集帳號)、且作者庫該平台網址與頁面作者帳號相符
     → renames(會寫回);缺平台網址無法核對的 → rename_candidates(只列在報告,不寫回)。
     比對名字前兩邊都經 stmap.txt 簡繁折算(fold_zh,與站內搜尋同一套:繁→簡逐字對應),所以「咸魚 / 咸鱼」「百憂解 / 百忧解」視為同名、不算改名。
     以下改列「需人工確認」(rename_manual,寫進 Issue、不寫回;2026-11-05 實測誤判):
       · 同一作者同一平台在不同篇抓到兩個以上不同的新名字(「上-一只大鹅 / 下-一只大鹅」= 抓到文章標題,不是作者名)
       · 新名字像標題片段(上- / 下- / 番外 / 第N章 / (上)…,title_fragment)
   - --browser(只在站長本機):lofter / ao3 / aff 改走 browser_checker.py(Playwright 真瀏覽器),postype 照舊 urllib;
     結果形狀相同、進同一套 advance() 與 link_status.json。沒裝 Playwright / WARP 開著 / 沒有 Lofter cookie 時印提示並略過該平台。
     --browser --probe:每個平台只抓 3 筆(正常 / 已知 ❌ / 不存在)印出最終網址、狀態碼、判定、頁面前 300 字,不寫任何檔案(驗判斷規則用)。
     固定設定檔:AFF 預設用 _build/browser_profile/(有頭系統 Chrome,保留 cf_clearance 與登入);--profile aff,lofter 改平台、--no-profile 關掉、
     --profile-headless 改無頭;第一次先跑 --setup-profile(開 AFF 首頁讓站長手動登入、通過驗證,按 Enter 存檔)。
   用法:python check_links.py [--platforms postype,lofter,ao3,aff] [--no 1352,1255] [--limit N] [--verbose]
                              [--browser [--probe] [--headed] [--browser-channel chrome] [--profile aff | --no-profile] [--profile-headless]]
                             [--setup-profile]
"""
import argparse, io, json, os, random, re, sys, threading, time
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkers
from checkers._http import TransientError
import build_site as B

TZ = timezone(timedelta(hours=8))
STATE_FILE, REPORT_FILE, REPORT_MD = 'link_status.json', 'check_report.json', 'check_report.md'
DEAD_DAYS = 2            # 連續幾「天」deleted 才算真的死
RECHECK_DEAD_DAYS = 30   # 已死的每幾天複查一次
RETRIES = 2              # 逾時 / 5xx 重試次數
GAP = (1.5, 3.0)         # 同平台請求間隔(秒,隨機)
BLOCK_PROBE = 3          # 前幾筆全被擋就略過該平台
PLAT_MAX_PER_RUN = {'aff': 150}   # 每次執行每個平台最多查幾筆(沒列的不限);超過的下次再查,最久沒查的先(prioritize)
DEAD_MARK = B.DEAD_MARK
PLAT_URL_KEYS = {'postype': ('Postype',), 'lofter': ('Lofter', 'Lofter2'), 'ao3': ('AO3',), 'aff': ('AF',)}

def today_str(now=None):
    return (now or datetime.now(TZ)).strftime('%Y-%m-%d')

def days_between(a, b):
    """'YYYY-MM-DD' 兩個日期差幾天(b - a);任一空字串 → 很大的數(視為很久以前)。"""
    if not a or not b:
        return 10 ** 6
    return (datetime.strptime(b, '%Y-%m-%d') - datetime.strptime(a, '%Y-%m-%d')).days

# ---------- 狀態機(純函式,pytest 測這些) ----------

def is_due(entry, today):
    """今天要不要檢查:沒紀錄 → 要;已死且距上次檢查不到 30 天 → 不用;其餘都要。"""
    if not entry:
        return True
    if entry.get('dead') and days_between(entry.get('last', ''), today) < RECHECK_DEAD_DAYS:
        return False
    return True

def last_checked(entry):
    """排序用:上次真的查過的日期('' = 沒查過,排最前面)。"""
    return (entry or {}).get('last') or ''

def prioritize(targets, state, cap):
    """每次執行的上限:依 link_status.json 的 last 由舊到新排(沒查過的最前面、同日期維持原順序),只取前 cap 筆;
    cap 是 0 / None 就只排序不截斷。回傳 (要查的清單, 延後的筆數)。"""
    ordered = sorted(targets, key=lambda t: last_checked(state.get(t['url'])))
    if cap and len(ordered) > cap:
        return ordered[:cap], len(ordered) - cap
    return ordered, 0

def advance(entry, res, today):
    """把一次檢查結果併進紀錄。回傳新的 entry(不改原物件)。
    - skipped(被限速而沒真的查):只記 reason / code,連 last 都不動(下次 prioritize 仍排在最前面)
    - unknown:只更新 last / code / reason,status / streak / dead 都不動
    - deleted:status 變成 deleted,streak = 連續觀測到 deleted 的「天數」(同一天重跑不重複計);streak ≥ 2 → dead
    - ok / login_required:streak 同樣按天數累計;ok 且原本 dead → 復活(dead=False);ok 時更新 author_name
    - 結果帶 extra(AO3 章節進度)就原樣存進 entry['extra']"""
    e = dict(entry or {})
    st = res.get('status', 'unknown')
    if res.get('skipped'):
        e['code'], e['reason'] = res.get('code'), res.get('reason')
        return e
    e['last'], e['code'], e['reason'] = today, res.get('code'), res.get('reason')
    e.setdefault('first', today)
    if st == 'unknown':
        return e
    if e.get('status') == st:
        if e.get('counted') != today:
            e['streak'] = int(e.get('streak', 0)) + 1
    else:
        e['streak'] = 1
    e['status'], e['counted'] = st, today
    if st == 'deleted':
        if e['streak'] >= DEAD_DAYS and not e.get('dead'):
            e['dead'], e['dead_since'] = True, today
    elif st == 'ok':
        if e.get('dead'):
            e['dead'] = False
            e.pop('dead_since', None)
        if res.get('author_name'):
            e['author_name'] = res['author_name']
            if res.get('author_url'):
                e['author_url'] = res['author_url']
    if res.get('extra'):
        e['extra'] = res['extra']      # 瀏覽器模式解析到的附加資訊(AO3 章節進度 / 完結);先記錄、不寫回 Notion
    return e

def events_for(entry, marked, today):
    """這個連結今天該產生什麼事件:'new_dead'(該標 ❌ 但 Notion 還沒標)、'revived'(Notion 有 ❌ 但今天看到 ok)。"""
    if not entry:
        return None
    if entry.get('dead') and not marked:
        return 'new_dead'
    if marked and entry.get('status') == 'ok' and entry.get('last') == today and not entry.get('dead'):
        return 'revived'
    return None

# ---------- 作者改名判斷(純函式) ----------

_ZH = None
def _zh_map():
    """stmap.txt(繁字串 / 簡字串逐字對應)→ {繁: 簡};第一次用到才讀(import 不讀檔)。"""
    global _ZH
    if _ZH is None:
        t, s = B.load_stmap(os.path.dirname(os.path.abspath(__file__)))
        _ZH = dict(zip(t, s))
    return _ZH

def fold_zh(s, zh=None):
    """簡繁折算:繁體逐字換成簡體(與 src/data.js 的 foldZH 同一套表),比對名字用;顯示照原樣。"""
    m = _zh_map() if zh is None else zh
    return ''.join(m.get(c, c) for c in (s or ''))

def norm_name(s):
    return fold_zh(re.sub(r'\s+', '', (s or ''))).casefold()

def same_name(a, b):
    """兩個名字只差簡繁 / 大小寫 / 空白 → True。"""
    return norm_name(a) == norm_name(b)

_NUM = r'[0-9０-９一二三四五六七八九十百千零〇兩两]+'
TITLE_FRAGMENT = re.compile(
    r'^[上中下前後后][\-－—–_·・:：]'                     # 上-一只大鹅
    r'|[\-－—–_·・][上中下前後后完]$'                       # 一只大鹅-下
    r'|[(（【\[「][上中下前後后完續续][)）】\]」]'          # (上)【下】
    r'|番外|第\s*' + _NUM + r'\s*[章話话回集篇部節节卷幕季]'
    r'|[上中下前後后]篇|完[結结]篇|[終终最][章話话]|序章'
    r'|\bchapter\s*\d|\bch\.?\s*\d|\bpart\s*\d|\bep\.?\s*\d', re.I)

def title_fragment(name):
    """名字裡像文章標題片段的字樣(上- / 下- / 番外 / 第N章…)→ 回該片段;正常筆名回 ''。"""
    m = TITLE_FRAGMENT.search((name or '').strip())
    return m.group(0) if m else ''

def rename_hold_reason(old, new, known=()):
    """改名寫回前的保險(check_links 與 notion_writeback 都用):簡繁 / 大小寫相同、或新名字像標題片段 → 回原因字串;可以寫回回 ''。"""
    if not (new or '').strip():
        return '新名字是空的'
    if same_name(old, new) or norm_name(new) in set(known or ()):
        return '只差簡繁 / 大小寫,不算改名'
    frag = title_fragment(new)
    if frag:
        return '新名字含標題片段「%s」,可能抓到文章標題' % frag
    return ''

def known_names(person):
    """作者目前名稱本身、括號內外各段(「노네임(noname)」→ 노네임、noname)、斜線 / 頓號分段、曾用名。"""
    out = set()
    name = person.get('name', '')
    for raw in [name] + list(person.get('aliases') or []):
        out.add(norm_name(raw))
        for part in re.split(r'[()（）/／、|]', raw):
            if part.strip():
                out.add(norm_name(part))
    out.discard('')
    return out

def handle_of(platform, url):
    """各平台網址 → 可比對的帳號識別;認不出來回 ''。"""
    u = (url or '').strip()
    if not u:
        return ''
    sp = urlsplit(u if '://' in u else 'https://' + u)
    host, path = (sp.hostname or '').lower(), sp.path or ''
    if platform == 'postype':
        m = re.search(r'@([A-Za-z0-9_.\-]+)', u)
        if m:
            return m.group(1).lower()
        if host.endswith('.postype.com') and host != 'www.postype.com':
            return host.split('.')[0]
        return ''
    if platform == 'lofter':
        return host.split('.')[0] if host.endswith('.lofter.com') and host != 'www.lofter.com' else ''
    if platform == 'ao3':
        m = re.search(r'/users/([^/?#]+)', path)
        return m.group(1).lower() if m else ''
    if platform == 'aff':
        m = re.search(r'/profile/view/(\d+)', path)
        return m.group(1) if m else ''
    return ''

def person_handles(platform, person):
    hs = set()
    for key in PLAT_URL_KEYS.get(platform, ()):
        h = handle_of(platform, (person.get('urls') or {}).get(key, ''))
        if h:
            hs.add(h)
    return hs

def observed_handles(platform, author_url, work_url):
    hs = set()
    for u in (author_url, work_url):
        h = handle_of(platform, u)
        if h:
            hs.add(h)
    return hs

def detect_renames(observations, people, articles, manual=None):
    """observations: [{no, platform, name, author_url, url}];articles: {no: article};people: {pid: person}。
    回傳 (renames, candidates),元素 {pid, old, new, platform, nos}。
    疑似抓錯來源的(同一作者同平台抓到多個不同新名字、新名字像標題片段)不進上面兩個清單,
    改 append 到 manual(有給的話):{pid, old, platform, names: [{new, nos}], why}。"""
    by_pid = defaultdict(lambda: defaultdict(set))        # (pid) → (platform, norm new) → {no}
    display = {}                                          # (platform, norm) → 原始顯示名
    name_owner = defaultdict(set)                         # (platform, norm name) → {pid}
    handle_owner = defaultdict(set)                       # (platform, handle) → {pid}
    obs_handles = defaultdict(set)                        # (pid, platform, norm) → 頁面上看到的帳號
    for ob in observations:
        a = articles.get(ob['no'])
        if not a or not ob.get('name'):
            continue
        ids = [i for i in (a.get('author_ids') or []) if i]
        if len(a.get('author_ids') or []) != 1 or a.get('translator_ids') or len(ids) != 1:
            continue   # 只看單一作者、無譯者、且有穩定 ID 的作品
        pid, plat, nn = ids[0], ob['platform'], norm_name(ob['name'])
        if pid not in people:
            continue
        by_pid[pid][(plat, nn)].add(ob['no'])
        display[(plat, nn)] = ob['name'].strip()
        name_owner[(plat, nn)].add(pid)
        hs = observed_handles(plat, ob.get('author_url', ''), ob.get('url', ''))
        obs_handles[(pid, plat, nn)] |= hs
        for h in hs:
            handle_owner[(plat, h)].add(pid)
    renames, candidates = [], []
    sort_nos = lambda nos: sorted(nos, key=lambda x: (len(x), x))
    held = []
    def hold(pid, plat, items, why):
        held.append({'pid': pid, 'old': people[pid]['name'], 'platform': plat, 'why': why,
                     'names': [{'new': display[(plat, nn)], 'nos': sort_nos(nos)} for nn, nos in items]})
    for pid, seen in by_pid.items():
        person = people[pid]
        kn = known_names(person)
        # 新名字 = 不是已知名稱、不是合集 / 轉載帳號(同名掛在多位作者底下)、
        # 也不是在別人帳號上看到的(作者庫有該平台網址、頁面帳號卻對不上 = 轉載)的;依平台分組
        fresh = defaultdict(list)
        for (plat, nn), nos in seen.items():
            if nn in kn or len(name_owner[(plat, nn)]) > 1:
                continue
            ph, oh = person_handles(plat, person), obs_handles[(pid, plat, nn)]
            if ph and oh and not (ph & oh):
                continue
            fresh[plat].append((nn, nos))
        for plat, items in fresh.items():
            items.sort(key=lambda x: (-len(x[1]), x[0]))
            if len(items) > 1:      # 同一作者在不同篇抓到不同新名字 → 抓錯來源(例如文章標題的上下集),不寫回
                hold(pid, plat, items, '同一作者在不同篇抓到 %d 個不同的新名字,可能抓錯來源(文章標題?)' % len(items))
                continue
            nn, nos = items[0]
            if len(nos) < 2:
                continue
            frag = title_fragment(display[(plat, nn)])
            if frag:
                hold(pid, plat, items, '新名字含標題片段「%s」,可能抓到文章標題' % frag)
                continue
            ph = person_handles(plat, person)
            oh = obs_handles[(pid, plat, nn)]
            item = {'pid': pid, 'old': person['name'], 'new': display[(plat, nn)], 'platform': plat, 'nos': sort_nos(nos)}
            if ph and oh and (ph & oh):
                if any(len(handle_owner[(plat, h)]) > 1 for h in (ph & oh)):
                    continue   # 這個帳號同時出現在別的作者名下 → 共用帳號,不動
                renames.append(item)
            elif ph and oh:
                continue       # 作者庫有該平台網址但帳號對不上 → 不是這位作者的帳號(合集 / 轉載)
            else:
                candidates.append(item)   # 無法核對帳號 → 只列出,不寫回
    key = lambda r: (r['platform'], r['old'], r['new'])
    if manual is not None:
        manual.extend(sorted(held, key=lambda r: (r['platform'], r['old'])))
    return sorted(renames, key=key), sorted(candidates, key=key)

# ---------- 讀資料 ----------

def load_json(path, default):
    try:
        return json.load(io.open(path, encoding='utf-8'))
    except Exception:
        return default

def load_site_data(src_dir):
    """優先用 fetch_data.py 產出的 CSV 走 build_site.build_data();沒有 CSV 就退回讀 ../data.json(精簡格式,expand_data 還原)。
    回傳 (articles_by_no, people)。"""
    import glob
    if glob.glob(os.path.join(src_dir, '*%s_all.csv' % '176a7213548080cda25dd9e1edd5b7a4')):
        DATA, _ = B.build_data(src_dir)
    else:
        djs = os.path.join(src_dir, '..', 'data.json')
        DATA = B.expand_data(json.load(io.open(djs, encoding='utf-8')))
        print('(沒有 Notion CSV,改用 %s 的作者 / 文章資料)' % os.path.relpath(djs))
    return {a['no']: a for a in DATA['articles']}, DATA['people']

def collect_targets(links_json, articles, people, platforms, only_nos=None):
    """要檢查的網址清單(同一網址只查一次,refs 列出它出現在哪些地方)。
    refs 元素:{'kind':'article','no','title','label','marked','block'} 或 {'kind':'author','pid','name','key'}"""
    targets = OrderedDict()
    blocks = links_json.get('__blocks__') if isinstance(links_json.get('__blocks__'), dict) else {}
    for no, by_title in links_json.items():
        if no.startswith('__') or not isinstance(by_title, dict):
            continue
        if only_nos and no not in only_nos:
            continue
        a = articles.get(no) if isinstance(articles, dict) else None
        for title, lst in by_title.items():
            # article_links.json 若殘留舊標題(改名 / 改號前那頁的連結),只看目前標題那組,跟 build_site 選連結的規則一致;
            # fetch_data.merge_links 已會清掉,這裡再守一道,免得把別篇的連結算在這個 No 頭上
            if a and len(by_title) > 1 and title != (a.get('name') or ''):
                continue
            for item in lst or []:
                lab, url = item[0], item[1]
                plat = checkers.platform_of(url)
                if not plat or plat not in platforms:
                    continue
                pos = (blocks.get(no) or {}).get('links', {}).get(url)
                t = targets.setdefault(url, {'url': url, 'platform': plat, 'refs': []})
                t['refs'].append({'kind': 'article', 'no': no, 'title': title, 'label': lab,
                                  'marked': DEAD_MARK in lab, 'block': pos,
                                  'page': (blocks.get(no) or {}).get('page')})
    if not only_nos:
        for pid, person in people.items():
            for key, url in (person.get('urls') or {}).items():
                plat = checkers.platform_of(url)
                if not plat or plat not in platforms:
                    continue
                t = targets.setdefault(url, {'url': url, 'platform': plat, 'refs': []})
                t['refs'].append({'kind': 'author', 'pid': pid, 'name': person.get('name', ''), 'key': key})
    return list(targets.values())

# ---------- 抓 ----------

def check_with_retry(url, sleep=time.sleep):
    last = None
    for attempt in range(RETRIES + 1):
        try:
            return checkers.check(url)
        except TransientError as e:
            last = e
            if attempt < RETRIES:
                sleep(random.uniform(*GAP))
    return {'status': 'unknown', 'author_name': None, 'reason': 'transient:%s' % last, 'code': None, 'final': url}

def run_platform(plat, targets, results, lock, verbose, sleep=time.sleep, checker=check_with_retry):
    """一個平台一條執行緒:逐筆檢查、隨機間隔;前 BLOCK_PROBE 筆全被擋 → 略過其餘。"""
    stat = {'checked': 0, 'blocked': False, 'skipped': 0}
    blocked_head = 0
    for i, t in enumerate(targets):
        res = checker(t['url'])
        with lock:
            results[t['url']] = res
        stat['checked'] += 1
        if verbose or res['status'] not in ('ok',):
            print('  [%s] %-14s %s  %s' % (plat, res['status'] + ('(' + str(res.get('reason')) + ')' if res.get('reason') else ''),
                                           t['url'], res.get('author_name') or ''), flush=True)
        if res.get('blocked'):
            blocked_head += 1
            if blocked_head >= BLOCK_PROBE and stat['checked'] == blocked_head:
                stat['blocked'] = True
                stat['skipped'] = len(targets) - stat['checked']
                print('  [%s] 前 %d 筆全部被擋(%s)→ 本次略過此平台其餘 %d 筆' % (plat, blocked_head, res.get('reason'), stat['skipped']), flush=True)
                break
        if i < len(targets) - 1:
            sleep(random.uniform(*GAP))
    return stat

# ---------- 報告 ----------

def build_report(today, targets, results, state, articles, people, plat_stats):
    rep = {'date': today, 'generated': datetime.now(TZ).isoformat(timespec='seconds'),
           'platforms': {}, 'new_dead': [], 'revived': [], 'renames': [], 'rename_candidates': [], 'rename_manual': [],
           'author_pages': {'deleted': [], 'revived': []}, 'counts': defaultdict(int)}
    for plat, st in plat_stats.items():
        rep['platforms'][plat] = dict(st, label=checkers.PLATFORM_LABEL[plat])
    observations = []
    for t in targets:
        url, e = t['url'], state.get(t['url'])
        res = results.get(url)
        if res:
            rep['counts'][res['status']] += 1
        if not e:
            continue
        for ref in t['refs']:
            if ref['kind'] == 'article':
                ev = events_for(e, ref['marked'], today)
                if ev:
                    rep[ev].append({'url': url, 'platform': t['platform'], 'no': ref['no'], 'title': ref['title'],
                                    'label': ref['label'], 'reason': e.get('reason'), 'code': e.get('code'),
                                    'streak': e.get('streak'), 'dead_since': e.get('dead_since'),
                                    'block': ref.get('block'), 'page': ref.get('page')})
                if res and res.get('status') == 'ok' and res.get('author_name'):
                    observations.append({'no': ref['no'], 'platform': t['platform'], 'name': res['author_name'],
                                         'author_url': res.get('author_url', ''), 'url': url})
            else:
                if e.get('dead') and res and res.get('status') == 'deleted':
                    rep['author_pages']['deleted'].append({'pid': ref['pid'], 'name': ref['name'], 'platform': t['platform'],
                                                           'url': url, 'streak': e.get('streak')})
    rep['renames'], rep['rename_candidates'] = detect_renames(observations, people, articles, rep['rename_manual'])
    rep['counts'] = dict(rep['counts'])
    for k in ('new_dead', 'revived'):
        rep[k].sort(key=lambda x: (len(x['no']), x['no'], x['url']))
    rep['has_changes'] = bool(rep['new_dead'] or rep['revived'] or rep['renames'] or rep['rename_manual'])
    return rep

RENAME_MANUAL_HEAD = '### 需人工確認:作者改名(疑似抓錯名字,未寫回 Notion)'

def rename_manual_lines(items):
    """Issue 內文「需人工確認」的改名段(check_links 的 rename_manual、notion_writeback 寫回前擋下的都用這個格式)。"""
    if not items:
        return []
    L = ['', RENAME_MANUAL_HEAD]
    for r in items:
        names = r.get('names') or [{'new': r.get('new', ''), 'nos': r.get('nos') or []}]
        got = ' / '.join('「%s」(No.%s)' % (x['new'], '、'.join(x['nos'])) for x in names)
        L.append('- %s(%s):抓到 %s — %s' % (r['old'], checkers.PLATFORM_LABEL.get(r['platform'], r['platform']), got, r['why']))
    return L

def report_markdown(rep):
    """GitHub Issue 內文(分「已刪」「復活」「改名」三段;另附作者頁與平台狀態)。"""
    L = ['巡檢日期:%s(台北)' % rep['date'], '']
    def link_lines(items):
        return ['- No.%s《%s》%s — %s(%s%s)' % (x['no'], x['title'], x['label'].replace(DEAD_MARK, '').strip(), x['url'],
                                             checkers.PLATFORM_LABEL[x['platform']],
                                             ';HTTP %s' % x['code'] if x.get('code') else '') for x in items] or ['(無)']
    L += ['## 已刪'] + link_lines(rep['new_dead']) + ['']
    L += ['## 復活'] + link_lines(rep['revived']) + ['']
    rn = ['- 改名:%s → %s(%s);依據 No.%s' % (r['old'], r['new'], checkers.PLATFORM_LABEL[r['platform']], '、'.join(r['nos']))
          for r in rep['renames']]
    L += ['## 改名'] + (rn or ['(無)'])
    if rep['rename_candidates']:
        L += ['', '### 待確認的改名候選(作者庫沒有該平台網址可核對,未寫回)']
        L += ['- %s → %s(%s);依據 No.%s' % (r['old'], r['new'], checkers.PLATFORM_LABEL[r['platform']], '、'.join(r['nos']))
              for r in rep['rename_candidates']]
    L += rename_manual_lines(rep.get('rename_manual'))
    if rep['author_pages']['deleted']:
        L += ['', '### 作者頁連結失效(請人工確認是否已刪帳號 → 紅標)']
        L += ['- %s:%s(%s)' % (x['name'], x['url'], checkers.PLATFORM_LABEL[x['platform']]) for x in rep['author_pages']['deleted']]
    L += ['', '### 平台狀態']
    for plat, st in rep['platforms'].items():
        L.append('- %s:檢查 %d 筆%s%s' % (st['label'], st['checked'], ';被擋,略過 %d 筆' % st['skipped'] if st.get('blocked') else '',
                                        ';' + st['note'] if st.get('note') else ''))
    return '\n'.join(L) + '\n'

# ---------- 主流程 ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description='原文連結巡檢(不寫 Notion)')
    ap.add_argument('--platforms', default='postype,lofter,ao3,aff', help='要檢查的平台,逗號分隔')
    ap.add_argument('--no', default='', help='只檢查這些編號的連結(逗號分隔;測試用)')
    ap.add_argument('--limit', type=int, default=0, help='每個平台最多檢查幾筆(測試用)')
    ap.add_argument('--src', default='.', help='_build 資料夾(article_links.json / CSV 所在)')
    ap.add_argument('--state', default=STATE_FILE)
    ap.add_argument('--report', default=REPORT_FILE)
    ap.add_argument('--verbose', action='store_true')
    ap.add_argument('--browser', action='store_true', help='lofter / ao3 / aff 改用 Playwright 真瀏覽器抓(只在本機;需 pip install playwright)')
    ap.add_argument('--probe', action='store_true', help='搭配 --browser:每平台只抓 3 筆樣本印出判斷依據,不寫任何檔案')
    ap.add_argument('--headed', action='store_true', help='搭配 --browser:開有頭的瀏覽器視窗(除錯用)')
    ap.add_argument('--browser-channel', default='', help="搭配 --browser:Playwright 的 channel,例如 chrome(用系統 Chrome)或留空用內建 Chromium;也套用到固定設定檔")
    ap.add_argument('--profile', default='aff', help='搭配 --browser:走固定設定檔 _build/browser_profile/ 的平台(逗號分隔,預設 aff)')
    ap.add_argument('--no-profile', action='store_true', help='搭配 --browser:不用固定設定檔(AFF 也走一般的無頭瀏覽器)')
    ap.add_argument('--profile-headless', action='store_true', help='搭配 --browser:固定設定檔改用無頭模式(預設有頭,無頭容易被 Cloudflare 認出來)')
    ap.add_argument('--setup-profile', action='store_true', help='開有頭 Chrome 到 AFF 首頁,手動登入、通過驗證後按 Enter 存成固定設定檔,然後結束')
    args = ap.parse_args(argv)
    if args.probe and not args.browser:
        ap.error('--probe 要搭配 --browser')
    if args.setup_profile:
        import browser_checker as BC
        ok = BC.setup_profile(args.src, channel=args.browser_channel)
        if not ok:
            raise SystemExit(1)
        return None

    platforms = [p.strip() for p in args.platforms.split(',') if p.strip() in checkers.PLATFORMS]
    BC, pre, browser_plats = None, None, []
    if args.browser:
        import browser_checker as BC
        browser_plats = [p for p in platforms if p in BC.PLATFORMS]
        prof_plats = () if args.no_profile else tuple(p.strip() for p in args.profile.split(',') if p.strip())
        pre = BC.preflight(args.src, browser_plats, profile_platforms=prof_plats,
                           profile_headless=args.profile_headless, profile_channel=args.browser_channel)
    http_plats = [p for p in platforms if p not in browser_plats]
    only = set(x.strip() for x in args.no.split(',') if x.strip()) or None
    today = today_str()
    links_json = load_json(os.path.join(args.src, 'article_links.json'), {})
    if not links_json:
        raise SystemExit('找不到 article_links.json(先跑 fetch_data.py)')
    articles, people = load_site_data(args.src)
    state_path = os.path.join(args.src, args.state)
    state = load_json(state_path, {})
    meta = state.pop('__meta__', {})

    targets = collect_targets(links_json, articles, people, platforms, only)
    if args.probe:
        print('--probe:只抓樣本、不寫任何檔案(平台:%s)' % '、'.join(browser_plats), flush=True)
        BC.probe(targets, state, browser_plats, pre, headed=args.headed, channel=args.browser_channel)
        return None
    due = [t for t in targets if is_due(state.get(t['url']), today)]
    by_plat = defaultdict(list)
    for t in due:
        by_plat[t['platform']].append(t)
    deferred = {}
    for p, cap in PLAT_MAX_PER_RUN.items():
        if by_plat.get(p):
            by_plat[p], deferred[p] = prioritize(by_plat[p], state, cap)
    if args.limit:
        for p in by_plat:
            by_plat[p] = by_plat[p][:args.limit]
    print('巡檢 %s:連結 %d 筆(今天要查 %d 筆:%s)' % (
        today, len(targets), sum(len(v) for v in by_plat.values()),
        '、'.join('%s %d' % (checkers.PLATFORM_LABEL[p], len(by_plat[p])) for p in platforms if by_plat.get(p))), flush=True)
    for p, n in deferred.items():
        if n:
            print('  %s 今天到期 %d 筆,每次最多查 %d 筆(最久沒查的先),其餘 %d 筆下次再查' % (
                checkers.PLATFORM_LABEL[p], len(by_plat[p]) + n, PLAT_MAX_PER_RUN[p], n), flush=True)

    results, lock, plat_stats, threads = {}, threading.Lock(), {}, []
    def worker(p):
        plat_stats[p] = run_platform(p, by_plat[p], results, lock, args.verbose)
    def browser_worker():
        # Playwright sync API 要在同一條執行緒上開、用、關,所以三個瀏覽器平台在這一條執行緒依序跑;Postype 的 urllib 執行緒照舊並行
        plat_stats.update(BC.run_all(pre, by_plat, browser_plats, results, lock, args.verbose,
                                     headed=args.headed, channel=args.browser_channel))
    if browser_plats:
        th = threading.Thread(target=browser_worker, daemon=True)
        th.start(); threads.append(th)
    for p in http_plats:
        if by_plat.get(p):
            th = threading.Thread(target=worker, args=(p,), daemon=True)
            th.start(); threads.append(th)
        else:
            plat_stats[p] = {'checked': 0, 'blocked': False, 'skipped': 0}
    for th in threads:
        th.join()

    for url, res in results.items():
        state[url] = advance(state.get(url), res, today)
        state[url]['platform'] = checkers.platform_of(url)
    rep = build_report(today, targets, results, state, articles, people, plat_stats)

    out = OrderedDict([('__meta__', {'updated': rep['generated'], 'date': today, 'platforms': plat_stats,
                                     'runs': int(meta.get('runs', 0)) + 1})])
    for url in sorted(state):
        out[url] = state[url]
    io.open(state_path, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=0, sort_keys=False))
    io.open(os.path.join(args.src, args.report), 'w', encoding='utf-8').write(json.dumps(rep, ensure_ascii=False, indent=1))
    md_path = os.path.join(args.src, REPORT_MD)
    if rep['has_changes']:
        io.open(md_path, 'w', encoding='utf-8').write(report_markdown(rep))
    elif os.path.exists(md_path):
        os.remove(md_path)

    print('')
    print('結果:', ', '.join('%s %d' % kv for kv in sorted(rep['counts'].items())) or '(沒有檢查任何連結)')
    for p, st in plat_stats.items():
        if st.get('blocked'):
            print('  ⚠️ %s 被擋(略過 %d 筆%s)' % (checkers.PLATFORM_LABEL[p], st['skipped'], ';' + st['note'] if st.get('note') else ''))
    print('新死 %d、復活 %d、改名 %d(候選 %d、需人工確認 %d)、作者頁失效 %d' % (
        len(rep['new_dead']), len(rep['revived']), len(rep['renames']), len(rep['rename_candidates']), len(rep['rename_manual']),
        len(rep['author_pages']['deleted'])))
    for x in rep['new_dead']:
        print('  ❌ 新死 No.%s《%s》%s %s' % (x['no'], x['title'], x['label'], x['url']))
    for x in rep['revived']:
        print('  ♻️ 復活 No.%s《%s》%s %s' % (x['no'], x['title'], x['label'], x['url']))
    for r in rep['renames']:
        print('  ✏️ 改名 %s → %s(%s;No.%s)' % (r['old'], r['new'], r['platform'], '、'.join(r['nos'])))
    for r in rep['rename_manual']:
        print('  ✋ 需人工確認 %s(%s):%s — %s' % (r['old'], r['platform'], ' / '.join(
            '%s(No.%s)' % (x['new'], '、'.join(x['nos'])) for x in r['names']), r['why']))
    for r in rep['rename_candidates']:
        print('  ❔ 候選 %s → %s(%s;No.%s;作者庫無該平台網址可核對)' % (r['old'], r['new'], r['platform'], '、'.join(r['nos'])))
    print('已寫入 %s、%s%s' % (args.state, args.report, '、' + REPORT_MD if rep['has_changes'] else ''))
    return rep

if __name__ == '__main__':
    main()
