import { describe, it, expect } from 'vitest';
import {
  monthRange, monthlyCounts, tagRanking, authorRanking, deadRatio, personCount, tagCount, overview,
  scatterPoints, yearlyDead, daysSince, ymOf, yearOf, ymLabel, withAlpha, BIRTH, START_YM, IMPORT_YM,
  monthlyChartConfig, rankingChartConfig, scatterChartConfig, yearlyChartConfig,
} from '../src/stats.js';
import { art } from './fixtures.js';

const FACETS = [
  { key: '文章狀態', type: 'single', options: [] },
  { key: 'CP配對', type: 'multi', options: [] },
  { key: '氛圍', type: 'multi', options: [] },
];
// 六篇:跨 2024/12 ~ 2025/03,兩篇已刪,含多作者、譯者、作者 ID、空作者
const ARTS = [
  art(1, { 'CP配對': ['安/員'], '氛圍': ['甜文'], '文章狀態': ['完結'] }, { ck: 202412311200, author: '甲', author_ids: ['idA'] }),
  art(2, { 'CP配對': ['安/員'], '氛圍': ['甜文', '日常'] }, { ck: 202501051000, author: '甲、乙', author_ids: ['idA', 'idB'] }),
  art(3, { 'CP配對': ['員/安'], '氛圍': ['虐文'] }, { ck: 202501200900, dead: true, author: '乙', author_ids: ['idB'] }),
  art(4, { 'CP配對': ['安/員'], '氛圍': ['日常'] }, { ck: 202503010800, author: '丙', author_ids: [''], translator: '譯者丁', translator_ids: ['idD'] }),
  art(5, { 'CP配對': ['互攻'], '氛圍': ['甜文'] }, { ck: 202503150800, dead: true, author: '', author_ids: [] }),
  art(6, { 'CP配對': ['安/員'], '氛圍': [] }, { ck: 0, author: '甲', author_ids: ['idA'] }),   // 沒有 ck:不進任何時間分組
];
const PEOPLE = { idA: { name: '甲(新名)', urls: {}, aliases: ['甲'], dead: false }, idB: { name: '乙', urls: {}, aliases: [], dead: false }, idD: { name: '譯者丁', urls: {}, aliases: [], dead: false } };

describe('日期工具', () => {
  it('ck → 年月 / 年份 / 標籤', () => {
    expect(ymOf(202412311200)).toBe(202412);
    expect(yearOf(202412311200)).toBe(2024);
    expect(ymOf(0)).toBe(0);
    expect(ymLabel(202308)).toBe('2023/08');
  });
  it('monthRange 含頭尾、跨年', () => {
    expect(monthRange(202311, 202402)).toEqual([202311, 202312, 202401, 202402]);
    expect(monthRange(202405, 202405)).toEqual([202405]);
    expect(monthRange(202405, 202401)).toEqual([202405]);   // 終點比起點早:只回起點
  });
  it('daysSince:宇宙誕生到指定日', () => {
    expect(daysSince(BIRTH, new Date(2023, 7, 7))).toBe(0);
    expect(daysSince(BIRTH, new Date(2023, 7, 8))).toBe(1);
    expect(daysSince(BIRTH, new Date(2024, 7, 7))).toBe(366);   // 2024 是閏年
    expect(daysSince(BIRTH, new Date(2020, 0, 1))).toBe(0);     // 不會變負數
  });
  it('withAlpha:#hex → rgba,非 hex 原樣', () => {
    expect(withAlpha('#d9788f', 0.5)).toBe('rgba(217, 120, 143, 0.5)');
    expect(withAlpha('rgb(1,2,3)', 0.5)).toBe('rgb(1,2,3)');
  });
});

