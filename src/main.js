// 組裝:讀資料、建立狀態、接 DOM 事件、呼叫各模組。
// 狀態說明:
//   sel / modes            標籤三態與任一/全部(見 filter.js)
//   authorFilter           作者專頁
//   shelfOn / shelfTab     書架模式與分頁
//   lazyList               主列表分批渲染(每批 BATCH 張,捲到底前自動補;見 render.js createLazyList)
//   _mode / _cur / _annIdx 詳情視窗:'art' 文章、'ann' 公告、'tool' 書架匯出 / 匯入 / 清除;_navList = 從哪一排點開(null = 主列表目前篩選+排序)
//   _opener                打開詳情前的焦點元素(書卡標題鈕 / 輪播小卡 / 書架工具鈕),關閉後把焦點還回去(鍵盤使用者才不會迷路)
// 無障礙:詳情是 <dialog>(showModal 原生鎖焦點、Esc 關閉);篩選結果數與輪播頁數用 aria-live 宣告;
//        尊重 prefers-reduced-motion(捲動不用 smooth)。
// 這支由 src/boot.js 在抓到 data.json 之後動態 import,所以執行時 window.DATA 一定已經有了。
import { loadData, sg, buildTag2Facet, sortAnnouncements, makePersonLookup } from './data.js';
import { passes, filterArticles, authorWorks, cycleTag, selectTag, removeTag, toggleMode, clearSelection, selectionChips } from './filter.js';
import { sortArticles, pickRandom } from './sort.js';
import { KEYS, loadSet, saveSet, loadShelfTab, saveShelfTab, loadTheme, saveTheme, loadListState, saveListState,
  exportState, importState, decodeState, previewImport, extractPayload, buildImportURL, clearAllRecords, IMPORT_PARAM } from './storage.js';
import { buildShareURL, parseShareHash, articleShareURL, parseArticleParam, stripArticleParam } from './url.js';
import { relatedArticles } from './related.js';
import { createReactions } from './reactions.js';
import { postReport, fetchLiveStats } from './api.js';
import * as R from './render.js';

const { D, foldZH } = loadData();
const deadAuthors = new Set(D.dead_authors || []);
const persons = makePersonLookup(D.people);   // 作者以 Notion 作者頁 ID 對應(改名也不會斷)
const tag2facet = buildTag2Facet(D.facets);
const ANNS = sortAnnouncements(D.announcements);
const deadNos = new Set(D.articles.filter((a) => a.dead).map((a) => a.no));

const $ = (id) => document.getElementById(id);
const reduceMotion = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const scrollBehavior = () => (reduceMotion() ? 'auto' : 'smooth');
// 捲到工具列:工具列現在是 sticky,貼住時 scrollIntoView 不會動,改捲它前面的哨兵(#tbSentinel 的 scroll-margin-top = 頂欄高度)
const scrollToToolbar = () => ($('tbSentinel') || document.querySelector('.toolbar')).scrollIntoView({ behavior: scrollBehavior() });
// 螢幕閱讀器宣告(aria-live 區域;同一句不重複塞,避免重複念)
function announce(id, text) { const el = $(id); if (el && el.textContent !== text) el.textContent = text; }

// ---- 狀態 ----
const sel = {}, modes = {};
let authorFilter = null, _cur = null, shelfOn = false;
let _mode = 'art', _annIdx = null, _navList = null, _opener = null;
const BATCH = 40;   // 主列表每批書卡數:先畫 40 張,其餘捲到底前再補

// 我的書架:收藏 + 待閱讀 + 已讀,存瀏覽器本機
const favs = loadSet(KEYS.FAVS), readSet = loadSet(KEYS.READ), todoSet = loadSet(KEYS.TODO);
let shelfTab = loadShelfTab();
const SHELF = { fav: favs, todo: todoSet, read: readSet };

// 公開愛心數 / 觀測數
const reactions = createReactions({ favs, deadNos, onChange: () => { render(true); if (modalOpen() && _cur) openDetail(_cur); } });

// 傳給 render.js 的畫面脈絡
const ctx = { facets: D.facets, persons, deadAuthors, favs, readSet, todoSet, likeNum: reactions.likeNum, viewNum: reactions.viewNum };

const q = $('q');
const topbarEl = document.querySelector('.topbar');
// 詳情視窗:<dialog>(新樣板)用 open 屬性;舊的 index.html 還是 div 時退回 display:flex(同步前的過渡期不會壞)
const isDialog = () => typeof $('modal').showModal === 'function';
const modalOpen = () => (isDialog() ? $('modal').open : $('modal').style.display === 'flex');
// ---- 彈窗開著時鎖住背景捲動 ----
// iOS Safari 只靠 body{overflow:hidden} 擋不住觸控捲動(在彈窗裡滑、尤其滑到底之後會帶動整頁),
// 所以用標準做法:記下 scrollY,把 body 固定(position:fixed; top:-scrollY; width:100%,class 在 modal.css),
// 關閉時還原並 scrollTo 回原位置。_lockY = 鎖住期間的「真正」捲動位置(鎖住時 window.scrollY 會變 0,
// 列表狀態記憶 saveList 與 restoreList 都要改看它,從詳情 / 分享頁回來的位置與已載入張數才不會跑掉)。
let _lockY = null;
const scrollLocked = () => _lockY !== null;
function lockScroll() {
  if (scrollLocked()) return;
  _lockY = Math.round(window.scrollY);
  const b = document.body, sb = window.innerWidth - document.documentElement.clientWidth;   // 桌機:補回捲軸寬度,版面不會跳
  b.style.top = -_lockY + 'px';
  if (sb > 0) b.style.paddingRight = sb + 'px';
  b.classList.add('az-lock');
}
/** 鎖住期間要改背景位置(例如開站時 restoreList 的還原捲動在彈窗已開之後才執行)。 */
function setLockedY(y) { _lockY = Math.round(y); document.body.style.top = -_lockY + 'px'; }
function unlockScroll() {
  if (!scrollLocked()) return;
  const y = _lockY; _lockY = null;
  const b = document.body;
  b.classList.remove('az-lock'); b.style.top = ''; b.style.paddingRight = '';
  window.scrollTo(0, y);
}
function showSheet() {
  const m = $('modal');
  if (modalOpen()) return;
  _opener = document.activeElement && document.activeElement !== document.body ? document.activeElement : _opener;
  lockScroll();
  if (isDialog()) m.showModal(); else m.style.display = 'flex';
}
/** 重新填入詳情內容前後:把焦點留在同一個位置(例如按了收藏後重繪,焦點不掉回 body)。 */
function keepSheetFocus(fill) {
  const sheet = $('sheet'), act = document.activeElement;
  const focusables = () => [...sheet.querySelectorAll('button:not([disabled]),a[href],input,textarea,[tabindex="0"]')];
  const idx = act && sheet.contains(act) ? focusables().indexOf(act) : -1;
  fill();
  if (idx >= 0) { const f = focusables(); (f[idx] || f[f.length - 1] || sheet.querySelector('.close'))?.focus(); }
}

