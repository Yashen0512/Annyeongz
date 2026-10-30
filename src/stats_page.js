// 統計星圖(stats.html)的組裝:fetch data.json(精簡格式)→ expandData 還原、讀 CSS 變數當圖表顏色、主題切換、
// 「全部 / 排除已刪」切換、愛心 / 觀測計數(Val Town,失敗退回 _build/reactions_backup.json)。計算與圖表設定都在 stats.js。
// 資料載入與首頁同一條路:fetchData() → window.DATA → loadData()(expandData + normalizeData);抓到資料之後才跑 init()。
import { loadData, fetchData } from './data.js';
import { loadTheme, saveTheme } from './storage.js';
import { encodeShare } from './url.js';
import { REACT_API, fetchCounts } from './api.js';
import { overview, createCharts } from './stats.js';

const $ = (id) => document.getElementById(id);
let D = null;
const chartLib = () => window.Chart;

/** 文章分享頁網址:Session B 的 /p/<編號>/ 合併後改成 `./p/${no}/`;目前先連回首頁帶 ?p=。 */
export const articleURL = (no) => `./?p=${encodeURIComponent(no)}`;
/** 首頁套用作者篩選的網址(與「複製篩選」同一種 #f= 格式)。 */
export const authorURL = (name) => './' + encodeShare({ author: name });

// ---- 主題(與首頁同一個 localStorage key,預設深色)----
const _root = document.documentElement;
function applyTheme(t) {
  _root.setAttribute('data-theme', t);
  const b = $('theme'); if (b) b.textContent = t === 'dark' ? '☀️' : '🌙';
  saveTheme(t);
}
applyTheme(loadTheme());
$('theme').onclick = () => { applyTheme(_root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark'); if (D) draw(); };

/** 圖表顏色一律從 CSS 變數讀,主題切換後重讀重畫。 */
function readColors() {
  const cs = getComputedStyle(_root);
  const v = (k) => cs.getPropertyValue(k).trim();
  return { accent: v('--accent'), be: v('--be'), he: v('--he'), exc: v('--exc'), oe: v('--oe'), purp: v('--purp'),
    ink: v('--ink'), muted: v('--muted'), line: v('--line'), card: v('--card'), font: getComputedStyle(document.body).fontFamily };
}

// ---- 總覽數字卡 ----
function renderOverview() {
  const o = overview(D, new Date());
  const cells = [
    ['📚 總收錄', o.total.toLocaleString(), '篇'],
    ['✍️ 作者 / 譯者', o.people.toLocaleString(), '人'],
    ['🏷️ 標籤', o.tags.toLocaleString(), '個'],
    ['🪦 原文已刪', o.dead.toLocaleString(), `篇(${o.deadPct}%)`],
    ['🌌 宇宙誕生至今', o.days.toLocaleString(), '天'],
  ];
  $('overview').innerHTML = cells.map(([l, v, u]) => `<div class="ov-card"><div class="ov-l">${l}</div><div class="ov-v">${v}<span class="ov-u">${u}</span></div></div>`).join('');
}

// ---- 圖表 ----
let charts = [], counts = null, excludeDead = false;
function destroyCharts() { charts.forEach((c) => c.destroy()); charts = []; }
function draw() {
  destroyCharts();
  const colors = readColors(), Chart = chartLib();
  if (Chart) {
    Chart.defaults.font.family = colors.font;
    Chart.defaults.color = colors.ink;
  }
  const res = createCharts(Chart, D, {
    canvases: { monthly: $('cMonthly'), tags: $('cTags'), authors: $('cAuthors'), scatter: $('cScatter'), yearly: $('cYearly') },
    colors, counts, excludeDead, now: new Date(),
    onAuthorClick: (name) => { location.href = authorURL(name); },
    onPointClick: (p) => { location.href = articleURL(p.no); },
  });
  charts = res.charts;
  const h = $('cTags').closest('.chart-box'); if (h) h.style.height = Math.max(240, res.tags.length * 26 + 60) + 'px';
  const h2 = $('cAuthors').closest('.chart-box'); if (h2) h2.style.height = Math.max(240, res.authors.length * 26 + 60) + 'px';
}

function setExcludeDead(v) {
  excludeDead = v;
  $('tagAll').classList.toggle('on', !v); $('tagAlive').classList.toggle('on', v);
  draw();
}

/** 愛心 / 觀測計數:先問 Val Town,失敗退回建置時的備份檔;都沒有就顯示提示。 */
async function loadCounts() {
  let j = REACT_API ? await fetchCounts() : null;
  if (!j) {
    try { const r = await fetch('_build/reactions_backup.json', { cache: 'no-store' }); if (r.ok) j = await r.json(); } catch (e) { j = null; }
    if (j && typeof j === 'object' && !Array.isArray(j)) { const n = $('scatterNote'); if (n) n.textContent = '(即時計數讀不到,顯示建置時的備份)'; }
    else j = null;
  }
  if (!j) { const n = $('scatterNote'); if (n) n.textContent = '(計數讀取失敗,暫時無法顯示)'; return; }
  counts = j;
  draw();
}

// ---- 啟動:抓到 data.json 才畫 ----
function init() {
  if (!chartLib()) {
    document.querySelectorAll('.chart-box').forEach((b) => { b.innerHTML = '<div class="chart-err">⚠️ 圖表程式庫(vendor/chart.umd.js)載入失敗</div>'; });
  }
  $('tagAll').onclick = () => setExcludeDead(false);
  $('tagAlive').onclick = () => setExcludeDead(true);
  if (D.updated) $('updatedNote').textContent = '🗺️ 星圖更新:' + D.updated;
  if (D.synced) $('syncedNote').textContent = '📡 訊號同步:' + D.synced;
  renderOverview();
  draw();
  loadCounts();
}
function showError(msg) {
  const o = $('overview'); if (o) o.innerHTML = `<div class="chart-err">📡 星圖載入失敗:${msg}</div>`;
}
fetchData()
  .then((j) => { window.DATA = j; D = loadData().D; return new Promise((r) => (document.readyState === 'loading' ? window.addEventListener('DOMContentLoaded', r) : r())); })
  .then(init)
  .catch((e) => showError((e && e.message) || '請檢查網路後再試'));
