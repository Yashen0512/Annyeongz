# -*- coding: utf-8 -*-
"""check_links.py 的純函式:到期判斷、「連續兩天才算死」狀態機、事件判定、作者改名判斷、平台被擋的短路、重試。不碰網路。"""
import check_links as CL
from checkers._http import TransientError

D1, D2, D3 = '2026-10-30', '2026-10-31', '2026-11-01'
dead = lambda: {'status': 'deleted', 'author_name': None, 'reason': '404', 'code': 404}
ok = lambda name=None: {'status': 'ok', 'author_name': name, 'reason': 'ld_json', 'code': 200, 'author_url': ''}
unk = lambda: {'status': 'unknown', 'author_name': None, 'reason': 'transient', 'code': None}
login = lambda: {'status': 'login_required', 'author_name': None, 'reason': 'login_wall', 'code': 200}

# ---- 狀態機 ----
def test_two_consecutive_days_required():
    e = CL.advance(None, dead(), D1)
    assert e['status'] == 'deleted' and e['streak'] == 1 and not e.get('dead')
    e = CL.advance(e, dead(), D1)                      # 同一天重跑不重複計
    assert e['streak'] == 1 and not e.get('dead')
    e = CL.advance(e, dead(), D2)
    assert e['streak'] == 2 and e['dead'] is True and e['dead_since'] == D2

def test_unknown_does_not_change_counts():
    e = CL.advance(None, dead(), D1)
    e2 = CL.advance(e, unk(), D2)
    assert e2['status'] == 'deleted' and e2['streak'] == 1 and not e2.get('dead') and e2['last'] == D2
    e3 = CL.advance(e2, dead(), D3)
    assert e3['dead'] is True                          # 第二次觀測到 deleted(中間 unknown 不算斷)

def test_ok_breaks_streak_and_revives():
    e = CL.advance(CL.advance(None, dead(), D1), dead(), D2)
    assert e['dead']
    e = CL.advance(e, ok('新名'), D3)
    assert e['status'] == 'ok' and e['dead'] is False and 'dead_since' not in e and e['streak'] == 1
    assert e['author_name'] == '新名'

def test_login_required_does_not_revive_or_kill():
    e = CL.advance(CL.advance(None, dead(), D1), dead(), D2)
    e = CL.advance(e, login(), D3)
    assert e['dead'] is True and e['status'] == 'login_required'
    e = CL.advance(None, login(), D1); e = CL.advance(e, login(), D2)
    assert not e.get('dead')

def test_ok_then_deleted_restarts_streak():
    e = CL.advance(None, ok(), D1)
    e = CL.advance(e, dead(), D2)
    assert e['streak'] == 1 and not e.get('dead')

def test_reset_entry_clears_dead_and_streak():
    e = CL.advance(CL.advance(None, dead(), D1), dead(), D2)
    e['author_name'], e['platform'] = '某博客', 'lofter'
    r = CL.reset_entry(e, D3)
    assert r['status'] == 'ok' and r['streak'] == 0 and r['dead'] is False and r['last'] == D3 and r['reason'] == 'reset'
    assert 'dead_since' not in r and 'counted' not in r
    assert r['author_name'] == '某博客' and r['platform'] == 'lofter' and r['first'] == D1     # 其餘欄位保留
    assert e['dead'] is True                                                                  # 不改原物件
    # 重設後再看到 deleted 從 1 重新數,要再連續兩天才死
    e2 = CL.advance(r, dead(), D3)
    assert e2['streak'] == 1 and not e2.get('dead')
    assert CL.reset_entry(None, D1)['status'] == 'ok' and CL.reset_entry(None, D1)['first'] == D1

