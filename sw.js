// Annyeongz PWA service worker — network-first(更新優先),離線時用快取
const CACHE = 'annyeongz-v5';
const ASSETS = ['./', './index.html', './manifest.webmanifest',
  './banner.png', './banner-mobile.png', './icon-192.png', './icon-512.png',
  './styles/base.css', './styles/panel.css', './styles/main.css', './styles/modal.css', './styles/responsive.css', './styles/intro.css',
  './src/intro.js', './src/main.js', './src/data.js', './src/filter.js', './src/sort.js', './src/storage.js',
  './src/url.js', './src/render.js', './src/related.js', './src/reactions.js', './src/api.js',
  // 統計星圖
  './stats.html', './styles/stats.css', './src/stats.js', './src/stats_page.js', './vendor/chart.umd.js',
  // 書架匯出 / 匯入
  './vendor/lz-string.min.js', './vendor/qrcode.js'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys()
    .then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  const url = new URL(e.request.url);
  if (url.origin !== location.origin) return; // 外部資源(計數器等)不攔
  e.respondWith(
    fetch(e.request).then(r => {
      const cp = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, cp));
      return r;
    }).catch(() => caches.match(e.request).then(m => m || caches.match('./index.html')))
  );
});
