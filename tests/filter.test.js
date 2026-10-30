import { describe, it, expect } from 'vitest';
import { passes, filterArticles, cycleTag, toggleMode, removeTag, clearSelection, selectionChips, authorWorks, matchesAuthor } from '../src/filter.js';
import { makePersonLookup, personRefs } from '../src/data.js';
import { ARTICLES, art } from './fixtures.js';

const nos = (list) => list.map((a) => a.no);

describe('標籤三態與同區 / 跨區', () => {
  it('同區選兩個標籤 → OR(任一)', () => {
    const sel = { 'CP配對': { '安/員': 'on', '員/安': 'on' } };
    expect(nos(filterArticles(ARTICLES, { sel }))).toEqual(['1', '2', '3']);
  });
  it('兩個區各選一個 → AND(同時)', () => {
    const sel = { 'CP配對': { '安/員': 'on' }, '氛圍': { '甜文': 'on' } };
    expect(nos(filterArticles(ARTICLES, { sel }))).toEqual(['1']);
  });
  it('點擊循環:未選 → 包含 → 排除 → 取消(第二次點擊變排除、第三次取消)', () => {
    const sel = {};
    expect(cycleTag(sel, 'CP配對', '安/員')).toBe('on');
    expect(cycleTag(sel, 'CP配對', '安/員')).toBe('exc');
    expect(sel['CP配對']['安/員']).toBe('exc');
    expect(cycleTag(sel, 'CP配對', '安/員')).toBeUndefined();
    expect(sel['CP配對']).toEqual({});
  });
  it('排除:有該標籤的文一律不顯示', () => {
    const sel = { 'CP配對': { '安/員': 'exc' } };
    expect(nos(filterArticles(ARTICLES, { sel }))).toEqual(['2', '4', '5']);
  });
  it('區標題切成「全部」後同區變 AND', () => {
    const sel = { 'CP配對': { '安/員': 'on', '員/安': 'on' } };
    const modes = {};
    expect(toggleMode(modes, 'CP配對')).toBe(true);
    expect(nos(filterArticles(ARTICLES, { sel, modes }))).toEqual(['3']);
    expect(toggleMode(modes, 'CP配對')).toBe(false);   // 再切回任一
    expect(modes).toEqual({});
    expect(nos(filterArticles(ARTICLES, { sel, modes }))).toEqual(['1', '2', '3']);
  });
  it('「全部」只影響該區,其他區仍是 OR', () => {
    const sel = { '氛圍': { '甜文': 'on', '日常': 'on' }, 'CP配對': { '安/員': 'on', '員/安': 'on' } };
    const modes = { '氛圍': 'and' };
    expect(nos(filterArticles(ARTICLES, { sel, modes }))).toEqual(['2']);
  });
  it('排除與包含同時存在:先排除再看包含', () => {
    const sel = { 'CP配對': { '安/員': 'on', '員/安': 'exc' } };
    expect(nos(filterArticles(ARTICLES, { sel }))).toEqual(['1']);   // 3 同時有兩個,被排除
    const sel2 = { '氛圍': { '甜文': 'on' }, 'CP配對': { '安/員': 'exc' } };
    expect(nos(filterArticles(ARTICLES, { sel: sel2 }))).toEqual(['2', '5']);
  });
  it('沒有任何條件 → 全部通過', () => {
    expect(nos(filterArticles(ARTICLES, {}))).toEqual(['1', '2', '3', '4', '5']);
    expect(passes(ARTICLES[0])).toBe(true);
  });
  it('移除單一條件、清除全部、條件列 chips', () => {
    const sel = { 'CP配對': { '安/員': 'on', '互攻': 'exc' }, '氛圍': { '甜文': 'on' } }, modes = { '氛圍': 'and' };
    expect(selectionChips(sel)).toEqual([
      { key: 'CP配對', val: '安/員', exc: false }, { key: 'CP配對', val: '互攻', exc: true }, { key: '氛圍', val: '甜文', exc: false }]);
    removeTag(sel, '氛圍', '甜文');
    expect(sel).toEqual({ 'CP配對': { '安/員': 'on', '互攻': 'exc' } });
    clearSelection(sel, modes);
    expect(sel).toEqual({}); expect(modes).toEqual({});
  });
});