def test_reset_links_cli_rewrites_state_file(tmp_path, capsys):
    import json
    u, v = 'https://a.lofter.com/post/1_2', 'https://b.lofter.com/post/3_4'
    st = {'__meta__': {'runs': 3, 'date': D2}, u: CL.advance(CL.advance(None, dead(), D1), dead(), D2), v: CL.advance(None, ok(), D2)}
    p = tmp_path / 'link_status.json'
    p.write_text(json.dumps(st, ensure_ascii=False), encoding='utf-8')
    assert CL.reset_links_cli(str(p), [u, 'https://nope.lofter.com/post/9'], today=D3) == 0
    out = json.loads(p.read_text(encoding='utf-8'))
    assert list(out)[0] == '__meta__' and out['__meta__'] == {'runs': 3, 'date': D2}        # __meta__ 保留、排最前
    assert out[u]['status'] == 'ok' and out[u]['streak'] == 0 and out[u]['dead'] is False and out[u]['last'] == D3
    assert out[v] == st[v]                                                                  # 別的連結不動
    msg = capsys.readouterr().out
    assert '已重設' in msg and 'nope.lofter.com' in msg and '略過' in msg
    # 全部找不到 → 不寫檔、回傳 1
    before = p.read_text(encoding='utf-8')
    assert CL.reset_links_cli(str(p), ['https://nope.lofter.com/post/9'], today=D3) == 1
    assert p.read_text(encoding='utf-8') == before
    assert CL.reset_links_cli(str(tmp_path / 'missing.json'), [u], today=D3) == 1

def test_main_reset_link_does_not_need_article_links(tmp_path, capsys):
    import json
    u = 'https://a.lofter.com/post/1_2'
    p = tmp_path / 'link_status.json'
    p.write_text(json.dumps({'__meta__': {}, u: CL.advance(CL.advance(None, dead(), D1), dead(), D2)}), encoding='utf-8')
    assert CL.main(['--src', str(tmp_path), '--reset-link', u]) == 0        # 沒有 article_links.json 也能跑
    assert json.loads(p.read_text(encoding='utf-8'))[u]['dead'] is False

def test_is_due_dead_rechecked_every_30_days():
    assert CL.is_due(None, D1) is True
    assert CL.is_due({'dead': True, 'last': '2026-10-20'}, D1) is False      # 10 天前,不用
    assert CL.is_due({'dead': True, 'last': '2026-09-29'}, D1) is True       # 31 天
    assert CL.is_due({'dead': False, 'status': 'deleted', 'last': D1}, D2) is True
    assert CL.is_due({'status': 'ok', 'last': D1}, D1) is True

def test_events_for():
    assert CL.events_for({'dead': True, 'status': 'deleted', 'last': D1}, False, D1) == 'new_dead'
    assert CL.events_for({'dead': True, 'status': 'deleted', 'last': D1}, True, D1) is None     # Notion 已有 ❌
    assert CL.events_for({'dead': False, 'status': 'ok', 'last': D1}, True, D1) == 'revived'    # 有 ❌ 但今天 ok
    assert CL.events_for({'dead': False, 'status': 'ok', 'last': D1}, True, D2) is None        # 今天沒查
    assert CL.events_for({'dead': False, 'status': 'login_required', 'last': D1}, True, D1) is None
    assert CL.events_for({'dead': False, 'status': 'deleted', 'streak': 1, 'last': D1}, False, D1) is None  # 才一天
    assert CL.events_for(None, False, D1) is None

# ---- 作者改名 ----
PID, PID2 = 'a' * 32, 'b' * 32
def people(url='https://www.postype.com/profile/@abc123', aliases=()):
    return {PID: {'name': '노네임(noname)', 'urls': {'Postype': url} if url else {}, 'aliases': list(aliases), 'dead': False},
            PID2: {'name': '別人', 'urls': {}, 'aliases': [], 'dead': False}}
def arts(*nos, pid=PID, tr=()):
    return {n: {'no': n, 'author_ids': [pid], 'translator_ids': list(tr)} for n in nos}