// ---- 篩選 / 排序 ----
function filterState() {
  return {
    sel, modes, author: authorFilter, lookup: persons, term: foldZH(q.value.trim()),
    shelf: shelfOn ? SHELF[shelfTab] : null, shelfTab,
    hideRead: !!$('hideRead')?.checked, readSet,
    hideDead: !!$('hideDead')?.checked,
  };
}
function sortHits(hits) { return sortArticles(hits, $('sort').value, { likeOf: reactions.likeNum, viewOf: reactions.viewNum }); }
function currentHits() { return sortHits(filterArticles(D.articles, filterState())); }
function navArticles() { return _navList || currentHits(); }

// ---- 書架 ----
function afterMark() { render(true); updateShelfBtn(); if (modalOpen() && _cur) openDetail(_cur); }
function toggleFav(no) {
  const adding = !favs.has(no);
  adding ? favs.add(no) : favs.delete(no); saveSet(KEYS.FAVS, favs);
  reactions.onFavChange(no, adding);
  afterMark();
}
function toggleRead(no) {
  if (readSet.has(no)) readSet.delete(no);
  else { readSet.add(no); if (todoSet.delete(no)) saveSet(KEYS.TODO, todoSet); }   // 讀完自動移出待閱讀
  saveSet(KEYS.READ, readSet); afterMark();
}
function toggleTodo(no) { todoSet.has(no) ? todoSet.delete(no) : todoSet.add(no); saveSet(KEYS.TODO, todoSet); afterMark(); }
function setShelfTab(k) { shelfTab = k; saveShelfTab(k); updateShelfBtn(); render(); }
function updateShelfBtn() {
  const b = $('shelfBtn'); if (b) { b.textContent = '📚 書架'; b.classList.toggle('on', shelfOn); b.setAttribute('aria-pressed', String(shelfOn)); }
  const tb = $('shelfTabs'); if (!tb) return;
  tb.style.display = shelfOn ? 'flex' : 'none';
  tb.innerHTML = R.shelfTabsHTML(SHELF, shelfTab) + R.shelfToolsHTML();
}