describe('隱藏已讀 / 隱藏原文已刪 與篩選疊加', () => {
  const readSet = new Set(['1', '2']);
  it('隱藏已讀', () => {
    expect(nos(filterArticles(ARTICLES, { hideRead: true, readSet }))).toEqual(['3', '4', '5']);
  });
  it('隱藏原文已刪', () => {
    expect(nos(filterArticles(ARTICLES, { hideDead: true }))).toEqual(['1', '2', '4', '5']);
  });
  it('兩者 + 標籤篩選同時疊加', () => {
    const sel = { 'CP配對': { '安/員': 'on', '員/安': 'on' } };   // 1,2,3
    expect(nos(filterArticles(ARTICLES, { sel, hideRead: true, readSet, hideDead: true }))).toEqual([]);
    expect(nos(filterArticles(ARTICLES, { sel, hideRead: true, readSet }))).toEqual(['3']);
    expect(nos(filterArticles(ARTICLES, { sel, hideDead: true }))).toEqual(['1', '2']);
  });
  it('書架模式:只顯示該分頁的集合;在「已讀」分頁時忽略隱藏已讀', () => {
    expect(nos(filterArticles(ARTICLES, { shelf: new Set(['2', '4']), shelfTab: 'fav' }))).toEqual(['2', '4']);
    expect(nos(filterArticles(ARTICLES, { shelf: new Set(['2', '4']), shelfTab: 'fav', hideRead: true, readSet }))).toEqual(['4']);
    expect(nos(filterArticles(ARTICLES, { shelf: readSet, shelfTab: 'read', hideRead: true, readSet }))).toEqual(['1', '2']);
  });
});

describe('搜尋與作者', () => {
  it('搜尋字比對折算後的 _s(呼叫端已做簡繁折算)', () => {
    expect(nos(filterArticles(ARTICLES, { term: '时间' }))).toEqual(['5']);
    expect(nos(filterArticles(ARTICLES, { term: '文 1' }))).toEqual(['1']);
    expect(nos(filterArticles(ARTICLES, { term: '' }))).toHaveLength(5);
  });
  it('作者 / 譯者專頁:名字須完全相同', () => {
    expect(nos(filterArticles(ARTICLES, { author: '作者B' }))).toEqual(['2']);
    expect(nos(filterArticles(ARTICLES, { author: '譯者C' }))).toEqual(['4']);
    expect(nos(authorWorks(ARTICLES, '作者A'))).toEqual(['1', '3', '4', '5']);
    expect(nos(filterArticles(ARTICLES, { author: '作者' }))).toEqual([]);
  });
});

describe('作者 ID 對應(author_ids / people 以 Notion 作者頁 ID 為鍵)', () => {
  const ID_A = 'a'.repeat(32), ID_B = 'b'.repeat(32);
  const people = { [ID_A]: { name: '新名字', urls: {}, aliases: ['舊名字'], dead: false }, [ID_B]: { name: '作者B', urls: {}, aliases: [], dead: true } };
  const lookup = makePersonLookup(people);
  const withId = art(9, {}, { author: '新名字', author_ids: [ID_A] });
  const renamed = art(10, {}, { author: '舊名字', author_ids: [ID_A] });   // 建檔時叫舊名字,同一個作者頁
  const noId = art(11, {}, { author: '舊名字' });                            // 舊資料沒有 ID
  it('personRefs 把名字與 ID 一一對應', () => {
    expect(personRefs(withId)).toEqual({ authors: [{ name: '新名字', id: ID_A }], translators: [] });
    expect(personRefs(art(12, {}, { author: '甲、乙', author_ids: [ID_A], translator: '丙', translator_ids: [ID_B] })))
      .toEqual({ authors: [{ name: '甲', id: ID_A }, { name: '乙', id: '' }], translators: [{ name: '丙', id: ID_B }] });
  });
  it('lookup:名字與曾用名都能對到同一個 ID', () => {
    expect(lookup.idOf('新名字')).toBe(ID_A); expect(lookup.idOf('舊名字')).toBe(ID_A); expect(lookup.idOf('沒這人')).toBeNull();
    expect(lookup.find('任何名字', ID_B).name).toBe('作者B');
    expect(lookup.find('舊名字').name).toBe('新名字');
  });
  it('作者專頁:同時比對目前名字與曾用名,透過 ID 對應', () => {
    expect(nos(filterArticles([withId, renamed, noId, ARTICLES[0]], { author: '新名字', lookup }))).toEqual(['9', '10']);
    expect(nos(filterArticles([withId, renamed, noId, ARTICLES[0]], { author: '舊名字', lookup }))).toEqual(['9', '10', '11']);
    expect(matchesAuthor(noId, '新名字', lookup)).toBe(false);   // 沒 ID 又名字不同 → 對不到
    expect(matchesAuthor(noId, '舊名字')).toBe(true);           // 沒 lookup 時只比名字字串
    expect(nos(authorWorks([withId, renamed], '新名字', lookup))).toEqual(['9', '10']);
  });
});
