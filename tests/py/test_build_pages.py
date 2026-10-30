# -*- coding: utf-8 -*-
"""build_pages.py:分享頁 meta / 描述、標題折行、字型回退、sitemap / RSS,以及用 30 篇 fixture 跑完整產頁並驗證 hash 跳過重產。"""
import io, json, os, shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
import pytest
from conftest import ROOT, FIXTURE
import build_site as B
import build_pages as P

FACETS = [{'key': '文章類型', 'type': 'single'}, {'key': '結局', 'type': 'single'},
          {'key': 'CP配對', 'type': 'multi'}, {'key': '氛圍', 'type': 'multi'}, {'key': '題材梗', 'type': 'multi'}]

def art(**kw):
    a = {'no': '12', 'name': '戀戀遊戲機', 'author': 'littlecan', 'translator': '', 'alias': '', 'dead': False,
         'edited': '2026/6/26', 'ek': 202606262306, 'created': '2025/12/18', 'ck': 202512180002,
         'tags': {'文章類型': ['長篇'], '結局': ['HE'], 'CP配對': ['員/安'], '氛圍': ['甜文', '日常'], '題材梗': []}}
    a.update(kw)
    return a

# ---- 文字 ----
def test_top_tags_multi_first_then_single():
    assert P.top_tags(art(), FACETS) == ['員/安', '甜文', '日常']
    assert P.top_tags(art(tags={'文章類型': ['短篇'], '結局': [], 'CP配對': ['安/員'], '氛圍': [], '題材梗': []}), FACETS) == ['安/員', '短篇']

def test_title_and_description():
    assert P.page_title(art()) == '戀戀遊戲機 — littlecan | Annyeongz 平行宇宙'
    assert P.page_title(art(translator='了山')) == '戀戀遊戲機 — littlecan · 譯 了山 | Annyeongz 平行宇宙'
    assert P.page_title(art(author='')) == '戀戀遊戲機 | Annyeongz 平行宇宙'
    assert P.description(art(), FACETS) == '員/安 · 甜文 · 日常'
    assert P.description(art(alias='番外一《A》\n番外二《B》'), FACETS) == '番外一《A》、番外二《B》'
    assert P.description(art(dead=True), FACETS) == '(原文已刪)員/安 · 甜文 · 日常'
    assert P.description(art(alias='x' * 300), FACETS).endswith('…') and len(P.description(art(alias='x' * 300), FACETS)) == 160

def test_page_html_meta_and_redirect():
    h = P.page_html(art(name='A<B>&"C"', dead=True), FACETS)
    assert '<title>A&lt;B&gt;&amp;&quot;C&quot; — littlecan | Annyeongz 平行宇宙</title>' in h
    assert '<meta property="og:image" content="https://yashen0512.github.io/Annyeongz/p/12/og.png">' in h
    assert '<meta property="og:url" content="https://yashen0512.github.io/Annyeongz/p/12/">' in h
    assert '<meta name="twitter:card" content="summary_large_image">' in h
    assert 'content="(原文已刪)員/安 · 甜文 · 日常"' in h
    assert '<script>location.replace("../../?p=12");</script>' in h
    assert '作者:littlecan' in h and '標籤:員/安 · 甜文 · 日常 · 長篇 · HE' in h and '原文已刪' in h
    assert P.HASH_RE.search(h).group(1) == P.page_hash(art(name='A<B>&"C"', dead=True), FACETS)

def test_hash_changes_with_content_only():
    assert P.page_hash(art(), FACETS) == P.page_hash(art(), FACETS)
    assert P.page_hash(art(), FACETS) != P.page_hash(art(name='改名'), FACETS)
    assert P.og_hash(art(), FACETS) != P.og_hash(art(dead=True), FACETS)
    assert P.og_hash(art(), FACETS) == P.og_hash(art(alias='只影響分享頁,不影響圖'), FACETS)

def test_wrap_text_cjk_and_latin():
    width = lambda s: len(s) * 10
    assert P.wrap_text('一二三四五六七八', width, 40, 2) == (['一二三四', '五六七八'], False)
    assert P.wrap_text('一二三四五六七八九十', width, 40, 2) == (['一二三四', '五六七…'], True)
    assert P.wrap_text('hello world again', width, 110, 2) == (['hello world', 'again'], False)
    assert P.wrap_text('abc', width, 100, 2) == (['abc'], False)

def test_dates():
    assert P.iso_date('2026/6/26') == '2026-06-26'
    assert P.iso_date('') is None
    dt = P.key_to_dt(202606262306)
    assert (dt.year, dt.month, dt.day, dt.hour, dt.minute) == (2026, 6, 26, 23, 6) and dt.utcoffset() == timedelta(hours=8)
    assert P.key_to_dt(0) is None

# ---- 字型回退 ----
@pytest.fixture(scope='module')
def fonts():
    return P.Fonts()

def test_fonts_cover_hanzi_hangul_and_fallbacks(fonts):
    assert fonts.covers('TC', '戀') and not fonts.covers('TC', '재') and fonts.covers('KR', '재')
    assert fonts.clean('재수 없는 여자') == '재수 없는 여자'
    assert fonts.clean('专') == '專'            # TC 沒有的簡體字 → stmap 轉繁體
    assert fonts.clean('𝐋𝐎𝐕𝐄') == 'LOVE'       # 數學粗體 → NFKC
    assert fonts.clean('🚗轎車') == '轎車'      # emoji 沒字 → 略過
    fams = [seg for seg, _ in fonts.runs('안유진 x 張員瑛', 'b', 20)]
    assert fams == ['안유진', ' x 張員瑛']

