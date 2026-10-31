import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { expandData, normalizeData, makeFolder } from '../src/data.js';

// 精簡格式(build_site.compact_data 產出,tests/fixtures/compact_30.json)→ expandData 要還原成 expected.json 的完整形狀
const compact = JSON.parse(readFileSync(new URL('./fixtures/compact_30.json', import.meta.url), 'utf-8'));
const expected = JSON.parse(readFileSync(new URL('./fixtures/build_input/expected.json', import.meta.url), 'utf-8'));

describe('expandData:精簡 data.json → 完整資料', () => {
  it('30 篇 fixture 還原後與 build_site 的完整輸出逐篇相同(含 tags 15 面、作者 ID、created/edited)', () => {
    const D = expandData(JSON.parse(JSON.stringify(compact)));
    expect(D.v).toBeUndefined(); expect(D.pids).toBeUndefined();
    expect(D.total).toBe(30); expect(D.facets.length).toBe(15);
    expect(D.people).toEqual(expected.people);
    expect(D.announcements).toEqual(expected.announcements);
    const byNo = Object.fromEntries(D.articles.map((a) => [a.no, a]));
    for (const e of expected.articles) expect(byNo[e.no]).toEqual(e);
  });
  it('空欄位還原成空字串 / 空陣列 / false,單選分面也是陣列', () => {
    const D = expandData(compact);
    const a = D.articles.find((x) => x.no === '233');
    expect(a.author).toBe(''); expect(a.author_ids).toEqual([]); expect(a.translator_ids).toEqual([]);
    expect(Object.keys(a.tags).length).toBe(15);
    expect(Array.isArray(a.tags['文章狀態'])).toBe(true);
    expect(D.articles.some((x) => x.dead === true) && D.articles.some((x) => x.dead === false)).toBe(true);
  });
  it('舊的完整格式(沒有 v)原樣回傳;空值不會炸', () => {
    const full = { total: 1, facets: [], articles: [{ no: '1' }] };
    expect(expandData(full)).toBe(full);
    expect(expandData(null)).toBe(null);
  });
  it('normalizeData 接在後面可補上搜尋字串 _s(簡繁折算)', () => {
    const fold = makeFolder('員', '员');
    const D = normalizeData(expandData(JSON.parse(JSON.stringify(compact))), fold);
    const a = D.articles.find((x) => x.no === '10089');
    expect(a._s).toContain('了山之前说');            // 譯者也可搜
    expect(D.articles.every((x) => typeof x._s === 'string')).toBe(true);
  });
});

// 頂欄下方「📡 最後更新:X」:synced 字串解析與相對時間(純函式)
import { parseSynced, relativeTime } from '../src/data.js';
describe('parseSynced / relativeTime:最後更新的相對時間', () => {
  it('『2026/10/31 9:01 PM』當台北時間解析成 UTC 13:01;AM / PM / 12 點都對;壞字串回 null', () => {
    expect(parseSynced('2026/10/31 9:01 PM').toISOString()).toBe('2026-10-31T13:01:00.000Z');
    expect(parseSynced('2026/10/31 12:05 AM').toISOString()).toBe('2026-10-30T16:05:00.000Z');
    expect(parseSynced('2026/10/31 12:30 PM').toISOString()).toBe('2026-10-31T04:30:00.000Z');
    expect(parseSynced('2026/1/2 8:31 AM').toISOString()).toBe('2026-01-02T00:31:00.000Z');
    expect(parseSynced('')).toBe(null); expect(parseSynced(null)).toBe(null); expect(parseSynced('昨天')).toBe(null);
  });
  it('剛剛 / N 分鐘前 / N 小時前 / 昨天 / 前天 / N 天前(zh-Hant),未來時間當剛剛', () => {
    const t0 = Date.UTC(2026, 9, 31, 13, 1), at = (ms) => relativeTime(new Date(t0), t0 + ms);
    const M = 60000, H = 60 * M, D = 24 * H;
    expect(at(0)).toBe('剛剛'); expect(at(59 * 1000)).toBe('剛剛'); expect(at(-5 * M)).toBe('剛剛');
    expect(at(1 * M)).toMatch(/^1 ?分鐘前$/); expect(at(45 * M)).toMatch(/^45 ?分鐘前$/);
    expect(at(1 * H)).toMatch(/^1 ?小時前$/); expect(at(23 * H + 59 * M)).toMatch(/^23 ?小時前$/);
    expect(at(1 * D)).toBe('昨天'); expect(at(2 * D + 3 * H)).toBe('前天');
    expect(at(3 * D)).toMatch(/^3 ?天前$/); expect(at(40 * D)).toMatch(/^40 ?天前$/);
    expect(relativeTime(null)).toBe('');
  });
});