// ---- 主題切換(深/淺,記憶於 localStorage,預設深色配合品牌)----
const _root = document.documentElement;
function applyTheme(t) {
  if (_root.getAttribute('data-theme') !== t) _root.setAttribute('data-theme', t);   // 沒變就不重設(改 data-theme 會讓整頁樣式重算;開站時 head 的小 script 已先設好)
  saveTheme(t);
  const b = $('theme'); if (b) { b.textContent = t === 'dark' ? '☀️' : '🌙'; b.setAttribute('aria-label', t === 'dark' ? '切換為白晝(淺色)' : '切換為黑夜(深色)'); }
}
applyTheme(loadTheme());
$('theme').onclick = () => applyTheme(_root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');

// ---- 主列表(分批渲染:先畫前 BATCH 張,捲到底前自動補下一批;篩選 / 排序改變時 render() 重置)----
const lazyList = R.createLazyList($('list'), $('more'), {
  batch: BATCH,
  renderBatch: (slice) => {
    const list = $('list'), n0 = list.children.length;
    if (n0 === 0) resetCardObs();   // 清單重畫:舊卡都不在了,觀察器重來
    R.renderCards(list, slice, ctx, (a, el) => { _navList = null; openDetail(a, el); });
    for (let i = n0; i < list.children.length; i++) observeCard(list.children[i]);
  },
  onChange: () => scheduleSaveList(),
});
// keepPos = true(搜尋 / 排序 / 勾選框 / 收藏重繪)時維持已顯示的張數,不跳回第一批(對應原站「不跳回第 1 頁」的行為)
function render(keepPos) {
  const list = $('list');
  const hits = currentHits();
  $('count').textContent = `共 ${hits.length} / ${D.total} 篇`;
  announce('liveCount', `找到 ${hits.length} 篇`);   // 篩選結果數變化 → aria-live 宣告
  { const pb = document.querySelector('.pbdone'); if (pb) pb.textContent = `看 ${hits.length} 篇 ✓`; }
  R.renderAuthorHead($('authorHead'), authorFilter, authorFilter ? authorWorks(D.articles, authorFilter, persons).length : 0, ctx,
    () => { authorFilter = null; render(); scrollToToolbar(); });
  if (!hits.length) {
    lazyList.set([], false);
    list.innerHTML = R.emptyHTML(shelfOn && SHELF[shelfTab].size === 0 ? shelfTab : null);
    R.syncStyles(sel, modes); renderSelBar(); return;
  }
  lazyList.set(hits, !!keepPos);
  R.syncStyles(sel, modes); renderSelBar();
}
function renderSelBar() {
  R.renderSelBar($('selbar'), selectionChips(sel), {
    onRemove: (k, v) => { removeTag(sel, k, v); render(); },
    onClearAll: () => { clearSelection(sel, modes); authorFilter = null; render(); },
  });
}

// ---- 輪播:星際廣播 / 新星誕生 / 軌道更新;熱門星系 ----
// 四區都等該區塊接近視窗時才初始化(R.whenVisible),開站時主執行緒只忙首批書卡;輪播畫好後順便更新箭頭顯示
let _snavRaf = 0;
function lazySection(secId, fn) {
  const sec = $(secId);
  R.whenVisible(sec, () => {
    fn();
    // 箭頭要讀 scrollWidth(強制排版),幾個區塊同時畫好時合併到同一幀只讀一次
    if (!_snavRaf) _snavRaf = requestAnimationFrame(() => { _snavRaf = 0; updateAllSnav(); document.querySelectorAll('.striprow').forEach(announceStripPage); });
  });
}
function renderAnn() {
  if (!ANNS.length) return;
  $('annSec').style.display = '';   // 先顯示區塊,IntersectionObserver 才觀測得到
  lazySection('annSec', () => R.renderStrip($('ann'), ANNS, { html: R.annCardHTML, cls: R.annCardCls, onClick: (x, i) => openAnn(i) }));
}
function renderLatest() {
  lazySection('latestSec', () => {
    // 最新收錄:依「建立時間(實際新增進資料庫)」由新到舊,不是按編號
    const newest = D.articles.filter((a) => a.ck).sort((a, b) => b.ck - a.ck).slice(0, 8);
    R.renderStrip($('latest'), newest, { html: R.latestCardHTML, onClick: (a, i, el) => { _navList = newest; openDetail(a, el); } });
  });
}
function renderStatus() {
  lazySection('statusSec', () => {
    const arr = D.articles.filter((a) => a.ek).sort((a, b) => b.ek - a.ek).slice(0, 8);
    R.renderStrip($('statusUpd'), arr, { html: R.statusCardHTML, onClick: (a, i, el) => { _navList = arr; openDetail(a, el); } });
  });
}
function renderHot() {
  // 熱門星系只有 16 個 chip,直接畫;它的高度隨資料而定,不先畫好會把下面的列表往下推(CLS)
  R.renderHot($('hot'), D.facets, (key, v) => { selectTag(sel, key, v); render(); scrollToToolbar(); });
}

// ---- 詳情 / 公告視窗(內容在打開時才產生 DOM,關閉時清空;#sheet 平常是空的)----
function openAnn(i) {
  if (i < 0 || i >= ANNS.length) return;
  _mode = 'ann'; _annIdx = i; _cur = null;
  const sheet = $('sheet');
  keepSheetFocus(() => { sheet.innerHTML = R.annHTML(ANNS[i], i, ANNS.length); });
  showSheet(); sheet.scrollTop = 0;
}
/** 打開文章詳情;opener = 觸發的元素(書卡標題鈕 / 輪播小卡),關閉後焦點回到它。 */
function openDetail(a, opener) {
  const changed = !modalOpen() || _mode !== 'art' || !_cur || _cur.no !== a.no;   // 剛打開或換了一篇才捲回頂端、焦點給關閉鈕(開著時按收藏 / 已讀重繪維持位置與焦點)
  _mode = 'art'; _annIdx = null; _cur = a;
  if (opener && !modalOpen()) _opener = opener;
  reactions.markView(a.no);
  const sheet = $('sheet');
  const L = navArticles();
  keepSheetFocus(() => { sheet.innerHTML = R.detailHTML(a, ctx, { rel: relatedArticles(a, D.articles, 6), navIndex: L.findIndex((x) => x.no === a.no), navLen: L.length }); });
  showSheet();
  if (changed) { sheet.scrollTop = 0; if (isDialog()) sheet.querySelector('.close')?.focus(); }   // 換篇時焦點回到最上面的關閉鈕
}
// 關閉:先同步解鎖還原捲動,再 close()(<dialog> 的 close 事件是非同步的,點標籤 / 作者後緊接的 render + scrollToToolbar
// 必須在解鎖之後執行,否則會被還原捲動蓋掉);Esc / 點灰底走瀏覽器的 close → 下面的 close 事件補解鎖
function closeDetail() { stopScan(); unlockScroll(); const m = $('modal'); if (isDialog()) { if (m.open) m.close(); } else { m.style.display = 'none'; restoreFocus(); $('sheet').innerHTML = ''; } }
/** 關閉後把焦點還給打開它的元素;那張卡若已重繪(例如按了收藏),改找同編號的卡。 */
function restoreFocus() {
  let el = _opener; _opener = null;
  // 從書卡打開、又用 ←→ 換了篇:焦點回到「最後看的那篇」的卡(列表裡有的話),沒有就回原卡;原卡重繪過也改找同編號的卡
  const fromCard = el && el.classList && el.classList.contains('card-open');
  if (_mode === 'art' && _cur && (fromCard || (el && !el.isConnected))) {
    const c = document.querySelector(`.card[data-no="${CSS.escape(_cur.no)}"] .card-open`); if (c) el = c;
  }
  if (el && el.isConnected && !el.matches('[tabindex="-1"]')) el.focus();   // 目標一定是書卡 / 小卡 / 工具鈕本身,不是 main 或 section 這種容器
}
$('modal').onclick = (e) => { if (e.target.id === 'modal') closeDetail(); };   // 點灰底(dialog 本身)關閉
$('modal').addEventListener('close', () => { stopScan(); unlockScroll(); restoreFocus(); $('sheet').innerHTML = ''; });   // Esc / close() 都會經過這裡(Esc 關掉匯入視窗時也要停相機);先解鎖再還焦點(focus 可能捲動);內容清空,下次打開才建
function openByNo(no) { const a = D.articles.find((x) => x.no === no); if (a) { _navList = null; openDetail(a); } }
// 開站時網址帶 ?p=<No>(從分享頁 p/<No>/ 導回來)→ 打開該篇詳情,並把參數從網址拿掉(其他參數與 #f= 保留)
function openSharedArticle() {
  const no = parseArticleParam(location.search); if (!no) return;
  try { history.replaceState(null, '', stripArticleParam(location.href)); } catch (e) { /* 舊瀏覽器 */ }
  openByNo(no);
}
// 詳情裡的「複製分享連結」:複製該篇的靜態分享頁網址(貼到社群會顯示專屬預覽卡)
function shareArticle(no, btn) {
  const old = btn ? btn.textContent : '';
  copyURL(articleShareURL(no)).then((ok) => {
    if (!btn) return;
    btn.textContent = ok ? '✓ 已複製!' : '⚠ 複製失敗'; setTimeout(() => { btn.textContent = old; }, 1600);
  });
}
// 點標籤 → 篩出同標籤的文
function filterByTag(enc) {
  const v = decodeURIComponent(enc); const fac = tag2facet[v]; if (!fac) return;
  selectTag(sel, fac, v);
  closeDetail(); render(); scrollToToolbar();
}
function filterName(enc) { const name = decodeURIComponent(enc); if (name) { authorFilter = name; closeDetail(); render(); scrollToToolbar(); } }
// 詳情視窗:Esc 關閉、←→ 切上下篇(依目前篩選+排序的清單)
function navDetail(d) {
  if (!modalOpen()) return;
  if (_mode === 'ann') { if (_annIdx != null) openAnn(_annIdx + d); return; }
  if (!_cur) return;
  const list = navArticles();
  const i = list.findIndex((x) => x.no === _cur.no); if (i < 0) return;
  const j = i + d; if (j >= 0 && j < list.length) openDetail(list[j]);
}
document.addEventListener('keydown', (e) => {
  if (!modalOpen()) return;
  if (e.key === 'Escape') { if (!isDialog()) closeDetail(); return; }   // <dialog> 的 Esc 由瀏覽器處理(cancel → close)
  if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) return;      // 輸入框裡的左右鍵是在移游標
  if (e.key === 'ArrowLeft') navDetail(-1);
  else if (e.key === 'ArrowRight') navDetail(1);
});

