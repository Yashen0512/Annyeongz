# -*- coding: utf-8 -*-
"""瀏覽器巡檢模式(check_links.py --browser 用):用 Playwright 開真的 Chromium 抓 Lofter / AO3 / Asianfanfics。
   這三個平台用 urllib 從任何 IP 都會被登入牆 / Cloudflare 擋(見 checkers/{lofter,ao3,aff}.py 檔頭),
   真瀏覽器才過得去;所以這個模式**只在站長本機跑**,GitHub Actions 的 check_links.yml 不加 --browser,照舊只跑 Postype。
   Playwright 是可選相依(requirements.txt 註解裡的那行):沒裝就 is_available() = False,check_links.py 印提示並略過這三個平台。

   判斷邏輯全部在純函式 classify(platform, final_url, status, html, url='', error='') → 跟 checkers 同形狀的結果
   {status, author_name, reason, code, final, …};pytest 用 tests/fixtures/html/ 的合成樣本直接測,不碰瀏覽器。
   2026-11-04 站長本機 `--probe` 實測(headless Chromium 與系統 Chrome 結果相同):Lofter 四筆判定全對(404 頁 `<title>404 Not Found`、
   「哎呀，页面走丢了...」「你查找的链接可能已损毁，或页面已被移除」);AFF 第一筆 200 正常、第二筆起 403 繁中版 Cloudflare 驗證頁
   (`<title>請稍候...`、「正在執行安全驗證」「Enable JavaScript and cookies to continue」「Ray ID」「Performance and Security by Cloudflare」);
   AO3 全站停機回 418「Request temporarily denied. | Archive of Our Own」「The archive is down for maintenance」(資安事件,非 Cloudflare)。
   AO3 正常頁 / 已刪頁的真實字樣要等恢復後再 `--probe` 補。規則改了請一併更新 tests/fixtures/html/ 的合成樣本。

   各平台:
   - Lofter:啟動前載入 cookies/lofter.json(「Get cookies.txt LOCALLY」或 Cookie-Editor 匯出的 JSON;也吃 Netscape cookies.txt)。
       沒有 cookie 檔 → 印提示、略過 Lofter。帶了 cookie 仍被導到 www.lofter.com/front/login → cookie 過期:login_required(blocked,
       不算死)並略過其餘 Lofter 連結。404 / 頁面顯示「页面不存在」→ deleted;整個部落格打不開(子網域 DNS 不存在 /
       連線被拒,且 www.lofter.com 本身連得上)或頁面顯示「博客不存在」→ deleted,reason = blog_gone。
       啟動時看 LOFTER_SESS 的到期日:剩不到 COOKIE_WARN_DAYS 天印醒目警告,已過期就略過 Lofter。
       合集分享頁(www.lofter.com/front/blog/collection/share?collectionId=…)另一套規則:404 狀態碼不算已刪(unknown,collection_404),
       只認「合集不存在 / 已被删除」字樣;author_name 一律 None(見 checkers/lofter.py)。
       作者名(author_name)依序取文章頁 header 連回首頁的連結文字(<title> 以「-該名」結尾互相印證最好)→ 都沒有時改抓部落格首頁的名字
       (lofter_home_name,同 host 只抓一次,source = blog_home)。2026-11-05 實測:舊版從 <title> 切「 - 」把「某文 - 上-一只大鹅」切成「上-一只大鹅」。
   - AO3:網址自動加 ?view_adult=true 跳過成人確認頁。**全站停機**(狀態碼 418、標題含 Request temporarily denied、或內文 down for maintenance)
       → unknown,reason = ao3_down(不是 Cloudflare、不改任何計數),第一筆遇到就略過整個 AO3、本次不再打(印「AO3 停機中，略過」)。
       404 或「Sorry, we couldn't find the work you were looking for」→ deleted;「This work is only available to registered users」→ login_required(不算死)。
       另外解析章節進度(Chapters: 5/10、5/?)與 Completed 日期,放在結果的 extra 欄位(check_links.advance 會存進 link_status.json),先只記錄、不寫回 Notion。
   - Asianfanfics:正常、或顯示 SUBSCRIBERS ONLY / Please subscribe to read 都算 ok(文還在,只是要訂閱);
       404 頁(標題「Page Not Found」、內文「The page you were looking for doesn't exist or has moved.」,2026-11-05 站長用平常的 Chrome 實看)→ deleted。
       連續請求會被 Cloudflare 擋(第二筆起 403 驗證頁),所以 AFF 每筆間隔拉長到 GAP_PLAT['aff'] = 15~25 秒。
       **限速(2026-11-06 實測:約 100 筆後大量 unknown(empty),後段 http_429)**:
         · 每次執行最多 check_links.PLAT_MAX_PER_RUN['aff'] = 150 筆,依 link_status.json 的 last 排序、最久沒查的先,剩下的下次再跑(check_links.prioritize);
         · 一出現 HTTP 429(classify 標 rate_limited,不管頁面內容)或連續 EMPTY_MAX_STREAK = 5 筆 empty → 立刻停止該平台本次巡檢,
           其餘連結記 unknown(reason rate_limited_skip、skipped=True:advance 不動任何計數也不動 last,下次仍排在前面)並印警告;
         · 第一個 429 之前的結果照常;之後(同一個 session)AFF 的 deleted 一律改判 unknown(reason 原因_rate_limited,demote_after_rate_limit),
           限速期間的 404 不可信;
         · 作者頁(profile/u/…)跟作品頁在同一個清單、同一套規則。
       2026-11-05 實測:同頁等滿 20 秒仍停在「驗證成功。正在等待 … 回應」= Cloudflare 認出自動化瀏覽器(平常的 Chrome 開同一網址直接是 404 頁),
       所以 AFF 預設改走**固定設定檔**(見下方「固定設定檔」)。
   - 共用:同平台順序跑、每筆間隔 GAP 隨機 2~4 秒(AFF 另計);任何平台拿到 HTTP 429 都標 rate_limited、該平台本次立刻停止;每個平台一個 browser context 重用(不每筆開新瀏覽器);逾時 TIMEOUT_MS = 20 秒 → unknown;
       Cloudflare 挑戰頁用**頁面內容**判斷、不看狀態碼(標題 Just a moment / 請稍候 / 请稍候,或內文 Ray ID / Performance and Security by Cloudflare /
       Enable JavaScript and cookies to continue / 正在執行安全驗證…):在**同一頁**等驗證自己跑完(標題或網址變了、頁面不再是挑戰頁),
       最多 CF_SOLVE_S = 20 秒,過了就用那頁的內容判斷;等完仍是挑戰頁 → unknown(cf_challenge_wait)並計數,同平台連續 CF_MAX_STREAK = 5 筆
       就略過該平台並印警告。
       啟動時 GET https://www.cloudflare.com/cdn-cgi/trace,回應含 warp=on 就印提示並略過三個平台(WARP 的出口 IP 會被擋)。
   沙箱:Playwright 預設幫 Chromium 加 --no-sandbox;只有 Linux(容器)保留,Windows / macOS 傳 chromium_sandbox=True 不加
       (有頭 Chrome 才不會跳黃色警告條;needs_no_sandbox)。
   瀏覽器:預設 Playwright 內建的 Chromium(無頭;UA 裡的 HeadlessChrome 會換成 Chrome);--browser-channel chrome 改用系統 Chrome、
       --headed 開視窗看畫面、環境變數 AZ_BROWSER_EXE 直接指定執行檔。
   基本反偵測(所有瀏覽器都套):--disable-blink-features=AutomationControlled、拿掉 Playwright 預設的 --enable-automation、
       init script 把 navigator.webdriver 改成 undefined(STEALTH_ARGS / STEALTH_IGNORE / STEALTH_JS)。
   固定設定檔(PROFILE_PLATFORMS,預設只有 AFF;check_links.py --profile aff,lofter 可改、--no-profile 關掉):
       用 launch_persistent_context(user_data_dir = _build/browser_profile/,git 忽略)+ 系統 Chrome(channel chrome),
       保留 cf_clearance 與 AFF 登入狀態;**不改 UA**(cf_clearance 綁 UA,換了 UA 就失效)、預設**有頭**(headless 容易被認出來;--profile-headless 可改)。
       設定檔要先用 `python check_links.py --setup-profile` 建:開有頭 Chrome 到 AFF 首頁,站長手動登入、通過驗證,按 Enter 關閉並存檔(setup_profile)。
       用了設定檔仍是 cf_challenge_wait → AFF 維持 unknown(不改計數),log 提示「AFF 被 Cloudflare 擋，請重跑 --setup-profile 或手動檢查」。
       同一個設定檔一次只能被一個 Chrome 開:跑巡檢前把 --setup-profile 的視窗關掉。
   用法:由 check_links.py 呼叫(--browser / --probe);本檔不自己當 main。"""
