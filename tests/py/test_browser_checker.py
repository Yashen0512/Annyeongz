# -*- coding: utf-8 -*-
"""browser_checker.py(check_links.py --browser):判斷純函式 classify()、AO3 章節進度、cookie 匯出檔解析與到期判斷、WARP 偵測、
   --probe 的樣本挑選、挑戰頁連續計數與登入牆短路(用假的 session,不開瀏覽器)、preflight 的各種略過原因、與 check_links 的接線。
   HTML 樣本是依各平台已知行為自己寫的合成片段(tests/fixtures/html/),尚未在真瀏覽器實測;規則修正時請一併更新樣本。"""
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
    for code in (200, 403, 503, 418):
        r = BC.classify(plat, url, code, load('cf_challenge.html'), url=url)
        assert r['status'] == 'unknown' and r['reason'] == 'cf_challenge' and r['challenge'] and r['blocked']
    assert BC.classify('aff', AF, 403, load('aff_cf.html'), url=AF)['challenge']
    assert not BC.classify('aff', AF, 200, load('aff_ok.html'), url=AF).get('challenge')

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
    assert CL.main(['--browser', '--probe', '--src', str(b), '--platforms', 'lofter,ao3,aff', '--no', '1,2']) is None
    assert sorted(os.listdir(str(b))) == ['article_links.json'] and fake.closed
    assert {p for p, _ in fake.calls} == {'lofter', 'ao3', 'aff'} and len(fake.calls) == 3 + 2 + 2
