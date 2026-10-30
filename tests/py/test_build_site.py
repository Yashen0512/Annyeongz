# -*- coding: utf-8 -*-
"""build_site.py:dead 判定、作者拆分與 ID 保留、日期解析,以及用 30 篇 fixture 跑完整建置比對結果。"""
import io, json, os, shutil
from datetime import datetime, timezone, timedelta
import pytest
from conftest import ROOT, FIXTURE
import build_site as B

# ---- dead 判定 ----
def test_is_dead_manual_red():
    assert B.is_dead(True, [['PT', 'https://a']]) is True
    assert B.is_dead(True, []) is True

def test_is_dead_ratio_over_half():
    live, dead = ['PT', 'https://a'], ['LFT', 'https://b', 1]
    assert B.is_dead(False, [dead]) is True              # 1/1
    assert B.is_dead(False, [dead, live]) is False       # 1/2 不算「超過一半」
    assert B.is_dead(False, [dead, dead, live]) is True  # 2/3
    assert B.is_dead(False, [live, live]) is False
    assert B.is_dead(False, []) is False                 # 沒連結不算已刪

def test_is_dead_ignores_internal_links():
    internal = ['接續 前傳', 'annyeongz:549']
    assert B.is_dead(False, [['LFT', 'https://b', 1], internal]) is True    # 站內互連不計入分母
    assert B.is_dead(False, [internal]) is False

def test_split_links_marks_dead_by_x():
    out = B.split_links([['Postype-原文 ❌', 'https://p'], ['LFT', 'https://l'], ['❌', 'https://only']])
    assert out == [['Postype-原文', 'https://p', 1], ['LFT', 'https://l'], ['https://only', 'https://only', 1]]

def test_dead_conflict():
    assert B.dead_conflict(True, [['PT', 'https://a']]) is True
    assert B.dead_conflict(True, [['PT', 'https://a', 1]]) is False
    assert B.dead_conflict(False, [['PT', 'https://a']]) is False

# ---- 作者拆分與 ID ----
def test_author_parts_keeps_notion_ids():
    cell = 'ㅍ.,ㅍ (https://www.notion.so/1aaa7213548080cda25dd9e1edd5b7a4), 노네임(noname) (https://www.notion.so/2bbb72135480802f9fd3d8b0020af461)'
    assert B.author_parts(cell) == [('ㅍ.,ㅍ', '1aaa7213548080cda25dd9e1edd5b7a4'), ('노네임(noname)', '2bbb72135480802f9fd3d8b0020af461')]
    assert B.author_names(cell) == ['ㅍ.,ㅍ', '노네임(noname)']

def test_author_parts_without_urls_falls_back_to_comma():
    assert B.author_parts('甲, 乙') == [('甲', ''), ('乙', '')]
    assert B.author_parts('') == []

def test_author_parts_id_with_dashes_is_normalized():
    assert B.author_parts('甲 (https://www.notion.so/1aaa7213-5480-80cd-a25d-d9e1edd5b7a4)') == [('甲', '1aaa7213548080cda25dd9e1edd5b7a4')]

def test_split_author_translator():
    parts = [('作者', 'a' * 32), ('譯者一', 'b' * 32), ('譯者二', '')]
    assert B.split_author_translator(parts, True) == (['作者'], ['a' * 32], ['譯者一', '譯者二'], ['b' * 32, ''])
    assert B.split_author_translator(parts, False) == (['作者', '譯者一', '譯者二'], ['a' * 32, 'b' * 32, ''], [], [])
    assert B.split_author_translator(parts[:1], True) == (['作者'], ['a' * 32], [], [])   # 譯文但只有一人 → 都是作者

# ---- 日期 ----
def test_parse_dt():
    assert B.parse_dt('2025年6月3日 下午10:26') == ('2025/6/3', 202506032226)
    assert B.parse_dt('2025年6月3日 上午12:06') == ('2025/6/3', 202506030006)
    assert B.parse_dt('2025年6月3日 12:30') == ('2025/6/3', 202506031230)
    assert B.parse_dt('') == ('', 0)

def test_fmt_updated_and_synced():
    assert B.fmt_updated(202610292354) == '2026/10/29 11:54 PM'
    assert B.fmt_updated(0) == ''
    tz = timezone(timedelta(hours=8))
    assert B.fmt_synced(datetime(2026, 10, 30, 8, 36, tzinfo=tz)) == '2026/10/30 8:31 AM'    # 排程班次貼齊生日時間
    assert B.fmt_synced(datetime(2026, 10, 30, 14, 5, tzinfo=tz)) == '2026/10/30 2:05 PM'   # 手動建置顯示實際時間

# ---- 整個建置:fixture 重建出來的 30 篇要跟 data.js 原本一模一樣 ----
@pytest.fixture(scope='module')
def built():
    now = datetime(2026, 10, 30, 14, 5, tzinfo=timezone(timedelta(hours=8)))
    DATA, report = B.build_data(FIXTURE, now=now)
    expected = json.load(io.open(os.path.join(FIXTURE, 'expected.json'), encoding='utf-8'))
    return DATA, report, expected

def test_build_articles_roundtrip(built):
    DATA, report, expected = built
    assert DATA['total'] == 30
    got = {a['no']: a for a in DATA['articles']}
    for e in expected['articles']:
        assert got[e['no']] == e, '編號 %s 重建結果與 data.js 不同' % e['no']