def ob(no, name='새이름', handle='@abc123', plat='postype'):
    return {'no': no, 'platform': plat, 'name': name, 'author_url': 'https://www.postype.com/profile/' + handle,
            'url': 'https://www.postype.com/@blog/post/%s' % no}

def test_rename_needs_two_works_and_matching_handle():
    r, c = CL.detect_renames([ob('1'), ob('2')], people(), arts('1', '2'))
    assert r == [{'pid': PID, 'old': '노네임(noname)', 'new': '새이름', 'platform': 'postype', 'nos': ['1', '2']}] and c == []
    r, c = CL.detect_renames([ob('1')], people(), arts('1'))
    assert r == [] and c == []

def test_rename_ignores_known_names_and_aliases():
    assert CL.detect_renames([ob('1', '노네임'), ob('2', '노네임')], people(), arts('1', '2')) == ([], [])     # 括號前段
    assert CL.detect_renames([ob('1', 'NoName'), ob('2', 'noname ')], people(), arts('1', '2')) == ([], [])  # 括號內、大小寫 / 空白
    assert CL.detect_renames([ob('1', '舊名'), ob('2', '舊名')], people(aliases=['舊名']), arts('1', '2')) == ([], [])

def test_rename_skips_shared_collection_account():
    a = arts('1', '2'); a.update(arts('3', pid=PID2))
    obs = [ob('1', '合集帳號'), ob('2', '合集帳號'), ob('3', '合集帳號')]
    assert CL.detect_renames(obs, people(), a) == ([], [])

def test_rename_handle_mismatch_is_dropped_and_missing_url_is_candidate():
    assert CL.detect_renames([ob('1', handle='@other'), ob('2', handle='@other')], people(), arts('1', '2')) == ([], [])
    r, c = CL.detect_renames([ob('1'), ob('2')], people(url=''), arts('1', '2'))
    assert r == [] and len(c) == 1 and c[0]['new'] == '새이름'

def test_rename_requires_single_author_without_translator():
    assert CL.detect_renames([ob('1'), ob('2')], people(), arts('1', '2', tr=['c' * 32])) == ([], [])
    multi = {n: {'no': n, 'author_ids': [PID, PID2], 'translator_ids': []} for n in ('1', '2')}
    assert CL.detect_renames([ob('1'), ob('2')], people(), multi) == ([], [])

def test_handle_of():
    assert CL.handle_of('postype', 'https://www.postype.com/profile/@Abc123') == 'abc123'
    assert CL.handle_of('postype', 'https://myblog.postype.com/') == 'myblog'
    assert CL.handle_of('lofter', 'https://foo.lofter.com/post/1_2') == 'foo'
    assert CL.handle_of('ao3', 'https://archiveofourown.org/users/Name/pseuds/P') == 'name'
    assert CL.handle_of('aff', 'https://www.asianfanfics.com/profile/view/42') == '42'
    assert CL.handle_of('aff', 'https://www.asianfanfics.com/profile/u/handle') == ''

# ---- 收集 / 平台被擋 / 重試 ----
def test_collect_targets_dedupes_and_marks():
    links = {'1': {'A': [['Postype-原文', 'https://www.postype.com/@b/post/1'], ['前傳', 'annyeongz:2']]},
             '2': {'B': [['❌ PT', 'https://www.postype.com/@b/post/1'], ['WB', 'https://weibo.com/1']]},
             '__edited__': {}, '__blocks__': {'1': {'page': 'p1', 'links': {'https://www.postype.com/@b/post/1': ['blk1', 0]}}}}
    ppl = {PID: {'name': 'x', 'urls': {'Lofter': 'https://foo.lofter.com/'}, 'aliases': [], 'dead': False}}
    ts = CL.collect_targets(links, {}, ppl, ['postype', 'lofter'])
    assert [t['url'] for t in ts] == ['https://www.postype.com/@b/post/1', 'https://foo.lofter.com/']
    refs = ts[0]['refs']
    assert [r['marked'] for r in refs] == [False, True] and refs[0]['block'] == ['blk1', 0] and refs[0]['page'] == 'p1'
    assert ts[1]['refs'][0]['kind'] == 'author'
    assert len(CL.collect_targets(links, {}, ppl, ['postype', 'lofter'], only_nos={'2'})) == 1   # --no 不查作者頁