import io, json, os, random, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

from checkers import _http as H
from checkers import lofter as _lofter, ao3 as _ao3, aff as _aff

PLATFORMS = ('lofter', 'ao3', 'aff')
GAP = (2.0, 4.0)            # 同平台每筆間隔(秒,隨機)
GAP_PLAT = {'aff': (15.0, 25.0)}  # 個別平台的間隔(AFF 連續請求會被 Cloudflare 擋 / 限速,2026-11-06 實測 6~10 秒跑約 100 筆就 429,拉長)
TIMEOUT_MS = 20000          # 單頁逾時 → unknown
SETTLE_MS = 3000            # domcontentloaded 之後再等 networkidle 最多這麼久(讓 JS 把內容畫出來;逾時不算錯)
CF_SOLVE_S = 20             # 遇到 Cloudflare 挑戰頁:在同一頁等驗證跑完,最多幾秒
CF_POLL_S = 1.0             # 等驗證時每隔幾秒看一次標題 / 網址有沒有變
CF_MAX_STREAK = 5           # 同平台連續幾筆挑戰頁就略過該平台
RATE_LIMIT_CODE = 429       # 限速:拿到這個狀態碼(不管頁面內容)→ rate_limited,該平台本次立刻停止
EMPTY_MAX_STREAK = 5        # 連續幾筆 unknown(empty)視同被限速,立刻停止(只套用在 EMPTY_STREAK_PLATFORMS)
EMPTY_STREAK_PLATFORMS = ('aff',)   # 2026-11-06 實測 AFF 被限速時先是整頁空白、後段才 429
COOKIE_DIR = 'cookies'
COOKIE_FILE = os.path.join(COOKIE_DIR, 'lofter.json')
COOKIE_SESS = 'LOFTER_SESS'
COOKIE_WARN_DAYS = 3
WARP_TRACE = 'https://www.cloudflare.com/cdn-cgi/trace'
TZ = timezone(timedelta(hours=8))
INSTALL_HINT = 'pip install playwright && playwright install chromium'
PROFILE_DIR = 'browser_profile'          # 固定設定檔(相對 _build;git 忽略)
PROFILE_PLATFORMS = ('aff',)             # 預設走固定設定檔的平台
PROFILE_CHANNEL = 'chrome'               # 固定設定檔用系統 Chrome
AFF_HOME = 'https://www.asianfanfics.com/'
LABEL = {'lofter': 'Lofter', 'ao3': 'AO3', 'aff': 'AFF'}
STEALTH_ARGS = ('--disable-blink-features=AutomationControlled',)
STEALTH_IGNORE = ('--enable-automation',)
STEALTH_JS = "Object.defineProperty(Navigator.prototype, 'webdriver', {get: () => undefined, configurable: true});"
VIEWPORT = {'width': 1280, 'height': 900}

CF_TITLES = ('Just a moment', '請稍候', '请稍候', 'Attention Required! | Cloudflare')     # 挑戰頁的 <title>(多語系)
CF_MARKERS = ('cf-challenge', 'cf-chl-', '_cf_chl_opt', 'Ray ID', 'Performance and Security by Cloudflare',
              'Performance & security by Cloudflare', 'Enable JavaScript and cookies to continue',
              'Verify you are human', 'Verifying you are human', 'Checking your browser',
              '正在執行安全驗證', '正在执行安全验证', '驗證您是人類', '验证您是人类')
AO3_DOWN_CODE = 418                                      # AO3 全站停機時 nginx 回的狀態碼(2026-11 資安事件)
AO3_DOWN = ('Request temporarily denied', 'down for maintenance')   # 前者看 <title>,後者看內文
LOFTER_BLOG_GONE = ('博客不存在', '该博客不存在', '博客已注销', '该博客已注销', '博主已注销', '博客已关闭', '该用户不存在')
LOFTER_GONE = _lofter.GONE_TEXT + ('文章不存在', '该文章不存在', '该文章已被删除', '内容不存在', '404',
                                   '页面走丢了', '页面已被移除', '链接可能已损毁')     # 後三個是 2026-11-04 實測的 404 頁字樣
AFF_SUBSCRIBE = ('subscribers only', 'please subscribe to read', 'subscribe to read', 'subscribe to this story to read')
AFF_GONE = tuple(k for k in _aff.GONE_TEXT if k != 'the page you requested') + ('404 page not found',)   # _aff.GONE_TEXT 已含 2026-11-05 實看的 404 頁字樣
AO3_GONE = (_ao3.NOT_FOUND, 'this work has been deleted', 'work could not be found')
NET_GONE = ('net::ERR_NAME_NOT_RESOLVED', 'net::ERR_CONNECTION_REFUSED', 'net::ERR_CONNECTION_CLOSED',
            'net::ERR_CONNECTION_RESET', 'net::ERR_CERT_COMMON_NAME_INVALID', 'net::ERR_SSL_PROTOCOL_ERROR')

# ---------- 可用性 / 環境偵測(純函式部分可測) ----------

def is_available():
    """有沒有裝 Playwright(Python 套件);瀏覽器本體要另外 `playwright install chromium`,沒裝會在 start() 時報錯。"""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except ImportError:
        return False

def is_warp(trace_text):
    """cloudflare.com/cdn-cgi/trace 的回應:有一行 warp=on 或 warp=plus 就是 WARP 開著。"""
    return re.search(r'^warp=(on|plus)\s*$', trace_text or '', re.M) is not None

def fetch_trace(timeout=6):
    """GET WARP_TRACE;連不上回 ''(不當成 WARP,也不擋巡檢)。"""
    try:
        req = urllib.request.Request(WARP_TRACE, headers={'User-Agent': H.UA})
        with urllib.request.urlopen(req, timeout=timeout, context=H.SSL_CTX) as r:
            return r.read(4000).decode('utf-8', 'replace')
    except Exception:
        return ''

# ---------- cookie ----------

_SAMESITE = {'no_restriction': 'None', 'none': 'None', 'lax': 'Lax', 'strict': 'Strict'}

