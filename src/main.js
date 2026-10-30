// 組裝:讀資料、建立狀態、接 DOM 事件、呼叫各模組。
// 狀態說明:
//   sel / modes            標籤三態與任一/全部(見 filter.js)
//   authorFilter           作者專頁
//   shelfOn / shelfTab     書架模式與分頁
//   page                   主列表目前頁數(每頁 PER 篇)
//   _mode / _cur / _annIdx 詳情視窗:'art' 文章、'ann' 公告、'tool' 書架匯出 / 匯入 / 清除;_navList = 從哪一排點開(null = 主列表目前篩選+排序)
import { loadData, sg, buildTag2Facet, sortAnnouncements, makePersonLookup } from './data.js';
import { passes, filterArticles, authorWorks, cycleTag, selectTag, removeTag, toggleMode, clearSelection, selectionChips } from './filter.js';
import { sortArticles, pickRandom } from './sort.js';
import { KEYS, loadSet, saveSet, loadShelfTab, saveShelfTab, loadTheme, saveTheme,
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
const scrollToToolbar = () => document.querySelector('.toolbar').scrollIntoView({ behavior: 'smooth' });

// ---- 狀態 ----
const sel = {}, modes = {};
let authorFilter = null, _cur = null, shelfOn = false;
let _mode = 'art', _annIdx = null, _navList = null;
const PER = 30; let page = 1;

// 我的書架:收藏 + 待閱讀 + 已讀,存瀏覽器本機
const favs = loadSet(KEYS.FAVS), readSet = loadSet(KEYS.READ), todoSet = loadSet(KEYS.TODO);
let shelfTab = loadShelfTab();
const SHELF = { fav: favs, todo: todoSet, read: readSet };

// 公開愛心數 / 觀測數
const reactions = createReactions({ favs, deadNos, onChange: () => { render(true); if (modalOpen() && _cur) openDetail(_cur); } });

// 傳給 render.js 的畫面脈絡
const ctx = { facets: D.facets, persons, deadAuthors, favs, readSet, todoSet, likeNum: reactions.likeNum, viewNum: reactions.viewNum };

const q = $('q');
const modalOpen = () => $('modal').style.display === 'flex';

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
  const b = $('shelfBtn'); if (b) { b.textContent = '📚 書架'; b.classList.toggle('on', shelfOn); }
  const tb = $('shelfTabs'); if (!tb) return;
  tb.style.display = shelfOn ? 'flex' : 'none';
  tb.innerHTML = R.shelfTabsHTML(SHELF, shelfTab) + R.shelfToolsHTML();
}

