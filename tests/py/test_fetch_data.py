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