describe('每月分組 monthlyCounts', () => {
  it('每個月都有格子、沒收錄的月是 0,累積逐月加總', () => {
    const r = monthlyCounts(ARTS, 202412, 202503);
    expect(r.labels).toEqual(['2024/12', '2025/01', '2025/02', '2025/03']);
    expect(r.counts).toEqual([1, 2, 0, 2]);
    expect(r.cumulative).toEqual([1, 3, 3, 5]);
  });
  it('起點之前收錄的算進累積起始值、終點之後與沒有 ck 的不計', () => {
    const r = monthlyCounts(ARTS, 202501, 202502);
    expect(r.counts).toEqual([2, 0]);
    expect(r.cumulative).toEqual([3, 3]);   // 2024/12 那篇算進起始值;2025/03 兩篇與 No.6 不計
  });
  it('預設從匯入月(2025/01)的下一個月起算,匯入批次只進累積起始值', () => {
    expect(IMPORT_YM).toBe(202501);
    expect(START_YM).toBe(202502);
    const r = monthlyCounts(ARTS, START_YM, 202503);
    expect(r.labels).toEqual(['2025/02', '2025/03']);
    expect(r.counts).toEqual([0, 2]);          // 2025/01 那兩篇不畫在趨勢線上
    expect(r.cumulative).toEqual([3, 5]);      // 但累積從 3 起算(2024/12 一篇 + 2025/01 兩篇),總數不變
  });
});

describe('排行', () => {
  it('標籤排行只算多選分面、篇數多→少、同數依標籤名,可限制名次', () => {
    const all = tagRanking(ARTS, FACETS);
    expect(all[0]).toEqual({ tag: '安/員', facet: 'CP配對', count: 4 });
    expect(all.slice(0, 3).map((t) => t.tag)).toEqual(['安/員', '甜文', '日常']);
    expect(all.slice(3).map((t) => t.tag).sort()).toEqual(['互攻', '員/安', '虐文'].sort());   // 同為 1 篇,順序依標籤名
    expect(all.find((t) => t.tag === '完結')).toBeUndefined();   // 單選分面不計
    expect(tagRanking(ARTS, FACETS, { top: 2 }).map((t) => t.tag)).toEqual(['安/員', '甜文']);
  });
  it('標籤排行可排除原文已刪', () => {
    const alive = tagRanking(ARTS, FACETS, { excludeDead: true });
    expect(alive.find((t) => t.tag === '甜文').count).toBe(2);        // No.5 已刪不算
    expect(alive.find((t) => t.tag === '互攻')).toBeUndefined();        // 只出現在已刪那篇
    expect(alive.find((t) => t.tag === '員/安')).toBeUndefined();
  });
  it('作者排行:作者與譯者都算、依 ID 歸戶並用目前顯示名、同一篇同一人只算一次', () => {
    const r = authorRanking(ARTS, PEOPLE);
    expect(r[0]).toEqual({ name: '甲(新名)', id: 'idA', count: 3 });
    expect(r.find((p) => p.name === '乙').count).toBe(2);
    expect(r.find((p) => p.name === '丙')).toEqual({ name: '丙', id: '', count: 1 });   // 沒 ID 退回名字
    expect(r.find((p) => p.name === '譯者丁').count).toBe(1);
    expect(r.find((p) => p.name === '')).toBeUndefined();                                 // 空作者不計
    expect(authorRanking(ARTS, PEOPLE, { top: 1 })).toHaveLength(1);
  });
  it('同一人同一篇掛作者又掛譯者只算一次', () => {
    const a = art(9, {}, { author: '甲', author_ids: ['idA'], translator: '甲', translator_ids: ['idA'] });
    expect(authorRanking([a], PEOPLE)[0].count).toBe(1);
  });
});

