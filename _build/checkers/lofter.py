# -*- coding: utf-8 -*-
"""Lofter(xxx.lofter.com)— ⚠️ 2026-10-30 probe.py 實測:雲端 / 海外 IP 不論正常、已刪、不存在,
   全部 302 → https://www.lofter.com/front/login(登入牆,連 /rss 也回空),所以在 GitHub Actions 上
   這個平台等於「略過」:一律回 login_required(blocked),不會把任何 Lofter 連結標成已刪。
   以下規則依已知行為寫成、尚未實測,站長在能看到 Lofter 的網路環境執行時才會用到:
   - 404 → deleted
   - 原網址是 /post/…,最終網址被導回該部落格首頁(路徑 /)或 www.lofter.com 首頁 → deleted(刪文常見導向)
   - 200 且內文含「页面不存在」「该页面不存在」「博客不存在」「内容已删除」等 → deleted
   - 最終網址是 www.lofter.com/front/login 或頁面是登入表單 → login_required
   - 其餘 200 → ok;author_name 取 og:site_name,沒有就取 <title> 最後一段的博客名(「標題 - 博客名」),都沒有 → None"""
import re
from . import _http as H

GONE_TEXT = ('该页面不存在', '頁面不存在', '页面不存在', '博客不存在', '内容已删除', '该内容已被删除', '抱歉，你访问的页面')
LOGIN_PATH = '/front/login'

def _blog_name(html):
    n = H.meta(html, 'og:site_name')
    if n:
        return n
    t = H.title_of(html)
    if ' - ' in t:
        return t.rsplit(' - ', 1)[1].strip() or None
    if '-' in t and len(t) < 80:
        return t.rsplit('-', 1)[1].strip() or None
    return None

def parse(code, final, html, url=''):
    fh, fp = H.host_of(final), H.path_of(final)
    if fh == 'www.lofter.com' and fp.startswith(LOGIN_PATH):
        return H.result('login_required', reason='login_wall', blocked=True, code=code, final=final)
    if code == 404:
        return H.result('deleted', reason='404', code=code, final=final)
    if code in (403, 429):
        return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
    if code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    if '/post/' in H.path_of(url) and (fp in ('', '/') or fh in ('www.lofter.com', 'lofter.com')):
        return H.result('deleted', reason='redirect_home', code=code, final=final)
    txt = H.text_of(html[:200000])
    if any(k in txt for k in GONE_TEXT):
        return H.result('deleted', reason='gone_text', code=code, final=final)
    if re.search(r'(登录|登錄)\s*LOFTER', txt) and 'post' not in H.path_of(final):
        return H.result('login_required', reason='login_form', code=code, final=final)
    return H.result('ok', _blog_name(html), reason='200', code=code, final=final, author_url=fh)

def check(url):
    code, final, html = H.fetch(url)
    return parse(code, final, html, url)
