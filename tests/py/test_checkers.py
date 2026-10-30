# -*- coding: utf-8 -*-
"""checkers/*.py:用 tests/fixtures/html/ 的 HTML 樣本(依 probe.py 實測結構仿寫的最小樣本)測各平台的 parse() 純函式,
   不碰網路。Postype 三種樣本是 2026-10-30 實測過的;Lofter / AO3 / AFF 在雲端被登入牆 / Cloudflare 擋住,
   樣本依已知行為寫成(見各 checker 檔頭)。"""
import io, os
import pytest
from conftest import ROOT
import checkers
from checkers import postype, lofter, ao3, aff, _http

HTML = os.path.join(ROOT, 'tests', 'fixtures', 'html')
def load(name):
    return io.open(os.path.join(HTML, name), encoding='utf-8').read()

def test_platform_of():
    assert checkers.platform_of('https://www.postype.com/@a/post/1') == 'postype'
    assert checkers.platform_of('https://sub.postype.com/post/1') == 'postype'
    assert checkers.platform_of('https://xxx.lofter.com/post/1_2') == 'lofter'
    assert checkers.platform_of('https://archiveofourown.org/works/1') == 'ao3'
    assert checkers.platform_of('https://www.asianfanfics.com/story/view/1/x') == 'aff'
    assert checkers.platform_of('https://weibo.com/u/1') is None
    assert checkers.platform_of('annyeongz:123') is None
    assert checkers.platform_of('') is None

def test_check_unsupported_platform_is_unknown():
    assert checkers.check('https://weibo.com/u/1')['status'] == 'unknown'

# ---- Postype(實測) ----
PT = 'https://www.postype.com/@testblog/post/12345678'
def test_postype_ok_parses_author_from_ld_json():
    r = postype.parse(200, PT, load('postype_ok.html'), PT)
    assert r['status'] == 'ok' and r['author_name'] == '새이름(新名)'
    assert r['author_url'] == 'https://www.postype.com/profile/@abc123'

def test_postype_404_is_deleted():
    r = postype.parse(404, PT, load('postype_404.html'), PT)
    assert r['status'] == 'deleted' and r['author_name'] is None and r['reason'] == '404'

def test_postype_200_gone_text_is_deleted():
    assert postype.parse(200, PT, load('postype_gone200.html'), PT)['status'] == 'deleted'

def test_postype_redirect_to_home_is_deleted():
    assert postype.parse(200, 'https://www.postype.com/', load('postype_404.html'), PT)['status'] == 'deleted'

def test_postype_403_is_unknown_blocked():
    r = postype.parse(403, PT, '', PT)
    assert r['status'] == 'unknown' and r.get('blocked')

def test_postype_200_without_markers_is_unknown():
    assert postype.parse(200, PT, load('postype_404.html'), PT)['status'] == 'unknown'

# ---- Lofter ----
LF = 'https://testblog.lofter.com/post/1a2b3c4d_5e6f7a8b9'
def test_lofter_login_wall_is_login_required_and_blocked():
    r = lofter.parse(200, 'https://www.lofter.com/front/login', load('lofter_login.html'), LF)
    assert r['status'] == 'login_required' and r.get('blocked')

def test_lofter_ok_author_from_og_site_name():
    r = lofter.parse(200, LF, load('lofter_ok.html'), LF)
    assert r['status'] == 'ok' and r['author_name'] == '測試博客'

def test_lofter_title_fallback_for_blog_name():
    html = load('lofter_ok.html').replace('<meta property="og:site_name" content="測試博客"/>', '')
    assert lofter.parse(200, LF, html, LF)['author_name'] == '測試博客'

def test_lofter_deleted_cases():
    assert lofter.parse(404, LF, '', LF)['status'] == 'deleted'
    assert lofter.parse(200, 'https://testblog.lofter.com/', load('lofter_ok.html'), LF)['reason'] == 'redirect_home'
    assert lofter.parse(200, LF, load('lofter_gone.html'), LF)['status'] == 'deleted'

# ---- AO3 ----
A3 = 'https://archiveofourown.org/works/123'
def test_ao3_ok_parses_pseud():
    r = ao3.parse(200, A3, load('ao3_ok.html'), A3)
    assert r['status'] == 'ok' and r['author_name'] == 'testpseud' and '/users/testuser/' in r['author_url']

def test_ao3_404_is_deleted():
    assert ao3.parse(404, A3, load('ao3_404.html'), A3)['status'] == 'deleted'

def test_ao3_registered_only_is_login_required_not_deleted():
    r = ao3.parse(200, A3, load('ao3_login.html'), A3)
    assert r['status'] == 'login_required'

def test_ao3_adult_interstitial_is_ok():
    r = ao3.parse(200, A3, load('ao3_adult.html'), A3)
    assert r['status'] == 'ok' and r['author_name'] == 'testpseud'

def test_ao3_cloudflare_418_is_unknown_blocked():
    r = ao3.parse(418, A3, load('ao3_cf.html'), A3)
    assert r['status'] == 'unknown' and r.get('blocked')

def test_ao3_view_adult_param():
    assert ao3.with_view_adult(A3) == A3 + '?view_adult=true'
    assert ao3.with_view_adult(A3 + '?view_adult=true') == A3 + '?view_adult=true'

# ---- Asianfanfics ----
AF = 'https://www.asianfanfics.com/story/view/123/test'
def test_aff_ok_author_link_text():
    r = aff.parse(200, AF, load('aff_ok.html'), AF)
    assert r['status'] == 'ok' and r['author_name'] == 'testwriter' and r['author_url'] == '/profile/view/123456'

def test_aff_cloudflare_403_is_unknown_blocked():
    r = aff.parse(403, AF, load('aff_cf.html'), AF)
    assert r['status'] == 'unknown' and r.get('blocked')

def test_aff_deleted_cases():
    assert aff.parse(404, AF, '', AF)['status'] == 'deleted'
    assert aff.parse(200, 'https://www.asianfanfics.com/', load('aff_empty.html'), AF)['reason'] == 'redirect_home'

def test_aff_subscribers_only_is_login_required():
    assert aff.parse(200, AF, load('aff_login.html'), AF)['status'] == 'login_required'

def test_aff_empty_page_is_unknown_not_deleted():
    assert aff.parse(200, AF, load('aff_empty.html'), AF)['status'] == 'unknown'

# ---- _http 小工具 ----
def test_html_helpers():
    h = load('lofter_ok.html')
    assert _http.title_of(h) == '測試文章 - 測試博客'
    assert _http.meta(h, 'og:site_name') == '測試博客'
    assert '內文' in _http.text_of(h) and '<' not in _http.text_of(h)
    assert _http.ld_json(load('postype_ok.html'))[0]['@type'] == 'BlogPosting'
