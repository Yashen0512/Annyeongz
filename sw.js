// Annyeongz PWA service worker(樣板:build_site.py 會把 20261030-2129 換成本次建置的 synced 時間戳,輸出成 sw.js;
// 不要手改 sw.js、也不要手寫版本號)。
//
// 快取策略:
//   靜態資源(index.html、CSS、JS、圖示、WebP 橫幅、manifest) cache-first;快取名帶 VERSION,新版本上線 → 安裝新快取、啟用時清掉舊版。
//   資料檔 data.json(其他 .json 如 reactions_backup 亦同)  stale-while-revalidate:先回快取讓頁面秒開,背景抓新版寫回快取;
//                                                           內容有變就 postMessage {type:'data-updated'} 給所有分頁,頁面顯示「有新收錄」提示條。
//   跨網域請求(Postype / Lofter / AO3 / AFF 等閱讀連結、Val Town 計數、GoatCounter) 一律不攔、不快取。
const VERSION = '20261030-2129';
const STATIC_CACHE = 'az-static-' + VERSION;
const DATA_CACHE = 'az-data';           // 資料快取不分版(靠 stale-while-revalidate 自己換新)
const DATA_FILE = 'data.json';
const PRECACHE = [
  './', './index.html', './manifest.webmanifest',
  './styles/base.css', './styles/panel.css', './styles/main.css', './styles/modal.css', './styles/responsive.css', './styles/intro.css',
  './src/intro.js', './src/boot.js', './src/pwa.js', './src/main.js', './src/data.js', './src/filter.js', './src/sort.js',
  './src/storage.js', './src/url.js', './src/render.js', './src/related.js', './src/reactions.js', './src/api.js',
  './assets/icons/icon-192.png', './assets/icons/icon-512.png', './assets/icons/icon-maskable-512.png',
  './assets/banner.webp', './assets/banner-1200.webp', './assets/banner-mobile.webp',
  // 統計星圖
  './stats.html', './styles/stats.css', './src/stats.js', './src/stats_page.js', './vendor/chart.umd.js',
  // 書架匯出 / 匯入
  './vendor/lz-string.min.js', './vendor/qrcode.js',
];

self.addEventListener('install', (e) => {
  e.waitUntil((async () => {
    const c = await caches.open(STATIC_CACHE);
    await c.addAll(PRECACHE);
    // 資料也先抓一份進快取,第一次安裝後就能離線看;失敗(離線中安裝)不影響安裝
    try { await (await caches.open(DATA_CACHE)).add(DATA_FILE); } catch (err) { /* 下次 fetch 再補 */ }
  })());
  // 不自動 skipWaiting:由頁面在使用者點「重新整理」時送 {type:'skipWaiting'},避免正在看的分頁被換掉快取
});

self.addEventListener('activate', (e) => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== STATIC_CACHE && k !== DATA_CACHE).map((k) => caches.delete(k)));   // 舊版靜態快取與舊版 annyeongz-v* 都清掉
    await self.clients.claim();
  })());
});

self.addEventListener('message', (e) => {
  if (e.data && e.data.type === 'skipWaiting') self.skipWaiting();
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          // 外部連結與第三方服務:不攔、不快取
  if (url.pathname.endsWith('.json')) { e.respondWith(staleWhileRevalidate(e, req, url.pathname.endsWith('/' + DATA_FILE))); return; }   // data.json 與 reactions_backup.json
  if (url.pathname.includes('/p/')) return;                   // 分享頁 p/<No>/ 只是導回首頁,不佔快取
  e.respondWith(cacheFirst(req));
});

/** 靜態資源:有快取就用,沒有才上網並存進本版快取;離線且是頁面導覽時退回快取的 index.html。 */
async function cacheFirst(req) {
  const isNav = req.mode === 'navigate';
  const cached = await caches.match(req, { ignoreSearch: isNav });
  if (cached) return cached;
  try {
    const res = await fetch(req);
    if (res.ok && res.type === 'basic') {
      const c = await caches.open(STATIC_CACHE);
      c.put(req, res.clone());
    }
    return res;
  } catch (err) {
    if (isNav) { const idx = await caches.match('./index.html'); if (idx) return idx; }
    return new Response('', { status: 504, statusText: 'offline' });
  }
}

/** data.json(與其他 .json):先回快取,背景更新;notify = true 且更新後內容不同就通知頁面。沒有快取時直接等網路。 */
async function staleWhileRevalidate(e, req, notify) {
  const cache = await caches.open(DATA_CACHE);
  const cached = await cache.match(req, { ignoreSearch: true });
  const snapshot = cached ? cached.clone() : null;   // 比對用的副本要先留著:cached 回給頁面後 body 就被讀走,之後再 clone 會丟錯
  // 背景更新走 cache:'no-cache':一定向伺服器重新驗證(有 ETag / Last-Modified 時是便宜的 304),
  // 不然會拿到瀏覽器 HTTP 快取裡的舊檔(GitHub Pages 的 max-age=600 內),永遠偵測不到新收錄
  const update = fetch(req.url, { cache: 'no-cache', credentials: 'same-origin' }).then(async (res) => {
    if (!res || !res.ok) return res;
    const fresh = res.clone();
    const differs = snapshot ? await changed(snapshot, res.clone()) : false;
    await cache.put(req, fresh);
    if (differs && notify) await notifyClients({ type: 'data-updated', version: VERSION });
    return res;
  }).catch((err) => { console.warn('[sw] data.json 背景更新失敗', err); return null; });
  if (cached) { e.waitUntil(update); return cached; }
  const res = await update;
  return res || new Response('{}', { status: 504, statusText: 'offline', headers: { 'Content-Type': 'application/json' } });
}

/** 兩份回應內容是否不同:優先比 ETag / Last-Modified(GitHub Pages 兩者都有),沒有才比內文。 */
async function changed(a, b) {
  const tag = (r) => r.headers.get('etag') || r.headers.get('last-modified') || '';
  if (tag(a) && tag(b)) return tag(a) !== tag(b);
  const [x, y] = await Promise.all([a.text(), b.text()]);
  return x !== y;
}

async function notifyClients(msg) {
  const cs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  cs.forEach((c) => c.postMessage(msg));
}