def test_run_platform_stops_after_three_blocked():
    targets = [{'url': 'https://www.asianfanfics.com/story/view/%d/x' % i, 'platform': 'aff', 'refs': []} for i in range(10)]
    calls = []
    def fake(url):
        calls.append(url)
        return {'status': 'unknown', 'author_name': None, 'reason': 'blocked', 'blocked': True, 'code': 403}
    import threading
    st = CL.run_platform('aff', targets, {}, threading.Lock(), False, sleep=lambda s: None, checker=fake)
    assert st == {'checked': 3, 'blocked': True, 'skipped': 7} and len(calls) == 3

def test_run_platform_not_blocked_when_only_some_fail():
    targets = [{'url': 'u%d' % i, 'platform': 'postype', 'refs': []} for i in range(4)]
    seq = iter([{'status': 'ok', 'author_name': 'a', 'code': 200}] + [{'status': 'unknown', 'author_name': None, 'blocked': True, 'code': 403}] * 3)
    import threading
    st = CL.run_platform('postype', targets, {}, threading.Lock(), False, sleep=lambda s: None, checker=lambda u: next(seq))
    assert st['checked'] == 4 and st['blocked'] is False

def test_check_with_retry(monkeypatch):
    n = {'c': 0}
    def flaky(url):
        n['c'] += 1
        if n['c'] < 3:
            raise TransientError('HTTP 503')
        return ok()
    monkeypatch.setattr(CL.checkers, 'check', flaky)
    assert CL.check_with_retry('https://x', sleep=lambda s: None)['status'] == 'ok' and n['c'] == 3
    monkeypatch.setattr(CL.checkers, 'check', lambda u: (_ for _ in ()).throw(TransientError('timeout')))
    r = CL.check_with_retry('https://x', sleep=lambda s: None)
    assert r['status'] == 'unknown' and r['reason'].startswith('transient')

def test_report_markdown_sections():
    rep = {'date': D1, 'platforms': {'postype': {'label': 'Postype', 'checked': 3, 'blocked': False, 'skipped': 0},
                                     'aff': {'label': 'Asianfanfics', 'checked': 3, 'blocked': True, 'skipped': 9}},
           'new_dead': [{'no': '1', 'title': 'T', 'label': 'PT', 'url': 'https://p/1', 'platform': 'postype', 'code': 404}],
           'revived': [], 'renames': [{'old': 'A', 'new': 'B', 'platform': 'postype', 'nos': ['1', '2']}],
           'rename_candidates': [], 'author_pages': {'deleted': [], 'revived': []}}
    md = CL.report_markdown(rep)
    assert '## 已刪' in md and '## 復活' in md and '## 改名' in md
    assert 'No.1《T》PT — https://p/1' in md and '改名:A → B(Postype)' in md and '略過 9 筆' in md
    rep['renames'] = []
    assert '## 改名\n(無)' in CL.report_markdown(rep) and '## 復活\n(無)' in CL.report_markdown(rep)

def test_collect_targets_ignores_stale_title_under_a_no():
    # article_links.json 殘留改號前那頁的標題時,只看目前標題那組(與 build_site 挑連結的規則一致)
    links = {'786': {'Passionate A&W': [['Postype-番外1-原文', 'https://www.postype.com/@g/post/15413585']],
                     '설계실 로맨스': [['Postype-原文', 'https://www.postype.com/@n/post/6308988']]},
             '__edited__': {}, '__blocks__': {}}
    arts = {'786': {'no': '786', 'name': '설계실 로맨스'}}
    assert [t['url'] for t in CL.collect_targets(links, arts, {}, ['postype'])] == ['https://www.postype.com/@n/post/6308988']
    assert len(CL.collect_targets(links, {}, {}, ['postype'])) == 2            # 沒有文章資料時照舊全查
    one = {'786': {'舊標題': [['PT', 'https://www.postype.com/@n/post/6308988']]}, '__edited__': {}, '__blocks__': {}}
    assert len(CL.collect_targets(one, arts, {}, ['postype'])) == 1          # 只有一組標題就沿用(build_site 也是)