def _netscape_cookies(text):
    """Netscape cookies.txt(7 欄 tab 分隔)→ 同 JSON 匯出的 dict 形狀。"""
    out = []
    for line in (text or '').splitlines():
        if line.startswith('#HttpOnly_'):
            line, http_only = line[len('#HttpOnly_'):], True
        else:
            http_only = False
        if not line.strip() or line.startswith('#'):
            continue
        f = line.split('\t')
        if len(f) < 7:
            continue
        out.append({'domain': f[0], 'path': f[2], 'secure': f[3].upper() == 'TRUE', 'expirationDate': float(f[4] or 0) or None,
                    'name': f[5], 'value': f[6], 'httpOnly': http_only})
    return out

def load_cookies(path):
    """讀 cookie 匯出檔 → Playwright context.add_cookies() 吃的清單。
    相容:「Get cookies.txt LOCALLY」的 JSON(陣列,每筆 domain / expirationDate / hostOnly / httpOnly / name / path / sameSite / secure / session / value)、
    Cookie-Editor 的 JSON(同樣欄位,sameSite 是 lax / strict / no_restriction / null)、包在 {"cookies": [...]} 裡的寫法,
    以及 Netscape 格式的 cookies.txt。空檔或格式不對 → ValueError。"""
    text = io.open(path, encoding='utf-8-sig').read()
    try:
        raw = json.loads(text)
    except ValueError:
        raw = _netscape_cookies(text)
    if isinstance(raw, dict):
        raw = raw.get('cookies') or raw.get('data') or []
    if not isinstance(raw, list):
        raise ValueError('cookie 檔格式看不懂:%s' % path)
    out = []
    for c in raw:
        if not isinstance(c, dict) or not c.get('name') or 'value' not in c:
            continue
        domain = c.get('domain') or ''
        if not domain:
            continue
        ck = {'name': c['name'], 'value': str(c.get('value', '')), 'domain': domain, 'path': c.get('path') or '/',
              'httpOnly': bool(c.get('httpOnly')), 'secure': bool(c.get('secure'))}
        exp = c.get('expirationDate') if not c.get('session') else None
        if exp:
            ck['expires'] = float(exp)
        ss = _SAMESITE.get(str(c.get('sameSite') or '').lower())
        if ss == 'None' and not ck['secure']:
            ss = 'Lax'      # Chromium 不收 SameSite=None 又不 secure 的 cookie
        if ss:
            ck['sameSite'] = ss
        out.append(ck)
    if not out:
        raise ValueError('cookie 檔裡沒有任何 cookie:%s' % path)
    return out

def cookie_expiry(cookies, name=COOKIE_SESS):
    """指定 cookie 的到期時間(台北時間的 datetime);沒有該 cookie 或沒有到期日(session cookie)→ None。"""
    for c in cookies or []:
        if c.get('name') == name and c.get('expires'):
            return datetime.fromtimestamp(float(c['expires']), TZ)
    return None

def cookie_status(cookies, now=None, name=COOKIE_SESS, warn_days=COOKIE_WARN_DAYS):
    """→ (狀態, 到期時間, 剩餘天數):'missing'(沒有這個 cookie)、'no_expiry'(session cookie,沒有到期日)、
    'expired'、'expiring'(剩不到 warn_days 天)、'ok'。"""
    now = now or datetime.now(TZ)
    if not any(c.get('name') == name for c in cookies or []):
        return 'missing', None, None
    exp = cookie_expiry(cookies, name)
    if exp is None:
        return 'no_expiry', None, None
    left = (exp - now).total_seconds() / 86400
    if left <= 0:
        return 'expired', exp, left
    return ('expiring' if left < warn_days else 'ok'), exp, left

def fmt_dt(dt):
    return dt.strftime('%Y-%m-%d %H:%M') if dt else '?'

# ---------- 判斷(純函式) ----------

def is_cf_challenge(status, html):
    """Cloudflare 挑戰頁:看 <title>(Just a moment / 請稍候 / 请稍候…)或頁面前段的標記字樣(Ray ID、Performance and Security by Cloudflare、
    Enable JavaScript and cookies to continue、正在執行安全驗證…)。只看內容、不看狀態碼:真瀏覽器拿到的挑戰頁有 200 / 403 / 503 都見過,
    2026-11-04 實測 AFF 的是 403 繁中版。"""
    body = (html or '')[:30000]
    title = H.title_of(body)
    return any(k in title for k in CF_TITLES) or any(k in body for k in CF_MARKERS)

def gap_for(platform):
    """該平台每筆之間的間隔範圍(秒)。"""
    return GAP_PLAT.get(platform, GAP)

def is_ao3_down(status, html):
    """AO3 全站停機頁(不是 Cloudflare):狀態碼 418、<title> 含 Request temporarily denied、或內文含 down for maintenance。"""
    if status == AO3_DOWN_CODE:
        return True
    body = (html or '')[:30000]
    return AO3_DOWN[0].lower() in H.title_of(body).lower() or AO3_DOWN[1].lower() in H.text_of(body).lower()

def ao3_progress(html):
    """AO3 作品頁的 stats:Chapters: 5/10(或 5/?)、Completed / Updated 日期、字數 → extra dict;解析不到回 None。"""
    body = html or ''
    m = re.search(r'<dd[^>]*class=["\']chapters["\'][^>]*>\s*(\d+)\s*/\s*(\d+|\?)\s*</dd>', body, re.I) \
        or re.search(r'Chapters:\s*(\d+)\s*/\s*(\d+|\?)', H.text_of(body[:300000]))
    if not m:
        return None
    cur, tot = int(m.group(1)), (None if m.group(2) == '?' else int(m.group(2)))
    ex = {'chapters': '%d/%s' % (cur, '?' if tot is None else tot), 'chapter_current': cur, 'chapter_total': tot,
          'complete': tot is not None and cur >= tot}
    s = re.search(r'<dt[^>]*class=["\']status["\'][^>]*>\s*(Completed|Updated):?\s*</dt>\s*<dd[^>]*class=["\']status["\'][^>]*>\s*([^<]+?)\s*</dd>', body, re.I)
    if s:
        ex['status'] = s.group(1).lower()
        ex['status_date'] = s.group(2).strip()
        if s.group(1).lower() == 'completed':
            ex['complete'] = True
    w = re.search(r'<dd[^>]*class=["\']words["\'][^>]*>\s*([\d,]+)\s*</dd>', body, re.I)
    if w:
        ex['words'] = int(w.group(1).replace(',', ''))
    return ex

def _nav_error_result(platform, error, final, url):
    if error == 'timeout':
        return H.result('unknown', reason='timeout', code=None, final=final)
    if platform == 'lofter' and any(error.startswith(k) for k in NET_GONE):
        return H.result('deleted', reason='blog_gone', code=None, final=final, detail=error)
    return H.result('unknown', reason='nav_error', code=None, final=final, detail=error)

def classify(platform, final_url, status, html, url='', error=''):
    """瀏覽器抓到的東西 → checkers 同形狀的結果。status 是 HTTP 狀態碼(None = 沒拿到),error 是導覽錯誤
    ('timeout'、'net::ERR_NAME_NOT_RESOLVED'、'network'…;'' = 沒錯誤)。多出來的鍵:challenge(Cloudflare 挑戰頁,呼叫端據此等待重試 / 計數)、
    blocked(平台層級被擋,呼叫端略過該平台其餘連結)、down(AO3 全站停機,呼叫端略過整個平台且不計挑戰頁)、
    rate_limited(HTTP 429,呼叫端立刻停止該平台、之後的 deleted 不可信)、extra(AO3 章節進度)。"""
    final = final_url or url
    if error:
        return _nav_error_result(platform, error, final, url)
    body = html or ''
    if status == RATE_LIMIT_CODE:       # 限速:不看頁面內容(Cloudflare 1015 也是 429 挑戰頁長相),呼叫端據 rate_limited 停止該平台
        return H.result('unknown', reason='http_%d' % RATE_LIMIT_CODE, code=status, final=final, blocked=True, rate_limited=True)
    if platform == 'ao3' and is_ao3_down(status, body):
        return H.result('unknown', reason='ao3_down', code=status, final=final, blocked=True, down=True)
    if is_cf_challenge(status, body):
        return H.result('unknown', reason='cf_challenge', code=status, final=final, blocked=True, challenge=True)
    if platform == 'lofter':
        return _classify_lofter(final, status, body, url)
    if platform == 'ao3':
        return _classify_ao3(final, status, body, url)
    if platform == 'aff':
        return _classify_aff(final, status, body, url)
    return H.result('unknown', reason='unsupported', code=status, final=final)

