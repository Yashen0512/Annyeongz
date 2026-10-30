# -*- coding: utf-8 -*-
"""AO3(archiveofourown.org)— ⚠️ 2026-10-30 probe.py 實測:雲端 IP 一律 418「Request temporarily denied」
   (Cloudflare 挑戰頁,正常 / 已刪 / 不存在三種都一樣),所以在 GitHub Actions 上這個平台等於「略過」:
   回 unknown(blocked),不會把任何 AO3 連結標成已刪。以下規則依 AO3 已知行為寫成、尚未實測:
   - 404,內文含「Sorry, we couldn't find the work you were looking for」→ deleted(404 本身就足夠)
   - 200,內文含「This work is only available to registered users」或被導到 /users/login → login_required(不是已刪)
   - 成人內容中間頁(「This work could have adult content」):抓的時候帶 ?view_adult=true 直接跳過;
     若仍遇到 → ok(作品還在),author_name 盡量從頁面的 byline 解析
   - 200 且有 byline(<h3 class="byline heading"><a rel="author" href="/users/帳號/pseuds/筆名">筆名</a>)→ ok,
     author_name = 筆名(pseud);Anonymous / 孤兒化作品沒有 <a rel="author"> → None
   - 418 / 403 / 503 + Cloudflare 挑戰 → unknown(blocked)"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from . import _http as H

NOT_FOUND = "couldn't find the work"
LOGIN_ONLY = 'only available to registered users'
ADULT = 'could have adult content'
CF = ('Request temporarily denied', 'Just a moment', 'cf-chl', '_cf_chl_opt', 'challenge-platform')

def with_view_adult(url):
    sp = urlsplit(url)
    q = dict(parse_qsl(sp.query, keep_blank_values=True))
    q.setdefault('view_adult', 'true')
    return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(q), sp.fragment))

def _byline(html):
    m = re.search(r'<h3[^>]*class=["\'][^"\']*byline[^"\']*["\'][^>]*>(.*?)</h3>', html or '', re.S | re.I)
    seg = m.group(1) if m else (html or '')[:300000]
    a = re.search(r'<a[^>]+rel=["\']author["\'][^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', seg, re.S | re.I) \
        or re.search(r'<a[^>]+href=["\']([^"\']*)["\'][^>]+rel=["\']author["\'][^>]*>(.*?)</a>', seg, re.S | re.I)
    if not a:
        return None, ''
    return H.unescape(re.sub(r'<[^>]+>', '', a.group(2))), a.group(1)

def parse(code, final, html, url=''):
    body = html or ''
    if code in (418, 403, 503, 429) or any(k in body[:20000] for k in CF):
        return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
    if code == 404:
        return H.result('deleted', reason='404' + ('_text' if NOT_FOUND in body else ''), code=code, final=final)
    if code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    if '/users/login' in H.path_of(final) or LOGIN_ONLY in body:
        return H.result('login_required', reason='login_only', code=code, final=final)
    name, href = _byline(body)
    if ADULT in body:
        return H.result('ok', name, reason='adult_interstitial', code=code, final=final, author_url=href)
    if name or 'id="workskin"' in body or 'class="work meta group"' in body:
        return H.result('ok', name, reason='byline' if name else 'workskin', code=code, final=final, author_url=href)
    return H.result('unknown', reason='no_markers', code=code, final=final)

def check(url):
    code, final, html = H.fetch(with_view_adult(url))
    return parse(code, final, html, url)