# ---- 2026-11-05 實測誤判:簡繁差異、同作者多個新名字、標題片段 ----
LFT_PID = 'd' * 32
def lft_people(name='咸魚', url='https://xianyu.lofter.com/', aliases=()):
    return {LFT_PID: {'name': name, 'urls': {'Lofter': url} if url else {}, 'aliases': list(aliases), 'dead': False}}
def lob(no, name, host='xianyu.lofter.com'):
    return {'no': no, 'platform': 'lofter', 'name': name, 'author_url': host,
            'url': 'https://%s/post/1a2b_%s' % (host, no)}

def test_fold_zh_uses_stmap():
    assert CL.fold_zh('咸魚') == CL.fold_zh('咸鱼') == CL.fold_zh('鹹魚')
    assert CL.same_name('百憂解', '百忧解') and CL.same_name('一隻大鵝', '一只大鹅')
    assert not CL.same_name('百憂解', '百憂')

def test_rename_ignores_simplified_traditional_difference():
    a = arts('1', '2', '3', pid=LFT_PID)
    assert CL.detect_renames([lob(n, '咸鱼') for n in ('1', '2', '3')], lft_people(), a) == ([], [])
    p = lft_people('百憂解', 'https://baiyoujie.lofter.com/')
    obs = [lob(n, '百忧解', 'baiyoujie.lofter.com') for n in ('1', '2')]
    manual = []
    assert CL.detect_renames(obs, p, a, manual) == ([], []) and manual == []
    # 曾用名也一樣折算
    assert CL.detect_renames([lob(n, '舊名字') for n in ('1', '2')], lft_people(aliases=['旧名字']), a) == ([], [])

def test_rename_conflicting_new_names_go_to_manual():
    a = arts('1', '2', '3', '4', pid=LFT_PID)
    p = lft_people('一只大鹅', 'https://dae.lofter.com/')
    obs = [lob('1', '上-一只大鹅', 'dae.lofter.com'), lob('2', '上-一只大鹅', 'dae.lofter.com'),
           lob('3', '下-一只大鹅', 'dae.lofter.com'), lob('4', '下-一只大鹅', 'dae.lofter.com')]
    manual = []
    assert CL.detect_renames(obs, p, a, manual) == ([], [])
    assert len(manual) == 1 and manual[0]['old'] == '一只大鹅' and manual[0]['platform'] == 'lofter'
    assert [x['new'] for x in manual[0]['names']] == ['上-一只大鹅', '下-一只大鹅'] and '不同的新名字' in manual[0]['why']
    # 一篇抓到別的名字也算衝突(就算另一個名字有兩篇)
    obs = [lob('1', '新筆名', 'dae.lofter.com'), lob('2', '新筆名', 'dae.lofter.com'), lob('3', '雨季', 'dae.lofter.com')]
    manual = []
    assert CL.detect_renames(obs, p, a, manual) == ([], []) and len(manual) == 1
    # 在別人帳號(轉載)上看到的名字不算衝突:真的改名照常寫回
    obs = [lob('1', '新筆名', 'dae.lofter.com'), lob('2', '新筆名', 'dae.lofter.com'), lob('3', '轉載號', 'repost.lofter.com')]
    manual = []
    r, c = CL.detect_renames(obs, p, a, manual)
    assert [x['new'] for x in r] == ['新筆名'] and manual == []