// ---- 主題切換(深/淺,記憶於 localStorage,預設深色配合品牌)----
const _root = document.documentElement;
function applyTheme(t) { _root.setAttribute('data-theme', t); const b = $('theme'); if (b) b.textContent = t === 'dark' ? '☀️' : '🌙'; saveTheme(t); }
applyTheme(loadTheme());
$('theme').onclick = () => applyTheme(_root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');

// ---- 主列表 ----
function render(keepPage) {
  if (!keepPage) page = 1;
  const list = $('list'); list.innerHTML = '';
  const hits = currentHits();
  const pages = Math.max(1, Math.ceil(hits.length / PER));
  if (page > pages) page = pages;
  $('count').textContent = `共 ${hits.length} / ${D.total} 篇`;
  { const pb = document.querySelector('.pbdone'); if (pb) pb.textContent = `看 ${hits.length} 篇 ✓`; }
  R.renderAuthorHead($('authorHead'), authorFilter, authorFilter ? authorWorks(D.articles, authorFilter, persons).length : 0, ctx,
    () => { authorFilter = null; render(); scrollToToolbar(); });
  if (!hits.length) {
    list.innerHTML = R.emptyHTML(shelfOn && SHELF[shelfTab].size === 0 ? shelfTab : null);
    $('pager').innerHTML = '';
    R.syncStyles(sel, modes); renderSelBar(); return;
  }
  R.renderCards(list, hits.slice((page - 1) * PER, page * PER), ctx, (a) => { _navList = null; openDetail(a); });
  R.renderPager($('pager'), page, pages, gotoPage);
  R.syncStyles(sel, modes); renderSelBar();
}
function gotoPage(p) { page = p; render(true); scrollToToolbar(); }
function renderSelBar() {
  R.renderSelBar($('selbar'), selectionChips(sel), {
    onRemove: (k, v) => { removeTag(sel, k, v); render(); },
    onClearAll: () => { clearSelection(sel, modes); authorFilter = null; render(); },
  });
}

// ---- 輪播:星際廣播 / 新星誕生 / 軌道更新;熱門星系 ----
function renderAnn() {
  if (!ANNS.length) return;
  $('annSec').style.display = '';
  R.renderStrip($('ann'), ANNS, { html: R.annCardHTML, cls: R.annCardCls, onClick: (x, i) => openAnn(i) });
}
function renderLatest() {
  // 最新收錄:依「建立時間(實際新增進資料庫)」由新到舊,不是按編號
  const newest = D.articles.filter((a) => a.ck).sort((a, b) => b.ck - a.ck).slice(0, 8);
  R.renderStrip($('latest'), newest, { html: R.latestCardHTML, onClick: (a) => { _navList = newest; openDetail(a); } });
}
function renderStatus() {
  const arr = D.articles.filter((a) => a.ek).sort((a, b) => b.ek - a.ek).slice(0, 8);
  R.renderStrip($('statusUpd'), arr, { html: R.statusCardHTML, onClick: (a) => { _navList = arr; openDetail(a); } });
}
function renderHot() {
  R.renderHot($('hot'), D.facets, (key, v) => { selectTag(sel, key, v); render(); scrollToToolbar(); });
}

// ---- 詳情 / 公告視窗 ----
function openAnn(i) {
  if (i < 0 || i >= ANNS.length) return;
  _mode = 'ann'; _annIdx = i; _cur = null;
  const sheet = $('sheet');
  sheet.innerHTML = R.annHTML(ANNS[i], i, ANNS.length);
  $('modal').style.display = 'flex'; sheet.scrollTop = 0;
}
function openDetail(a) {
  const changed = (_mode !== 'art' || !_cur || _cur.no !== a.no);   // 換了一篇才捲回頂端(按收藏/已讀重繪時維持位置)
  _mode = 'art'; _annIdx = null; _cur = a;
  reactions.markView(a.no);
  const sheet = $('sheet');
  const L = navArticles();
  sheet.innerHTML = R.detailHTML(a, ctx, { rel: relatedArticles(a, D.articles, 6), navIndex: L.findIndex((x) => x.no === a.no), navLen: L.length });
  $('modal').style.display = 'flex';
  if (changed) sheet.scrollTop = 0;
}
function closeDetail() { stopScan(); $('modal').style.display = 'none'; }
$('modal').onclick = (e) => { if (e.target.id === 'modal') closeDetail(); };
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
  if (e.key === 'Escape') closeDetail();
  else if (e.key === 'ArrowLeft') navDetail(-1);
  else if (e.key === 'ArrowRight') navDetail(1);
});