// ---- 書架匯出 / 匯入 / 清除所有紀錄(共用詳情的 #modal;_mode = 'tool' 時 ←→ 不會切換文章)----
function openTool(html) {
  stopScan();
  _mode = 'tool'; _cur = null; _annIdx = null;
  const sheet = $('sheet');
  keepSheetFocus(() => { sheet.innerHTML = html; });
  showSheet(); sheet.scrollTop = 0;
  if (isDialog() && !sheet.contains(document.activeElement)) sheet.querySelector('.close')?.focus();
}
function setMsg(id, text, cls) { const el = $(id); if (el) { el.textContent = text || ''; el.className = 'xmsg' + (cls ? ' ' + cls : ''); } }
// 複製到剪貼簿;不支援時退回 prompt(與「複製篩選」同一套)
function copyText(text, msgId, okText) {
  const done = (ok) => setMsg(msgId, ok ? okText : '⚠ 複製失敗,請直接全選上面的字串複製', ok ? 'ok' : 'err');
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => done(true)).catch(() => { prompt('複製這段文字:', text); done(true); });
  else { prompt('複製這段文字:', text); done(true); }
}
const siteBase = () => location.origin + location.pathname;
// vendor 單檔(lz-string 壓縮、qrcode 產 QR)只有匯出 / 匯入才需要,用到時才載(不佔首頁啟動時間);離線時由 service worker 的預快取供應
const _vendor = {};
function loadScript(src) {
  if (!_vendor[src]) _vendor[src] = new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = () => { delete _vendor[src]; rej(new Error(src + ' 載入失敗')); }; document.head.appendChild(s); });
  return _vendor[src];
}
function ensureVendor() {
  return Promise.all([window.LZString ? null : loadScript('vendor/lz-string.min.js'), window.qrcode ? null : loadScript('vendor/qrcode.js')]).catch(() => {});   // 載不到時 exportState / renderQR 自己會顯示錯誤
}
// 匯出:字串 + 複製 / 複製連結 / QR code(QR 內容是匯入連結,用相機掃到就直接開站)
async function shelfExport() {
  openTool(R.exportHTML({ payload: null, err: '⏳ 準備中…', counts: { shelf: favs.size, read: readSet.size, todo: todoSet.size } }));   // 先開視窗(焦點與 opener 在使用者動作當下記錄),再等 vendor
  await ensureVendor();
  if (!modalOpen() || _mode !== 'tool') return;
  let payload = null, err = '';
  try { payload = exportState({ favs, read: readSet, todo: todoSet }); } catch (e) { err = e.message; }
  openTool(R.exportHTML({ payload, err, counts: { shelf: favs.size, read: readSet.size, todo: todoSet.size } }));
  if (!payload) return;
  const link = buildImportURL(payload, siteBase());
  $('xpCopy').onclick = () => copyText(payload, 'xpMsg', '✓ 已複製字串,到另一台裝置的「📥 匯入」貼上');
  $('xpLink').onclick = () => copyText(link, 'xpMsg', '✓ 已複製連結,在另一台裝置打開就會跳出匯入預覽');
  const out = $('xpOut'); out.onfocus = () => out.select();
  const qr = $('xpQr'); if (qr) renderQR(qr, link);
}
function renderQR(el, text) {
  const Q = window.qrcode;   // vendor/qrcode.js
  if (typeof Q !== 'function') { el.innerHTML = '<div class="xmsg err">QR code 元件未載入,請改用複製</div>'; return; }
  try { const q = Q(0, 'M'); q.addData(text, 'Byte'); q.make(); el.innerHTML = q.createSvgTag({ cellSize: 4, margin: 2, scalable: true, alt: '匯入連結 QR code' }); }
  catch (e) { el.innerHTML = '<div class="xmsg err">內容太長,QR code 畫不下,請改用複製</div>'; }
}
// 匯入:貼上(或掃 QR)→ 預覽「將加入 X 本書架、Y 篇已讀、Z 篇待閱讀」→ 選合併 / 覆蓋 → 確認才寫入
let _imPending = null, _imText = '';   // 解析成功、等待確認的匯入內容與原字串
async function shelfImport(prefill) {
  _imPending = null; _imText = '';
  await ensureVendor();
  const canScan = typeof window.BarcodeDetector === 'function' && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  openTool(R.importHTML({ canScan, prefill }));
  $('imPreview').onclick = () => previewImportText($('imIn').value);
  const sc = $('imScan'); if (sc) sc.onclick = () => startScan((code) => { $('imIn').value = code; previewImportText(code); });
  $('imScanStop').onclick = stopScan;
  if (prefill) previewImportText(prefill);
}
const imMode = () => { const r = document.querySelector('input[name=imMode]:checked'); return r ? r.value : 'merge'; };
function previewImportText(text) {
  stopScan();
  const pre = $('imPre'); if (!pre) return;
  try { _imPending = decodeState(text); _imText = text; }
  catch (e) { _imPending = null; _imText = ''; pre.style.display = 'none'; setMsg('imMsg', '⚠️ ' + e.message, 'err'); return; }
  setMsg('imMsg', '');
  renderImPreview('merge');
}
function renderImPreview(mode) {
  const pre = $('imPre'); if (!pre || !_imPending) return;
  const st = previewImport({ favs, read: readSet, todo: todoSet }, _imPending, mode);
  pre.innerHTML = R.importPreviewHTML(st, mode, _imPending.exportedAt); pre.style.display = '';
  pre.querySelectorAll('input[name=imMode]').forEach((r) => { r.onchange = () => renderImPreview(imMode()); });
  $('imGo').onclick = confirmImport;
}
function confirmImport() {
  if (!_imPending) return;
  const mode = imMode(); let r;
  try { r = importState(_imText, { favs, read: readSet, todo: todoSet, mode }); }
  catch (e) { setMsg('imMsg', '⚠️ ' + e.message, 'err'); return; }
  reactions.markCounted(r.addedShelf);   // 匯入的收藏在原裝置已算過愛心,這裡不再 +1
  if (new RegExp('[?&]' + IMPORT_PARAM + '=').test(location.search)) history.replaceState(null, '', location.pathname + location.hash);   // 從 ?s= 連結來的:寫入後移除參數
  _imPending = null; _imText = '';
  afterMark();
  openTool(R.importDoneHTML(r, mode));
}
// 相機掃 QR(BarcodeDetector;不支援的瀏覽器沒有這顆按鈕)
let _scan = null;   // {stream, timer}
function startScan(onCode) {
  const box = $('imCam'), video = box && box.querySelector('video'); if (!video) return;
  stopScan(); setMsg('imMsg', '');
  navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } }).then((stream) => {
    if (!modalOpen() || !$('imCam')) { stream.getTracks().forEach((t) => t.stop()); return; }   // 等權限時視窗已經關了
    const det = new window.BarcodeDetector({ formats: ['qr_code'] });
    _scan = { stream, timer: 0 };
    video.srcObject = stream; box.style.display = ''; video.play().catch(() => {});
    const tick = () => {
      if (!_scan) return;
      const p = video.readyState >= 2 ? det.detect(video) : Promise.resolve([]);
      p.then((codes) => {
        const c = (codes || []).find((x) => x.rawValue);
        if (c && _scan) { stopScan(); onCode(c.rawValue); return; }
        if (_scan) _scan.timer = setTimeout(tick, 250);
      }).catch(() => { if (_scan) _scan.timer = setTimeout(tick, 400); });
    };
    tick();
  }).catch((e) => {
    const why = e && (e.name === 'NotAllowedError' || e.name === 'SecurityError') ? '沒有相機權限' : (e && e.name === 'NotFoundError' ? '找不到相機' : '無法開啟相機');
    setMsg('imMsg', '⚠️ ' + why + ',請改用貼上字串', 'err');
  });
}
function stopScan() {
  if (!_scan) return;
  clearTimeout(_scan.timer); _scan.stream.getTracks().forEach((t) => t.stop()); _scan = null;
  const box = $('imCam'); if (box) { box.style.display = 'none'; const v = box.querySelector('video'); if (v) v.srcObject = null; }
}
// 清除所有紀錄:要輸入「清除」才能按
function shelfClear() {
  openTool(R.clearHTML({ fav: favs.size, todo: todoSet.size, read: readSet.size }));
  const inp = $('clIn'), go = $('clGo');
  inp.oninput = () => { go.disabled = inp.value.trim() !== R.CLEAR_WORD; };
  inp.onkeydown = (e) => { if (e.key === 'Enter' && !go.disabled) go.click(); };
  go.onclick = () => {
    if (inp.value.trim() !== R.CLEAR_WORD) return;
    [...favs].forEach((no) => reactions.onFavChange(no, false));   // 與逐篇取消收藏相同:已計入的公開愛心會扣回
    clearAllRecords({ favs, read: readSet, todo: todoSet });
    reactions.forgetAll();
    shelfTab = 'fav';
    afterMark();
    openTool(R.clearedHTML());
  };
  setTimeout(() => inp.focus(), 50);
}
// 另一台裝置用 ?s=<匯出字串> 打開本站:自動跳出匯入預覽(只預覽,確認後才寫入)
function applyImportParam() {
  if (!new RegExp('[?&]' + IMPORT_PARAM + '=').test(location.search)) return;
  shelfImport(extractPayload(location.href));
}