def test_title_fragment():
    for bad in ('上-一只大鹅', '下-一只大鹅', '一只大鹅-下', '雨季番外', '第3章', '第 十二 話', '雨季（上）', '【下】雨季',
                '雨季 上篇', '完結篇', 'Chapter 2', 'ch.3', 'Part 1'):
        assert CL.title_fragment(bad), bad
    for good in ('一只大鹅', '天上人間', '上官', '下雨天', '노네임', 'noname', 'chapters', '百憂解', 'ep_writer'):
        assert CL.title_fragment(good) == '', good

def test_rename_title_fragment_goes_to_manual():
    a = arts('1', '2', pid=LFT_PID)
    p = lft_people('一只大鹅', 'https://dae.lofter.com/')
    manual = []
    assert CL.detect_renames([lob('1', '番外-一只大鹅', 'dae.lofter.com'), lob('2', '番外-一只大鹅', 'dae.lofter.com')],
                             p, a, manual) == ([], [])
    assert len(manual) == 1 and '標題片段「番外」' in manual[0]['why']

def test_rename_hold_reason():
    assert CL.rename_hold_reason('咸魚', '咸鱼') and CL.rename_hold_reason('一只大鹅', '上-一只大鹅')
    assert CL.rename_hold_reason('A', '') and CL.rename_hold_reason('A', 'b', known={'b'})
    assert CL.rename_hold_reason('노네임', '새이름') == ''

def test_report_includes_rename_manual_and_opens_issue():
    rep = {'date': D1, 'platforms': {}, 'new_dead': [], 'revived': [], 'renames': [], 'rename_candidates': [],
           'rename_manual': [{'pid': LFT_PID, 'old': '一只大鹅', 'platform': 'lofter', 'why': '同一作者在不同篇抓到 2 個不同的新名字',
                              'names': [{'new': '上-一只大鹅', 'nos': ['1', '2']}, {'new': '下-一只大鹅', 'nos': ['3']}]}],
           'author_pages': {'deleted': [], 'revived': []}}
    md = CL.report_markdown(rep)
    assert CL.RENAME_MANUAL_HEAD in md
    assert '- 一只大鹅(Lofter):抓到 「上-一只大鹅」(No.1、2) / 「下-一只大鹅」(No.3)' in md

def test_build_report_has_changes_with_only_manual():
    p = lft_people('一只大鹅', 'https://dae.lofter.com/')
    a = arts('1', '2', pid=LFT_PID)
    targets, results, state = [], {}, {}
    for no, nm in (('1', '上-一只大鹅'), ('2', '下-一只大鹅')):
        u = 'https://dae.lofter.com/post/1a2b_%s' % no
        targets.append({'url': u, 'platform': 'lofter', 'refs': [{'kind': 'article', 'no': no, 'title': 'T', 'label': 'LFT', 'marked': False}]})
        results[u] = {'status': 'ok', 'author_name': nm, 'author_url': 'dae.lofter.com', 'reason': '200', 'code': 200}
        state[u] = CL.advance(None, results[u], D1)
    rep = CL.build_report(D1, targets, results, state, a, p, {})
    assert rep['renames'] == [] and len(rep['rename_manual']) == 1 and rep['has_changes'] is True

# ---- 2026-11-06:每次執行上限(AFF 150 筆),最久沒查的先 ----
def test_prioritize_oldest_first_and_cap():
    tg = lambda i: {'url': 'https://www.asianfanfics.com/story/view/%d/x' % i, 'platform': 'aff', 'refs': []}
    targets = [tg(i) for i in range(6)]
    state = {targets[0]['url']: {'last': '2026-11-05'}, targets[1]['url']: {'last': '2026-10-01'},
             targets[2]['url']: {'last': '2026-11-05'}, targets[4]['url']: {'last': '2026-10-20'}}   # 3、5 沒查過
    got, deferred = CL.prioritize(targets, state, 4)
    assert [t['url'][-3] for t in got] == ['3', '5', '1', '4'] and deferred == 2      # 沒查過的最前面(維持原順序)、再依 last 由舊到新
    got, deferred = CL.prioritize(targets, state, 0)
    assert len(got) == 6 and deferred == 0 and [t['url'][-3] for t in got][-2:] == ['0', '2']   # 不截斷只排序;同日期維持原順序
    assert CL.prioritize(targets, state, 10)[1] == 0
    assert CL.PLAT_MAX_PER_RUN == {'aff': 150}