// ---- 書架匯出 / 匯入 / 清除所有紀錄(共用詳情的 #modal;_mode = 'tool' 時 ←→ 不會切換文章)----
function openTool(html) {
  stopScan();
  _mode = 'tool'; _cur = null; _annIdx = null;
  const sheet = $('sheet'); sheet.innerHTML = html;
  $('modal').style.display = 'flex'; sheet.scrollTop = 0;
}
function setMsg(id, text, cls) { const el = $(id); if (el) { el.textContent = text || ''; el.className = 'xmsg' + (cls ? ' ' + cls : ''); } }
// 複製到剪貼簿;不支援時退回 prompt(與「複製篩選」同一套)
function copyText(text, msgId, okText) {
  const done = (ok) => setMsg(msgId, ok ? okText : '⚠ 複製失敗,請直接全選上面的字串複製', ok ? 'ok' : 'err');
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => done(true)).catch(() => { prompt('複製這段文字:', text); done(true); });
  else { prompt('複製這段文字:', text); done(true); }
}
const siteBase = () => location.origin + location.pathname;
// 匯出:字串 + 複製 / 複製連結 / QR code(QR 內容是匯入連結,用相機掃到就直接開站)
function shelfExport() {
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
function shelfImport(prefill) {
  _imPending = null; _imText = '';
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
function toggleReport(id) { const b = $(id); if (b) b.classList.toggle('open'); }
function pickReason(btn, other) {
  const box = btn.closest('.repbox');
  box.querySelectorAll('.opts .ctl').forEach((x) => x.classList.remove('on'));
  btn.classList.add('on'); box.dataset.sel = btn.textContent.trim();   // 目前點選的回報原因
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
$('filterToggle').onclick = () => {
  const p = $('panel'); const open = p.classList.toggle('open');
  document.body.classList.toggle('noscroll', open && window.innerWidth <= 860);
};

// ---- 輪播箭頭:只在「有得捲」時出現(沒溢出全藏、捲到頭藏左、捲到底藏右)----
document.querySelectorAll('.snav').forEach((btn) => {
  btn.onclick = () => { const s = btn.parentElement.querySelector('.strip'); const amt = Math.max(220, s.clientWidth * 0.8); s.scrollBy({ left: btn.classList.contains('l') ? -amt : amt, behavior: 'smooth' }); };
});
function updateSnav(row) {
  const s = row.querySelector('.strip'); if (!s) return;
  const l = row.querySelector('.snav.l'), r = row.querySelector('.snav.r');
  const can = s.scrollWidth - s.clientWidth > 2;
  if (l) l.classList.toggle('hide', !can || s.scrollLeft <= 1);
  if (r) r.classList.toggle('hide', !can || s.scrollLeft + s.clientWidth >= s.scrollWidth - 1);
}
function updateAllSnav() { document.querySelectorAll('.striprow').forEach(updateSnav); }
document.querySelectorAll('.striprow .strip').forEach((s) => s.addEventListener('scroll', () => updateSnav(s.closest('.striprow'))));
window.addEventListener('resize', updateAllSnav);
window.addEventListener('load', updateAllSnav);
updateAllSnav();

// ---- 回到頂部 ----
const toTop = $('toTop');
window.addEventListener('scroll', () => { toTop.classList.toggle('show', window.scrollY > 400); });
toTop.onclick = () => { toTop.blur(); window.scrollTo({ top: 0, behavior: 'smooth' }); };

// ---- 頁尾:統計 / 更新時間 ----
function renderStats(s, live) { R.renderStats($('statsCard'), s || D.stats, live); }
function loadLiveStats() { fetchLiveStats().then((j) => { if (j) renderStats(j, true); }); }
if (D.updated) { $('updatedNote').textContent = '🗺️ 星圖更新:' + D.updated; }
if (D.synced) { $('syncedNote').innerHTML = '📡 訊號同步:' + D.synced + ' <span title="每天 08:31・21:01 自動更新&#10;안유진 08/31 · 장원영 09/01 🎂" style="cursor:help">🎂</span>'; }

// 詳情 / 書卡 HTML 字串裡的 inline onclick 會呼叫這些函式,所以要掛到 window(ES module 內的函式不是全域)
Object.assign(window, { toggleFav, toggleTodo, toggleRead, setShelfTab, filterByTag, filterName, openByNo, shareArticle, closeDetail, navDetail, toggleReport, pickReason, sendReport, shelfExport, shelfImport, shelfClear });

// ---- 啟動 ----
R.buildPanel($('panel'), D.facets, {
  onTag: (key, val) => { cycleTag(sel, key, val); render(); },
  onMode: (key) => { toggleMode(modes, key); render(); },
});
renderAnn(); renderLatest(); renderStatus(); renderHot(); renderStats(); loadLiveStats(); reactions.loadCounts(); updateShelfBtn(); applyShareHash(); render(); updateAllSnav(); applyImportParam(); openSharedArticle();
// PWA:註冊 service worker(可加到主畫面、離線可看)
if ('serviceWorker' in navigator) { window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {})); }
