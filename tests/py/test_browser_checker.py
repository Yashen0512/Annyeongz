# -*- coding: utf-8 -*-
"""browser_checker.py(check_links.py --browser):判斷純函式 classify()、AO3 章節進度、cookie 匯出檔解析與到期判斷、WARP 偵測、
   --probe 的樣本挑選、挑戰頁連續計數與登入牆短路(用假的 session,不開瀏覽器)、preflight 的各種略過原因、與 check_links 的接線。
   HTML 樣本是合成片段(tests/fixtures/html/):lofter_404 / aff_cf_zh / ao3_down 依 2026-11-04 站長本機 --probe 的真實字樣寫成,
   其餘依已知行為自己寫;規則修正時請一併更新樣本。"""
import io, json, os, threading
from datetime import datetime, timedelta
import pytest
from conftest import ROOT
import browser_checker as BC
import check_links as CL

HTML = os.path.join(ROOT, 'tests', 'fixtures', 'html')
COOK = os.path.join(ROOT, 'tests', 'fixtures', 'cookies')
def load(name):
    return io.open(os.path.join(HTML, name), encoding='utf-8').read()

LF = 'https://testblog.lofter.com/post/1a2b3c4d_5e6f7a8b9'
A3 = 'https://archiveofourown.org/works/123'
AF = 'https://www.asianfanfics.com/story/view/123/test'
LOGIN = 'https://www.lofter.com/front/login?from=xxx'

# ---- Lofter ----
def test_lofter_login_wall_with_cookie_is_login_required_blocked():
    r = BC.classify('lofter', LOGIN, 200, load('lofter_login.html'), url=LF)
    assert r['status'] == 'login_required' and r['reason'] == 'login_wall' and r['blocked'] and not r.get('challenge')

def test_lofter_404_and_gone_text_are_deleted():
    assert BC.classify('lofter', LF, 404, load('lofter_404.html'), url=LF)['reason'] == '404'
    # 2026-11-04 實測的 404 頁:標題 404 Not Found、「哎呀，页面走丢了...」;就算拿掉標題與 404 字樣也認得出
    soft = '<html><head><title>LOFTER</title></head><body><p>哎呀，页面走丢了...</p><p>你查找的链接可能已损毁，或页面已被移除。</p></body></html>'
    r = BC.classify('lofter', LF, 200, soft, url=LF)
    assert r['status'] == 'deleted' and r['reason'] == 'gone_text'
    r = BC.classify('lofter', LF, 200, load('lofter_404.html'), url=LF)        # 軟 404(200 但頁面說不存在)
    assert r['status'] == 'deleted' and r['reason'] == 'gone_text'
    assert BC.classify('lofter', LF, 200, load('lofter_gone.html'), url=LF)['status'] == 'deleted'

def test_lofter_blog_gone():
    r = BC.classify('lofter', LF, 200, load('lofter_blog_gone.html'), url=LF)
    assert r['status'] == 'deleted' and r['reason'] == 'blog_gone'
    r = BC.classify('lofter', LF, None, '', url=LF, error='net::ERR_NAME_NOT_RESOLVED')   # 子網域打不開
    assert r['status'] == 'deleted' and r['reason'] == 'blog_gone' and r['detail'] == 'net::ERR_NAME_NOT_RESOLVED'
    r = BC.classify('lofter', LF, None, '', url=LF, error='network')                    # 自己的網路斷了(session 已核對 www 連不上)
    assert r['status'] == 'unknown' and r['reason'] == 'nav_error'

def test_lofter_blog_root():
    root = 'https://testblog.lofter.com/'
    assert BC.classify('lofter', root, 404, load('lofter_404.html'), url=root)['reason'] == 'blog_gone'   # 查的是首頁本身(作者庫網址)
    assert BC.classify('lofter', LF, 404, load('lofter_404.html'), url=LF)['reason'] == '404'
    assert BC.blog_root_gone(404, '') and BC.blog_root_gone(None, '', 'net::ERR_CONNECTION_REFUSED')
    assert BC.blog_root_gone(200, load('lofter_blog_gone.html')) and not BC.blog_root_gone(200, load('lofter_ok.html'))
    assert not BC.blog_root_gone(None, '', 'network') and not BC.blog_root_gone(None, '', 'timeout')

def test_check_marks_blog_gone_when_root_also_gone(monkeypatch):
    """某篇 404 → 再看首頁:首頁也 404 → reason 變 blog_gone;首頁正常 → 維持 404。fetch 用假的,不開瀏覽器。"""
    pages = {LF: (404, LF, load('lofter_404.html'), ''), 'https://testblog.lofter.com/': (404, 'https://testblog.lofter.com/', '', '')}
    s = BC.BrowserSession(sleep=lambda x: None, log=lambda *a: None)
    monkeypatch.setattr(s, 'fetch', lambda plat, url, page=None: pages[url])
    r = s.check('lofter', LF)
    assert r['status'] == 'deleted' and r['reason'] == 'blog_gone' and r['detail'] == 'post:404'
    pages['https://testblog.lofter.com/'] = (200, 'https://testblog.lofter.com/', load('lofter_ok.html'), '')
    s2 = BC.BrowserSession(sleep=lambda x: None, log=lambda *a: None)
    monkeypatch.setattr(s2, 'fetch', lambda plat, url, page=None: pages[url])
    assert s2.check('lofter', LF)['reason'] == '404'
    assert s2.check('lofter', LF)['reason'] == '404'            # 同 host 的首頁只查一次(快取)

def test_lofter_ok_post_with_cookie():
    r = BC.classify('lofter', LF, 200, load('lofter_post_js.html'), url=LF)
    assert r['status'] == 'ok' and r['author_name'] == '測試博客' and r['author_url'] == 'testblog.lofter.com'
    assert BC.classify('lofter', LF, 200, load('lofter_ok.html'), url=LF)['status'] == 'ok'

def test_lofter_redirect_home_and_timeout():
    assert BC.classify('lofter', 'https://testblog.lofter.com/', 200, load('lofter_ok.html'), url=LF)['reason'] == 'redirect_home'
    r = BC.classify('lofter', LF, None, '', url=LF, error='timeout')
    assert r['status'] == 'unknown' and r['reason'] == 'timeout'
    assert BC.classify('lofter', LF, 200, '<html><body></body></html>', url=LF)['reason'] == 'empty'

# ---- AO3 ----
def test_ao3_ok_with_chapter_progress_in_extra():
    r = BC.classify('ao3', A3 + '?view_adult=true', 200, load('ao3_chapters.html'), url=A3)
    assert r['status'] == 'ok' and r['author_name'] == 'testpseud'
    ex = r['extra']
    assert ex['chapters'] == '5/10' and ex['chapter_current'] == 5 and ex['chapter_total'] == 10
    assert ex['complete'] is False and ex['status'] == 'updated' and ex['status_date'] == '2025-03-02' and ex['words'] == 12345

