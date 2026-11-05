# -*- coding: utf-8 -*-
"""_build/更新網站_巡檢片段.bat.txt 的分流:用一個只懂這個片段用到的 cmd 語法的小直譯器跑,確認
   沒帶參數不會跑巡檢、只印「[巡檢] 略過」(2026-11-05 站長回報沒帶參數也跑了:echo 裡的半形「)」把 if ( ) 區塊提早關掉)。
   片段裡只准用 rem / set / if…goto / if…set / goto / :標籤 / echo / python;出現 ( ) 區塊就直接失敗。"""
import io, os, re
from conftest import ROOT

SNIPPET = os.path.join(ROOT, '_build', '更新網站_巡檢片段.bat.txt')

def run_bat(args):
    lines = [l.rstrip('\r\n') for l in io.open(SNIPPET, encoding='utf-8')]
    labels = {l.strip()[1:].lower(): i for i, l in enumerate(lines) if l.strip().startswith(':') and not l.strip().startswith('::')}
    argv = list(args) + [''] * 3
    env, out, i = {}, [], 0
    def expand(s):
        s = re.sub(r'%~([1-9])', lambda m: argv[int(m.group(1)) - 1], s)
        return re.sub(r'%(\w+)%', lambda m: env.get(m.group(1), ''), s)
    def do(cmd):
        cmd = cmd.strip()
        m = re.match(r'goto\s+(:?\S+)$', cmd, re.I)
        if m:
            return 'goto', m.group(1).lstrip(':').lower()
        m = re.match(r'set\s+"(\w+)=(.*)"$', cmd, re.I)
        if m:
            if m.group(2):
                env[m.group(1)] = m.group(2)
            else:
                env.pop(m.group(1), None)
            return None
        raise AssertionError('不支援的指令(片段只准用 goto / set "V=…"):%r' % cmd)
    steps = 0
    while i < len(lines):
        steps += 1
        assert steps < 1000
        raw = lines[i].strip()
        i += 1
        assert not raw.endswith('(') and raw != ')', '片段不准用 ( ) 區塊:%r' % raw
        if not raw or raw.lower().startswith('rem') or raw.startswith(':'):
            continue
        low = raw.lower()
        if low.startswith('echo'):
            out.append(('echo', expand(raw[4:].strip()) if raw[4:5] != '.' else ''))
            continue
        if low.startswith('python '):
            out.append(('python', re.sub(r'\s+', ' ', expand(raw[7:])).strip()))
            continue
        act = None
        m = re.match(r'if\s+(/I\s+)?"([^"]*)"=="([^"]*)"\s+(.*)$', raw, re.I)
        if m:
            a, b = expand(m.group(2)), m.group(3)
            if (a.lower() == b.lower()) if m.group(1) else (a == b):
                act = do(m.group(4))
        else:
            m = re.match(r'if\s+(not\s+)?defined\s+(\w+)\s+(.*)$', raw, re.I)
            if m:
                if (m.group(2) in env) != bool(m.group(1)):
                    act = do(m.group(3))
            else:
                act = do(raw)
        if act:
            if act[1] == 'eof':
                break
            i = labels[act[1]]
    return [c for k, c in out if k == 'python'], [c for k, c in out if k == 'echo']

def test_no_args_skips_check():
    py, echo = run_bat([])
    assert py == [] and '[巡檢] 略過' in echo

def test_other_first_arg_skips_check():
    py, echo = run_bat(['abc'])
    assert py == [] and '[巡檢] 略過' in echo

def test_check_runs_and_writes():
    py, echo = run_bat(['巡檢'])
    assert py == ['check_links.py', 'notion_writeback.py --go'] and '[巡檢] 略過' not in echo
    assert run_bat(['check'])[0] == ['check_links.py', 'notion_writeback.py --go']

def test_check_browser_and_dry_any_order():
    assert run_bat(['巡檢', '瀏覽器'])[0] == ['check_links.py --browser', 'notion_writeback.py --go']
    assert run_bat(['巡檢', 'dry', '瀏覽器'])[0] == ['check_links.py --browser', 'notion_writeback.py']
    assert run_bat(['check', 'browser', 'dry'])[0] == ['check_links.py --browser', 'notion_writeback.py']

def test_setup_profile_only():
    assert run_bat(['設定檔'])[0] == ['check_links.py --setup-profile']
    assert run_bat(['setup'])[0] == ['check_links.py --setup-profile']

def test_no_half_width_paren_in_echo():
    for l in io.open(SNIPPET, encoding='utf-8'):
        s = l.strip()
        if s.lower().startswith('echo'):
            assert '(' not in s and ')' not in s, s