// ---- 連結回報 ----
function toggleReport(id) {
  const b = $(id); if (!b) return;
  const open = b.classList.toggle('open');
  document.querySelector(`[aria-controls="${id}"]`)?.setAttribute('aria-expanded', String(open));
  if (open) b.querySelector('.ctl')?.focus();
}
function pickReason(btn, other) {
  const box = btn.closest('.repbox');
  box.querySelectorAll('.opts .ctl').forEach((x) => { x.classList.remove('on'); x.setAttribute('aria-pressed', 'false'); });
  btn.classList.add('on'); btn.setAttribute('aria-pressed', 'true'); box.dataset.sel = btn.textContent.trim();   // 目前點選的回報原因
  const ta = box.querySelector('textarea');
  if (ta) ta.style.display = other ? 'block' : 'none';   // 選「其他」才展開文字框
}
// 逐連結回報:原因前面加上連結名稱(「AFF:🔗 打不開」),服務端不用改
function sendReport(no, i) {
  const box = $('rb' + i); if (!box) return;
  const ta = box.querySelector('textarea'), msg = box.querySelector('.rmsg');
  const title = _cur ? (_cur.name || '') : '';
  const label = (_cur && _cur.links && _cur.links[i]) ? _cur.links[i][0] : '';
  if (!box.dataset.sel) { if (msg) msg.textContent = '請先點選一個原因'; return; }
  let reason = (label ? label + ':' : '') + box.dataset.sel;
  const extra = (ta && ta.style.display !== 'none' ? ta.value : '').trim();
  if (extra) reason += ':' + extra;
  reason = reason.slice(0, 500);
  if (msg) msg.textContent = '送出中…';
  const fail = () => { if (msg) msg.textContent = '⚠️ 送出失敗,請稍後再試'; };
  postReport(no, title, reason).then((j) => {
    if (j && j.ok) { if (msg) msg.textContent = '✅ 訊號已收到,謝謝回報!'; if (ta) ta.value = ''; }
    else fail();
  }).catch(fail);
}