def test_build_articles_sorted_by_no_desc(built):
    nos = [int(a['no']) for a in built[0]['articles']]
    assert nos == sorted(nos, reverse=True)

def test_build_people_keyed_by_notion_id(built):
    DATA, _, expected = built
    assert DATA['people'] == expected['people']
    for pid, p in DATA['people'].items():
        assert len(pid) == 32 and set(p) == {'name', 'urls', 'aliases', 'dead'} and p['aliases'] == []
    ids = [i for a in DATA['articles'] for i in a['author_ids'] + a['translator_ids']]
    assert ids and all(i in DATA['people'] for i in ids)
    assert DATA['dead_authors'] == [p['name'] for p in DATA['people'].values() if p['dead']]

def test_build_author_fields_are_parallel(built):
    for a in built[0]['articles']:
        assert len(a['author_ids']) == (len(a['author'].split('、')) if a['author'] else 0)
        assert len(a['translator_ids']) == (len(a['translator'].split('、')) if a['translator'] else 0)
    byno = {a['no']: a for a in built[0]['articles']}
    assert byno['233']['author'] == '' and byno['233']['author_ids'] == []
    assert '、' in byno['1270']['author'] and len(byno['1270']['author_ids']) == 2
    assert byno['10089']['translator'] and byno['10089']['translator_ids']

def test_build_misc(built):
    DATA, report, expected = built
    assert DATA['announcements'] == expected['announcements']
    assert DATA['updated'] == expected['updated']
    assert DATA['synced'] == '2026/10/30 2:05 PM'
    assert DATA['stats'] and DATA['stats']['total'] > 0
    assert [f['key'] for f in DATA['facets']][:4] == ['文章類型', '文章篇幅', '結局', '文章狀態']
    assert len(DATA['facets']) == 15
    assert report['dead_conflicts'] == []

def test_old_authors_csv_without_id_column_is_resolved(tmp_path):
    """舊版作者庫 CSV 沒有「頁面ID」欄 → 用主表作者欄的網址回填 ID。"""
    src = tmp_path / 'in'
    shutil.copytree(FIXTURE, src)
    p = src / '_authors' / 'authors_all.csv'
    rows = p.read_text(encoding='utf-8-sig').splitlines()
    rows = [','.join(r.split(',')[:-1]) for r in rows]   # 砍掉最後一欄(頁面ID)
    p.write_text('\n'.join(rows) + '\n', encoding='utf-8-sig')
    DATA, _ = B.build_data(str(src))
    expected = json.load(io.open(os.path.join(FIXTURE, 'expected.json'), encoding='utf-8'))
    assert DATA['people'] == expected['people']

def test_write_site_injects_data_and_copies_static(tmp_path):
    DATA, _ = B.build_data(FIXTURE)
    src = tmp_path / 'build'; src.mkdir()
    shutil.copy(os.path.join(ROOT, '_build', 'site_template.html'), src / 'site_template.html')
    shutil.copy(os.path.join(ROOT, '_build', 'stmap.txt'), src / 'stmap.txt')
    out = tmp_path / 'site'
    tpl, copied = B.write_site(DATA, str(src), str(out), repo_root=ROOT)
    html = (out / 'index.html').read_text(encoding='utf-8')
    assert '/*__DATA__*/' not in html and 'window.DATA = {' in html
    assert '__STMAP_T__' not in html and '__STMAP_S__' not in html
    assert '<script type="module" src="src/main.js"></script>' in html
    assert (out / 'data.js').read_text(encoding='utf-8').startswith('window.DATA = {')
    assert copied == ['src', 'styles', 'vendor', 'stats.html']
    assert (out / 'src' / 'main.js').exists() and (out / 'styles' / 'base.css').exists()
    assert (out / 'src' / 'stats.js').exists() and (out / 'styles' / 'stats.css').exists()   # 統計星圖的程式與樣式
    assert (out / 'vendor' / 'chart.umd.js').exists() and (out / 'stats.html').exists()
    assert (out / 'vendor' / 'lz-string.min.js').exists() and (out / 'vendor' / 'qrcode.js').exists()   # 書架匯出 / 匯入
    assert 'href="stats.html"' in html   # 首頁頁尾有「📊 統計星圖」連結
    assert B.self_check(html, {c: i for i, c in enumerate(['文章名稱', 'No', '上次編輯時間', '建立時間', '文章狀態', '文章篇幅', '文章類型', '結局', '紅標'] + list(B.F.FACETS) + B.F.EVENT_FACETS)}, str(out)) == []

def test_copy_static_is_noop_when_out_is_repo_root():
    assert B.copy_static(ROOT, ROOT) == []

def test_self_check_reports_missing_endpoint():
    warn = B.self_check('<html></html>', {}, '/nonexistent')
    assert any('REACT_API' in w for w in warn) and any('缺欄位' in w for w in warn) and any('src/' in w for w in warn)
    assert any('stats.html' in w for w in warn) and any('chart.umd.js' in w for w in warn)
    assert any('lz-string.min.js' in w for w in warn) and any('qrcode.js' in w for w in warn)

def test_number_report_detects_duplicates_and_gaps():
    arts = [{'no': '1', 'name': 'a'}, {'no': '1', 'name': 'b'}, {'no': '3', 'name': 'c'}, {'no': '10001', 'name': 'e'}]
    lines = '\n'.join(B.number_report(arts))
    assert 'No 1 重複 2 篇' in lines and '可回填空號(1 個):2' in lines and '一般文最大 3' in lines
