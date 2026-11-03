# -*- coding: utf-8 -*-
"""canary.py:隱形版權 canary 的純函式(hash、挑選、比對)、本機 canary.json 的讀寫與祕密來源,以及 CLI。"""
import io, json, os
import pytest
from conftest import ROOT, FIXTURE
import build_site as B
import canary as CN

SECRET = 'unit-test-secret'

@pytest.fixture(scope='module')
def DATA():
    return B.build_data(FIXTURE)[0]

def test_digest_is_hmac_of_no_and_name():
    h = CN.digest(SECRET, '12', '戀戀遊戲機')
    assert len(h) == CN.HASH_LEN and all(c in '0123456789abcdef' for c in h)
    assert h == CN.digest(SECRET, '12', '戀戀遊戲機')                 # 同輸入同結果
    assert h != CN.digest(SECRET, '13', '戀戀遊戲機') != CN.digest(SECRET, '12', '戀戀遊戲機(改)')
    assert h != CN.digest('another-secret', '12', '戀戀遊戲機')         # 沒有祕密算不出來

def test_pick_is_deterministic_and_skips_dead_or_unnamed(DATA):
    picked = CN.pick(DATA['articles'], SECRET)
    assert len(picked) == CN.K and picked == CN.pick(list(reversed(DATA['articles'])), SECRET)   # 與輸入順序無關
    assert all(a['name'] and not a['dead'] for a in picked)
    assert [a['no'] for a in picked] != [a['no'] for a in CN.pick(DATA['articles'], 'other')]   # 換祕密換人
    assert CN.pick([{'no': '1', 'name': '', 'dead': False}, {'no': '2', 'name': 'x', 'dead': True}, {'no': '3', 'name': 'y'}], SECRET) == [{'no': '3', 'name': 'y'}]

def test_canary_list_is_sorted_hashes_of_items(DATA):
    items = CN.items(DATA, SECRET)
    assert len(items) == CN.K and all(set(x) == {'no', 'name', 'hash'} for x in items)
    assert all(x['hash'] == CN.digest(SECRET, x['no'], x['name']) for x in items)
    lst = CN.canary_list(DATA, SECRET)
    assert lst == sorted(x['hash'] for x in items) and len(set(lst)) == CN.K

def test_pairs_of_accepts_full_and_compact_shapes():
    assert CN.pairs_of({'articles': [{'no': '1', 'name': 'A'}, {'no': '1', 'name': 'A'}]}) == [('1', 'A')]
    assert CN.pairs_of({'v': 2, 'articles': [{'n': '2', 'm': 'B'}]}) == [('2', 'B')]
    assert CN.pairs_of([{'x': {'no': 3, 'name': 'C'}}, {'no': '4'}, 'junk']) == [('3', 'C')]
    assert CN.pairs_of(None) == []

def test_compare_detects_copied_data_json_pairs_and_clean(DATA, tmp_path):
    canary = {'secret': SECRET, 'items': CN.items(DATA, SECRET)}
    # ① 整包搬走 data.json:_origin、_canary 都在
    raw = B.data_json(DATA, CN.canary_list(DATA, SECRET))
    r = CN.compare(canary, json.loads(raw), raw)
    assert r['verdict'] == 'copied' and r['origin'] == B.origin_mark(DATA['synced'])
    assert r['hashes'] == CN.canary_list(DATA, SECRET) and r['recomputed'] == CN.K and len(r['pairs']) == CN.K
    # ② 只搬走編號 + 篇名(自己重新輸出,沒有 _ 鍵):hash 不在、但對應關係對得上
    foreign = {'items': [{'no': a['no'], 'name': a['name']} for a in DATA['articles']]}
    text = json.dumps(foreign, ensure_ascii=False)
    r = CN.compare(canary, foreign, text)
    assert r['verdict'] == 'pairs' and r['hashes'] == [] and r['recomputed'] == 0 and r['origin'] is None
    assert r['pairs'] == sorted((x['no'], x['name']) for x in canary['items'])
    # ③ 無關的站:乾淨
    other = {'items': [{'no': a['no'], 'name': a['name'] + '(別站改了標題)'} for a in DATA['articles']]}
    r = CN.compare(canary, other, json.dumps(other, ensure_ascii=False))
    assert r['verdict'] == 'clean' and r['pairs'] == [] and r['hashes'] == []
    # ④ 純文字(非 JSON)也能比 hash / _origin
    r = CN.compare(canary, None, '… ' + canary['items'][0]['hash'] + ' …')
    assert r['verdict'] == 'copied' and r['hashes'] == [canary['items'][0]['hash']]

def test_load_secret_env_then_file_then_none(tmp_path, monkeypatch):
    monkeypatch.delenv(CN.ENV, raising=False)
    assert CN.load_secret(str(tmp_path)) is None
    (tmp_path / CN.FILE_NAME).write_text(json.dumps({'secret': ' from-file '}), encoding='utf-8')
    assert CN.load_secret(str(tmp_path)) == 'from-file'
    (tmp_path / CN.FILE_NAME).write_text('not json', encoding='utf-8')
    assert CN.load_secret(str(tmp_path)) is None
    monkeypatch.setenv(CN.ENV, 'from-env')
    assert CN.load_secret(str(tmp_path)) == 'from-env'                 # 環境變數優先

def test_record_writes_items_and_keeps_history(DATA, tmp_path):
    path = str(tmp_path / CN.FILE_NAME)
    doc = CN.record(DATA, SECRET, path)
    assert doc['secret'] == SECRET and doc['items'] == CN.items(DATA, SECRET) and doc['history'] == [] and doc['updated']
    assert CN.load_file(path)['items'] == doc['items']
    D2 = json.loads(json.dumps(DATA))
    old_no = doc['items'][0]['no']
    next(a for a in D2['articles'] if a['no'] == old_no)['name'] += '(改名)'   # 篇名改了 → hash 換新、舊的進 history
    doc2 = CN.record(D2, SECRET, path)
    assert doc2['items'] != doc['items'] and doc['items'][0] in doc2['history'] and doc['items'][0] not in doc2['items']
    doc3 = CN.record(D2, SECRET, path)
    assert doc3['history'] == doc2['history']                              # 重跑不重複累積

def test_cli_init_show_check(DATA, tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(CN.ENV, raising=False)
    monkeypatch.setattr(CN, 'HERE', str(tmp_path))
    path = tmp_path / CN.FILE_NAME
    assert CN.main(['init']) == 0 and path.exists() and len(CN.load_file(str(path))['secret']) == 48
    secret = CN.load_file(str(path))['secret']
    assert CN.main(['init']) == 0 and CN.load_file(str(path))['secret'] == secret   # 不覆蓋
    data_path = tmp_path / 'data.json'
    data_path.write_text(B.data_json(DATA, CN.canary_list(DATA, secret)), encoding='utf-8')
    assert CN.main(['show', '--data', str(data_path)]) == 0
    assert CN.load_file(str(path))['items'] == CN.items(DATA, secret)
    assert CN.main(['check', str(data_path)]) == 0
    assert '整包搬走' in capsys.readouterr().out
    assert CN.main([]) == 1