def demote_after_rate_limit(res):
    """第一個 429 之後的結果:deleted(404 / gone_text / redirect_home…)一律改判 unknown,reason = 原因_rate_limited,
    其他鍵(code / final / author…)照舊;不是 deleted 的原樣回傳。限速期間 AFF 的 404 不可信(2026-11-06 實測)。"""
    if (res or {}).get('status') != 'deleted':
        return res
    out = dict(res)
    out['status'] = 'unknown'
    out['reason'] = '%s_rate_limited' % (res.get('reason') or 'deleted')
    return out

def rate_limited_skip(url, why):
    """被限速而停止後,其餘連結記這個:unknown、不計數、skipped=True(check_links.advance 不動 last,下次仍排在最前面)。"""
    return H.result('unknown', reason='rate_limited_skip', code=None, final=url, skipped=True, detail=why)

def blog_root_gone(status, html, error=''):
    """Lofter 部落格首頁(https://xxx.lofter.com/)還在不在:DNS / 連線錯誤、404、或頁面說博客不存在 → True(整個部落格沒了)。"""
    if error:
        return any(error.startswith(k) for k in NET_GONE)
    if status == 404:
        return True
    return any(k in H.text_of((html or '')[:200000]) for k in LOFTER_BLOG_GONE)

def home_blog_name(html, host):
    """部落格首頁 → 博客名:header 連回首頁的連結文字;沒有就用首頁 <title>(首頁標題就是博客名,不含文章標題)。"""
    name, src = _lofter.blog_name(html, host)
    if src in ('header_title', 'header'):
        return name
    return H.title_of(html) or name

def _classify_lofter(final, status, body, url):
    fh, fp = H.host_of(final), H.path_of(final)
    if fh in ('www.lofter.com', 'lofter.com') and (fp.startswith(_lofter.LOGIN_PATH) or fp.rstrip('/') == '/login'):
        return H.result('login_required', reason='login_wall', code=status, final=final, blocked=True)
    if _lofter.is_collection(url):          # 合集分享頁:404 狀態碼不算已刪,只認「合集不存在」字樣(見 checkers/lofter.py)
        if status in (403, 429):
            return H.result('unknown', reason='http_%s' % status, code=status, final=final)
        return _lofter.classify_collection(status, final, body, url)
    txt = H.text_of(body[:200000])
    if any(k in txt for k in LOFTER_BLOG_GONE):
        return H.result('deleted', reason='blog_gone', code=status, final=final)
    if status == 404:
        root = H.path_of(url) in ('', '/')      # 查的是部落格首頁本身(作者庫的平台網址)而不是某篇
        return H.result('deleted', reason='blog_gone' if root else '404', code=status, final=final)
    if status in (403, 429):
        return H.result('unknown', reason='http_%s' % status, code=status, final=final)
    if status is not None and status != 200:
        return H.result('unknown', reason='http_%s' % status, code=status, final=final)
    if '/post/' in H.path_of(url) and (fp in ('', '/') or fh in ('www.lofter.com', 'lofter.com')):
        return H.result('deleted', reason='redirect_home', code=status, final=final)
    if any(k in txt for k in LOFTER_GONE if k != '404') or '404' in H.title_of(body) or txt.lstrip().startswith('404'):
        return H.result('deleted', reason='gone_text', code=status, final=final)
    if re.search(r'(登录|登錄)\s*LOFTER', txt) and '/post/' not in fp:
        return H.result('login_required', reason='login_form', code=status, final=final, blocked=True)
    if not txt.strip():
        return H.result('unknown', reason='empty', code=status, final=final)
    name, src = _lofter.blog_name(body, fh)
    return H.result('ok', name, reason='200', code=status, final=final, author_url=fh, author_source=src)

def _classify_ao3(final, status, body, url):
    low = H.text_of(body[:300000]).lower()
    if status == 404 or any(k.lower() in low for k in AO3_GONE):
        return H.result('deleted', reason='404' if status == 404 else 'gone_text', code=status, final=final)
    if '/users/login' in H.path_of(final) or _ao3.LOGIN_ONLY.lower() in low:
        return H.result('login_required', reason='login_only', code=status, final=final)
    if status is not None and status != 200:
        return H.result('unknown', reason='http_%s' % status, code=status, final=final)
    name, href = _ao3._byline(body)
    extra = ao3_progress(body)
    if _ao3.ADULT in body:
        return H.result('ok', name, reason='adult_interstitial', code=status, final=final, author_url=href, extra=extra)
    if name or 'id="workskin"' in body or 'class="work meta group"' in body or extra:
        return H.result('ok', name, reason='byline' if name else 'workskin', code=status, final=final, author_url=href, extra=extra)
    return H.result('unknown', reason='no_markers', code=status, final=final)

def _classify_aff(final, status, body, url):
    low = H.text_of(body[:300000]).lower().replace('\u2019', "'")      # doesn’t → doesn't
    if status == 404 or any(k in low for k in AFF_GONE):
        return H.result('deleted', reason='404' if status == 404 else 'gone_text', code=status, final=final)
    if status is not None and status != 200:
        return H.result('unknown', reason='http_%s' % status, code=status, final=final)
    fp = H.path_of(final).rstrip('/')
    if '/story/view/' in H.path_of(url) and fp in ('', '/home'):
        return H.result('deleted', reason='redirect_home', code=status, final=final)
    name, href = _aff._author(body)
    if any(k in low for k in AFF_SUBSCRIBE):
        return H.result('ok', name, reason='subscribers_only', code=status, final=final, author_url=href)
    if name:
        return H.result('ok', name, reason='author_link', code=status, final=final, author_url=href)
    return H.result('unknown', reason='empty', code=status, final=final)

# ---------- --probe 的樣本挑選(純函式) ----------

def nonexistent_url(platform, base_url):
    """用同平台一個真實網址造一個明顯不存在的網址(--probe 的第三筆)。"""
    sp = urlsplit(base_url)
    if platform == 'lofter':
        return '%s://%s/post/1a2b3c4d_fffffffffff' % (sp.scheme or 'https', sp.netloc)
    if platform == 'ao3':
        return 'https://archiveofourown.org/works/999999999999'
    return 'https://www.asianfanfics.com/story/view/9999999999/annyeongz-probe'