describe('比例與總覽', () => {
  it('deadRatio:已刪篇數與百分比(小數一位),空陣列不除以零', () => {
    expect(deadRatio(ARTS)).toEqual({ dead: 2, total: 6, pct: 33.3 });
    expect(deadRatio([])).toEqual({ dead: 0, total: 0, pct: 0 });
  });
  it('personCount / tagCount', () => {
    expect(personCount(ARTS)).toBe(4);          // idA、idB、丙(名字)、idD
    expect(tagCount(ARTS, FACETS)).toBe(6);
  });
  it('overview 彙整五個數字', () => {
    const o = overview({ articles: ARTS, facets: FACETS, people: PEOPLE }, new Date(2023, 7, 17));
    expect(o).toEqual({ total: 6, people: 4, tags: 6, dead: 2, deadPct: 33.3, days: 10 });
  });
});

describe('散佈與年度', () => {
  it('scatterPoints:x 觀測、y 愛心;已刪與沒計數的不畫;沒有 counts 回空', () => {
    const counts = { '1': [5, 30], '3': [9, 9], '4': ['2', '7'], '6': 'bad' };
    expect(scatterPoints(ARTS, counts)).toEqual([
      { x: 30, y: 5, no: '1', name: '文 1' },
      { x: 7, y: 2, no: '4', name: '文 4' },
    ]);
    expect(scatterPoints(ARTS, null)).toEqual([]);
  });
  it('yearlyDead:按收錄年份分組、年份小→大、沒有 ck 的不計', () => {
    expect(yearlyDead(ARTS)).toEqual([
      { year: 2024, total: 1, dead: 0, alive: 1 },
      { year: 2025, total: 4, dead: 2, alive: 2 },
    ]);
  });
});

describe('Chart.js 設定物件(純函式)', () => {
  const colors = { accent: '#d9788f', be: '#5b7fb5', he: '#3f9d6b', exc: '#c0563f', oe: '#c79a3e', purp: '#8a5fc0', ink: '#2c2a26', muted: '#8a8377', line: '#e6e0d5', card: '#fff' };
  it('每月趨勢:兩條線、累積在右軸', () => {
    const cfg = monthlyChartConfig(monthlyCounts(ARTS, 202412, 202503), colors);
    expect(cfg.type).toBe('line');
    expect(cfg.data.datasets.map((d) => d.yAxisID)).toEqual(['y', 'y1']);
    expect(cfg.options.scales.y1.position).toBe('right');
    expect(cfg.data.datasets[1].data).toEqual([1, 3, 3, 5]);
  });
  it('排行:橫向長條、有 onClick 才掛點擊', () => {
    const cfg = rankingChartConfig(['a', 'b'], [2, 1], colors);
    expect(cfg.options.indexAxis).toBe('y');
    expect(cfg.options.onClick).toBeUndefined();
    let hit = null;
    const c2 = rankingChartConfig(['a', 'b'], [2, 1], colors, { onClick: (i) => { hit = i; } });
    c2.options.onClick({}, [{ index: 1 }]);
    expect(hit).toBe(1);
  });
  it('散佈:tooltip 標題含編號與篇名、點擊回傳該點', () => {
    const pts = scatterPoints(ARTS, { '1': [5, 30] });
    let got = null;
    const cfg = scatterChartConfig(pts, colors, { onClick: (p) => { got = p; } });
    expect(cfg.options.plugins.tooltip.callbacks.title([{ raw: pts[0] }])).toEqual(['#1 文 1']);
    expect(cfg.options.plugins.tooltip.callbacks.label({ raw: pts[0] })).toBe('🔭 觀測 30・❤️ 愛心 5');
    cfg.options.onClick({}, [{ index: 0 }]);
    expect(got.no).toBe('1');
  });
  it('年度:堆疊、頁尾顯示總數與比例', () => {
    const rows = yearlyDead(ARTS);
    const cfg = yearlyChartConfig(rows, colors);
    expect(cfg.options.scales.x.stacked && cfg.options.scales.y.stacked).toBe(true);
    expect(cfg.data.datasets.map((d) => d.label)).toEqual(['仍可閱讀', '原文已刪']);
    expect(cfg.options.plugins.tooltip.callbacks.footer([{ dataIndex: 1 }])).toBe('共 4 篇,已刪 50%');
  });
});