def test_ao3_complete_and_open_ended():
    ex = BC.classify('ao3', A3, 200, load('ao3_complete.html'), url=A3)['extra']
    assert ex['chapters'] == '3/3' and ex['complete'] is True and ex['status'] == 'completed' and ex['status_date'] == '2024-06-06'
    ex = BC.classify('ao3', A3, 200, load('ao3_open_ended.html'), url=A3)['extra']
    assert ex['chapters'] == '2/?' and ex['chapter_total'] is None and ex['complete'] is False and 'words' not in ex
    assert BC.ao3_progress(load('aff_ok.html')) is None
    assert BC.ao3_progress('<p>Chapters: 7/?</p>')['chapters'] == '7/?'     # 純文字的退路

def test_ao3_single_chapter_work_has_no_extra_when_no_stats():
    r = BC.classify('ao3', A3, 200, load('ao3_ok.html'), url=A3)
    assert r['status'] == 'ok' and r.get('extra') is None

def test_ao3_404_and_registered_only():
    assert BC.classify('ao3', A3, 404, load('ao3_404.html'), url=A3) == dict(BC.classify('ao3', A3, 404, load('ao3_404.html'), url=A3), status='deleted')
    assert BC.classify('ao3', A3, 200, load('ao3_404.html'), url=A3)['reason'] == 'gone_text'
    r = BC.classify('ao3', A3, 200, load('ao3_login.html'), url=A3)
    assert r['status'] == 'login_required' and r['reason'] == 'login_only' and not r.get('blocked')
    assert BC.classify('ao3', A3, 200, load('ao3_adult.html'), url=A3)['status'] == 'ok'

# ---- Asianfanfics ----
def test_aff_subscribers_only_is_ok():
    r = BC.classify('aff', AF, 200, load('aff_subscribers.html'), url=AF)
    assert r['status'] == 'ok' and r['reason'] == 'subscribers_only' and r['author_name'] == 'testwriter'
    assert BC.classify('aff', AF, 200, load('aff_login.html'), url=AF)['status'] == 'ok'      # 舊樣本的「subscribers only」也算 ok

def test_aff_404_and_ok():
    assert BC.classify('aff', AF, 404, load('aff_404.html'), url=AF)['reason'] == '404'
    r = BC.classify('aff', AF, 200, load('aff_404.html'), url=AF)
    assert r['status'] == 'deleted' and r['reason'] == 'gone_text'
    assert BC.classify('aff', AF, 200, load('aff_ok.html'), url=AF)['reason'] == 'author_link'
    assert BC.classify('aff', AF, 200, load('aff_empty.html'), url=AF)['status'] == 'unknown'
    assert BC.classify('aff', 'https://www.asianfanfics.com/', 200, load('aff_empty.html'), url=AF)['reason'] == 'redirect_home'

# ---- Cloudflare ----
@pytest.mark.parametrize('plat,url', [('ao3', A3), ('aff', AF), ('lofter', LF)])
def test_cloudflare_challenge_is_unknown_and_flagged(plat, url):
    for code in (200, 403, 503):
        r = BC.classify(plat, url, code, load('cf_challenge.html'), url=url)
        assert r['status'] == 'unknown' and r['reason'] == 'cf_challenge' and r['challenge'] and r['blocked'] and not r.get('down')
    assert BC.classify('aff', AF, 403, load('aff_cf.html'), url=AF)['challenge']
    assert not BC.classify('aff', AF, 200, load('aff_ok.html'), url=AF).get('challenge')

def test_cloudflare_challenge_traditional_chinese_aff_403():
    """2026-11-04 實測:AFF 第二筆起回 403 繁中版驗證頁(<title>請稍候...、正在執行安全驗證、Ray ID、Performance and Security by Cloudflare),
    以前只看英文字樣所以判成 http_403、3 秒就放棄。"""
    for name in ('aff_cf_zh.html', 'aff_cf_min.html'):
        for code in (403, 200, 503):
            r = BC.classify('aff', AF, code, load(name), url=AF)
            assert r['status'] == 'unknown' and r['reason'] == 'cf_challenge' and r['challenge'] and r['blocked'], (name, code)
    assert BC.classify('aff', AF, 403, '<html><head><title>請稍候...</title></head><body></body></html>', url=AF)['challenge']   # 標題就夠
    assert BC.classify('aff', AF, 403, '<html><head><title>请稍候...</title></head><body></body></html>', url=AF)['challenge']   # 簡體版
    for k in ('Ray ID: <code>abc</code>', 'Performance and Security by Cloudflare', 'Enable JavaScript and cookies to continue', '正在執行安全驗證'):
        assert BC.is_cf_challenge(403, '<html><head><title>x</title></head><body>%s</body></html>' % k), k

def test_cloudflare_detection_uses_content_not_status():
    assert not BC.is_cf_challenge(403, load('aff_ok.html')) and not BC.is_cf_challenge(418, load('ao3_ok.html'))
    assert not BC.is_cf_challenge(200, load('lofter_post_js.html')) and not BC.is_cf_challenge(200, load('lofter_404.html'))
    # 內文剛好出現「請稍候」(文章內容)不算:這個字樣只看 <title>
    post = load('lofter_post_js.html').replace('</body>', '<p>請稍候，下一章明天更新。</p></body>')
    assert not BC.is_cf_challenge(200, post) and BC.classify('lofter', LF, 200, post, url=LF)['status'] == 'ok'
    assert BC.classify('aff', AF, 403, load('aff_empty.html'), url=AF)['reason'] == 'http_403'      # 真的只是 403、不是挑戰頁才算 http_403

def test_gap_for_platform():
    assert BC.gap_for('aff') == (6.0, 10.0) and BC.gap_for('aff')[0] > BC.GAP[1]     # AFF 連續請求第二筆就被擋,間隔拉長
    assert BC.gap_for('lofter') == BC.GAP and BC.gap_for('ao3') == BC.GAP

# ---- AO3 停機(2026-11 資安事件,全站 418) ----
def test_ao3_down_is_unknown_and_down_not_challenge():
    for code in (418, 200, 503, None):
        r = BC.classify('ao3', A3 + '?view_adult=true', code, load('ao3_down.html'), url=A3)
        assert r['status'] == 'unknown' and r['reason'] == 'ao3_down' and r['blocked'] and r['down'] and not r.get('challenge'), code
    assert BC.classify('ao3', A3, 418, '', url=A3)['reason'] == 'ao3_down'                                   # 418 本身就算
    assert BC.classify('ao3', A3, 200, '<html><head><title>Request temporarily denied. | Archive of Our Own</title></head><body></body></html>', url=A3)['reason'] == 'ao3_down'
    assert BC.classify('ao3', A3, 200, '<html><head><title>AO3</title></head><body><p>The archive is down for maintenance.</p></body></html>', url=A3)['reason'] == 'ao3_down'
    assert BC.is_ao3_down(418, '') and BC.is_ao3_down(200, load('ao3_down.html')) and not BC.is_ao3_down(200, load('ao3_ok.html'))
    # 只有 AO3 這樣判:AFF 的 418 + 挑戰頁仍是 cf_challenge,AFF 一般 418 是 http_418
    assert BC.classify('aff', AF, 418, load('cf_challenge.html'), url=AF)['reason'] == 'cf_challenge'
    assert BC.classify('aff', AF, 418, load('aff_empty.html'), url=AF)['reason'] == 'http_418'
    assert BC.classify('ao3', A3, 200, load('ao3_ok.html'), url=A3)['status'] == 'ok'                     # 正常頁不受影響

