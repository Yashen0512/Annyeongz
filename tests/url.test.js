import { describe, it, expect } from 'vitest';
import { encodeShare, buildShareURL, parseShareHash, HASH_PREFIX } from '../src/url.js';

const BASE = 'https://yashen0512.github.io/Annyeongz/';

describe('篩選狀態 ⇄ 網址參數', () => {
  it('沒有任何條件 → 純網址(沒有 #f=)', () => {
    expect(encodeShare({})).toBe('');
    expect(encodeShare({ sel: {}, modes: {}, author: null, q: '   ', sort: 'old' })).toBe('');
    expect(buildShareURL({}, BASE)).toBe(BASE);
  });
  it('序列化後再解析回來等於原狀態', () => {
    const share = {
      sel: { 'CP配對': { '安/員': 'on', '互攻': 'exc' }, '氛圍': { '甜文': 'on', '日常': 'on' } },
      modes: { '氛圍': 'and' },
      author: '노네임(noname)',
      q: '穿越',
      sort: 'latest',
    };
    const url = buildShareURL(share, BASE);
    expect(url.startsWith(BASE + HASH_PREFIX)).toBe(true);
    const hash = url.slice(BASE.length);
    expect(parseShareHash(hash)).toEqual(share);
  });
  it('格式:#f= + encodeURIComponent(JSON),鍵名 s / m / a / q / sort', () => {
    const hash = encodeShare({ sel: { 'CP配對': { '安/員': 'on' } }, modes: { 'CP配對': 'and' }, author: 'A', q: ' x ', sort: 'new' });
    expect(JSON.parse(decodeURIComponent(hash.slice(3)))).toEqual({ s: { 'CP配對': { '安/員': 'on' } }, m: { 'CP配對': 'and' }, a: 'A', q: 'x', sort: 'new' });
  });
  it('預設排序 old 不寫進網址;解析時 sort / q 沒給就是 undefined(呼叫端不動原值)', () => {
    const hash = encodeShare({ sel: { '氛圍': { '甜文': 'on' } }, sort: 'old' });
    expect(hash).toBe('#f=' + encodeURIComponent('{"s":{"氛圍":{"甜文":"on"}}}'));
    expect(parseShareHash(hash)).toEqual({ sel: { '氛圍': { '甜文': 'on' } }, modes: {}, author: null, q: undefined, sort: undefined });
  });
  it('只有搜尋字或只有排序也能來回', () => {
    expect(parseShareHash(encodeShare({ q: 'abc' })).q).toBe('abc');
    expect(parseShareHash(encodeShare({ sort: 'views' })).sort).toBe('views');
  });
  it('不是 #f= 開頭、JSON 壞掉、非物件 → null', () => {
    expect(parseShareHash('')).toBeNull();
    expect(parseShareHash('#other')).toBeNull();
    expect(parseShareHash('#f=%7Bbroken')).toBeNull();
    expect(parseShareHash('#f=123')).toBeNull();
  });
  it('s / m 不是物件時當成空的', () => {
    expect(parseShareHash('#f=' + encodeURIComponent('{"s":"x","m":5,"a":""}'))).toEqual({ sel: {}, modes: {}, author: null, q: undefined, sort: undefined });
  });
});