def pick_probe_samples(targets, state, platform):
    """從 collect_targets 的清單 + link_status.json 挑:1 筆預期正常(link_status 曾是 ok,否則第一筆 Notion 沒標 ❌ 的)、
    1 筆 Notion 已標 ❌、1 筆不存在的網址;Lofter 多一筆「整個部落格不存在」,有合集連結時再多一筆合集分享頁。回傳 [(說明, 網址)]。"""
    plat = [t for t in targets if t['platform'] == platform]
    art = lambda t: [r for r in t['refs'] if r.get('kind') == 'article']
    ok = next((t for t in plat if (state.get(t['url']) or {}).get('status') == 'ok'), None) \
        or next((t for t in plat if art(t) and not any(r['marked'] for r in art(t))), None)
    marked = next((t for t in plat if any(r['marked'] for r in art(t))), None)
    out = []
    if ok:
        out.append(('正常(預期 ok)', ok['url']))
    if marked:
        out.append(('已知 ❌(預期 deleted)', marked['url']))
    base = ok or marked
    if base:
        out.append(('不存在(預期 deleted)', nonexistent_url(platform, base['url'])))
    if platform == 'lofter':
        out.append(('整個部落格不存在(預期 deleted / blog_gone)', 'https://annyeongz-no-such-blog-0512.lofter.com/'))
        coll = next((t for t in plat if _lofter.is_collection(t['url'])), None)
        if coll:
            out.append(('合集分享頁(預期 ok;404 狀態碼只算 unknown)', coll['url']))
    return out

# ---------- 固定設定檔 / 反偵測(純函式部分可測) ----------

def profile_dir(src_dir):
    return os.path.join(src_dir, PROFILE_DIR)

def profile_exists(src_dir):
    """設定檔資料夾在而且不是空的(Chrome 第一次開就會寫進 Default/ 等檔案)。"""
    d = profile_dir(src_dir)
    return os.path.isdir(d) and bool(os.listdir(d))

def needs_no_sandbox(os_name=None):
    """Playwright 預設會幫 Chromium 加 --no-sandbox(chromium_sandbox=False)。只有 Linux(容器 / root 跑時沙箱起不來)需要它;
    Windows / macOS 不需要,而且有頭 Chrome 會跳黃色警告條「您使用的是不受支援的命令列標記:--no-sandbox」(2026-11-05 站長回報)。"""
    return (os_name or sys.platform).startswith('linux')

def launch_kwargs(headless, channel='', executable='', os_name=None):
    """chromium.launch / launch_persistent_context 共用的參數:有頭與否、channel / 執行檔、基本反偵測旗標、沙箱。不給 user_agent。
    非 Linux 一律 chromium_sandbox=True(不加 --no-sandbox,見 needs_no_sandbox)。"""
    kw = {'headless': bool(headless), 'args': list(STEALTH_ARGS), 'ignore_default_args': list(STEALTH_IGNORE)}
    if not needs_no_sandbox(os_name):
        kw['chromium_sandbox'] = True
    if channel:
        kw['channel'] = channel
    if executable:
        kw['executable_path'] = executable
    return kw

def profile_launch_kwargs(profile, executable='', os_name=None):
    """固定設定檔:預設有頭、系統 Chrome,不改 UA(cf_clearance 綁 UA)。"""
    kw = launch_kwargs(bool(profile.get('headless')), profile.get('channel') or PROFILE_CHANNEL, executable, os_name)
    kw.update(locale='zh-TW', viewport=dict(VIEWPORT))
    return kw

def profile_config(src_dir, platforms=PROFILE_PLATFORMS, headless=False, channel=''):
    """→ preflight / BrowserSession 用的 {'dir', 'platforms', 'headless', 'channel', 'exists'};platforms 空 = 不用設定檔(回 None)。"""
    plats = tuple(p for p in (platforms or ()) if p in PLATFORMS)
    if not plats:
        return None
    return {'dir': profile_dir(src_dir), 'platforms': plats, 'headless': bool(headless),
            'channel': channel or PROFILE_CHANNEL, 'exists': profile_exists(src_dir)}

def cf_profile_hint(plat):
    return '%s 被 Cloudflare 擋，請重跑 --setup-profile 或手動檢查' % LABEL.get(plat, plat)

def _uses_profile(session, plat):
    f = getattr(session, 'uses_profile', None)
    return bool(f and f(plat))

def setup_profile(src_dir, url=AFF_HOME, channel='', log=print, input_fn=input, playwright_factory=None, executable=''):
    """--setup-profile:用固定設定檔開有頭 Chrome 到 AFF 首頁,讓站長手動登入、通過 Cloudflare 驗證,按 Enter 後關閉(設定檔自動存檔)。
    回傳 True / False(沒裝 Playwright 或瀏覽器開不起來)。playwright_factory 給測試換成假的。"""
    if playwright_factory is None:
        if not is_available():
            log('⚠️ 沒有安裝 Playwright,請先:%s' % INSTALL_HINT)
            return False
        from playwright.sync_api import sync_playwright as playwright_factory
    d = profile_dir(src_dir)
    os.makedirs(d, exist_ok=True)
    prof = {'headless': False, 'channel': channel or PROFILE_CHANNEL}
    executable = executable or os.environ.get('AZ_BROWSER_EXE', '')
    with playwright_factory() as pw:
        try:
            ctx = pw.chromium.launch_persistent_context(d, **profile_launch_kwargs(prof, executable))
        except Exception as e:
            log('⚠️ 開不了瀏覽器:%s' % str(e).splitlines()[0][:200])
            log('   (沒裝 Google Chrome?或設定檔正被別的 Chrome 視窗使用,先把它關掉;也可用 --browser-channel 改用別的瀏覽器)')
            return False
        try:
            ctx.add_init_script(STEALTH_JS)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=60000)
            except Exception as e:
                log('⚠️ 打開 %s 時出錯(%s),可以在視窗裡自己重新整理' % (url, str(e).splitlines()[0][:120]))
            log('已用固定設定檔開啟 %s(設定檔:%s)' % (url, d))
            log('請在瀏覽器視窗裡:① 通過 Cloudflare 驗證(看到 AFF 首頁)② 登入 AFF ③ 隨便點開一篇文確認看得到。')
            input_fn('完成後回到這裡按 Enter,會關閉瀏覽器並存檔…')
            try:
                names = {c.get('name') for c in ctx.cookies(url)}
            except Exception:
                names = set()
            log('cf_clearance:%s;AFF cookie %d 個' % ('✅ 有' if 'cf_clearance' in names else '⚠️ 沒有(可能還沒通過驗證,可再跑一次)', len(names)))
        finally:
            try:
                ctx.close()
            except Exception:
                pass
    log('設定檔已存到 %s;之後 --browser 的 AFF 會用它(有頭 Chrome 視窗會跳出來,跑完自動關)。' % d)
    return True

# ---------- 瀏覽器 ----------