// ---- 工具列 ----
$('reset').onclick = () => {
  clearSelection(sel, modes); authorFilter = null; shelfOn = false;
  $('hideRead').checked = false; $('hideDead').checked = false; q.value = ''; $('sort').value = 'old';
  updateShelfBtn(); render();
};
$('shelfBtn').onclick = () => { shelfOn = !shelfOn; updateShelfBtn(); render(); scrollToToolbar(); };
// 注意:原站把 render 直接當事件處理器,事件物件被當成 keepPage(真值),所以搜尋/排序/勾選時不會跳回第 1 頁;這裡維持同樣行為。
$('hideRead').onchange = () => render(true);
$('hideDead').onchange = () => render(true);
q.oninput = () => render(true);
$('sort').onchange = () => render(true);
// 複製網址:navigator.clipboard,不支援或失敗時退回 prompt() 讓人手動複製。回傳 Promise<boolean>
// (書架匯出用的 copyText 走訊息列,這裡的分享按鈕只要改按鈕文字,所以分開一支)
function copyURL(text) {
  const fallback = () => { prompt('複製這個網址分享:', text); return true; };
  if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text).then(() => true).catch(fallback);
  return Promise.resolve(fallback());
}
// 可分享的篩選網址:把目前篩選編進網址 #f=,別人打開就是同樣篩選
function currentShare() { return { sel, modes, author: authorFilter, q: q.value, sort: $('sort').value }; }
function applyShareHash() {
  const s = parseShareHash(location.hash); if (!s) return;
  clearSelection(sel, modes);
  Object.assign(sel, s.sel); Object.assign(modes, s.modes);
  authorFilter = s.author;
  if (s.q !== undefined) q.value = s.q;
  if (s.sort) $('sort').value = s.sort;
}
$('shareBtn').onclick = () => {
  const url = buildShareURL(currentShare(), location.origin + location.pathname), btn = $('shareBtn'), old = '🔗 複製篩選';
  copyURL(url).then((ok) => { btn.textContent = ok ? '✓ 已複製!' : '⚠ 複製失敗'; setTimeout(() => btn.textContent = old, 1600); });
};
// 穿越蟲洞:在目前篩選結果中隨機開一篇(略過 原文已刪/無連結,抽到也讀不了)
$('rand').onclick = () => {
  const f = filterState();
  const h = D.articles.filter((a) => passes(a, f) && !a.dead && a.links && a.links.length);
  const a = pickRandom(h);
  if (a) { _navList = null; openDetail(a); R.wormholeToast($('sheet')); }
};
function setPanelOpen(open) {
  const p = $('panel'); p.classList.toggle('open', open);
  document.body.classList.toggle('noscroll', open && window.innerWidth <= 860);
  $('filterToggle').setAttribute('aria-expanded', String(open));
  if (open) p.querySelector('.pbdone, .fh')?.focus(); else $('filterToggle').focus();   // 手機全螢幕面板:焦點進去 / 出來
}
$('filterToggle').onclick = () => setPanelOpen(!$('panel').classList.contains('open'));
document.querySelector('.pbdone').onclick = () => setPanelOpen(false);
$('panel').addEventListener('keydown', (e) => { if (e.key === 'Escape' && $('panel').classList.contains('open')) setPanelOpen(false); });

