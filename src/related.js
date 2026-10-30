// 「類似的文」:多訊號相似度(內容標籤最重 + 同作者 + 同結局/篇幅/類型),純函式。
import { sg, persons } from './data.js';

export const REL_FACETS = ['CP配對', '情感梗', '背景設定', '類型世界觀', '題材梗'];   // 內容面

export function contentTags(a) {
  const out = [];
  REL_FACETS.forEach((f) => { ((a.tags && a.tags[f]) || []).forEach((t) => out.push(t)); });
  return out;
}

/** 回傳與 a 最相似的 n 篇(分數高→低,同分編號大→小)。 */
export function relatedArticles(a, articles, n) {
  const mine = new Set(contentTags(a)), pa = new Set(persons(a));
  const ae = sg(a, '結局'), al = sg(a, '文章篇幅'), at = sg(a, '文章類型');
  const scored = [];
  for (const b of articles) {
    if (b.no === a.no) continue;
    let s = 0;
    for (const t of contentTags(b)) if (mine.has(t)) s += 4;      // 每個共同內容標籤 +4(最關鍵)
    if (persons(b).some((p) => pa.has(p))) s += 3;                // 同作者/譯者 +3
    if (ae && ae === sg(b, '結局')) s += 1;
    if (al && al === sg(b, '文章篇幅')) s += 1;
    if (at && at === sg(b, '文章類型')) s += 0.5;
    if (s > 0) scored.push([s, b]);
  }
  scored.sort((x, y) => y[0] - x[0] || (parseInt(y[1].no) || 0) - (parseInt(x[1].no) || 0));
  return scored.slice(0, n).map((x) => x[1]);
}
