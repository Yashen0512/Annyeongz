// PWA:註冊 service worker、顯示「有新收錄 / 新版本,點此重新整理」提示條、「安裝到桌面」按鈕。
// 提示條 #updateBar 與安裝鈕 #installBtn 都在 site_template.html 裡,預設 hidden。
//   - sw.js 在 data.json 背景更新且內容有變時 postMessage {type:'data-updated'} → 顯示提示條,點了重新整理
//   - 新版 sw.js 安裝完成在等待(waiting)→ 同一條提示;點了送 {type:'skipWaiting'},controllerchange 後自動重新整理
//   - 瀏覽器觸發 beforeinstallprompt 才顯示安裝鈕(已安裝或不支援的環境永遠不出現)
const $ = (id) => document.getElementById(id);

export function initPWA() {
  initInstallButton();
  if (!('serviceWorker' in navigator)) return;
  const bar = $('updateBar');
  let waiting = null, refreshing = false;
  let hadController = !!navigator.serviceWorker.controller;   // 第一次安裝時 clients.claim() 也會觸發 controllerchange,那不是「換新版」

  const showBar = (text) => {
    if (!bar) return;
    bar.textContent = text + '，點此重新整理 ↻';
    bar.hidden = false;
  };
  if (bar) {
    bar.onclick = () => {
      bar.hidden = true;
      if (waiting) waiting.postMessage({ type: 'skipWaiting' });   // 換上新版後 controllerchange 會重新整理
      else location.reload();
    };
  }
  navigator.serviceWorker.addEventListener('message', (e) => {
    if (e.data && e.data.type === 'data-updated') showBar('✨ 有新收錄');
  });
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController) { hadController = true; return; }   // 首次安裝接管:不重新整理
    if (refreshing) return;
    refreshing = true; location.reload();
  });
  const trackInstalling = (w) => {
    if (!w) return;
    w.addEventListener('statechange', () => {
      if (w.state === 'installed' && navigator.serviceWorker.controller) { waiting = w; showBar('🚀 網站有新版本'); }
    });
  };
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('sw.js').then((reg) => {
      if (reg.waiting && navigator.serviceWorker.controller) { waiting = reg.waiting; showBar('🚀 網站有新版本'); }
      trackInstalling(reg.installing);
      reg.addEventListener('updatefound', () => trackInstalling(reg.installing));
    }).catch(() => {});
  });
}

function initInstallButton() {
  const btn = $('installBtn');
  if (!btn) return;
  let deferred = null;
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); deferred = e; btn.hidden = false;
  });
  btn.onclick = () => {
    if (!deferred) return;
    const p = deferred; deferred = null; btn.hidden = true;
    p.prompt();
    p.userChoice.then((r) => { if (!r || r.outcome !== 'accepted') { deferred = p; btn.hidden = false; } }).catch(() => {});
  };
  window.addEventListener('appinstalled', () => { deferred = null; btn.hidden = true; });
}