# ---- 同頁等 Cloudflare 驗證跑完 ----
class FakePage:
    """假的 Playwright page:steps 是每次 poll 後的 (title, url, html);用完就停在最後一個。"""
    def __init__(self, steps, url):
        self.steps, self.url, self._title, self._html, self.i = list(steps), url, '', '', 0
        self.main_frame = object()
        self.waited = 0
    def _advance(self):
        if self.i < len(self.steps):
            self._title, self.url, self._html = self.steps[self.i]
            self.i += 1
    def title(self):
        self._advance()
        return self._title
    def wait_for_load_state(self, state, timeout=0):
        self.waited += 1
    def content(self):
        return self._html

def _cf_session(monkeypatch, page, first):
    slept = []
    s = BC.BrowserSession(sleep=slept.append, log=lambda *a: None)
    monkeypatch.setattr(s, 'fetch', lambda plat, url, page=None: first)
    monkeypatch.setattr(s, 'page_for', lambda plat: page)
    return s, slept

def test_wait_challenge_resolves_when_title_changes(monkeypatch):
    cf = load('aff_cf_zh.html')
    ok = load('aff_subscribers.html')
    page = FakePage([('請稍候...', AF, cf), ('請稍候...', AF, cf), ('Test Story - Asianfanfics', AF, ok)], AF)
    s, slept = _cf_session(monkeypatch, page, (403, AF, cf, ''))
    s._status[id(page)] = 200                                   # 驗證完 Cloudflare 自動重載,response 事件記到的狀態碼
    r = s.check('aff', AF)
    assert r['status'] == 'ok' and r['reason'] == 'subscribers_only' and r['code'] == 200 and not r.get('challenge')
    assert slept == [BC.CF_POLL_S] * 3 and page.waited == 1 and s.last[2] == ok

def test_wait_challenge_keeps_waiting_through_intermediate_page(monkeypatch):
    """「驗證成功。正在等待回應」標題變了但還是挑戰頁 → 繼續等,直到真的換頁。"""
    cf, mid, ok = load('aff_cf_zh.html'), load('aff_cf_min.html').replace('請稍候...', '驗證成功'), load('aff_ok.html')
    page = FakePage([('驗證成功', AF, mid), ('驗證成功', AF, mid), ('Test Story - Asianfanfics', AF, ok)], AF)
    s, slept = _cf_session(monkeypatch, page, (403, AF, cf, ''))
    r = s.check('aff', AF)
    assert r['status'] == 'ok' and r['reason'] == 'author_link' and r['code'] is None and len(slept) == 3

def test_wait_challenge_gives_up_after_cf_solve_seconds(monkeypatch):
    cf = load('aff_cf_zh.html')
    page = FakePage([('請稍候...', AF, cf)], AF)
    s, slept = _cf_session(monkeypatch, page, (403, AF, cf, ''))
    r = s.check('aff', AF)
    assert r['status'] == 'unknown' and r['reason'] == 'cf_challenge_wait' and r['challenge'] and r['blocked']
    assert len(slept) == int(BC.CF_SOLVE_S / BC.CF_POLL_S) and sum(slept) == pytest.approx(BC.CF_SOLVE_S)   # 最多等 20 秒

def test_check_does_not_wait_for_ao3_down(monkeypatch):
    page = FakePage([], A3)
    s, slept = _cf_session(monkeypatch, page, (418, A3 + '?view_adult=true', load('ao3_down.html'), ''))
    r = s.check('ao3', A3)
    assert r['reason'] == 'ao3_down' and r['down'] and slept == []

# ---- cookie ----
def test_load_cookies_get_cookies_txt_locally_json():
    cs = BC.load_cookies(os.path.join(COOK, 'lofter_getcookies.json'))
    sess = next(c for c in cs if c['name'] == 'LOFTER_SESS')
    assert sess == {'name': 'LOFTER_SESS', 'value': 'sess-value', 'domain': '.lofter.com', 'path': '/', 'httpOnly': True,
                    'secure': False, 'expires': 1767225600.123}            # sameSite unspecified → 不給
    pp = next(c for c in cs if c['name'] == 'NTES_PASSPORT')
    assert pp['sameSite'] == 'None' and pp['secure'] is True
    js = next(c for c in cs if c['name'] == 'JSESSIONID')
    assert 'expires' not in js and js['sameSite'] == 'Lax'                  # session cookie 沒有到期日

def test_load_cookies_cookie_editor_json_and_netscape():
    cs = BC.load_cookies(os.path.join(COOK, 'lofter_cookie_editor.json'))
    sess = next(c for c in cs if c['name'] == 'LOFTER_SESS')
    assert sess['sameSite'] == 'Lax' and sess['expires'] == 1767225600       # no_restriction 但不 secure → 降成 Lax
    assert 'sameSite' not in next(c for c in cs if c['name'] == 'usertrack')
    cs = BC.load_cookies(os.path.join(COOK, 'lofter_netscape.txt'))
    sess = next(c for c in cs if c['name'] == 'LOFTER_SESS')
    assert sess['httpOnly'] is True and sess['expires'] == 1767225600 and sess['domain'] == '.lofter.com'

def test_load_cookies_wrapped_and_bad(tmp_path):
    p = tmp_path / 'c.json'
    p.write_text(json.dumps({'cookies': [{'name': 'a', 'value': '1', 'domain': '.lofter.com'}]}), encoding='utf-8')
    assert BC.load_cookies(str(p))[0]['path'] == '/'
    p.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError):
        BC.load_cookies(str(p))
    p.write_text('"nope"', encoding='utf-8')
    with pytest.raises(ValueError):
        BC.load_cookies(str(p))

def test_cookie_status():
    exp = datetime(2026, 1, 1, 8, 0, tzinfo=BC.TZ)       # 1767225600 = 2026-01-01 00:00 UTC
    cs = BC.load_cookies(os.path.join(COOK, 'lofter_getcookies.json'))
    assert BC.cookie_expiry(cs) == exp.replace(microsecond=123000)
    assert BC.cookie_status(cs, now=exp - timedelta(days=10))[0] == 'ok'
    st, e, left = BC.cookie_status(cs, now=exp - timedelta(days=2))
    assert st == 'expiring' and 1.9 < left < 2.1
    assert BC.cookie_status(cs, now=exp + timedelta(hours=1))[0] == 'expired'
    assert BC.COOKIE_WARN_DAYS == 3
    assert BC.cookie_status(cs, now=exp - timedelta(days=3, hours=1))[0] == 'ok'          # 剩 3 天多:還不警告
    assert BC.cookie_status(cs, now=exp - timedelta(days=2, hours=23))[0] == 'expiring'   # 剩不到 3 天:開始警告
    # 2026-11-04 實測:LOFTER_SESS 到期 2026-11-16 17:29 → 11/04 正常、11/13 傍晚起每天警告
    real = [{'name': 'LOFTER_SESS', 'expires': datetime(2026, 11, 16, 17, 29, tzinfo=BC.TZ).timestamp()}]
    assert BC.cookie_status(real, now=datetime(2026, 11, 4, 12, 0, tzinfo=BC.TZ))[0] == 'ok'
    assert BC.cookie_status(real, now=datetime(2026, 11, 13, 18, 0, tzinfo=BC.TZ))[0] == 'expiring'
    assert BC.cookie_status(real, now=datetime(2026, 11, 16, 18, 0, tzinfo=BC.TZ))[0] == 'expired'
    assert BC.cookie_status([{'name': 'other', 'expires': 1.0}], now=exp)[0] == 'missing'
    assert BC.cookie_status([{'name': 'LOFTER_SESS'}], now=exp)[0] == 'no_expiry'

