# -*- coding: utf-8 -*-
"""瀏覽器巡檢模式(check_links.py --browser 用):用 Playwright 開真的 Chromium 抓 Lofter / AO3 / Asianfanfics。
   這三個平台用 urllib 從任何 IP 都會被登入牆 / Cloudflare 擋(見 checkers/{lofter,ao3,aff}.py 檔頭),
   真瀏覽器才過得去;所以這個模式**只在站長本機跑**,GitHub Actions 的 check_links.yml 不加 --browser,照舊只跑 Postype。
   Playwright 是可選相依(requirements.txt 註解裡的那行):沒裝就 is_available() = False,check_links.py 印提示並略過這三個平台。

   判斷邏輯全部在純函式 classify(platform, final_url, status, html, url='', error='') → 跟 checkers 同形狀的結果
   {status, author_name, reason, code, final, …};pytest 用 tests/fixtures/html/ 的合成樣本直接測,不碰瀏覽器。
   ⚠️ 這些規則(尤其 Lofter 帶 cookie 之後的頁面、AFF 訂閱頁)是依已知行為寫的、尚未在真瀏覽器實測,
   請先用 `python check_links.py --browser --probe` 在本機跑一遍,把輸出貼回來修規則。

   各平台:
   - Lofter:啟動前載入 cookies/lofter.json(「Get cookies.txt LOCALLY」或 Cookie-Editor 匯出的 JSON;也吃 Netscape cookies.txt)。
       沒有 cookie 檔 → 印提示、略過 Lofter。帶了 cookie 仍被導到 www.lofter.com/front/login → cookie 過期:login_required(blocked,
       不算死)並略過其餘 Lofter 連結。404 / 頁面顯示「页面不存在」→ deleted;整個部落格打不開(子網域 DNS 不存在 /
       連線被拒,且 www.lofter.com 本身連得上)或頁面顯示「博客不存在」→ deleted,reason = blog_gone。
       啟動時看 LOFTER_SESS 的到期日:剩不到 COOKIE_WARN_DAYS 天印醒目警告,已過期就略過 Lofter。
   - AO3:網址自動加 ?view_adult=true 跳過成人確認頁。404 或「Sorry, we couldn't find the work you were looking for」→ deleted;
       「This work is only available to registered users」→ login_required(不算死)。另外解析章節進度(Chapters: 5/10、5/?)
       與 Completed 日期,放在結果的 extra 欄位(check_links.advance 會存進 link_status.json),先只記錄、不寫回 Notion。
   - Asianfanfics:正常、或顯示 SUBSCRIBERS ONLY / Please subscribe to read 都算 ok(文還在,只是要訂閱);404 Page Not Found → deleted。
   - 共用:同平台順序跑、每筆間隔 GAP 隨機 2~4 秒;每個平台一個 browser context 重用(不每筆開新瀏覽器);逾時 TIMEOUT_MS = 20 秒 → unknown;
       Cloudflare 挑戰頁(Just a moment / cf-challenge…)等 CF_WAIT = 8 秒再抓一次,仍擋 → unknown 並計數,同平台連續 CF_MAX_STREAK = 5 筆
       就略過該平台並印警告。啟動時 GET https://www.cloudflare.com/cdn-cgi/trace,回應含 warp=on 就印提示並略過三個平台(WARP 的出口 IP 會被擋)。
   瀏覽器:預設 Playwright 內建的 Chromium(無頭;UA 裡的 HeadlessChrome 會換成 Chrome);--browser-channel chrome 改用系統 Chrome、
       --headed 開視窗看畫面、環境變數 AZ_BROWSER_EXE 直接指定執行檔。
   用法:由 check_links.py 呼叫(--browser / --probe);本檔不自己當 main。"""
import io, json, os, random, re, time, urllib.request
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit

from checkers import _http as H
from checkers import lofter as _lofter, ao3 as _ao3, aff as _aff

