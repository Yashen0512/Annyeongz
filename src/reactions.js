// 公開愛心數 + 觀測數(存 Val Town,匿名只記數字)。
// 讀取失敗也只是不顯示數字,書架照常運作;已標「原文已刪」的文不計數。
import { KEYS, loadSet, saveSet, firstViewThisSession } from './storage.js';
import { REACT_API, postReaction, fetchCounts } from './api.js';

/**
 * @param {{favs:Set, deadNos:Set, onChange:()=>void}} opts
 *   favs     本機收藏集合(載入計數後會補送上線前就收藏、或上次沒送成功的愛心)
 *   deadNos  原文已刪的編號(不計數)
 *   onChange 計數變動後要重繪時呼叫
 */
export function createReactions({ favs, deadNos, onChange }) {
  const favSent = loadSet(KEYS.FAVS_SENT);   // 已計入公開愛心數的收藏(避免重複 +1)
  let counts = null;                          // {no:[愛心,觀測]};null = 尚未載入 / 載入失敗

  const canReact = (no) => !!REACT_API && !deadNos.has(no);
  function cnt(no, i) { return counts && counts[no] ? counts[no][i] : 0; }
  function bump(no, i, d) { if (!counts) return; const c = counts[no] || (counts[no] = [0, 0]); c[i] = Math.max(0, c[i] + d); }
  function likeNum(no) { const v = cnt(no, 0); return canReact(no) && v > 0 ? v : 0; }
  function viewNum(no) { return canReact(no) ? cnt(no, 1) : 0; }

  function reactLike(no) {
    favSent.add(no); saveSet(KEYS.FAVS_SENT, favSent); bump(no, 0, 1);
    postReaction(no, 'like').then((ok) => { if (!ok) { favSent.delete(no); saveSet(KEYS.FAVS_SENT, favSent); bump(no, 0, -1); } });  // 失敗就下次載入再補
  }
  /** 收藏切換後同步公開愛心數(adding = 這次是加入收藏)。 */
  function onFavChange(no, adding) {
    if (!canReact(no)) return;
    if (adding) { if (!favSent.has(no)) reactLike(no); }
    else if (favSent.has(no)) { favSent.delete(no); saveSet(KEYS.FAVS_SENT, favSent); bump(no, 0, -1); postReaction(no, 'unlike'); }
  }
  /** 從別台裝置匯入的收藏:那邊已經算過愛心了,這裡只標成「已計入」,不再 +1(loadCounts 的補算也會略過)。 */
  function markCounted(nos) {
    let changed = false;
    (nos || []).forEach((no) => { if (!favSent.has(no)) { favSent.add(no); changed = true; } });
    if (changed) saveSet(KEYS.FAVS_SENT, favSent);
  }
  /** 清除所有紀錄後:忘掉「已計入」清單(key 已由 storage.clearAllRecords 移除)。 */
  function forgetAll() { favSent.clear(); }
  /** 打開詳情時記一次觀測(同一分頁同一篇只算一次)。 */
  function markView(no) {
    if (!canReact(no)) return;
    if (!firstViewThisSession(no)) return;
    bump(no, 1, 1); postReaction(no, 'view');
  }
  function loadCounts() {
    if (!REACT_API) return;
    fetchCounts().then((j) => {
      if (!j) return;
      counts = j;
      // 補算:上線前就收藏、或上次沒送成功的(一次最多 40 篇,避免觸發頻率限制,剩下的下次再補)
      [...favs].filter((no) => !favSent.has(no) && canReact(no)).slice(0, 40).forEach(reactLike);
      onChange();
    });
  }
  return { canReact, cnt, likeNum, viewNum, onFavChange, markView, loadCounts, markCounted, forgetAll };
}