class BrowserSession:
    """一個 Playwright;一般平台共用一個 Chromium、每個平台一個 context(Lofter 的帶 cookie)與一個 page 重用;
    走固定設定檔的平台(profile['platforms'],預設 AFF)用 launch_persistent_context(有頭系統 Chrome、不改 UA)。
    兩種瀏覽器都是第一次用到才開(prepare / page_for)。
    sync API 只能在建立它的那條執行緒用,所以 start / check / close 都要在同一條執行緒(check_links.py 用一條執行緒跑三個平台)。"""
    def __init__(self, cookies=None, headed=False, channel='', log=print, sleep=time.sleep, executable='', profile=None, playwright_factory=None):
        self.cookies, self.headed, self.channel, self.log, self.sleep = (cookies or {}), headed, channel, log, sleep
        self.executable = executable or os.environ.get('AZ_BROWSER_EXE', '')   # 指定瀏覽器執行檔(例如系統 Chrome 的 chrome.exe);留空用 Playwright 內建 Chromium
        self.profile = profile or {}
        self._factory = playwright_factory
        self._pw = self._browser = self._ua = self._pctx = None
        self._ctx = {}
        self._reach = {}
        self.rate_limited = set()   # 這個 session 裡已經拿過 429 的平台:之後該平台的 deleted 一律改判 unknown(demote_after_rate_limit)
        self._status = {}    # id(page) → 該頁最後一次主框架導覽的狀態碼(Cloudflare 驗證完自動重載時,page.goto 的回應已經過時)
        self.last = None     # 最後一次 fetch 的 (status, final, html, error),--probe 印頁面文字用

    def start(self):
        if self._factory is None:
            from playwright.sync_api import sync_playwright
            self._factory = sync_playwright
        self._pw = self._factory().start()
        return self

    def uses_profile(self, plat):
        return plat in (self.profile.get('platforms') or ())

    def _ensure_browser(self):
        """一般平台共用的 Chromium(第一次用到才開)。無頭時把 UA 裡的 HeadlessChrome 換成 Chrome(這個 context 不用 cf_clearance)。"""
        if self._browser is None:
            self._browser = self._pw.chromium.launch(**launch_kwargs(not self.headed, self.channel, self.executable))
            tmp = self._browser.new_context()
            try:
                ua = tmp.new_page().evaluate('navigator.userAgent')
            finally:
                tmp.close()
            self._ua = (ua or H.UA).replace('HeadlessChrome', 'Chrome')   # 無頭模式預設 UA 帶 HeadlessChrome,會被當機器人
            self.log('瀏覽器:%s %s%s' % (self._browser.browser_type.name, self._browser.version, '(有頭)' if self.headed else ''))
        return self._browser

    def _ensure_profile(self):
        """固定設定檔的 persistent context(第一次用到才開):有頭系統 Chrome、不改 UA、保留 cf_clearance 與登入狀態。"""
        if self._pctx is None:
            d = self.profile['dir']
            os.makedirs(d, exist_ok=True)
            kw = profile_launch_kwargs(self.profile, self.executable)
            self._pctx = self._pw.chromium.launch_persistent_context(d, **kw)
            self._pctx.add_init_script(STEALTH_JS)
            self.log('瀏覽器(固定設定檔):%s%s,設定檔 %s' % (kw.get('executable_path') or kw.get('channel') or 'chromium',
                                                       '(無頭)' if kw['headless'] else '(有頭)', d))
        return self._pctx

    def prepare(self, plat):
        """開好該平台要用的瀏覽器(run_all / probe 先呼叫,開不起來在這裡就丟例外,呼叫端略過該平台)。"""
        self.page_for(plat)

    def close(self):
        for ctx, _ in self._ctx.values():
            if ctx is self._pctx:
                continue
            try:
                ctx.close()
            except Exception:
                pass
        self._ctx = {}
        for obj in (self._pctx, self._browser):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._pctx = self._browser = self._pw = None

    def page_for(self, plat):
        if plat not in self._ctx:
            if self.uses_profile(plat):
                ctx = self._ensure_profile()
                used = any(c is ctx for c, _ in self._ctx.values())
                page = ctx.pages[0] if (ctx.pages and not used) else ctx.new_page()   # persistent context 開起來就有一頁,先用它
            else:
                ctx = self._ensure_browser().new_context(user_agent=self._ua, locale='zh-TW', viewport=dict(VIEWPORT))
                ctx.add_init_script(STEALTH_JS)
                page = ctx.new_page()
            if self.cookies.get(plat):
                ctx.add_cookies(self.cookies[plat])
            self._track_status(page)
            self._ctx[plat] = (ctx, page)
        return self._ctx[plat][1]

    def _track_status(self, page):
        """記下這頁每次主框架導覽的狀態碼(含 Cloudflare 驗證完的自動重載),wait_challenge 之後才知道最後那頁是幾。"""
        def on_response(resp):
            try:
                if resp.frame == page.main_frame and resp.request.is_navigation_request():
                    self._status[id(page)] = resp.status
            except Exception:
                pass
        try:
            page.on('response', on_response)
        except Exception:
            pass

    def fetch(self, plat, url, page=None):
        """→ (status, final_url, html, error);error:''、'timeout'、'net::ERR_…'、'nav_error:…'。"""
        from playwright.sync_api import TimeoutError as PWTimeout, Error as PWError
        page = page or self.page_for(plat)
        try:
            resp = page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_MS)
        except PWTimeout:
            return None, page.url, '', 'timeout'
        except PWError as e:
            msg = (str(e) or repr(e)).splitlines()[0]
            m = re.search(r'net::[A-Z_0-9]+', msg)
            return None, url, '', (m.group(0) if m else 'nav_error:' + msg[:120])
        try:
            page.wait_for_load_state('networkidle', timeout=SETTLE_MS)
        except PWError:
            pass
        html = self._content(page)
        st = resp.status if resp else None
        self._status[id(page)] = st
        return st, page.url, html, ''

    def _content(self, page):
        try:
            return page.content()
        except Exception:        # Playwright 的 Error(頁面正在重載時 content() 會丟);不在這裡 import playwright,測試用假 page 也能跑
            return ''

    def wait_challenge(self, page, final0, html0):
        """Cloudflare 挑戰頁:在同一頁等驗證自己跑完(標題或網址變了、或頁面不再是挑戰頁),每 CF_POLL_S 秒看一次、最多 CF_SOLVE_S 秒。
        回 (status, final, html):status 是這頁最後一次主框架導覽的狀態碼(驗證完 Cloudflare 會自動重載)。時間到仍是挑戰頁就回當下那頁。
        (不 import playwright:例外一律接 Exception,pytest 用假 page 就能測。)"""
        title0 = H.title_of(html0)
        for _ in range(max(1, int(CF_SOLVE_S / CF_POLL_S))):
            self.sleep(CF_POLL_S)
            try:
                title, url = page.title(), page.url
            except Exception:
                continue
            if title == title0 and url == final0:
                continue
            try:
                page.wait_for_load_state('networkidle', timeout=SETTLE_MS)
            except Exception:
                pass
            html = self._content(page)
            if not is_cf_challenge(None, html):
                return self._status.get(id(page)), page.url, html
            title0, final0 = H.title_of(html), page.url      # 「驗證成功。正在等待回應」之類的中間頁,繼續等
        return self._status.get(id(page)), page.url, self._content(page)

    def reachable(self, plat, home):
        """平台首頁連不連得上(每次執行只試一次):Lofter 子網域打不開時,先確認不是自己的網路斷了。"""
        if home not in self._reach:
            ctx = self._ctx[plat][0] if plat in self._ctx else None
            page = ctx.new_page() if ctx else None
            try:
                st, _, _, err = self.fetch(plat, home, page=page)
                self._reach[home] = (err == '' and st is not None)
            finally:
                if page:
                    page.close()
        return self._reach[home]

    def _qualify_error(self, plat, err):
        if plat == 'lofter' and any(err.startswith(k) for k in NET_GONE):
            return err if self.reachable(plat, 'https://www.lofter.com/') else 'network'
        return err

    def lofter_blog_gone(self, host):
        """某篇判定已刪時多看一眼部落格首頁(同一個 host 只查一次):整個部落格沒了 → True。"""
        key = 'root:' + host
        if key not in self._reach:
            self.sleep(random.uniform(*gap_for('lofter')))
            st, _, html, err = self.fetch('lofter', 'https://%s/' % host)
            self._reach[key] = blog_root_gone(st, html, self._qualify_error('lofter', err))
        return self._reach[key]

    def lofter_home_name(self, host):
        """部落格首頁的博客名(同一個 host 只抓一次):文章頁 header 找不到博客名時的穩定來源。抓不到回 None。"""
        key = 'name:' + host
        if key not in self._reach:
            self.sleep(random.uniform(*gap_for('lofter')))
            st, _, html, err = self.fetch('lofter', 'https://%s/' % host)
            name = None
            if not err and st == 200 and not blog_root_gone(st, html):
                name = home_blog_name(html, host)
            self._reach[key] = name
        return self._reach[key]

    def check(self, plat, url):
        """抓一筆並判斷;Cloudflare 挑戰頁在同一頁等驗證跑完(wait_challenge)再判斷一次,仍是挑戰頁 → reason = cf_challenge_wait;
        Lofter 某篇已刪時再看部落格首頁在不在(reason 改成 blog_gone)。回傳 checkers 形狀的結果。"""
        target = _ao3.with_view_adult(url) if plat == 'ao3' else url
        st, final, html, err = self.fetch(plat, target)
        res = classify(plat, final, st, html, url=url, error=self._qualify_error(plat, err))
        if res.get('challenge'):
            st, final, html = self.wait_challenge(self.page_for(plat), final, html)
            res = classify(plat, final, st, html, url=url)
            if res.get('challenge'):
                res['reason'] = 'cf_challenge_wait'
        self.last = (st, final, html, err)
        if plat == 'lofter' and res['status'] == 'deleted' and res.get('reason') != 'blog_gone' and '/post/' in H.path_of(url):
            host = H.host_of(url)
            if host.endswith('.lofter.com') and host != 'www.lofter.com' and self.lofter_blog_gone(host):
                res['reason'], res['detail'] = 'blog_gone', 'post:' + str(res.get('reason'))
        if plat == 'lofter' and res['status'] == 'ok' and res.get('author_source') not in ('header_title', 'header'):
            host = H.host_of(url)               # 文章頁 header 找不到博客名(只剩 <title> / og 可猜)→ 改用部落格首頁的名字
            if host.endswith('.lofter.com') and host != 'www.lofter.com':
                name = self.lofter_home_name(host)
                if name:
                    res['author_name'], res['author_source'] = name, 'blog_home'
        res.setdefault('final', final)
        if plat in self.rate_limited:
            res = demote_after_rate_limit(res)     # 第一個 429 之後:限速期間的 404 不可信
        if res.get('rate_limited'):
            self.rate_limited.add(plat)
        return res

