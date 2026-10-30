import { describe, it, expect } from 'vitest';
import { sortArticles, SORT_MODES, seededRandom, shuffle, pickRandom, noNum } from '../src/sort.js';
import { ARTICLES, art } from './fixtures.js';

const nos = (list) => list.map((a) => a.no);
const likes = { '1': 5, '2': 9, '3': 9, '4': 0, '5': 2 }, views = { '1': 30, '2': 3, '3': 3, '4': 50, '5': 0 };
const ctx = { likeOf: (no) => likes[no] || 0, viewOf: (no) => views[no] || 0 };

describe('六種排序', () => {
  it('定義六種模式', () => expect(SORT_MODES).toEqual(['old', 'new', 'latest', 'likes', 'views', 'random']));
  it('old:編號 小→大', () => expect(nos(sortArticles(ARTICLES.slice().reverse(), 'old'))).toEqual(['1', '2', '3', '4', '5']));
  it('new:編號 大→小', () => expect(nos(sortArticles(ARTICLES, 'new'))).toEqual(['5', '4', '3', '2', '1']));
  it('latest:建立時間新→舊,同時間再比編號大→小', () => {
    expect(nos(sortArticles(ARTICLES, 'latest'))).toEqual(['4', '2', '3', '1', '5']);
  });
  it('likes:愛心多→少,同數再比編號大→小', () => {
    expect(nos(sortArticles(ARTICLES, 'likes', ctx))).toEqual(['3', '2', '1', '5', '4']);
  });
  it('views:觀測多→少,同數再比編號大→小', () => {
    expect(nos(sortArticles(ARTICLES, 'views', ctx))).toEqual(['4', '1', '3', '2', '5']);
  });
  it('random(穿越蟲洞):固定 seed 可重現、不同 seed 不同、元素不多不少', () => {
    const a = nos(sortArticles(ARTICLES, 'random', { rng: seededRandom(42) }));
    const b = nos(sortArticles(ARTICLES, 'random', { rng: seededRandom(42) }));
    const c = nos(sortArticles(ARTICLES, 'random', { rng: seededRandom(7) }));
    expect(a).toEqual(b);
    expect(a).toEqual(['1', '5', '3', '2', '4']);   // seed 42 的固定結果
    expect(c).toEqual(['4', '2', '3', '5', '1']);   // seed 7 的固定結果
    expect(a.slice().sort()).toEqual(['1', '2', '3', '4', '5']);
  });
  it('沒有愛心 / 觀測資料時退回編號大→小', () => {
    expect(nos(sortArticles(ARTICLES, 'likes'))).toEqual(['5', '4', '3', '2', '1']);
    expect(nos(sortArticles(ARTICLES, 'views'))).toEqual(['5', '4', '3', '2', '1']);
  });
  it('不修改原陣列', () => {
    const src = ARTICLES.slice(); sortArticles(src, 'new'); sortArticles(src, 'random', { rng: seededRandom(1) });
    expect(nos(src)).toEqual(['1', '2', '3', '4', '5']);
  });
  it('未知模式退回標題排序(與原站相同)', () => {
    const list = [art(1, {}, { name: '乙' }), art(2, {}, { name: '甲' })];
    expect(sortArticles(list, 'nope').map((a) => a.name)).toEqual(['甲', '乙'].sort((x, y) => x.localeCompare(y, 'zh-Hant')));
  });
  it('非數字編號當 -1', () => {
    expect(noNum({ no: 'abc' })).toBe(-1); expect(noNum({ no: '12' })).toBe(12);
  });
});

describe('隨機工具', () => {
  it('seededRandom 回 [0,1) 且可重現', () => {
    const r1 = seededRandom(123), r2 = seededRandom(123);
    for (let i = 0; i < 20; i++) { const v = r1(); expect(v).toBeGreaterThanOrEqual(0); expect(v).toBeLessThan(1); expect(v).toBe(r2()); }
  });
  it('pickRandom:固定 seed 挑同一篇;空清單回 undefined', () => {
    expect(pickRandom(ARTICLES, seededRandom(3))).toBe(pickRandom(ARTICLES, seededRandom(3)));
    expect(pickRandom([], seededRandom(3))).toBeUndefined();
    expect(pickRandom(ARTICLES, () => 0).no).toBe('1');
    expect(pickRandom(ARTICLES, () => 0.999).no).toBe('5');
  });
  it('shuffle 保留全部元素', () => {
    expect(shuffle([1, 2, 3, 4], seededRandom(9)).sort()).toEqual([1, 2, 3, 4]);
  });
});
