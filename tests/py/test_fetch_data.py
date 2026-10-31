# -*- coding: utf-8 -*-
"""fetch_data.py 的純函式:No 解析三種型別、日期格式、token 來源。import 不會碰網路(主流程在 main())。"""
import os
import fetch_data as FD

def test_read_no_number():
    assert FD.read_no({'properties': {'No': {'type': 'number', 'number': 1232}}}) == '1232'
    assert FD.read_no({'properties': {'No': {'type': 'number', 'number': 12.0}}}) == '12'
    assert FD.read_no({'properties': {'No': {'type': 'number', 'number': 12.5}}}) == '12.5'
    assert FD.read_no({'properties': {'No': {'type': 'number', 'number': None}}}) == ''

def test_read_no_unique_id():
    assert FD.read_no({'properties': {'No': {'type': 'unique_id', 'unique_id': {'prefix': 'AZ', 'number': 10089}}}}) == '10089'

def test_read_no_title_or_rich_text():
    assert FD.read_no({'properties': {'No': {'type': 'title', 'title': [{'plain_text': ' 77'}, {'plain_text': '7 '}]}}}) == '777'
    assert FD.read_no({'properties': {'No': {'type': 'rich_text', 'rich_text': [{'plain_text': '42'}]}}}) == '42'
    assert FD.read_no({'properties': {}}) == ''

def test_fmt_dt_taipei_12h():
    assert FD.fmt_dt('2026-06-23T16:06:00.000Z') == '2026年6月24日 上午12:06'   # UTC+8 跨日、12 時制
    assert FD.fmt_dt('2026-10-29T15:54:00.000Z') == '2026年10月29日 下午11:54'
    assert FD.fmt_dt('') == ''
    assert FD.fmt_date('2026-10-18') == '2026年10月18日'

def test_is_red():
    assert FD.is_red({'icon': {'type': 'icon', 'icon': {'color': 'red'}}}) is True
    assert FD.is_red({'icon': {'type': 'emoji', 'emoji': '🍍'}}) is False
    assert FD.is_red({}) is False

def test_resolve_token_prefers_env_then_file_then_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('NOTION_TOKEN', raising=False)
    assert FD.resolve_token() == ''                      # 都沒有 → 空字串(交給代理注入)
    (tmp_path / 'notion_token.txt').write_text('secret_file\n', encoding='utf-8')
    assert FD.resolve_token() == 'secret_file'
    monkeypatch.setenv('NOTION_TOKEN', 'secret_env')
    assert FD.resolve_token() == 'secret_env'

def test_block_links_returns_rich_text_index():
    blk = {'type': 'heading_2', 'heading_2': {'rich_text': [
        {'plain_text': 'Postype-原文', 'href': 'https://p/1'}, {'plain_text': '❌', 'href': None}, {'plain_text': 'LFT', 'href': 'https://l/1'}]}}
    assert FD.block_links(blk) == [['Postype-原文❌LFT', 'https://p/1', 0], ['Postype-原文❌LFT', 'https://l/1', 2]]
    bm = {'type': 'bookmark', 'bookmark': {'url': 'https://b/1', 'caption': []}}
    assert FD.block_links(bm) == [['https://b/1', 'https://b/1', -1]]
    assert FD.block_links({'type': 'divider', 'divider': {}}) == []

# ---- merge_links:增量重抓與清掉舊標題 / 舊編號 ----
def _page(no, title, pid, edited):
    return {'id': pid, 'last_edited_time': edited,
            'properties': {'No': {'type': 'number', 'number': no}, '文章名稱': {'type': 'title', 'title': [{'plain_text': title}]}}}
def _link_block(bid, text, url):
    return {'id': bid, 'type': 'paragraph', 'paragraph': {'rich_text': [{'plain_text': text, 'href': url}]}}