# ---------- 跟 check_links.py 接的部分 ----------

def preflight(src_dir, platforms, log=print, now=None, trace=None, profile_platforms=PROFILE_PLATFORMS, profile_headless=False, profile_channel=''):
    """啟動前檢查,不開瀏覽器:Playwright 有沒有裝、WARP 有沒有開、Lofter cookie 在不在 / 過期沒、固定設定檔建了沒。
    回傳 {'available', 'warp', 'usable': [可跑的平台], 'notes': {平台: 略過原因}, 'cookies': {平台: cookie 清單},
    'profile': profile_config(…) 或 None}。"""
    pre = {'available': is_available(), 'warp': False, 'usable': [], 'notes': {}, 'cookies': {},
           'profile': profile_config(src_dir, [p for p in (profile_platforms or ()) if p in platforms], profile_headless, profile_channel)}
    plats = [p for p in platforms if p in PLATFORMS]
    if not pre['available']:
        log('⚠️ 沒有安裝 Playwright,--browser 模式無法使用;請先:%s。本次略過 %s。' % (INSTALL_HINT, '、'.join(plats)))
        for p in plats:
            pre['notes'][p] = '未安裝 Playwright,略過'
        return pre
    trace_text = fetch_trace() if trace is None else trace
    if is_warp(trace_text):
        pre['warp'] = True
        log('⚠️ 偵測到 Cloudflare WARP 開啟,三個海外平台會被擋,請先關閉 WARP 再跑。本次略過 %s。' % '、'.join(plats))
        for p in plats:
            pre['notes'][p] = 'WARP 開啟,略過'
        return pre
    for p in plats:
        if p == 'lofter':
            path = os.path.join(src_dir, COOKIE_FILE)
            if not os.path.exists(path):
                pre['notes'][p] = '沒有 %s,略過' % COOKIE_FILE
                log('ℹ️ 找不到 %s(用瀏覽器擴充「Get cookies.txt LOCALLY」或 Cookie-Editor 在登入 Lofter 後匯出 JSON 放到這裡),本次略過 Lofter。' % path)
                continue
            try:
                cookies = load_cookies(path)
            except Exception as e:
                pre['notes'][p] = 'cookie 檔讀不了:%s' % e
                log('⚠️ %s 讀不了(%s),本次略過 Lofter。' % (path, e))
                continue
            st, exp, left = cookie_status(cookies, now)
            if st == 'expired':
                pre['notes'][p] = 'Lofter cookie 已於 %s 過期,略過' % fmt_dt(exp)
                log('⚠️ Lofter cookie(%s)已於 %s 過期,請重新登入 Lofter 並匯出 cookie 覆蓋 %s。本次略過 Lofter。' % (COOKIE_SESS, fmt_dt(exp), COOKIE_FILE))
                continue
            if st == 'expiring':
                log('🚨🚨 Lofter cookie 將於 %s 過期(剩 %.1f 天),請重新匯出 %s 🚨🚨' % (fmt_dt(exp), left, COOKIE_FILE))
            elif st == 'missing':
                log('⚠️ %s 裡沒有 %s,可能不是登入後匯出的;仍會嘗試,被導到登入頁就會略過。' % (path, COOKIE_SESS))
            else:
                log('Lofter cookie:%d 筆,%s %s' % (len(cookies), COOKIE_SESS,
                                                   '到期 %s(剩 %.1f 天,剩不到 %d 天會警告)' % (fmt_dt(exp), left, COOKIE_WARN_DAYS) if exp else '(session cookie,無到期日)'))
            pre['cookies'][p] = cookies
        pre['usable'].append(p)
    prof = pre['profile']
    pplats = [p for p in (prof or {}).get('platforms', ()) if p in pre['usable']]
    if pplats:
        names = '、'.join(LABEL[p] for p in pplats)
        if prof['exists']:
            log('%s 使用固定設定檔 %s(%s Chrome%s)' % (names, prof['dir'], '無頭' if prof['headless'] else '有頭', '' if prof['headless'] else ',會跳出視窗,跑完自動關'))
        else:
            log('⚠️ 還沒有固定設定檔 %s:%s 很可能被 Cloudflare 擋。請先跑 python check_links.py --setup-profile(手動登入、通過驗證)。本次仍會嘗試。' % (prof['dir'], names))
    return pre

def skip_stat(n, note):
    return {'checked': 0, 'blocked': True, 'skipped': n, 'challenges': 0, 'note': note}

