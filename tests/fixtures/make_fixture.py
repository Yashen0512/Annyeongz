# -*- coding: utf-8 -*-
"""從 data.js 反推一份 30 篇的建置輸入(主表 CSV、作者庫 CSV、公告 CSV、article_links.json),
   放在 tests/fixtures/build_input/,讓 pytest 不需要 Notion token 也能跑完整個 build_site.py。
   重新產生:python3 tests/fixtures/make_fixture.py(從倉庫根目錄執行;只用標準庫)。
   挑選規則(固定、可重現):編號 233(作者空白)、1270(多作者)、10089(譯文:作者+譯者)、
   1232 / 10022(站內互連)、幾篇原文已刪(❌ 過半、紅標)、有收錄篇名的,再依編號補到 30 篇。"""
import csv, io, json, os, sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, '_build'))
import build_site as B   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'build_input')
MUST = ['233', '1270', '10089', '1232', '10022', '1', '305', '1396']
PLAT_BY_LABEL = {lab: col for lab, col in B.PLATCOL.items()}

def cn_dt(key):
    """YYYYMMDDHHMM → Notion 中文日期『2025年6月3日 下午10:26』(parse_dt 的反函式)。0 → ''。"""
    if not key:
        return ''
    s = str(key)
    y, mo, d, h, mi = int(s[0:4]), int(s[4:6]), int(s[6:8]), int(s[8:10]), int(s[10:12])
    ap = '上午' if h < 12 else '下午'
    h12 = h % 12 or 12
    return '%d年%d月%d日 %s%d:%02d' % (y, mo, d, ap, h12, mi)

def cn_date(dk):
    return '%d年%d月%d日' % (dk // 10000, dk // 100 % 100, dk % 100) if dk else ''

def pick(articles):
    byno = {a['no']: a for a in articles}
    chosen = [byno[n] for n in MUST if n in byno]
    def want(a):
        return a not in chosen
    # 原文已刪:❌ 過半的、紅標的各挑兩篇;有收錄篇名的兩篇;有譯者的一篇
    ratio_dead = [a for a in articles if a['dead'] and B.is_dead(False, a['links']) and want(a)][:2]
    manual_dead = [a for a in articles if a['dead'] and not B.is_dead(False, a['links']) and want(a)][:2]
    chosen += ratio_dead + manual_dead
    chosen += [a for a in articles if a['alias'] and want(a)][:2]
    chosen += [a for a in articles if a['translator'] and want(a)][:1]
    for a in sorted(articles, key=lambda x: int(x['no'])):
        if len(chosen) >= 30:
            break
        if want(a):
            chosen.append(a)
    return chosen[:30]

def main():
    D = json.loads(io.open(os.path.join(ROOT, 'data.js'), encoding='utf-8').read()[len('window.DATA = '):-1])
    arts = pick(D['articles'])
    os.makedirs(os.path.join(OUT, '_authors'), exist_ok=True)
    os.makedirs(os.path.join(OUT, '_announce'), exist_ok=True)
    facet_cols = list(B.F.FACETS.keys()) + B.F.EVENT_FACETS
    header = ['文章名稱', 'No', '上次編輯時間', '人設(安、員)', '作者/譯者資料庫', '建立時間', '文章標籤',
              '文章狀態', '文章篇幅', '文章類型', '結局'] + facet_cols + ['紅標', '收錄篇名']
    rows, links, pids = [], {}, []
    for a in arts:
        cell = []
        for names_key, ids_key in (('author', 'author_ids'), ('translator', 'translator_ids')):
            names = a[names_key].split('、') if a[names_key] else []
            for nm, pid in zip(names, a[ids_key]):
                cell.append('%s (https://www.notion.so/%s)' % (nm, pid))
                if pid not in pids:
                    pids.append(pid)
        manual = a['dead'] and not B.is_dead(False, a['links'])   # 紅標才會 dead 的 → 紅標 = Y
        rows.append([a['name'], a['no'], cn_dt(a['ek']), a['persona'], ', '.join(cell), cn_dt(a['ck']), '',
                     (a['tags'].get('文章狀態') or [''])[0], (a['tags'].get('文章篇幅') or [''])[0],
                     (a['tags'].get('文章類型') or [''])[0], (a['tags'].get('結局') or [''])[0]]
                    + [', '.join(a['tags'].get(f, [])) for f in facet_cols] + ['Y' if manual else '', a['alias']])
        links[a['no']] = {a['name']: [[l[0] + ' ❌' if len(l) > 2 else l[0], l[1]] for l in a['links']]}
    with io.open(os.path.join(OUT, 'Annyeongz_176a7213548080cda25dd9e1edd5b7a4_all.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)
    ah = ['作者名稱'] + [col for col in B.PLATCOL.values()] + ['紅標', '頁面ID']
    with io.open(os.path.join(OUT, '_authors', 'authors_all.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(ah)
        for pid in pids:
            p = D['people'][pid]
            w.writerow([p['name']] + [p['urls'].get(lab, '') for lab in B.PLATCOL] + ['Y' if p['dead'] else '', pid])
    with io.open(os.path.join(OUT, '_announce', 'announce_all.csv'), 'w', encoding='utf-8-sig', newline='') as fh:
        w = csv.writer(fh); w.writerow(['內容', '日期', '置頂'])
        for x in D['announcements']:
            w.writerow([x['content'], cn_date(x['dk']), 'Yes' if x['pin'] else 'No'])
    links['__edited__'] = {}
    io.open(os.path.join(OUT, 'article_links.json'), 'w', encoding='utf-8').write(json.dumps(links, ensure_ascii=False, indent=0))
    io.open(os.path.join(OUT, 'stats.json'), 'w', encoding='utf-8').write(json.dumps(D['stats'], ensure_ascii=False))
    # 預期輸出:這 30 篇在 data.js 裡的原樣(測試用來比對「重建 == 原本」)
    expected = {'articles': arts, 'people': {pid: D['people'][pid] for pid in pids}, 'announcements': D['announcements'],
                'updated': B.fmt_updated(max(a['ek'] for a in arts))}
    io.open(os.path.join(OUT, 'expected.json'), 'w', encoding='utf-8').write(json.dumps(expected, ensure_ascii=False, indent=0))
    print('fixture:', len(arts), '篇', len(pids), '位作者 →', OUT)

if __name__ == '__main__':
    main()
