# -*- coding: utf-8 -*-
"""原文平台連結檢查器(供 check_links.py 使用)。只用標準庫。

共用介面:check(url) → {'status': 'ok' | 'deleted' | 'login_required' | 'unknown', 'author_name': str | None, …}
    - status        ok = 作品還在;deleted = 確定已刪(404 / 平台的「不存在」頁 / 導向首頁);
                    login_required = 要登入或要過中間頁才看得到(不是已刪);unknown = 判斷不了(被擋、5xx、逾時…)
    - author_name   頁面上解析到的作者「目前顯示名」;解析不到就是 None,不猜
    其餘鍵是輔助資訊:code(HTTP 狀態碼)、final(最終網址)、reason(判斷依據的簡短代碼)、
    blocked(True = 整個平台層級被擋:登入牆 / Cloudflare 挑戰頁,check_links.py 會據此略過該平台其餘連結)、
    author_url(作者頁網址或帳號,供 check_links.py 核對作者庫的平台網址,避免把合集帳號當成作者改名)。

每個平台一個模組,各有純函式 parse(code, final_url, html, url) → 結果 dict(pytest 直接餵 HTML 樣本測這個),
check(url) = _http.fetch() + parse()。網路錯誤與 5xx 由 _http.fetch 丟出 TransientError,交給 check_links.py 重試。

平台 → 網域:
    postype  www.postype.com、*.postype.com
    lofter   *.lofter.com(www.lofter.com/front/login 是登入牆)
    ao3      archiveofourown.org
    aff      www.asianfanfics.com
"""
from urllib.parse import urlsplit
from . import postype, lofter, ao3, aff

PLATFORMS = {'postype': postype, 'lofter': lofter, 'ao3': ao3, 'aff': aff}
PLATFORM_LABEL = {'postype': 'Postype', 'lofter': 'Lofter', 'ao3': 'AO3', 'aff': 'Asianfanfics'}

def platform_of(url):
    """網址 → 平台代碼;不是四個平台之一(微博、X、站內互連 annyeongz:…)回 None。"""
    if not url or not url.lower().startswith(('http://', 'https://')):
        return None
    host = (urlsplit(url).hostname or '').lower()
    if host == 'postype.com' or host.endswith('.postype.com'):
        return 'postype'
    if host == 'lofter.com' or host.endswith('.lofter.com'):
        return 'lofter'
    if host == 'archiveofourown.org' or host.endswith('.archiveofourown.org'):
        return 'ao3'
    if host == 'asianfanfics.com' or host.endswith('.asianfanfics.com'):
        return 'aff'
    return None

def check(url):
    """依網域分派;不支援的平台回 unknown(reason='unsupported')。"""
    plat = platform_of(url)
    if not plat:
        return {'status': 'unknown', 'author_name': None, 'reason': 'unsupported', 'code': None, 'final': url}
    return PLATFORMS[plat].check(url)
