// 篩選狀態 ⇄ 網址參數。
// 格式:<網址>#f=<encodeURIComponent(JSON)>,JSON 只放有設定的欄位:
//   s    標籤三態 {分面: {標籤: 'on' | 'exc'}}
//   m    任一/全部 {分面: 'and'}
//   a    作者/譯者專頁名字
//   q    搜尋字(未折算的原始輸入,去頭尾空白)
//   sort 排序(預設 old 不寫)
// 沒有任何條件時就是純網址(沒有 #f=)。

export const HASH_PREFIX = '#f=';

/**
 * 把篩選狀態壓成 hash 片段('#f=...');沒有任何條件回空字串。
 * @param {{sel?:object, modes?:object, author?:string|null, q?:string, sort?:string}} share
 */
export function encodeShare(share = {}) {
  const o = {};
  if (share.sel && Object.keys(share.sel).length) o.s = share.sel;
  if (share.modes && Object.keys(share.modes).length) o.m = share.modes;
  if (share.author) o.a = share.author;
  const q = (share.q || '').trim();
  if (q) o.q = q;
  if (share.sort && share.sort !== 'old') o.sort = share.sort;
  return Object.keys(o).length ? HASH_PREFIX + encodeURIComponent(JSON.stringify(o)) : '';
}

/** 完整分享網址:base(origin + pathname)+ hash。 */
export function buildShareURL(share, base) {
  return base + encodeShare(share);
}

/**
 * 解析 hash。不是 #f= 開頭或 JSON 壞掉回 null(呼叫端維持原狀);
 * 否則回 { sel, modes, author, q, sort }:q / sort 沒給時為 undefined(呼叫端不動原值)。
 */
export function parseShareHash(hash) {
  if (!hash || !hash.startsWith(HASH_PREFIX)) return null;
  let o;
  try { o = JSON.parse(decodeURIComponent(hash.slice(HASH_PREFIX.length))); } catch (e) { return null; }
  if (!o || typeof o !== 'object') return null;
  return {
    sel: (o.s && typeof o.s === 'object') ? o.s : {},
    modes: (o.m && typeof o.m === 'object') ? o.m : {},
    author: o.a || null,
    q: o.q,
    sort: o.sort,
  };
}
