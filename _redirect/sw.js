// Annyeongz 平行宇宙舊網址(yashen0512.github.io/Annyeongz/)的 service worker「自毀版」——搬家後取代原本的 sw.js。
// 由 _cloudflare/build_redirect.py 複製到輸出資料夾,不要直接改輸出檔。
//
// 為什麼需要:原本的 sw.js 換頁時先拿快取,回訪的讀者會一直看到手機裡存的舊站、永遠走不到轉址頁。
// 讀者的瀏覽器下次來會發現 sw.js 變了 → 裝上這一版(立刻接手)→ 刪掉平行宇宙在這個網域的快取、註銷自己、
// 把開著的分頁重新載入;重新載入就不再被快取攔住,會拿到轉址頁 → 帶著書架去新網址。
//
// 注意:yashen0512.github.io 這個網域底下還有別的專案(例如 exam-board),快取是整個網域共用的,
//       所以只刪平行宇宙自己的(az- 開頭的 az-static-*/az-data,以及更早的 annyeongz-v*),別的一律不碰。
self.addEventListener('install', () => self.skipWaiting());

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => /^(az-|annyeongz)/.test(k)).map((k) => caches.delete(k)));
    } catch (err) { /* 刪不掉也繼續:下面註銷後快取就不會再被用到 */ }
    try { await self.registration.unregister(); } catch (err) {}
    try {
      const wins = await self.clients.matchAll({ type: 'window' });
      wins.forEach((c) => { try { c.navigate(c.url); } catch (err) {} });
    } catch (err) {}
  })());
});

// 被註銷前的這段時間,所有請求一律直接走網路(不攔)
