// 啟動:先抓 data.json(精簡格式;由 service worker 以 stale-while-revalidate 供應,回訪秒開),
// 放到 window.DATA 之後再動態載入 main.js。index.html 因此不再內嵌 1MB 多的資料,首次繪製不用等資料下載完。
// main.js / data.js 仍從 window.DATA 讀(loadData 會先 expandData 還原),所以其餘模組不用知道資料是怎麼來的。
import { initPWA } from './pwa.js';
import { fetchData } from './data.js';

// 捲動位置由 main.js 自己還原(連同已載入的張數),瀏覽器的自動還原會跟分批渲染打架
if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

function showError(msg) {
  document.body.classList.remove('loading');
  const el = document.getElementById('list');
  if (el) el.innerHTML = `<div class="empty">📡 星圖載入失敗<br><span>${msg}</span><br><button class="ctl" onclick="location.reload()">重新整理</button></div>`;
}

/** 等首屏(橫幅)畫出來再抓資料:半 MB 的 data.json 不跟樣式、橫幅搶頻寬,首次繪製與 LCP 先完成;橫幅載不到或太慢最多等 800ms。 */
function afterFirstPaint() {
  return new Promise((resolve) => {
    const img = document.querySelector('#banner img');
    let done = false;
    const go = () => { if (done) return; done = true; requestAnimationFrame(() => requestAnimationFrame(resolve)); };   // 多等一幀確保已經畫到螢幕
    if (!img || img.complete) go();
    else { img.addEventListener('load', go, { once: true }); img.addEventListener('error', go, { once: true }); }
    setTimeout(go, 800);
  });
}

afterFirstPaint()
  .then(() => fetchData())
  .then((j) => { window.DATA = j; return import('./main.js'); })
  .catch((e) => showError((e && e.message) || '請檢查網路後再試'));

initPWA();
