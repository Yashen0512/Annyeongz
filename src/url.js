// 篩選狀態 ⇄ 網址參數。
// 格式:<網址>#f=<encodeURIComponent(JSON)>,JSON 只放有設定的欄位:
//   s    標籤三態 {分面: {標籤: 'on' | 'exc'}}
//   m    任一/全部 {分面: 'and'}
//   a    作者/譯者專頁名字
//   q    搜尋字(未折算的原始輸入,去頭尾空白)
//   sort 排序(預設 old 不寫)
// 沒有任何條件時就是純網址(沒有 #f=)。
//
// 另外還有「作品分享網址」:<SITE_BASE>p/<No>/ 是 _build/build_pages.py 產出的靜態分享頁(社群預覽卡用),
// 它會導回首頁 ?p=<No>;首頁開站時讀到 p 參數就打開該篇詳情,再用 history.replaceState 把參數拿掉。

export const HASH_PREFIX = '#f=';
export const SITE_BASE = 'https://yashen0512.github.io/Annyeongz/';   // 站台正式網址(分享頁的 og:url 也用這個)
export const PAGE_PARAM = 'p';

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

/** 一篇作品的分享網址(靜態分享頁):https://yashen0512.github.io/Annyeongz/p/<No>/ */
export function articleShareURL(no, base = SITE_BASE) {
  return base + 'p/' + encodeURIComponent(String(no)) + '/';
}

/** 從 location.search 讀 ?p=<No>;沒有或空白回 null。 */
export function parseArticleParam(search) {
  const v = new URLSearchParams(search || '').get(PAGE_PARAM);
  const no = (v || '').trim();
  return no || null;
}

/** 把 ?p= 從網址拿掉(其他參數與 #hash 保留),回傳 history.replaceState 用的相對網址。 */
export function stripArticleParam(href) {
  const u = new URL(href);
  u.searchParams.delete(PAGE_PARAM);
  return u.pathname + u.search + u.hash;
}