def test_advance_skipped_result_keeps_last():
    skipped = {'status': 'unknown', 'author_name': None, 'reason': 'rate_limited_skip', 'code': None, 'skipped': True}
    e = CL.advance({'status': 'ok', 'streak': 2, 'counted': '2026-11-01', 'last': '2026-11-01', 'first': '2026-10-01'}, skipped, '2026-11-06')
    assert e['last'] == '2026-11-01' and e['streak'] == 2 and e['status'] == 'ok' and e['reason'] == 'rate_limited_skip'
    assert CL.is_due(e, '2026-11-07')
    assert CL.advance({}, skipped, '2026-11-06').get('last') is None
    assert CL.last_checked(None) == '' and CL.last_checked({'last': '2026-11-01'}) == '2026-11-01'

def test_main_caps_aff_per_run_oldest_first(tmp_path, monkeypatch, capsys):
    """main:AFF 到期超過上限時只查最久沒查的那幾筆,其餘下次;Postype 不受上限影響。"""
    import browser_checker as BC
    b = tmp_path / '_build'; b.mkdir()
    import io as _io, os, json
    from conftest import ROOT
    (tmp_path / 'data.json').write_text(_io.open(os.path.join(ROOT, 'tests', 'fixtures', 'compact_30.json'), encoding='utf-8').read(), encoding='utf-8')
    af = lambda i: 'https://www.asianfanfics.com/story/view/%d/x' % i
    links = {str(i): {'T%d' % i: [['AF', af(i)]]} for i in range(1, 6)}
    links['6'] = {'T6': [['PT', 'https://www.postype.com/@b/post/1']]}
    (b / 'article_links.json').write_text(json.dumps(links, ensure_ascii=False), encoding='utf-8')
    (b / 'link_status.json').write_text(json.dumps({af(1): {'last': '2026-11-05', 'status': 'ok'}, af(2): {'last': '2026-10-01', 'status': 'ok'},
                                                    af(4): {'last': '2026-10-15', 'status': 'ok'}}), encoding='utf-8')
    monkeypatch.setattr(CL, 'PLAT_MAX_PER_RUN', {'aff': 2})
    monkeypatch.setattr(BC, 'preflight', lambda src, plats, **k: {'available': True, 'warp': False, 'usable': list(plats), 'notes': {}, 'cookies': {}})
    got = {}
    def fake_run_all(pre, by_plat, platforms, results, lock, *a, **k):
        got.update({p: [t['url'] for t in ts] for p, ts in by_plat.items()})
        return {p: {'checked': 0, 'blocked': False, 'skipped': 0, 'challenges': 0} for p in platforms}
    monkeypatch.setattr(BC, 'run_all', fake_run_all)
    monkeypatch.setattr(CL, 'run_platform', lambda p, ts, *a, **k: {'checked': len(ts), 'blocked': False, 'skipped': 0})
    CL.main(['--browser', '--src', str(b), '--platforms', 'postype,aff', '--no', '1,2,3,4,5,6'])
    assert got['aff'] == [af(3), af(5)]                                           # 沒查過的兩筆先(維持編號順序),其餘三筆下次
    out = capsys.readouterr().out
    assert 'Asianfanfics 今天到期 5 筆,每次最多查 2 筆(最久沒查的先),其餘 3 筆下次再查' in out and '今天要查 3 筆' in out