def test_is_warp():
    assert BC.is_warp('fl=1\nip=1.2.3.4\nwarp=on\ngateway=off\n')
    assert BC.is_warp('warp=plus\n')
    assert not BC.is_warp('warp=off\n') and not BC.is_warp('') and not BC.is_warp('xwarp=on')

# ---- --probe 樣本 ----
def targets():
    ref = lambda marked: {'kind': 'article', 'no': '1', 'title': 'T', 'label': '❌ x' if marked else 'x', 'marked': marked}
    return [{'url': 'https://a.lofter.com/post/1_2', 'platform': 'lofter', 'refs': [ref(False)]},
            {'url': 'https://b.lofter.com/post/3_4', 'platform': 'lofter', 'refs': [ref(True)]},
            {'url': 'https://c.lofter.com/', 'platform': 'lofter', 'refs': [{'kind': 'author', 'pid': 'p', 'name': 'n', 'key': 'Lofter'}]},
            {'url': 'https://archiveofourown.org/works/5', 'platform': 'ao3', 'refs': [ref(False)]},
            {'url': 'https://www.asianfanfics.com/story/view/7/x', 'platform': 'aff', 'refs': [ref(True)]}]

def test_pick_probe_samples():
    s = BC.pick_probe_samples(targets(), {}, 'lofter')
    assert [u for _, u in s] == ['https://a.lofter.com/post/1_2', 'https://b.lofter.com/post/3_4',
                                 'https://a.lofter.com/post/1a2b3c4d_fffffffffff', 'https://annyeongz-no-such-blog-0512.lofter.com/']
    s = BC.pick_probe_samples(targets(), {'https://b.lofter.com/post/3_4': {'status': 'ok'}}, 'lofter')
    assert s[0][1] == 'https://b.lofter.com/post/3_4'                       # link_status 曾是 ok 的優先
    s = BC.pick_probe_samples(targets(), {}, 'ao3')
    assert len(s) == 2 and s[1][1] == 'https://archiveofourown.org/works/999999999999'
    s = BC.pick_probe_samples(targets(), {}, 'aff')
    assert [l for l, _ in s][0].startswith('已知 ❌') and s[1][1].startswith('https://www.asianfanfics.com/story/view/9999999999/')
    assert BC.pick_probe_samples([], {}, 'aff') == []

# ---- run_platform / run_all / probe(假 session) ----
class FakeSession:
    def __init__(self, script):
        self.script, self.calls, self.last, self.closed = script, [], None, False
        self.sleep = lambda s: None
    def start(self):
        return self
    def close(self):
        self.closed = True
    def check(self, plat, url):
        self.calls.append((plat, url))
        res = self.script(plat, url)
        self.last = (res.get('code'), res.get('final', url), '<html><title>t</title><body>text</body></html>', '')
        return res

CF = lambda: {'status': 'unknown', 'author_name': None, 'reason': 'cf_challenge', 'code': 403, 'blocked': True, 'challenge': True}
OK = lambda: {'status': 'ok', 'author_name': 'a', 'reason': 'author_link', 'code': 200}
WALL = lambda: {'status': 'login_required', 'author_name': None, 'reason': 'login_wall', 'code': 200, 'blocked': True}
def tg(plat, n):
    return [{'url': 'https://x/%s/%d' % (plat, i), 'platform': plat, 'refs': []} for i in range(n)]

def test_run_platform_skips_after_five_consecutive_challenges():
    s = FakeSession(lambda p, u: CF())
    st = BC.run_platform('aff', tg('aff', 12), s, {}, threading.Lock(), log=lambda *a: None, sleep=lambda x: None)
    assert st == {'checked': 5, 'blocked': True, 'skipped': 7, 'challenges': 5, 'note': 'Cloudflare 挑戰頁連續 5 筆'}

def test_run_platform_challenge_streak_resets_on_success():
    seq = iter([CF(), CF(), CF(), CF(), OK(), CF(), CF(), OK()])
    s = FakeSession(lambda p, u: next(seq))
    st = BC.run_platform('ao3', tg('ao3', 8), s, {}, threading.Lock(), log=lambda *a: None, sleep=lambda x: None)
    assert st['checked'] == 8 and st['blocked'] is False and st['challenges'] == 6

DOWN = lambda: {'status': 'unknown', 'author_name': None, 'reason': 'ao3_down', 'code': 418, 'blocked': True, 'down': True}
def test_run_platform_ao3_down_skips_whole_platform_at_first_hit():
    lines, results = [], {}
    s = FakeSession(lambda p, u: DOWN())
    st = BC.run_platform('ao3', tg('ao3', 7), s, results, threading.Lock(), log=lines.append, sleep=lambda x: None)
    assert st == {'checked': 1, 'blocked': True, 'skipped': 6, 'challenges': 0, 'note': 'AO3 停機中'}
    assert len(s.calls) == 1 and any('AO3 停機中，略過' in l for l in lines)
    assert results['https://x/ao3/0']['status'] == 'unknown'          # 走 advance 只會記 unknown,不改任何計數
    e = CL.advance({'status': 'ok', 'streak': 3, 'counted': '2026-11-03', 'last': '2026-11-03'}, DOWN(), '2026-11-04')
    assert e['status'] == 'ok' and e['streak'] == 3 and e['reason'] == 'ao3_down' and e['last'] == '2026-11-04' and not e.get('dead')

def test_run_platform_lofter_login_wall_stops_platform():
    seq = iter([OK(), WALL(), OK()])
    s, results = FakeSession(lambda p, u: next(seq)), {}
    st = BC.run_platform('lofter', tg('lofter', 3), s, results, threading.Lock(), log=lambda *a: None, sleep=lambda x: None)
    assert st['checked'] == 2 and st['blocked'] and st['skipped'] == 1 and '登入牆' in st['note']
    assert results['https://x/lofter/1']['status'] == 'login_required'      # 不算死,走 advance 只會記 login_required

