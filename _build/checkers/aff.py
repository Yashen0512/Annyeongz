# -*- coding: utf-8 -*-
"""Asianfanfics(www.asianfanfics.com)— ⚠️ 2026-10-30 probe.py 實測:雲端 IP 一律 403 + Cloudflare
   「Just a moment…」受管挑戰頁(正常 / 已刪 / 不存在三種都一樣),所以在 GitHub Actions 上這個平台等於「略過」:
   回 unknown(blocked),不會把任何 AFF 連結標成已刪。以下規則依已知行為寫成、尚未實測:
   - 404 → deleted
   - 原網址是 /story/view/…,最終網址被導到首頁(路徑 / 或 /home)→ deleted
   - 200 且內文含「story does not exist」「story has been deleted」「not found」類字樣 → deleted
   - 200 且內文含「subscribers only」「members only」「log in to view」→ login_required
   - 200 且有作者連結(<a href=".../profile/view/數字">作者名</a>)→ ok,author_name = 連結文字
   - 200 但找不到作者連結也沒有上述字樣(「內容為空」)→ 保守回 unknown(reason=empty),不自動當成已刪"""
import re
from . import _http as H

GONE_TEXT = ('story does not exist', 'story has been deleted', 'this story has been removed',
             'story not found', 'page not found', 'the page you requested')
LOGIN_TEXT = ('subscribers only', 'members only', 'log in to view', 'login to view', 'must be logged in')
CF = ('Just a moment', '_cf_chl_opt', 'cf-chl', 'challenge-platform')

def _author(html):
    m = re.search(r'<a[^>]+href=["\'](?:https?://(?:www\.)?asianfanfics\.com)?(/profile/view/\d+)["\'][^>]*>(.*?)</a>',
                  html or '', re.S | re.I)
    if not m:
        return None, ''
    name = H.unescape(re.sub(r'<[^>]+>', '', m.group(2)))
    return (name or None), m.group(1)

def parse(code, final, html, url=''):
    body = html or ''
    if code in (403, 503, 429) or any(k in body[:20000] for k in CF):
        return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
    if code == 404:
        return H.result('deleted', reason='404', code=code, final=final)
    if code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    fp = H.path_of(final).rstrip('/')
    if '/story/view/' in H.path_of(url) and fp in ('', '/home'):
        return H.result('deleted', reason='redirect_home', code=code, final=final)
    low = H.text_of(body[:300000]).lower()
    if any(k in low for k in GONE_TEXT):
        return H.result('deleted', reason='gone_text', code=code, final=final)
    if any(k in low for k in LOGIN_TEXT):
        return H.result('login_required', reason='login_text', code=code, final=final)
    name, href = _author(body)
    if name:
        return H.result('ok', name, reason='author_link', code=code, final=final, author_url=href)
    return H.result('unknown', reason='empty', code=code, final=final)

def check(url):
    code, final, html = H.fetch(url)
    return parse(code, final, html, url)
