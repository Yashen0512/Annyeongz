// 「類似的文」:多訊號相似度,純函式(不碰 DOM)。2026/11/07 改版:
//   - 內容標籤依「稀有度」給分(IDF 式):共同標籤分數 = 2 + log2(全庫篇數 / 有該標籤的篇數),上限 8。
//     「校園」「現實向」幾百篇都有 → 約 3 分;「破鏡重圓」約 5 分;「哨嚮」「九號房設定」「朝鮮日據背景」這種幾篇才有的接近 8 分。
//   - CP 配對衝突扣分:兩篇都有標 CP、完全沒交集、也都沒有「互攻」→ −4(讀者最在意的一項,不該只是眾多標籤之一)。
//   - 氛圍納入但權重低:每個共同氛圍 +1.5、最多算 2 個(只負責在內容相近時排序,不負責找文)。
//   - 同作者 / 譯者 +3,但結果裡同一人最多占 2 篇(避免 6 篇全是同一位作者,推薦才有探索性)。
//   - 同結局 +1、同篇幅 +0.5、同類型 +0.5(類型九成是都市現實,資訊量低)。
//   - 排除「原文已刪」的文;總分 ≤ 0 不列;同分先比愛心數(有給 likeOf 時),再比編號大(新)→小。
import { sg, persons } from './data.js';

export const REL_FACETS = ['CP配對', '情感梗', '背景設定', '類型世界觀', '題材梗'];   // 內容面(參與稀有度計分)
export const MOOD_FACET = '氛圍';
const CP_FACET = 'CP配對', CP_ANY = '互攻';
const W = { tagBase: 2, tagMax: 8, cpConflict: -4, mood: 1.5, moodMax: 2, person: 3, ending: 1, length: 0.5, type: 0.5, perPersonCap: 2 };

/** 內容標籤(facet|值,避免不同分面同名字串相撞)。 */
export function contentTags(a) {
  const out = [];
  REL_FACETS.forEach((f) => { ((a.tags && a.tags[f]) || []).forEach((t) => out.push(f + '|' + t)); });
  return out;
}

/** 每個內容標籤的分數(依稀有度),對同一份 articles 只算一次。 */
const _weights = new WeakMap();
export function tagWeights(articles) {
  let w = _weights.get(articles);
  if (w) return w;
  const cnt = new Map();
  for (const a of articles) for (const t of contentTags(a)) cnt.set(t, (cnt.get(t) || 0) + 1);
  const N = Math.max(1, articles.length);
  w = new Map();
  cnt.forEach((c, t) => w.set(t, Math.min(W.tagMax, W.tagBase + Math.log2(N / c))));
  _weights.set(articles, w);
  return w;
}

/** 兩篇 CP 是否衝突:都有標、沒交集、都沒「互攻」。 */
export function cpConflict(a, b) {
  const x = (a.tags && a.tags[CP_FACET]) || [], y = (b.tags && b.tags[CP_FACET]) || [];
  if (!x.length || !y.length) return false;
  if (x.includes(CP_ANY) || y.includes(CP_ANY)) return false;
  return !x.some((v) => y.includes(v));
}

/** a 與 b 的相似分數(給測試 / 除錯用;relatedArticles 內部也用它)。 */
export function similarity(a, b, weights) {
  const mine = new Set(contentTags(a));
  let s = 0;
  for (const t of contentTags(b)) if (mine.has(t)) s += weights.get(t) || W.tagBase;
  if (cpConflict(a, b)) s += W.cpConflict;
  const ma = (a.tags && a.tags[MOOD_FACET]) || [], mb = (b.tags && b.tags[MOOD_FACET]) || [];
  let moods = 0;
  for (const m of mb) if (ma.includes(m) && moods < W.moodMax) { moods++; s += W.mood; }
  const pa = persons(a);
  if (pa.length && persons(b).some((p) => pa.includes(p))) s += W.person;
  const ae = sg(a, '結局'), al = sg(a, '文章篇幅'), at = sg(a, '文章類型');
  if (ae && ae === sg(b, '結局')) s += W.ending;
  if (al && al === sg(b, '文章篇幅')) s += W.length;
  if (at && at === sg(b, '文章類型')) s += W.type;
  return s;
}

/**
 * 回傳與 a 最相似的 n 篇。
 * @param {object} a 目前這篇  @param {object[]} articles 全庫  @param {number} n 篇數
 * @param {{likeOf?: (no:string)=>number}} [opts] likeOf:取愛心數,同分時多的排前
 */
export function relatedArticles(a, articles, n, opts = {}) {
  const weights = tagWeights(articles);
  const likeOf = opts.likeOf || (() => 0);
  const scored = [];
  for (const b of articles) {
    if (b.no === a.no || b.dead) continue;
    const s = similarity(a, b, weights);
    if (s > 0) scored.push([s, b]);
  }
  scored.sort((x, y) => y[0] - x[0] || likeOf(y[1].no) - likeOf(x[1].no) || (parseInt(y[1].no) || 0) - (parseInt(x[1].no) || 0));
  // 同一位作者 / 譯者最多占 perPersonCap 篇
  const used = new Map(), out = [];
  for (const [, b] of scored) {
    if (out.length >= n) break;
    const ps = persons(b);
    if (ps.some((p) => (used.get(p) || 0) >= W.perPersonCap)) continue;
    ps.forEach((p) => used.set(p, (used.get(p) || 0) + 1));
    out.push(b);
  }
  return out;
}