def test_run_all_uses_one_session_and_skips_unusable():
    pre = {'usable': ['ao3'], 'notes': {'lofter': '沒有 cookies/lofter.json,略過'}, 'cookies': {}}
    by = {'lofter': tg('lofter', 4), 'ao3': tg('ao3', 2), 'aff': []}
    s, results = FakeSession(lambda p, u: OK()), {}
    stats = BC.run_all(pre, by, ['lofter', 'ao3', 'aff'], results, threading.Lock(), log=lambda *a: None, session=s)
    assert stats['lofter'] == BC.skip_stat(4, '沒有 cookies/lofter.json,略過')
    assert stats['ao3']['checked'] == 2 and stats['aff'] == BC.skip_stat(0, '略過')   # 不在 usable 又沒 note → 一樣是略過
    assert len(results) == 2 and s.closed is False                           # 外部給的 session 不由 run_all 關

def test_run_all_skip_stat_for_platform_without_note():
    pre = {'usable': [], 'notes': {}, 'cookies': {}}
    stats = BC.run_all(pre, {'aff': tg('aff', 1)}, ['aff'], {}, threading.Lock(), log=lambda *a: None)
    assert stats['aff']['skipped'] == 1 and stats['aff']['blocked']

def test_probe_prints_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lines = []
    s = FakeSession(lambda p, u: dict(OK(), extra={'chapters': '1/1'}) if p == 'ao3' else OK())
    pre = {'usable': ['ao3', 'aff'], 'notes': {'lofter': 'WARP 開啟,略過'}, 'cookies': {}}
    BC.probe(targets(), {}, ['lofter', 'ao3', 'aff'], pre, log=lines.append, session=s)
    out = '\n'.join(lines)
    assert '[lofter] 略過:WARP 開啟,略過' in out and '===== ao3' in out and '===== aff' in out
    assert 'extra={"chapters": "1/1"}' in out and '頁面文字:t text' in out and '判定:ok(author_link)' in out
    assert len(s.calls) == 4 and os.listdir(tmp_path) == []