def test_merge_links_prunes_stale_title_after_renumber():
    # 2026-10-31 的情境:「Passionate A&W」那頁原本是 No.786,後來改號成 10047,786 給了新頁「설계실 로맨스」。
    # 舊版只會把新頁的連結塞進 links['786'],舊標題那組留著,巡檢就把 10047 的番外連結算在 786 頭上。
    links = {'786': {'Passionate A&W': [['Postype-番外1-原文', 'https://www.postype.com/@g/post/15413585']]},
             '__edited__': {'786': 'T0'},
             '__blocks__': {'786': {'page': 'PA', 'links': {'https://www.postype.com/@g/post/15413585': ['B1', 0]}}}}
    pages = [_page(10047, 'Passionate A&W', 'PA', 'T1'), _page(786, '설계실 로맨스', 'PB', 'T2')]
    children = {'PA': [_link_block('B1', 'Postype-番外1-原文', 'https://www.postype.com/@g/post/15413585')],
                'PB': [_link_block('B2', 'Postype-原文', 'https://www.postype.com/@n/post/6308988')]}
    calls = []
    def fetch(pid):
        calls.append(pid); return children[pid]
    out, new, refetched, pruned = FD.merge_links(links, pages, fetch)
    assert out['786'] == {'설계실 로맨스': [['Postype-原文', 'https://www.postype.com/@n/post/6308988']]}
    assert out['10047'] == {'Passionate A&W': [['Postype-番外1-原文', 'https://www.postype.com/@g/post/15413585']]}
    assert out['__blocks__']['786'] == {'page': 'PB', 'links': {'https://www.postype.com/@n/post/6308988': ['B2', 0]}}
    assert out['__blocks__']['10047']['page'] == 'PA' and out['__edited__'] == {'786': 'T2', '10047': 'T1'}
    assert (new, refetched, pruned) == (2, 0, 1) and calls == ['PA', 'PB']

def test_merge_links_skips_cached_refetches_edited_and_drops_removed_pages():
    links = {'1': {'A': [['PT', 'https://www.postype.com/@a/post/1']]},
             '2': {'B': [['PT', 'https://www.postype.com/@b/post/2']]},
             '3': {'C': [['PT', 'https://www.postype.com/@c/post/3']]},
             '__edited__': {'1': 'T1', '2': 'T2', '3': 'T3'},
             '__blocks__': {'1': {'page': 'P1', 'links': {}}, '2': {'page': 'P2', 'links': {}}, '3': {'page': 'P3', 'links': {}}}}
    pages = [_page(1, 'A', 'P1', 'T1'),            # 沒動 → 不抓
             _page(2, 'B', 'P2', 'T2b'),           # 頁面編輯過 → 重抓(標題沒變)
             _page(4, 'D', 'P4', 'T4'),            # 新 No
             _page(5, 'E', 'P5', 'T5'), _page(5, 'E2', 'P5b', 'T5')]   # 重複編號:兩頁都保留
    children = {'P2': [_link_block('B2', 'PT', 'https://www.postype.com/@b/post/2b')], 'P4': [], 'P5': [], 'P5b': []}
    out, new, refetched, pruned = FD.merge_links(links, pages, lambda pid: children[pid])
    assert out['1'] == {'A': [['PT', 'https://www.postype.com/@a/post/1']]}
    assert out['2'] == {'B': [['PT', 'https://www.postype.com/@b/post/2b']]}
    assert '3' not in out and '3' not in out['__edited__'] and '3' not in out['__blocks__']   # 主表已經沒有 No.3
    assert out['4'] == {'D': []} and set(out['5']) == {'E', 'E2'}
    assert (new, refetched, pruned) == (3, 1, 1)

def test_merge_links_renamed_title_keeps_only_new_title():
    links = {'9': {'舊標題': [['PT', 'https://www.postype.com/@a/post/9']]}, '__edited__': {'9': 'T0'},
             '__blocks__': {'9': {'page': 'P9', 'links': {}}}}
    out, new, refetched, pruned = FD.merge_links(links, [_page(9, '新標題', 'P9', 'T1')],
                                                 lambda pid: [_link_block('B9', 'PT', 'https://www.postype.com/@a/post/9')])
    assert out['9'] == {'新標題': [['PT', 'https://www.postype.com/@a/post/9']]} and pruned == 1