PLATFORMS = ('lofter', 'ao3', 'aff')
GAP = (2.0, 4.0)            # 同平台每筆間隔(秒,隨機)
TIMEOUT_MS = 20000          # 單頁逾時 → unknown
SETTLE_MS = 3000            # domcontentloaded 之後再等 networkidle 最多這麼久(讓 JS 把內容畫出來;逾時不算錯)
CF_WAIT = 8                 # 遇到 Cloudflare 挑戰頁:等幾秒再抓一次
CF_MAX_STREAK = 5           # 同平台連續幾筆挑戰頁就略過該平台
COOKIE_DIR = 'cookies'
COOKIE_FILE = os.path.join(COOKIE_DIR, 'lofter.json')
COOKIE_SESS = 'LOFTER_SESS'
COOKIE_WARN_DAYS = 3
WARP_TRACE = 'https://www.cloudflare.com/cdn-cgi/trace'
TZ = timezone(timedelta(hours=8))
INSTALL_HINT = 'pip install playwright && playwright install chromium'

CF_MARKERS = ('Just a moment', 'cf-challenge', 'cf-chl-', '_cf_chl_opt', 'Request temporarily denied',
              'Verify you are human', 'Checking your browser', 'Attention Required! | Cloudflare')
LOFTER_BLOG_GONE = ('博客不存在', '该博客不存在', '博客已注销', '该博客已注销', '博主已注销', '博客已关闭', '该用户不存在')
LOFTER_GONE = _lofter.GONE_TEXT + ('文章不存在', '该文章不存在', '该文章已被删除', '内容不存在', '404')
AFF_SUBSCRIBE = ('subscribers only', 'please subscribe to read', 'subscribe to read', 'subscribe to this story to read')
AFF_GONE = tuple(k for k in _aff.GONE_TEXT if k != 'the page you requested') + ('404 page not found',)
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
    """Cloudflare 挑戰頁:看 <head> 附近有沒有標記字樣(不看狀態碼,真瀏覽器拿到的挑戰頁有時是 200 / 403 / 503 / 418)。"""
    return any(k in (html or '')[:30000] for k in CF_MARKERS)

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
    blocked(平台層級被擋,呼叫端略過該平台其餘連結)、extra(AO3 章節進度)。"""
    final = final_url or url
    if error:
        return _nav_error_result(platform, error, final, url)
    body = html or ''
    if is_cf_challenge(status, body):
        return H.result('unknown', reason='cf_challenge', code=status, final=final, blocked=True, challenge=True)
    if platform == 'lofter':
        return _classify_lofter(final, status, body, url)
    if platform == 'ao3':
        return _classify_ao3(final, status, body, url)
    if platform == 'aff':
        return _classify_aff(final, status, body, url)
    return H.result('unknown', reason='unsupported', code=status, final=final)

def blog_root_gone(status, html, error=''):
    """Lofter 部落格首頁(https://xxx.lofter.com/)還在不在:DNS / 連線錯誤、404、或頁面說博客不存在 → True(整個部落格沒了)。"""
    if error:
        return any(error.startswith(k) for k in NET_GONE)
    if status == 404:
        return True
    return any(k in H.text_of((html or '')[:200000]) for k in LOFTER_BLOG_GONE)

def _classify_lofter(final, status, body, url):
    fh, fp = H.host_of(final), H.path_of(final)
    if fh in ('www.lofter.com', 'lofter.com') and (fp.startswith(_lofter.LOGIN_PATH) or fp.rstrip('/') == '/login'):
        return H.result('login_required', reason='login_wall', code=status, final=final, blocked=True)
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
    return H.result('ok', _lofter._blog_name(body), reason='200', code=status, final=final, author_url=fh)

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
    low = H.text_of(body[:300000]).lower()
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
    1 筆 Notion 已標 ❌、1 筆不存在的網址;Lofter 多一筆「整個部落格不存在」。回傳 [(說明, 網址)]。"""
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
    return out

# ---------- 瀏覽器 ----------

class BrowserSession:
    """一個 Playwright + 一個 Chromium;每個平台一個 context(Lofter 的帶 cookie)與一個 page 重用。
    sync API 只能在建立它的那條執行緒用,所以 start / check / close 都要在同一條執行緒(check_links.py 用一條執行緒跑三個平台)。"""
    def __init__(self, cookies=None, headed=False, channel='', log=print, sleep=time.sleep, executable=''):
        self.cookies, self.headed, self.channel, self.log, self.sleep = (cookies or {}), headed, channel, log, sleep
        self.executable = executable or os.environ.get('AZ_BROWSER_EXE', '')   # 指定瀏覽器執行檔(例如系統 Chrome 的 chrome.exe);留空用 Playwright 內建 Chromium
        self._pw = self._browser = self._ua = None
        self._ctx = {}
        self._reach = {}
        self.last = None     # 最後一次 fetch 的 (status, final, html, error),--probe 印頁面文字用

    def start(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {'headless': not self.headed}
        if self.channel:
            kw['channel'] = self.channel
        if self.executable:
            kw['executable_path'] = self.executable
        self._browser = self._pw.chromium.launch(**kw)
        tmp = self._browser.new_context()
        try:
            ua = tmp.new_page().evaluate('navigator.userAgent')
        finally:
            tmp.close()
        self._ua = (ua or H.UA).replace('HeadlessChrome', 'Chrome')   # 無頭模式預設 UA 帶 HeadlessChrome,會被當機器人
        self.log('瀏覽器:%s %s%s' % (self._browser.browser_type.name, self._browser.version, '(有頭)' if self.headed else ''))
        return self

    def close(self):
        for ctx, _ in self._ctx.values():
            try:
                ctx.close()
            except Exception:
                pass
        self._ctx = {}
        for obj in (self._browser, self._pw):
            try:
                if obj:
                    obj.close() if obj is self._browser else obj.stop()
            except Exception:
                pass
        self._browser = self._pw = None

    def page_for(self, plat):
        if plat not in self._ctx:
            ctx = self._browser.new_context(user_agent=self._ua, locale='zh-TW', viewport={'width': 1280, 'height': 900})
            if self.cookies.get(plat):
                ctx.add_cookies(self.cookies[plat])
            self._ctx[plat] = (ctx, ctx.new_page())
        return self._ctx[plat][1]

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
        try:
            html = page.content()
        except PWError:
            html = ''
        return (resp.status if resp else None), page.url, html, ''

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
            self.sleep(random.uniform(*GAP))
            st, _, html, err = self.fetch('lofter', 'https://%s/' % host)
            self._reach[key] = blog_root_gone(st, html, self._qualify_error('lofter', err))
        return self._reach[key]

    def check(self, plat, url):
        """抓一筆並判斷;Cloudflare 挑戰頁等 CF_WAIT 秒再抓一次;Lofter 某篇已刪時再看部落格首頁在不在(reason 改成 blog_gone)。
        回傳 checkers 形狀的結果。"""
        target = _ao3.with_view_adult(url) if plat == 'ao3' else url
        st, final, html, err = self.fetch(plat, target)
        res = classify(plat, final, st, html, url=url, error=self._qualify_error(plat, err))
        if res.get('challenge'):
            self.sleep(CF_WAIT)
            st, final, html, err = self.fetch(plat, target)
            res = classify(plat, final, st, html, url=url, error=self._qualify_error(plat, err))
            if res.get('challenge'):
                res['reason'] = 'cf_challenge_x2'
        self.last = (st, final, html, err)
        if plat == 'lofter' and res['status'] == 'deleted' and res.get('reason') != 'blog_gone' and '/post/' in H.path_of(url):
            host = H.host_of(url)
            if host.endswith('.lofter.com') and host != 'www.lofter.com' and self.lofter_blog_gone(host):
                res['reason'], res['detail'] = 'blog_gone', 'post:' + str(res.get('reason'))
        res.setdefault('final', final)
        return res

# ---------- 跟 check_links.py 接的部分 ----------

def preflight(src_dir, platforms, log=print, now=None, trace=None):
    """啟動前檢查,不開瀏覽器:Playwright 有沒有裝、WARP 有沒有開、Lofter cookie 在不在 / 過期沒。
    回傳 {'available', 'warp', 'usable': [可跑的平台], 'notes': {平台: 略過原因}, 'cookies': {平台: cookie 清單}}。"""
    pre = {'available': is_available(), 'warp': False, 'usable': [], 'notes': {}, 'cookies': {}}
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
                log('Lofter cookie:%d 筆,%s %s' % (len(cookies), COOKIE_SESS, '到期 ' + fmt_dt(exp) if exp else '(session cookie,無到期日)'))
            pre['cookies'][p] = cookies
        pre['usable'].append(p)
    return pre

def skip_stat(n, note):
    return {'checked': 0, 'blocked': True, 'skipped': n, 'challenges': 0, 'note': note}

def run_platform(plat, targets, session, results, lock, verbose=False, log=print, sleep=time.sleep):
    """一個平台順序跑完(呼叫端保證在 session 的執行緒上)。回傳 {'checked','blocked','skipped','challenges', 'note'?}。
    - Cloudflare 挑戰頁連續 CF_MAX_STREAK 筆 → 略過其餘並印警告
    - Lofter 登入牆(blocked 且不是挑戰頁)→ cookie 過期,略過其餘(狀態 login_required,不算死)"""
    stat = {'checked': 0, 'blocked': False, 'skipped': 0, 'challenges': 0}
    streak = 0
    for i, t in enumerate(targets):
        res = session.check(plat, t['url'])
        with lock:
            results[t['url']] = res
        stat['checked'] += 1
        if verbose or res['status'] != 'ok':
            log('  [%s] %-14s %s  %s' % (plat, res['status'] + ('(' + str(res.get('reason')) + ')' if res.get('reason') else ''),
                                         t['url'], res.get('author_name') or ''))
        if res.get('challenge'):
            stat['challenges'] += 1
            streak += 1
            if streak >= CF_MAX_STREAK:
                stat['blocked'], stat['skipped'] = True, len(targets) - stat['checked']
                stat['note'] = 'Cloudflare 挑戰頁連續 %d 筆' % streak
                log('  ⚠️ [%s] Cloudflare 挑戰頁連續 %d 筆 → 本次略過此平台其餘 %d 筆(請確認 WARP / VPN 已關、或改用 --headed 看看畫面)' % (plat, streak, stat['skipped']))
                break
        else:
            streak = 0
            if res.get('blocked'):
                stat['blocked'], stat['skipped'] = True, len(targets) - stat['checked']
                stat['note'] = '登入牆(cookie 過期或無效)'
                log('  ⚠️ [%s] 帶了 cookie 仍被導到登入頁 → cookie 已過期或無效,請重新匯出 %s;本次略過其餘 %d 筆(不算已刪)' % (plat, COOKIE_FILE, stat['skipped']))
                break
        if i < len(targets) - 1:
            sleep(random.uniform(*GAP))
    return stat

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
        session = BrowserSession(cookies=pre['cookies'], headed=headed, channel=channel, log=log)
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
        session = BrowserSession(cookies=pre['cookies'], headed=headed, channel=channel, log=log).start()
    try:
        for p in todo:
            samples = pick_probe_samples(targets, state, p)
            log('')
            log('===== %s(%d 筆)=====' % (p, len(samples)))
            for label, url in samples:
                t0 = time.time()
                res = session.check(p, url)
                st, final, html, err = session.last or (None, url, '', '')
                log('--- %s' % label)
                log('    網址:%s' % url)
                log('    最終:%s' % final)
                log('    狀態碼:%s  導覽錯誤:%s  耗時:%.1fs' % (st, err or '-', time.time() - t0))
                log('    判定:%s(%s)  作者:%s%s' % (res['status'], res.get('reason'), res.get('author_name') or '-',
                                                   '  extra=' + json.dumps(res['extra'], ensure_ascii=False) if res.get('extra') else ''))
                log('    頁面文字:%s' % H.text_of(html)[:300].replace('\n', ' '))
                log('    <title>:%s' % H.title_of(html))
                session.sleep(random.uniform(*GAP))
    finally:
        if own:
            session.close()
