// 站外服務(Val Town)的網路呼叫,只包 fetch、不碰 DOM。端點由 index.html 的 window.AZ_CONFIG 提供:
//   REACT_API  公開愛心數 / 觀測數(GET 讀全部、POST {no,type} 記一筆;留空 = 整個功能略過)
//   REPORT_API 回報連結失效(POST {no,title,reason})
//   STATS_API  即時瀏覽人次統計(GET)
const cfg = (typeof window !== 'undefined' && window.AZ_CONFIG) || {};
export const REACT_API = cfg.REACT_API || '';
export const REPORT_API = cfg.REPORT_API || '';
export const STATS_API = cfg.STATS_API || '';

/** 記一筆愛心/取消/觀測;回 Promise<boolean>(失敗不丟錯)。 */
export function postReaction(no, type) {
  return fetch(REACT_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ no, type }) })
    .then((r) => r.ok).catch(() => false);
}

/** 讀取全部計數 {編號: [愛心, 觀測]};不是物件(或失敗)回 null。 */
export function fetchCounts() {
  return fetch(REACT_API, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((j) => {
    if (!j || typeof j !== 'object' || Array.isArray(j)) return null;
    return j;
  }).catch(() => null);
}

/** 送出連結回報;回 Promise<json | null>,網路錯誤會 reject(呼叫端顯示失敗)。 */
export function postReport(no, title, reason) {
  return fetch(REPORT_API, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ no, title, reason }) })
    .then((r) => (r.ok ? r.json() : null));
}

/** 即時統計;格式不對或失敗回 null。 */
export function fetchLiveStats() {
  return fetch(STATS_API, { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((j) => {
    if (j && !j.error && typeof j.total === 'number') return j;
    return null;
  }).catch(() => null);
}
