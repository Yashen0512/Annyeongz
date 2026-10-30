// 排序:純函式,六種排序。不碰 DOM、不碰網路;愛心數/觀測數由呼叫端以函式傳入。
//
//   old     編號 小→大
//   new     編號 大→小
//   latest  🆕 最新收錄(建立時間 ck 新→舊,同時間再比編號大→小)
//   likes   ❤️ 愛心最多(同數再比編號大→小)
//   views   🔭 最多人觀測(同數再比編號大→小)
//   random  🌀 穿越蟲洞(隨機;傳入固定 seed 的亂數函式即可重現)
// 其他未知模式退回標題筆畫序(localeCompare zh-Hant),與原站行為相同。

export const SORT_MODES = ['old', 'new', 'latest', 'likes', 'views', 'random'];

/** 編號轉數字;非數字當 -1(排到最前/最後)。 */
export const noNum = (a) => { const v = parseInt(a.no, 10); return isNaN(v) ? -1 : v; };

/**
 * mulberry32:可指定 seed 的簡單亂數產生器,回傳 () => [0,1) 的函式(測試用固定 seed 可重現)。
 */
export function seededRandom(seed) {
  let t = seed >>> 0;
  return function () {
    t = (t + 0x6D2B79F5) >>> 0;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r = (r + Math.imul(r ^ (r >>> 7), 61 | r)) ^ r;
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

/** Fisher–Yates 洗牌(回傳新陣列)。 */
export function shuffle(list, rng = Math.random) {
  const s = list.slice();
  for (let i = s.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [s[i], s[j]] = [s[j], s[i]];
  }
  return s;
}

/** 穿越蟲洞按鈕用:從清單隨機挑一篇(空清單回 undefined)。 */
export function pickRandom(list, rng = Math.random) {
  if (!list || !list.length) return undefined;
  return list[Math.floor(rng() * list.length)];
}

/**
 * @param {Array} hits 文章陣列(不會被修改)
 * @param {string} mode SORT_MODES 之一
 * @param {{likeOf?:(no:string)=>number, viewOf?:(no:string)=>number, rng?:()=>number}} ctx
 */
export function sortArticles(hits, mode, ctx = {}) {
  const likeOf = ctx.likeOf || (() => 0), viewOf = ctx.viewOf || (() => 0), rng = ctx.rng || Math.random;
  const n = noNum;
  const s = hits.slice();
  if (mode === 'new') s.sort((a, b) => n(b) - n(a));
  else if (mode === 'old') s.sort((a, b) => n(a) - n(b));
  else if (mode === 'latest') s.sort((a, b) => ((b.ck || 0) - (a.ck || 0)) || (n(b) - n(a)));
  else if (mode === 'likes') s.sort((a, b) => (likeOf(b.no) - likeOf(a.no)) || (n(b) - n(a)));
  else if (mode === 'views') s.sort((a, b) => (viewOf(b.no) - viewOf(a.no)) || (n(b) - n(a)));
  else if (mode === 'random') return shuffle(s, rng);
  else s.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'zh-Hant'));
  return s;
}