def run_platform(plat, targets, session, results, lock, verbose=False, log=print, sleep=time.sleep):
    """一個平台順序跑完(呼叫端保證在 session 的執行緒上)。回傳 {'checked','blocked','skipped','challenges', 'note'?}。
    - AO3 全站停機(down)→ 第一筆遇到就略過整個 AO3,本次不再打(狀態 unknown,不改任何計數)
    - 限速:HTTP 429(rate_limited)、或 EMPTY_STREAK_PLATFORMS 連續 EMPTY_MAX_STREAK 筆 unknown(empty)→ 立刻停止,
      其餘連結記 rate_limited_skip(unknown、不計數、不動 last)並印警告;作者頁與作品頁同一套
    - Cloudflare 挑戰頁連續 CF_MAX_STREAK 筆 → 略過其餘並印警告
    - Lofter 登入牆(blocked 且不是挑戰頁)→ cookie 過期,略過其餘(狀態 login_required,不算死)"""
    stat = {'checked': 0, 'blocked': False, 'skipped': 0, 'challenges': 0}
    streak, empties, hinted, prof = 0, 0, False, _uses_profile(session, plat)
    def stop_rate_limited(i, why):
        rest = targets[i + 1:]
        with lock:
            for r in rest:
                results[r['url']] = rate_limited_skip(r['url'], why)
        stat['blocked'], stat['skipped'] = True, len(rest)
        stat['note'] = '被限速(%s),已停止' % why
        log('  🚨 [%s] %s → 立刻停止本平台巡檢,其餘 %d 筆記 unknown(不計數,下次優先查);請隔久一點再跑,或把間隔拉長' % (plat, why, len(rest)))
    for i, t in enumerate(targets):
        res = session.check(plat, t['url'])
        with lock:
            results[t['url']] = res
        stat['checked'] += 1
        if verbose or res['status'] != 'ok':
            log('  [%s] %-14s %s  %s' % (plat, res['status'] + ('(' + str(res.get('reason')) + ')' if res.get('reason') else ''),
                                         t['url'], res.get('author_name') or ''))
        if res.get('rate_limited'):
            stop_rate_limited(i, 'HTTP %s' % (res.get('code') or RATE_LIMIT_CODE))
            break
        if plat in EMPTY_STREAK_PLATFORMS and res['status'] == 'unknown' and res.get('reason') == 'empty':
            empties += 1
            if empties >= EMPTY_MAX_STREAK:
                stop_rate_limited(i, '連續 %d 筆空白頁' % empties)
                break
        else:
            empties = 0
        if res.get('down'):
            stat['blocked'], stat['skipped'] = True, len(targets) - stat['checked']
            stat['note'] = 'AO3 停機中'
            log('  ⚠️ [%s] AO3 停機中，略過(本次不再打其餘 %d 筆;恢復後再跑,不改任何計數)' % (plat, stat['skipped']))
            break
        if res.get('challenge'):
            stat['challenges'] += 1
            streak += 1
            if prof and not hinted:
                log('  ⚠️ [%s] %s(仍記 unknown,不改計數)' % (plat, cf_profile_hint(plat)))
                hinted = True
            if streak >= CF_MAX_STREAK:
                stat['blocked'], stat['skipped'] = True, len(targets) - stat['checked']
                stat['note'] = 'Cloudflare 挑戰頁連續 %d 筆' % streak + (';' + cf_profile_hint(plat) if prof else '')
                log('  ⚠️ [%s] Cloudflare 挑戰頁連續 %d 筆 → 本次略過此平台其餘 %d 筆(%s)' % (
                    plat, streak, stat['skipped'], cf_profile_hint(plat) if prof else '請確認 WARP / VPN 已關、或改用 --headed 看看畫面'))
                break
        else:
            streak = 0
            if res.get('blocked'):
                stat['blocked'], stat['skipped'] = True, len(targets) - stat['checked']
                stat['note'] = '登入牆(cookie 過期或無效)'
                log('  ⚠️ [%s] 帶了 cookie 仍被導到登入頁 → cookie 已過期或無效,請重新匯出 %s;本次略過其餘 %d 筆(不算已刪)' % (plat, COOKIE_FILE, stat['skipped']))
                break
        if i < len(targets) - 1:
            sleep(random.uniform(*gap_for(plat)))
    return stat

def _prepare(session, plat, log=print):
    """開好該平台的瀏覽器;開不起來回略過原因字串(並印提示),成功回 ''。"""
    f = getattr(session, 'prepare', None)
    if not f:
        return ''
    try:
        f(plat)
        return ''
    except Exception as e:
        msg = str(e).splitlines()[0][:200] if str(e) else repr(e)
        log('  ⚠️ [%s] 瀏覽器開不起來:%s' % (plat, msg))
        if _uses_profile(session, plat):
            log('     (固定設定檔要系統 Google Chrome;設定檔正被別的 Chrome 視窗使用時也會失敗,先把 --setup-profile 的視窗關掉)')
        return '瀏覽器開不起來'

def run_all(pre, by_plat, platforms, results, lock, verbose=False, log=print, headed=False, channel='', session=None):
    """在同一條執行緒上開瀏覽器、依序跑 platforms 裡可用的平台;不可用的回 skip_stat。回傳 {平台: stat}。"""
    stats = {}
    todo = [p for p in platforms if p in PLATFORMS]
    for p in todo:
        if p not in pre['usable']:
            stats[p] = skip_stat(len(by_plat.get(p) or []), pre['notes'].get(p, '略過'))
    todo = [p for p in todo if p in pre['usable']]
    if not todo:
        return stats
    own = session is None
    if own:
        session = BrowserSession(cookies=pre['cookies'], headed=headed, channel=channel, log=log, profile=pre.get('profile'))
        try:
            session.start()
        except Exception as e:
            log('⚠️ 瀏覽器啟動失敗:%s(沒裝瀏覽器本體?請執行 playwright install chromium)' % e)
            for p in todo:
                stats[p] = skip_stat(len(by_plat.get(p) or []), '瀏覽器啟動失敗')
            return stats
    try:
        for p in todo:
            ts = by_plat.get(p) or []
            if not ts:
                stats[p] = {'checked': 0, 'blocked': False, 'skipped': 0, 'challenges': 0}
                continue
            err = _prepare(session, p, log)
            if err:
                stats[p] = skip_stat(len(ts), err)
                continue
            stats[p] = run_platform(p, ts, session, results, lock, verbose, log)
    finally:
        if own:
            session.close()
    return stats

def probe(targets, state, platforms, pre, log=print, headed=False, channel='', session=None):
    """--probe:每個平台抓幾筆代表性樣本,印最終網址 / 狀態碼 / 判定 / 頁面前 300 字;不寫任何檔案。"""
    todo = [p for p in platforms if p in PLATFORMS]
    for p in todo:
        if p not in pre['usable']:
            log('[%s] 略過:%s' % (p, pre['notes'].get(p, '')))
    todo = [p for p in todo if p in pre['usable']]
    if not todo:
        return
    own = session is None
    if own:
        session = BrowserSession(cookies=pre['cookies'], headed=headed, channel=channel, log=log, profile=pre.get('profile')).start()
    try:
        for p in todo:
            samples = pick_probe_samples(targets, state, p)
            log('')
            log('===== %s(%d 筆%s)=====' % (p, len(samples), ',固定設定檔' if _uses_profile(session, p) else ''))
            err = _prepare(session, p, log)
            if err:
                log('[%s] 略過:%s' % (p, err))
                continue
            for label, url in samples:
                t0 = time.time()
                res = session.check(p, url)
                st, final, html, err = session.last or (None, url, '', '')
                log('--- %s' % label)
                log('    網址:%s' % url)
                log('    最終:%s' % final)
                log('    狀態碼:%s  導覽錯誤:%s  耗時:%.1fs' % (st, err or '-', time.time() - t0))
                log('    判定:%s(%s)  作者:%s%s%s' % (res['status'], res.get('reason'), res.get('author_name') or '-',
                                                   '(來源 %s)' % res['author_source'] if res.get('author_source') else '',
                                                   '  extra=' + json.dumps(res['extra'], ensure_ascii=False) if res.get('extra') else ''))
                log('    頁面文字:%s' % H.text_of(html)[:300].replace('\n', ' '))
                log('    <title>:%s' % H.title_of(html))
                if res.get('down'):
                    log('    ⚠️ AO3 停機中，略過(其餘樣本本次不再打)')
                    break
                if res.get('challenge') and _uses_profile(session, p):
                    log('    ⚠️ %s' % cf_profile_hint(p))
                session.sleep(random.uniform(*gap_for(p)))
    finally:
        if own:
            session.close()