# ---- normalize_links:站內互連改寫、丟掉提及作者庫的假連結、同網址去重 ----
def test_normalize_links_drops_author_page_mentions():
    # 2026-10-31 的 No.909:段落「Postype-正文-原文 作者:@박프로」裡作者名是 @ 提及作者庫頁面,也帶 href,
    # block_links 把它記成第二條同名「連結」,網站就把每條閱讀連結顯示兩次。
    links = {'909': {'개강에 생일': [
                 ['Postype-正文-原文 作者:박프로', 'https://www.postype.com/@parkpro/post/16549828'],
                 ['Postype-正文-原文 作者:박프로', 'https://app.notion.com/p/179a721354808011b6c9d43af704a75a'],
                 ['❌Postype-番外-原文 作者:무', 'https://www.postype.com/@nothing-left09/post/15207213'],
                 ['❌Postype-番外-原文 作者:무', 'https://www.notion.so/17aa72135480809383c9de1555cc3d48']]},
             '__edited__': {'909': 'T'},
             '__blocks__': {'909': {'page': 'P909', 'links': {
                 'https://www.postype.com/@parkpro/post/16549828': ['B1', 0],
                 'https://app.notion.com/p/179a721354808011b6c9d43af704a75a': ['B1', 2],
                 'https://www.postype.com/@nothing-left09/post/15207213': ['B2', 1],
                 'https://www.notion.so/17aa72135480809383c9de1555cc3d48': ['B2', 3]}}}}
    out, rewritten, dropped, deduped = FD.normalize_links(links, {'P909': '909'})
    assert out['909'] == {'개강에 생일': [
        ['Postype-正文-原文 作者:박프로', 'https://www.postype.com/@parkpro/post/16549828'],
        ['❌Postype-番外-原文 作者:무', 'https://www.postype.com/@nothing-left09/post/15207213']]}
    assert set(out['__blocks__']['909']['links']) == {'https://www.postype.com/@parkpro/post/16549828',
                                                        'https://www.postype.com/@nothing-left09/post/15207213'}
    assert out['__edited__'] == {'909': 'T'} and (rewritten, dropped, deduped) == (0, 2, 0)

def test_normalize_links_rewrites_article_mentions_but_keeps_notion_site():
    pid = 'a' * 32
    links = {'1': {'A': [['前傳', 'https://www.notion.so/%s?pvs=4' % pid],
                         ['Notion 公開頁', 'https://someone.notion.site/fic-123'],
                         ['PT', 'https://www.postype.com/@a/post/1']]},
             '__blocks__': {'1': {'page': 'P1', 'links': {'https://www.notion.so/%s?pvs=4' % pid: ['B1', 0]}}}}
    out, rewritten, dropped, deduped = FD.normalize_links(links, {pid: '77'})
    assert out['1']['A'] == [['前傳', 'annyeongz:77'], ['Notion 公開頁', 'https://someone.notion.site/fic-123'],
                             ['PT', 'https://www.postype.com/@a/post/1']]
    assert out['__blocks__']['1']['links'] == {'https://www.notion.so/%s?pvs=4' % pid: ['B1', 0]}   # 改寫過的仍留 block 位置
    assert (rewritten, dropped, deduped) == (1, 0, 0)

def test_normalize_links_dedupes_same_url_keeping_dead_mark():
    links = {'5': {'E': [['PT', 'https://www.postype.com/@a/post/5'], ['PT ❌', 'https://www.postype.com/@a/post/5'],
                         ['LFT ❌', 'https://x.lofter.com/post/1'], ['LFT', 'https://x.lofter.com/post/1']]}}
    out, rewritten, dropped, deduped = FD.normalize_links(links, {})
    # 同網址只留一條(第一條的位置),名稱取有 ❌ 的那條
    assert out['5']['E'] == [['PT ❌', 'https://www.postype.com/@a/post/5'], ['LFT ❌', 'https://x.lofter.com/post/1']]
    assert (rewritten, dropped, deduped) == (0, 0, 2)
    assert '__blocks__' not in out   # 沒有 __blocks__ 也不會壞

def test_is_notion_url():
    assert FD.is_notion_url('https://app.notion.com/p/179a721354808011b6c9d43af704a75a')
    assert FD.is_notion_url('https://www.notion.so/abc')
    assert FD.is_notion_url('https://notion.so/abc')
    assert not FD.is_notion_url('https://someone.notion.site/page')
    assert not FD.is_notion_url('https://www.postype.com/@a/post/1')
    assert not FD.is_notion_url('annyeongz:12')
