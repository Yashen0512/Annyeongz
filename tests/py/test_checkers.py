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

# 系列頁(/series/):裁自 No.1000(空系列)、No.1009(正常系列)、No.1020(正常單篇)的實際頁面
SER = 'https://www.postype.com/@03ppiyak04/series/1197108'
def test_postype_is_series_url():
    assert postype.is_series_url(SER) and not postype.is_series_url(PT)

def test_postype_empty_series_is_deleted_even_with_200():
    r = postype.parse(200, SER, load('postype_series_empty.html'), SER)
    assert r['status'] == 'deleted' and r['reason'] == 'series_empty' and r['author_name'] is None

def test_postype_live_series_is_ok_with_nickname():
    live = 'https://www.postype.com/@parkpro/series/1176394'
    r = postype.parse(200, live, load('postype_series_live.html'), live)
    assert r['status'] == 'ok' and r['reason'] == 'series_10' and r['author_name'] == '박프로'

def test_postype_series_without_count_is_unknown():
    assert postype.parse(200, SER, load('postype_ok.html'), SER)['reason'] == 'series_no_count'
    assert postype.parse(404, SER, '', SER)['status'] == 'deleted'
    assert postype.parse(200, 'https://www.postype.com/@03ppiyak04', '', SER)['reason'] == 'redirect_home'

def test_postype_series_count():
    assert postype.series_count('<p>총 0화</p>') == 0 and postype.series_count('<p>총 12화</p>') == 12
    assert postype.series_count('<p>nothing</p>') is None

def test_postype_live_post_fixture_from_no1020():
    live = 'https://www.postype.com/@mil-ky/post/11607115'
    r = postype.parse(200, live, load('postype_post_live.html'), live)
    assert r['status'] == 'ok' and r['author_name'] == '우유' and r['author_url'] == 'https://www.postype.com/profile/@tvyw3c'

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
    assert lofter.parse(200, LF, load('lofter_404.html'), LF)['status'] == 'deleted'     # 實測 404 頁字樣(軟 404)
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
    for name in ('cf_challenge.html', 'ao3_down.html'):        # Cloudflare 挑戰頁、2026-11 全站停機頁(418)都只是 unknown
        r = ao3.parse(418, A3, load(name), A3)
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

# ---- Lofter 博客名來源與合集頁(2026-11-05 實測誤判) ----
def test_lofter_blog_name_prefers_header_over_title_dash():
    # <title>「【安员】雨季 - 上-一只大鹅」:舊版先切「 - 」得到「上-一只大鹅」
    html = load('lofter_post_header.html')
    assert lofter.blog_name(html, 'testblog.lofter.com') == ('一只大鹅', 'header_title')
    r = lofter.parse(200, LF, html, LF)
    assert r['status'] == 'ok' and r['author_name'] == '一只大鹅' and r['author_source'] == 'header_title'
    # 沒有 header 連結時:<title> 取最後一個連字號之後(不再優先切「 - 」)
    no_head = html.replace('<h1><a href="//testblog.lofter.com/">一只大鹅</a></h1>', '')
    assert lofter.blog_name(no_head, 'testblog.lofter.com') == ('一只大鹅', 'title')
    assert lofter.header_names(html, 'testblog.lofter.com') == ['一只大鹅']        # 頭像(無文字)、首页、归档 都略過
    assert lofter.header_names(html, 'www.lofter.com') == []
    assert lofter.title_suffix('雨季 - 上-一只大鹅') == '一只大鹅' and lofter.title_suffix('沒有連字號') == ''

def test_lofter_post_with_notfound_title_is_ok():
    """2026-11-06 誤判:No.1347 篇名《페이지를 찾을 수 없습니다(找不到頁面)》、內文又寫了 404 / 页面不存在,但它是 HTTP 200 的正常文章。"""
    html = load('lofter_post_notfound_title.html')
    assert lofter.has_post(html, 'testblog.lofter.com') and not lofter.is_error_page(html, 'testblog.lofter.com')
    r = lofter.parse(200, LF, html, LF)
    assert r['status'] == 'ok' and r['reason'] == '200' and r['author_name'] == '測試博客'
    # 篇名就叫「404 Not Found」的正常文章也一樣 ok(有文章結構就不看標題)
    t404 = html.replace('페이지를 찾을 수 없습니다(找不到頁面)-測試博客', '404 Not Found-測試博客')
    assert lofter.parse(200, LF, t404, LF)['status'] == 'ok'
    # 同樣的內文字樣、但沒有任何文章結構(只剩錯誤模板)→ 才是 gone_text
    bare = '<html><head><title>LOFTER</title></head><body><p>哎呀，页面走丢了...</p><p>页面不存在</p></body></html>'
    assert not lofter.has_post(bare, 'testblog.lofter.com') and lofter.is_error_page(bare, 'testblog.lofter.com')
    assert lofter.parse(200, LF, bare, LF)['reason'] == 'gone_text'

def test_lofter_error_page_structure():
    """錯誤頁的判定看結構:<title> 整個是「404 Not Found」(真 404 頁)、或沒有文章結構且內文有 GONE_TEXT;現有兩個錯誤頁樣本都要認得。"""
    for f in ('lofter_404.html', 'lofter_gone.html'):
        assert lofter.is_error_page(load(f), 'testblog.lofter.com') and not lofter.has_post(load(f), 'testblog.lofter.com'), f
    assert lofter.ERROR_TITLE_RE.match('404 Not Found') and not lofter.ERROR_TITLE_RE.match('404 Not Found-測試博客')
    # 現有的正常樣本都有文章結構;只剩標題、沒有關鍵字的頁面不是錯誤頁(維持 ok)
    for f in ('lofter_ok.html', 'lofter_post_js.html', 'lofter_post_header.html'):
        assert lofter.has_post(load(f), 'testblog.lofter.com'), f
    assert not lofter.is_error_page('<html><head><title>某主題</title></head><body><p>內文</p></body></html>', 'testblog.lofter.com')
    # header 有博客名、<title> 是「文章標題-博客名」也算文章結構;只有博客名(首頁)不算
    hdr = '<html><head><title>文章-某博客</title></head><body><a href="//testblog.lofter.com/">某博客</a></body></html>'
    assert lofter.has_post(hdr, 'testblog.lofter.com')
    assert not lofter.has_post(hdr.replace('<title>文章-某博客</title>', '<title>某博客</title>'), 'testblog.lofter.com')

def test_lofter_collection_rules():
    C = 'https://www.lofter.com/front/blog/collection/share?collectionId=22232844&incantation=hjTWr10sOl21'
    assert lofter.is_collection(C) and not lofter.is_collection(LF)
    r = lofter.parse(404, C, '', C)
    assert r['status'] == 'unknown' and r['reason'] == 'collection_404'           # 404 狀態碼不算已刪
    r = lofter.parse(200, C, load('lofter_collection_ok.html'), C)
    assert r['status'] == 'ok' and r['reason'] == 'collection' and r['author_name'] is None
    r = lofter.parse(404, C, load('lofter_collection_gone.html'), C)
    assert r['status'] == 'deleted' and r['reason'] == 'collection_gone'
    assert lofter.parse(200, 'https://www.lofter.com/front/login', '', C)['status'] == 'login_required'
