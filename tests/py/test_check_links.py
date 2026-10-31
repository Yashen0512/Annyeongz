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