// ---- 跳到 #編號:在目前篩選結果裡找該篇,自動載入到那張卡、捲過去、短暫高亮並把焦點給它 ----
function jumpTo(raw) {
  const no = String(raw || '').replace(/^#/, '').trim(), msg = $('jumpMsg');
  if (!no) { if (msg) msg.textContent = ''; return false; }
  const idx = lazyList.hits().findIndex((a) => a.no === no);
  if (idx < 0) {
    if (msg) msg.textContent = D.articles.some((a) => a.no === no) ? `#${no} 不在目前的篩選結果裡,先放寬條件或重設篩選` : `沒有 #${no} 這篇`;
    return false;
  }
  if (msg) msg.textContent = '';
  lazyList.ensure(idx + 1);   // 還沒載到就一次補到那張(之後的仍照批載)
  const card = $('list').querySelector(`.card[data-no="${CSS.escape(no)}"]`);
  if (card) highlightCard(card);
  return true;
}
function highlightCard(card) {
  document.querySelectorAll('.card.hl').forEach((c) => c.classList.remove('hl'));
  // 即時捲動(可能一跳就是幾百張,平滑捲動反而暈且久):卡片置中於「頂欄 + sticky 工具列」以下的空間,高卡頂端也不會被擋住
  const r = card.getBoundingClientRect(), bars = barsHeight();
  const free = Math.max(0, window.innerHeight - bars - r.height);
  window.scrollTo(0, Math.max(0, Math.round(window.scrollY + r.top - bars - free / 2)));
  void card.offsetWidth;   // 重新觸發高亮動畫
  card.classList.add('hl');
  card.querySelector('.card-open')?.focus({ preventScroll: true });
  setTimeout(() => card.classList.remove('hl'), 2400);
}
$('jumpForm').onsubmit = (e) => { e.preventDefault(); jumpTo($('jumpNo').value); };
$('jumpNo').addEventListener('change', () => { if (_mini && $('jumpNo').value.trim()) jumpTo($('jumpNo').value); });   // 手機壓縮列沒有「前往」鈕(iOS 數字鍵盤也沒有 Enter):輸入完離開欄位就跳

// ---- 記住主列表狀態(sessionStorage):從詳情、分享頁(p/<No>/ 導回來)或瀏覽器「上一頁」回來時,
//      已載入的張數與捲動位置照舊,不會重置回第一批。簽章 = 會影響清單內容的所有狀態;對不上(篩選變了)就不還原。
function listSig() {
  return JSON.stringify({ sel, modes, a: authorFilter, q: q.value.trim(), s: $('sort').value, sh: shelfOn ? shelfTab : '', hr: !!$('hideRead').checked, hd: !!$('hideDead').checked });
}
let _saveTm = 0;
function saveList() { saveListState({ sig: listSig(), shown: lazyList.shown(), y: scrollLocked() ? _lockY : Math.round(window.scrollY) }); }   // 彈窗開著時 scrollY 是 0,要存鎖住前的位置
function scheduleSaveList() { if (_saveTm) return; _saveTm = setTimeout(() => { _saveTm = 0; saveList(); }, 250); }
window.addEventListener('scroll', scheduleSaveList, { passive: true });
window.addEventListener('pagehide', saveList);
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') saveList(); });
function restoreList() {
  const st = loadListState(); if (!st || st.sig !== listSig()) return false;
  if (st.shown > lazyList.shown()) lazyList.ensure(st.shown);
  if (st.y > 0) requestAnimationFrame(() => requestAnimationFrame(() => { if (scrollLocked()) setLockedY(st.y); else window.scrollTo(0, st.y); }));   // 等補上的卡排版完再捲;彈窗已開(?p= / ?s=)就先記在鎖裡,關閉時再捲
  return true;
}

// ---- 輪播箭頭:只在「有得捲」時出現(沒溢出全藏、捲到頭藏左、捲到底藏右)----
function stripScroll(s, dir) { const amt = Math.max(220, s.clientWidth * 0.8); s.scrollBy({ left: dir * amt, behavior: scrollBehavior() }); }
document.querySelectorAll('.snav').forEach((btn) => {
  btn.onclick = () => stripScroll(btn.parentElement.querySelector('.strip'), btn.classList.contains('l') ? -1 : 1);
});
function updateSnav(row) {
  const s = row.querySelector('.strip'); if (!s) return;
  const l = row.querySelector('.snav.l'), r = row.querySelector('.snav.r');
  const can = s.scrollWidth - s.clientWidth > 2;
  if (l) l.classList.toggle('hide', !can || s.scrollLeft <= 1);
  if (r) r.classList.toggle('hide', !can || s.scrollLeft + s.clientWidth >= s.scrollWidth - 1);
  // 箭頭鈕隱藏時若焦點正在它上面,把焦點移到另一邊的箭頭(否則焦點會掉回 body,鍵盤使用者迷路)
  const a = document.activeElement;
  if (a === l && l.classList.contains('hide')) (r && !r.classList.contains('hide') ? r : s.firstElementChild)?.focus();
  else if (a === r && r.classList.contains('hide')) (l && !l.classList.contains('hide') ? l : s.firstElementChild)?.focus();
}
function updateAllSnav() { document.querySelectorAll('.striprow').forEach(updateSnav); }
// 輪播目前頁數(以可視寬度為一頁)→ aria-live 宣告「第 X / Y 頁」;捲動停下來才念
function announceStripPage(row) {
  const s = row.querySelector('.strip'), live = row.querySelector('.strip-page'); if (!s || !live) return;
  const n = Math.max(1, Math.ceil(s.scrollWidth / Math.max(1, s.clientWidth)));
  const p = Math.min(n, Math.round(s.scrollLeft / Math.max(1, s.clientWidth)) + 1);
  const t = n > 1 ? `第 ${p} / ${n} 頁` : ''; if (live.textContent !== t) live.textContent = t;
}
document.querySelectorAll('.striprow').forEach((row) => {
  const s = row.querySelector('.strip'); if (!s) return;
  let tm = null;
  s.addEventListener('scroll', () => { updateSnav(row); clearTimeout(tm); tm = setTimeout(() => announceStripPage(row), 150); });
  // 鍵盤:在小卡上按 ← → 移到上一張 / 下一張(自動捲入畫面),Home / End 到頭尾;在箭頭鈕上按 ← → 直接捲動
  row.addEventListener('keydown', (e) => {
    const k = e.key; if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(k)) return;
    const cards = [...s.children]; const i = cards.indexOf(e.target);
    if (i < 0) { if (k === 'ArrowLeft' || k === 'ArrowRight') { e.preventDefault(); stripScroll(s, k === 'ArrowLeft' ? -1 : 1); } return; }
    e.preventDefault();
    const j = k === 'Home' ? 0 : k === 'End' ? cards.length - 1 : Math.min(cards.length - 1, Math.max(0, i + (k === 'ArrowLeft' ? -1 : 1)));
    cards[j].focus(); cards[j].scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: scrollBehavior() });
  });
});
window.addEventListener('resize', updateAllSnav);
window.addEventListener('load', updateAllSnav);
updateAllSnav();

// ---- 回到頂部(桌機右下角 #toTop、手機壓縮工具列裡的 #toTopBar):顯示目前視窗最上方那張卡的編號「↑ #1305」----
const toTop = $('toTop'), toTopBar = $('toTopBar');
window.addEventListener('scroll', () => { if (!scrollLocked()) toTop.classList.toggle('show', window.scrollY > 400); });   // 鎖住時 scrollY 變 0,不要讓按鈕閃一下
const goTop = (e, btn) => { if (e.detail) btn.blur(); window.scrollTo({ top: 0, behavior: scrollBehavior() }); };   // 滑鼠點才 blur(手機不留粉色殘影),鍵盤保留焦點
toTop.onclick = (e) => goTop(e, toTop);
if (toTopBar) toTopBar.onclick = (e) => goTop(e, toTopBar);
// 書卡用 IntersectionObserver 盯(不是每次 scroll 都算):root 的上緣往下縮「頂欄 + 工具列」的高度,卡片的底邊穿過那條線才會觸發;
// 視窗裡的卡放在 _visCards,取 top 最小的那張。bars 高度變了(手機壓縮 / 頂欄換行)才重建觀察器。
const _visCards = new Set();
let _cardObs = null, _cardObsBars = -1;
function cardObsBars() { return Math.round(topbarEl.offsetHeight + ($('toolbar') ? $('toolbar').offsetHeight : 0)); }
function buildCardObs() {
  if (!('IntersectionObserver' in window)) return;
  const bars = cardObsBars(); if (_cardObs && bars === _cardObsBars) return;
  if (_cardObs) _cardObs.disconnect(); _visCards.clear(); _cardObsBars = bars;
  _cardObs = new IntersectionObserver((es) => {
    es.forEach((e) => { if (e.isIntersecting) _visCards.add(e.target); else _visCards.delete(e.target); });
    updateToTop();
  }, { rootMargin: `-${bars}px 0px 0px 0px`, threshold: 0 });
  document.querySelectorAll('#list .card').forEach((c) => _cardObs.observe(c));
}
function observeCard(c) { if (_cardObs) _cardObs.observe(c); }
function resetCardObs() { if (_cardObs) _cardObs.disconnect(); _visCards.clear(); updateToTop(); }
function updateToTop() {
  let best = null, bt = Infinity;
  _visCards.forEach((c) => { if (!c.isConnected) { _visCards.delete(c); return; } const t = c.getBoundingClientRect().top; if (t < bt) { bt = t; best = c; } });
  const no = best ? best.dataset.no : '';
  [toTop, toTopBar].forEach((b) => {
    if (!b || b.dataset.no === no) return;
    b.dataset.no = no;
    b.innerHTML = no ? `↑ <span class="tno" aria-hidden="true">#${no}</span>` : '↑';
    b.setAttribute('aria-label', no ? `回到頂部，目前在 #${no}` : '回到頂部');
  });
}

