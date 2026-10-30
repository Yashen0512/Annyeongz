# -*- coding: utf-8 -*-
"""Postype(www.postype.com)— 2026-10-30 以 probe.py 實測的判斷依據(三種樣本都驗過):
   - 正常作品:200,<head> 有 ld+json {"@type":"BlogPosting", "author":{"@type":"Person","name":…,"url":"…/profile/@帳號"}}
     → ok;author_name = ld+json author.name(= 作者目前的暱稱;Next.js 資料裡的 nickname 同值)
   - 已刪作品 / 不存在的編號:直接 404(頁面是站方錯誤頁「앗, 존재하지 않는 길이에요.」)→ deleted
   - 另外保守處理:200 但內文含「존재하지 않는 글」或被導到首頁 / 部落格首頁(最終網址沒有 /post/)→ deleted
   - 403 / 429 / Cloudflare 類挑戰頁 → unknown(blocked)
   - 200 但沒有 ld+json、<title> 又是站名(「포스타입 - …」)→ unknown(可能是需要登入的會員限定頁;不猜)
   會員限定 / 成人認證的文仍是 200 + ld+json,所以算 ok(作品還在)。"""
import re
from . import _http as H

GONE_TEXT = ('존재하지 않는 글', '존재하지 않는 포스트', '삭제된 글', '삭제된 포스트')
SITE_TITLE = '포스타입'

def _author_from_ld(html):
    for j in H.ld_json(html):
        if not isinstance(j, dict):
            continue
        au = j.get('author')
        if isinstance(au, list):
            au = au[0] if au else None
        if isinstance(au, dict) and au.get('name'):
            return H.unescape(str(au['name'])), (au.get('url') or '').strip()
    return None, ''

def _nickname(html):
    m = re.search(r'nickname\\?":\\?"((?:[^"\\]|\\.)*?)\\?"', html or '')
    return H.unescape(m.group(1)) if m else None

def parse(code, final, html, url=''):
    if code == 404:
        return H.result('deleted', reason='404', code=code, final=final)
    if code in (403, 429) or 'cf-chl' in (html or '')[:5000] or '_cf_chl_opt' in (html or ''):
        return H.result('unknown', reason='blocked', blocked=True, code=code, final=final)
    if code != 200:
        return H.result('unknown', reason='http_%s' % code, code=code, final=final)
    if '/post/' in H.path_of(url) and '/post/' not in H.path_of(final):
        return H.result('deleted', reason='redirect_home', code=code, final=final)
    txt = H.text_of(html[:200000])
    if any(k in txt for k in GONE_TEXT):
        return H.result('deleted', reason='gone_text', code=code, final=final)
    name, au_url = _author_from_ld(html)
    if name:
        return H.result('ok', name, reason='ld_json', code=code, final=final, author_url=au_url)
    nick = _nickname(html)
    if nick:
        return H.result('ok', nick, reason='nickname', code=code, final=final, author_url='')
    t = H.title_of(html)
    if t and not t.startswith(SITE_TITLE):
        return H.result('ok', None, reason='title_only', code=code, final=final)
    return H.result('unknown', reason='no_markers', code=code, final=final)

def check(url):
    code, final, html = H.fetch(url)
    return parse(code, final, html, url)
