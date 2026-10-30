# -*- coding: utf-8 -*-
"""checkers 共用的 HTTP 抓取與 HTML 小工具。只用標準庫,帶一般瀏覽器 User-Agent,跟隨轉址並回報最終網址。
   逾時 / 連線錯誤 / 5xx / 429 一律丟 TransientError,由 check_links.py 決定重試;4xx 正常回傳(內文照讀)。"""
import gzip, html as _html, http.cookiejar, json, re, ssl, urllib.error, urllib.request
from urllib.parse import urlsplit

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
HEADERS = {'User-Agent': UA,
           'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
           'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8,ko;q=0.7',
           'Accept-Encoding': 'gzip'}
TIMEOUT = 30
MAX_BYTES = 1_500_000   # 只讀前 1.5MB,判斷與解析作者名都在 <head> / 頁首

class TransientError(Exception):
    """暫時性失敗(逾時、連線錯、5xx、429):可以重試;重試仍失敗 = unknown,不算已刪。"""

def _ssl_context():
    try:
        import truststore            # 站長電腦若有裝,直接信任系統憑證庫(同 fetch_data.py)
        truststore.inject_into_ssl()
    except ImportError:
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            pass
    return ssl.create_default_context()
SSL_CTX = _ssl_context()

def fetch(url, timeout=TIMEOUT, extra_headers=None):
    """回傳 (狀態碼, 最終網址, 內文字串)。4xx 也回傳(讀內文);網路錯誤 / 5xx / 429 丟 TransientError。"""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                         urllib.request.HTTPSHandler(context=SSL_CTX))
    hdr = dict(HEADERS)
    if extra_headers:
        hdr.update(extra_headers)
    req = urllib.request.Request(url, headers=hdr)
    try:
        resp = opener.open(req, timeout=timeout)
        code, final, raw, enc = resp.status, resp.geturl(), resp.read(MAX_BYTES), resp.headers.get('Content-Encoding')
    except urllib.error.HTTPError as e:
        if e.code >= 500 or e.code == 429:
            raise TransientError('HTTP %d' % e.code)
        try:
            raw = e.read(MAX_BYTES)
        except Exception:
            raw = b''
        code, final, enc = e.code, e.geturl() or url, e.headers.get('Content-Encoding')
    except (urllib.error.URLError, TimeoutError, OSError, ConnectionError) as e:
        raise TransientError(repr(e))
    if (enc or '').lower() == 'gzip':
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass   # 被 MAX_BYTES 截斷時解不開;退回原樣(通常 head 已足夠)
    return code, final, raw.decode('utf-8', 'replace')

# ---- HTML 小工具(純函式) ----
def unescape(s):
    return _html.unescape(s or '').strip()

def title_of(html):
    m = re.search(r'<title[^>]*>(.*?)</title>', html or '', re.S | re.I)
    return unescape(re.sub(r'\s+', ' ', m.group(1))) if m else ''

def meta(html, prop):
    """<meta property="og:xxx" content="…"> 或 name="…";找不到回 ''。"""
    pat = r'<meta[^>]+(?:property|name)=["\']%s["\'][^>]*content=["\']([^"\']*)["\']' % re.escape(prop)
    m = re.search(pat, html or '', re.I)
    if not m:   # content 在前、property 在後的寫法
        pat2 = r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']%s["\']' % re.escape(prop)
        m = re.search(pat2, html or '', re.I)
    return unescape(m.group(1)) if m else ''

def ld_json(html):
    """所有 <script type="application/ld+json"> 解析成 list(解析失敗的略過)。"""
    out = []
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html or '', re.S | re.I):
        try:
            j = json.loads(m.group(1))
        except Exception:
            continue
        out.extend(j if isinstance(j, list) else [j])
    return out

def text_of(html):
    """去掉 script/style 與標籤的可見文字(壓縮空白),給關鍵字判斷用。"""
    s = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html or '', flags=re.S | re.I)
    s = re.sub(r'<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', unescape(s))

def host_of(url):
    return (urlsplit(url or '').hostname or '').lower()

def path_of(url):
    return urlsplit(url or '').path or '/'

def result(status, author_name=None, **extra):
    r = {'status': status, 'author_name': author_name or None}
    r.update(extra)
    return r