def test_probe_stops_ao3_after_down(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    lines = []
    s = FakeSession(lambda p, u: DOWN() if p == 'ao3' else OK())
    pre = {'usable': ['ao3', 'aff'], 'notes': {}, 'cookies': {}}
    BC.probe(targets(), {}, ['ao3', 'aff'], pre, log=lines.append, session=s)
    out = '\n'.join(lines)
    assert '判定:unknown(ao3_down)' in out and 'AO3 停機中，略過' in out
    assert [p for p, _ in s.calls] == ['ao3', 'aff', 'aff'] and os.listdir(tmp_path) == []

# ---- preflight ----
def test_preflight_without_playwright(monkeypatch, tmp_path):
    monkeypatch.setattr(BC, 'is_available', lambda: False)
    lines = []
    pre = BC.preflight(str(tmp_path), ['lofter', 'ao3', 'aff'], log=lines.append, trace='')
    assert pre['usable'] == [] and set(pre['notes']) == {'lofter', 'ao3', 'aff'} and 'pip install playwright' in lines[0]

def test_preflight_warp_on(monkeypatch, tmp_path):
    monkeypatch.setattr(BC, 'is_available', lambda: True)
    lines = []
    pre = BC.preflight(str(tmp_path), ['ao3'], log=lines.append, trace='warp=on\n')
    assert pre['warp'] and pre['usable'] == [] and 'WARP' in lines[0]

def test_preflight_lofter_cookie_cases(monkeypatch, tmp_path):
    monkeypatch.setattr(BC, 'is_available', lambda: True)
    lines = []
    pre = BC.preflight(str(tmp_path), ['lofter', 'ao3', 'aff'], log=lines.append, trace='warp=off\n')
    assert pre['usable'] == ['ao3', 'aff'] and 'lofter.json' in pre['notes']['lofter']
    (tmp_path / 'cookies').mkdir()
    dst = tmp_path / 'cookies' / 'lofter.json'
    dst.write_bytes(io.open(os.path.join(COOK, 'lofter_getcookies.json'), 'rb').read())
    exp = datetime(2026, 1, 1, 8, 0, tzinfo=BC.TZ)
    lines.clear()
    pre = BC.preflight(str(tmp_path), ['lofter'], log=lines.append, trace='', now=exp - timedelta(days=1))
    assert pre['usable'] == ['lofter'] and len(pre['cookies']['lofter']) == 3 and any('🚨' in l and '2026-01-01' in l for l in lines)
    lines.clear()
    pre = BC.preflight(str(tmp_path), ['lofter'], log=lines.append, trace='', now=exp - timedelta(days=12))
    assert pre['usable'] == ['lofter'] and not any('🚨' in l for l in lines) and any('剩 12.0 天' in l and '剩不到 3 天' in l for l in lines)
    pre = BC.preflight(str(tmp_path), ['lofter'], log=lines.append, trace='', now=exp + timedelta(days=1))
    assert pre['usable'] == [] and '過期' in pre['notes']['lofter']
    dst.write_text('not json at all', encoding='utf-8')
    pre = BC.preflight(str(tmp_path), ['lofter'], log=lines.append, trace='', now=exp)
    assert pre['usable'] == [] and 'cookie 檔讀不了' in pre['notes']['lofter']

# ---- 與 check_links 的接線 ----
def test_advance_keeps_extra():
    e = CL.advance(None, dict(OK(), extra={'chapters': '5/10', 'complete': False}), '2026-11-04')
    assert e['extra'] == {'chapters': '5/10', 'complete': False} and e['status'] == 'ok'
    e = CL.advance(e, {'status': 'unknown', 'author_name': None, 'reason': 'timeout', 'code': None}, '2026-11-05')
    assert e['extra']['chapters'] == '5/10'

def test_probe_requires_browser_flag():
    with pytest.raises(SystemExit):
        CL.main(['--probe'])

def _build_dir(tmp_path):
    """最小的 _build:article_links.json + 上一層的 data.json(用 30 篇 fixture),給 main() 跑。"""
    b = tmp_path / '_build'; b.mkdir()
    compact = io.open(os.path.join(ROOT, 'tests', 'fixtures', 'compact_30.json'), encoding='utf-8').read()
    (tmp_path / 'data.json').write_text(compact, encoding='utf-8')
    links = {'1': {'A': [['Lofter-原文', LF], ['AO3', A3]]}, '2': {'B': [['❌ AF', AF], ['PT', 'https://www.postype.com/@b/post/1']]},
             '__edited__': {}, '__blocks__': {}}
    (b / 'article_links.json').write_text(json.dumps(links, ensure_ascii=False), encoding='utf-8')
    return b

def test_main_browser_without_playwright_skips_three_platforms(tmp_path, monkeypatch):
    b = _build_dir(tmp_path)
    monkeypatch.setattr(BC, 'is_available', lambda: False)
    rep = CL.main(['--browser', '--src', str(b), '--platforms', 'lofter,ao3,aff', '--no', '1,2'])   # --no:不含作者頁
    assert rep['counts'] == {} and all(rep['platforms'][p]['skipped'] == 1 and rep['platforms'][p].get('note') for p in ('lofter', 'ao3', 'aff'))
    st = json.load(io.open(str(b / 'link_status.json'), encoding='utf-8'))
    assert set(st) == {'__meta__'}                                           # 沒查任何連結,什麼都不記
    assert '未安裝 Playwright' in CL.report_markdown(rep)

def test_main_browser_runs_fake_session_through_advance(tmp_path, monkeypatch):
    b = _build_dir(tmp_path)
    monkeypatch.setattr(BC, 'preflight', lambda src, plats, **k: {'available': True, 'warp': False, 'usable': list(plats), 'notes': {}, 'cookies': {}})
    def script(p, u):
        return {'lofter': OK(), 'ao3': dict(OK(), extra={'chapters': '2/2', 'complete': True}),
                'aff': {'status': 'deleted', 'author_name': None, 'reason': '404', 'code': 404}}[p]
    monkeypatch.setattr(BC, 'BrowserSession', lambda **k: FakeSession(script))
    monkeypatch.setattr(BC, 'GAP', (0, 0))
    monkeypatch.setattr(BC, 'GAP_PLAT', {})
    rep = CL.main(['--browser', '--src', str(b), '--platforms', 'lofter,ao3,aff', '--no', '1,2'])
    assert rep['counts'] == {'ok': 2, 'deleted': 1}
    st = json.load(io.open(str(b / 'link_status.json'), encoding='utf-8'))
    assert st[A3]['extra'] == {'chapters': '2/2', 'complete': True} and st[A3]['platform'] == 'ao3'
    assert st[AF]['status'] == 'deleted' and st[AF]['streak'] == 1 and not st[AF].get('dead')   # 第一天,還不算死
    assert rep['new_dead'] == []

def test_main_probe_writes_nothing(tmp_path, monkeypatch):
    b = _build_dir(tmp_path)
    monkeypatch.setattr(BC, 'preflight', lambda src, plats, **k: {'available': True, 'warp': False, 'usable': list(plats), 'notes': {}, 'cookies': {}})
    fake = FakeSession(lambda p, u: OK())
    monkeypatch.setattr(BC, 'BrowserSession', lambda **k: fake)
    monkeypatch.setattr(BC, 'GAP', (0, 0))
    monkeypatch.setattr(BC, 'GAP_PLAT', {})
    assert CL.main(['--browser', '--probe', '--src', str(b), '--platforms', 'lofter,ao3,aff', '--no', '1,2']) is None
    assert sorted(os.listdir(str(b))) == ['article_links.json'] and fake.closed
    assert {p for p, _ in fake.calls} == {'lofter', 'ao3', 'aff'} and len(fake.calls) == 3 + 2 + 2

# ---- AFF 404 頁(2026-11-05 站長用平常的 Chrome 實看) ----
def test_aff_real_404_page_is_deleted():
    r = BC.classify('aff', AF, 404, load('aff_404.html'), url=AF)
    assert r['status'] == 'deleted' and r['reason'] == '404'
    r = BC.classify('aff', AF, 200, load('aff_404.html'), url=AF)                  # 軟 404 也認得(樣本頁首有 Members only,不能判成 ok)
    assert r['status'] == 'deleted' and r['reason'] == 'gone_text'
    curly = '<html><head><title>Asianfanfics</title></head><body><p>The page you were looking for doesn\u2019t exist or has moved.</p></body></html>'
    assert BC.classify('aff', AF, 200, curly, url=AF)['status'] == 'deleted'      # 彎引號
    from checkers import aff
    assert aff.parse(404, AF, load('aff_404.html'), AF)['status'] == 'deleted'
    assert aff.parse(200, AF, curly, AF)['status'] == 'deleted'

# ---- 固定設定檔 / 反偵測 ----
def test_launch_kwargs_stealth_and_no_user_agent():
    kw = BC.launch_kwargs(True)
    assert kw == {'headless': True, 'args': ['--disable-blink-features=AutomationControlled'], 'ignore_default_args': ['--enable-automation']}
    assert BC.launch_kwargs(False, 'chrome', 'C:/x/chrome.exe')['executable_path'] == 'C:/x/chrome.exe'
    kw = BC.profile_launch_kwargs({})
    assert kw['headless'] is False and kw['channel'] == 'chrome' and 'user_agent' not in kw     # 預設有頭、系統 Chrome、不改 UA
    assert '--disable-blink-features=AutomationControlled' in kw['args'] and kw['locale'] == 'zh-TW'
    assert BC.profile_launch_kwargs({'headless': True, 'channel': 'msedge'})['channel'] == 'msedge'
    assert 'webdriver' in BC.STEALTH_JS and 'undefined' in BC.STEALTH_JS

def test_profile_config(tmp_path):
    assert BC.profile_config(str(tmp_path), ()) is None and BC.profile_config(str(tmp_path), ['postype']) is None
    c = BC.profile_config(str(tmp_path))
    assert c == {'dir': os.path.join(str(tmp_path), 'browser_profile'), 'platforms': ('aff',), 'headless': False,
                 'channel': 'chrome', 'exists': False}
    (tmp_path / 'browser_profile').mkdir()
    assert not BC.profile_exists(str(tmp_path))                                    # 空資料夾不算
    (tmp_path / 'browser_profile' / 'Local State').write_text('{}', encoding='utf-8')
    assert BC.profile_config(str(tmp_path), ['aff', 'lofter'])['exists'] and BC.profile_config(str(tmp_path), ['aff', 'lofter'])['platforms'] == ('aff', 'lofter')

def test_preflight_profile_defaults_to_aff_and_warns_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(BC, 'is_available', lambda: True)
    lines = []
    pre = BC.preflight(str(tmp_path), ['ao3', 'aff'], log=lines.append, trace='')
    assert pre['profile']['platforms'] == ('aff',) and pre['usable'] == ['ao3', 'aff']
    assert any('還沒有固定設定檔' in l and '--setup-profile' in l for l in lines)
    (tmp_path / 'browser_profile').mkdir(); (tmp_path / 'browser_profile' / 'Local State').write_text('{}', encoding='utf-8')
    lines.clear()
    pre = BC.preflight(str(tmp_path), ['aff'], log=lines.append, trace='')
    assert any('使用固定設定檔' in l and '有頭' in l for l in lines)
    lines.clear()
    pre = BC.preflight(str(tmp_path), ['aff'], log=lines.append, trace='', profile_platforms=())       # --no-profile
    assert pre['profile'] is None and lines == []
    pre = BC.preflight(str(tmp_path), ['ao3'], log=lines.append, trace='')                            # 這次沒跑 AFF → 不用設定檔
    assert pre['profile'] is None
    pre = BC.preflight(str(tmp_path), ['aff'], log=lines.append, trace='', profile_headless=True, profile_channel='msedge')
    assert pre['profile']['headless'] and pre['profile']['channel'] == 'msedge'

class _PWPage:
    def __init__(self):
        self.handlers = []
    def evaluate(self, js):
        return 'Mozilla/5.0 HeadlessChrome/143.0'
    def on(self, ev, fn):
        self.handlers.append(ev)

class _PWCtx:
    def __init__(self, kw, pages=0):
        self.kw, self.scripts, self.cookies_added, self.closed = kw, [], [], 0
        self.pages = [_PWPage() for _ in range(pages)]
    def new_page(self):
        p = _PWPage(); self.pages.append(p); return p
    def add_init_script(self, js):
        self.scripts.append(js)
    def add_cookies(self, cs):
        self.cookies_added += cs
    def cookies(self, url=None):
        return [{'name': 'cf_clearance'}, {'name': 'aff_session'}]
    def close(self):
        self.closed += 1

class _PWBrowser:
    version = '143.0'
    class browser_type:
        name = 'chromium'
    def __init__(self, kw):
        self.kw, self.contexts, self.closed = kw, [], 0
    def new_context(self, **kw):
        c = _PWCtx(kw); self.contexts.append(c); return c
    def close(self):
        self.closed += 1

class _PWChromium:
    def __init__(self):
        self.launched, self.persistent = [], []
    def launch(self, **kw):
        b = _PWBrowser(kw); self.launched.append(b); return b
    def launch_persistent_context(self, d, **kw):
        c = _PWCtx(dict(kw, user_data_dir=d), pages=1); self.persistent.append(c); return c

class _PW:
    def __init__(self):
        self.chromium, self.stopped = _PWChromium(), 0
    def start(self):
        return self
    def stop(self):
        self.stopped += 1
    def __enter__(self):
        return self
    def __exit__(self, *a):
        self.stopped += 1

def test_session_uses_persistent_profile_for_aff_only(tmp_path):
    pw, lines = _PW(), []
    prof = BC.profile_config(str(tmp_path))
    s = BC.BrowserSession(cookies={'lofter': [{'name': 'LOFTER_SESS', 'value': 'v', 'domain': '.lofter.com', 'path': '/'}]},
                          log=lines.append, profile=prof, playwright_factory=lambda: pw).start()
    assert pw.chromium.launched == [] and pw.chromium.persistent == []             # 第一次用到才開
    s.prepare('aff')
    pc = pw.chromium.persistent[0]
    assert pc.kw['user_data_dir'] == prof['dir'] and os.path.isdir(prof['dir'])
    assert pc.kw['headless'] is False and pc.kw['channel'] == 'chrome' and 'user_agent' not in pc.kw
    assert '--enable-automation' in pc.kw['ignore_default_args'] and pc.scripts == [BC.STEALTH_JS]
    assert s.page_for('aff') is pc.pages[0] and pw.chromium.launched == []        # 用 persistent context 原本那一頁
    assert any('固定設定檔' in l and '有頭' in l for l in lines)
    s.prepare('lofter')                                                            # 一般平台:無頭 Chromium、UA 換掉 HeadlessChrome、帶 cookie
    b = pw.chromium.launched[0]
    ctx = b.contexts[-1]
    assert b.kw['headless'] is True and '--disable-blink-features=AutomationControlled' in b.kw['args']
    assert ctx.kw['user_agent'] == 'Mozilla/5.0 Chrome/143.0' and ctx.scripts == [BC.STEALTH_JS] and ctx.cookies_added[0]['name'] == 'LOFTER_SESS'
    assert s.uses_profile('aff') and not s.uses_profile('lofter')
    s.close()
    assert pc.closed == 1 and b.closed == 1 and pw.stopped == 1

def test_session_without_profile_runs_aff_in_normal_browser(tmp_path):
    pw = _PW()
    s = BC.BrowserSession(log=lambda *a: None, playwright_factory=lambda: pw).start()
    s.prepare('aff')
    assert pw.chromium.persistent == [] and len(pw.chromium.launched) == 1 and not s.uses_profile('aff')

def test_run_platform_profile_hint_once_and_in_note():
    class ProfSession(FakeSession):
        def uses_profile(self, plat):
            return plat == 'aff'
    lines = []
    st = BC.run_platform('aff', tg('aff', 6), ProfSession(lambda p, u: dict(CF(), reason='cf_challenge_wait')), {}, threading.Lock(),
                         log=lines.append, sleep=lambda x: None)
    hint = 'AFF 被 Cloudflare 擋，請重跑 --setup-profile 或手動檢查'
    assert sum(hint in l and '不改計數' in l for l in lines) == 1                  # 第一筆就提示,只提示一次
    assert st['checked'] == 5 and st['blocked'] and hint in st['note'] and any(hint in l and '略過' in l for l in lines)
    lines.clear()
    BC.run_platform('aff', tg('aff', 2), FakeSession(lambda p, u: CF()), {}, threading.Lock(), log=lines.append, sleep=lambda x: None)
    assert not any('setup-profile' in l for l in lines)                           # 沒用設定檔就不提示

def test_run_all_skips_platform_when_browser_cannot_open():
    class Broken(FakeSession):
        def uses_profile(self, plat):
            return True
        def prepare(self, plat):
            raise RuntimeError('Chromium distribution \'chrome\' is not found\nline2')
    lines, s = [], Broken(lambda p, u: OK())
    pre = {'usable': ['aff'], 'notes': {}, 'cookies': {}}
    stats = BC.run_all(pre, {'aff': tg('aff', 3)}, ['aff'], {}, threading.Lock(), log=lines.append, session=s)
    assert stats['aff'] == BC.skip_stat(3, '瀏覽器開不起來') and s.calls == []
    assert any('is not found' in l for l in lines) and any('--setup-profile 的視窗關掉' in l for l in lines)

def test_probe_prints_profile_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    class ProfSession(FakeSession):
        def uses_profile(self, plat):
            return True
    lines = []
    s = ProfSession(lambda p, u: dict(CF(), reason='cf_challenge_wait'))
    BC.probe(targets(), {}, ['aff'], {'usable': ['aff'], 'notes': {}, 'cookies': {}}, log=lines.append, session=s)
    out = '\n'.join(lines)
    assert '===== aff(2 筆,固定設定檔)=====' in out and out.count('請重跑 --setup-profile') == 2

def test_setup_profile_opens_aff_home_and_waits_for_enter(tmp_path):
    pw, lines, asked = _PW(), [], []
    class Page(_PWPage):
        def goto(self, url, **kw):
            asked.append(('goto', url))
    def factory():
        orig = pw.chromium.launch_persistent_context
        def lpc(d, **kw):
            c = orig(d, **kw); c.pages = [Page()]; return c
        pw.chromium.launch_persistent_context = lpc
        return pw
    ok = BC.setup_profile(str(tmp_path), log=lines.append, input_fn=lambda msg: asked.append(('input', msg)), playwright_factory=factory)
    pc = pw.chromium.persistent[0]
    assert ok and asked[0] == ('goto', BC.AFF_HOME) and asked[1][0] == 'input' and 'Enter' in asked[1][1]
    assert pc.kw['headless'] is False and pc.kw['channel'] == 'chrome' and 'user_agent' not in pc.kw and pc.scripts == [BC.STEALTH_JS]
    assert pc.kw['user_data_dir'] == os.path.join(str(tmp_path), 'browser_profile') and pc.closed == 1
    assert any('cf_clearance:✅' in l for l in lines) and any('登入 AFF' in l for l in lines)

def test_setup_profile_launch_failure(tmp_path):
    pw, lines = _PW(), []
    def boom(d, **kw):
        raise RuntimeError('user data directory is already in use')
    pw.chromium.launch_persistent_context = boom
    assert BC.setup_profile(str(tmp_path), log=lines.append, input_fn=lambda m: None, playwright_factory=lambda: pw) is False
    assert any('already in use' in l for l in lines) and any('關掉' in l for l in lines)

def test_setup_profile_without_playwright(monkeypatch, tmp_path):
    monkeypatch.setattr(BC, 'is_available', lambda: False)
    lines = []
    assert BC.setup_profile(str(tmp_path), log=lines.append) is False and 'pip install playwright' in lines[0]

def test_main_setup_profile_needs_no_article_links(tmp_path, monkeypatch):
    called = {}
    monkeypatch.setattr(BC, 'setup_profile', lambda src, channel='': called.update(src=src, channel=channel) or True)
    assert CL.main(['--setup-profile', '--src', str(tmp_path), '--browser-channel', 'msedge']) is None
    assert called == {'src': str(tmp_path), 'channel': 'msedge'} and os.listdir(str(tmp_path)) == []
    monkeypatch.setattr(BC, 'setup_profile', lambda src, channel='': False)
    with pytest.raises(SystemExit):
        CL.main(['--setup-profile', '--src', str(tmp_path)])

@pytest.mark.parametrize('argv,expect', [([], (('aff',), False)), (['--no-profile'], ((), False)),
                                         (['--profile', 'aff,lofter', '--profile-headless'], (('aff', 'lofter'), True))])
def test_main_passes_profile_options_to_preflight(tmp_path, monkeypatch, argv, expect):
    b = _build_dir(tmp_path)
    got = {}
    def fake_pre(src, plats, **k):
        got.update(k)
        return {'available': True, 'warp': False, 'usable': [], 'notes': {p: 'x' for p in plats}, 'cookies': {}, 'profile': None}
    monkeypatch.setattr(BC, 'preflight', fake_pre)
    CL.main(['--browser', '--src', str(b), '--platforms', 'aff', '--no', '1,2'] + argv)
    assert (got['profile_platforms'], got['profile_headless']) == expect

def test_gitignore_has_browser_profile():
    gi = io.open(os.path.join(ROOT, '.gitignore'), encoding='utf-8').read().split()
    assert '_build/browser_profile/' in gi and '_build/cookies/' in gi

# ---- 2026-11-05:--no-sandbox 只在 Linux、Lofter 博客名來源、合集頁 ----
def test_no_sandbox_only_on_linux():
    assert BC.needs_no_sandbox('linux') and not BC.needs_no_sandbox('win32') and not BC.needs_no_sandbox('darwin')
    assert BC.launch_kwargs(False, 'chrome', os_name='win32')['chromium_sandbox'] is True        # Windows 不加 --no-sandbox
    assert 'chromium_sandbox' not in BC.launch_kwargs(True, os_name='linux')                    # Linux 容器維持 Playwright 預設
    assert BC.profile_launch_kwargs({}, os_name='win32')['chromium_sandbox'] is True
    assert 'chromium_sandbox' not in BC.profile_launch_kwargs({}, os_name='linux')

LC = 'https://www.lofter.com/front/blog/collection/share?collectionId=22388853&incantation=hjAYkBwHkDb7'
def test_lofter_collection_in_browser():
    r = BC.classify('lofter', LC, 404, '<html><head><title>LOFTER</title></head><body><div id="app"></div></body></html>', url=LC)
    assert r['status'] == 'unknown' and r['reason'] == 'collection_404'
    r = BC.classify('lofter', LC, 200, load('lofter_collection_ok.html'), url=LC)
    assert r['status'] == 'ok' and r['author_name'] is None
    assert BC.classify('lofter', LC, 200, load('lofter_collection_gone.html'), url=LC)['reason'] == 'collection_gone'
    assert BC.classify('lofter', 'https://www.lofter.com/front/login', 200, load('lofter_login.html'), url=LC)['status'] == 'login_required'

def test_lofter_author_from_header_in_browser():
    r = BC.classify('lofter', LF, 200, load('lofter_post_header.html'), url=LF)
    assert r['status'] == 'ok' and r['author_name'] == '一只大鹅' and r['author_source'] == 'header_title'

def test_check_uses_blog_home_name_when_no_header(monkeypatch):
    """文章頁沒有 header 博客名(只能從 <title> 猜)→ 改抓部落格首頁的名字,同一個 host 只抓一次。"""
    post = '<html><head><title>雨季 - 上-一只大鹅</title></head><body><p>內文</p></body></html>'
    home = '<html><head><title>一只大鹅</title></head><body><p>首頁</p></body></html>'
    LF2 = LF.replace('5e6f7a8b9', '000000000')
    calls = []
    def fetch(plat, url, page=None):
        calls.append(url)
        return (200, url, home if url == 'https://testblog.lofter.com/' else post, '')
    s = BC.BrowserSession(sleep=lambda x: None, log=lambda *a: None)
    monkeypatch.setattr(s, 'fetch', fetch)
    r = s.check('lofter', LF)
    assert r['author_name'] == '一只大鹅' and r['author_source'] == 'blog_home'
    assert s.check('lofter', LF2)['author_name'] == '一只大鹅'
    assert calls.count('https://testblog.lofter.com/') == 1
    # header 有名字就不多抓首頁
    calls.clear()
    s2 = BC.BrowserSession(sleep=lambda x: None, log=lambda *a: None)
    monkeypatch.setattr(s2, 'fetch', lambda plat, url, page=None: calls.append(url) or (200, url, load('lofter_post_header.html'), ''))
    assert s2.check('lofter', LF)['author_source'] == 'header_title' and calls == [LF]
    # 首頁抓不到 → 保留文章頁猜的名字
    s3 = BC.BrowserSession(sleep=lambda x: None, log=lambda *a: None)
    monkeypatch.setattr(s3, 'fetch', lambda plat, url, page=None: (None, url, '', 'timeout') if url.endswith('.com/') else (200, url, post, ''))
    r = s3.check('lofter', LF)
    assert r['author_name'] == '一只大鹅' and r['author_source'] == 'title'

def test_home_blog_name():
    assert BC.home_blog_name('<title>一只大鹅</title>', 'testblog.lofter.com') == '一只大鹅'
    assert BC.home_blog_name(load('lofter_post_header.html'), 'testblog.lofter.com') == '一只大鹅'

def test_probe_samples_include_lofter_collection():
    tgs = [{'url': LF, 'platform': 'lofter', 'refs': [{'kind': 'article', 'marked': False}]},
           {'url': LC, 'platform': 'lofter', 'refs': [{'kind': 'article', 'marked': False}]}]
    s = BC.pick_probe_samples(tgs, {}, 'lofter')
    assert s[-1] == ('合集分享頁(預期 ok;404 狀態碼只算 unknown)', LC)