# ---- 整個產頁:30 篇 fixture ----
@pytest.fixture(scope='module')
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp('site')
    DATA, _ = B.build_data(FIXTURE, now=datetime(2026, 10, 30, 14, 5, tzinfo=timezone(timedelta(hours=8))))
    src = tmp_path_factory.mktemp('build')
    shutil.copy(os.path.join(ROOT, '_build', 'site_template.html'), src / 'site_template.html')
    shutil.copy(os.path.join(ROOT, '_build', 'stmap.txt'), src / 'stmap.txt')
    B.write_site(DATA, str(src), str(out), repo_root=ROOT)
    st = P.build_pages(P.load_data(str(out)), str(out), images=True)
    return out, DATA, st

def test_build_pages_outputs(site):
    out, DATA, st = site
    assert st['pages'] == 30 and st['images'] == 30 and st['skipped'] == 0 and st['removed'] == 0 and st['bad_no'] == []
    assert sorted(st['feeds']) == ['feed-updated.xml', 'feed.xml', 'robots.txt', 'sitemap.xml']
    a = DATA['articles'][0]
    html = (out / 'p' / a['no'] / 'index.html').read_text(encoding='utf-8')
    assert '<meta property="og:title" content="' + P.page_title(a).replace('&', '&amp;').replace('"', '&quot;') in html
    from PIL import Image
    with Image.open(out / 'p' / a['no'] / 'og.png') as im:
        assert im.size == (1200, 630) and im.text['az-hash'] == P.og_hash(a, DATA['facets'])
    dead = [x for x in DATA['articles'] if x['dead']]
    assert dead and '(原文已刪)' in (out / 'p' / dead[0]['no'] / 'index.html').read_text(encoding='utf-8')

def test_build_pages_skips_unchanged_and_regenerates_changed(site):
    out, DATA, _ = site
    st = P.build_pages(P.load_data(str(out)), str(out), images=True)
    assert (st['pages'], st['images'], st['skipped'], st['feeds']) == (0, 0, 30, [])
    D2 = json.loads(json.dumps(DATA))
    D2['articles'][0]['name'] = D2['articles'][0]['name'] + '(改)'   # 改標題:頁與圖都要重產
    D2['articles'][1]['alias'] = '番外《新增》'                        # 只改收錄篇名:只有頁要重產
    st = P.build_pages(D2, str(out), images=True)
    assert (st['pages'], st['images'], st['skipped']) == (2, 1, 28)
    assert 'feed.xml' in st['feeds']
    st = P.build_pages(DATA, str(out), images=True)   # 改回來
    assert (st['pages'], st['images']) == (2, 1)

def test_build_pages_removes_stale_dirs_only_ours(site):
    out, DATA, _ = site
    (out / 'p' / '999999').mkdir()
    (out / 'p' / '999999' / 'index.html').write_text('<meta name="az-hash" content="%s">' % ('0' * 40), encoding='utf-8')
    (out / 'p' / 'keepme').mkdir()
    (out / 'p' / 'keepme' / 'index.html').write_text('<p>不是我們產的</p>', encoding='utf-8')
    st = P.build_pages(DATA, str(out), images=False)
    assert st['removed'] == 1 and not (out / 'p' / '999999').exists() and (out / 'p' / 'keepme').exists()
    shutil.rmtree(out / 'p' / 'keepme')

def test_sitemap_and_feeds_are_valid_xml(site):
    out, DATA, _ = site
    ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
    sm = ET.parse(out / 'sitemap.xml').getroot()
    locs = [u.find('s:loc', ns).text for u in sm.findall('s:url', ns)]
    assert locs[0] == 'https://yashen0512.github.io/Annyeongz/' and len(locs) == 31
    assert all(l.startswith('https://yashen0512.github.io/Annyeongz/p/') and l.endswith('/') for l in locs[1:])
    a = DATA['articles'][0]
    mods = {u.find('s:loc', ns).text: u.find('s:lastmod', ns).text for u in sm.findall('s:url', ns)}
    assert mods[P.share_url(a['no'])] == P.iso_date(a['edited'])
    for fn, key in (('feed.xml', 'ck'), ('feed-updated.xml', 'ek')):
        ch = ET.parse(out / fn).getroot().find('channel')
        items = ch.findall('item')
        assert 0 < len(items) <= 50
        first = max(DATA['articles'], key=lambda x: x[key])
        assert items[0].find('link').text == P.share_url(first['no'])
        assert items[0].find('title').text.startswith(first['name'])
        assert items[0].find('pubDate').text.endswith('+0800')
        assert items[0].find('description').text
        dates = [x[key] for x in DATA['articles']]
        assert ch.find('lastBuildDate').text == P.rss_xml.__globals__['format_datetime'](P.key_to_dt(max(dates)))
    assert (out / 'robots.txt').read_text(encoding='utf-8') == 'User-agent: *\nAllow: /\nSitemap: https://yashen0512.github.io/Annyeongz/sitemap.xml\n'

def test_load_data_parses_data_js(tmp_path):
    (tmp_path / 'data.js').write_text('window.DATA = {"total": 1, "articles": []};', encoding='utf-8')
    assert P.load_data(str(tmp_path)) == {'total': 1, 'articles': []}