// ---- sticky 工具列:貼在頂欄下方(top = --topbar-h,量實際高度寫進 CSS 變數);捲過工具列(.stuck)底色同頂欄 + 細分隔線。
//      手機(≤860px)捲過去改壓縮版(.mini):只留 🔧 篩選、排序、跳到 #、↑,其他那組(#tbExtra)搬進篩選面板頂部(#panelTools),
//      #tbSpace 補回少掉的高度,下面的版面不跳;捲回最上面再搬回來。偵測用 IntersectionObserver 盯工具列前面的哨兵 #tbSentinel。
const toolbar = $('toolbar'), tbSentinel = $('tbSentinel'), tbExtra = $('tbExtra'), tbSpace = $('tbSpace'), panelTools = $('panelTools');
const isMobile = () => window.innerWidth <= 860;
let _stuck = false, _mini = false, _tbObs = null;
function barsHeight() { return topbarEl.offsetHeight + (toolbar ? toolbar.offsetHeight : 0); }   // 跳到 #編號的偏移:頂欄 + 工具列(貼住時就在頂欄下方)
const setVar = (name, px) => document.documentElement.style.setProperty(name, Math.round(px) + 'px');
function measureBars() {
  setVar('--topbar-h', topbarEl.offsetHeight);
  setVar('--toolbar-h', toolbar ? toolbar.offsetHeight : 0);
  buildCardObs();
}
function setMini(on) {
  if (!toolbar || !tbExtra || on === _mini) return;
  _mini = on; document.body.classList.toggle('tb-mini', on);
  if (on) {
    const full = toolbar.offsetHeight;
    toolbar.classList.add('mini'); panelTools.appendChild(tbExtra);
    tbSpace.style.height = Math.max(0, full - toolbar.offsetHeight) + 'px';
  } else {
    toolbar.classList.remove('mini'); toolbar.insertBefore(tbExtra, $('jumpForm'));
    tbSpace.style.height = '0px';
  }
  measureBars();
}
function setStuck(on) {
  if (!toolbar || on === _stuck) return;
  _stuck = on; toolbar.classList.toggle('stuck', on);
  setMini(on && isMobile());
}
function watchToolbar() {
  if (!tbSentinel || !('IntersectionObserver' in window)) return;
  if (_tbObs) _tbObs.disconnect();
  const top = Math.round(topbarEl.offsetHeight);
  // root 的上緣往下縮頂欄高度、下緣往外放很大:哨兵只要在頂欄下緣以下(含視窗外下方)都算相交,
  // 跑到頂欄下緣以上才不相交 = 捲過工具列了。下緣不放大的話,哨兵從「視窗下方」直接捲到「頂欄上方」都是不相交,觀察器不會觸發。
  _tbObs = new IntersectionObserver((es) => {
    const e = es[es.length - 1];
    setStuck(!e.isIntersecting && e.boundingClientRect.top < top);
  }, { rootMargin: `-${top}px 0px 100000px 0px`, threshold: 0 });
  _tbObs.observe(tbSentinel);
}
function initSticky() {
  measureBars(); watchToolbar();
  if ('ResizeObserver' in window) {
    let tm = 0;
    new ResizeObserver(() => { clearTimeout(tm); tm = setTimeout(() => { measureBars(); watchToolbar(); }, 60); }).observe(topbarEl);   // 頂欄換行(手機搜尋列換到第二行)→ 重量、重盯
    if (toolbar) new ResizeObserver(() => measureBars()).observe(toolbar);
  }
  window.addEventListener('resize', () => { setMini(_stuck && isMobile()); measureBars(); });
}

// ---- 頁尾:統計 / 更新時間 ----
function renderStats(s, live) { R.renderStats($('statsCard'), s || D.stats, live); }
function loadLiveStats() { fetchLiveStats().then((j) => { if (j) renderStats(j, true); }); }
if (D.updated) { $('updatedNote').textContent = '🗺️ 星圖更新:' + D.updated; }
if (D.synced) { $('syncedNote').innerHTML = '📡 訊號同步:' + D.synced + ' <span title="每天 08:31・21:01 自動更新&#10;안유진 08/31 · 장원영 09/01 🎂" style="cursor:help">🎂</span>'; }

// 詳情 / 書卡 HTML 字串裡的 inline onclick 會呼叫這些函式,所以要掛到 window(ES module 內的函式不是全域)
Object.assign(window, { toggleFav, toggleTodo, toggleRead, setShelfTab, filterByTag, filterName, openByNo, shareArticle, closeDetail, navDetail, toggleReport, pickReason, sendReport, shelfExport, shelfImport, shelfClear });

// ---- 啟動 ----
// 先把主列表第一批畫出來(使用者最先看到的),其餘工作拆成獨立小工作延後,避免單一長工作卡住互動。
// PWA(service worker、安裝鈕、更新提示)在 src/pwa.js,由 boot.js 啟動。
const defer = (fn) => ('requestIdleCallback' in window ? requestIdleCallback(fn, { timeout: 800 }) : setTimeout(fn, 1));
initSticky();                                // 先量頂欄高度(sticky 工具列的 top)、掛上哨兵與書卡觀察器,再畫第一批
updateShelfBtn(); applyShareHash(); renderHot(); render();
renderAnn(); renderLatest(); renderStatus();
document.body.classList.remove('loading');   // 主內容(資料到了才有意義)此時一次顯示;輪播區塊有固定高度,之後補上不會推動版面
restoreList();                               // 從詳情 / 分享頁 / 上一頁回來:已載入張數與捲動位置照舊
applyImportParam(); openSharedArticle();     // ?s= 匯入預覽、?p= 分享頁導回來開詳情
defer(() => {
  R.buildPanel($('panel'), D.facets, {
    onTag: (key, val) => { cycleTag(sel, key, val); render(); },
    onMode: (key) => { toggleMode(modes, key); render(); },
  });
  R.syncStyles(sel, modes);
});
defer(() => { renderStats(); loadLiveStats(); reactions.loadCounts(); updateAllSnav(); });
